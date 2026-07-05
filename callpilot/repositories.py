from __future__ import annotations

import sqlite3
from typing import Any

from .compliance import active_workspace_id
from .config import CLINIC_BUSINESS_TYPES, clinic_mode
from .integrations import env_connected
from .storage import row_dict


def clinic_business_clause(prefix: str = "businesses") -> tuple[str, list[Any]]:
    if not clinic_mode():
        return "", []
    placeholders = ",".join("?" for _ in CLINIC_BUSINESS_TYPES)
    return f"{prefix}.business_type in ({placeholders})", list(CLINIC_BUSINESS_TYPES)


def get_businesses(
    conn: sqlite3.Connection,
    business_type: str | None = None,
    workspace_id: int | None = None,
) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    sql = "select * from businesses where workspace_id = ?"
    args: list[Any] = [workspace_id]
    if business_type and business_type != "All Businesses":
        sql += " and business_type = ?"
        args.append(business_type)
    else:
        clinic_clause, clinic_args = clinic_business_clause("businesses")
        if clinic_clause:
            sql += f" and {clinic_clause}"
            args.extend(clinic_args)
    sql += " order by name"
    rows = conn.execute(sql, args).fetchall()
    return [dict(row) for row in rows]

def get_business(
    conn: sqlite3.Connection,
    business_id: int,
    workspace_id: int | None = None,
) -> dict[str, Any] | None:
    workspace_id = active_workspace_id(conn, workspace_id)
    clinic_clause, clinic_args = clinic_business_clause("businesses")
    extra = f" and {clinic_clause}" if clinic_clause else ""
    return row_dict(
        conn.execute(
            f"select * from businesses where id = ? and workspace_id = ?{extra}",
            (business_id, workspace_id, *clinic_args),
        ).fetchone()
    )

def get_services(
    conn: sqlite3.Connection,
    business_id: int,
    workspace_id: int | None = None,
) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    rows = conn.execute(
        """
        select services.*
        from services
        join businesses on businesses.id = services.business_id
        where services.business_id = ? and businesses.workspace_id = ?
        order by services.name
        """,
        (business_id, workspace_id),
    ).fetchall()
    return [dict(row) for row in rows]

def get_knowledge(
    conn: sqlite3.Connection,
    business_id: int,
    workspace_id: int | None = None,
) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    rows = conn.execute(
        """
        select knowledge_base.*
        from knowledge_base
        join businesses on businesses.id = knowledge_base.business_id
        where knowledge_base.business_id = ?
          and businesses.workspace_id = ?
          and coalesce(knowledge_base.status, 'approved') = 'approved'
        order by knowledge_base.id
        """,
        (business_id, workspace_id),
    ).fetchall()
    return [dict(row) for row in rows]

def get_leads(
    conn: sqlite3.Connection,
    filters: dict[str, str] | None = None,
    workspace_id: int | None = None,
) -> list[dict[str, Any]]:
    filters = filters or {}
    workspace_id = active_workspace_id(conn, workspace_id)
    sql = """
        select leads.*, businesses.name as business_name, businesses.business_type
        from leads
        left join businesses on businesses.id = leads.business_id
    """
    clauses = ["leads.workspace_id = ?"]
    args: list[Any] = [workspace_id]
    clinic_clause, clinic_args = clinic_business_clause("businesses")
    if clinic_clause:
        clauses.append(clinic_clause)
        args.extend(clinic_args)
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

def get_lead(
    conn: sqlite3.Connection,
    lead_id: int,
    workspace_id: int | None = None,
) -> dict[str, Any] | None:
    workspace_id = active_workspace_id(conn, workspace_id)
    clinic_clause, clinic_args = clinic_business_clause("businesses")
    extra = f" and {clinic_clause}" if clinic_clause else ""
    row = conn.execute(
        f"""
        select leads.*, businesses.name as business_name, businesses.business_type, businesses.agent_name,
               businesses.handoff_email, businesses.handoff_phone
        from leads
        left join businesses on businesses.id = leads.business_id
        where leads.id = ? and leads.workspace_id = ?{extra}
        """,
        (lead_id, workspace_id, *clinic_args),
    ).fetchone()
    return row_dict(row)

def get_bookings(conn: sqlite3.Connection, workspace_id: int | None = None) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    clinic_clause, clinic_args = clinic_business_clause("businesses")
    extra = f" and {clinic_clause}" if clinic_clause else ""
    rows = conn.execute(
        f"""
        select bookings.*, businesses.name as business_name
        from bookings
        left join businesses on businesses.id = bookings.business_id
        where bookings.workspace_id = ?{extra}
        order by datetime(bookings.created_at) desc
        """,
        (workspace_id, *clinic_args),
    ).fetchall()
    return [dict(row) for row in rows]

def get_call_logs(conn: sqlite3.Connection, workspace_id: int | None = None) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    clinic_clause, clinic_args = clinic_business_clause("businesses")
    extra = f" and {clinic_clause}" if clinic_clause else ""
    rows = conn.execute(
        f"""
        select call_logs.*, businesses.name as business_name, leads.customer_name
        from call_logs
        left join businesses on businesses.id = call_logs.business_id
        left join leads on leads.id = call_logs.lead_id
        where call_logs.workspace_id = ?{extra}
        order by datetime(call_logs.created_at) desc
        """,
        (workspace_id, *clinic_args),
    ).fetchall()
    return [dict(row) for row in rows]

def get_notifications(conn: sqlite3.Connection, workspace_id: int | None = None) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    clinic_clause, clinic_args = clinic_business_clause("businesses")
    extra = f" and {clinic_clause}" if clinic_clause else ""
    rows = conn.execute(
        f"""
        select notifications.*, businesses.name as business_name, leads.customer_name
        from notifications
        left join businesses on businesses.id = notifications.business_id
        left join leads on leads.id = notifications.lead_id
        where notifications.workspace_id = ?{extra}
        order by datetime(notifications.created_at) desc
        """,
        (workspace_id, *clinic_args),
    ).fetchall()
    return [dict(row) for row in rows]

def get_qa_evaluations(
    conn: sqlite3.Connection,
    status: str | None = None,
    workspace_id: int | None = None,
) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    clinic_clause, clinic_args = clinic_business_clause("businesses")
    sql = """
        select qa_evaluations.*, businesses.name as business_name, businesses.business_type,
               leads.customer_name, call_logs.provider, call_logs.created_at as call_created_at
        from qa_evaluations
        left join businesses on businesses.id = qa_evaluations.business_id
        left join leads on leads.id = qa_evaluations.lead_id
        left join call_logs on call_logs.id = qa_evaluations.call_log_id
    """
    args: list[Any] = [workspace_id]
    sql += " where qa_evaluations.workspace_id = ?"
    if clinic_clause:
        sql += f" and {clinic_clause}"
        args.extend(clinic_args)
    if status and status != "all":
        sql += " and qa_evaluations.qa_status = ?"
        args.append(status)
    sql += " order by datetime(qa_evaluations.evaluated_at) desc"
    return [dict(row) for row in conn.execute(sql, args).fetchall()]

def get_qa_for_lead(
    conn: sqlite3.Connection,
    lead_id: int,
    workspace_id: int | None = None,
) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    clinic_clause, clinic_args = clinic_business_clause("businesses")
    extra = f" and {clinic_clause}" if clinic_clause else ""
    rows = conn.execute(
        f"""
        select qa_evaluations.*, call_logs.provider, call_logs.created_at as call_created_at
        from qa_evaluations
        left join call_logs on call_logs.id = qa_evaluations.call_log_id
        left join businesses on businesses.id = qa_evaluations.business_id
        where qa_evaluations.lead_id = ? and qa_evaluations.workspace_id = ?{extra}
        order by datetime(qa_evaluations.evaluated_at) desc
        """,
        (lead_id, workspace_id, *clinic_args),
    ).fetchall()
    return [dict(row) for row in rows]

def get_events(
    conn: sqlite3.Connection,
    lead_id: int | None = None,
    workspace_id: int | None = None,
) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    clinic_clause, clinic_args = clinic_business_clause("businesses")
    extra = f" and {clinic_clause}" if clinic_clause else ""
    if lead_id:
        rows = conn.execute(
            f"""
            select agent_events.* from agent_events
            left join businesses on businesses.id = agent_events.business_id
            where lead_id = ? and agent_events.workspace_id = ?{extra}
            order by datetime(agent_events.created_at) desc
            """,
            (lead_id, workspace_id, *clinic_args),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            select agent_events.* from agent_events
            left join businesses on businesses.id = agent_events.business_id
            where agent_events.workspace_id = ?{extra}
            order by datetime(agent_events.created_at) desc
            limit 12
            """,
            (workspace_id, *clinic_args),
        ).fetchall()
    return [dict(row) for row in rows]

def production_readiness(
    conn: sqlite3.Connection,
    business_id: int,
    workspace_id: int | None = None,
) -> dict[str, Any]:
    workspace_id = active_workspace_id(conn, workspace_id)
    business = get_business(conn, business_id, workspace_id)
    if not business:
        return {"success": False, "error": "Business not found"}
    services = get_services(conn, business_id, workspace_id)
    knowledge = get_knowledge(conn, business_id, workspace_id)
    checks = [
        ("workspace_assigned", bool(business.get("workspace_id"))),
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
    staff_count = conn.execute(
        "select count(*) from staff_contacts where business_id = ? and receives_handoff = 1",
        (business_id,),
    ).fetchone()[0]
    consent_count = conn.execute(
        "select count(*) from consent_records where business_id = ? and status = 'active'",
        (business_id,),
    ).fetchone()[0]
    dnc_count = conn.execute(
        "select count(*) from do_not_call where workspace_id = ? and status = 'active'",
        (business.get("workspace_id"),),
    ).fetchone()[0]
    if not staff_count:
        checks.append(("staff_handoff_contact", False))
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
        "workspace_id": business.get("workspace_id"),
        "compliance_counts": {
            "staff_handoff_contacts": staff_count,
            "active_consent_records": consent_count,
            "workspace_dnc_entries": dnc_count,
        },
        "demo_risks": demo_risks,
        "next_actions": missing
        or (
            ["Connect at least one production voice/AI provider and enable webhook signature verification."]
            if not connected_integrations
            else ["Run golden call, safety, language, and tool-call QA before launch."]
        ),
    }
