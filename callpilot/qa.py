from __future__ import annotations

import sqlite3
from typing import Any

from .utils import as_json, from_json, now


QA_RULES = {
    "transcript_present": 15,
    "contact_or_handoff": 15,
    "summary_present": 10,
    "safety_guardrails": 20,
    "booking_integrity": 15,
    "language_policy": 10,
    "actionable_next_step": 15,
}


def qa_status(score: int, critical_failures: list[str]) -> str:
    if critical_failures:
        return "fail"
    if score >= 85:
        return "pass"
    if score >= 65:
        return "review"
    return "fail"


def evaluate_payload(
    transcript: str,
    analysis: dict[str, Any],
    business: dict[str, Any],
    lead: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lead = lead or {}
    score = 0
    findings: list[str] = []
    failures: list[str] = []
    breakdown: dict[str, int] = {key: 0 for key in QA_RULES}

    if transcript.strip():
        breakdown["transcript_present"] = QA_RULES["transcript_present"]
    else:
        failures.append("Transcript is missing.")

    has_contact = bool(analysis.get("customer_phone") or analysis.get("customer_email") or lead.get("customer_phone") or lead.get("customer_email"))
    handoff = bool(analysis.get("handoff_triggered") or lead.get("handoff_triggered"))
    if has_contact or handoff:
        breakdown["contact_or_handoff"] = QA_RULES["contact_or_handoff"]
    else:
        findings.append("No contact detail and no human handoff were captured.")

    if analysis.get("ai_summary") or lead.get("ai_summary"):
        breakdown["summary_present"] = QA_RULES["summary_present"]
    else:
        findings.append("AI summary is missing.")

    safety_notes = analysis.get("safety_notes") or from_json(lead.get("safety_notes"), [])
    regulated = business.get("business_type") in {"Clinic", "Hospital", "Dentist", "Law Firm", "Legal", "Insurance", "Finance"}
    advice_request = bool((analysis.get("extracted_fields") or {}).get("advice_request"))
    if not regulated or safety_notes:
        breakdown["safety_guardrails"] = QA_RULES["safety_guardrails"]
    else:
        failures.append("Regulated call has no safety guardrail notes.")
    if advice_request and not handoff:
        failures.append("Regulated advice request did not trigger human handoff.")

    booking_requested = bool(analysis.get("booking_requested") or lead.get("booking_requested"))
    booking_confirm_language = any(word in transcript.lower() for word in ["confirmed booking", "appointment confirmed", "reservation confirmed"])
    if not (booking_requested and booking_confirm_language):
        breakdown["booking_integrity"] = QA_RULES["booking_integrity"]
    else:
        failures.append("Call appears to confirm a booking before connected availability/staff confirmation.")

    extracted = analysis.get("extracted_fields") or from_json(lead.get("extracted_fields"), {})
    if not extracted.get("unsupported_language"):
        breakdown["language_policy"] = QA_RULES["language_policy"]
    elif handoff:
        breakdown["language_policy"] = max(0, QA_RULES["language_policy"] - 3)
        findings.append("Unsupported language was detected and routed to handoff.")
    else:
        failures.append("Unsupported language was not routed to handoff.")

    if analysis.get("recommended_action") or lead.get("recommended_action"):
        breakdown["actionable_next_step"] = QA_RULES["actionable_next_step"]
    else:
        findings.append("Recommended action is missing.")

    score = max(0, min(100, sum(breakdown.values())))
    status = qa_status(score, failures)
    return {
        "qa_score": score,
        "qa_status": status,
        "rule_breakdown": breakdown,
        "findings": findings,
        "critical_failures": failures,
        "review_required": status != "pass",
    }


def evaluate_call_log(conn: sqlite3.Connection, call_log_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        select call_logs.*, businesses.business_type, businesses.name as business_name, businesses.workspace_id,
               leads.safety_notes, leads.extracted_fields, leads.ai_summary, leads.recommended_action,
               leads.customer_phone, leads.customer_email, leads.handoff_triggered, leads.booking_requested
        from call_logs
        left join businesses on businesses.id = call_logs.business_id
        left join leads on leads.id = call_logs.lead_id
        where call_logs.id = ?
        """,
        (call_log_id,),
    ).fetchone()
    if not row:
        return None
    business = {
        "id": row["business_id"],
        "name": row["business_name"],
        "business_type": row["business_type"],
        "workspace_id": row["workspace_id"],
    }
    lead = {
        "safety_notes": row["safety_notes"],
        "extracted_fields": row["extracted_fields"],
        "ai_summary": row["ai_summary"],
        "recommended_action": row["recommended_action"],
        "customer_phone": row["customer_phone"],
        "customer_email": row["customer_email"],
        "handoff_triggered": row["handoff_triggered"],
        "booking_requested": row["booking_requested"],
    }
    analysis = from_json(row["analysis_json"], {})
    result = evaluate_payload(row["transcript"] or "", analysis, business, lead)
    existing = conn.execute("select id from qa_evaluations where call_log_id = ?", (call_log_id,)).fetchone()
    if existing:
        conn.execute(
            """
            update qa_evaluations
            set qa_score=?, qa_status=?, rule_breakdown=?, findings=?, critical_failures=?,
                review_required=?, evaluated_at=?
            where id=?
            """,
            (
                result["qa_score"],
                result["qa_status"],
                as_json(result["rule_breakdown"]),
                as_json(result["findings"]),
                as_json(result["critical_failures"]),
                1 if result["review_required"] else 0,
                now(),
                existing["id"],
            ),
        )
        result["id"] = int(existing["id"])
    else:
        result["id"] = int(
            conn.execute(
                """
                insert into qa_evaluations (
                    workspace_id, business_id, lead_id, call_log_id, qa_score, qa_status,
                    rule_breakdown, findings, critical_failures, review_required, evaluated_at, created_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["workspace_id"],
                    row["business_id"],
                    row["lead_id"],
                    call_log_id,
                    result["qa_score"],
                    result["qa_status"],
                    as_json(result["rule_breakdown"]),
                    as_json(result["findings"]),
                    as_json(result["critical_failures"]),
                    1 if result["review_required"] else 0,
                    now(),
                    now(),
                ),
            ).lastrowid
        )
    return result


def backfill_qa_evaluations(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        """
        select call_logs.id
        from call_logs
        left join qa_evaluations on qa_evaluations.call_log_id = call_logs.id
        where qa_evaluations.id is null
        order by call_logs.id
        """
    ).fetchall()
    for row in rows:
        evaluate_call_log(conn, int(row["id"]))
    return len(rows)
