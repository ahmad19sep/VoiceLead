from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from callpilot.server import configured_host, configured_port


class ServerConfigTest(unittest.TestCase):
    def test_server_defaults_remain_local(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(configured_host(), "127.0.0.1")
            self.assertEqual(configured_port(), 8000)

    def test_server_host_and_port_can_come_from_env(self) -> None:
        with patch.dict(os.environ, {"APP_HOST": "0.0.0.0", "APP_PORT": "9000"}, clear=True):
            self.assertEqual(configured_host(), "0.0.0.0")
            self.assertEqual(configured_port(), 9000)

    def test_invalid_port_falls_back_to_default(self) -> None:
        for value in ["abc", "0", "65536", "-1"]:
            with self.subTest(value=value):
                with patch.dict(os.environ, {"APP_PORT": value}, clear=True):
                    self.assertEqual(configured_port(), 8000)

    def test_platform_injected_port_is_honored(self) -> None:
        # Render/Railway free hosts inject PORT; APP_PORT still wins when set.
        with patch.dict(os.environ, {"PORT": "10000"}, clear=True):
            self.assertEqual(configured_port(), 10000)
        with patch.dict(os.environ, {"PORT": "10000", "APP_PORT": "9000"}, clear=True):
            self.assertEqual(configured_port(), 9000)


if __name__ == "__main__":
    unittest.main()
