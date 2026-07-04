from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "CallPilot AI"

APP_TAGLINE = "Universal AI Calling Agent for Any Business"

DB_PATH = Path(__file__).resolve().parent.parent / "callpilot.db"

BUSINESS_TYPES = [
    "Hotel",
    "Clinic",
    "Hospital",
    "Dentist",
    "Home Services",
    "Restaurant",
    "Call Center",
    "Customer Support",
    "Lead Generation",
    "Sales",
    "Software Agency",
    "Law Firm",
    "Legal",
    "Insurance",
    "Finance",
    "Real Estate",
    "Property Management",
    "Ecommerce",
    "Retail",
    "Automotive",
    "Logistics",
    "Education",
    "Recruiting",
    "Travel",
    "Government",
    "Custom",
]

TONE_OPTIONS = [
    "Friendly",
    "Professional",
    "Warm",
    "Fast and direct",
    "Premium hotel style",
    "Clinic receptionist style",
    "Sales assistant style",
    "Emergency dispatcher style",
    "Legal intake style",
    "Custom",
]

SCORE_RULES = {
    "clear_need": 20,
    "contact_detail": 15,
    "name_provided": 10,
    "timeline_date": 15,
    "ready_to_book": 20,
    "matches_service": 10,
    "urgency_high_value": 10,
}

SCORE_LABELS = {
    "clear_need": "Clear need/request detected",
    "contact_detail": "Contact detail provided",
    "name_provided": "Name provided",
    "timeline_date": "Timeline/date provided",
    "ready_to_book": "Ready to book / wants callback",
    "matches_service": "Matches business service",
    "urgency_high_value": "Urgency or high-value signal",
}

SAMPLE_TRANSCRIPTS = {
    "hotel": """AI: Hi, thanks for calling RoyalStay Hotel. How can I help you today?
Caller: I want to book a deluxe room for this Friday for two people.
AI: Sure, may I have your name and phone number?
Caller: My name is Ahmad and my number is 0300-1234567.
AI: Great. How many nights will you stay?
Caller: Two nights. Please confirm availability.""",
    "clinic": """AI: Hi, thanks for calling BrightCare Dental Clinic. How can I help you?
Caller: I need to book a dental checkup tomorrow.
AI: Sure, may I have your name?
Caller: Ahmad.
AI: And your phone number?
Caller: 0300-1234567.
AI: Are you a new or existing patient?
Caller: New patient.""",
    "home": """AI: Hi, thanks for calling EliteFix Plumbing & HVAC. How can I help?
Caller: My AC stopped working and I need someone today.
AI: What area are you located in?
Caller: DHA Lahore.
AI: May I have your name and phone number?
Caller: Ahmad, 0300-1234567.""",
    "restaurant": """AI: Hi, thanks for calling QuickBite Restaurant. How can I help?
Caller: I want to reserve a table for 8 people tonight.
AI: Sure, what time should I reserve it for?
Caller: 8 PM.
AI: May I have your name and phone number?
Caller: Ahmad, 0300-1234567.""",
    "software": """AI: Hi, thanks for calling CodeNest Software House. How can I help?
Caller: I need an AI voice agent and CRM for my business.
AI: That sounds good. What is your timeline and budget?
Caller: I want to start this week and my budget is around $2000.
AI: May I have your name and email?
Caller: Ahmad, ahmad@example.com.""",
    "law": """AI: Hi, thanks for calling LegalBridge Law Firm. How can I help?
Caller: I need to book a consultation with a lawyer about a business contract.
AI: I can collect your details for a consultation. May I have your name and phone number?
Caller: Ahmad, 0300-1234567.
AI: Is this urgent?
Caller: Yes, I need help this week.""",
    "custom": """AI: Hi, thanks for calling your business. How can I help today?
Caller: I want to talk to a human about your service and get a quote this week.
AI: May I have your name and phone number?
Caller: Ahmad, 0300-1234567.""",
}

def load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
