from __future__ import annotations

import gc
import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.config import app_tagline, business_types_for_mode, platform_mode
from callpilot.http import CallPilotHandler


class PlatformModeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "callpilot-test.db"
        self.db_patch = patch.object(storage, "DB_PATH", self.db_path)
        self.db_patch.start()
        storage.init_db()

    def tearDown(self) -> None:
        self.db_patch.stop()
        gc.collect()
        self.temp_dir.cleanup()

    def test_clinic_mode_is_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(platform_mode(), "clinic")
            self.assertIn("clinic's AI receptionist", app_tagline())
            self.assertEqual(business_types_for_mode(), ["Clinic", "Hospital", "Dentist"])

    def test_universal_mode_restores_universal_labels(self) -> None:
        with patch.dict(os.environ, {"PLATFORM_MODE": "universal"}, clear=True):
            self.assertEqual(platform_mode(), "universal")
            self.assertIn("Universal AI Calling Agent", app_tagline())
            self.assertIn("Hotel", business_types_for_mode())

    def test_clinic_sidebar_hides_frozen_surfaces(self) -> None:
        with patch.dict(os.environ, {"PLATFORM_MODE": "clinic"}, clear=False):
            server, thread, base_url = self.start_server()
            try:
                html = self.fetch_text(f"{base_url}/")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertIn("AI receptionist", html)
        self.assertIn("Patients/Inquiries", html)
        self.assertNotIn('href="/modules"', html)
        self.assertNotIn('href="/campaigns"', html)

    def test_clinic_mode_hides_module_routes_and_filters_api(self) -> None:
        with patch.dict(os.environ, {"PLATFORM_MODE": "clinic"}, clear=False):
            server, thread, base_url = self.start_server()
            try:
                modules = self.fetch_json(f"{base_url}/api/modules")["modules"]
                module_status = self.fetch_status(f"{base_url}/modules")
                campaign_status = self.fetch_status(f"{base_url}/campaigns")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual([row["key"] for row in modules], ["healthcare"])
        self.assertEqual(module_status, 404)
        self.assertEqual(campaign_status, 404)

    def test_universal_mode_exposes_module_catalog(self) -> None:
        with patch.dict(os.environ, {"PLATFORM_MODE": "universal"}, clear=False):
            server, thread, base_url = self.start_server()
            try:
                modules = self.fetch_json(f"{base_url}/api/modules")["modules"]
                module_status = self.fetch_status(f"{base_url}/modules")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertGreater(len(modules), 1)
        self.assertEqual(module_status, 200)

    def start_server(self) -> tuple[ThreadingHTTPServer, threading.Thread, str]:
        server = ThreadingHTTPServer(("127.0.0.1", 0), CallPilotHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, thread, f"http://127.0.0.1:{server.server_port}"

    def fetch_text(self, url: str) -> str:
        with urllib.request.urlopen(url, timeout=5) as response:
            self.assertEqual(response.status, 200)
            return response.read().decode("utf-8")

    def fetch_json(self, url: str) -> dict[str, object]:
        return json.loads(self.fetch_text(url))

    def fetch_status(self, url: str) -> int:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return int(response.status)
        except urllib.error.HTTPError as exc:
            return int(exc.code)


if __name__ == "__main__":
    unittest.main()
