from __future__ import annotations

import gc
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.compliance import (
    default_workspace_id,
    reset_request_context,
    set_request_context,
    upsert_workspace_user,
)
from callpilot.http import CallPilotHandler
from callpilot.repositories import get_businesses
from callpilot.sessions import SESSION_COOKIE, sign_session, verify_session
from callpilot.utils import now


class SessionContextTest(unittest.TestCase):
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

    def test_signed_session_rejects_tampering(self) -> None:
        value = sign_session({"workspace_id": 123, "user_email": "owner@example.com"})

        self.assertEqual(verify_session(value)["workspace_id"], 123)
        self.assertEqual(verify_session(value + "broken"), {})

    def test_repository_defaults_follow_request_workspace_context(self) -> None:
        with storage.db() as conn:
            default_id = default_workspace_id(conn)
            other_id, _business_id = self.create_workspace_with_business(conn)

            default_businesses = get_businesses(conn)
            tokens = set_request_context(other_id, "owner@other.test")
            try:
                other_businesses = get_businesses(conn)
            finally:
                reset_request_context(tokens)

        self.assertTrue(default_businesses)
        self.assertEqual({row["workspace_id"] for row in default_businesses}, {default_id})
        self.assertEqual([row["name"] for row in other_businesses], ["Other Session Clinic"])

    def test_workspace_switch_sets_cookie_for_api_context(self) -> None:
        with storage.db() as conn:
            other_id, _business_id = self.create_workspace_with_business(conn)
            upsert_workspace_user(conn, other_id, "Other Owner", "owner@other.test", "owner")

        server = ThreadingHTTPServer(("127.0.0.1", 0), CallPilotHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            payload = urllib.parse.urlencode({"workspace_id": str(other_id), "next": "/api/workspace"}).encode("utf-8")
            request = urllib.request.Request(
                f"{base_url}/workspace/switch",
                data=payload,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            opener = urllib.request.build_opener(NoRedirectHandler)
            try:
                response = opener.open(request, timeout=5)
            except urllib.error.HTTPError as exc:
                if exc.code != 303:
                    raise
                response = exc
            cookie = response.headers["Set-Cookie"].split(";", 1)[0]

            api_request = urllib.request.Request(f"{base_url}/api/workspace", headers={"Cookie": cookie})
            with urllib.request.urlopen(api_request, timeout=5) as api_response:
                data = json.loads(api_response.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(response.status, 303)
        self.assertEqual(data["workspace"]["id"], other_id)
        self.assertEqual(data["current_user"]["email"], "owner@other.test")

    def test_viewer_session_cannot_use_protected_post_route(self) -> None:
        with storage.db() as conn:
            workspace_id = default_workspace_id(conn)
            upsert_workspace_user(conn, workspace_id, "View Only", "viewer@example.com", "viewer")

        server = ThreadingHTTPServer(("127.0.0.1", 0), CallPilotHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        cookie = f"{SESSION_COOKIE}=" + sign_session(
            {"workspace_id": workspace_id, "user_email": "viewer@example.com"}
        )
        try:
            payload = json.dumps({"business_id": 1, "transcript": "Caller wants a callback."}).encode("utf-8")
            request = urllib.request.Request(
                f"{base_url}/api/ai/analyze-call",
                data=payload,
                method="POST",
                headers={"Content-Type": "application/json", "Cookie": cookie},
            )
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request, timeout=5)
            body = json.loads(raised.exception.read().decode("utf-8"))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(raised.exception.code, 403)
        self.assertFalse(body["success"])
        self.assertEqual(body["required_permission"], "place_calls")

    def create_workspace_with_business(self, conn: object) -> tuple[int, int]:
        timestamp = now()
        workspace_id = int(
            conn.execute(
                """
                insert into workspaces (name, slug, plan, status, timezone, created_at, updated_at)
                values ('Other Workspace', 'other-session', 'demo', 'active', 'UTC', ?, ?)
                """,
                (timestamp, timestamp),
            ).lastrowid
        )
        business_id = int(
            conn.execute(
                """
                insert into businesses (
                    workspace_id, name, business_type, agent_name, status, created_at, updated_at
                )
                values (?, 'Other Session Clinic', 'Clinic', 'Other Agent', 'active', ?, ?)
                """,
                (workspace_id, timestamp, timestamp),
            ).lastrowid
        )
        return workspace_id, business_id


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


if __name__ == "__main__":
    unittest.main()
