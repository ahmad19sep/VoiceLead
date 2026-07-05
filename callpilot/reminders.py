from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any

from .clinic import get_clinic_profile
from .compliance import audit_event, outbound_allowed
from .jobs import enqueue_job
from .repositories import get_business
from .utils import now


REMINDER_POLICY_VERSION = "clinic-reminder-v1"

# Approved trilingual reminder scripts. No medical content — appointment
# logistics only, with a clear opt-out sentence in every language.
REMINDER_SCRIPTS: dict[str, str] = {
    "en": (
        "Hello, this is a reminder from {clinic_name} about your appointment on {date} at {time}. "
        "If you need to cancel or reschedule, please call us back. "
        "Say stop or call us to opt out of reminder calls."
    ),
    "ur": (
        "Assalam o alaikum, yeh {clinic_name} ki taraf se yaad-dehani hai: aap ki appointment {date} ko {time} par hai. "
        "Agar cancel ya reschedule karna ho to barah-e-karam humein call karen. "
        "Reminder calls band karwane ke liye stop kahen ya humein call karen."
    ),
    "ar": (
        "مرحبا، هذا تذكير من عيادة {clinic_name} بموعدك بتاريخ {date} في تمام {time}. "
        "إذا أردت الإلغاء أو إعادة الجدولة، يرجى معاودة الاتصال بنا. "
        "قل توقف أو اتصل بنا لإيقاف مكالمات التذكير."
    ),
}

_WINDOW_PATTERN = re.compile(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})")
DEFAULT_CALL_WINDOW = ((9, 0), (20, 0))


def parse_call_window(text: str | None) -> tuple[tuple[int, int], tuple[int, int]]:
    """Parse the business allowed-calling window ("09:00-18:00 ...")."""
    match = _WINDOW_PATTERN.search(text or "")
    if not match:
        return DEFAULT_CALL_WINDOW
    start = (min(23, int(match.group(1))), min(59, int(match.group(2))))
    end = (min(23, int(match.group(3))), min(59, int(match.group(4))))
    return (start, end)


def within_call_window(window: tuple[tuple[int, int], tuple[int, int]], at: datetime) -> bool:
    start, end = window
    minutes = at.hour * 60 + at.minute
    return start[0] * 60 + start[1] <= minutes < end[0] * 60 + end[1]


def next_window_start(window: tuple[tuple[int, int], tuple[int, int]], at: datetime) -> datetime:
    start, _ = window
    candidate = at.replace(hour=start[0], minute=start[1], second=0, microsecond=0)
    if candidate <= at:
        candidate += timedelta(days=1)
    return candidate


def reminder_language(profile: dict[str, Any]) -> str:
    language = (profile.get("default_language") or "en").strip().lower()
    return language if language in REMINDER_SCRIPTS else "en"


def build_reminder_message(clinic_name: str, language: str, date: str, time_text: str) -> str:
    script = REMINDER_SCRIPTS.get(language, REMINDER_SCRIPTS["en"])
    return script.format(
        clinic_name=clinic_name or "the clinic",
        date=date or "your scheduled date",
        time=time_text or "the scheduled time",
    )


def _reminder_due_at(booking: dict[str, Any], offset_hours: int) -> str:
    """Best-effort: schedule at appointment time minus offset when parseable."""
    raw_date = (booking.get("requested_date") or "").strip()
    raw_time = (booking.get("requested_time") or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            value = f"{raw_date} {raw_time}".strip() if fmt.endswith("%H:%M") else raw_date
            appointment = datetime.strptime(value, fmt)
            return (appointment - timedelta(hours=offset_hours)).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return now()


def schedule_appointment_reminders(conn: sqlite3.Connection, workspace_id: int | None = None) -> int:
    """Enqueue at most one reminder job per confirmed clinic booking."""
    created = 0
    rows = conn.execute(
        """
        select bookings.*, businesses.business_type
        from bookings
        join businesses on businesses.id = bookings.business_id
        where bookings.status = 'confirmed'
          and businesses.business_type in ('Clinic', 'Hospital', 'Dentist')
        """
    ).fetchall()
    for row in rows:
        booking = dict(row)
        profile = get_clinic_profile(conn, int(booking["business_id"]), booking.get("workspace_id"))
        if not profile.get("reminders_enabled"):
            continue
        existing = conn.execute(
            """
            select id from jobs
            where job_type='appointment_reminder' and resource_type='booking' and resource_id=?
            """,
            (str(booking["id"]),),
        ).fetchone()
        if existing:
            continue
        enqueue_job(
            conn,
            booking.get("workspace_id"),
            "appointment_reminder",
            "booking",
            booking["id"],
            {"booking_id": booking["id"], "policy_version": REMINDER_POLICY_VERSION},
            scheduled_at=_reminder_due_at(booking, int(profile.get("reminder_offset_hours") or 24)),
            max_attempts=1,
            priority=2,
        )
        created += 1
    return created


def run_appointment_reminder(conn: sqlite3.Connection, job: dict[str, Any]) -> dict[str, Any]:
    from .utils import from_json

    payload = from_json(job.get("payload"), {})
    booking_id = int(payload.get("booking_id") or job.get("resource_id") or 0)
    row = conn.execute(
        "select * from bookings where id = ? and workspace_id = ?",
        (booking_id, job.get("workspace_id")),
    ).fetchone()
    if not row:
        return {"status": "skipped", "reason": "booking_not_found"}
    booking = dict(row)
    if booking["status"] != "confirmed":
        return {"status": "skipped", "reason": f"booking_status_{booking['status']}"}

    business = get_business(conn, int(booking["business_id"]), int(job["workspace_id"]))
    if not business:
        return {"status": "skipped", "reason": "business_not_found"}
    profile = get_clinic_profile(conn, int(booking["business_id"]), int(job["workspace_id"]))
    if not profile.get("reminders_enabled"):
        return {"status": "skipped", "reason": "reminders_disabled"}

    phone = booking.get("customer_phone") or ""
    allowed, reason = outbound_allowed(conn, business, phone)
    if not allowed:
        audit_event(
            conn,
            job.get("workspace_id"),
            "worker",
            "reminder_suppressed",
            "booking",
            booking_id,
            {"reason": reason, "policy_version": REMINDER_POLICY_VERSION},
        )
        return {"status": "suppressed", "reason": reason}

    window = parse_call_window(business.get("quiet_hours"))
    current = datetime.strptime(now(), "%Y-%m-%d %H:%M:%S")
    if not within_call_window(window, current):
        resume_at = next_window_start(window, current).strftime("%Y-%m-%d %H:%M:%S")
        # Deferral must not consume the single allowed attempt.
        conn.execute(
            "update jobs set status='pending', attempts=0, scheduled_at=?, updated_at=? where id=?",
            (resume_at, now(), job["id"]),
        )
        audit_event(
            conn,
            job.get("workspace_id"),
            "worker",
            "reminder_deferred_quiet_hours",
            "booking",
            booking_id,
            {"resume_at": resume_at},
        )
        return {"status": "deferred", "reason": "outside_call_window", "resume_at": resume_at}

    language = reminder_language(profile)
    message = build_reminder_message(
        business.get("name") or "", language, booking.get("requested_date") or "", booking.get("requested_time") or ""
    )

    from .providers import create_outbound_call

    result = create_outbound_call("twilio", phone, int(booking["business_id"]))
    delivered = bool(result.success and result.provider_call_id)
    conn.execute(
        """
        insert into notifications (
            workspace_id, business_id, lead_id, notification_type, channel, recipient, subject, message, status, created_at
        )
        values (?, ?, ?, 'appointment_reminder', 'voice', ?, ?, ?, ?, ?)
        """,
        (
            job.get("workspace_id"),
            booking["business_id"],
            booking.get("lead_id"),
            phone,
            f"Appointment reminder ({language}): {business.get('name')}",
            message,
            "sent" if delivered else "failed",
            now(),
        ),
    )
    audit_event(
        conn,
        job.get("workspace_id"),
        "worker",
        "reminder_call_attempted",
        "booking",
        booking_id,
        {
            "language": language,
            "delivered": delivered,
            "provider": result.provider,
            "provider_call_id": result.provider_call_id,
            "policy_version": REMINDER_POLICY_VERSION,
        },
    )
    if not delivered:
        # Honest failure: no provider, no fake reminded state, no retry (max one attempt).
        return {"status": "provider_unavailable", "reason": result.message, "language": language}

    from .clinic_workflow import apply_booking_transition

    apply_booking_transition(
        conn,
        booking_id,
        "reminded",
        actor="worker",
        idempotency_key=f"appointment-reminder-{booking_id}",
        note=f"Reminder call delivered in {language}.",
        workspace_id=int(job["workspace_id"]),
    )
    return {
        "status": "delivered",
        "language": language,
        "provider_call_id": result.provider_call_id,
    }
