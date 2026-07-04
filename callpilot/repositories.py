from __future__ import annotations

import sqlite3
from typing import Any

from .integrations import env_connected
from .storage import row_dict


def get_businesses(conn: sqlite3.Connection, business_type: str | None = None) -> list[dict[str, Any]]:
    if business_type and business_type != "All Businesses":
        rows = conn.execute(
            "select * from businesses where business_type = ? order by name",
            (business_type,),
        ).fetchall()
    else:
        rows = conn.execute("select * from businesses order by name").fetchall()
    return [dict(row) for row in rows]

def get_business(conn: sqlite3.Connection, business_id: int) -> dict[str, Any] | None:
    return row_dict(conn.execute("select * from businesses where id = ?", (business_id,)).fetchone())

def get_services(conn: sqlite3.Connection, business_id: int) -> list[dict[str, Any]]:
    rows = conn.execute("select * from services where business_id = ? order by id", (business_id,)).fetchall()
    return [dict(row) for row in rows]

def get_knowledge(conn: sqlite3.Connection, business_id: int) -> list[dict[str, Any]]:
    rows = conn.execute("select * from knowledge_base where business_id = ? order by id", (business_id,)).fetchall()
    return [dict(row) for row in rows]

def get_leads(conn: sqlite3.Connection, filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
    filters = filters or {}
    sql = """
        select leads.*, businesses.name as business_name, businesses.business_type
        from leads
        left join businesses on businesses.id = leads.business_id
    """
    clauses = []
    args: list[Any] = []
    if filters.get("business_id"):
        clauses.append("leads.business_id = ?")
        args.append(filters["business_id"])
    if filters.get("temperature") and filters["temperature"] != "all":
        clauses.append("leads.lead_temperature = ?")
        args.append(filters["temperature"])
    if filters.get("status") and filters["status"] != "all":
        clauses.append("leads.status = ?")
        args.append(filters["status"])
    if filters.get("q"):
        clauses.append(
            "(customer_name like ? or customer_phone like ? or service_requested like ? or businesses.name like ?)"
        )
        needle = f"%{filters['q']}%"
        args.extend([needle, needle, needle, needle])
    if clauses:
        sql += " where " + " and ".join(clauses)
    sql += " order by datetime(leads.created_at) desc"
    return [dict(row) for row in conn.execute(sql, args).fetchall()]

def get_lead(conn: sqlite3.Connection, lead_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        select leads.*, businesses.name as business_name, businesses.business_type, businesses.agent_name,
               businesses.handoff_email, businesses.handoff_phone
        from leads
        left join businesses on businesses.id = leads.business_id
        where leads.id = ?
        """,
        (lead_id,),
    ).fetchone()
    return row_dict(row)

def get_bookings(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select bookings.*, businesses.name as business_name
        from bookings
        left join businesses on businesses.id = bookings.business_id
        order by datetime(bookings.created_at) desc
        """
    ).fetchall()
    return [dict(row) for row in rows]

def get_call_logs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select call_logs.*, businesses.name as business_name, leads.customer_name
        from call_logs
        left join businesses on businesses.id = call_logs.business_id
        left join leads on leads.id = call_logs.lead_id
        order by datetime(call_logs.created_at) desc
        """
    ).fetchall()
    return [dict(row) for row in rows]

def get_notifications(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select notifications.*, businesses.name as business_name, leads.customer_name
        from notifications
        left join businesses on businesses.id = notifications.business_id
        left join leads on leads.id = notifications.lead_id
        order by datetime(notifications.created_at) desc
        """
    ).fetchall()
    return [dict(row) for row in rows]

def get_events(conn: sqlite3.Connection, lead_id: int | None = None) -> list[dict[str, Any]]:
    if lead_id:
        rows = conn.execute(
            "select * from agent_events where lead_id = ? order by datetime(created_at) desc",
            (lead_id,),
        ).fetchall()
    else:
        rows = conn.execute("select * from agent_events order by datetime(created_at) desc limit 12").fetchall()
    return [dict(row) for row in rows]

def production_readiness(conn: sqlite3.Connection, business_id: int) -> dict[str, Any]:
    business = get_business(conn, business_id)
    if not business:
        return {"success": False, "error": "Business not found"}
    services = get_services(conn, business_id)
    knowledge = get_knowledge(conn, business_id)
    checks = [
        ("business_profile", bool(business.get("name") and business.get("business_type"))),
        ("services_configured", bool(services)),
        ("knowledge_base_configured", bool(knowledge)),
        ("module_selected", bool(business.get("module_key"))),
        ("allowed_call_types", bool(business.get("allowed_call_types"))),
        ("blocked_outcomes", bool(business.get("blocked_outcomes"))),
        ("language_policy", bool(business.get("supported_languages"))),
        ("compliance_profile", bool(business.get("compliance_profile"))),
        ("consent_policy", bool(business.get("consent_policy"))),
        ("recording_disclosure", bool(business.get("recording_disclosure"))),
        ("handoff_contact", bool(business.get("handoff_phone") or business.get("handoff_email"))),
        ("qa_checks", bool(business.get("qa_checks"))),
    ]
    integration_checks = {
        "twilio": env_connected("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"),
        "openai": env_connected("OPENAI_API_KEY"),
        "vapi": env_connected("VAPI_API_KEY"),
        "retell": env_connected("RETELL_API_KEY"),
        "deepgram": env_connected("DEEPGRAM_API_KEY"),
        "elevenlabs": env_connected("ELEVENLABS_API_KEY"),
    }
    missing = [name for name, ok in checks if not ok]
    configured = [name for name, ok in checks if ok]
    connected_integrations = [name for name, ok in integration_checks.items() if ok]
    demo_risks = [
        "Voice/AI providers are still in demo mode until production keys and signed webhooks are configured."
        if not connected_integrations
        else "",
        "Calendar/CRM/PMS/EHR/POS integrations must be connected before confirming live bookings or account actions."
        if not business.get("integration_targets")
        else "",
    ]
    demo_risks = [item for item in demo_risks if item]
    ready = not missing and bool(connected_integrations)
    return {
        "success": True,
        "business_id": business_id,
        "business_name": business.get("name"),
        "module_key": business.get("module_key") or "custom",
        "workflow_version": business.get("workflow_version") or "v1",
        "ready_for_production": ready,
        "configured_checks": configured,
        "missing_checks": missing,
        "integration_status": integration_checks,
        "demo_risks": demo_risks,
        "next_actions": missing
        or (
            ["Connect at least one production voice/AI provider and enable webhook signature verification."]
            if not connected_integrations
            else ["Run golden call, safety, language, and tool-call QA before launch."]
        ),
    }
