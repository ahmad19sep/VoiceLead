from __future__ import annotations

import re
import sqlite3
from typing import Any

from .utils import as_json, now


DEFAULT_WORKSPACE_SLUG = "default"


def normalize_phone(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip()
    if value.startswith("+"):
        return "+" + re.sub(r"\D", "", value)
    digits = re.sub(r"\D", "", value)
    if digits.startswith("92") and len(digits) >= 12:
        return "+" + digits[:12]
    if digits.startswith("3") and len(digits) == 10:
        return "0" + digits
    return digits


def default_workspace_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("select id from workspaces where slug = ?", (DEFAULT_WORKSPACE_SLUG,)).fetchone()
    if row:
        return int(row["id"])
    return int(
        conn.execute(
            """
            insert into workspaces (name, slug, plan, status, timezone, created_at, updated_at)
            values ('Default Workspace', ?, 'demo', 'active', 'Asia/Karachi', ?, ?)
            """,
            (DEFAULT_WORKSPACE_SLUG, now(), now()),
        ).lastrowid
    )


def audit_event(
    conn: sqlite3.Connection,
    workspace_id: int | None,
    actor_type: str,
    action: str,
    resource_type: str,
    resource_id: int | str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        insert into audit_logs (workspace_id, actor_type, action, resource_type, resource_id, metadata, created_at)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            workspace_id,
            actor_type,
            action,
            resource_type,
            str(resource_id) if resource_id is not None else None,
            as_json(metadata or {}),
            now(),
        ),
    )


def get_workspace(conn: sqlite3.Connection, workspace_id: int | None = None) -> dict[str, Any] | None:
    workspace_id = workspace_id or default_workspace_id(conn)
    row = conn.execute("select * from workspaces where id = ?", (workspace_id,)).fetchone()
    return dict(row) if row else None


def get_staff_contacts(conn: sqlite3.Connection, workspace_id: int | None = None) -> list[dict[str, Any]]:
    workspace_id = workspace_id or default_workspace_id(conn)
    rows = conn.execute(
        """
        select staff_contacts.*, businesses.name as business_name
        from staff_contacts
        left join businesses on businesses.id = staff_contacts.business_id
        where staff_contacts.workspace_id = ?
        order by staff_contacts.name
        """,
        (workspace_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_consent_records(conn: sqlite3.Connection, workspace_id: int | None = None, limit: int = 25) -> list[dict[str, Any]]:
    workspace_id = workspace_id or default_workspace_id(conn)
    rows = conn.execute(
        """
        select consent_records.*, businesses.name as business_name
        from consent_records
        left join businesses on businesses.id = consent_records.business_id
        where consent_records.workspace_id = ?
        order by datetime(consent_records.created_at) desc
        limit ?
        """,
        (workspace_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def get_dnc_entries(conn: sqlite3.Connection, workspace_id: int | None = None) -> list[dict[str, Any]]:
    workspace_id = workspace_id or default_workspace_id(conn)
    rows = conn.execute(
        "select * from do_not_call where workspace_id = ? order by datetime(created_at) desc",
        (workspace_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_audit_logs(conn: sqlite3.Connection, workspace_id: int | None = None, limit: int = 25) -> list[dict[str, Any]]:
    workspace_id = workspace_id or default_workspace_id(conn)
    rows = conn.execute(
        "select * from audit_logs where workspace_id = ? order by datetime(created_at) desc limit ?",
        (workspace_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def record_consent(
    conn: sqlite3.Connection,
    business_id: int,
    phone: str,
    consent_type: str,
    source: str,
    proof: str,
) -> int:
    business = conn.execute("select workspace_id from businesses where id = ?", (business_id,)).fetchone()
    workspace_id = int(business["workspace_id"]) if business and business["workspace_id"] else default_workspace_id(conn)
    normalized = normalize_phone(phone)
    consent_id = int(
        conn.execute(
            """
            insert into consent_records (
                workspace_id, business_id, customer_phone, consent_type, source, proof, status, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (workspace_id, business_id, normalized, consent_type, source, proof, now(), now()),
        ).lastrowid
    )
    audit_event(
        conn,
        workspace_id,
        "operator",
        "consent_recorded",
        "consent_record",
        consent_id,
        {"business_id": business_id, "phone": normalized, "consent_type": consent_type, "source": source},
    )
    return consent_id


def add_dnc_entry(conn: sqlite3.Connection, phone: str, reason: str, source: str) -> int:
    workspace_id = default_workspace_id(conn)
    normalized = normalize_phone(phone)
    row = conn.execute(
        "select id from do_not_call where workspace_id = ? and customer_phone = ?",
        (workspace_id, normalized),
    ).fetchone()
    if row:
        conn.execute(
            "update do_not_call set reason=?, source=?, status='active', updated_at=? where id=?",
            (reason, source, now(), row["id"]),
        )
        dnc_id = int(row["id"])
    else:
        dnc_id = int(
            conn.execute(
                """
                insert into do_not_call (workspace_id, customer_phone, reason, source, status, created_at, updated_at)
                values (?, ?, ?, ?, 'active', ?, ?)
                """,
                (workspace_id, normalized, reason, source, now(), now()),
            ).lastrowid
        )
    audit_event(conn, workspace_id, "operator", "dnc_added", "do_not_call", dnc_id, {"phone": normalized, "reason": reason})
    return dnc_id


def has_active_consent(conn: sqlite3.Connection, business_id: int, phone: str, consent_type: str = "outbound_call") -> bool:
    normalized = normalize_phone(phone)
    row = conn.execute(
        """
        select id from consent_records
        where business_id = ? and customer_phone = ? and consent_type = ? and status = 'active'
        order by datetime(created_at) desc
        limit 1
        """,
        (business_id, normalized, consent_type),
    ).fetchone()
    return bool(row)


def is_do_not_call(conn: sqlite3.Connection, phone: str, workspace_id: int | None = None) -> bool:
    normalized = normalize_phone(phone)
    workspace_id = workspace_id or default_workspace_id(conn)
    row = conn.execute(
        "select id from do_not_call where workspace_id = ? and customer_phone = ? and status = 'active'",
        (workspace_id, normalized),
    ).fetchone()
    return bool(row)


def outbound_allowed(conn: sqlite3.Connection, business: dict[str, Any], phone: str) -> tuple[bool, str]:
    workspace_id = int(business.get("workspace_id") or default_workspace_id(conn))
    normalized = normalize_phone(phone)
    if not normalized:
        return False, "Phone number is required."
    if is_do_not_call(conn, normalized, workspace_id):
        audit_event(conn, workspace_id, "system", "outbound_blocked_dnc", "business", business.get("id"), {"phone": normalized})
        return False, "Blocked by Do Not Call list."
    max_attempts = int(business.get("max_outbound_attempts") or 0)
    if max_attempts <= 0:
        audit_event(
            conn,
            workspace_id,
            "system",
            "outbound_blocked_policy",
            "business",
            business.get("id"),
            {"phone": normalized, "reason": "max_outbound_attempts_zero"},
        )
        return False, "Outbound calls are disabled for this business policy."
    if not has_active_consent(conn, int(business["id"]), normalized):
        audit_event(
            conn,
            workspace_id,
            "system",
            "outbound_blocked_no_consent",
            "business",
            business.get("id"),
            {"phone": normalized},
        )
        return False, "Outbound consent is required before starting a real call."
    return True, "Outbound policy checks passed."
