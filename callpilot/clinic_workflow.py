from __future__ import annotations

import sqlite3
from typing import Any

from .compliance import active_workspace_id, audit_event
from .utils import as_json, now
from .workflows import create_event


CLINIC_WORKFLOW_VERSION = "clinic-v1"

# Clinic appointment lifecycle. Each state lists the states it may transition to.
# Terminal states have no outbound transitions.
CLINIC_TRANSITIONS: dict[str, set[str]] = {
    "requested": {"confirmed", "rescheduled", "cancelled"},
    "confirmed": {"reminded", "rescheduled", "completed", "cancelled", "no_show"},
    "reminded": {"rescheduled", "completed", "cancelled", "no_show"},
    "rescheduled": {"confirmed", "reminded", "rescheduled", "completed", "cancelled", "no_show"},
    "no_show": {"rescheduled"},
    "completed": set(),
    "cancelled": set(),
}

CLINIC_STATES = set(CLINIC_TRANSITIONS)
TERMINAL_STATES = {state for state, targets in CLINIC_TRANSITIONS.items() if not targets}


class WorkflowError(Exception):
    """Raised when a clinic workflow transition is rejected."""


def normalize_status(value: str | None) -> str:
    clean = (value or "").strip().lower()
    return clean or "requested"


def is_terminal(state: str | None) -> bool:
    return normalize_status(state) in TERMINAL_STATES


def allowed_transitions(state: str | None) -> set[str]:
    return set(CLINIC_TRANSITIONS.get(normalize_status(state), set()))


def can_transition(from_status: str | None, to_status: str | None) -> bool:
    return normalize_status(to_status) in allowed_transitions(from_status)


def _load_booking(conn: sqlite3.Connection, booking_id: int, workspace_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "select * from bookings where id = ? and workspace_id = ?",
        (booking_id, workspace_id),
    ).fetchone()
    return dict(row) if row else None


def _cached_transition(
    conn: sqlite3.Connection, booking_id: int, idempotency_key: str | None
) -> dict[str, Any] | None:
    if not idempotency_key:
        return None
    row = conn.execute(
        """
        select * from clinic_workflow_transitions
        where booking_id = ? and idempotency_key = ?
        """,
        (booking_id, idempotency_key),
    ).fetchone()
    return dict(row) if row else None


def get_booking_transitions(
    conn: sqlite3.Connection, booking_id: int, workspace_id: int | None = None
) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    rows = conn.execute(
        """
        select * from clinic_workflow_transitions
        where booking_id = ? and workspace_id = ?
        order by id
        """,
        (booking_id, workspace_id),
    ).fetchall()
    return [dict(row) for row in rows]


def record_initial_state(
    conn: sqlite3.Connection,
    booking_id: int,
    business_id: int | None,
    lead_id: int | None,
    status: str = "requested",
    workspace_id: int | None = None,
    idempotency_key: str | None = None,
) -> None:
    """Log the opening state of a booking so its history starts at creation."""
    workspace_id = active_workspace_id(conn, workspace_id)
    conn.execute(
        """
        insert into clinic_workflow_transitions (
            workspace_id, business_id, booking_id, lead_id, workflow_version,
            from_status, to_status, actor, idempotency_key, note, metadata, created_at
        )
        values (?, ?, ?, ?, ?, NULL, ?, 'system', ?, 'Booking created.', ?, ?)
        """,
        (
            workspace_id,
            business_id,
            booking_id,
            lead_id,
            CLINIC_WORKFLOW_VERSION,
            normalize_status(status),
            idempotency_key,
            as_json({}),
            now(),
        ),
    )


def apply_booking_transition(
    conn: sqlite3.Connection,
    booking_id: int,
    to_status: str,
    actor: str = "operator",
    idempotency_key: str | None = None,
    note: str | None = None,
    metadata: dict[str, Any] | None = None,
    workspace_id: int | None = None,
) -> dict[str, Any]:
    """Apply a versioned, audited clinic booking transition.

    Rejects unknown target states, transitions out of terminal states, and
    transitions the state machine does not allow. Replaying the same
    ``idempotency_key`` returns the original result without a second write.
    """
    workspace_id = active_workspace_id(conn, workspace_id)
    target = normalize_status(to_status)

    booking = _load_booking(conn, booking_id, workspace_id)
    if not booking:
        raise WorkflowError(f"Booking {booking_id} not found in this workspace.")

    current = normalize_status(booking["status"])
    business_id = booking["business_id"]
    lead_id = booking["lead_id"]

    cached = _cached_transition(conn, booking_id, idempotency_key)
    if cached:
        return {
            "booking_id": booking_id,
            "from_status": cached["from_status"],
            "to_status": cached["to_status"],
            "workflow_version": cached["workflow_version"],
            "idempotent": True,
            "applied": False,
        }

    if target not in CLINIC_STATES:
        audit_event(
            conn,
            workspace_id,
            actor,
            "clinic_workflow_transition_rejected",
            "booking",
            booking_id,
            {"from": current, "to": target, "reason": "unknown_state"},
        )
        raise WorkflowError(f"Unknown clinic workflow state: {to_status!r}.")

    if current == target:
        return {
            "booking_id": booking_id,
            "from_status": current,
            "to_status": target,
            "workflow_version": CLINIC_WORKFLOW_VERSION,
            "idempotent": True,
            "applied": False,
        }

    if current in TERMINAL_STATES or target not in allowed_transitions(current):
        reason = "terminal_state" if current in TERMINAL_STATES else "invalid_transition"
        audit_event(
            conn,
            workspace_id,
            actor,
            "clinic_workflow_transition_rejected",
            "booking",
            booking_id,
            {"from": current, "to": target, "reason": reason},
        )
        raise WorkflowError(f"Cannot move clinic booking from {current} to {target}.")

    timestamp = now()
    conn.execute(
        "update bookings set status=?, updated_at=? where id=? and workspace_id=?",
        (target, timestamp, booking_id, workspace_id),
    )
    conn.execute(
        """
        insert into clinic_workflow_transitions (
            workspace_id, business_id, booking_id, lead_id, workflow_version,
            from_status, to_status, actor, idempotency_key, note, metadata, created_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            workspace_id,
            business_id,
            booking_id,
            lead_id,
            CLINIC_WORKFLOW_VERSION,
            current,
            target,
            actor,
            idempotency_key,
            note,
            as_json(metadata or {}),
            timestamp,
        ),
    )
    create_event(
        conn,
        business_id,
        lead_id,
        "clinic_workflow_transition",
        f"Booking moved from {current} to {target}.",
        {"from": current, "to": target, "workflow_version": CLINIC_WORKFLOW_VERSION},
        timestamp,
    )
    audit_event(
        conn,
        workspace_id,
        actor,
        "clinic_workflow_transition",
        "booking",
        booking_id,
        {"from": current, "to": target, "workflow_version": CLINIC_WORKFLOW_VERSION},
    )

    from .scheduling import sync_booking_for_status

    calendar = sync_booking_for_status(
        conn,
        {"id": booking_id, "business_id": business_id, "lead_id": lead_id},
        target,
        actor=actor,
        workspace_id=workspace_id,
    )
    return {
        "booking_id": booking_id,
        "from_status": current,
        "to_status": target,
        "workflow_version": CLINIC_WORKFLOW_VERSION,
        "idempotent": False,
        "applied": True,
        "calendar": calendar,
    }
