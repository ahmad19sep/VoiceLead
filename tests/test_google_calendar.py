from __future__ import annotations

import base64
import gc
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot import google_calendar
from callpilot.calendar import GoogleCalendarAdapter
from callpilot.repositories import get_businesses
from callpilot.scheduling import sync_booking


def make_service_account() -> dict[str, str]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return {"client_email": "callpilot@test-project.iam.gserviceaccount.com", "private_key": pem}


SERVICE_ACCOUNT = make_service_account()
FAKE_ENV = {
    "GOOGLE_CALENDAR_ID": "clinic-demo@group.calendar.google.com",
    "GOOGLE_CALENDAR_CREDENTIALS": json.dumps(SERVICE_ACCOUNT),
}


def b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


class JwtAndBodyTest(unittest.TestCase):
    def test_signed_jwt_has_correct_claims(self) -> None:
        token = google_calendar.build_signed_jwt(SERVICE_ACCOUNT, now=1_700_000_000)
        header_raw, claims_raw, signature = token.split(".")
        header = json.loads(b64url_decode(header_raw))
        claims = json.loads(b64url_decode(claims_raw))
        self.assertEqual(header, {"alg": "RS256", "typ": "JWT"})
        self.assertEqual(claims["iss"], SERVICE_ACCOUNT["client_email"])
        self.assertEqual(claims["aud"], google_calendar.TOKEN_URL)
        self.assertEqual(claims["exp"] - claims["iat"], 3600)
        self.assertTrue(signature)

    def test_client_ready_reports_missing_pieces(self) -> None:
        with patch.dict(os.environ, {"GOOGLE_CALENDAR_ID": "", "GOOGLE_CALENDAR_CREDENTIALS": ""}, clear=False):
            ready, reason = google_calendar.client_ready()
        self.assertFalse(ready)
        self.assertIn("GOOGLE_CALENDAR_ID", reason)
        with patch.dict(os.environ, FAKE_ENV, clear=False):
            ready, reason = google_calendar.client_ready()
        self.assertTrue(ready)

    def test_event_body_from_booking(self) -> None:
        booking = {
            "customer_name": "Fatima Khan",
            "service_requested": "Cleaning",
            "customer_phone": "0300 5551122",
            "requested_date": "2026-07-08",
            "requested_time": "11:00",
        }
        body = google_calendar.event_body(booking)
        self.assertIn("Fatima Khan", body["summary"])
        self.assertEqual(body["start"]["dateTime"], "2026-07-08T11:00:00")
        self.assertEqual(body["end"]["dateTime"], "2026-07-08T11:30:00")
        self.assertEqual(body["start"]["timeZone"], "Asia/Karachi")
        self.assertIsNone(google_calendar.event_body({"requested_date": "next week"}))


class LiveAdapterFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "callpilot-test.db"
        self.patch = patch.object(storage, "DB_PATH", self.db_path)
        self.patch.start()
        storage.init_db()
        self.env = patch.dict(os.environ, FAKE_ENV, clear=False)
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.patch.stop()
        gc.collect()
        self.temp_dir.cleanup()

    def new_booking(self, status: str = "requested") -> int:
        with storage.db() as conn:
            clinic = [row for row in get_businesses(conn) if row["name"] == "BrightCare Dental Clinic"][0]
            booking_id = int(
                conn.execute(
                    """
                    insert into bookings (
                        workspace_id, business_id, customer_name, customer_phone, booking_type,
                        service_requested, requested_date, requested_time, status
                    )
                    values (?, ?, 'Fatima Khan', '0300 5551122', 'Consultation', 'Cleaning',
                            '2026-07-08', '11:00', ?)
                    """,
                    (clinic["workspace_id"], clinic["id"], status),
                ).lastrowid
            )
            conn.commit()
        return booking_id

    def test_adapter_reports_production_ready_with_credentials(self) -> None:
        adapter = GoogleCalendarAdapter()
        self.assertTrue(adapter.connected())
        self.assertTrue(adapter.production_ready())

    def test_create_sync_stores_real_event_id(self) -> None:
        booking_id = self.new_booking()
        with patch.object(google_calendar, "api_request", return_value={"id": "evt_google_123"}) as api:
            with storage.db() as conn:
                result = sync_booking(conn, booking_id, "create")
                conn.commit()
                booking = dict(conn.execute("select * from bookings where id=?", (booking_id,)).fetchone())
        self.assertEqual(result["sync_status"], "confirmed")
        self.assertEqual(result["event_id"], "evt_google_123")
        self.assertEqual(booking["calendar_event_id"], "evt_google_123")
        self.assertEqual(booking["calendar_sync_status"], "confirmed")
        method, path = api.call_args[0][0], api.call_args[0][1]
        self.assertEqual(method, "POST")
        self.assertIn("/events", path)

    def test_cancel_sync_deletes_event(self) -> None:
        booking_id = self.new_booking("confirmed")
        with storage.db() as conn:
            conn.execute(
                "update bookings set calendar_event_id='evt_google_123', calendar_sync_status='confirmed' where id=?",
                (booking_id,),
            )
            conn.commit()
        with patch.object(google_calendar, "api_request", return_value={}) as api:
            with storage.db() as conn:
                result = sync_booking(conn, booking_id, "cancel")
                conn.commit()
        self.assertEqual(result["sync_status"], "cancelled")
        self.assertEqual(api.call_args[0][0], "DELETE")
        self.assertIn("evt_google_123", api.call_args[0][1])

    def test_api_error_keeps_booking_pending_not_fake_confirmed(self) -> None:
        booking_id = self.new_booking()
        with patch.object(google_calendar, "api_request", side_effect=RuntimeError("Google Calendar API 403: denied")):
            with storage.db() as conn:
                result = sync_booking(conn, booking_id, "create")
                conn.commit()
                booking = dict(conn.execute("select * from bookings where id=?", (booking_id,)).fetchone())
        self.assertEqual(result["sync_status"], "pending")
        self.assertIsNone(booking["calendar_event_id"])
        self.assertIn("403", booking["calendar_message"])

    def test_unparseable_date_refuses_event(self) -> None:
        with storage.db() as conn:
            clinic = [row for row in get_businesses(conn) if row["name"] == "BrightCare Dental Clinic"][0]
            booking_id = int(
                conn.execute(
                    """
                    insert into bookings (workspace_id, business_id, customer_name, booking_type,
                                          requested_date, status)
                    values (?, ?, 'Vague Caller', 'Consultation', 'next week sometime', 'requested')
                    """,
                    (clinic["workspace_id"], clinic["id"]),
                ).lastrowid
            )
            conn.commit()
        with patch.object(google_calendar, "api_request") as api:
            with storage.db() as conn:
                result = sync_booking(conn, booking_id, "create")
                conn.commit()
        api.assert_not_called()
        self.assertEqual(result["sync_status"], "pending")
        self.assertIn("parseable", result["message"])


if __name__ == "__main__":
    unittest.main()
