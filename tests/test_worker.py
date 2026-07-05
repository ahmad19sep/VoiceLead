from __future__ import annotations

import gc
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.jobs import enqueue_job, get_jobs
from callpilot.worker import env_int, main, run_worker_once


class WorkerTest(unittest.TestCase):
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

    def test_env_int_uses_defaults_for_invalid_values(self) -> None:
        for value in ["", "abc", "0", "-5"]:
            with self.subTest(value=value):
                with patch.dict(os.environ, {"WORKER_BATCH_LIMIT": value}, clear=True):
                    self.assertEqual(env_int("WORKER_BATCH_LIMIT", 20), 20)

    def test_run_worker_once_processes_due_jobs(self) -> None:
        with storage.db() as conn:
            job_id = enqueue_job(conn, None, "unknown_test_job", "test", "1", max_attempts=1)

        results = run_worker_once(limit=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["job_id"], job_id)
        self.assertEqual(results[0]["status"], "completed")
        with storage.db() as conn:
            jobs = get_jobs(conn, "completed")
        self.assertEqual([row["id"] for row in jobs], [job_id])
        self.assertIn("unknown_job_type_unknown_test_job", jobs[0]["result"])

    def test_worker_once_cli_exits_successfully(self) -> None:
        self.assertEqual(main(["--once", "--limit", "1"]), 0)


if __name__ == "__main__":
    unittest.main()
