from __future__ import annotations

import gc
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from callpilot import storage


class StorageConfigTest(unittest.TestCase):
    def test_configured_db_path_uses_storage_default(self) -> None:
        with patch.dict(os.environ, {"SQLITE_DB_PATH": "", "DB_PATH": ""}, clear=False):
            self.assertEqual(storage.configured_db_path(), storage.DB_PATH)

    def test_sqlite_db_path_env_overrides_default_and_creates_parent(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            db_path = Path(temp_dir.name) / "nested" / "callpilot-test.db"
            with patch.dict(os.environ, {"SQLITE_DB_PATH": str(db_path), "DB_PATH": ""}, clear=False):
                conn = storage.db()
                try:
                    conn.execute("create table sample (id integer primary key)")
                    conn.commit()
                finally:
                    conn.close()

            self.assertTrue(db_path.exists())
        finally:
            gc.collect()
            temp_dir.cleanup()

    def test_db_path_env_is_a_fallback(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            db_path = Path(temp_dir.name) / "fallback.db"
            with patch.dict(os.environ, {"SQLITE_DB_PATH": "", "DB_PATH": str(db_path)}, clear=False):
                self.assertEqual(storage.configured_db_path(), db_path)
        finally:
            gc.collect()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
