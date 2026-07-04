from __future__ import annotations

import sqlite3
from typing import Any

from .compliance import audit_event, default_workspace_id
from .utils import as_json, from_json, now


def enqueue_job(
    conn: sqlite3.Connection,
    workspace_id: int | None,
    job_type: str,
    resource_type: str,
    resource_id: int | str | None,
    payload: dict[str, Any] | None = None,
    scheduled_at: str | None = None,
    max_attempts: int = 3,
    priority: int = 5,
) -> int:
    workspace_id = workspace_id or default_workspace_id(conn)
    return int(
        conn.execute(
            """
            insert into jobs (
                workspace_id, job_type, resource_type, resource_id, payload, status,
                priority, attempts, max_attempts, scheduled_at, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, 'pending', ?, 0, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                job_type,
                resource_type,
                str(resource_id) if resource_id is not None else None,
                as_json(payload or {}),
                priority,
                max_attempts,
                scheduled_at or now(),
                now(),
                now(),
            ),
        ).lastrowid
    )


def get_jobs(conn: sqlite3.Connection, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    sql = "select * from jobs"
    args: list[Any] = []
    if status and status != "all":
        sql += " where status = ?"
        args.append(status)
    sql += " order by datetime(scheduled_at), priority asc, id asc limit ?"
    args.append(limit)
    return [dict(row) for row in conn.execute(sql, args).fetchall()]


def complete_job(conn: sqlite3.Connection, job_id: int, result: dict[str, Any]) -> None:
    conn.execute(
        "update jobs set status='completed', result=?, finished_at=?, updated_at=? where id=?",
        (as_json(result), now(), now(), job_id),
    )


def fail_job(conn: sqlite3.Connection, job: dict[str, Any], error: str) -> None:
    attempts = int(job.get("attempts") or 0)
    max_attempts = int(job.get("max_attempts") or 1)
    status = "failed" if attempts >= max_attempts else "pending"
    conn.execute(
        "update jobs set status=?, error=?, finished_at=?, updated_at=? where id=?",
        (status, error, now() if status == "failed" else None, now(), job["id"]),
    )


def run_campaign_call_prepare(conn: sqlite3.Connection, job: dict[str, Any]) -> dict[str, Any]:
    from .campaigns import suppression_reason
    from .repositories import get_business

    payload = from_json(job.get("payload"), {})
    recipient_id = int(payload.get("recipient_id") or job.get("resource_id") or 0)
    row = conn.execute("select * from campaign_recipients where id = ?", (recipient_id,)).fetchone()
    if not row:
        return {"status": "skipped", "reason": "recipient_not_found"}
    recipient = dict(row)
    business = get_business(conn, int(recipient["business_id"]))
    if not business:
        return {"status": "skipped", "reason": "business_not_found"}
    if recipient["status"] not in {"queued", "ready"}:
        return {"status": "skipped", "reason": f"recipient_status_{recipient['status']}"}

    reason = suppression_reason(conn, business, recipient.get("customer_phone") or "")
    if reason:
        conn.execute(
            """
            update campaign_recipients
            set status='suppressed', suppression_reason=?, updated_at=?
            where id=?
            """,
            (reason, now(), recipient_id),
        )
        audit_event(
            conn,
            recipient["workspace_id"],
            "worker",
            "campaign_recipient_suppressed",
            "campaign_recipient",
            recipient_id,
            {"reason": reason},
        )
        return {"status": "suppressed", "reason": reason}

    conn.execute(
        """
        update campaign_recipients
        set status='ready', last_attempt_at=?, updated_at=?
        where id=?
        """,
        (now(), now(), recipient_id),
    )
    audit_event(
        conn,
        recipient["workspace_id"],
        "worker",
        "campaign_recipient_ready",
        "campaign_recipient",
        recipient_id,
        {"campaign_id": recipient["campaign_id"]},
    )
    return {"status": "ready_for_dialer", "reason": "manual_worker_prepared_only"}


def run_post_call_qa(conn: sqlite3.Connection, job: dict[str, Any]) -> dict[str, Any]:
    from .qa import evaluate_call_log

    payload = from_json(job.get("payload"), {})
    call_log_id = int(payload.get("call_log_id") or job.get("resource_id") or 0)
    result = evaluate_call_log(conn, call_log_id)
    return {"status": "evaluated", "qa": result}


def run_job(conn: sqlite3.Connection, job: dict[str, Any]) -> dict[str, Any]:
    conn.execute(
        "update jobs set status='running', attempts=attempts+1, started_at=?, updated_at=? where id=?",
        (now(), now(), job["id"]),
    )
    job = dict(conn.execute("select * from jobs where id = ?", (job["id"],)).fetchone())
    try:
        if job["job_type"] == "campaign_call_prepare":
            result = run_campaign_call_prepare(conn, job)
        elif job["job_type"] == "post_call_qa":
            result = run_post_call_qa(conn, job)
        else:
            result = {"status": "skipped", "reason": f"unknown_job_type_{job['job_type']}"}
        complete_job(conn, int(job["id"]), result)
        return {"job_id": job["id"], "status": "completed", "result": result}
    except Exception as error:
        fail_job(conn, job, str(error))
        return {"job_id": job["id"], "status": "failed", "error": str(error)}


def run_due_jobs(conn: sqlite3.Connection, limit: int = 20) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select * from jobs
        where status = 'pending' and datetime(scheduled_at) <= datetime(?)
        order by priority asc, datetime(scheduled_at), id
        limit ?
        """,
        (now(), limit),
    ).fetchall()
    return [run_job(conn, dict(row)) for row in rows]


def schedule_campaign_jobs(conn: sqlite3.Connection, campaign_id: int) -> int:
    recipients = conn.execute(
        "select * from campaign_recipients where campaign_id = ? and status = 'queued'",
        (campaign_id,),
    ).fetchall()
    created = 0
    for row in recipients:
        existing = conn.execute(
            """
            select id from jobs
            where job_type='campaign_call_prepare' and resource_type='campaign_recipient'
              and resource_id=? and status in ('pending', 'running', 'completed')
            """,
            (str(row["id"]),),
        ).fetchone()
        if existing:
            continue
        enqueue_job(
            conn,
            row["workspace_id"],
            "campaign_call_prepare",
            "campaign_recipient",
            row["id"],
            {"campaign_id": row["campaign_id"], "recipient_id": row["id"]},
            max_attempts=1,
            priority=3,
        )
        created += 1
    return created
