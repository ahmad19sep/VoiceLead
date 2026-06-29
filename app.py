from __future__ import annotations

import html
import json
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse


APP_NAME = "CallPilot AI"
APP_TAGLINE = "Universal AI Calling Agent for Any Business"
DB_PATH = Path(__file__).with_name("callpilot.db")

BUSINESS_TYPES = [
    "Hotel",
    "Clinic",
    "Home Services",
    "Restaurant",
    "Software Agency",
    "Law Firm",
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
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def days_ago(days: int, hours: int = 0) -> str:
    return (datetime.now() - timedelta(days=days, hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def title(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(part.capitalize() for part in value.replace("_", " ").split())


def money_or_text(value: str | None) -> str:
    return value if value else "Not provided"


def format_dt(value: str | None) -> str:
    if not value:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt).strftime("%b %d, %I:%M %p")
        except ValueError:
            pass
    return value


def as_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True)


def from_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    return conn


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None


def lead_temperature(score: int) -> str:
    if score >= 75:
        return "hot"
    if score >= 45:
        return "warm"
    return "cold"


def badge(text: str, kind: str) -> str:
    return f'<span class="badge {esc(kind)}">{esc(text)}</span>'


def temp_badge(temp: str) -> str:
    return badge(title(temp), f"temp-{temp}")


def status_badge(status: str) -> str:
    return badge(title(status), f"status-{status}")


def integration_badge(connected: bool, label: str | None = None) -> str:
    if connected:
        return badge(label or "Connected", "status-active")
    return badge(label or "Missing", "status-missing")


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            create table if not exists businesses (
                id integer primary key autoincrement,
                name text not null,
                business_type text not null,
                description text,
                phone text,
                email text,
                website text,
                location text,
                working_hours text,
                agent_name text,
                agent_greeting text,
                agent_tone text,
                fallback_message text,
                hot_lead_threshold integer default 75,
                warm_lead_threshold integer default 45,
                handoff_name text,
                handoff_phone text,
                handoff_email text,
                handoff_instructions text,
                status text default 'active',
                created_at text default current_timestamp,
                updated_at text default current_timestamp
            );

            create table if not exists services (
                id integer primary key autoincrement,
                business_id integer not null,
                name text not null,
                description text,
                price_note text,
                is_bookable integer default 1,
                is_emergency integer default 0,
                created_at text default current_timestamp,
                foreign key (business_id) references businesses(id) on delete cascade
            );

            create table if not exists knowledge_base (
                id integer primary key autoincrement,
                business_id integer not null,
                question text not null,
                answer text not null,
                category text,
                tags text,
                source text,
                embedding_id text,
                created_at text default current_timestamp,
                foreign key (business_id) references businesses(id) on delete cascade
            );

            create table if not exists leads (
                id integer primary key autoincrement,
                business_id integer,
                customer_name text,
                customer_phone text,
                customer_email text,
                request_type text,
                service_requested text,
                industry text,
                location text,
                urgency text,
                timeline text,
                budget text,
                intent text,
                extracted_fields text,
                lead_score integer default 0,
                lead_temperature text default 'cold',
                status text default 'new',
                ai_summary text,
                recommended_action text,
                transcript text,
                score_breakdown text,
                safety_notes text,
                handoff_triggered integer default 0,
                booking_requested integer default 0,
                created_at text default current_timestamp,
                updated_at text default current_timestamp,
                foreign key (business_id) references businesses(id) on delete set null
            );

            create table if not exists bookings (
                id integer primary key autoincrement,
                business_id integer not null,
                lead_id integer,
                customer_name text,
                customer_phone text,
                customer_email text,
                booking_type text,
                requested_date text,
                requested_time text,
                number_of_people text,
                service_requested text,
                notes text,
                status text default 'requested',
                created_at text default current_timestamp,
                updated_at text default current_timestamp,
                foreign key (business_id) references businesses(id) on delete cascade,
                foreign key (lead_id) references leads(id) on delete set null
            );

            create table if not exists call_logs (
                id integer primary key autoincrement,
                business_id integer,
                lead_id integer,
                provider text default 'demo',
                call_id text,
                caller_phone text,
                transcript text,
                recording_url text,
                duration_seconds integer,
                call_status text,
                analysis_json text,
                created_at text default current_timestamp,
                foreign key (business_id) references businesses(id) on delete set null,
                foreign key (lead_id) references leads(id) on delete set null
            );

            create table if not exists call_sessions (
                id integer primary key autoincrement,
                business_id integer,
                call_sid text unique,
                caller_phone text,
                transcript text,
                turn_count integer default 0,
                lead_id integer,
                status text default 'active',
                created_at text default current_timestamp,
                updated_at text default current_timestamp,
                foreign key (business_id) references businesses(id) on delete cascade,
                foreign key (lead_id) references leads(id) on delete set null
            );

            create table if not exists notifications (
                id integer primary key autoincrement,
                business_id integer,
                lead_id integer,
                notification_type text,
                channel text default 'dashboard',
                recipient text,
                subject text,
                message text,
                status text default 'sent',
                created_at text default current_timestamp,
                foreign key (business_id) references businesses(id) on delete cascade,
                foreign key (lead_id) references leads(id) on delete set null
            );

            create table if not exists agent_events (
                id integer primary key autoincrement,
                business_id integer,
                lead_id integer,
                event_type text not null,
                description text,
                metadata text,
                created_at text default current_timestamp,
                foreign key (business_id) references businesses(id) on delete cascade,
                foreign key (lead_id) references leads(id) on delete set null
            );

            create table if not exists settings (
                id integer primary key autoincrement,
                key text unique not null,
                value text,
                created_at text default current_timestamp,
                updated_at text default current_timestamp
            );
            """
        )
        count = conn.execute("select count(*) from businesses").fetchone()[0]
        if count == 0:
            seed_data(conn)


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
        business_id = conn.execute(
            """
            insert into businesses (
                name, business_type, description, phone, email, website, location, working_hours,
                agent_name, agent_greeting, agent_tone, fallback_message, handoff_name,
                handoff_phone, handoff_email, handoff_instructions, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def get_businesses(conn: sqlite3.Connection, business_type: str | None = None) -> list[dict[str, Any]]:
    if business_type and business_type != "All Businesses":
        rows = conn.execute(
            "select * from businesses where business_type = ? order by name",
            (business_type,),
        ).fetchall()
    else:
        rows = conn.execute("select * from businesses order by name").fetchall()
    return [dict(row) for row in rows]


def get_business(conn: sqlite3.Connection, business_id: int) -> dict[str, Any] | None:
    return row_dict(conn.execute("select * from businesses where id = ?", (business_id,)).fetchone())


def get_services(conn: sqlite3.Connection, business_id: int) -> list[dict[str, Any]]:
    rows = conn.execute("select * from services where business_id = ? order by id", (business_id,)).fetchall()
    return [dict(row) for row in rows]


def get_knowledge(conn: sqlite3.Connection, business_id: int) -> list[dict[str, Any]]:
    rows = conn.execute("select * from knowledge_base where business_id = ? order by id", (business_id,)).fetchall()
    return [dict(row) for row in rows]


def get_leads(conn: sqlite3.Connection, filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
    filters = filters or {}
    sql = """
        select leads.*, businesses.name as business_name, businesses.business_type
        from leads
        left join businesses on businesses.id = leads.business_id
    """
    clauses = []
    args: list[Any] = []
    if filters.get("business_id"):
        clauses.append("leads.business_id = ?")
        args.append(filters["business_id"])
    if filters.get("temperature") and filters["temperature"] != "all":
        clauses.append("leads.lead_temperature = ?")
        args.append(filters["temperature"])
    if filters.get("status") and filters["status"] != "all":
        clauses.append("leads.status = ?")
        args.append(filters["status"])
    if filters.get("q"):
        clauses.append(
            "(customer_name like ? or customer_phone like ? or service_requested like ? or businesses.name like ?)"
        )
        needle = f"%{filters['q']}%"
        args.extend([needle, needle, needle, needle])
    if clauses:
        sql += " where " + " and ".join(clauses)
    sql += " order by datetime(leads.created_at) desc"
    return [dict(row) for row in conn.execute(sql, args).fetchall()]


def get_lead(conn: sqlite3.Connection, lead_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        select leads.*, businesses.name as business_name, businesses.business_type, businesses.agent_name,
               businesses.handoff_email, businesses.handoff_phone
        from leads
        left join businesses on businesses.id = leads.business_id
        where leads.id = ?
        """,
        (lead_id,),
    ).fetchone()
    return row_dict(row)


def get_bookings(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select bookings.*, businesses.name as business_name
        from bookings
        left join businesses on businesses.id = bookings.business_id
        order by datetime(bookings.created_at) desc
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_call_logs(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select call_logs.*, businesses.name as business_name, leads.customer_name
        from call_logs
        left join businesses on businesses.id = call_logs.business_id
        left join leads on leads.id = call_logs.lead_id
        order by datetime(call_logs.created_at) desc
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_notifications(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select notifications.*, businesses.name as business_name, leads.customer_name
        from notifications
        left join businesses on businesses.id = notifications.business_id
        left join leads on leads.id = notifications.lead_id
        order by datetime(notifications.created_at) desc
        """
    ).fetchall()
    return [dict(row) for row in rows]


def get_events(conn: sqlite3.Connection, lead_id: int | None = None) -> list[dict[str, Any]]:
    if lead_id:
        rows = conn.execute(
            "select * from agent_events where lead_id = ? order by datetime(created_at) desc",
            (lead_id,),
        ).fetchall()
    else:
        rows = conn.execute("select * from agent_events order by datetime(created_at) desc limit 12").fetchall()
    return [dict(row) for row in rows]


def clean(value: str) -> str:
    return re.sub(r"[.,!?;:]+$", "", value.strip())


def first_match(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return clean(match.group(1))
    return None


def extract_name(text: str) -> str | None:
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
            if re.fullmatch(r"[A-Za-z ]{2,40}", first):
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
    if business_type == "Clinic":
        return "Dental appointment" if any(word in lower for word in ["appointment", "checkup", "book"]) else "Clinic inquiry"
    if business_type == "Home Services":
        return "Technician visit" if any(word in lower for word in ["repair", "technician", "stopped", "leak"]) else "Service inquiry"
    if business_type == "Restaurant":
        return "Table reservation" if any(word in lower for word in ["reserve", "reservation", "table"]) else "Restaurant inquiry"
    if business_type == "Software Agency":
        return "Project inquiry"
    if business_type == "Law Firm":
        return "Legal consultation"
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
    if business["business_type"] == "Clinic":
        safety_notes.append("No medical diagnosis or medicine recommendation was given.")
    if business["business_type"] == "Law Firm":
        safety_notes.append("No legal advice was given; the call is intake only.")
    if business["business_type"] == "Hotel":
        safety_notes.append("Availability is not confirmed until staff verifies the booking request.")

    sensitive = business["business_type"] in {"Clinic", "Law Firm"} and (emergency or human_request)
    handoff = (
        score >= int(business.get("hot_lead_threshold") or 75)
        or human_request
        or emergency
        or sensitive
        or high_value
        or complaint
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


def create_event(
    conn: sqlite3.Connection,
    business_id: int | None,
    lead_id: int | None,
    event_type: str,
    description: str,
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> None:
    conn.execute(
        """
        insert into agent_events (business_id, lead_id, event_type, description, metadata, created_at)
        values (?, ?, ?, ?, ?, ?)
        """,
        (business_id, lead_id, event_type, description, as_json(metadata or {}), created_at or now()),
    )


def create_notification(conn: sqlite3.Connection, business_id: int, lead_id: int, analysis: dict[str, Any]) -> None:
    business = get_business(conn, business_id)
    if not business:
        return
    subject = f"Hot lead: {business['name']} - {analysis.get('request_type') or 'Call request'}"
    message = "\n".join(
        [
            "Hot Lead Alert",
            f"Business: {business['name']}",
            f"Agent: {business.get('agent_name') or 'AI Agent'}",
            f"Customer: {analysis.get('customer_name') or 'Unknown'}",
            f"Phone: {analysis.get('customer_phone') or 'Not provided'}",
            f"Request: {analysis.get('request_type') or analysis.get('service_requested') or 'Unknown'}",
            f"Score: {analysis.get('lead_score')}/100",
            "",
            f"Summary: {analysis.get('ai_summary')}",
            "",
            f"Recommended Action: {analysis.get('recommended_action')}",
        ]
    )
    conn.execute(
        """
        insert into notifications (
            business_id, lead_id, notification_type, channel, recipient, subject, message, status, created_at
        )
        values (?, ?, 'hot_lead_alert', 'dashboard', ?, ?, ?, 'sent', ?)
        """,
        (business_id, lead_id, business.get("handoff_email"), subject, message, now()),
    )
    create_event(conn, business_id, lead_id, "notification_created", "Hot lead notification created.", {})


def create_booking(conn: sqlite3.Connection, business_id: int, lead_id: int, analysis: dict[str, Any]) -> None:
    fields = analysis.get("extracted_fields") or {}
    conn.execute(
        """
        insert into bookings (
            business_id, lead_id, customer_name, customer_phone, customer_email, booking_type,
            requested_date, requested_time, number_of_people, service_requested, notes, status, created_at, updated_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'requested', ?, ?)
        """,
        (
            business_id,
            lead_id,
            analysis.get("customer_name"),
            analysis.get("customer_phone"),
            analysis.get("customer_email"),
            analysis.get("request_type"),
            analysis.get("timeline"),
            fields.get("requested_time"),
            fields.get("number_of_people"),
            analysis.get("service_requested"),
            analysis.get("ai_summary"),
            now(),
            now(),
        ),
    )
    create_event(conn, business_id, lead_id, "booking_created", "Booking request created.", {})


def create_lead_from_analysis(
    conn: sqlite3.Connection,
    business_id: int,
    transcript: str,
    analysis: dict[str, Any],
    provider: str = "demo",
    call_id: str | None = None,
    caller_phone: str | None = None,
    recording_url: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    created = created_at or now()
    cur = conn.execute(
        """
        insert into leads (
            business_id, customer_name, customer_phone, customer_email, request_type, service_requested,
            industry, location, urgency, timeline, budget, intent, extracted_fields,
            lead_score, lead_temperature, status, ai_summary, recommended_action, transcript,
            score_breakdown, safety_notes, handoff_triggered, booking_requested, created_at, updated_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            business_id,
            analysis.get("customer_name"),
            analysis.get("customer_phone") or caller_phone,
            analysis.get("customer_email"),
            analysis.get("request_type"),
            analysis.get("service_requested"),
            analysis.get("industry"),
            analysis.get("location"),
            analysis.get("urgency"),
            analysis.get("timeline"),
            analysis.get("budget"),
            analysis.get("intent"),
            as_json(analysis.get("extracted_fields") or {}),
            analysis.get("lead_score"),
            analysis.get("lead_temperature"),
            analysis.get("ai_summary"),
            analysis.get("recommended_action"),
            transcript,
            as_json(analysis.get("score_breakdown") or {}),
            as_json(analysis.get("safety_notes") or []),
            1 if analysis.get("handoff_triggered") else 0,
            1 if analysis.get("booking_requested") else 0,
            created,
            created,
        ),
    )
    lead_id = int(cur.lastrowid)
    conn.execute(
        """
        insert into call_logs (
            business_id, lead_id, provider, call_id, caller_phone, transcript, recording_url,
            duration_seconds, call_status, analysis_json, created_at
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, 'analyzed', ?, ?)
        """,
        (
            business_id,
            lead_id,
            provider,
            call_id,
            caller_phone or analysis.get("customer_phone"),
            transcript,
            recording_url,
            max(45, len(transcript.split()) * 2),
            as_json(analysis),
            created,
        ),
    )
    create_event(conn, business_id, lead_id, "lead_created", "Lead created from call analysis.", {}, created)
    create_event(
        conn,
        business_id,
        lead_id,
        "lead_scored",
        f"Lead scored {analysis.get('lead_score')}/100 and marked {analysis.get('lead_temperature')}.",
        analysis.get("score_breakdown"),
        created,
    )
    if analysis.get("booking_requested"):
        create_booking(conn, business_id, lead_id, analysis)
    if analysis.get("handoff_triggered"):
        create_notification(conn, business_id, lead_id, analysis)
        create_event(conn, business_id, lead_id, "human_handoff_triggered", "Human handoff rule triggered.", {})
    return get_lead(conn, lead_id) or {"id": lead_id}


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
    cur = conn.execute(
        """
        insert into call_sessions (business_id, call_sid, caller_phone, transcript, turn_count, status, created_at, updated_at)
        values (?, ?, ?, '', 0, 'active', ?, ?)
        """,
        (business_id, call_sid, caller_phone, now(), now()),
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


def stats(conn: sqlite3.Connection, business_type: str | None = None) -> dict[str, int]:
    business_clause = ""
    args: list[Any] = []
    if business_type and business_type != "All Businesses":
        business_clause = " where business_type = ?"
        args.append(business_type)
    businesses = conn.execute(f"select id from businesses{business_clause}", args).fetchall()
    ids = [row["id"] for row in businesses]
    if ids:
        placeholders = ",".join("?" for _ in ids)
        lead_where = f" where business_id in ({placeholders})"
        lead_args = ids
    else:
        lead_where = " where 1 = 0"
        lead_args = []
    today = datetime.now().strftime("%Y-%m-%d")
    total_leads = conn.execute(f"select count(*) from leads{lead_where}", lead_args).fetchone()[0]
    total_score = conn.execute(f"select coalesce(sum(lead_score), 0) from leads{lead_where}", lead_args).fetchone()[0]
    return {
        "businesses": len(ids),
        "active_agents": conn.execute(
            f"select count(*) from businesses{business_clause} {'and' if business_clause else 'where'} status = 'active'",
            args,
        ).fetchone()[0],
        "total_calls": conn.execute(
            f"select count(*) from call_logs{lead_where.replace('business_id', 'business_id')}",
            lead_args,
        ).fetchone()[0],
        "calls_today": conn.execute(
            f"select count(*) from call_logs{lead_where} and date(created_at) = ?",
            [*lead_args, today],
        ).fetchone()[0],
        "total_leads": total_leads,
        "hot_leads": conn.execute(
            f"select count(*) from leads{lead_where} and lead_temperature = 'hot'",
            lead_args,
        ).fetchone()[0],
        "warm_leads": conn.execute(
            f"select count(*) from leads{lead_where} and lead_temperature = 'warm'",
            lead_args,
        ).fetchone()[0],
        "cold_leads": conn.execute(
            f"select count(*) from leads{lead_where} and lead_temperature = 'cold'",
            lead_args,
        ).fetchone()[0],
        "bookings": conn.execute(
            f"select count(*) from bookings{lead_where}",
            lead_args,
        ).fetchone()[0],
        "pending_handoffs": conn.execute(
            f"select count(*) from leads{lead_where} and handoff_triggered = 1 and status = 'new'",
            lead_args,
        ).fetchone()[0],
        "avg_score": round(total_score / total_leads) if total_leads else 0,
    }


def layout(title_text: str, active: str, content: str) -> str:
    nav = [
        ("/", "Dashboard"),
        ("/businesses", "Businesses"),
        ("/agent-builder", "Agent Builder"),
        ("/demo-call", "Demo Call"),
        ("/real-calling", "Real Calling"),
        ("/leads", "Leads"),
        ("/bookings", "Bookings"),
        ("/calls", "Calls"),
        ("/notifications", "Notifications"),
        ("/settings", "Settings"),
    ]
    nav_html = "".join(
        f'<a class="{"active" if active == label else ""}" href="{href}">{label}</a>' for href, label in nav
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title_text)} - {APP_NAME}</title>
  <style>
    :root {{
      --bg: #07111f;
      --panel: rgba(255,255,255,.085);
      --panel-strong: rgba(255,255,255,.13);
      --white: #f8fafc;
      --muted: #a7b5c8;
      --line: rgba(255,255,255,.16);
      --hot: #fb7185;
      --warm: #fbbf24;
      --cold: #94a3b8;
      --green: #34d399;
      --blue: #38bdf8;
      --purple: #a78bfa;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at top left, rgba(56,189,248,.22), transparent 34%),
        radial-gradient(circle at 90% 10%, rgba(167,139,250,.22), transparent 30%),
        linear-gradient(135deg, #07111f 0%, #0f172a 48%, #111827 100%);
      color: var(--white);
      font-family: Inter, Segoe UI, Arial, sans-serif;
      min-height: 100vh;
    }}
    a {{ color: inherit; text-decoration: none; }}
    .shell {{ display: grid; grid-template-columns: 274px 1fr; min-height: 100vh; }}
    .sidebar {{
      border-right: 1px solid var(--line);
      background: rgba(2,6,23,.74);
      backdrop-filter: blur(18px);
      padding: 22px 16px;
      position: sticky;
      top: 0;
      height: 100vh;
    }}
    .brand {{ display: flex; gap: 12px; align-items: center; margin-bottom: 24px; }}
    .mark {{ width: 44px; height: 44px; display: grid; place-items: center; border-radius: 12px; background: linear-gradient(135deg, var(--blue), var(--purple)); font-weight: 900; }}
    .brand strong {{ display: block; font-size: 16px; }}
    .brand span {{ color: var(--muted); font-size: 12px; }}
    .nav {{ display: grid; gap: 6px; }}
    .nav a {{ padding: 11px 12px; border-radius: 10px; color: var(--muted); font-size: 14px; font-weight: 750; }}
    .nav a:hover, .nav a.active {{ background: var(--panel-strong); color: white; }}
    .main {{ min-width: 0; }}
    .topbar {{ min-height: 70px; display: flex; justify-content: space-between; align-items: center; padding: 16px 28px; border-bottom: 1px solid var(--line); background: rgba(15,23,42,.5); backdrop-filter: blur(14px); }}
    .topbar p {{ margin: 3px 0 0; color: var(--muted); font-size: 13px; }}
    main {{ max-width: 1320px; margin: 0 auto; padding: 28px; }}
    h1 {{ margin: 0; font-size: 31px; letter-spacing: 0; }}
    h2 {{ margin: 0; font-size: 18px; }}
    h3 {{ margin: 0; font-size: 15px; }}
    p {{ line-height: 1.65; }}
    .muted {{ color: var(--muted); }}
    .hero {{ padding: 28px; border: 1px solid var(--line); border-radius: 22px; background: linear-gradient(135deg, rgba(56,189,248,.16), rgba(167,139,250,.12)); box-shadow: 0 24px 80px rgba(0,0,0,.22); }}
    .hero p {{ max-width: 880px; color: #d5deea; }}
    .grid {{ display: grid; gap: 16px; }}
    .metrics {{ grid-template-columns: repeat(6, minmax(0,1fr)); margin-top: 18px; }}
    .two {{ grid-template-columns: 1.15fr .85fr; }}
    .three {{ grid-template-columns: repeat(3, minmax(0,1fr)); }}
    .cards {{ grid-template-columns: repeat(3, minmax(0,1fr)); }}
    .panel {{ border: 1px solid var(--line); border-radius: 18px; background: var(--panel); box-shadow: 0 20px 70px rgba(0,0,0,.18); backdrop-filter: blur(16px); }}
    .pad {{ padding: 20px; }}
    .metric {{ padding: 18px; border: 1px solid var(--line); border-radius: 18px; background: rgba(255,255,255,.08); }}
    .metric span {{ display:block; color: var(--muted); font-size: 13px; font-weight: 750; }}
    .metric strong {{ display:block; margin-top: 9px; font-size: 30px; }}
    .hot strong {{ color: var(--hot); }} .warm strong {{ color: var(--warm); }} .cold strong {{ color: var(--cold); }} .good strong {{ color: var(--green); }}
    .row {{ display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap; }}
    .actions {{ display: flex; gap: 9px; flex-wrap: wrap; align-items: center; }}
    .btn {{ border: 1px solid var(--line); border-radius: 10px; background: rgba(255,255,255,.08); color: white; padding: 10px 14px; min-height: 40px; font-weight: 800; cursor: pointer; display: inline-flex; align-items:center; justify-content:center; }}
    .btn:hover {{ background: rgba(255,255,255,.14); }}
    .btn.primary {{ background: linear-gradient(135deg, var(--blue), var(--purple)); border-color: transparent; color: #03111f; }}
    .btn.danger {{ color: var(--hot); }}
    .badge {{ display:inline-flex; min-height:24px; align-items:center; border-radius:999px; padding:3px 9px; font-size:12px; font-weight:850; border:1px solid transparent; }}
    .temp-hot {{ background: rgba(251,113,133,.16); color: #fecdd3; border-color: rgba(251,113,133,.36); }}
    .temp-warm {{ background: rgba(251,191,36,.15); color: #fde68a; border-color: rgba(251,191,36,.36); }}
    .temp-cold {{ background: rgba(148,163,184,.16); color: #cbd5e1; border-color: rgba(148,163,184,.36); }}
    .status-active, .status-won, .status-sent, .status-connected {{ background: rgba(52,211,153,.15); color:#bbf7d0; border-color: rgba(52,211,153,.35); }}
    .status-new, .status-demo, .status-requested {{ background: rgba(56,189,248,.15); color:#bae6fd; border-color: rgba(56,189,248,.35); }}
    .status-follow_up, .status-contacted {{ background: rgba(251,191,36,.15); color:#fde68a; border-color: rgba(251,191,36,.35); }}
    .status-lost, .status-missing {{ background: rgba(251,113,133,.15); color:#fecdd3; border-color: rgba(251,113,133,.35); }}
    .list .item {{ display:block; padding: 15px 20px; border-top: 1px solid var(--line); }}
    .list .item:first-child {{ border-top: 0; }}
    .list .item:hover {{ background: rgba(255,255,255,.06); }}
    .mini {{ border:1px solid var(--line); border-radius: 14px; padding: 14px; background: rgba(255,255,255,.07); }}
    .mini span {{ color: var(--muted); font-size: 12px; font-weight: 800; display:block; }}
    .mini strong {{ display:block; margin-top:5px; }}
    table {{ width:100%; border-collapse:collapse; min-width: 940px; }}
    th {{ text-align:left; color: var(--muted); font-size:12px; text-transform:uppercase; padding:13px 16px; background:rgba(255,255,255,.06); }}
    td {{ padding:15px 16px; border-top:1px solid var(--line); vertical-align:middle; }}
    tr:hover td {{ background: rgba(255,255,255,.045); }}
    .table-wrap {{ overflow-x:auto; }}
    input, textarea, select {{ width:100%; border:1px solid var(--line); border-radius:11px; padding:11px 12px; background:rgba(2,6,23,.46); color:white; font:inherit; }}
    option {{ color:#111827; }}
    textarea {{ min-height: 150px; resize:vertical; line-height:1.55; }}
    label {{ display:grid; gap:7px; font-size:14px; font-weight:800; }}
    .form-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:15px; }}
    .full {{ grid-column: 1 / -1; }}
    pre {{ white-space:pre-wrap; overflow:auto; background:rgba(2,6,23,.65); color:#e5edf8; border-radius:14px; padding:16px; line-height:1.6; }}
    .bar {{ height:9px; border-radius:999px; overflow:hidden; background:rgba(255,255,255,.11); }}
    .bar span {{ display:block; height:100%; background:linear-gradient(90deg, var(--blue), var(--purple)); }}
    @media (max-width: 1100px) {{
      .shell {{ grid-template-columns:1fr; }}
      .sidebar {{ height:auto; position:static; }}
      .nav {{ grid-template-columns: repeat(9, max-content); overflow-x:auto; }}
      .metrics, .two, .three, .cards, .form-grid {{ grid-template-columns:1fr; }}
      main, .topbar {{ padding-left:16px; padding-right:16px; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand"><div class="mark">CP</div><div><strong>{APP_NAME}</strong><span>{APP_TAGLINE}</span></div></div>
      <nav class="nav">{nav_html}</nav>
    </aside>
    <div class="main">
      <header class="topbar">
        <div><strong>{APP_NAME}</strong><p>{APP_TAGLINE}</p></div>
        <div>{badge('Demo mode', 'status-demo')}</div>
      </header>
      <main>{content}</main>
    </div>
  </div>
</body>
</html>"""


def metric(label: str, value: Any, kind: str = "") -> str:
    return f'<div class="metric {esc(kind)}"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>'


def render_dashboard(query: dict[str, list[str]]) -> str:
    selected = query.get("type", ["All Businesses"])[0]
    with db() as conn:
        s = stats(conn, selected)
        events = get_events(conn)
        leads = get_leads(conn, {"temperature": "hot"})[:5]
    options = "".join(
        f'<option value="{esc(item)}" {"selected" if selected == item else ""}>{esc(item)}</option>'
        for item in ["All Businesses", *BUSINESS_TYPES]
    )
    event_html = "".join(
        f'<div class="item"><strong>{esc(e["description"])}</strong><div class="muted">{esc(e["event_type"])} - {format_dt(e["created_at"])}</div></div>'
        for e in events
    )
    lead_html = "".join(
        f'<a class="item" href="/leads/{lead["id"]}"><div class="row"><div><strong>{esc(lead["customer_name"] or "Unknown caller")}</strong> {temp_badge(lead["lead_temperature"])}<div class="muted">{esc(lead["business_name"])} - {esc(lead["request_type"])}</div></div><strong>{lead["lead_score"]}/100</strong></div></a>'
        for lead in leads
    )
    content = f"""
    <section class="hero">
      <h1>{APP_NAME}</h1>
      <p>{APP_TAGLINE}</p>
      <p>Create AI phone agents for hotels, clinics, restaurants, agencies, home services, law firms, and more - all from one dashboard.</p>
      <div class="actions">
        <a class="btn primary" href="/agent-builder">Create New Agent</a>
        <a class="btn" href="/demo-call">Test Demo Call</a>
        <a class="btn" href="/leads">View Leads</a>
      </div>
    </section>
    <form method="get" class="actions" style="margin-top:18px;">
      <select style="max-width:260px" name="type">{options}</select>
      <button class="btn" type="submit">Filter</button>
    </form>
    <section class="grid metrics">
      {metric('Total Businesses', s['businesses'])}
      {metric('Active Agents', s['active_agents'], 'good')}
      {metric('Calls Today', s['calls_today'])}
      {metric('Total Leads', s['total_leads'])}
      {metric('Hot Leads', s['hot_leads'], 'hot')}
      {metric('Bookings', s['bookings'], 'warm')}
      {metric('Pending Handoffs', s['pending_handoffs'], 'hot')}
      {metric('Average Score', s['avg_score'])}
      {metric('Warm Leads', s['warm_leads'], 'warm')}
      {metric('Cold Leads', s['cold_leads'], 'cold')}
      {metric('Total Calls', s['total_calls'])}
    </section>
    <section class="grid two" style="margin-top:18px;">
      <div class="panel"><div class="pad"><h2>Latest Call Activity</h2></div><div class="list">{event_html}</div></div>
      <div class="panel"><div class="pad"><h2>Recent Hot Leads</h2></div><div class="list">{lead_html}</div></div>
    </section>
    """
    return layout("Dashboard", "Dashboard", content)


def render_businesses() -> str:
    with db() as conn:
        businesses = get_businesses(conn)
        cards = []
        for business in businesses:
            counts = stats(conn, business["business_type"])
            cards.append(
                f"""
                <article class="panel pad">
                  <div class="row"><h2>{esc(business['name'])}</h2>{status_badge(business['status'])}</div>
                  <p class="muted">{esc(business['business_type'])} - {esc(business['agent_name'])}</p>
                  <div class="grid three">
                    <div class="mini"><span>Total Leads</span><strong>{counts['total_leads']}</strong></div>
                    <div class="mini"><span>Hot Leads</span><strong>{counts['hot_leads']}</strong></div>
                    <div class="mini"><span>Bookings</span><strong>{counts['bookings']}</strong></div>
                  </div>
                  <div class="actions" style="margin-top:14px;">
                    <a class="btn" href="/businesses/{business['id']}">View</a>
                    <a class="btn" href="/agent-builder?business_id={business['id']}">Edit</a>
                    <a class="btn primary" href="/demo-call?business_id={business['id']}">Test Call</a>
                  </div>
                </article>
                """
            )
    content = f"""
    <section class="row">
      <div><h1>Businesses</h1><p class="muted">Create and manage AI phone agents for multiple industries.</p></div>
      <a class="btn primary" href="/agent-builder">Create Business Agent</a>
    </section>
    <section class="grid cards" style="margin-top:18px;">{''.join(cards)}</section>
    """
    return layout("Businesses", "Businesses", content)


def render_business_detail(business_id: int) -> str:
    with db() as conn:
        business = get_business(conn, business_id)
        if not business:
            return render_not_found()
        services = get_services(conn, business_id)
        knowledge = get_knowledge(conn, business_id)
        leads = get_leads(conn, {"business_id": str(business_id)})[:5]
    services_html = "".join(
        f'<div class="mini"><span>{esc(s["name"])}</span><strong>{esc(s["description"])}</strong><p class="muted">{esc(s["price_note"])}</p></div>'
        for s in services
    )
    faq_html = "".join(
        f'<div class="item"><strong>{esc(k["question"])}</strong><div class="muted">{esc(k["answer"])}</div></div>'
        for k in knowledge
    )
    lead_html = "".join(
        f'<a class="item" href="/leads/{lead["id"]}"><strong>{esc(lead["customer_name"] or "Unknown")}</strong> {temp_badge(lead["lead_temperature"])}<div class="muted">{esc(lead["request_type"])} - {lead["lead_score"]}/100</div></a>'
        for lead in leads
    )
    content = f"""
    <a class="btn" href="/businesses">Back to Businesses</a>
    <section class="hero" style="margin-top:16px;">
      <div class="row">
        <div><h1>{esc(business['name'])}</h1><p>{esc(business['business_type'])} - {esc(business['agent_name'])}</p></div>
        {status_badge(business['status'])}
      </div>
      <p>{esc(business['description'])}</p>
      <div class="actions">
        <a class="btn primary" href="/demo-call?business_id={business_id}">Test Call</a>
        <a class="btn" href="/agent-builder?business_id={business_id}">Edit Agent</a>
      </div>
    </section>
    <section class="grid two" style="margin-top:18px;">
      <div class="panel pad"><h2>Services</h2><div class="grid three" style="margin-top:14px;">{services_html}</div></div>
      <div class="panel"><div class="pad"><h2>Knowledge Base / FAQs</h2></div><div class="list">{faq_html}</div></div>
    </section>
    <section class="panel" style="margin-top:18px;"><div class="pad"><h2>Recent Leads</h2></div><div class="list">{lead_html}</div></section>
    """
    return layout(business["name"], "Businesses", content)


def parse_lines(text: str, parts: int) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        pieces = [piece.strip() for piece in line.split("|")]
        while len(pieces) < parts:
            pieces.append("")
        rows.append(pieces[:parts])
    return rows


def render_agent_builder(query: dict[str, list[str]]) -> str:
    business_id = int(query.get("business_id", ["0"])[0] or 0)
    with db() as conn:
        business = get_business(conn, business_id) if business_id else None
        services = get_services(conn, business_id) if business_id else []
        knowledge = get_knowledge(conn, business_id) if business_id else []
    template = template_for_business_type(business["business_type"] if business else "Hotel")
    business_type_value = business["business_type"] if business else "Hotel"
    type_options = "".join(
        f'<option value="{esc(item)}" {"selected" if item == business_type_value else ""}>{esc(item)}</option>'
        for item in BUSINESS_TYPES
    )
    tone_value = business["agent_tone"] if business else template["tone"]
    tone_options = "".join(
        f'<option value="{esc(item)}" {"selected" if item == tone_value else ""}>{esc(item)}</option>'
        for item in TONE_OPTIONS
    )
    services_text = "\n".join(
        f"{s['name']} | {s['description']} | {s['price_note'] or ''} | {s['is_bookable']} | {s['is_emergency']}"
        for s in services
    ) or "Service name | Description | Price note | 1 | 0"
    faq_text = "\n".join(f"{k['question']} | {k['answer']} | {k['category'] or ''}" for k in knowledge) or (
        "Question | Answer | Category"
    )
    action = f"/agent-builder/{business_id}/update" if business else "/agent-builder/create"
    content = f"""
    <section>
      <h1>Agent Builder</h1>
      <p class="muted">Create a flexible AI phone agent for any business.</p>
    </section>
    <form class="panel pad" method="post" action="{action}" style="margin-top:18px;">
      <h2>Business Info</h2>
      <div class="form-grid" style="margin-top:14px;">
        <label>Business name<input name="name" value="{esc((business or {}).get('name', ''))}" required></label>
        <label>Business type<select name="business_type">{type_options}</select></label>
        <label class="full">Description<textarea name="description">{esc((business or {}).get('description', template['description']))}</textarea></label>
        <label>Phone<input name="phone" value="{esc((business or {}).get('phone', ''))}"></label>
        <label>Email<input name="email" value="{esc((business or {}).get('email', ''))}"></label>
        <label>Location<input name="location" value="{esc((business or {}).get('location', ''))}"></label>
        <label>Working hours<input name="working_hours" value="{esc((business or {}).get('working_hours', ''))}"></label>
        <label>Website<input name="website" value="{esc((business or {}).get('website', ''))}"></label>
      </div>
      <h2 style="margin-top:22px;">Agent Identity</h2>
      <div class="form-grid" style="margin-top:14px;">
        <label>Agent name<input name="agent_name" value="{esc((business or {}).get('agent_name', template['agent_name']))}"></label>
        <label>Agent tone<select name="agent_tone">{tone_options}</select></label>
        <label class="full">Agent greeting<textarea name="agent_greeting">{esc((business or {}).get('agent_greeting', template['greeting']))}</textarea></label>
        <label class="full">Fallback message<textarea name="fallback_message">{esc((business or {}).get('fallback_message', template['fallback']))}</textarea></label>
      </div>
      <h2 style="margin-top:22px;">Services</h2>
      <p class="muted">One per line: service name | description | price note | is bookable 1/0 | is emergency 1/0</p>
      <textarea name="services">{esc(services_text)}</textarea>
      <h2 style="margin-top:22px;">Knowledge Base / FAQs</h2>
      <p class="muted">One per line: question | answer | category</p>
      <textarea name="faqs">{esc(faq_text)}</textarea>
      <h2 style="margin-top:22px;">Human Handoff Rules</h2>
      <div class="form-grid" style="margin-top:14px;">
        <label>Hot lead threshold<input type="number" name="hot_lead_threshold" value="{esc((business or {}).get('hot_lead_threshold', 75))}"></label>
        <label>Warm lead threshold<input type="number" name="warm_lead_threshold" value="{esc((business or {}).get('warm_lead_threshold', 45))}"></label>
        <label>Handoff person name<input name="handoff_name" value="{esc((business or {}).get('handoff_name', ''))}"></label>
        <label>Handoff phone<input name="handoff_phone" value="{esc((business or {}).get('handoff_phone', ''))}"></label>
        <label>Handoff email<input name="handoff_email" value="{esc((business or {}).get('handoff_email', ''))}"></label>
        <label class="full">Handoff instructions<textarea name="handoff_instructions">{esc((business or {}).get('handoff_instructions', 'Alert the assigned team member when handoff rules trigger.'))}</textarea></label>
      </div>
      <div class="actions" style="margin-top:18px;"><button class="btn primary" type="submit">Save Agent</button></div>
    </form>
    """
    return layout("Agent Builder", "Agent Builder", content)


def save_agent(form: dict[str, str], business_id: int | None = None) -> int:
    with db() as conn:
        if business_id:
            conn.execute(
                """
                update businesses set name=?, business_type=?, description=?, phone=?, email=?, website=?, location=?,
                working_hours=?, agent_name=?, agent_greeting=?, agent_tone=?, fallback_message=?,
                hot_lead_threshold=?, warm_lead_threshold=?, handoff_name=?, handoff_phone=?,
                handoff_email=?, handoff_instructions=?, updated_at=? where id=?
                """,
                (
                    form.get("name"),
                    form.get("business_type"),
                    form.get("description"),
                    form.get("phone"),
                    form.get("email"),
                    form.get("website"),
                    form.get("location"),
                    form.get("working_hours"),
                    form.get("agent_name"),
                    form.get("agent_greeting"),
                    form.get("agent_tone"),
                    form.get("fallback_message"),
                    int(form.get("hot_lead_threshold") or 75),
                    int(form.get("warm_lead_threshold") or 45),
                    form.get("handoff_name"),
                    form.get("handoff_phone"),
                    form.get("handoff_email"),
                    form.get("handoff_instructions"),
                    now(),
                    business_id,
                ),
            )
            conn.execute("delete from services where business_id=?", (business_id,))
            conn.execute("delete from knowledge_base where business_id=?", (business_id,))
        else:
            business_id = int(
                conn.execute(
                    """
                    insert into businesses (
                        name, business_type, description, phone, email, website, location, working_hours,
                        agent_name, agent_greeting, agent_tone, fallback_message, hot_lead_threshold,
                        warm_lead_threshold, handoff_name, handoff_phone, handoff_email, handoff_instructions,
                        status, created_at, updated_at
                    )
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (
                        form.get("name"),
                        form.get("business_type"),
                        form.get("description"),
                        form.get("phone"),
                        form.get("email"),
                        form.get("website"),
                        form.get("location"),
                        form.get("working_hours"),
                        form.get("agent_name"),
                        form.get("agent_greeting"),
                        form.get("agent_tone"),
                        form.get("fallback_message"),
                        int(form.get("hot_lead_threshold") or 75),
                        int(form.get("warm_lead_threshold") or 45),
                        form.get("handoff_name"),
                        form.get("handoff_phone"),
                        form.get("handoff_email"),
                        form.get("handoff_instructions"),
                        now(),
                        now(),
                    ),
                ).lastrowid
            )
        for name, description, price, bookable, emergency in parse_lines(form.get("services", ""), 5):
            if name.lower() == "service name" or not name:
                continue
            conn.execute(
                "insert into services (business_id, name, description, price_note, is_bookable, is_emergency) values (?, ?, ?, ?, ?, ?)",
                (business_id, name, description, price, int(bookable or 1), int(emergency or 0)),
            )
        for question, answer, category in parse_lines(form.get("faqs", ""), 3):
            if question.lower() == "question" or not question:
                continue
            conn.execute(
                "insert into knowledge_base (business_id, question, answer, category, tags, source) values (?, ?, ?, ?, ?, 'agent_builder')",
                (business_id, question, answer, category, category.lower()),
            )
        create_event(conn, business_id, None, "agent_saved", "Business agent saved from Agent Builder.", {})
        return business_id


def render_demo_call(query: dict[str, list[str]]) -> str:
    with db() as conn:
        businesses = get_businesses(conn)
    business_id = int(query.get("business_id", [businesses[0]["id"] if businesses else 1])[0] or 1)
    sample_key = query.get("sample", ["hotel"])[0]
    selected = next((b for b in businesses if int(b["id"]) == business_id), businesses[0])
    transcript = SAMPLE_TRANSCRIPTS.get(sample_key) or SAMPLE_TRANSCRIPTS.get(selected["business_type"].lower().split()[0], SAMPLE_TRANSCRIPTS["custom"])
    options = "".join(
        f'<option value="{b["id"]}" {"selected" if int(b["id"]) == business_id else ""}>{esc(b["name"])} - {esc(b["business_type"])}</option>'
        for b in businesses
    )
    sample_links = "".join(
        f'<a class="btn" href="/demo-call?business_id={business_id}&sample={key}">{esc(label)}</a>'
        for key, label in [
            ("hotel", "Hotel Booking"),
            ("clinic", "Clinic Appointment"),
            ("home", "Home Emergency"),
            ("restaurant", "Restaurant Reservation"),
            ("software", "Software Inquiry"),
            ("law", "Law Consultation"),
            ("custom", "Custom Business"),
        ]
    )
    content = f"""
    <section>
      <h1>Demo Call Simulator</h1>
      <p class="muted">Select a business, test a sample transcript, and create leads, bookings, call logs, and handoff alerts.</p>
    </section>
    <section class="grid two" style="margin-top:18px;">
      <form class="panel pad" method="post" action="/demo-call/analyze">
        <label>Business<select name="business_id">{options}</select></label>
        <p class="muted"><strong>Agent greeting:</strong> {esc(selected.get('agent_greeting'))}</p>
        <div class="actions" style="margin-bottom:12px;">{sample_links}</div>
        <label>Transcript<textarea name="transcript" style="min-height:360px;">{esc(transcript)}</textarea></label>
        <div class="actions" style="margin-top:14px;"><button class="btn primary" type="submit">Analyze Call</button></div>
      </form>
      <aside class="panel pad">
        <h2>Mock AI Agent Pipeline</h2>
        <p class="muted">Router Agent, Knowledge Agent, Lead Qualification Agent, Booking Agent, Scoring Agent, Handoff Agent, Safety Agent, and Notification Agent run in demo mode.</p>
        <div class="grid">
          <div class="mini"><span>AI Provider</span><strong>Mock AI active unless keys exist</strong></div>
          <div class="mini"><span>Database</span><strong>SQLite local mode</strong></div>
          <div class="mini"><span>Voice</span><strong>Webhook-ready demo mode</strong></div>
        </div>
      </aside>
    </section>
    """
    return layout("Demo Call", "Demo Call", content)


def render_real_calling(query: dict[str, list[str]]) -> str:
    selected_id = int(query.get("business_id", ["1"])[0] or 1)
    message = query.get("message", [""])[0]
    error = query.get("error", [""])[0]
    public_url = app_url()
    with db() as conn:
        businesses = get_businesses(conn)
    selected = next((b for b in businesses if int(b["id"]) == selected_id), businesses[0])
    options = "".join(
        f'<option value="{b["id"]}" {"selected" if int(b["id"]) == selected_id else ""}>{esc(b["name"])} - {esc(b["business_type"])}</option>'
        for b in businesses
    )
    webhook_url = f"{public_url}/api/twilio/voice?business_id={selected_id}"
    gather_url = f"{public_url}/api/twilio/gather?business_id={selected_id}"
    can_twilio_reach = not (public_url.startswith("http://127.0.0.1") or public_url.startswith("http://localhost"))
    status_note = (
        integration_badge(True, "Public URL set")
        if can_twilio_reach
        else integration_badge(False, "Needs public HTTPS URL")
    )
    content = f"""
    <section class="hero">
      <h1>Real Calling</h1>
      <p>Connect a real Twilio phone number to CallPilot AI. Twilio will call these webhooks when someone phones your number, CallPilot will gather speech, analyze the call, create a lead, create a booking when needed, and trigger handoff notifications.</p>
      <div class="actions">{status_note} {integration_badge(env_connected('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_PHONE_NUMBER'), 'Twilio keys ready' if env_connected('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_PHONE_NUMBER') else 'Twilio keys missing')}</div>
    </section>
    {'<section class="panel pad" style="margin-top:16px;">'+badge('Success','status-active')+' '+esc(message)+'</section>' if message else ''}
    {'<section class="panel pad" style="margin-top:16px;">'+badge('Error','status-missing')+' '+esc(error)+'</section>' if error else ''}
    <section class="grid two" style="margin-top:18px;">
      <div class="panel pad">
        <h2>Inbound Calling Setup</h2>
        <form method="get" action="/real-calling" class="actions" style="margin-top:14px;">
          <select style="max-width:360px" name="business_id">{options}</select>
          <button class="btn" type="submit">Show Webhook</button>
        </form>
        <p class="muted">Selected business: <strong>{esc(selected['name'])}</strong></p>
        <label>Twilio Voice Webhook URL<input readonly value="{esc(webhook_url)}"></label>
        <p class="muted">In Twilio Console, open your phone number, set **A call comes in** to Webhook, method POST, and paste the URL above.</p>
        <div class="mini" style="margin-top:12px;">
          <span>Important</span>
          <strong>Twilio cannot call 127.0.0.1 directly.</strong>
          <p class="muted">Use ngrok or another tunnel, set APP_URL in `.env` to that public HTTPS URL, restart `python app.py`, then copy the webhook again.</p>
        </div>
      </div>
      <div class="panel pad">
        <h2>Outbound Test Call</h2>
        <p class="muted">This makes Twilio call your phone, then CallPilot speaks and gathers your answer.</p>
        <form method="post" action="/real-calling/outbound" class="grid" style="margin-top:14px;">
          <label>Business<select name="business_id">{options}</select></label>
          <label>Your phone number<input name="to_number" placeholder="+923001234567"></label>
          <button class="btn primary" type="submit">Start Real Test Call</button>
        </form>
      </div>
    </section>
    <section class="panel pad" style="margin-top:18px;">
      <h2>What Happens During A Real Call</h2>
      <div class="grid three" style="margin-top:14px;">
        <div class="mini"><span>1</span><strong>Caller phones Twilio number</strong><p class="muted">Twilio requests CallPilot's voice webhook.</p></div>
        <div class="mini"><span>2</span><strong>CallPilot asks questions</strong><p class="muted">Twilio speech recognition sends spoken answers back.</p></div>
        <div class="mini"><span>3</span><strong>Lead is created</strong><p class="muted">The same scoring, booking, call log, and notification engine runs.</p></div>
      </div>
    </section>
    <section class="panel pad" style="margin-top:18px;">
      <h2>Developer Endpoints</h2>
      <p><strong>Initial Twilio webhook:</strong> <code>{esc(webhook_url)}</code></p>
      <p><strong>Speech gather webhook:</strong> <code>{esc(gather_url)}</code></p>
    </section>
    """
    return layout("Real Calling", "Real Calling", content)


def render_leads(query: dict[str, list[str]]) -> str:
    filters = {
        "q": query.get("q", [""])[0],
        "temperature": query.get("temperature", ["all"])[0],
        "status": query.get("status", ["all"])[0],
        "business_id": query.get("business_id", [""])[0],
    }
    with db() as conn:
        leads = get_leads(conn, filters)
        businesses = get_businesses(conn)
    business_options = '<option value="">All Businesses</option>' + "".join(
        f'<option value="{b["id"]}" {"selected" if str(b["id"]) == filters["business_id"] else ""}>{esc(b["name"])}</option>'
        for b in businesses
    )
    temp_options = "".join(
        f'<option value="{v}" {"selected" if filters["temperature"] == v else ""}>{title(v)}</option>'
        for v in ["all", "hot", "warm", "cold"]
    )
    status_options = "".join(
        f'<option value="{v}" {"selected" if filters["status"] == v else ""}>{title(v)}</option>'
        for v in ["all", "new", "contacted", "follow_up", "won", "lost"]
    )
    rows = "".join(
        f"""
        <tr>
          <td><strong>{esc(lead['customer_name'] or 'Unknown')}</strong></td>
          <td>{esc(lead['business_name'])}</td>
          <td>{esc(lead['customer_phone'] or lead['customer_email'] or 'Missing')}</td>
          <td>{esc(lead['request_type'] or lead['service_requested'] or 'Request')}</td>
          <td><strong>{lead['lead_score']}</strong> {temp_badge(lead['lead_temperature'])}</td>
          <td>{status_badge(lead['status'])}</td>
          <td>{'Yes' if lead['booking_requested'] else 'No'}</td>
          <td>{'Yes' if lead['handoff_triggered'] else 'No'}</td>
          <td><a class="btn" href="/leads/{lead['id']}">View</a></td>
        </tr>
        """
        for lead in leads
    )
    content = f"""
    <section class="row"><div><h1>Leads CRM</h1><p class="muted">Universal lead inbox for all business agents.</p></div><a class="btn primary" href="/demo-call">Create Lead From Demo Call</a></section>
    <form method="get" class="panel pad actions" style="margin-top:18px;">
      <input style="max-width:240px" name="q" value="{esc(filters['q'])}" placeholder="Search leads">
      <select style="max-width:220px" name="business_id">{business_options}</select>
      <select style="max-width:150px" name="temperature">{temp_options}</select>
      <select style="max-width:160px" name="status">{status_options}</select>
      <button class="btn primary" type="submit">Filter</button>
    </form>
    <section class="panel table-wrap" style="margin-top:18px;"><table><thead><tr><th>Customer</th><th>Business</th><th>Contact</th><th>Request</th><th>Score</th><th>Status</th><th>Booking</th><th>Handoff</th><th>Open</th></tr></thead><tbody>{rows or '<tr><td colspan="9">No leads found.</td></tr>'}</tbody></table></section>
    """
    return layout("Leads", "Leads", content)


def render_lead_detail(lead_id: int) -> str:
    with db() as conn:
        lead = get_lead(conn, lead_id)
        if not lead:
            return render_not_found()
        events = get_events(conn, lead_id)
        booking = conn.execute("select * from bookings where lead_id = ? order by id desc limit 1", (lead_id,)).fetchone()
    breakdown = from_json(lead.get("score_breakdown"), {})
    safety = from_json(lead.get("safety_notes"), [])
    extracted = from_json(lead.get("extracted_fields"), {})
    bars = "".join(
        f'<div style="margin-bottom:13px;"><div class="row"><strong>{esc(SCORE_LABELS[key])}</strong><span class="muted">{int(breakdown.get(key,0))}/{max_points}</span></div><div class="bar"><span style="width:{min(100,int((int(breakdown.get(key,0))/max_points)*100))}%"></span></div></div>'
        for key, max_points in SCORE_RULES.items()
    )
    safety_html = "".join(f'<li>{esc(note)}</li>' for note in safety) or "<li>No safety warnings.</li>"
    fields_html = "".join(f'<div class="mini"><span>{esc(title(k))}</span><strong>{esc(v)}</strong></div>' for k, v in extracted.items())
    event_html = "".join(
        f'<div class="item"><strong>{esc(e["description"])}</strong><div class="muted">{esc(e["event_type"])} - {format_dt(e["created_at"])}</div></div>'
        for e in events
    )
    booking_html = (
        f'<div class="mini"><span>Booking Request</span><strong>{esc(booking["booking_type"])}</strong><p class="muted">{esc(booking["status"])} - {esc(booking["requested_date"] or "")} {esc(booking["requested_time"] or "")}</p></div>'
        if booking
        else '<div class="mini"><span>Booking Request</span><strong>None</strong></div>'
    )
    status_buttons = "".join(
        f'<form method="post" action="/leads/{lead_id}/status"><input type="hidden" name="status" value="{s}"><button class="btn" type="submit">Mark {title(s)}</button></form>'
        for s in ["contacted", "follow_up", "won", "lost"]
    )
    content = f"""
    <a class="btn" href="/leads">Back to Leads</a>
    <section class="hero" style="margin-top:16px;">
      <div class="row"><div><h1>{esc(lead['customer_name'] or 'Unknown caller')}</h1><p>{esc(lead['business_name'])} - {esc(lead['request_type'])}</p></div><div>{temp_badge(lead['lead_temperature'])} {status_badge(lead['status'])}</div></div>
      <div class="grid three" style="margin-top:14px;"><div class="mini"><span>Score</span><strong>{lead['lead_score']}/100</strong></div><div class="mini"><span>Contact</span><strong>{esc(lead['customer_phone'] or lead['customer_email'] or 'Missing')}</strong></div>{booking_html}</div>
      <div class="actions" style="margin-top:16px;">{status_buttons}<form method="post" action="/leads/{lead_id}/handoff"><button class="btn primary" type="submit">Trigger Handoff</button></form><form method="post" action="/leads/{lead_id}/delete"><button class="btn danger" type="submit">Delete</button></form></div>
    </section>
    <section class="grid two" style="margin-top:18px;">
      <div class="grid">
        <div class="panel pad"><h2>AI Summary</h2><p>{esc(lead['ai_summary'])}</p><div class="mini"><span>Recommended Action</span><strong>{esc(lead['recommended_action'])}</strong></div></div>
        <div class="panel pad"><h2>Score Breakdown</h2><div style="margin-top:14px;">{bars}</div></div>
        <div class="panel pad"><h2>Safety Notes</h2><ul>{safety_html}</ul></div>
      </div>
      <div class="grid">
        <div class="panel pad"><h2>Extracted Fields</h2><div class="grid two" style="margin-top:14px;">{fields_html}</div></div>
        <div class="panel pad"><h2>Call Transcript</h2><pre>{esc(lead['transcript'])}</pre></div>
        <div class="panel"><div class="pad"><h2>Event Timeline</h2></div><div class="list">{event_html}</div></div>
      </div>
    </section>
    """
    return layout("Lead Detail", "Leads", content)


def render_bookings() -> str:
    with db() as conn:
        bookings = get_bookings(conn)
    rows = "".join(
        f"""
        <tr>
          <td><strong>{esc(b['customer_name'] or 'Unknown')}</strong></td><td>{esc(b['business_name'])}</td><td>{esc(b['booking_type'])}</td><td>{esc(b['requested_date'] or '')}</td><td>{esc(b['requested_time'] or '')}</td><td>{esc(b['number_of_people'] or '')}</td><td>{status_badge(b['status'])}</td><td><form method="post" action="/bookings/{b['id']}/status"><select name="status"><option>requested</option><option>confirmed</option><option>completed</option><option>cancelled</option></select><button class="btn" type="submit">Update</button></form></td>
        </tr>
        """
        for b in bookings
    )
    content = f"<section><h1>Bookings</h1><p class='muted'>Booking requests created by AI agents.</p></section><section class='panel table-wrap' style='margin-top:18px;'><table><thead><tr><th>Customer</th><th>Business</th><th>Type</th><th>Date</th><th>Time</th><th>People</th><th>Status</th><th>Action</th></tr></thead><tbody>{rows}</tbody></table></section>"
    return layout("Bookings", "Bookings", content)


def render_calls() -> str:
    with db() as conn:
        calls = get_call_logs(conn)
    rows = "".join(
        f"<tr><td>{esc(c['business_name'])}</td><td>{esc(c['customer_name'] or 'Unknown')}</td><td>{esc(c['provider'])}</td><td>{esc(c['caller_phone'] or '')}</td><td>{esc(c['call_status'])}</td><td>{esc(c['duration_seconds'])}s</td><td>{format_dt(c['created_at'])}</td><td><a class='btn' href='/leads/{c['lead_id']}'>Lead</a></td></tr>"
        for c in calls
    )
    content = f"<section><h1>Call Logs</h1><p class='muted'>Demo calls and future voice provider webhook logs.</p></section><section class='panel table-wrap' style='margin-top:18px;'><table><thead><tr><th>Business</th><th>Customer</th><th>Provider</th><th>Caller Phone</th><th>Status</th><th>Duration</th><th>Created</th><th>Open</th></tr></thead><tbody>{rows}</tbody></table></section>"
    return layout("Calls", "Calls", content)


def render_notifications() -> str:
    with db() as conn:
        notes = get_notifications(conn)
    rows = "".join(
        f"<tr><td>{esc(n['business_name'])}</td><td>{esc(n['customer_name'] or 'Unknown')}</td><td>{esc(title(n['notification_type']))}</td><td>{esc(n['channel'])}</td><td>{esc(n['recipient'])}</td><td>{esc(n['subject'])}</td><td>{status_badge(n['status'])}</td><td><a class='btn' href='/leads/{n['lead_id']}'>Open</a></td></tr>"
        for n in notes
    )
    content = f"<section><h1>Notifications</h1><p class='muted'>Dashboard alerts for human handoff. Email, WhatsApp, SMS, and Slack can be connected later.</p></section><section class='panel table-wrap' style='margin-top:18px;'><table><thead><tr><th>Business</th><th>Lead</th><th>Type</th><th>Channel</th><th>Recipient</th><th>Preview</th><th>Status</th><th>Open</th></tr></thead><tbody>{rows}</tbody></table></section>"
    return layout("Notifications", "Notifications", content)


def env_connected(*keys: str) -> bool:
    return all(bool(os.environ.get(key)) for key in keys)


def render_settings(saved: bool = False) -> str:
    env_rows = [
        ("SQLite", True, "Connected"),
        ("Supabase", env_connected("SUPABASE_URL", "SUPABASE_ANON_KEY"), None),
        ("Mock AI", True, "Active"),
        ("OpenAI", env_connected("OPENAI_API_KEY"), None),
        ("Claude", env_connected("ANTHROPIC_API_KEY"), None),
        ("Vapi", env_connected("VAPI_API_KEY"), None),
        ("Retell", env_connected("RETELL_API_KEY"), None),
        ("Twilio", env_connected("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"), None),
        ("ElevenLabs", env_connected("ELEVENLABS_API_KEY"), None),
        ("Deepgram", env_connected("DEEPGRAM_API_KEY"), None),
        ("Email SMTP", env_connected("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"), None),
        ("Slack", env_connected("SLACK_WEBHOOK_URL"), None),
        ("WhatsApp", env_connected("WHATSAPP_API_KEY"), None),
    ]
    with db() as conn:
        setting_rows = {row["key"]: row["value"] for row in conn.execute("select key, value from settings").fetchall()}
    integration_html = "".join(
        f'<div class="mini"><span>{esc(name)}</span><strong>{integration_badge(connected, label)}</strong></div>'
        for name, connected, label in env_rows
    )
    content = f"""
    <section><h1>Settings</h1><p class="muted">Integration status and demo mode settings.</p>{'<p>'+badge('Saved','status-active')+'</p>' if saved else ''}</section>
    <section class="panel pad" style="margin-top:18px;">
      <h2>App Settings</h2>
      <form method="post" action="/settings/update" class="form-grid" style="margin-top:14px;">
        <label>App name<input name="app_name" value="{esc(setting_rows.get('app_name', APP_NAME))}"></label>
        <label>Theme<input name="theme" value="{esc(setting_rows.get('theme', 'dark premium'))}"></label>
        <label>Demo mode<select name="demo_mode"><option value="true">true</option><option value="false">false</option></select></label>
        <label>Default hot lead threshold<input name="default_hot_lead_threshold" type="number" value="{esc(setting_rows.get('default_hot_lead_threshold', '75'))}"></label>
        <label>Default warm lead threshold<input name="default_warm_lead_threshold" type="number" value="{esc(setting_rows.get('default_warm_lead_threshold', '45'))}"></label>
        <div class="full"><button class="btn primary" type="submit">Save Settings</button></div>
      </form>
    </section>
    <section class="panel pad" style="margin-top:18px;">
      <h2>Connection Status</h2>
      <p class="muted">Some integrations are running in demo mode because API keys are missing.</p>
      <div class="grid three">{integration_html}</div>
    </section>
    """
    return layout("Settings", "Settings", content)


def render_not_found() -> str:
    return layout("Not Found", "", "<section class='panel pad'><h1>Page not found</h1><p><a class='btn primary' href='/'>Go to Dashboard</a></p></section>")


class CallPilotHandler(BaseHTTPRequestHandler):
    server_version = "CallPilotAI/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send_html(self, content: str, status: int = 200) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, indent=2, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_xml(self, content: str, status: int = 200) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def body_bytes(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length else b""

    def form(self) -> dict[str, str]:
        parsed = parse_qs(self.body_bytes().decode("utf-8", errors="replace"), keep_blank_values=True)
        return {key: values[0] if values else "" for key, values in parsed.items()}

    def json_body(self) -> dict[str, Any]:
        raw = self.body_bytes().decode("utf-8", errors="replace")
        return json.loads(raw) if raw.strip() else {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        if path == "/":
            self.send_html(render_dashboard(query))
        elif path == "/businesses":
            self.send_html(render_businesses())
        elif re.fullmatch(r"/businesses/\d+", path):
            self.send_html(render_business_detail(int(path.rsplit("/", 1)[1])))
        elif path == "/agent-builder":
            self.send_html(render_agent_builder(query))
        elif path == "/demo-call":
            self.send_html(render_demo_call(query))
        elif path == "/real-calling":
            self.send_html(render_real_calling(query))
        elif path == "/leads":
            self.send_html(render_leads(query))
        elif re.fullmatch(r"/leads/\d+", path):
            self.send_html(render_lead_detail(int(path.rsplit("/", 1)[1])))
        elif path == "/bookings":
            self.send_html(render_bookings())
        elif path == "/calls":
            self.send_html(render_calls())
        elif path == "/notifications":
            self.send_html(render_notifications())
        elif path == "/settings":
            self.send_html(render_settings(query.get("saved", ["0"])[0] == "1"))
        elif path == "/api/leads":
            with db() as conn:
                self.send_json({"success": True, "leads": get_leads(conn)})
        elif path == "/api/businesses":
            with db() as conn:
                self.send_json({"success": True, "businesses": get_businesses(conn)})
        elif path == "/api/twilio/voice":
            self.handle_twilio_voice(query, {})
        else:
            self.send_html(render_not_found(), 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        if path == "/agent-builder/create":
            business_id = save_agent(self.form())
            self.redirect(f"/businesses/{business_id}")
            return
        update_match = re.fullmatch(r"/agent-builder/(\d+)/update", path)
        if update_match:
            business_id = int(update_match.group(1))
            save_agent(self.form(), business_id)
            self.redirect(f"/businesses/{business_id}")
            return
        if path == "/demo-call/analyze":
            form = self.form()
            business_id = int(form.get("business_id") or 1)
            transcript = form.get("transcript", "")
            with db() as conn:
                business = get_business(conn, business_id)
                if not business:
                    self.redirect("/demo-call")
                    return
                analysis = analyze_call(transcript, business, get_services(conn, business_id), get_knowledge(conn, business_id))
                lead = create_lead_from_analysis(conn, business_id, transcript, analysis, provider="demo")
            self.redirect(f"/leads/{lead['id']}")
            return
        if path == "/real-calling/outbound":
            form = self.form()
            business_id = int(form.get("business_id") or 1)
            ok, msg = create_twilio_outbound_call(form.get("to_number", ""), business_id)
            param = "message" if ok else "error"
            self.redirect(f"/real-calling?business_id={business_id}&{param}={urlencode({'x': msg})[2:]}")
            return
        status_match = re.fullmatch(r"/leads/(\d+)/status", path)
        if status_match:
            lead_id = int(status_match.group(1))
            status = self.form().get("status", "new")
            if status not in {"new", "contacted", "follow_up", "won", "lost"}:
                status = "new"
            with db() as conn:
                conn.execute("update leads set status=?, updated_at=? where id=?", (status, now(), lead_id))
                lead = get_lead(conn, lead_id)
                create_event(conn, lead["business_id"] if lead else None, lead_id, "status_changed", f"Lead status changed to {status}.", {"status": status})
            self.redirect(f"/leads/{lead_id}")
            return
        handoff_match = re.fullmatch(r"/leads/(\d+)/handoff", path)
        if handoff_match:
            lead_id = int(handoff_match.group(1))
            with db() as conn:
                lead = get_lead(conn, lead_id)
                if lead:
                    analysis = {
                        "customer_name": lead["customer_name"],
                        "customer_phone": lead["customer_phone"],
                        "request_type": lead["request_type"],
                        "lead_score": lead["lead_score"],
                        "ai_summary": lead["ai_summary"],
                        "recommended_action": lead["recommended_action"],
                    }
                    create_notification(conn, lead["business_id"], lead_id, analysis)
                    conn.execute("update leads set handoff_triggered=1 where id=?", (lead_id,))
            self.redirect(f"/leads/{lead_id}")
            return
        delete_match = re.fullmatch(r"/leads/(\d+)/delete", path)
        if delete_match:
            lead_id = int(delete_match.group(1))
            with db() as conn:
                conn.execute("delete from leads where id=?", (lead_id,))
            self.redirect("/leads")
            return
        booking_match = re.fullmatch(r"/bookings/(\d+)/status", path)
        if booking_match:
            booking_id = int(booking_match.group(1))
            status = self.form().get("status", "requested")
            with db() as conn:
                conn.execute("update bookings set status=?, updated_at=? where id=?", (status, now(), booking_id))
            self.redirect("/bookings")
            return
        if path == "/settings/update":
            form = self.form()
            with db() as conn:
                for key, value in form.items():
                    conn.execute(
                        """
                        insert into settings (key, value, created_at, updated_at)
                        values (?, ?, ?, ?)
                        on conflict(key) do update set value=excluded.value, updated_at=excluded.updated_at
                        """,
                        (key, value, now(), now()),
                    )
            self.redirect("/settings?saved=1")
            return
        if path == "/api/ai/analyze-call":
            data = self.json_body()
            business_id = int(data.get("business_id") or 1)
            transcript = data.get("transcript", "")
            with db() as conn:
                business = get_business(conn, business_id)
                if not business:
                    self.send_json({"success": False, "error": "Business not found"}, 404)
                    return
                analysis = analyze_call(transcript, business, get_services(conn, business_id), get_knowledge(conn, business_id))
            self.send_json(analysis)
            return
        if path == "/api/voice/webhook":
            data = self.json_body()
            business_id = int(data.get("business_id") or 1)
            transcript = data.get("transcript", "")
            with db() as conn:
                business = get_business(conn, business_id)
                if not business:
                    self.send_json({"success": False, "error": "Business not found"}, 404)
                    return
                analysis = analyze_call(transcript, business, get_services(conn, business_id), get_knowledge(conn, business_id))
                lead = create_lead_from_analysis(
                    conn,
                    business_id,
                    transcript,
                    analysis,
                    provider=data.get("provider", "voice_webhook"),
                    call_id=data.get("call_id"),
                    caller_phone=data.get("caller_phone"),
                    recording_url=data.get("recording_url"),
                )
            self.send_json(
                {
                    "success": True,
                    "lead_id": lead["id"],
                    "lead_score": lead["lead_score"],
                    "lead_temperature": lead["lead_temperature"],
                    "booking_requested": bool(lead["booking_requested"]),
                    "handoff_triggered": bool(lead["handoff_triggered"]),
                }
            )
            return
        if path == "/api/twilio/voice":
            self.handle_twilio_voice(query, self.form())
            return
        if path == "/api/twilio/gather":
            self.handle_twilio_gather(query, self.form())
            return
        self.send_html(render_not_found(), 404)

    def handle_twilio_voice(self, query: dict[str, list[str]], form: dict[str, str]) -> None:
        business_id = int((query.get("business_id") or [form.get("business_id") or "1"])[0] or 1)
        call_sid = form.get("CallSid") or f"manual-test-{datetime.now().timestamp()}"
        caller_phone = form.get("From")
        with db() as conn:
            business = get_business(conn, business_id)
            if not business:
                self.send_xml(twilio_finish_twiml("Sorry, this CallPilot business agent was not found."), 404)
                return
            get_or_create_call_session(conn, business_id, call_sid, caller_phone)
        prompt = (
            f"{business.get('agent_greeting') or 'Hi, thanks for calling.'} "
            "Please tell me what you need. Include your name and best callback number if you can."
        )
        self.send_xml(twilio_gather_twiml(business_id, prompt))

    def handle_twilio_gather(self, query: dict[str, list[str]], form: dict[str, str]) -> None:
        business_id = int((query.get("business_id") or [form.get("business_id") or "1"])[0] or 1)
        call_sid = form.get("CallSid") or f"manual-test-{datetime.now().timestamp()}"
        caller_phone = form.get("From")
        speech = form.get("SpeechResult", "").strip()
        if not speech:
            self.send_xml(twilio_gather_twiml(business_id, "I did not catch that. Please say your request again."))
            return

        with db() as conn:
            business = get_business(conn, business_id)
            if not business:
                self.send_xml(twilio_finish_twiml("Sorry, this CallPilot business agent was not found."), 404)
                return
            session = get_or_create_call_session(conn, business_id, call_sid, caller_phone)
            transcript = (session.get("transcript") or "").strip()
            transcript = (transcript + "\n" if transcript else "") + f"Caller: {speech}"
            turn_count = int(session.get("turn_count") or 0) + 1
            analysis = analyze_call(transcript, business, get_services(conn, business_id), get_knowledge(conn, business_id))
            if not analysis.get("customer_phone") and caller_phone:
                analysis["customer_phone"] = caller_phone
                analysis["score_breakdown"]["contact_detail"] = SCORE_RULES["contact_detail"]
                analysis["lead_score"] = min(100, sum(analysis["score_breakdown"].values()))
                analysis["lead_temperature"] = lead_temperature(analysis["lead_score"])

            if should_finish_twilio_call(analysis, turn_count, speech):
                lead = create_lead_from_analysis(
                    conn,
                    business_id,
                    transcript,
                    analysis,
                    provider="twilio",
                    call_id=call_sid,
                    caller_phone=caller_phone,
                )
                conn.execute(
                    "update call_sessions set transcript=?, turn_count=?, lead_id=?, status='completed', updated_at=? where call_sid=?",
                    (transcript, turn_count, lead["id"], now(), call_sid),
                )
                self.send_xml(
                    twilio_finish_twiml(
                        "Thanks. I have captured your request and sent it to the team. Someone will follow up soon. Goodbye."
                    )
                )
                return

            conn.execute(
                "update call_sessions set transcript=?, turn_count=?, updated_at=? where call_sid=?",
                (transcript, turn_count, now(), call_sid),
            )
            self.send_xml(twilio_gather_twiml(business_id, next_twilio_prompt(analysis, business)))


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    load_dotenv()
    init_db()
    server = ThreadingHTTPServer((host, port), CallPilotHandler)
    print(f"{APP_NAME} running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
