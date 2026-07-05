from __future__ import annotations

import gc
import http.client
import json
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.http import CallPilotHandler


def end_of_call_report(call_id: str = "vapi-call-001") -> dict:
    return {
        "message": {
            "type": "end-of-call-report",
            "call": {"id": call_id, "customer": {"number": "+923005556677"}},
            "artifact": {
                "transcript": (
                    "AI: Thank you for calling BrightCare Dental Clinic.\n"
                    "User: Hi, my name is Imran Shah, I want to book a cleaning appointment on 2026-07-20 at 14:00. "
                    "My number is 0300 5556677."
                ),
                "recordingUrl": "https://storage.vapi.ai/rec-001.wav",
            },
        }
    }


class VapiWebhookTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "callpilot-test.db"
        self.patch = patch.object(storage, "DB_PATH", self.db_path)
        self.patch.start()
        storage.init_db()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), CallPilotHandler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.patch.stop()
        gc.collect()
        self.temp_dir.cleanup()

    def post(self, payload: dict, secret: str | None = None, path: str = "/api/vapi/webhook"):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Content-Type": "application/json"}
        if secret is not None:
            headers["X-Vapi-Secret"] = secret
        connection.request("POST", path, body=json.dumps(payload), headers=headers)
        response = connection.getresponse()
        body = json.loads(response.read().decode("utf-8"))
        connection.close()
        return response.status, body

    def test_end_of_call_report_creates_lead(self) -> None:
        status, body = self.post(end_of_call_report())
        self.assertEqual(status, 200)
        self.assertTrue(body["handled"])
        with storage.db() as conn:
            lead = conn.execute("select * from leads where id=?", (body["lead_id"],)).fetchone()
            call_log = conn.execute(
                "select * from call_logs where provider='vapi' and call_id='vapi-call-001'"
            ).fetchone()
        self.assertIsNotNone(lead)
        self.assertIn("Imran Shah", lead["customer_name"] or "")
        self.assertEqual(lead["timeline"], "2026-07-20")
        self.assertIsNotNone(call_log)
        self.assertEqual(call_log["recording_url"], "https://storage.vapi.ai/rec-001.wav")

    def test_duplicate_report_does_not_create_second_lead(self) -> None:
        _, first = self.post(end_of_call_report("dup-call"))
        _, second = self.post(end_of_call_report("dup-call"))
        self.assertTrue(first["handled"])
        self.assertFalse(second["handled"])
        self.assertEqual(second["reason"], "duplicate")
        with storage.db() as conn:
            count = conn.execute(
                "select count(*) from call_logs where provider='vapi' and call_id='dup-call'"
            ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_secret_is_enforced_when_configured(self) -> None:
        with patch.dict(os.environ, {"VAPI_WEBHOOK_SECRET": "topsecret123"}, clear=False):
            bad_status, _ = self.post(end_of_call_report("sec-1"), secret="wrong")
            missing_status, _ = self.post(end_of_call_report("sec-2"))
            good_status, good_body = self.post(end_of_call_report("sec-3"), secret="topsecret123")
        self.assertEqual(bad_status, 403)
        self.assertEqual(missing_status, 403)
        self.assertEqual(good_status, 200)
        self.assertTrue(good_body["handled"])

    def test_other_message_types_are_acknowledged_not_ingested(self) -> None:
        status, body = self.post({"message": {"type": "status-update", "status": "in-progress"}})
        self.assertEqual(status, 200)
        self.assertFalse(body["handled"])
        with storage.db() as conn:
            count = conn.execute("select count(*) from call_logs where provider='vapi'").fetchone()[0]
        self.assertEqual(count, 0)

    def test_webhook_is_reachable_with_auth_enabled(self) -> None:
        with patch.dict(os.environ, {"AUTH_REQUIRED": "true"}, clear=False):
            status, body = self.post(end_of_call_report("auth-call"))
        self.assertEqual(status, 200)
        self.assertTrue(body["handled"])


if __name__ == "__main__":
    unittest.main()
