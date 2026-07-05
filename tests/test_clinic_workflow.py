from __future__ import annotations

import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.clinic_workflow import (
    WorkflowError,
    apply_booking_transition,
    get_booking_transitions,
)
from callpilot.repositories import get_businesses
from callpilot.workflows import create_booking


class ClinicWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "callpilot-test.db"
        self.patch = patch.object(storage, "DB_PATH", self.db_path)
        self.patch.start()
        storage.init_db()

    def tearDown(self) -> None:
        self.patch.stop()
        gc.collect()
        self.temp_dir.cleanup()

    def clinic_id(self) -> tuple[int, int]:
        with storage.db() as conn:
            clinic = [row for row in get_businesses(conn) if row["name"] == "BrightCare Dental Clinic"][0]
            return int(clinic["id"]), int(clinic["workspace_id"])

    def new_booking(self, status: str = "requested") -> int:
        business_id, workspace_id = self.clinic_id()
        with storage.db() as conn:
            booking_id = int(
                conn.execute(
                    """
                    insert into bookings (workspace_id, business_id, customer_name, booking_type, status)
                    values (?, ?, 'Test Patient', 'Consultation', ?)
                    """,
                    (workspace_id, business_id, status),
                ).lastrowid
            )
            conn.commit()
        return booking_id

    def booking_status(self, booking_id: int) -> str:
        with storage.db() as conn:
            return conn.execute("select status from bookings where id = ?", (booking_id,)).fetchone()["status"]

    def test_valid_transitions_are_applied_and_recorded(self) -> None:
        booking_id = self.new_booking("requested")
        with storage.db() as conn:
            apply_booking_transition(conn, booking_id, "confirmed")
            apply_booking_transition(conn, booking_id, "completed")
            conn.commit()
            transitions = get_booking_transitions(conn, booking_id)

        self.assertEqual(self.booking_status(booking_id), "completed")
        pairs = [(t["from_status"], t["to_status"]) for t in transitions]
        self.assertEqual(pairs, [("requested", "confirmed"), ("confirmed", "completed")])
        with storage.db() as conn:
            audit_count = conn.execute(
                "select count(*) from audit_logs where action = 'clinic_workflow_transition' and resource_id = ?",
                (str(booking_id),),
            ).fetchone()[0]
        self.assertEqual(audit_count, 2)

    def test_invalid_transition_is_rejected(self) -> None:
        booking_id = self.new_booking("requested")
        with storage.db() as conn:
            with self.assertRaises(WorkflowError):
                apply_booking_transition(conn, booking_id, "completed")
            conn.commit()

        self.assertEqual(self.booking_status(booking_id), "requested")
        with storage.db() as conn:
            rejected = conn.execute(
                "select count(*) from audit_logs where action = 'clinic_workflow_transition_rejected'"
            ).fetchone()[0]
            transitions = get_booking_transitions(conn, booking_id)
        self.assertEqual(rejected, 1)
        self.assertEqual(transitions, [])

    def test_terminal_state_cannot_transition(self) -> None:
        booking_id = self.new_booking("cancelled")
        with storage.db() as conn:
            with self.assertRaises(WorkflowError):
                apply_booking_transition(conn, booking_id, "confirmed")
            conn.commit()
        self.assertEqual(self.booking_status(booking_id), "cancelled")

    def test_idempotency_key_prevents_double_apply(self) -> None:
        booking_id = self.new_booking("requested")
        with storage.db() as conn:
            first = apply_booking_transition(conn, booking_id, "confirmed", idempotency_key="abc-123")
            second = apply_booking_transition(conn, booking_id, "confirmed", idempotency_key="abc-123")
            conn.commit()
            transitions = get_booking_transitions(conn, booking_id)

        self.assertTrue(first["applied"])
        self.assertFalse(first["idempotent"])
        self.assertFalse(second["applied"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(len(transitions), 1)
        self.assertEqual(self.booking_status(booking_id), "confirmed")

    def test_created_booking_records_initial_state(self) -> None:
        business_id, workspace_id = self.clinic_id()
        with storage.db() as conn:
            lead_id = int(
                conn.execute(
                    "insert into leads (workspace_id, business_id, customer_name) values (?, ?, 'Init Patient')",
                    (workspace_id, business_id),
                ).lastrowid
            )
            create_booking(conn, business_id, lead_id, {"customer_name": "Init Patient"})
            conn.commit()
            booking = conn.execute(
                "select id from bookings where lead_id = ?", (lead_id,)
            ).fetchone()
            transitions = get_booking_transitions(conn, int(booking["id"]))

        self.assertEqual(len(transitions), 1)
        self.assertIsNone(transitions[0]["from_status"])
        self.assertEqual(transitions[0]["to_status"], "requested")
        self.assertEqual(transitions[0]["actor"], "system")


if __name__ == "__main__":
    unittest.main()
