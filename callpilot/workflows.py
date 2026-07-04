from __future__ import annotations

import sqlite3
from typing import Any

from .repositories import get_business, get_lead
from .utils import as_json, now


def create_event(
    conn: sqlite3.Connection,
    business_id: int | None,
    lead_id: int | None,
    event_type: str,
    description: str,
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> None:
    workspace_id = None
    if business_id:
        row = conn.execute("select workspace_id from businesses where id = ?", (business_id,)).fetchone()
        workspace_id = row["workspace_id"] if row else None
    conn.execute(
        """
        insert into agent_events (workspace_id, business_id, lead_id, event_type, description, metadata, created_at)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (workspace_id, business_id, lead_id, event_type, description, as_json(metadata or {}), created_at or now()),
    )

def create_notification(conn: sqlite3.Connection, business_id: int, lead_id: int, analysis: dict[str, Any]) -> None:
    business = get_business(conn, business_id)
    if not business:
        return
    subject = f"Hot lead: {business['name']} - {analysis.get('request_type') or 'Call request'}"
    message = "\n".join(
        [
            "Hot Lead Alert",
            f"Business: {business['name']}",
            f"Agent: {business.get('agent_name') or 'AI Agent'}",
            f"Customer: {analysis.get('customer_name') or 'Unknown'}",
            f"Phone: {analysis.get('customer_phone') or 'Not provided'}",
            f"Request: {analysis.get('request_type') or analysis.get('service_requested') or 'Unknown'}",
            f"Score: {analysis.get('lead_score')}/100",
            "",
            f"Summary: {analysis.get('ai_summary')}",
            "",
            f"Recommended Action: {analysis.get('recommended_action')}",
        ]
    )
    conn.execute(
        """
        insert into notifications (
            workspace_id, business_id, lead_id, notification_type, channel, recipient, subject, message, status, created_at
        )
        values (?, ?, ?, 'hot_lead_alert', 'dashboard', ?, ?, ?, 'sent', ?)
        """,
        (business.get("workspace_id"), business_id, lead_id, business.get("handoff_email"), subject, message, now()),
    )
    create_event(conn, business_id, lead_id, "notification_created", "Hot lead notification created.", {})

def create_booking(conn: sqlite3.Connection, business_id: int, lead_id: int, analysis: dict[str, Any]) -> None:
    fields = analysis.get("extracted_fields") or {}
    business = get_business(conn, business_id)
    conn.execute(
        """
        insert into bookings (
            workspace_id, business_id, lead_id, customer_name, customer_phone, customer_email, booking_type,
            requested_date, requested_time, number_of_people, service_requested, notes, status, created_at, updated_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'requested', ?, ?)
        """,
        (
            business.get("workspace_id") if business else None,
            business_id,
            lead_id,
            analysis.get("customer_name"),
            analysis.get("customer_phone"),
            analysis.get("customer_email"),
            analysis.get("request_type"),
            analysis.get("timeline"),
            fields.get("requested_time"),
            fields.get("number_of_people"),
            analysis.get("service_requested"),
            analysis.get("ai_summary"),
            now(),
            now(),
        ),
    )
    create_event(conn, business_id, lead_id, "booking_created", "Booking request created.", {})

def create_lead_from_analysis(
    conn: sqlite3.Connection,
    business_id: int,
    transcript: str,
    analysis: dict[str, Any],
    provider: str = "demo",
    call_id: str | None = None,
    caller_phone: str | None = None,
    recording_url: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or now()
    business = get_business(conn, business_id)
    workspace_id = business.get("workspace_id") if business else None
    cur = conn.execute(
        """
        insert into leads (
            workspace_id, business_id, customer_name, customer_phone, customer_email, request_type, service_requested,
            industry, location, urgency, timeline, budget, intent, extracted_fields,
            lead_score, lead_temperature, status, ai_summary, recommended_action, transcript,
            score_breakdown, safety_notes, handoff_triggered, booking_requested, created_at, updated_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            workspace_id,
            business_id,
            analysis.get("customer_name"),
            analysis.get("customer_phone") or caller_phone,
            analysis.get("customer_email"),
            analysis.get("request_type"),
            analysis.get("service_requested"),
            analysis.get("industry"),
            analysis.get("location"),
            analysis.get("urgency"),
            analysis.get("timeline"),
            analysis.get("budget"),
            analysis.get("intent"),
            as_json(analysis.get("extracted_fields") or {}),
            analysis.get("lead_score"),
            analysis.get("lead_temperature"),
            analysis.get("ai_summary"),
            analysis.get("recommended_action"),
            transcript,
            as_json(analysis.get("score_breakdown") or {}),
            as_json(analysis.get("safety_notes") or []),
            1 if analysis.get("handoff_triggered") else 0,
            1 if analysis.get("booking_requested") else 0,
            created,
            created,
        ),
    )
    lead_id = int(cur.lastrowid)
    conn.execute(
        """
        insert into call_logs (
            workspace_id, business_id, lead_id, provider, call_id, caller_phone, transcript, recording_url,
            duration_seconds, call_status, analysis_json, created_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, 'analyzed', ?, ?)
        """,
        (
            workspace_id,
            business_id,
            lead_id,
            provider,
            call_id,
            caller_phone or analysis.get("customer_phone"),
            transcript,
            recording_url,
            max(45, len(transcript.split()) * 2),
            as_json(analysis),
            created,
        ),
    )
    create_event(conn, business_id, lead_id, "lead_created", "Lead created from call analysis.", {}, created)
    create_event(
        conn,
        business_id,
        lead_id,
        "lead_scored",
        f"Lead scored {analysis.get('lead_score')}/100 and marked {analysis.get('lead_temperature')}.",
        analysis.get("score_breakdown"),
        created,
    )
    if analysis.get("booking_requested"):
        create_booking(conn, business_id, lead_id, analysis)
    if analysis.get("handoff_triggered"):
        create_notification(conn, business_id, lead_id, analysis)
        create_event(conn, business_id, lead_id, "human_handoff_triggered", "Human handoff rule triggered.", {})
    return get_lead(conn, lead_id) or {"id": lead_id}
