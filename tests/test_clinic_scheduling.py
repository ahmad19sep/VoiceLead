from __future__ import annotations

import gc
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.calendar import GoogleCalendarAdapter, calendar_adapter
from callpilot.clinic_workflow import apply_booking_transition
from callpilot.repositories import get_businesses
from callpilot.scheduling import get_booking_calendar_syncs, sync_booking


class ClinicSchedulingTest(unittest.TestCase):
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

    def booking_row(self, booking_id: int) -> dict:
        with storage.db() as conn:
            return dict(conn.execute("select * from bookings where id = ?", (booking_id,)).fetchone())

    def test_unconnected_calendar_leaves_booking_pending_without_event_id(self) -> None:
        booking_id = self.new_booking("requested")
        with storage.db() as conn:
            result = sync_booking(conn, booking_id, "create")
            conn.commit()

        self.assertFalse(result["event_id"])
        self.assertEqual(result["sync_status"], "pending")
        booking = self.booking_row(booking_id)
        self.assertIsNone(booking["calendar_event_id"])
        self.assertEqual(booking["calendar_sync_status"], "pending")

    def test_connected_but_no_client_still_refuses_fake_event_id(self) -> None:
        booking_id = self.new_booking("requested")
        env = {"GOOGLE_CALENDAR_ID": "clinic@group.calendar.google.com", "GOOGLE_CALENDAR_CREDENTIALS": "{}"}
        with patch.dict(os.environ, env, clear=False):
            adapter = GoogleCalendarAdapter()
            self.assertTrue(adapter.connected())
            self.assertFalse(adapter.production_ready())
            with storage.db() as conn:
                result = sync_booking(conn, booking_id, "create")
                conn.commit()

        # Credentials present but no live client: honest pending, still no fabricated id.
        self.assertFalse(result["event_id"])
        self.assertEqual(result["sync_status"], "pending")
        self.assertIn("not wired", result["message"])

    def test_confirm_transition_triggers_pending_calendar_sync(self) -> None:
        booking_id = self.new_booking("requested")
        with storage.db() as conn:
            outcome = apply_booking_transition(conn, booking_id, "confirmed")
            conn.commit()
            syncs = get_booking_calendar_syncs(conn, booking_id)

        self.assertIsNotNone(outcome["calendar"])
        self.assertEqual(outcome["calendar"]["action"], "create")
        self.assertEqual(len(syncs), 1)
        self.assertEqual(syncs[0]["action"], "create")
        self.assertEqual(syncs[0]["status"], "pending")

    def test_cancel_transition_triggers_cancel_sync(self) -> None:
        booking_id = self.new_booking("confirmed")
        with storage.db() as conn:
            apply_booking_transition(conn, booking_id, "cancelled")
            conn.commit()
            syncs = get_booking_calendar_syncs(conn, booking_id)

        actions = [s["action"] for s in syncs]
        self.assertIn("cancel", actions)
        booking = self.booking_row(booking_id)
        self.assertEqual(booking["calendar_sync_status"], "pending_cancel")

    def test_default_adapter_is_google_calendar(self) -> None:
        self.assertEqual(calendar_adapter().key, "google_calendar")


if __name__ == "__main__":
    unittest.main()
