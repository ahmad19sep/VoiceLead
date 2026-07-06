from __future__ import annotations

import re
import sqlite3
from difflib import SequenceMatcher
from typing import Any

from .utils import now


EMERGENCY_POLICY_VERSION = "clinic-emergency-v1"

# Approved trilingual medical-emergency phrase lists. Roman Urdu and Urdu
# script are both listed because callers use either. Phrases are matched
# with normalization plus fuzzy matching for latin-script typos.
EMERGENCY_PHRASES: dict[str, tuple[str, ...]] = {
    "en": (
        "chest pain",
        "heart attack",
        "stroke",
        "can't breathe",
        "cannot breathe",
        "difficulty breathing",
        "not breathing",
        "unconscious",
        "passed out",
        "heavy bleeding",
        "bleeding a lot",
        "severe bleeding",
        "seizure",
        "choking",
        "overdose",
        "severe allergic reaction",
        "anaphylaxis",
        "suicidal",
        "not waking up",
        "won't wake up",
        "collapsed",
    ),
    "ur": (
        # Roman Urdu
        "saans nahi",
        "sans nahi",
        "saans band",
        "sans band",
        "saans lene mein",
        "seenay mein dard",
        "seene mein dard",
        "seenay mein shadeed",
        "dil ka daura",
        "dil ka dora",
        "behosh",
        "hosh nahi",
        "hosh mein nahi",
        "khoon beh raha",
        "khoon nahi ruk",
        "khoon bohat",
        "daura par gaya",
        "dora par gaya",
        "zeher",
        # Urdu script
        "سانس نہیں",
        "سانس بند",
        "سینے میں درد",
        "دل کا دورہ",
        "بے ہوش",
        "ہوش نہیں",
        "خون بہہ رہا",
        "دورہ پڑ",
    ),
    "ar": (
        "ألم في الصدر",
        "ألم شديد في الصدر",
        "نوبة قلبية",
        "جلطة",
        "لا أستطيع التنفس",
        "لا يتنفس",
        "صعوبة في التنفس",
        "فاقد الوعي",
        "فقد الوعي",
        "أغمي عليه",
        "أغمي عليها",
        "نزيف حاد",
        "نزيف شديد",
        "النزيف لا يتوقف",
        "تشنج",
        "اختناق",
        "جرعة زائدة",
        "حالة طارئة",
    ),
}

_FUZZY_THRESHOLD = 0.84


def _normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("'", "'")
    text = re.sub(r"[.,!?;:،؟]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fuzzy_contains(phrase: str, text: str) -> bool:
    """Sliding word-window fuzzy match for latin-script phrases (typo tolerant)."""
    words = text.split()
    size = len(phrase.split())
    if not words or not size:
        return False
    for start in range(0, max(1, len(words) - size + 1)):
        window = " ".join(words[start : start + size])
        if SequenceMatcher(None, phrase, window).ratio() >= _FUZZY_THRESHOLD:
            return True
    return False


def detect_emergency(text: str) -> dict[str, Any]:
    """Detect a medical emergency in EN/UR/AR caller text.

    Returns a detection record that intentionally excludes the surrounding
    transcript so downstream alerts can stay PHI-free.
    """
    if not text:
        return {"detected": False}
    normalized = _normalize(text)
    for language, phrases in EMERGENCY_PHRASES.items():
        for phrase in phrases:
            clean_phrase = _normalize(phrase)
            if clean_phrase in normalized:
                return {
                    "detected": True,
                    "language": language,
                    "matched_phrase": phrase,
                    "match_type": "exact",
                    "policy_version": EMERGENCY_POLICY_VERSION,
                }
            if phrase.isascii() and _fuzzy_contains(clean_phrase, normalized):
                return {
                    "detected": True,
                    "language": language,
                    "matched_phrase": phrase,
                    "match_type": "fuzzy",
                    "policy_version": EMERGENCY_POLICY_VERSION,
                }
    return {"detected": False}


def mask_phone(phone: str | None) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) < 4:
        return "unavailable"
    return f"***{digits[-4:]}"


def create_emergency_alert(
    conn: sqlite3.Connection,
    business_id: int,
    lead_id: int | None,
    detection: dict[str, Any],
    caller_phone: str | None = None,
) -> None:
    """Escalate a detected emergency with a PHI-free staff alert.

    The alert must never contain the transcript, symptoms, the matched
    phrase, or the caller's name — only what staff need to act now.
    """
    business = conn.execute(
        "select id, workspace_id, name, handoff_email, handoff_phone from businesses where id = ?",
        (business_id,),
    ).fetchone()
    if not business:
        return
    language = detection.get("language") or "en"
    subject = f"EMERGENCY escalation: {business['name']}"
    message = "\n".join(
        [
            "Emergency Escalation Alert",
            f"Business: {business['name']}",
            f"Caller language: {language}",
            f"Callback number (masked): {mask_phone(caller_phone)}",
            f"Time: {now()}",
            "",
            "An emergency indicator was detected on a live call.",
            "The approved emergency script was used; no medical advice was given.",
            "Action: call the patient back immediately using the full number in the lead record.",
            "Medical details are withheld from this alert by policy.",
        ]
    )
    conn.execute(
        """
        insert into notifications (
            workspace_id, business_id, lead_id, notification_type, channel, recipient, subject, message, status, created_at
        )
        values (?, ?, ?, 'emergency_alert', 'dashboard', ?, ?, ?, 'sent', ?)
        """,
        (
            business["workspace_id"],
            business_id,
            lead_id,
            business["handoff_email"] or business["handoff_phone"],
            subject,
            message,
            now(),
        ),
    )
    from .compliance import audit_event
    from .workflows import create_event

    create_event(
        conn,
        business_id,
        lead_id,
        "emergency_escalated",
        "Emergency detected; staff alerted with PHI-free notification.",
        {
            "language": language,
            "match_type": detection.get("match_type"),
            "policy_version": detection.get("policy_version") or EMERGENCY_POLICY_VERSION,
        },
    )
    audit_event(
        conn,
        business["workspace_id"],
        "system",
        "emergency_escalated",
        "lead" if lead_id else "business",
        lead_id or business_id,
        {
            "language": language,
            "match_type": detection.get("match_type"),
            "policy_version": detection.get("policy_version") or EMERGENCY_POLICY_VERSION,
        },
    )
