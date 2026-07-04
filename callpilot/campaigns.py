from __future__ import annotations

import sqlite3
from typing import Any

from .compliance import audit_event, default_workspace_id, has_active_consent, is_do_not_call, normalize_phone
from .repositories import get_business
from .utils import now


def parse_targets(text: str) -> list[dict[str, str]]:
    targets = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) == 1:
            name, phone, notes = "", parts[0], ""
        elif len(parts) == 2:
            name, phone, notes = parts[0], parts[1], ""
        else:
            name, phone, notes = parts[0], parts[1], " | ".join(parts[2:])
        targets.append({"name": name, "phone": phone, "notes": notes})
    return targets


def suppression_reason(conn: sqlite3.Connection, business: dict[str, Any], phone: str) -> str | None:
    workspace_id = int(business.get("workspace_id") or default_workspace_id(conn))
    normalized = normalize_phone(phone)
    if not normalized:
        return "missing_phone"
    if is_do_not_call(conn, normalized, workspace_id):
        return "do_not_call"
    if int(business.get("max_outbound_attempts") or 0) <= 0:
        return "outbound_disabled"
    if not has_active_consent(conn, int(business["id"]), normalized):
        return "missing_consent"
    return None


def create_campaign(
    conn: sqlite3.Connection,
    business_id: int,
    name: str,
    campaign_type: str,
    targets_text: str,
    script: str,
) -> dict[str, Any]:
    business = get_business(conn, business_id)
    if not business:
        raise ValueError("Business not found")
    workspace_id = int(business.get("workspace_id") or default_workspace_id(conn))
    campaign_id = int(
        conn.execute(
            """
            insert into campaigns (
                workspace_id, business_id, name, campaign_type, status, script,
                quiet_hours, max_attempts, created_at, updated_at
            )
            values (?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                business_id,
                name,
                campaign_type,
                script,
                business.get("quiet_hours"),
                int(business.get("max_outbound_attempts") or 0),
                now(),
                now(),
            ),
        ).lastrowid
    )
    queued = 0
    suppressed = 0
    for target in parse_targets(targets_text):
        normalized = normalize_phone(target["phone"])
        reason = suppression_reason(conn, business, normalized)
        status = "suppressed" if reason else "queued"
        if reason:
            suppressed += 1
        else:
            queued += 1
        conn.execute(
            """
            insert into campaign_recipients (
                workspace_id, campaign_id, business_id, customer_name, customer_phone,
                notes, status, suppression_reason, attempts, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                workspace_id,
                campaign_id,
                business_id,
                target["name"],
                normalized,
                target["notes"],
                status,
                reason,
                now(),
                now(),
            ),
        )
    audit_event(
        conn,
        workspace_id,
        "operator",
        "campaign_created",
        "campaign",
        campaign_id,
        {"business_id": business_id, "queued": queued, "suppressed": suppressed},
    )
    return get_campaign(conn, campaign_id) or {"id": campaign_id}


def get_campaigns(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select campaigns.*, businesses.name as business_name,
               count(campaign_recipients.id) as total_recipients,
               sum(case when campaign_recipients.status = 'queued' then 1 else 0 end) as queued_recipients,
               sum(case when campaign_recipients.status = 'suppressed' then 1 else 0 end) as suppressed_recipients
        from campaigns
        left join businesses on businesses.id = campaigns.business_id
        left join campaign_recipients on campaign_recipients.campaign_id = campaigns.id
        group by campaigns.id
        order by datetime(campaigns.created_at) desc
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_campaign(conn: sqlite3.Connection, campaign_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        select campaigns.*, businesses.name as business_name, businesses.business_type
        from campaigns
        left join businesses on businesses.id = campaigns.business_id
        where campaigns.id = ?
        """,
        (campaign_id,),
    ).fetchone()
    return dict(row) if row else None


def get_campaign_recipients(conn: sqlite3.Connection, campaign_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "select * from campaign_recipients where campaign_id = ? order by id",
        (campaign_id,),
    ).fetchall()
    return [dict(row) for row in rows]
