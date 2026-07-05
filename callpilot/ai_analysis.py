from __future__ import annotations

import json
import os
import re
from typing import Any

from .analysis import analyze_call


DEFAULT_MODEL = "claude-opus-4-8"

# Structured output schema for call extraction. Strings use "" for unknown.
EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "customer_name": {"type": "string"},
        "customer_phone": {"type": "string"},
        "customer_email": {"type": "string"},
        "service_requested": {"type": "string"},
        "requested_date": {"type": "string", "description": "ISO date YYYY-MM-DD if stated, else empty"},
        "requested_time": {"type": "string", "description": "HH:MM 24h if stated, else empty"},
        "language": {"type": "string", "enum": ["en", "ur", "ar", "other"]},
        "intent": {"type": "string", "enum": ["ready_to_book", "information_request", "human_request", "complaint", "other"]},
        "booking_requested": {"type": "boolean"},
        "emergency_indicated": {"type": "boolean"},
        "advice_requested": {"type": "boolean"},
        "summary": {"type": "string", "description": "Two sentences max, grounded strictly in the transcript"},
    },
    "required": [
        "customer_name",
        "customer_phone",
        "customer_email",
        "service_requested",
        "requested_date",
        "requested_time",
        "language",
        "intent",
        "booking_requested",
        "emergency_indicated",
        "advice_requested",
        "summary",
    ],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "You extract structured intake data from clinic phone-call transcripts. "
    "Use only facts stated in the transcript; never invent contact details, dates, or medical content. "
    "Leave fields empty when the transcript does not state them. "
    "Transcripts may mix English, Roman Urdu, Urdu script, and Arabic."
)


def configured_model() -> str:
    return (os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL).strip()


def ai_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _extract_with_claude(transcript: str, business: dict[str, Any]) -> dict[str, Any]:
    """One structured-output extraction call. Raises on any API problem."""
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=configured_model(),
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": EXTRACTION_SCHEMA}},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Business: {business.get('name')} ({business.get('business_type')}).\n"
                    f"Transcript:\n{transcript}"
                ),
            }
        ],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Model refused the extraction request.")
    text = next(block.text for block in response.content if block.type == "text")
    return json.loads(text)


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def _grounded(value: str, transcript: str) -> str:
    """Only accept extracted contact facts literally present in the transcript."""
    clean = (value or "").strip()
    if not clean:
        return ""
    if clean.lower() in transcript.lower():
        return clean
    if _digits(clean) and _digits(clean) in _digits(transcript):
        return clean
    return ""


def merge_ai_extraction(base: dict[str, Any], extracted: dict[str, Any], transcript: str) -> dict[str, Any]:
    """Merge Claude's extraction into the rule-based analysis.

    Rules the merge must never break:
    - Contact facts are grounding-checked against the transcript (no hallucinated
      phones/emails/names).
    - Safety signals only ratchet up: Claude can add emergency/handoff flags but
      can never clear the deterministic ones.
    """
    merged = dict(base)
    fields = dict(merged.get("extracted_fields") or {})

    name = _grounded(extracted.get("customer_name", ""), transcript)
    phone = _grounded(extracted.get("customer_phone", ""), transcript)
    email = _grounded(extracted.get("customer_email", ""), transcript)
    if name:
        merged["customer_name"] = name
    if phone:
        merged["customer_phone"] = phone
    if email:
        merged["customer_email"] = email
    if extracted.get("service_requested"):
        merged["service_requested"] = extracted["service_requested"]
    if extracted.get("requested_date"):
        merged["timeline"] = extracted["requested_date"]
    if extracted.get("requested_time"):
        fields["requested_time"] = extracted["requested_time"]
    if extracted.get("summary"):
        merged["ai_summary"] = extracted["summary"]
    if extracted.get("intent") and extracted["intent"] != "other":
        merged["intent"] = extracted["intent"]
    if extracted.get("language") in {"en", "ur", "ar"}:
        fields["detected_language_code"] = extracted["language"]

    # Ratchet-up only: OR with the deterministic flags, never AND.
    merged["booking_requested"] = bool(merged.get("booking_requested") or extracted.get("booking_requested"))
    if extracted.get("emergency_indicated") and not (fields.get("medical_emergency") or {}).get("detected"):
        fields["medical_emergency"] = {
            "detected": True,
            "language": fields.get("detected_language_code", "en"),
            "match_type": "ai",
            "policy_version": "clinic-emergency-v1",
        }
        merged["urgency"] = "emergency"
    if extracted.get("emergency_indicated") or extracted.get("advice_requested"):
        merged["handoff_triggered"] = True

    merged["extracted_fields"] = fields
    return merged


def analyze_call_smart(
    transcript: str,
    business: dict[str, Any],
    services: list[dict[str, Any]],
    knowledge: list[dict[str, Any]],
) -> dict[str, Any]:
    """Rule-based analysis, upgraded by Claude when an API key is configured.

    Honest fallback: with no key, or on any API error, the deterministic
    analysis is returned unchanged and the provider is reported truthfully.
    """
    analysis = analyze_call(transcript, business, services, knowledge)
    if not ai_available():
        analysis["ai_provider"] = "rule_based"
        return analysis
    try:
        extracted = _extract_with_claude(transcript, business)
    except Exception as error:
        analysis["ai_provider"] = "rule_based"
        analysis["ai_error"] = str(error)[:200]
        return analysis
    merged = merge_ai_extraction(analysis, extracted, transcript)
    merged["ai_provider"] = configured_model()
    return merged
