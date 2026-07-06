from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

from .compliance import active_workspace_id
from .config import CLINIC_BUSINESS_TYPES, clinic_mode


def stats(
    conn: sqlite3.Connection,
    business_type: str | None = None,
    workspace_id: int | None = None,
) -> dict[str, int]:
    workspace_id = active_workspace_id(conn, workspace_id)
    business_clause = " where workspace_id = ?"
    args: list[Any] = [workspace_id]
    if business_type and business_type != "All Businesses":
        business_clause += " and business_type = ?"
        args.append(business_type)
    elif clinic_mode():
        placeholders = ",".join("?" for _ in CLINIC_BUSINESS_TYPES)
        business_clause += f" and business_type in ({placeholders})"
        args.extend(CLINIC_BUSINESS_TYPES)
    businesses = conn.execute(f"select id from businesses{business_clause}", args).fetchall()
    ids = [row["id"] for row in businesses]
    if ids:
        placeholders = ",".join("?" for _ in ids)
        lead_where = f" where business_id in ({placeholders})"
        lead_args = ids
    else:
        lead_where = " where 1 = 0"
        lead_args = []
    today = datetime.now().strftime("%Y-%m-%d")
    # One aggregate pass over leads instead of six separate scans.
    lead_row = conn.execute(
        f"""
        select count(*) as total,
               coalesce(sum(lead_score), 0) as score_sum,
               coalesce(sum(case when lead_temperature = 'hot' then 1 else 0 end), 0) as hot,
               coalesce(sum(case when lead_temperature = 'warm' then 1 else 0 end), 0) as warm,
               coalesce(sum(case when lead_temperature = 'cold' then 1 else 0 end), 0) as cold,
               coalesce(sum(case when handoff_triggered = 1 and status = 'new' then 1 else 0 end), 0) as pending
        from leads{lead_where}
        """,
        lead_args,
    ).fetchone()
    call_row = conn.execute(
        f"""
        select count(*) as total,
               coalesce(sum(case when date(created_at) = ? then 1 else 0 end), 0) as today
        from call_logs{lead_where}
        """,
        [today, *lead_args],
    ).fetchone()
    total_leads = int(lead_row["total"])
    return {
        "businesses": len(ids),
        "active_agents": conn.execute(
            f"select count(*) from businesses{business_clause} {'and' if business_clause else 'where'} status = 'active'",
            args,
        ).fetchone()[0],
        "total_calls": int(call_row["total"]),
        "calls_today": int(call_row["today"]),
        "total_leads": total_leads,
        "hot_leads": int(lead_row["hot"]),
        "warm_leads": int(lead_row["warm"]),
        "cold_leads": int(lead_row["cold"]),
        "bookings": conn.execute(
            f"select count(*) from bookings{lead_where}",
            lead_args,
        ).fetchone()[0],
        "pending_handoffs": int(lead_row["pending"]),
        "avg_score": round(int(lead_row["score_sum"]) / total_leads) if total_leads else 0,
    }
