from __future__ import annotations

from contextvars import ContextVar, Token
import re
import sqlite3
from typing import Any

from .utils import as_json, now


DEFAULT_WORKSPACE_SLUG = "default"
DEFAULT_OPERATOR_EMAIL = "operator@callpilot.local"
DEFAULT_OPERATOR_NAME = "Demo Operator"

ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "owner": (
        "manage_workspace",
        "manage_users",
        "manage_compliance",
        "manage_agents",
        "manage_campaigns",
        "run_jobs",
        "review_qa",
        "view_reports",
        "place_calls",
    ),
    "admin": (
        "manage_compliance",
        "manage_agents",
        "manage_campaigns",
        "run_jobs",
        "review_qa",
        "view_reports",
        "place_calls",
    ),
    "operator": (
        "manage_agents",
        "manage_campaigns",
        "run_jobs",
        "view_reports",
        "place_calls",
    ),
    "reviewer": ("review_qa", "view_reports"),
    "viewer": ("view_reports",),
}

ROLE_LABELS: dict[str, str] = {
    "owner": "Workspace owner",
    "admin": "Administrator",
    "operator": "Call operator",
    "reviewer": "QA reviewer",
    "viewer": "Read-only viewer",
}

_REQUEST_WORKSPACE_ID: ContextVar[int | None] = ContextVar("request_workspace_id", default=None)
_REQUEST_USER_EMAIL: ContextVar[str | None] = ContextVar("request_user_email", default=None)


def set_request_context(workspace_id: int | None = None, user_email: str | None = None) -> tuple[Token[int | None], Token[str | None]]:
    workspace_token = _REQUEST_WORKSPACE_ID.set(int(workspace_id) if workspace_id else None)
    email_token = _REQUEST_USER_EMAIL.set(user_email.strip().lower() if user_email else None)
    return workspace_token, email_token


def reset_request_context(tokens: tuple[Token[int | None], Token[str | None]]) -> None:
    workspace_token, email_token = tokens
    _REQUEST_WORKSPACE_ID.reset(workspace_token)
    _REQUEST_USER_EMAIL.reset(email_token)


def request_workspace_id() -> int | None:
    return _REQUEST_WORKSPACE_ID.get()


def request_user_email() -> str | None:
    return _REQUEST_USER_EMAIL.get()


def canonical_role(role: str | None) -> str:
    clean = (role or "viewer").strip().lower().replace(" ", "_")
    return clean if clean in ROLE_PERMISSIONS else "viewer"


def permissions_for_role(role: str | None) -> list[str]:
    return list(ROLE_PERMISSIONS[canonical_role(role)])


def role_allows(role: str | None, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS[canonical_role(role)]


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


def active_workspace_id(conn: sqlite3.Connection, workspace_id: int | None = None) -> int:
    requested = workspace_id if workspace_id is not None else request_workspace_id()
    if requested:
        row = conn.execute(
            "select id from workspaces where id = ? and status = 'active'",
            (int(requested),),
        ).fetchone()
        if row:
            return int(row["id"])
    return default_workspace_id(conn)


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


def upsert_workspace_user(
    conn: sqlite3.Connection,
    workspace_id: int,
    name: str,
    email: str,
    role: str = "operator",
    status: str = "active",
) -> tuple[dict[str, Any], bool]:
    clean_name = (name or DEFAULT_OPERATOR_NAME).strip()
    clean_email = (email or DEFAULT_OPERATOR_EMAIL).strip().lower()
    clean_role = canonical_role(role)
    clean_status = status if status in {"active", "invited", "disabled"} else "active"
    timestamp = now()
    row = conn.execute(
        """
        select * from workspace_users
        where workspace_id = ? and lower(email) = lower(?)
        limit 1
        """,
        (workspace_id, clean_email),
    ).fetchone()
    if row:
        if (
            row["name"] != clean_name
            or row["email"] != clean_email
            or canonical_role(row["role"]) != clean_role
            or row["status"] != clean_status
        ):
            conn.execute(
                """
                update workspace_users
                set name=?, email=?, role=?, status=?, updated_at=?
                where id=?
                """,
                (clean_name, clean_email, clean_role, clean_status, timestamp, row["id"]),
            )
        user_id = int(row["id"])
        created = False
    else:
        user_id = int(
            conn.execute(
                """
                insert into workspace_users (
                    workspace_id, name, email, role, status, created_at, updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?)
                """,
                (workspace_id, clean_name, clean_email, clean_role, clean_status, timestamp, timestamp),
            ).lastrowid
        )
        created = True
        audit_event(
            conn,
            workspace_id,
            "system",
            "workspace_user_created",
            "workspace_user",
            user_id,
            {"email": clean_email, "role": clean_role},
        )
    user = dict(conn.execute("select * from workspace_users where id = ?", (user_id,)).fetchone())
    user["permissions"] = permissions_for_role(user.get("role"))
    user["role_label"] = ROLE_LABELS[canonical_role(user.get("role"))]
    return user, created


def default_workspace_user(conn: sqlite3.Connection, workspace_id: int | None = None) -> dict[str, Any]:
    workspace_id = workspace_id or default_workspace_id(conn)
    user, _created = upsert_workspace_user(
        conn,
        workspace_id,
        DEFAULT_OPERATOR_NAME,
        DEFAULT_OPERATOR_EMAIL,
        "owner",
        "active",
    )
    return user


def workspace_user_by_email(conn: sqlite3.Connection, workspace_id: int, email: str | None) -> dict[str, Any] | None:
    if not email:
        return None
    row = conn.execute(
        """
        select * from workspace_users
        where workspace_id = ? and lower(email) = lower(?) and status = 'active'
        limit 1
        """,
        (workspace_id, email.strip().lower()),
    ).fetchone()
    if not row:
        return None
    user = dict(row)
    user["permissions"] = permissions_for_role(user.get("role"))
    user["role_label"] = ROLE_LABELS[canonical_role(user.get("role"))]
    return user


def first_workspace_user(conn: sqlite3.Connection, workspace_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        select * from workspace_users
        where workspace_id = ? and status = 'active'
        order by
          case role
            when 'owner' then 1
            when 'admin' then 2
            when 'operator' then 3
            when 'reviewer' then 4
            else 5
          end,
          name
        limit 1
        """,
        (workspace_id,),
    ).fetchone()
    if not row:
        return None
    user = dict(row)
    user["permissions"] = permissions_for_role(user.get("role"))
    user["role_label"] = ROLE_LABELS[canonical_role(user.get("role"))]
    return user


def get_workspace(conn: sqlite3.Connection, workspace_id: int | None = None) -> dict[str, Any] | None:
    workspace_id = active_workspace_id(conn, workspace_id)
    row = conn.execute("select * from workspaces where id = ?", (workspace_id,)).fetchone()
    return dict(row) if row else None


def get_workspaces(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    default_workspace_id(conn)
    rows = conn.execute(
        "select * from workspaces where status = 'active' order by name"
    ).fetchall()
    return [dict(row) for row in rows]


def get_workspace_users(conn: sqlite3.Connection, workspace_id: int | None = None) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    if not first_workspace_user(conn, workspace_id):
        default_workspace_user(conn, workspace_id)
    rows = conn.execute(
        """
        select * from workspace_users
        where workspace_id = ?
        order by
          case role
            when 'owner' then 1
            when 'admin' then 2
            when 'operator' then 3
            when 'reviewer' then 4
            else 5
          end,
          name
        """,
        (workspace_id,),
    ).fetchall()
    users = []
    for row in rows:
        user = dict(row)
        user["permissions"] = permissions_for_role(user.get("role"))
        user["role_label"] = ROLE_LABELS[canonical_role(user.get("role"))]
        users.append(user)
    return users


def workspace_context(
    conn: sqlite3.Connection,
    workspace_id: int | None = None,
    user_email: str | None = None,
) -> dict[str, Any]:
    workspace_id = active_workspace_id(conn, workspace_id)
    user = workspace_user_by_email(conn, workspace_id, user_email or request_user_email())
    if not user:
        user = first_workspace_user(conn, workspace_id) or default_workspace_user(conn, workspace_id)
    return {
        "workspace": get_workspace(conn, workspace_id),
        "current_user": user,
        "workspaces": get_workspaces(conn),
        "users": get_workspace_users(conn, workspace_id),
        "role_permissions": {role: list(permissions) for role, permissions in ROLE_PERMISSIONS.items()},
    }


def get_staff_contacts(conn: sqlite3.Connection, workspace_id: int | None = None) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
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
    workspace_id = active_workspace_id(conn, workspace_id)
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
    workspace_id = active_workspace_id(conn, workspace_id)
    rows = conn.execute(
        "select * from do_not_call where workspace_id = ? order by datetime(created_at) desc",
        (workspace_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def get_audit_logs(conn: sqlite3.Connection, workspace_id: int | None = None, limit: int = 25) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
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
    workspace_id: int | None = None,
) -> int:
    workspace_id = active_workspace_id(conn, workspace_id)
    business = conn.execute(
        "select workspace_id from businesses where id = ? and workspace_id = ?",
        (business_id, workspace_id),
    ).fetchone()
    if not business:
        raise ValueError("Business not found in the active workspace.")
    workspace_id = int(business["workspace_id"]) if business["workspace_id"] else workspace_id
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


def add_dnc_entry(
    conn: sqlite3.Connection,
    phone: str,
    reason: str,
    source: str,
    workspace_id: int | None = None,
) -> int:
    workspace_id = active_workspace_id(conn, workspace_id)
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
    workspace_id = active_workspace_id(conn, workspace_id)
    row = conn.execute(
        "select id from do_not_call where workspace_id = ? and customer_phone = ? and status = 'active'",
        (workspace_id, normalized),
    ).fetchone()
    return bool(row)


def outbound_allowed(conn: sqlite3.Connection, business: dict[str, Any], phone: str) -> tuple[bool, str]:
    workspace_id = int(business.get("workspace_id") or active_workspace_id(conn))
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
