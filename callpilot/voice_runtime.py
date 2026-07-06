from __future__ import annotations

import os
import re
import sqlite3
from typing import Any

from .clinic import get_clinic_profile
from .providers import provider_by_key
from .repositories import get_business


VOICE_RUNTIME_VERSION = "clinic-voice-v1"
RUNTIME_LANGUAGES = ("en", "ur", "ar")

# Urdu shares the Arabic script block; these letters exist in Urdu but not Arabic.
_URDU_ONLY_CHARS = "ےٹڈڑںھگچپژ"
_ARABIC_RANGE = re.compile(r"[؀-ۿ]")
_ROMAN_URDU_TERMS = (
    "salam",
    "assalam",
    "mujhe",
    "chahiye",
    "kitna",
    "shukriya",
    "appointment chahiye",
    "booking karni",
    "kal subah",
    "doctor sahab",
    # Distinctive Roman Urdu markers common in emergency and family speech.
    "saans nahi",
    "nahi aa rahi",
    "jaldi",
    "madad",
    "ammi",
    "abbu",
)
_ARABIC_TERMS = ("مرحبا", "شكرا", "حجز", "موعد", "عيادة", "دكتور")


# Approved, safe clinic prompt packs. Every language must carry a recording
# disclosure and an emergency script that never gives medical advice.
PROMPT_PACKS: dict[str, dict[str, str]] = {
    "en": {
        "greeting": "Thank you for calling {clinic_name}. This is {agent_name}, the clinic's AI receptionist.",
        "recording_disclosure": "This call may be recorded for quality and appointment accuracy.",
        "booking_prompt": "Which service and doctor would you like, and what date and time suit you?",
        "contact_prompt": "May I have your name and the best phone number for confirmation?",
        "emergency_script": (
            "If this is a medical emergency, please hang up and call your local emergency number now. "
            "I am alerting clinic staff immediately. I cannot give medical advice."
        ),
        "handoff_script": "I will ask our clinic staff to call you back as soon as possible.",
        "confirm_details": "Let me confirm: {details}. Is that correct?",
        "not_understood": "Sorry, I did not catch that clearly. Could you please repeat it?",
        "fallback": "I can take your name and number and have the clinic team call you back.",
        "closing": "Thank you for calling {clinic_name}. Your request has been noted.",
    },
    "ur": {
        "greeting": "{clinic_name} mein call karne ka shukriya. Main {agent_name} hoon, clinic ki AI receptionist.",
        "recording_disclosure": "Quality aur appointment ki durustgi ke liye yeh call record ho sakti hai.",
        "booking_prompt": "Aap kaun si service aur kaun se doctor ke liye, kis din aur waqt appointment chahte hain?",
        "contact_prompt": "Barah-e-karam apna naam aur raabtay ka behtareen number batayen.",
        "emergency_script": (
            "Agar yeh medical emergency hai to barah-e-karam foran call band kar ke apne local emergency number par call karen. "
            "Main clinic staff ko foran ittila kar rahi hoon. Main tibbi mashwara nahi de sakti."
        ),
        "handoff_script": "Main clinic staff se kahoongi ke aap ko jald az jald call back karen.",
        "confirm_details": "Main tasdeeq kar loon: {details}. Kya yeh durust hai?",
        "not_understood": "Maazrat, main theek se sun nahi saki. Barah-e-karam dobara bata dijiye.",
        "fallback": "Main aap ka naam aur number le kar clinic team se call back karwa sakti hoon.",
        "closing": "{clinic_name} mein call karne ka shukriya. Aap ki request note kar li gayi hai.",
    },
    "ar": {
        "greeting": "شكرا لاتصالك بعيادة {clinic_name}. أنا {agent_name}، موظفة الاستقبال الذكية للعيادة.",
        "recording_disclosure": "قد يتم تسجيل هذه المكالمة لضمان الجودة ودقة المواعيد.",
        "booking_prompt": "ما الخدمة والطبيب الذي ترغب به، وما التاريخ والوقت المناسبان لك؟",
        "contact_prompt": "من فضلك، ما اسمك وأفضل رقم هاتف للتأكيد؟",
        "emergency_script": (
            "إذا كانت هذه حالة طارئة، يرجى إنهاء المكالمة والاتصال برقم الطوارئ المحلي فورا. "
            "سأقوم بتنبيه طاقم العيادة حالا. لا يمكنني تقديم نصيحة طبية."
        ),
        "handoff_script": "سأطلب من طاقم العيادة معاودة الاتصال بك في أقرب وقت ممكن.",
        "confirm_details": "دعني أتأكد: {details}. هل هذا صحيح؟",
        "not_understood": "عذرا، لم أسمع ذلك بوضوح. هل يمكنك التكرار من فضلك؟",
        "fallback": "يمكنني تسجيل اسمك ورقمك ليقوم فريق العيادة بمعاودة الاتصال بك.",
        "closing": "شكرا لاتصالك بعيادة {clinic_name}. تم تسجيل طلبك.",
    },
}


def detect_language_code(text: str) -> str:
    """Detect the caller language as one of the clinic runtime codes."""
    if not text:
        return "en"
    urdu_script = any(char in text for char in _URDU_ONLY_CHARS)
    if urdu_script:
        return "ur"
    if any(term in text for term in _ARABIC_TERMS):
        return "ar"
    if _ARABIC_RANGE.search(text):
        # Arabic-block text without Urdu-only letters: treat as Arabic.
        return "ar"
    lower = text.lower()
    if any(term in lower for term in _ROMAN_URDU_TERMS):
        return "ur"
    return "en"


def resolve_language(
    detected: str | None, supported: list[str], default_language: str
) -> tuple[str, bool]:
    """Return (language, fallback_used) honoring the clinic language policy."""
    clean_default = default_language if default_language in RUNTIME_LANGUAGES else "en"
    clean_supported = [code for code in supported if code in RUNTIME_LANGUAGES] or [clean_default]
    code = (detected or "").strip().lower()
    if code in clean_supported:
        return code, False
    if clean_default in clean_supported:
        return clean_default, True
    return clean_supported[0], True


def prompt_pack(language: str, clinic_name: str = "", agent_name: str = "") -> dict[str, str]:
    pack = PROMPT_PACKS.get(language if language in PROMPT_PACKS else "en", PROMPT_PACKS["en"])
    return {
        key: value.format(
            clinic_name=clinic_name or "the clinic",
            agent_name=agent_name or "the assistant",
            details="{details}",  # runtime fills this per call
        )
        for key, value in pack.items()
    }


def configured_runtime_key() -> str:
    value = (os.environ.get("VOICE_RUNTIME") or "auto").strip().lower()
    if value in {"vapi", "retell"}:
        return value
    # auto: prefer whichever runtime has credentials, defaulting to vapi.
    for key in ("vapi", "retell"):
        if provider_by_key(key).connected():
            return key
    return "vapi"


def runtime_status() -> dict[str, Any]:
    """Honest voice-runtime readiness. Never claims a live agent without a provider."""
    key = configured_runtime_key()
    provider = provider_by_key(key)
    health = provider.health()
    blockers: list[str] = []
    if not health["connected"]:
        blockers.append(f"{health['provider']} credentials are not configured.")
    if not health["production_ready"]:
        blockers.append(f"{health['provider']} runtime adapter is not implemented; no live agent can answer a real number yet.")
    return {
        "runtime": key,
        "provider": health["provider"],
        "version": VOICE_RUNTIME_VERSION,
        "connected": health["connected"],
        "live_ready": health["production_ready"],
        "languages": list(RUNTIME_LANGUAGES),
        "blockers": blockers,
    }


def build_runtime_session(
    conn: sqlite3.Connection,
    business_id: int,
    caller_text: str | None = None,
    requested_language: str | None = None,
) -> dict[str, Any]:
    """Assemble the trilingual session config a live voice runtime would receive.

    The config is real and versioned; the ``runtime`` block stays honest about
    whether any provider can actually answer a phone number.
    """
    business = get_business(conn, business_id)
    if not business:
        raise ValueError(f"Business {business_id} not found.")
    profile = get_clinic_profile(conn, business_id)
    supported = [code.strip() for code in (profile.get("supported_languages") or "en").split(",") if code.strip()]
    default_language = (profile.get("default_language") or "en").strip().lower()

    detected = requested_language or (detect_language_code(caller_text or "") if caller_text else None)
    language, fallback_used = resolve_language(detected, supported, default_language)
    pack = prompt_pack(language, business.get("name") or "", business.get("agent_name") or "")
    if not profile.get("recording_disclosure_enabled"):
        pack = {key: value for key, value in pack.items() if key != "recording_disclosure"}

    return {
        "version": VOICE_RUNTIME_VERSION,
        "business_id": business_id,
        "language": language,
        "detected_language": detected,
        "language_fallback_used": fallback_used,
        "supported_languages": supported,
        "default_language": default_language,
        "knowledge_language": language,
        "prompts": pack,
        "policies": {
            "emergency_policy": profile.get("emergency_policy") or "",
            "after_hours_policy": profile.get("after_hours_policy") or "",
            "cancellation_window_hours": profile.get("cancellation_window_hours"),
            "recording_disclosure_enabled": bool(profile.get("recording_disclosure_enabled")),
        },
        "runtime": runtime_status(),
    }
