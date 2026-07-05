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
from callpilot.auth import (
    authenticate,
    ensure_owner_credentials,
    hash_password,
    is_locked_out,
    reset_rate_limiter,
    set_password,
    verify_password,
)
from callpilot.compliance import DEFAULT_OPERATOR_EMAIL
from callpilot.http import CallPilotHandler


class PasswordHashingTest(unittest.TestCase):
    def test_hash_and_verify_roundtrip(self) -> None:
        stored = hash_password("correct horse battery")
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password("correct horse battery", stored))
        self.assertFalse(verify_password("wrong password!", stored))

    def test_salts_are_unique(self) -> None:
        self.assertNotEqual(hash_password("same password"), hash_password("same password"))

    def test_verify_handles_garbage(self) -> None:
        self.assertFalse(verify_password("x", None))
        self.assertFalse(verify_password("x", "not-a-hash"))
        self.assertFalse(verify_password("x", "md5$1$aa$bb"))


class AuthDbTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "callpilot-test.db"
        self.patch = patch.object(storage, "DB_PATH", self.db_path)
        self.patch.start()
        storage.init_db()
        reset_rate_limiter()

    def tearDown(self) -> None:
        self.patch.stop()
        gc.collect()
        self.temp_dir.cleanup()
        reset_rate_limiter()

    def test_authenticate_seeded_owner_after_set_password(self) -> None:
        with storage.db() as conn:
            set_password(conn, DEFAULT_OPERATOR_EMAIL, "a-strong-password")
            conn.commit()
            user, message = authenticate(conn, DEFAULT_OPERATOR_EMAIL, "a-strong-password")
            bad_user, bad_message = authenticate(conn, DEFAULT_OPERATOR_EMAIL, "wrong-password-1")
            audit = conn.execute(
                "select count(*) from audit_logs where action='login_succeeded'"
            ).fetchone()[0]

        self.assertIsNotNone(user)
        self.assertEqual(user["email"], DEFAULT_OPERATOR_EMAIL)
        self.assertIsNone(bad_user)
        self.assertEqual(bad_message, "Invalid email or password.")
        self.assertEqual(audit, 1)

    def test_short_password_rejected(self) -> None:
        with storage.db() as conn:
            with self.assertRaises(ValueError):
                set_password(conn, DEFAULT_OPERATOR_EMAIL, "short")

    def test_rate_limit_locks_after_failures(self) -> None:
        with storage.db() as conn:
            set_password(conn, DEFAULT_OPERATOR_EMAIL, "a-strong-password")
            conn.commit()
            for _ in range(5):
                authenticate(conn, DEFAULT_OPERATOR_EMAIL, "wrong-password-1", "10.0.0.9")
            self.assertTrue(is_locked_out("10.0.0.9", DEFAULT_OPERATOR_EMAIL))
            user, message = authenticate(
                conn, DEFAULT_OPERATOR_EMAIL, "a-strong-password", "10.0.0.9"
            )
            lockout_audit = conn.execute(
                "select count(*) from audit_logs where action='login_locked_out'"
            ).fetchone()[0]

        self.assertIsNone(user)
        self.assertIn("Too many failed attempts", message)
        self.assertEqual(lockout_audit, 1)
        # A different IP is unaffected.
        self.assertFalse(is_locked_out("10.0.0.10", DEFAULT_OPERATOR_EMAIL))

    def test_admin_env_bootstraps_owner_credentials(self) -> None:
        env = {"ADMIN_EMAIL": "owner@clinic.example", "ADMIN_PASSWORD": "clinic-owner-pass"}
        with patch.dict(os.environ, env, clear=False):
            with storage.db() as conn:
                one_time = ensure_owner_credentials(conn)
                conn.commit()
                user, _ = authenticate(conn, "owner@clinic.example", "clinic-owner-pass")
        self.assertIsNone(one_time)
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "owner")

    def test_one_time_password_generated_when_auth_required(self) -> None:
        with patch.dict(os.environ, {"AUTH_REQUIRED": "true"}, clear=False):
            with storage.db() as conn:
                one_time = ensure_owner_credentials(conn)
                conn.commit()
                self.assertIsNotNone(one_time)
                user, _ = authenticate(conn, DEFAULT_OPERATOR_EMAIL, one_time)
                # Second call must not regenerate.
                self.assertIsNone(ensure_owner_credentials(conn))
        self.assertIsNotNone(user)


class AuthHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "callpilot-test.db"
        self.patch = patch.object(storage, "DB_PATH", self.db_path)
        self.patch.start()
        storage.init_db()
        reset_rate_limiter()
        with storage.db() as conn:
            set_password(conn, DEFAULT_OPERATOR_EMAIL, "a-strong-password")
            conn.commit()
        self.env = patch.dict(os.environ, {"AUTH_REQUIRED": "true"}, clear=False)
        self.env.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), CallPilotHandler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.env.stop()
        self.patch.stop()
        gc.collect()
        self.temp_dir.cleanup()
        reset_rate_limiter()

    def request(self, method: str, path: str, body: str | None = None, cookie: str | None = None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if cookie:
            headers["Cookie"] = cookie
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        payload = response.read().decode("utf-8", errors="replace")
        set_cookie = response.getheader("Set-Cookie")
        headers_out = dict(response.getheaders())
        connection.close()
        return response.status, payload, set_cookie, headers_out

    def test_unauthenticated_requests_are_redirected_or_401(self) -> None:
        status, _, _, headers = self.request("GET", "/")
        self.assertEqual(status, 303)
        self.assertEqual(headers.get("Location"), "/login")
        api_status, _, _, _ = self.request("GET", "/api/workspace")
        self.assertEqual(api_status, 401)
        health_status, _, _, _ = self.request("GET", "/healthz")
        self.assertEqual(health_status, 200)

    def test_login_flow_sets_session_and_grants_access(self) -> None:
        bad_status, bad_body, _, _ = self.request(
            "POST", "/login", f"email={DEFAULT_OPERATOR_EMAIL}&password=wrong-password-1"
        )
        self.assertEqual(bad_status, 401)
        self.assertIn("Invalid email or password", bad_body)

        status, _, set_cookie, headers = self.request(
            "POST", "/login", f"email={DEFAULT_OPERATOR_EMAIL}&password=a-strong-password"
        )
        self.assertEqual(status, 303)
        self.assertEqual(headers.get("Location"), "/")
        self.assertIn("callpilot_session=", set_cookie or "")

        cookie = set_cookie.split(";")[0]
        home_status, home_body, _, _ = self.request("GET", "/", cookie=cookie)
        self.assertEqual(home_status, 200)
        self.assertIn("Dashboard", home_body)

    def test_logout_clears_session(self) -> None:
        _, _, set_cookie, _ = self.request(
            "POST", "/login", f"email={DEFAULT_OPERATOR_EMAIL}&password=a-strong-password"
        )
        cookie = set_cookie.split(";")[0]
        status, _, cleared, headers = self.request("POST", "/logout", cookie=cookie)
        self.assertEqual(status, 303)
        self.assertEqual(headers.get("Location"), "/login")
        cleared_cookie = cleared.split(";")[0]
        blocked_status, _, _, blocked_headers = self.request("GET", "/", cookie=cleared_cookie)
        self.assertEqual(blocked_status, 303)
        self.assertEqual(blocked_headers.get("Location"), "/login")

    def test_security_headers_are_present(self) -> None:
        status, _, _, headers = self.request("GET", "/login")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(headers.get("X-Frame-Options"), "DENY")
        self.assertIn("default-src 'self'", headers.get("Content-Security-Policy", ""))


if __name__ == "__main__":
    unittest.main()
