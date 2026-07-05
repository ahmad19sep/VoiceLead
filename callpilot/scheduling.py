from __future__ import annotations

import sqlite3
from typing import Any

from .calendar import CalendarResult, calendar_adapter
from .compliance import active_workspace_id, audit_event
from .utils import as_json, now
from .workflows import create_event


# Which calendar action a clinic workflow target status should trigger.
STATUS_CALENDAR_ACTION: dict[str, str] = {
    "confirmed": "create",
    "rescheduled": "reschedule",
    "cancelled": "cancel",
}

# Resulting booking calendar_sync_status by (action, success).
_STATUS_ON_SUCCESS = {"create": "confirmed", "reschedule": "confirmed", "cancel": "cancelled"}
_STATUS_ON_FAILURE = {"create": "pending", "reschedule": "pending", "cancel": "pending_cancel"}


def _load_booking(conn: sqlite3.Connection, booking_id: int, workspace_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "select * from bookings where id = ? and workspace_id = ?",
        (booking_id, workspace_id),
    ).fetchone()
    return dict(row) if row else None


def get_booking_calendar_syncs(
    conn: sqlite3.Connection, booking_id: int, workspace_id: int | None = None
) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    rows = conn.execute(
        """
        select * from booking_calendar_syncs
        where booking_id = ? and workspace_id = ?
        order by id
        """,
        (booking_id, workspace_id),
    ).fetchall()
    return [dict(row) for row in rows]


def sync_booking(
    conn: sqlite3.Connection,
    booking_id: int,
    action: str,
    actor: str = "system",
    workspace_id: int | None = None,
    adapter_key: str | None = None,
) -> dict[str, Any]:
    """Attempt a calendar action for a booking and persist the honest result.

    Never fabricates a confirmed event id: if the adapter is unavailable the
    booking is recorded as pending, not confirmed. Creating an event for a
    booking that already holds a confirmed event id is a no-op.
    """
    workspace_id = active_workspace_id(conn, workspace_id)
    booking = _load_booking(conn, booking_id, workspace_id)
    if not booking:
        raise ValueError(f"Booking {booking_id} not found in this workspace.")

    adapter = calendar_adapter(adapter_key)
    existing_event = booking.get("calendar_event_id")

    if action == "create" and existing_event and booking.get("calendar_sync_status") == "confirmed":
        return {
            "booking_id": booking_id,
            "action": action,
            "provider": booking.get("calendar_provider"),
            "sync_status": "confirmed",
            "event_id": existing_event,
            "changed": False,
            "message": "Calendar event already confirmed.",
        }

    if action == "create":
        result = adapter.create_event(booking)
    elif action == "reschedule":
        result = adapter.reschedule_event(booking, existing_event)
    elif action == "cancel":
        result = adapter.cancel_event(booking, existing_event)
    else:
        raise ValueError(f"Unknown calendar action: {action!r}.")

    sync_status = (_STATUS_ON_SUCCESS if result.success else _STATUS_ON_FAILURE)[action]
    event_id = result.event_id or existing_event
    timestamp = now()

    conn.execute(
        """
        update bookings
        set calendar_provider=?, calendar_event_id=?, calendar_sync_status=?,
            calendar_synced_at=?, calendar_message=?, updated_at=?
        where id=? and workspace_id=?
        """,
        (
            result.provider,
            event_id,
            sync_status,
            timestamp,
            result.message,
            timestamp,
            booking_id,
            workspace_id,
        ),
    )
    conn.execute(
        """
        insert into booking_calendar_syncs (
            workspace_id, business_id, booking_id, provider, action, status, event_id, message, actor, created_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            workspace_id,
            booking.get("business_id"),
            booking_id,
            result.provider,
            action,
            sync_status,
            result.event_id,
            result.message,
            actor,
            timestamp,
        ),
    )
    create_event(
        conn,
        booking.get("business_id"),
        booking.get("lead_id"),
        "calendar_sync",
        f"Calendar {action} -> {sync_status} via {result.provider}.",
        {"action": action, "status": sync_status, "event_id": result.event_id, "message": result.message},
        timestamp,
    )
    audit_event(
        conn,
        workspace_id,
        actor,
        "booking_calendar_sync",
        "booking",
        booking_id,
        {"action": action, "status": sync_status, "provider": result.provider, "event_id": result.event_id},
    )
    return {
        "booking_id": booking_id,
        "action": action,
        "provider": result.provider,
        "sync_status": sync_status,
        "event_id": result.event_id,
        "changed": True,
        "message": result.message,
    }


def sync_booking_for_status(
    conn: sqlite3.Connection,
    booking: dict[str, Any],
    status: str,
    actor: str = "system",
    workspace_id: int | None = None,
) -> dict[str, Any] | None:
    """Trigger the calendar action mapped to a workflow status, if any.

    Calendar failures must not roll back a legitimate workflow transition, so
    any adapter/database error is swallowed here and left for a later retry.
    """
    action = STATUS_CALENDAR_ACTION.get(status)
    if not action:
        return None
    try:
        return sync_booking(conn, int(booking["id"]), action, actor=actor, workspace_id=workspace_id)
    except Exception:  # pragma: no cover - defensive; calendar is best-effort
        return None
