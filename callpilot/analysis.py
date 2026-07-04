from __future__ import annotations

import re
from typing import Any

from .config import SCORE_RULES
from .utils import lead_temperature


def clean(value: str) -> str:
    return re.sub(r"[.,!?;:]+$", "", value.strip())

def first_match(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return clean(match.group(1))
    return None

def extract_name(text: str) -> str | None:
    greetings = {"hi", "hello", "hey", "salam", "assalam", "namaste", "thanks", "thank you"}
    direct = first_match(
        [
            r"\bmy name is\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)",
            r"\bthis is\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)",
            r"\bi am\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)",
            r"\bi'm\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)",
        ],
        text,
    )
    if direct:
        return normalize_name(direct)
    for line in text.splitlines():
        if "caller:" not in line.lower():
            continue
        value = line.split(":", 1)[1]
        if "," in value:
            first = clean(value.split(",", 1)[0])
            if re.fullmatch(r"[A-Za-z ]{2,40}", first) and first.lower() not in greetings:
                return normalize_name(first)
    return None

def normalize_name(value: str) -> str:
    value = re.split(r"\s+(?:and|my|phone|number|email)\b", value, flags=re.IGNORECASE)[0]
    value = re.sub(r"\s+", " ", value).strip()
    return value.title()

def extract_phone(text: str) -> str | None:
    match = re.search(r"\b(?:\+92[-\s]?)?0?3\d{2}[-\s]?\d{7}\b", text)
    if match:
        return re.sub(r"\s+", "", match.group(0))

    word_phone = spoken_digits_to_phone(text)
    return word_phone

def spoken_digits_to_phone(text: str) -> str | None:
    number_words = {
        "zero": "0",
        "oh": "0",
        "o": "0",
        "one": "1",
        "two": "2",
        "three": "3",
        "four": "4",
        "for": "4",
        "five": "5",
        "six": "6",
        "seven": "7",
        "eight": "8",
        "ate": "8",
        "nine": "9",
    }
    tokens = re.findall(r"[a-zA-Z]+|\d+", text.lower())
    digits = ""
    best = ""
    for token in tokens:
        if token.isdigit():
            digits += token
        elif token in number_words:
            digits += number_words[token]
        else:
            if len(digits) > len(best):
                best = digits
            digits = ""
    if len(digits) > len(best):
        best = digits
    if len(best) >= 10:
        if best.startswith("92") and len(best) >= 12:
            return "+" + best[:12]
        if best.startswith("3") and len(best) >= 10:
            return "0" + best[:10]
        return best[:11] if best.startswith("0") else best[:10]
    return None

def extract_email(text: str) -> str | None:
    match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, flags=re.IGNORECASE)
    return match.group(0) if match else None

def extract_budget(text: str) -> str | None:
    match = re.search(r"(?:budget is|budget|around|under)\s+(?:rs\.?\s*|pkr\s*|\$)?([0-9,]+)", text, re.I)
    if match:
        raw = match.group(0)
        return clean(raw)
    return None

def extract_people(text: str) -> str | None:
    match = re.search(r"\b(?:for|table for)\s+(\d+)\s+(?:people|persons|guests|patients)?", text, re.I)
    if match:
        return match.group(1)
    return None

def extract_time(text: str) -> str | None:
    match = re.search(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM))\b", text)
    return match.group(1) if match else None

def extract_timeline(text: str) -> str | None:
    patterns = [
        r"\b(this Friday)\b",
        r"\b(tomorrow)\b",
        r"\b(today)\b",
        r"\b(tonight)\b",
        r"\b(this week)\b",
        r"\b(next week)\b",
        r"\b(next month)\b",
        r"\b(as soon as possible|asap|immediately|now)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None

def detect_language(text: str) -> str:
    lower = text.lower()
    roman_urdu_terms = [
        "salam",
        "assalam",
        "mujhe",
        "chahiye",
        "kal",
        "aaj",
        "kitna",
        "booking karni",
        "appointment chahiye",
        "shukriya",
    ]
    hindi_terms = ["namaste", "mujhe", "chahiye", "kal", "aaj", "dhanyavaad"]
    arabic_terms = ["مرحبا", "شكرا", "حجز", "موعد"]
    if any(term in text for term in arabic_terms):
        return "Arabic"
    if any(term in lower for term in roman_urdu_terms):
        return "Roman Urdu/Hindi"
    if any(term in lower for term in hindi_terms):
        return "Hindi"
    return "English"

def extract_location(text: str) -> str | None:
    return first_match(
        [
            r"\bin\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})",
            r"\blocated in\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,3})",
        ],
        text,
    )

def detect_service(text: str, services: list[dict[str, Any]]) -> tuple[str | None, bool]:
    lower = text.lower()
    for service in services:
        name = service["name"]
        words = [part for part in re.split(r"\W+", name.lower()) if len(part) > 2]
        if name.lower() in lower or any(word in lower for word in words):
            return name, True
    keyword_map = [
        ("room booking", ["room", "suite", "hotel", "nights", "stay"]),
        ("Dental appointment", ["dental", "checkup", "clinic", "patient"]),
        ("AC repair", ["ac", "cooling", "repair", "technician"]),
        ("Table reservation", ["reserve", "table", "restaurant"]),
        ("AI voice agent", ["ai voice", "crm", "software", "app", "automation"]),
        ("Legal consultation", ["lawyer", "legal", "contract", "case", "consultation"]),
    ]
    for service, keywords in keyword_map:
        if any(keyword in lower for keyword in keywords):
            return service, False
    return None, False

def request_type_for_business(business_type: str, text: str) -> str:
    lower = text.lower()
    if business_type == "Hotel":
        return "Room booking" if any(word in lower for word in ["book", "room", "suite", "stay"]) else "Hotel inquiry"
    if business_type in {"Clinic", "Hospital", "Dentist"}:
        return "Dental appointment" if any(word in lower for word in ["appointment", "checkup", "book"]) else "Clinic inquiry"
    if business_type == "Home Services":
        return "Technician visit" if any(word in lower for word in ["repair", "technician", "stopped", "leak"]) else "Service inquiry"
    if business_type == "Restaurant":
        return "Table reservation" if any(word in lower for word in ["reserve", "reservation", "table"]) else "Restaurant inquiry"
    if business_type in {"Software Agency", "Lead Generation", "Sales"}:
        return "Project inquiry"
    if business_type in {"Law Firm", "Legal", "Insurance", "Finance"}:
        return "Legal consultation"
    if business_type in {"Call Center", "Customer Support"}:
        return "Support request"
    if business_type in {"Real Estate", "Property Management"}:
        return "Property inquiry"
    if business_type in {"Ecommerce", "Retail", "Automotive", "Logistics"}:
        return "Commerce inquiry"
    if business_type in {"Education", "Recruiting", "Travel", "Government"}:
        return "Administrative inquiry"
    return "Business inquiry"

def keyword_search(knowledge: list[dict[str, Any]], text: str) -> list[dict[str, Any]]:
    lower = text.lower()
    scored = []
    for item in knowledge:
        haystack = f"{item['question']} {item['answer']} {item.get('tags') or ''}".lower()
        score = sum(1 for word in set(re.findall(r"[a-zA-Z]{4,}", lower)) if word in haystack)
        if score:
            scored.append((score, item))
    return [item for _, item in sorted(scored, key=lambda pair: pair[0], reverse=True)[:3]]

def analyze_call(
    transcript: str,
    business: dict[str, Any],
    services: list[dict[str, Any]],
    knowledge: list[dict[str, Any]],
) -> dict[str, Any]:
    lower = transcript.lower()
    detected_language = detect_language(transcript)
    name = extract_name(transcript)
    phone = extract_phone(transcript)
    email = extract_email(transcript)
    budget = extract_budget(transcript)
    timeline = extract_timeline(transcript)
    location = extract_location(transcript)
    service, service_match = detect_service(transcript, services)
    request_type = request_type_for_business(business["business_type"], transcript)
    booking_requested = bool(
        re.search(r"\bbook|reserve|appointment|schedule|confirm|visit|table|room|consultation|call back\b", lower)
    )
    human_request = bool(
        re.search(r"\bhuman|manager|doctor|lawyer|agent|sales person|receptionist|technician|staff\b", lower)
    )
    emergency = bool(re.search(r"\burgent|emergency|today|now|immediately|asap|as soon as possible\b", lower))
    complaint = bool(re.search(r"\bangry|frustrated|complaint|bad service|upset\b", lower))
    high_value = bool(budget and re.search(r"\$|2000|5000|[5-9][0-9]{3,}", budget))
    urgency = "emergency" if "emergency" in lower else ("urgent" if emergency else None)
    intent = "ready_to_book" if booking_requested else ("human_request" if human_request else "information_request")
    relevant_knowledge = keyword_search(knowledge, transcript)

    breakdown = {key: 0 for key in SCORE_RULES}
    breakdown["clear_need"] = SCORE_RULES["clear_need"] if service or request_type else 0
    breakdown["contact_detail"] = SCORE_RULES["contact_detail"] if phone or email else 0
    breakdown["name_provided"] = SCORE_RULES["name_provided"] if name else 0
    breakdown["timeline_date"] = SCORE_RULES["timeline_date"] if timeline else 0
    breakdown["ready_to_book"] = SCORE_RULES["ready_to_book"] if booking_requested or "call back" in lower else 0
    breakdown["matches_service"] = SCORE_RULES["matches_service"] if service_match else 0
    breakdown["urgency_high_value"] = SCORE_RULES["urgency_high_value"] if emergency or high_value else 0
    score = max(0, min(100, sum(breakdown.values())))
    temp = lead_temperature(score)

    safety_notes = []
    regulated = business["business_type"] in {"Clinic", "Hospital", "Dentist", "Law Firm", "Legal", "Insurance", "Finance"}
    healthcare = business["business_type"] in {"Clinic", "Hospital", "Dentist"}
    advice_request = bool(
        re.search(
            r"\b(should i|what medicine|diagnose|prescribe|legal advice|tax advice|financial advice|coverage advice|lawsuit)\b",
            lower,
        )
    )
    unsupported_language = bool(
        business.get("supported_languages")
        and detected_language.lower() not in business.get("supported_languages", "").lower()
    )

    if healthcare:
        safety_notes.append("No medical diagnosis or medicine recommendation was given.")
    if business["business_type"] in {"Law Firm", "Legal", "Insurance", "Finance"}:
        safety_notes.append("No licensed advice was given; the call is intake only.")
    if business["business_type"] == "Hotel":
        safety_notes.append("Availability is not confirmed until staff verifies the booking request.")
    if business.get("compliance_profile"):
        safety_notes.append(f"Compliance profile applied: {business['compliance_profile']}.")
    if business.get("blocked_outcomes"):
        first_block = business["blocked_outcomes"].splitlines()[0]
        safety_notes.append(f"Guardrail: {first_block}")
    if unsupported_language:
        safety_notes.append(f"Detected {detected_language}, which is outside configured language policy.")
    if advice_request and regulated:
        safety_notes.append("Caller requested regulated advice; human handoff is required.")

    sensitive = regulated and (emergency or human_request or advice_request)
    handoff = (
        score >= int(business.get("hot_lead_threshold") or 75)
        or human_request
        or emergency
        or sensitive
        or high_value
        or complaint
        or unsupported_language
        or ("pay" in lower and booking_requested)
    )

    fields = {
        "business_type": business["business_type"],
        "booking_requested": booking_requested,
        "human_request": human_request,
        "emergency_detected": emergency,
        "number_of_people": extract_people(transcript),
        "requested_time": extract_time(transcript),
        "knowledge_matches": [item["question"] for item in relevant_knowledge],
        "detected_language": detected_language,
        "module_key": business.get("module_key") or "custom",
        "workflow_version": business.get("workflow_version") or "v1",
        "allowed_call_types": business.get("allowed_call_types"),
        "blocked_outcomes": business.get("blocked_outcomes"),
        "compliance_profile": business.get("compliance_profile"),
        "unsupported_language": unsupported_language,
        "advice_request": advice_request,
    }
    customer = name or "Unknown caller"
    service_text = service or request_type or "business request"
    summary = f"{customer} contacted {business['name']} about {service_text}."
    if timeline:
        summary += f" Timeline/date mentioned: {timeline}."
    if budget:
        summary += f" Budget signal: {budget}."
    if phone or email:
        summary += " Contact details were provided."

    if handoff:
        action = f"Send to {business.get('handoff_name') or 'the team'} for fast follow-up."
    elif temp == "warm":
        action = "Follow up with availability, pricing, or next steps."
    else:
        action = "Keep as a low-priority inquiry and ask for missing details."

    return {
        "customer_name": name,
        "customer_phone": phone,
        "customer_email": email,
        "request_type": request_type,
        "service_requested": service,
        "industry": business["business_type"],
        "location": location,
        "urgency": urgency,
        "timeline": timeline,
        "budget": budget,
        "intent": intent,
        "detected_language": detected_language,
        "extracted_fields": fields,
        "lead_score": score,
        "lead_temperature": temp,
        "ai_summary": summary,
        "recommended_action": action,
        "score_breakdown": breakdown,
        "booking_requested": booking_requested,
        "handoff_triggered": handoff,
        "safety_notes": safety_notes,
    }
