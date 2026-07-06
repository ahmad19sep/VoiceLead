from __future__ import annotations

import sqlite3
from typing import Any

from .clinic import get_clinic_profile
from .repositories import get_business, get_services


LANGUAGE_LABELS = {"en": "English", "ur": "Urdu (respond in Roman Urdu pronunciation)", "ar": "Arabic"}
GREETING_HINTS = {
    "ur": "Aap Urdu mein bhi baat kar saktay hain.",
    "ar": "يمكنك التحدث بالعربية أيضا.",
}


def build_vapi_prompt(conn: sqlite3.Connection, business_id: int) -> dict[str, str] | None:
    """Generate the ready-to-paste Vapi assistant config for one clinic.

    Everything is driven by the operator's Agent Builder choices: the selected
    languages decide what the agent offers and speaks, and Urdu is always
    written as Roman Urdu.
    """
    business = get_business(conn, business_id)
    if not business:
        return None
    profile = get_clinic_profile(conn, business_id)
    services = get_services(conn, business_id)
    supported = [
        code.strip()
        for code in (profile.get("supported_languages") or "en").split(",")
        if code.strip() in LANGUAGE_LABELS
    ] or ["en"]
    default_language = (profile.get("default_language") or supported[0]).strip().lower()
    if default_language not in supported:
        default_language = supported[0]

    clinic_name = business.get("name") or "the clinic"
    agent_name = business.get("agent_name") or "the AI receptionist"
    hours = business.get("working_hours") or "shared by clinic staff"
    location = business.get("location") or ""
    service_names = ", ".join(s["name"] for s in services[:10]) or "clinic services"
    insurance = profile.get("insurance_accepted") or "staff will verify"

    language_line = ", ".join(LANGUAGE_LABELS[code] for code in supported)
    hint_lines = " ".join(GREETING_HINTS[code] for code in supported if code != "en" and code in GREETING_HINTS)
    disclosure = "This call may be recorded for quality. " if profile.get("recording_disclosure_enabled") else ""
    first_message = f"Thank you for calling {clinic_name}. {disclosure}How can I help you today?"
    if hint_lines:
        first_message += f" {hint_lines}"

    system_prompt = f"""You are {agent_name} for {clinic_name}{f' in {location}' if location else ''}.

LANGUAGE: Detect the caller's language. Speak only: {language_line}.
If the caller uses a language you do not support, politely continue in {LANGUAGE_LABELS[default_language].split(' (')[0]} and offer a staff callback.
Default language: {LANGUAGE_LABELS[default_language].split(' (')[0]}. Keep every reply to 1-2 short sentences; this is a phone call.

YOUR JOB, in order:
1. Understand what the caller needs (appointment, question, cancellation).
2. Collect: full name, phone number, service needed, preferred date and time.
3. Repeat the details back once to confirm ("Let me confirm: ... Is that correct?").
4. If you did not hear something clearly, ask the caller to repeat it - never guess a name, number, or date.
5. Tell them the clinic will confirm their appointment shortly.

CLINIC FACTS (answer only from these):
- Hours: {hours}.
- Services: {service_names}.
- Payment and insurance: {insurance}.

STRICT RULES:
- NEVER give medical advice, diagnosis, or medication guidance. Say: "Our doctor will advise you about that during your visit."
- If the caller describes a medical emergency (severe chest pain, heavy bleeding, breathing trouble, unconsciousness): say "If this is a medical emergency, please hang up and call your local emergency number now. I am alerting clinic staff immediately." Then ask for their callback number.
- If asked something not in the clinic facts, take a message for staff.
- Never invent appointment confirmations - staff confirm all bookings."""

    return {"first_message": first_message, "system_prompt": system_prompt}
