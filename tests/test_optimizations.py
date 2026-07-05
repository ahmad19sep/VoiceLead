from __future__ import annotations

import gc
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.server import inline_worker_enabled, inline_worker_interval


EXPECTED_INDEXES = {
    "idx_leads_workspace_created",
    "idx_bookings_workspace_status",
    "idx_call_logs_provider_call",
    "idx_call_logs_workspace_created",
    "idx_notifications_workspace_created",
    "idx_agent_events_lead",
    "idx_audit_logs_workspace",
    "idx_clinic_workflow_idempotency",
    "idx_jobs_status_scheduled",
}


class IndexTest(unittest.TestCase):
    def test_query_indexes_exist(self) -> None:
        temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        try:
            with patch.object(storage, "DB_PATH", Path(temp_dir.name) / "t.db"):
                storage.init_db()
                conn = storage.db()
                try:
                    names = {
                        row["name"]
                        for row in conn.execute("select name from sqlite_master where type='index'")
                    }
                finally:
                    conn.close()
            missing = EXPECTED_INDEXES - names
            self.assertEqual(missing, set(), f"missing indexes: {missing}")
        finally:
            gc.collect()
            temp_dir.cleanup()


class InlineWorkerConfigTest(unittest.TestCase):
    def test_enabled_by_default_and_disableable(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(inline_worker_enabled())
        with patch.dict(os.environ, {"INLINE_WORKER": "false"}, clear=True):
            self.assertFalse(inline_worker_enabled())

    def test_interval_parsing_with_floor(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(inline_worker_interval(), 300)
        with patch.dict(os.environ, {"WORKER_POLL_INTERVAL": "60"}, clear=True):
            self.assertEqual(inline_worker_interval(), 60)
        # Too-aggressive intervals and garbage fall back to the default.
        with patch.dict(os.environ, {"WORKER_POLL_INTERVAL": "5"}, clear=True):
            self.assertEqual(inline_worker_interval(), 300)
        with patch.dict(os.environ, {"WORKER_POLL_INTERVAL": "abc"}, clear=True):
            self.assertEqual(inline_worker_interval(), 300)


if __name__ == "__main__":
    unittest.main()
