from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any

TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"
SCOPE = "https://www.googleapis.com/auth/calendar.events"
DEFAULT_TIMEZONE = "Asia/Karachi"
DEFAULT_DURATION_MINUTES = 30

_token_cache: dict[str, Any] = {}

try:  # RS256 signing needs the cryptography package.
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without the dependency
    CRYPTO_AVAILABLE = False


def load_service_account() -> dict[str, Any] | None:
    raw = os.environ.get("GOOGLE_CALENDAR_CREDENTIALS") or ""
    if not raw.strip():
        return None
    try:
        info = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not info.get("client_email") or not info.get("private_key"):
        return None
    return info


def calendar_id() -> str:
    return (os.environ.get("GOOGLE_CALENDAR_ID") or "").strip()


def client_ready() -> tuple[bool, str]:
    if not CRYPTO_AVAILABLE:
        return False, "cryptography package is not installed."
    if not calendar_id():
        return False, "GOOGLE_CALENDAR_ID is not set."
    if not load_service_account():
        return False, "GOOGLE_CALENDAR_CREDENTIALS is missing or not valid service-account JSON."
    return True, "Google Calendar client is ready."


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def build_signed_jwt(info: dict[str, Any], now: int | None = None) -> str:
    issued = int(now if now is not None else time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": info["client_email"],
        "scope": SCOPE,
        "aud": TOKEN_URL,
        "iat": issued,
        "exp": issued + 3600,
    }
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        + "."
        + _b64url(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    )
    private_key = serialization.load_pem_private_key(info["private_key"].encode("utf-8"), password=None)
    signature = private_key.sign(signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64url(signature)}"


def get_access_token(info: dict[str, Any]) -> str:
    cached = _token_cache.get(info["client_email"])
    if cached and cached["expires_at"] > time.time() + 60:
        return cached["token"]
    body = urllib.parse.urlencode(
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": build_signed_jwt(info),
        }
    ).encode("utf-8")
    request = urllib.request.Request(TOKEN_URL, data=body, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    token = payload["access_token"]
    _token_cache[info["client_email"]] = {
        "token": token,
        "expires_at": time.time() + int(payload.get("expires_in", 3600)),
    }
    return token


def api_request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    info = load_service_account()
    if not info:
        raise RuntimeError("Google service account credentials are not configured.")
    token = get_access_token(info)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(f"{CALENDAR_API}{path}", data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Google Calendar API {error.code}: {detail[:300]}") from error


def parse_appointment_datetime(booking: dict[str, Any]) -> datetime | None:
    raw_date = (booking.get("requested_date") or "").strip()
    raw_time = (booking.get("requested_time") or "").strip()
    for date_fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            day = datetime.strptime(raw_date, date_fmt)
        except ValueError:
            continue
        for time_fmt in ("%H:%M", "%I:%M %p", "%I %p"):
            try:
                clock = datetime.strptime(raw_time, time_fmt)
                return day.replace(hour=clock.hour, minute=clock.minute)
            except ValueError:
                continue
        return day.replace(hour=10, minute=0)
    return None


def event_body(booking: dict[str, Any]) -> dict[str, Any] | None:
    start = parse_appointment_datetime(booking)
    if start is None:
        return None
    end = start + timedelta(minutes=DEFAULT_DURATION_MINUTES)
    summary = f"Appointment: {booking.get('customer_name') or 'Patient'}"
    service = booking.get("service_requested") or booking.get("booking_type")
    if service:
        summary += f" - {service}"
    description_lines = ["Created by CallPilot AI."]
    if booking.get("customer_phone"):
        description_lines.append(f"Phone: {booking['customer_phone']}")
    if booking.get("notes"):
        description_lines.append(f"Notes: {booking['notes']}")
    return {
        "summary": summary,
        "description": "\n".join(description_lines),
        "start": {"dateTime": start.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": DEFAULT_TIMEZONE},
        "end": {"dateTime": end.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": DEFAULT_TIMEZONE},
    }


def create_event(booking: dict[str, Any]) -> tuple[str | None, str]:
    body = event_body(booking)
    if body is None:
        return None, "Booking has no parseable appointment date; confirm a date before calendar sync."
    result = api_request("POST", f"/calendars/{urllib.parse.quote(calendar_id())}/events", body)
    event_id = result.get("id")
    return event_id, f"Google Calendar event created ({event_id})."


def cancel_event(event_id: str | None) -> tuple[bool, str]:
    if not event_id:
        return True, "No external calendar event existed; nothing to cancel."
    api_request("DELETE", f"/calendars/{urllib.parse.quote(calendar_id())}/events/{urllib.parse.quote(event_id)}")
    return True, f"Google Calendar event {event_id} cancelled."


def reschedule_event(booking: dict[str, Any], event_id: str | None) -> tuple[str | None, str]:
    if not event_id:
        return create_event(booking)
    body = event_body(booking)
    if body is None:
        return event_id, "Booking has no parseable new date; existing calendar event left unchanged."
    api_request(
        "PATCH",
        f"/calendars/{urllib.parse.quote(calendar_id())}/events/{urllib.parse.quote(event_id)}",
        body,
    )
    return event_id, f"Google Calendar event {event_id} rescheduled."
