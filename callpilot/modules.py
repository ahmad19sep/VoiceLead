from __future__ import annotations

from typing import Any

from .config import clinic_mode


DEFAULT_LANGUAGES = "English, Urdu, Roman Urdu/Hindi"
DEFAULT_CALL_TYPES = "Inbound FAQ, lead capture, booking request, human handoff"
DEFAULT_BLOCKED_OUTCOMES = "No confirmed booking without staff or calendar confirmation; no unsupported advice"


INDUSTRY_MODULES: dict[str, dict[str, Any]] = {
    "healthcare": {
        "status": "active",
        "label": "Healthcare Clinics Hospitals Dentists",
        "business_types": ["Clinic", "Hospital", "Dentist"],
        "intake_fields": [
            "Patient name",
            "Phone",
            "Appointment reason",
            "Preferred date/time",
            "New or existing patient",
            "Insurance/payment note",
            "Urgency",
        ],
        "allowed_call_types": [
            "Book, reschedule, cancel, and remind for appointments",
            "Collect administrative intake",
            "Answer approved clinic FAQs",
            "Route urgent calls to staff",
        ],
        "blocked_outcomes": [
            "No diagnosis, prescribing, treatment advice, or clinical triage",
            "No repeated follow-up calls unless clinic policy and consent allow it",
        ],
        "compliance_profile": "HIPAA/PHI aware, emergency escalation, identity verification, approved FAQ only",
        "language_policy": "English, Urdu, Roman Urdu/Hindi; handoff unsupported languages",
        "integration_targets": "Calendar/EHR, SMS reminders, staff handoff, consent records",
        "qa_checks": [
            "Medical advice refusal",
            "Urgent symptom handoff",
            "No appointment confirmation without availability",
        ],
    },
    "hospitality": {
        "status": "deferred",
        "label": "Hotels And Hospitality",
        "business_types": ["Hotel"],
        "intake_fields": ["Guest name", "Phone", "Check-in", "Check-out", "Guests", "Room type", "Budget", "Special request"],
        "allowed_call_types": [
            "Reservation requests",
            "Amenity and policy FAQs",
            "Directions and guest requests",
            "Room-service/front-desk routing",
        ],
        "blocked_outcomes": ["No guaranteed rate or availability without PMS/staff confirmation"],
        "compliance_profile": "Booking policy, guest verification, payment safety, escalation contacts",
        "language_policy": DEFAULT_LANGUAGES,
        "integration_targets": "PMS, calendar/availability, payment link, front desk handoff",
        "qa_checks": ["Cancellation policy accuracy", "Availability not hallucinated", "Guest request routing"],
    },
    "restaurant": {
        "status": "deferred",
        "label": "Restaurants And Food Ordering",
        "business_types": ["Restaurant"],
        "intake_fields": ["Customer name", "Phone", "Date", "Time", "Party size", "Order items", "Allergy note", "Pickup/delivery"],
        "allowed_call_types": [
            "Table reservations",
            "Menu and hours FAQs",
            "Order intake or order-link routing",
            "Catering leads and complaints",
        ],
        "blocked_outcomes": ["No allergy guarantees; no order placement unless POS mode is enabled"],
        "compliance_profile": "Allergen disclaimer, POS permissions, manager escalation, peak overflow",
        "language_policy": DEFAULT_LANGUAGES,
        "integration_targets": "POS, menu source, delivery zones, manager handoff",
        "qa_checks": ["Allergen disclaimer", "Modifier capture", "Busy-hour escalation"],
    },
    "support": {
        "status": "deferred",
        "label": "Call Centers And Customer Support",
        "business_types": ["Call Center", "Customer Support"],
        "intake_fields": ["Customer name", "Phone", "Account identifier", "Issue category", "Verification fields", "Priority"],
        "allowed_call_types": ["First-line support", "Ticket creation", "FAQ resolution", "Account/order lookup", "Escalation routing"],
        "blocked_outcomes": ["No refunds, warranty approvals, or account changes without verified policy/tool permission"],
        "compliance_profile": "Verification rules, SLA routing, audit events, policy-specific knowledge",
        "language_policy": DEFAULT_LANGUAGES,
        "integration_targets": "Zendesk/Freshdesk/CRM, order lookup, queue routing, status webhooks",
        "qa_checks": ["No account action before verification", "SLA escalation", "Policy version accuracy"],
    },
    "sales": {
        "status": "deferred",
        "label": "Lead Generation Sales And Product Caller",
        "business_types": ["Lead Generation", "Sales", "Software Agency"],
        "intake_fields": ["Name", "Company", "Need", "Budget", "Timeline", "Email", "Phone", "Consent source"],
        "allowed_call_types": ["Qualification", "Objection handling", "Appointment setting", "CRM pipeline updates"],
        "blocked_outcomes": ["No outbound call without consent, quiet-hour, DNC, opt-out, and max-attempt checks"],
        "compliance_profile": "TCPA/TSR/DNC aware, consent proof, opt-out enforcement, quiet hours",
        "language_policy": DEFAULT_LANGUAGES,
        "integration_targets": "CRM, calendar, product catalog, campaign dialer, opt-out list",
        "qa_checks": ["Opt-out suppression", "Max attempts", "No misleading pricing claims"],
    },
    "home_services": {
        "status": "deferred",
        "label": "Home Services And Field Service",
        "business_types": ["Home Services"],
        "intake_fields": ["Name", "Phone", "Service", "Location", "Problem description", "Urgency", "Access notes"],
        "allowed_call_types": ["Service inquiries", "Quote/estimate routing", "Technician dispatch", "Job scheduling", "Reminders"],
        "blocked_outcomes": ["No exact price or arrival guarantee unless dispatch integration confirms it"],
        "compliance_profile": "Emergency definitions, service areas, dispatch handoff, warranty policy",
        "language_policy": DEFAULT_LANGUAGES,
        "integration_targets": "Technician calendar, field-service CRM, dispatch status, SMS",
        "qa_checks": ["Emergency routing", "Service-area detection", "No exact quote hallucination"],
    },
    "regulated_services": {
        "status": "deferred",
        "label": "Legal Insurance And Finance",
        "business_types": ["Law Firm", "Legal", "Insurance", "Finance"],
        "intake_fields": ["Name", "Phone", "Matter type", "Short description", "Urgency", "Preferred time", "Documents needed"],
        "allowed_call_types": ["Administrative intake", "Consultation scheduling", "Document collection", "Licensed staff routing"],
        "blocked_outcomes": ["No legal, financial, tax, coverage, or licensed advice without approved staff policy"],
        "compliance_profile": "Strict advice guardrails, conflict/check routing, disclaimers, audit trail",
        "language_policy": DEFAULT_LANGUAGES,
        "integration_targets": "CRM/case system, calendar, secure document intake, handoff",
        "qa_checks": ["Advice refusal", "Conflict-check fields", "Disclaimers present"],
    },
    "real_estate": {
        "status": "deferred",
        "label": "Real Estate And Property Management",
        "business_types": ["Real Estate", "Property Management"],
        "intake_fields": ["Name", "Phone", "Buyer/seller/renter type", "Property/listing", "Budget", "Timeline", "Showing time"],
        "allowed_call_types": ["Listing FAQs", "Showing requests", "Lead qualification", "Maintenance routing", "Rent/payment routing"],
        "blocked_outcomes": ["No discriminatory questions or statements; no guaranteed availability without source data"],
        "compliance_profile": "Fair-housing language, maintenance emergency policy, agent/property manager handoff",
        "language_policy": DEFAULT_LANGUAGES,
        "integration_targets": "MLS/website source, CRM, showing calendar, property management system",
        "qa_checks": ["Fair-housing compliance", "Showing confirmation checks", "Maintenance emergency routing"],
    },
    "commerce": {
        "status": "deferred",
        "label": "Ecommerce Retail Automotive And Logistics",
        "business_types": ["Ecommerce", "Retail", "Automotive", "Logistics"],
        "intake_fields": ["Name", "Phone", "Order/product/vehicle", "Store/location", "Issue", "Preferred appointment", "Delivery status"],
        "allowed_call_types": ["Product questions", "Order status", "Returns", "Appointments", "Inventory checks", "Delivery follow-up"],
        "blocked_outcomes": ["No order placement, return approval, or inventory promise unless connected system confirms it"],
        "compliance_profile": "Return/warranty policy, payment safety, dispatch escalation, consent for follow-up",
        "language_policy": DEFAULT_LANGUAGES,
        "integration_targets": "Catalog/inventory, order system, CRM, service calendar, dispatch status",
        "qa_checks": ["No stale inventory claims", "Return policy accuracy", "Payment data safety"],
    },
    "admin_services": {
        "status": "deferred",
        "label": "Education Recruiting Travel Government",
        "business_types": ["Education", "Recruiting", "Travel", "Government"],
        "intake_fields": ["Name", "Phone", "Program/job/package/service", "Eligibility facts", "Documents", "Preferred appointment"],
        "allowed_call_types": ["Administrative FAQs", "Appointments", "Document checklists", "Recruiting screens", "Travel booking intake"],
        "blocked_outcomes": ["No eligibility guarantee, hiring decision, visa/legal advice, or public-benefit determination"],
        "compliance_profile": "Approved language, accessibility routing, department escalation, retention policy",
        "language_policy": DEFAULT_LANGUAGES,
        "integration_targets": "CRM/ATS/travel system, calendars, document checklist, department queues",
        "qa_checks": ["Eligibility disclaimer", "Department routing", "Document checklist accuracy"],
    },
    "custom": {
        "status": "deferred",
        "label": "Custom Universal Module",
        "business_types": ["Custom"],
        "intake_fields": ["Name", "Phone", "Email", "Request", "Timeline", "Notes"],
        "allowed_call_types": [DEFAULT_CALL_TYPES],
        "blocked_outcomes": [DEFAULT_BLOCKED_OUTCOMES],
        "compliance_profile": "Client-approved FAQ, human handoff, no unsupported commitments",
        "language_policy": DEFAULT_LANGUAGES,
        "integration_targets": "CRM, calendar, notifications, knowledge base",
        "qa_checks": ["Unsupported request handoff", "Missing data clarification", "No fake success states"],
    },
}


def visible_modules() -> dict[str, dict[str, Any]]:
    if not clinic_mode():
        return INDUSTRY_MODULES
    return {key: module for key, module in INDUSTRY_MODULES.items() if module.get("status") == "active"}


def module_for_business_type(business_type: str | None) -> dict[str, Any]:
    for key, module in INDUSTRY_MODULES.items():
        if business_type in module["business_types"]:
            return {"key": key, **module}
    return {"key": "custom", **INDUSTRY_MODULES["custom"]}


def module_by_key(module_key: str | None) -> dict[str, Any]:
    modules = visible_modules()
    if module_key in modules:
        return {"key": module_key, **modules[module_key]}
    return {"key": "custom", **INDUSTRY_MODULES["custom"]}


def module_options() -> list[tuple[str, str]]:
    return [(key, module["label"]) for key, module in visible_modules().items()]


def lines(values: list[str] | str | None) -> str:
    if not values:
        return ""
    if isinstance(values, str):
        return values
    return "\n".join(values)


def comma(values: list[str] | str | None) -> str:
    if not values:
        return ""
    if isinstance(values, str):
        return values
    return ", ".join(values)
