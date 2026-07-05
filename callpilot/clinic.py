from __future__ import annotations

import sqlite3
from typing import Any

from .compliance import active_workspace_id
from .storage import row_dict
from .utils import now


CLINIC_TYPES = {"Clinic", "Hospital", "Dentist"}
LANGUAGES = {"en", "ur", "ar"}
TIMEZONES = {"Asia/Karachi", "Asia/Dubai"}


def is_clinic_type(value: str | None) -> bool:
    return (value or "").strip() in CLINIC_TYPES


def split_parts(line: str, parts: int) -> list[str]:
    pieces = [piece.strip() for piece in line.split("|")]
    while len(pieces) < parts:
        pieces.append("")
    return pieces[:parts]


def parse_block(text: str, parts: int) -> list[list[str]]:
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(split_parts(line, parts))
    return rows


def parse_bool(value: str | None, default: int = 1) -> int:
    clean = (value or "").strip().lower()
    if not clean:
        return default
    return 1 if clean in {"1", "yes", "true", "y", "on"} else 0


def parse_int(value: str | None, default: int) -> int:
    try:
        return int(str(value or "").strip())
    except ValueError:
        return default


def parse_languages(value: str | None) -> list[str]:
    raw = (value or "").replace(";", ",").split(",")
    languages = []
    for item in raw:
        clean = item.strip().lower()
        if clean in LANGUAGES and clean not in languages:
            languages.append(clean)
    return languages


def validate_clinic_profile(form: dict[str, str]) -> list[str]:
    errors = []
    timezone = (form.get("clinic_timezone") or "Asia/Karachi").strip()
    if timezone not in TIMEZONES:
        errors.append("Clinic timezone must be Asia/Karachi or Asia/Dubai.")
    languages = parse_languages(form.get("clinic_supported_languages") or "en,ur")
    if not languages:
        errors.append("At least one supported clinic language is required.")
    default_language = (form.get("clinic_default_language") or "").strip().lower()
    if default_language and default_language not in languages:
        errors.append("Default language must be included in supported languages.")
    if parse_int(form.get("clinic_cancellation_window_hours"), 24) < 0:
        errors.append("Cancellation window cannot be negative.")
    if parse_int(form.get("clinic_reminder_offset_hours"), 24) < 1:
        errors.append("Reminder offset must be at least 1 hour.")

    providers = [row for row in parse_block(form.get("clinic_providers", ""), 6) if row[0].lower() != "name"]
    locations = [row for row in parse_block(form.get("clinic_locations", ""), 5) if row[0].lower() != "name"]
    if not providers:
        errors.append("At least one clinic provider/doctor is required.")
    if not locations:
        errors.append("At least one clinic location is required.")
    return errors


def default_clinic_profile() -> dict[str, Any]:
    return {
        "timezone": "Asia/Karachi",
        "supported_languages": "en,ur",
        "default_language": "ur",
        "insurance_accepted": "Cash, card, and clinic-approved insurance panels.",
        "cancellation_window_hours": 24,
        "after_hours_policy": "Capture caller name and callback number, then create a next-business-day staff task.",
        "emergency_policy": "Use the approved emergency script and alert clinic staff immediately. Do not provide medical advice.",
        "recording_disclosure_enabled": 1,
        "reminders_enabled": 0,
        "reminder_offset_hours": 24,
    }


def get_clinic_profile(conn: sqlite3.Connection, business_id: int, workspace_id: int | None = None) -> dict[str, Any]:
    workspace_id = active_workspace_id(conn, workspace_id)
    row = conn.execute(
        "select * from clinic_profiles where business_id = ? and workspace_id = ?",
        (business_id, workspace_id),
    ).fetchone()
    profile = default_clinic_profile()
    if row:
        profile.update(dict(row))
    return profile


def get_clinic_providers(conn: sqlite3.Connection, business_id: int, workspace_id: int | None = None) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    rows = conn.execute(
        """
        select * from clinic_providers
        where business_id = ? and workspace_id = ?
        order by active desc, name
        """,
        (business_id, workspace_id),
    ).fetchall()
    return [dict(row) for row in rows]


def get_clinic_locations(conn: sqlite3.Connection, business_id: int, workspace_id: int | None = None) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    rows = conn.execute(
        """
        select * from clinic_locations
        where business_id = ? and workspace_id = ?
        order by active desc, name
        """,
        (business_id, workspace_id),
    ).fetchall()
    return [dict(row) for row in rows]


def get_clinic_holidays(conn: sqlite3.Connection, business_id: int, workspace_id: int | None = None) -> list[dict[str, Any]]:
    workspace_id = active_workspace_id(conn, workspace_id)
    rows = conn.execute(
        """
        select * from clinic_holidays
        where business_id = ? and workspace_id = ?
        order by holiday_type, coalesce(date_value, weekday), name
        """,
        (business_id, workspace_id),
    ).fetchall()
    return [dict(row) for row in rows]


def save_clinic_setup(
    conn: sqlite3.Connection,
    workspace_id: int,
    business_id: int,
    form: dict[str, str],
) -> None:
    errors = validate_clinic_profile(form)
    if errors:
        raise ValueError(" ".join(errors))
    timestamp = now()
    profile = {
        "timezone": (form.get("clinic_timezone") or "Asia/Karachi").strip(),
        "supported_languages": ",".join(parse_languages(form.get("clinic_supported_languages") or "en,ur")),
        "default_language": (form.get("clinic_default_language") or "ur").strip().lower(),
        "insurance_accepted": form.get("clinic_insurance_accepted") or "",
        "cancellation_window_hours": parse_int(form.get("clinic_cancellation_window_hours"), 24),
        "after_hours_policy": form.get("clinic_after_hours_policy") or "",
        "emergency_policy": form.get("clinic_emergency_policy") or "",
        "recording_disclosure_enabled": parse_bool(form.get("clinic_recording_disclosure_enabled"), 1),
        "reminders_enabled": parse_bool(form.get("clinic_reminders_enabled"), 0),
        "reminder_offset_hours": parse_int(form.get("clinic_reminder_offset_hours"), 24),
    }
    existing = row_dict(
        conn.execute(
            "select id from clinic_profiles where business_id = ? and workspace_id = ?",
            (business_id, workspace_id),
        ).fetchone()
    )
    if existing:
        conn.execute(
            """
            update clinic_profiles
            set timezone=?, supported_languages=?, default_language=?, insurance_accepted=?,
                cancellation_window_hours=?, after_hours_policy=?, emergency_policy=?,
                recording_disclosure_enabled=?, reminders_enabled=?, reminder_offset_hours=?, updated_at=?
            where business_id=? and workspace_id=?
            """,
            (
                profile["timezone"],
                profile["supported_languages"],
                profile["default_language"],
                profile["insurance_accepted"],
                profile["cancellation_window_hours"],
                profile["after_hours_policy"],
                profile["emergency_policy"],
                profile["recording_disclosure_enabled"],
                profile["reminders_enabled"],
                profile["reminder_offset_hours"],
                timestamp,
                business_id,
                workspace_id,
            ),
        )
    else:
        conn.execute(
            """
            insert into clinic_profiles (
                workspace_id, business_id, timezone, supported_languages, default_language,
                insurance_accepted, cancellation_window_hours, after_hours_policy, emergency_policy,
                recording_disclosure_enabled, reminders_enabled, reminder_offset_hours, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                business_id,
                profile["timezone"],
                profile["supported_languages"],
                profile["default_language"],
                profile["insurance_accepted"],
                profile["cancellation_window_hours"],
                profile["after_hours_policy"],
                profile["emergency_policy"],
                profile["recording_disclosure_enabled"],
                profile["reminders_enabled"],
                profile["reminder_offset_hours"],
                timestamp,
                timestamp,
            ),
        )

    conn.execute("delete from clinic_providers where business_id=? and workspace_id=?", (business_id, workspace_id))
    for name, role, specialty, languages, location_name, working_hours in parse_block(form.get("clinic_providers", ""), 6):
        if not name or name.lower() == "name":
            continue
        conn.execute(
            """
            insert into clinic_providers (
                workspace_id, business_id, name, role, specialty, languages, location_name,
                working_hours, active, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (workspace_id, business_id, name, role, specialty, languages, location_name, working_hours, timestamp, timestamp),
        )

    conn.execute("delete from clinic_locations where business_id=? and workspace_id=?", (business_id, workspace_id))
    for name, address, phone, timezone, working_hours in parse_block(form.get("clinic_locations", ""), 5):
        if not name or name.lower() == "name":
            continue
        conn.execute(
            """
            insert into clinic_locations (
                workspace_id, business_id, name, address, phone, timezone, working_hours,
                active, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                workspace_id,
                business_id,
                name,
                address,
                phone,
                timezone or profile["timezone"],
                working_hours,
                timestamp,
                timestamp,
            ),
        )

    conn.execute("delete from clinic_holidays where business_id=? and workspace_id=?", (business_id, workspace_id))
    for holiday_type, name, date_or_weekday, start_time, end_time, closed_all_day in parse_block(
        form.get("clinic_holidays", ""), 6
    ):
        if not name or name.lower() == "name":
            continue
        clean_type = holiday_type if holiday_type in {"date", "weekly"} else "date"
        conn.execute(
            """
            insert into clinic_holidays (
                workspace_id, business_id, holiday_type, name, date_value, weekday,
                start_time, end_time, closed_all_day, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                business_id,
                clean_type,
                name,
                date_or_weekday if clean_type == "date" else None,
                date_or_weekday if clean_type == "weekly" else None,
                start_time,
                end_time,
                parse_bool(closed_all_day, 1),
                timestamp,
                timestamp,
            ),
        )


def backfill_clinic_setup(conn: sqlite3.Connection) -> None:
    timestamp = now()
    for business in conn.execute(
        """
        select id, workspace_id, name, business_type, phone, location, working_hours,
               handoff_name, supported_languages, recording_disclosure
        from businesses
        where business_type in ('Clinic', 'Hospital', 'Dentist')
        """
    ).fetchall():
        workspace_id = int(business["workspace_id"] or active_workspace_id(conn))
        business_id = int(business["id"])
        existing = conn.execute(
            "select id from clinic_profiles where business_id = ? and workspace_id = ?",
            (business_id, workspace_id),
        ).fetchone()
        if not existing:
            defaults = default_clinic_profile()
            supported = "en,ur"
            if business["supported_languages"]:
                lowered = business["supported_languages"].lower()
                found = [code for code in ["en", "ur", "ar"] if code in lowered]
                supported = ",".join(found or ["en", "ur"])
            conn.execute(
                """
                insert into clinic_profiles (
                    workspace_id, business_id, timezone, supported_languages, default_language,
                    insurance_accepted, cancellation_window_hours, after_hours_policy, emergency_policy,
                    recording_disclosure_enabled, reminders_enabled, reminder_offset_hours, created_at, updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    workspace_id,
                    business_id,
                    defaults["timezone"],
                    supported,
                    "ur" if "ur" in supported.split(",") else supported.split(",")[0],
                    defaults["insurance_accepted"],
                    defaults["cancellation_window_hours"],
                    defaults["after_hours_policy"],
                    defaults["emergency_policy"],
                    1,
                    defaults["reminders_enabled"],
                    defaults["reminder_offset_hours"],
                    timestamp,
                    timestamp,
                ),
            )
        provider_count = conn.execute(
            "select count(*) from clinic_providers where business_id = ? and workspace_id = ?",
            (business_id, workspace_id),
        ).fetchone()[0]
        if not provider_count:
            conn.execute(
                """
                insert into clinic_providers (
                    workspace_id, business_id, name, role, specialty, languages, location_name,
                    working_hours, active, created_at, updated_at
                )
                values (?, ?, ?, 'Dentist', 'General dentistry', 'en,ur', ?, ?, 1, ?, ?)
                """,
                (
                    workspace_id,
                    business_id,
                    business["handoff_name"] or "Clinic Provider",
                    business["location"] or "Main Clinic",
                    business["working_hours"] or "10:00-19:00",
                    timestamp,
                    timestamp,
                ),
            )
        location_count = conn.execute(
            "select count(*) from clinic_locations where business_id = ? and workspace_id = ?",
            (business_id, workspace_id),
        ).fetchone()[0]
        if not location_count:
            conn.execute(
                """
                insert into clinic_locations (
                    workspace_id, business_id, name, address, phone, timezone, working_hours,
                    active, created_at, updated_at
                )
                values (?, ?, 'Main Clinic', ?, ?, 'Asia/Karachi', ?, 1, ?, ?)
                """,
                (
                    workspace_id,
                    business_id,
                    business["location"] or "",
                    business["phone"] or "",
                    business["working_hours"] or "10:00-19:00",
                    timestamp,
                    timestamp,
                ),
            )
        holiday_count = conn.execute(
            "select count(*) from clinic_holidays where business_id = ? and workspace_id = ?",
            (business_id, workspace_id),
        ).fetchone()[0]
        if not holiday_count:
            conn.execute(
                """
                insert into clinic_holidays (
                    workspace_id, business_id, holiday_type, name, weekday,
                    start_time, end_time, closed_all_day, created_at, updated_at
                )
                values (?, ?, 'weekly', 'Friday half-day pattern', 'friday', '13:00', '15:00', 0, ?, ?)
                """,
                (workspace_id, business_id, timestamp, timestamp),
            )
