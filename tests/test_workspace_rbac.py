from __future__ import annotations

import tempfile
import unittest
import gc
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.compliance import default_workspace_id, default_workspace_user, get_workspace_users, role_allows
from callpilot.repositories import get_business, get_businesses, get_leads
from callpilot.utils import now


class WorkspaceRBACTest(unittest.TestCase):
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

    def test_default_workspace_owner_is_seeded(self) -> None:
        with storage.db() as conn:
            workspace_id = default_workspace_id(conn)
            user = default_workspace_user(conn, workspace_id)
            users = get_workspace_users(conn, workspace_id)

        self.assertEqual(user["email"], "operator@callpilot.local")
        self.assertEqual(user["role"], "owner")
        self.assertTrue(role_allows(user["role"], "manage_users"))
        self.assertFalse(role_allows("viewer", "manage_users"))
        self.assertEqual([row["email"] for row in users], ["operator@callpilot.local"])

    def test_repository_reads_are_workspace_scoped_by_default(self) -> None:
        with storage.db() as conn:
            default_id = default_workspace_id(conn)
            other_id = int(
                conn.execute(
                    """
                    insert into workspaces (name, slug, plan, status, timezone, created_at, updated_at)
                    values ('Other Workspace', 'other', 'demo', 'active', 'UTC', ?, ?)
                    """,
                    (now(), now()),
                ).lastrowid
            )
            other_business_id = int(
                conn.execute(
                    """
                    insert into businesses (
                        workspace_id, name, business_type, agent_name, status, created_at, updated_at
                    )
                    values (?, 'Other Tenant Clinic', 'Clinic', 'Other Agent', 'active', ?, ?)
                    """,
                    (other_id, now(), now()),
                ).lastrowid
            )
            conn.execute(
                """
                insert into leads (
                    workspace_id, business_id, customer_name, lead_score, lead_temperature, status, created_at, updated_at
                )
                values (?, ?, 'Other Caller', 80, 'hot', 'new', ?, ?)
                """,
                (other_id, other_business_id, now(), now()),
            )

            default_businesses = get_businesses(conn)
            other_businesses = get_businesses(conn, workspace_id=other_id)
            default_leads = get_leads(conn)
            other_leads = get_leads(conn, workspace_id=other_id)
            default_lookup = get_business(conn, other_business_id)
            other_lookup = get_business(conn, other_business_id, other_id)

        self.assertTrue(default_businesses)
        self.assertEqual(default_id, default_businesses[0]["workspace_id"])
        self.assertNotIn("Other Tenant Clinic", {row["name"] for row in default_businesses})
        self.assertEqual([row["name"] for row in other_businesses], ["Other Tenant Clinic"])
        self.assertNotIn("Other Caller", {row["customer_name"] for row in default_leads})
        self.assertEqual([row["customer_name"] for row in other_leads], ["Other Caller"])
        self.assertIsNone(default_lookup)
        self.assertEqual(other_lookup["name"], "Other Tenant Clinic")


if __name__ == "__main__":
    unittest.main()
