from __future__ import annotations

import gc
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.repositories import get_businesses
from callpilot.views.calendar_page import parse_booking_date, render_calendar, week_start_for


class CalendarUnitTest(unittest.TestCase):
    def test_parse_booking_date_formats(self) -> None:
        self.assertEqual(parse_booking_date("2026-07-10"), date(2026, 7, 10))
        self.assertEqual(parse_booking_date("10/07/2026"), date(2026, 7, 10))
        self.assertIsNone(parse_booking_date("tomorrow"))
        self.assertIsNone(parse_booking_date(None))

    def test_week_start_is_monday(self) -> None:
        start = week_start_for({"start": ["2026-07-10"]})  # a Friday
        self.assertEqual(start, date(2026, 7, 6))  # that week's Monday
        self.assertEqual(start.weekday(), 0)


class CalendarPageTest(unittest.TestCase):
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

    def seed_booking(self, requested_date: str, requested_time: str = "15:00", status: str = "confirmed") -> None:
        with storage.db() as conn:
            clinic = [row for row in get_businesses(conn) if row["business_type"] in {"Clinic", "Dentist"}][0]
            conn.execute(
                """
                insert into bookings (
                    workspace_id, business_id, customer_name, booking_type, service_requested,
                    requested_date, requested_time, status
                )
                values (?, ?, 'Calendar Patient', 'Consultation', 'Checkup', ?, ?, ?)
                """,
                (clinic["workspace_id"], clinic["id"], requested_date, requested_time, status),
            )
            conn.commit()

    def test_scheduled_booking_appears_in_week_grid(self) -> None:
        monday = date.today() - timedelta(days=date.today().weekday())
        target = monday + timedelta(days=2)
        self.seed_booking(target.isoformat())
        html = render_calendar({})
        self.assertIn("Appointment Calendar", html)
        self.assertIn("Calendar Patient", html)
        self.assertIn("15:00", html)

    def test_unparseable_dates_go_to_needs_date_bucket(self) -> None:
        self.seed_booking("next week sometime")
        html = render_calendar({})
        self.assertIn("Needs a confirmed date", html)
        self.assertIn("Calendar Patient", html)

    def test_week_navigation_moves_booking_out_of_view(self) -> None:
        monday = date.today() - timedelta(days=date.today().weekday())
        self.seed_booking(monday.isoformat())
        next_week = (monday + timedelta(days=7)).isoformat()
        html = render_calendar({"start": [next_week]})
        # Booking is scheduled this week, so next week's grid must not show it.
        self.assertNotIn("Calendar Patient", html)


if __name__ == "__main__":
    unittest.main()
