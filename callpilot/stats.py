from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any


def stats(conn: sqlite3.Connection, business_type: str | None = None) -> dict[str, int]:
    business_clause = ""
    args: list[Any] = []
    if business_type and business_type != "All Businesses":
        business_clause = " where business_type = ?"
        args.append(business_type)
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
    total_leads = conn.execute(f"select count(*) from leads{lead_where}", lead_args).fetchone()[0]
    total_score = conn.execute(f"select coalesce(sum(lead_score), 0) from leads{lead_where}", lead_args).fetchone()[0]
    return {
        "businesses": len(ids),
        "active_agents": conn.execute(
            f"select count(*) from businesses{business_clause} {'and' if business_clause else 'where'} status = 'active'",
            args,
        ).fetchone()[0],
        "total_calls": conn.execute(
            f"select count(*) from call_logs{lead_where.replace('business_id', 'business_id')}",
            lead_args,
        ).fetchone()[0],
        "calls_today": conn.execute(
            f"select count(*) from call_logs{lead_where} and date(created_at) = ?",
            [*lead_args, today],
        ).fetchone()[0],
        "total_leads": total_leads,
        "hot_leads": conn.execute(
            f"select count(*) from leads{lead_where} and lead_temperature = 'hot'",
            lead_args,
        ).fetchone()[0],
        "warm_leads": conn.execute(
            f"select count(*) from leads{lead_where} and lead_temperature = 'warm'",
            lead_args,
        ).fetchone()[0],
        "cold_leads": conn.execute(
            f"select count(*) from leads{lead_where} and lead_temperature = 'cold'",
            lead_args,
        ).fetchone()[0],
        "bookings": conn.execute(
            f"select count(*) from bookings{lead_where}",
            lead_args,
        ).fetchone()[0],
        "pending_handoffs": conn.execute(
            f"select count(*) from leads{lead_where} and handoff_triggered = 1 and status = 'new'",
            lead_args,
        ).fetchone()[0],
        "avg_score": round(total_score / total_leads) if total_leads else 0,
    }
