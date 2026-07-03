from __future__ import annotations

import sqlite3
from typing import Any

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
