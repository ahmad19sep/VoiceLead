from __future__ import annotations

import html
import json
import os
import sqlite3
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

from .utils import now


def app_url() -> str:
    return os.environ.get("APP_URL", "http://127.0.0.1:8000").rstrip("/")

def xml_escape(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)

def twiml_response(inner: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response>{inner}</Response>'

def twilio_gather_twiml(business_id: int, prompt: str) -> str:
    action = f"{app_url()}/api/twilio/gather?business_id={business_id}"
    return twiml_response(
        f'<Gather input="speech" action="{xml_escape(action)}" method="POST" timeout="7" speechTimeout="auto" language="en-US">'
        f"<Say voice=\"alice\">{xml_escape(prompt)}</Say>"
        "</Gather>"
        "<Say voice=\"alice\">I did not hear anything. Please call again, or our team can follow up later.</Say>"
        "<Hangup/>"
    )

def twilio_finish_twiml(message: str) -> str:
    return twiml_response(f"<Say voice=\"alice\">{xml_escape(message)}</Say><Hangup/>")

def get_or_create_call_session(
    conn: sqlite3.Connection,
    business_id: int,
    call_sid: str,
    caller_phone: str | None,
) -> dict[str, Any]:
    row = conn.execute("select * from call_sessions where call_sid = ?", (call_sid,)).fetchone()
    if row:
        return dict(row)
    business = conn.execute("select workspace_id from businesses where id = ?", (business_id,)).fetchone()
    workspace_id = business["workspace_id"] if business else None
    cur = conn.execute(
        """
        insert into call_sessions (workspace_id, business_id, call_sid, caller_phone, transcript, turn_count, status, created_at, updated_at)
        values (?, ?, ?, ?, '', 0, 'active', ?, ?)
        """,
        (workspace_id, business_id, call_sid, caller_phone, now(), now()),
    )
    return dict(conn.execute("select * from call_sessions where id = ?", (cur.lastrowid,)).fetchone())

def next_twilio_prompt(analysis: dict[str, Any], business: dict[str, Any]) -> str:
    if not analysis.get("customer_name"):
        return "Thanks. What is your name?"
    if not analysis.get("customer_phone") and not analysis.get("customer_email"):
        return "What is the best phone number or email for follow up?"
    if business["business_type"] in {"Hotel", "Clinic", "Restaurant", "Law Firm"} and not analysis.get("timeline"):
        return "What date or time would you prefer?"
    if business["business_type"] == "Home Services" and not analysis.get("location"):
        return "What area or location are you in?"
    if business["business_type"] == "Software Agency" and not analysis.get("budget"):
        return "Do you have a budget or timeline in mind?"
    return "Anything else our team should know?"

def should_finish_twilio_call(analysis: dict[str, Any], turn_count: int, speech: str) -> bool:
    lower = speech.lower()
    if any(word in lower for word in ["that's all", "that is all", "goodbye", "bye", "done"]):
        return True
    has_contact = bool(analysis.get("customer_phone") or analysis.get("customer_email"))
    has_need = bool(analysis.get("service_requested") or analysis.get("request_type"))
    if has_contact and has_need and (analysis.get("booking_requested") or analysis.get("timeline") or analysis.get("urgency")):
        return True
    return turn_count >= 3

def create_twilio_outbound_call(to_number: str, business_id: int) -> tuple[bool, str]:
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_PHONE_NUMBER")
    if not sid or not token or not from_number:
        return False, "Missing TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, or TWILIO_PHONE_NUMBER in .env."
    if app_url().startswith("http://127.0.0.1") or app_url().startswith("http://localhost"):
        return False, "APP_URL must be a public HTTPS URL, for example an ngrok URL, before Twilio can call your webhook."

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
    data = urlencode(
        {
            "To": to_number,
            "From": from_number,
            "Url": f"{app_url()}/api/twilio/voice?business_id={business_id}",
            "Method": "POST",
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    auth = f"{sid}:{token}".encode("utf-8")
    request.add_header("Authorization", "Basic " + __import__("base64").b64encode(auth).decode("ascii"))
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return True, f"Outbound call started. Twilio Call SID: {payload.get('sid', 'unknown')}"
    except urllib.error.HTTPError as error:
        return False, error.read().decode("utf-8", errors="replace")
    except Exception as error:
        return False, str(error)
