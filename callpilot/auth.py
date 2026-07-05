from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from typing import Any

from .compliance import audit_event, default_workspace_id
from .providers import env_flag, is_production
from .utils import now


PBKDF2_ITERATIONS = 260_000
MIN_PASSWORD_LENGTH = 10

# Login rate limiting: per (client_ip, email) sliding window.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60
_FAILED_LOGINS: dict[tuple[str, str], list[float]] = {}


def auth_required() -> bool:
    """Real login is forced in production and opt-in locally via AUTH_REQUIRED."""
    return env_flag("AUTH_REQUIRED", is_production())


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, iterations, salt, expected = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        ).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


def validate_password(password: str) -> str | None:
    if len(password or "") < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    return None


def set_password(conn: sqlite3.Connection, email: str, password: str) -> None:
    error = validate_password(password)
    if error:
        raise ValueError(error)
    conn.execute(
        "update workspace_users set password_hash=?, updated_at=? where lower(email)=lower(?)",
        (hash_password(password), now(), email.strip()),
    )


def _attempt_key(client_ip: str, email: str) -> tuple[str, str]:
    return (client_ip or "unknown", (email or "").strip().lower())


def is_locked_out(client_ip: str, email: str) -> bool:
    key = _attempt_key(client_ip, email)
    cutoff = time.monotonic() - LOCKOUT_SECONDS
    attempts = [stamp for stamp in _FAILED_LOGINS.get(key, []) if stamp > cutoff]
    _FAILED_LOGINS[key] = attempts
    return len(attempts) >= MAX_FAILED_ATTEMPTS


def record_failed_login(client_ip: str, email: str) -> None:
    _FAILED_LOGINS.setdefault(_attempt_key(client_ip, email), []).append(time.monotonic())


def clear_failed_logins(client_ip: str, email: str) -> None:
    _FAILED_LOGINS.pop(_attempt_key(client_ip, email), None)


def reset_rate_limiter() -> None:
    _FAILED_LOGINS.clear()


def authenticate(
    conn: sqlite3.Connection, email: str, password: str, client_ip: str = "unknown"
) -> tuple[dict[str, Any] | None, str]:
    """Verify credentials with rate limiting. Returns (user, message)."""
    clean_email = (email or "").strip().lower()
    if is_locked_out(client_ip, clean_email):
        audit_event(
            conn, None, "system", "login_locked_out", "workspace_user", clean_email, {"ip": client_ip}
        )
        return None, "Too many failed attempts. Try again later."
    row = conn.execute(
        """
        select * from workspace_users
        where lower(email)=lower(?) and status='active'
        order by id limit 1
        """,
        (clean_email,),
    ).fetchone()
    user = dict(row) if row else None
    if not user or not verify_password(password, user.get("password_hash")):
        record_failed_login(client_ip, clean_email)
        audit_event(
            conn,
            user.get("workspace_id") if user else None,
            "system",
            "login_failed",
            "workspace_user",
            clean_email,
            {"ip": client_ip},
        )
        # Same message for unknown user and wrong password (no user enumeration).
        return None, "Invalid email or password."
    clear_failed_logins(client_ip, clean_email)
    audit_event(
        conn,
        user.get("workspace_id"),
        "operator",
        "login_succeeded",
        "workspace_user",
        user.get("id"),
        {"ip": client_ip},
    )
    return user, "Login successful."


def ensure_owner_credentials(conn: sqlite3.Connection) -> str | None:
    """Bootstrap real credentials for the workspace owner.

    Priority: ADMIN_EMAIL/ADMIN_PASSWORD env pair. Otherwise, when auth is
    required and the seeded owner has no password, generate a one-time
    password, store only its hash, and return it so startup can print it once.
    """
    workspace_id = default_workspace_id(conn)
    admin_email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    admin_password = os.environ.get("ADMIN_PASSWORD") or ""
    if admin_email and admin_password:
        if validate_password(admin_password):
            raise ValueError("ADMIN_PASSWORD is too short; use at least 10 characters.")
        row = conn.execute(
            "select id from workspace_users where workspace_id=? and lower(email)=lower(?)",
            (workspace_id, admin_email),
        ).fetchone()
        if row:
            set_password(conn, admin_email, admin_password)
        else:
            conn.execute(
                """
                insert into workspace_users (workspace_id, name, email, role, status, password_hash, created_at, updated_at)
                values (?, 'Workspace Admin', ?, 'owner', 'active', ?, ?, ?)
                """,
                (workspace_id, admin_email, hash_password(admin_password), now(), now()),
            )
        audit_event(conn, workspace_id, "system", "admin_credentials_configured", "workspace_user", admin_email, {})
        return None

    if not auth_required():
        return None
    owner = conn.execute(
        """
        select * from workspace_users
        where workspace_id=? and role='owner' and status='active'
        order by id limit 1
        """,
        (workspace_id,),
    ).fetchone()
    if not owner or owner["password_hash"]:
        return None
    one_time = secrets.token_urlsafe(12)
    conn.execute(
        "update workspace_users set password_hash=?, updated_at=? where id=?",
        (hash_password(one_time), now(), owner["id"]),
    )
    audit_event(conn, workspace_id, "system", "owner_password_generated", "workspace_user", owner["id"], {})
    return one_time


def ensure_demo_viewer(conn: sqlite3.Connection) -> None:
    """Seed a read-only demo account for client walkthroughs.

    Controlled by DEMO_VIEWER_EMAIL/DEMO_VIEWER_PASSWORD. The account gets the
    'viewer' role, so route RBAC denies every mutation — safe to hand to a
    prospect on a live demo instance.
    """
    email = (os.environ.get("DEMO_VIEWER_EMAIL") or "").strip().lower()
    password = os.environ.get("DEMO_VIEWER_PASSWORD") or ""
    if not email or not password:
        return
    if validate_password(password):
        raise ValueError("DEMO_VIEWER_PASSWORD is too short; use at least 10 characters.")
    workspace_id = default_workspace_id(conn)
    row = conn.execute(
        "select id from workspace_users where workspace_id=? and lower(email)=lower(?)",
        (workspace_id, email),
    ).fetchone()
    if row:
        conn.execute(
            "update workspace_users set role='viewer', status='active', password_hash=?, updated_at=? where id=?",
            (hash_password(password), now(), row["id"]),
        )
    else:
        conn.execute(
            """
            insert into workspace_users (workspace_id, name, email, role, status, password_hash, created_at, updated_at)
            values (?, 'Demo Viewer', ?, 'viewer', 'active', ?, ?, ?)
            """,
            (workspace_id, email, hash_password(password), now(), now()),
        )
    audit_event(conn, workspace_id, "system", "demo_viewer_configured", "workspace_user", email, {})
