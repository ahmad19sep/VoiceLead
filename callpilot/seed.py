from __future__ import annotations

import sqlite3
from typing import Any

from .analysis import analyze_call
from .config import APP_NAME, SAMPLE_TRANSCRIPTS
from .modules import comma, lines, module_for_business_type
from .repositories import get_business, get_knowledge, get_services
from .utils import days_ago, now
from .workflows import create_lead_from_analysis


def template_for_business_type(business_type: str) -> dict[str, Any]:
    templates = {
        "Hotel": {
            "agent_name": "Sara AI Receptionist",
            "tone": "Premium hotel style",
            "greeting": "Hi, thanks for calling RoyalStay Hotel. This is Sara, your AI booking assistant. How can I help with your stay today?",
            "fallback": "I can take this as a booking request and send it to hotel staff for confirmation.",
            "description": "AI hotel receptionist for booking requests, guest questions, and handoff.",
            "fields": "Name, Phone, Check-in date, Check-out date, Guests, Room type, Budget, Special request",
        },
        "Clinic": {
            "agent_name": "Amina AI Receptionist",
            "tone": "Clinic receptionist style",
            "greeting": "Hi, thanks for calling BrightCare Clinic. This is Amina, your AI receptionist. I can help with appointments and clinic questions.",
            "fallback": "I can collect your details and ask clinic staff to follow up.",
            "description": "AI clinic receptionist for appointment booking and patient intake. No medical diagnosis.",
            "fields": "Patient name, Phone, Appointment reason, Preferred date/time, New or existing patient, Urgency",
        },
        "Home Services": {
            "agent_name": "Omar AI Dispatcher",
            "tone": "Emergency dispatcher style",
            "greeting": "Hi, thanks for calling EliteFix Plumbing & HVAC. I can help with repairs and urgent service requests.",
            "fallback": "I can collect your details and send them to dispatch.",
            "description": "AI dispatcher for repair calls, urgent jobs, technician visits, and lead capture.",
            "fields": "Name, Phone, Service, Location, Urgency, Problem description",
        },
        "Restaurant": {
            "agent_name": "Mina AI Host",
            "tone": "Warm",
            "greeting": "Hi, thanks for calling QuickBite Restaurant. I can help with reservations and menu questions.",
            "fallback": "I can send your reservation request to the restaurant team.",
            "description": "AI restaurant host for reservations, menu questions, timings, and guest requests.",
            "fields": "Name, Phone, Date, Time, Number of guests, Special request",
        },
        "Software Agency": {
            "agent_name": "Zain AI Sales Assistant",
            "tone": "Sales assistant style",
            "greeting": "Hi, thanks for calling CodeNest Software House. I can help understand your project and connect you with sales.",
            "fallback": "I can capture your requirements and send them to the sales team.",
            "description": "AI lead qualification assistant for software projects, budget, timeline, and sales handoff.",
            "fields": "Name, Company, Project type, Budget, Timeline, Email, Phone",
        },
        "Law Firm": {
            "agent_name": "Noor AI Intake Assistant",
            "tone": "Legal intake style",
            "greeting": "Hi, thanks for calling LegalBridge Law Firm. This is Noor, your AI intake assistant. I can collect details for a consultation.",
            "fallback": "I can collect your details and send them to the lawyer. I cannot give legal advice.",
            "description": "AI legal intake assistant for case screening and consultation booking. No legal advice.",
            "fields": "Name, Phone, Case type, Short case description, Urgency, Preferred consultation time",
        },
        "Custom": {
            "agent_name": "CallPilot Custom Agent",
            "tone": "Professional",
            "greeting": "Hi, thanks for calling. I can help answer questions, collect details, and send requests to the team.",
            "fallback": "I can collect your details and ask the team to follow up.",
            "description": "Flexible AI phone agent for a custom business.",
            "fields": "Name, Phone, Email, Request, Timeline, Notes",
        },
    }
    return templates.get(business_type, templates["Custom"])

def seed_data(conn: sqlite3.Connection) -> None:
    settings = {
        "app_name": APP_NAME,
        "theme": "dark premium",
        "demo_mode": "true",
        "default_hot_lead_threshold": "75",
        "default_warm_lead_threshold": "45",
        "production_guardrails": "enabled",
        "default_language_policy": "English, Urdu, Roman Urdu/Hindi",
    }
    for key, value in settings.items():
        conn.execute(
            "insert into settings (key, value, created_at, updated_at) values (?, ?, ?, ?)",
            (key, value, now(), now()),
        )

    businesses = [
        {
            "name": "RoyalStay Hotel",
            "business_type": "Hotel",
            "phone": "+92 300 1000001",
            "email": "bookings@royalstay.example",
            "location": "Lahore",
            "working_hours": "24/7 front desk",
            "website": "https://royalstay.example",
            "handoff_name": "Hotel Front Desk",
            "handoff_phone": "+92 300 1000101",
            "handoff_email": "frontdesk@royalstay.example",
            "services": [
                ("Deluxe room", "Comfortable room for couples or solo guests", "From Rs. 18,000/night", 1, 0),
                ("Suite", "Premium suite for business and family stays", "From Rs. 35,000/night", 1, 0),
                ("Airport pickup", "Pickup and drop-off service", "Priced by route", 1, 0),
            ],
            "faqs": [
                ("What is check-in time?", "Check-in starts at 2 PM.", "Booking"),
                ("What is check-out time?", "Check-out is at 12 PM.", "Booking"),
                ("Do you offer breakfast?", "Breakfast is available with selected room packages.", "Facilities"),
                ("Can I cancel my booking?", "Cancellation depends on the booking package and notice period.", "Policy"),
                ("Do you have airport pickup?", "Yes, airport pickup can be requested.", "Facilities"),
            ],
        },
        {
            "name": "BrightCare Dental Clinic",
            "business_type": "Clinic",
            "phone": "+92 300 1000002",
            "email": "appointments@brightcare.example",
            "location": "Gulberg Lahore",
            "working_hours": "10:00 AM - 7:00 PM",
            "website": "https://brightcare.example",
            "handoff_name": "Clinic Reception",
            "handoff_phone": "+92 300 1000202",
            "handoff_email": "reception@brightcare.example",
            "services": [
                ("Dental checkup", "Routine dental checkup", "Rs. 2,500 consultation", 1, 0),
                ("Cleaning", "Dental scaling and cleaning", "Starting Rs. 8,000", 1, 0),
                ("Emergency appointment", "Urgent dental pain appointment", "Same-day subject to availability", 1, 1),
            ],
            "faqs": [
                ("What are clinic timings?", "The clinic is open 10 AM to 7 PM.", "Hours"),
                ("Can I book tomorrow?", "The AI can create an appointment request for staff confirmation.", "Booking"),
                ("Do you diagnose on phone?", "No diagnosis is provided by phone.", "Safety"),
                ("Do you see new patients?", "Yes, new patients can request appointments.", "Appointments"),
                ("Is emergency care available?", "Urgent cases are handed to clinic staff.", "Emergency"),
            ],
        },
        {
            "name": "EliteFix Plumbing & HVAC",
            "business_type": "Home Services",
            "phone": "+92 300 1000003",
            "email": "dispatch@elitefix.example",
            "location": "DHA Lahore",
            "working_hours": "9:00 AM - 8:00 PM",
            "website": "https://elitefix.example",
            "handoff_name": "Dispatch Team",
            "handoff_phone": "+92 300 1000303",
            "handoff_email": "dispatch@elitefix.example",
            "services": [
                ("AC repair", "AC repair and cooling issues", "Inspection fee applies", 1, 1),
                ("Plumbing", "Leaks, bathroom plumbing, and pipe repairs", "Quote after inspection", 1, 1),
                ("Water heater", "Water heater repair and maintenance", "Quote after inspection", 1, 1),
            ],
            "faqs": [
                ("Do you handle urgent AC repair?", "Yes, urgent AC repair requests are sent to dispatch.", "Emergency"),
                ("Which areas do you serve?", "DHA, Gulberg, Model Town, Johar Town, and nearby Lahore areas.", "Service area"),
                ("Do you give exact price on phone?", "Exact price depends on inspection.", "Pricing"),
                ("Can I book a technician today?", "The AI can create a technician visit request.", "Booking"),
                ("Do you repair water heaters?", "Yes, water heater repair is supported.", "Services"),
            ],
        },
        {
            "name": "QuickBite Restaurant",
            "business_type": "Restaurant",
            "phone": "+92 300 1000004",
            "email": "reservations@quickbite.example",
            "location": "MM Alam Road Lahore",
            "working_hours": "12:00 PM - 12:00 AM",
            "website": "https://quickbite.example",
            "handoff_name": "Restaurant Manager",
            "handoff_phone": "+92 300 1000404",
            "handoff_email": "manager@quickbite.example",
            "services": [
                ("Table reservation", "Reserve tables for dine-in guests", "No booking fee", 1, 0),
                ("Family dinner", "Family seating and group reservations", "Advance request preferred", 1, 0),
                ("Menu questions", "Menu and timing questions", "Free", 0, 0),
            ],
            "faqs": [
                ("Do you take reservations?", "Yes, reservation requests can be created.", "Reservations"),
                ("What time do you close?", "The restaurant closes at midnight.", "Hours"),
                ("Do you have family seating?", "Yes, family seating is available.", "Facilities"),
                ("Can I reserve for a group?", "Group reservations can be requested.", "Reservations"),
                ("Do you offer takeaway?", "Yes, takeaway is available.", "Services"),
            ],
        },
        {
            "name": "CodeNest Software House",
            "business_type": "Software Agency",
            "phone": "+92 300 1000005",
            "email": "sales@codenest.example",
            "location": "Lahore",
            "working_hours": "10:00 AM - 6:00 PM",
            "website": "https://codenest.example",
            "handoff_name": "Sales Team",
            "handoff_phone": "+92 300 1000505",
            "handoff_email": "sales@codenest.example",
            "services": [
                ("AI voice agent", "Custom AI voice and call automation", "Discovery call required", 1, 0),
                ("CRM platform", "Custom CRM and dashboard development", "Project quote required", 1, 0),
                ("Web app", "Web app design and development", "Project quote required", 1, 0),
            ],
            "faqs": [
                ("Do you build AI agents?", "Yes, AI voice agents and workflow automations are supported.", "Services"),
                ("Do you give fixed quotes?", "A quote depends on scope, budget, and timeline.", "Pricing"),
                ("Can I book a discovery call?", "Yes, the AI can create a discovery call request.", "Sales"),
                ("Do you build CRMs?", "Yes, custom CRMs and dashboards are supported.", "Services"),
                ("How soon can work start?", "Start date depends on team availability and project scope.", "Timeline"),
            ],
        },
        {
            "name": "LegalBridge Law Firm",
            "business_type": "Law Firm",
            "phone": "+92 300 1000006",
            "email": "intake@legalbridge.example",
            "location": "Lahore",
            "working_hours": "9:00 AM - 5:00 PM",
            "website": "https://legalbridge.example",
            "handoff_name": "Legal Intake Team",
            "handoff_phone": "+92 300 1000606",
            "handoff_email": "intake@legalbridge.example",
            "services": [
                ("Business contract", "Consultation for business contracts", "Consultation fee applies", 1, 0),
                ("Company registration", "Company setup consultation", "Consultation fee applies", 1, 0),
                ("Property matter", "Property legal consultation", "Consultation fee applies", 1, 0),
            ],
            "faqs": [
                ("Can I get legal advice by phone?", "The AI only collects details and does not give legal advice.", "Safety"),
                ("Can I book a consultation?", "Yes, consultation requests can be created.", "Booking"),
                ("Do you handle contracts?", "Yes, business contract consultations are supported.", "Services"),
                ("Can urgent cases be escalated?", "Urgent requests are handed to the legal intake team.", "Handoff"),
                ("What details are needed?", "Name, phone, case type, short description, and urgency.", "Intake"),
            ],
        },
    ]

    for data in businesses:
        t = template_for_business_type(data["business_type"])
        module = module_for_business_type(data["business_type"])
        business_id = conn.execute(
            """
            insert into businesses (
                name, business_type, description, phone, email, website, location, working_hours,
                agent_name, agent_greeting, agent_tone, fallback_message, handoff_name,
                handoff_phone, handoff_email, handoff_instructions, module_key, intake_fields,
                allowed_call_types, blocked_outcomes, supported_languages, compliance_profile,
                consent_policy, recording_disclosure, quiet_hours, max_outbound_attempts,
                integration_targets, qa_checks, workflow_version, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["name"],
                data["business_type"],
                t["description"],
                data["phone"],
                data["email"],
                data["website"],
                data["location"],
                data["working_hours"],
                t["agent_name"],
                t["greeting"],
                t["tone"],
                t["fallback"],
                data["handoff_name"],
                data["handoff_phone"],
                data["handoff_email"],
                "Alert the assigned team member when handoff rules trigger.",
                module["key"],
                lines(module["intake_fields"]),
                lines(module["allowed_call_types"]),
                lines(module["blocked_outcomes"]),
                module["language_policy"],
                module["compliance_profile"],
                "Outbound calls require consent, opt-out handling, and client policy approval.",
                "Disclose recording when enabled by the client and required by region.",
                "09:00-18:00 local time unless the client policy says otherwise.",
                0 if data["business_type"] in {"Clinic", "Law Firm"} else 2,
                module["integration_targets"],
                comma(module["qa_checks"]),
                "v1",
                now(),
                now(),
            ),
        ).lastrowid

        for service in data["services"]:
            conn.execute(
                """
                insert into services (business_id, name, description, price_note, is_bookable, is_emergency)
                values (?, ?, ?, ?, ?, ?)
                """,
                (business_id, *service),
            )
        for question, answer, category in data["faqs"]:
            conn.execute(
                """
                insert into knowledge_base (business_id, question, answer, category, tags, source)
                values (?, ?, ?, ?, ?, 'seed')
                """,
                (business_id, question, answer, category, category.lower()),
            )

    samples = [
        (1, SAMPLE_TRANSCRIPTS["hotel"], "demo", days_ago(0, 2)),
        (2, SAMPLE_TRANSCRIPTS["clinic"], "demo", days_ago(0, 3)),
        (3, SAMPLE_TRANSCRIPTS["home"], "demo", days_ago(0, 5)),
        (4, "Caller: I want to ask if you have outdoor seating and what time you close.", "demo", days_ago(1, 1)),
        (5, SAMPLE_TRANSCRIPTS["software"], "demo", days_ago(0, 6)),
        (6, SAMPLE_TRANSCRIPTS["law"], "demo", days_ago(1, 3)),
        (1, "Caller: Just checking prices for a suite next month. I do not want to book yet.", "demo", days_ago(2, 0)),
        (4, "Caller: Do you have a kids menu? I may visit sometime later.", "demo", days_ago(2, 4)),
    ]
    for business_id, transcript, provider, created_at in samples:
        business = get_business(conn, business_id)
        if not business:
            continue
        analysis = analyze_call(transcript, business, get_services(conn, business_id), get_knowledge(conn, business_id))
        create_lead_from_analysis(conn, business_id, transcript, analysis, provider=provider, created_at=created_at)
