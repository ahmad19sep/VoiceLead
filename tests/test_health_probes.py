from __future__ import annotations

import gc
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.http import CallPilotHandler
from callpilot.security import health_probe, readiness_probe


class HealthProbeTest(unittest.TestCase):
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

    def test_health_probe_is_lightweight(self) -> None:
        probe = health_probe()

        self.assertTrue(probe["success"])
        self.assertEqual(probe["status"], "ok")
        self.assertEqual(probe["app"], "CallPilot AI")

    def test_readiness_probe_checks_database_and_blockers(self) -> None:
        probe = readiness_probe()

        self.assertTrue(probe["success"])
        self.assertEqual(probe["status"], "ready")
        self.assertTrue(probe["database"]["connected"])
        self.assertTrue(probe["database"]["schema_ready"])
        self.assertGreater(probe["database"]["business_count"], 0)

    def test_http_probe_routes_return_json(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), CallPilotHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_port}"
        try:
            health = self.fetch_json(f"{base_url}/healthz")
            readiness = self.fetch_json(f"{base_url}/readyz")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(health["status"], "ok")
        self.assertEqual(readiness["status"], "ready")

    def fetch_json(self, url: str) -> dict[str, object]:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                self.assertEqual(response.status, 200)
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            self.fail(f"{url} returned HTTP {exc.code}: {exc.read().decode('utf-8')}")


if __name__ == "__main__":
    unittest.main()
