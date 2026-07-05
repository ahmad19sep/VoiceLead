from __future__ import annotations

import gc
import http.client
import os
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.auth import authenticate, ensure_demo_viewer, reset_rate_limiter
from callpilot.http import CallPilotHandler


VIEWER_ENV = {
    "AUTH_REQUIRED": "true",
    "DEMO_VIEWER_EMAIL": "prospect@demo.example",
    "DEMO_VIEWER_PASSWORD": "look-but-dont-touch",
}


class DemoViewerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "callpilot-test.db"
        self.patch = patch.object(storage, "DB_PATH", self.db_path)
        self.patch.start()
        storage.init_db()
        reset_rate_limiter()
        self.env = patch.dict(os.environ, VIEWER_ENV, clear=False)
        self.env.start()
        with storage.db() as conn:
            ensure_demo_viewer(conn)
            conn.commit()

    def tearDown(self) -> None:
        self.env.stop()
        self.patch.stop()
        gc.collect()
        self.temp_dir.cleanup()
        reset_rate_limiter()

    def test_viewer_account_is_seeded_with_viewer_role(self) -> None:
        with storage.db() as conn:
            user, _ = authenticate(conn, "prospect@demo.example", "look-but-dont-touch")
            rerun_is_idempotent = ensure_demo_viewer(conn)
            count = conn.execute(
                "select count(*) from workspace_users where lower(email)='prospect@demo.example'"
            ).fetchone()[0]
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "viewer")
        self.assertIsNone(rerun_is_idempotent)
        self.assertEqual(count, 1)

    def test_viewer_can_browse_but_cannot_mutate(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), CallPilotHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def request(method: str, path: str, body: str | None = None, cookie: str | None = None):
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
                headers = {"Content-Type": "application/x-www-form-urlencoded"}
                if cookie:
                    headers["Cookie"] = cookie
                connection.request(method, path, body=body, headers=headers)
                response = connection.getresponse()
                payload = response.read().decode("utf-8", errors="replace")
                set_cookie = response.getheader("Set-Cookie")
                connection.close()
                return response.status, payload, set_cookie

            status, _, set_cookie = request(
                "POST", "/login", "email=prospect@demo.example&password=look-but-dont-touch"
            )
            self.assertEqual(status, 303)
            cookie = set_cookie.split(";")[0]

            browse_status, browse_body, _ = request("GET", "/", cookie=cookie)
            self.assertEqual(browse_status, 200)
            self.assertIn("Dashboard", browse_body)

            mutate_status, _, _ = request(
                "POST", "/jobs/run", "", cookie=cookie
            )
            self.assertEqual(mutate_status, 403)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
