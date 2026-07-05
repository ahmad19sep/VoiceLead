from __future__ import annotations

import gc
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.compliance import record_consent
from callpilot.jobs import run_due_jobs
from callpilot.reminders import (
    REMINDER_SCRIPTS,
    build_reminder_message,
    next_window_start,
    parse_call_window,
    schedule_appointment_reminders,
    within_call_window,
)
from callpilot.repositories import get_businesses


class ReminderUnitTest(unittest.TestCase):
    def test_scripts_cover_three_languages_with_opt_out(self) -> None:
        self.assertEqual(set(REMINDER_SCRIPTS), {"en", "ur", "ar"})
        self.assertIn("opt out", REMINDER_SCRIPTS["en"])
        self.assertIn("band karwane", REMINDER_SCRIPTS["ur"])
        self.assertIn("لإيقاف", REMINDER_SCRIPTS["ar"])

    def test_build_reminder_message_formats_details(self) -> None:
        message = build_reminder_message("BrightCare", "ur", "2026-07-10", "15:00")
        self.assertIn("BrightCare", message)
        self.assertIn("2026-07-10", message)
        self.assertIn("15:00", message)

    def test_call_window_parsing_and_checks(self) -> None:
        window = parse_call_window("09:00-18:00 local time unless the client policy says otherwise.")
        self.assertEqual(window, ((9, 0), (18, 0)))
        self.assertTrue(within_call_window(window, datetime(2026, 7, 5, 10, 30)))
        self.assertFalse(within_call_window(window, datetime(2026, 7, 5, 22, 0)))
        resume = next_window_start(window, datetime(2026, 7, 5, 22, 0))
        self.assertEqual((resume.day, resume.hour, resume.minute), (6, 9, 0))
        self.assertEqual(parse_call_window("no window here"), ((9, 0), (20, 0)))


class ReminderJobTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "callpilot-test.db"
        self.patch = patch.object(storage, "DB_PATH", self.db_path)
        self.patch.start()
        storage.init_db()
        with storage.db() as conn:
            clinic = [row for row in get_businesses(conn) if row["name"] == "BrightCare Dental Clinic"][0]
            self.business_id = int(clinic["id"])
            self.workspace_id = int(clinic["workspace_id"])
            conn.execute(
                "update clinic_profiles set reminders_enabled=1 where business_id=?",
                (self.business_id,),
            )
            conn.commit()

    def tearDown(self) -> None:
        self.patch.stop()
        gc.collect()
        self.temp_dir.cleanup()

    def enable_outbound(self, conn, phone: str) -> None:
        conn.execute(
            "update businesses set max_outbound_attempts=1 where id=?",
            (self.business_id,),
        )
        record_consent(conn, self.business_id, phone, "outbound_call", "test", "unit-test opt-in", self.workspace_id)

    def new_confirmed_booking(self, phone: str = "+92 300 5556677") -> int:
        with storage.db() as conn:
            booking_id = int(
                conn.execute(
                    """
                    insert into bookings (
                        workspace_id, business_id, customer_name, customer_phone, booking_type,
                        requested_date, requested_time, status
                    )
                    values (?, ?, 'Reminder Patient', ?, 'Consultation', '2026-07-10', '15:00', 'confirmed')
                    """,
                    (self.workspace_id, self.business_id, phone),
                ).lastrowid
            )
            conn.commit()
        return booking_id

    def test_schedules_exactly_one_job_per_booking(self) -> None:
        booking_id = self.new_confirmed_booking()
        with storage.db() as conn:
            first = schedule_appointment_reminders(conn)
            second = schedule_appointment_reminders(conn)
            conn.commit()
            jobs = conn.execute(
                "select * from jobs where job_type='appointment_reminder' and resource_id=?",
                (str(booking_id),),
            ).fetchall()
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["max_attempts"], 1)

    def test_reminder_scheduled_at_offset_before_appointment(self) -> None:
        booking_id = self.new_confirmed_booking()
        with storage.db() as conn:
            schedule_appointment_reminders(conn)
            conn.commit()
            job = conn.execute(
                "select scheduled_at from jobs where job_type='appointment_reminder' and resource_id=?",
                (str(booking_id),),
            ).fetchone()
        # 24h offset before 2026-07-10 15:00
        self.assertEqual(job["scheduled_at"], "2026-07-09 15:00:00")

    def test_opt_out_and_policy_suppress_reminder(self) -> None:
        booking_id = self.new_confirmed_booking()
        with storage.db() as conn:
            # Outbound stays disabled (max_outbound_attempts=0) -> suppressed by policy.
            conn.execute(
                "update jobs set scheduled_at='2000-01-01 00:00:00' where 1=0"
            )
            schedule_appointment_reminders(conn)
            conn.execute(
                "update jobs set scheduled_at=datetime('now','-1 hour') where job_type='appointment_reminder'"
            )
            with patch("callpilot.reminders.within_call_window", return_value=True):
                results = run_due_jobs(conn, workspace_id=self.workspace_id)
            conn.commit()
            suppressed_audit = conn.execute(
                "select count(*) from audit_logs where action='reminder_suppressed'"
            ).fetchone()[0]
            booking = conn.execute("select status from bookings where id=?", (booking_id,)).fetchone()

        reminder_results = [r for r in results if r["result"].get("status") == "suppressed"]
        self.assertEqual(len(reminder_results), 1)
        self.assertEqual(suppressed_audit, 1)
        self.assertEqual(booking["status"], "confirmed")

    def test_quiet_hours_defer_without_consuming_attempt(self) -> None:
        phone = "+92 300 5556677"
        self.new_confirmed_booking(phone)
        with storage.db() as conn:
            self.enable_outbound(conn, phone)
            schedule_appointment_reminders(conn)
            conn.execute(
                "update jobs set scheduled_at=datetime('now','-1 hour') where job_type='appointment_reminder'"
            )
            with patch("callpilot.reminders.within_call_window", return_value=False):
                results = run_due_jobs(conn, workspace_id=self.workspace_id)
            conn.commit()
            job = conn.execute(
                "select status, attempts from jobs where job_type='appointment_reminder'"
            ).fetchone()

        deferred = [r for r in results if r["status"] == "deferred"]
        self.assertEqual(len(deferred), 1)
        self.assertEqual(job["status"], "pending")
        self.assertEqual(job["attempts"], 0)

    def test_provider_unavailable_is_honest_and_single_attempt(self) -> None:
        phone = "+92 300 5556677"
        booking_id = self.new_confirmed_booking(phone)
        with storage.db() as conn:
            self.enable_outbound(conn, phone)
            schedule_appointment_reminders(conn)
            conn.execute(
                "update jobs set scheduled_at=datetime('now','-1 hour') where job_type='appointment_reminder'"
            )
            with patch("callpilot.reminders.within_call_window", return_value=True):
                results = run_due_jobs(conn, workspace_id=self.workspace_id)
            conn.commit()
            job = conn.execute(
                "select status, attempts from jobs where job_type='appointment_reminder'"
            ).fetchone()
            booking = conn.execute("select status from bookings where id=?", (booking_id,)).fetchone()
            notification = conn.execute(
                "select * from notifications where notification_type='appointment_reminder'"
            ).fetchone()

        reminder = [r for r in results if r["result"].get("status") == "provider_unavailable"]
        self.assertEqual(len(reminder), 1)
        # No Twilio configured: booking must NOT be marked reminded, notification failed.
        self.assertEqual(booking["status"], "confirmed")
        self.assertEqual(notification["status"], "failed")
        self.assertIn("(ur)", notification["subject"])
        self.assertIn("band karwane", notification["message"])
        # Max one attempt: job completed, never retried.
        self.assertEqual(job["status"], "completed")
        self.assertEqual(job["attempts"], 1)
        with storage.db() as conn:
            second = run_due_jobs(conn, workspace_id=self.workspace_id)
        self.assertEqual([r for r in second if r.get("result", {}).get("status") == "provider_unavailable"], [])

    def test_delivered_reminder_transitions_booking_to_reminded(self) -> None:
        phone = "+92 300 5556677"
        booking_id = self.new_confirmed_booking(phone)
        from callpilot.providers import ProviderResult

        fake = ProviderResult(True, "Twilio Voice", "create_outbound_call", "ok", "CA" + "a" * 32, "created")
        with storage.db() as conn:
            self.enable_outbound(conn, phone)
            schedule_appointment_reminders(conn)
            conn.execute(
                "update jobs set scheduled_at=datetime('now','-1 hour') where job_type='appointment_reminder'"
            )
            with patch("callpilot.reminders.within_call_window", return_value=True), patch(
                "callpilot.providers.create_outbound_call", return_value=fake
            ):
                results = run_due_jobs(conn, workspace_id=self.workspace_id)
            conn.commit()
            booking = conn.execute("select status from bookings where id=?", (booking_id,)).fetchone()
            transition = conn.execute(
                "select * from clinic_workflow_transitions where booking_id=? and to_status='reminded'",
                (booking_id,),
            ).fetchone()

        delivered = [r for r in results if r["result"].get("status") == "delivered"]
        self.assertEqual(len(delivered), 1)
        self.assertEqual(booking["status"], "reminded")
        self.assertIsNotNone(transition)
        self.assertEqual(transition["idempotency_key"], f"appointment-reminder-{booking_id}")


if __name__ == "__main__":
    unittest.main()
