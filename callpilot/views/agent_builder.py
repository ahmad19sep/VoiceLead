from __future__ import annotations

from ..compliance import audit_event, default_workspace_id
from .layout import layout, metric
from ..clinic import (
    default_clinic_profile,
    get_clinic_holidays,
    get_clinic_locations,
    get_clinic_profile,
    get_clinic_providers,
    is_clinic_type,
    save_clinic_setup,
)
from ..config import TONE_OPTIONS, business_types_for_mode
from ..modules import comma, lines, module_by_key, module_for_business_type, module_options
from ..repositories import get_business, get_knowledge, get_services
from ..seed import template_for_business_type
from ..storage import db
from ..utils import esc, now
from ..workflows import create_event


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


def parse_service_lines(text: str) -> list[dict[str, object]]:
    services = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        pieces = [piece.strip() for piece in line.split("|")]
        if pieces[0].lower() == "service name":
            continue
        original_len = len(pieces)
        while len(pieces) < 8:
            pieces.append("")
        if original_len >= 8:
            name, description, duration, provider_name, location_name, price, bookable, emergency = pieces[:8]
        else:
            name, description, price, bookable, emergency = pieces[:5]
            duration, provider_name, location_name = "30", "", ""
        try:
            duration_minutes = int(duration or 30)
        except ValueError:
            duration_minutes = 30
        services.append(
            {
                "name": name,
                "description": description,
                "duration_minutes": max(5, duration_minutes),
                "provider_name": provider_name,
                "location_name": location_name,
                "price_note": price,
                "is_bookable": int(bookable or 1),
                "is_emergency": int(emergency or 0),
            }
        )
    return services

def render_agent_builder(query: dict[str, list[str]]) -> str:
    business_id = int(query.get("business_id", ["0"])[0] or 0)
    with db() as conn:
        business = get_business(conn, business_id) if business_id else None
        services = get_services(conn, business_id) if business_id else []
        clinic_profile = get_clinic_profile(conn, business_id) if business_id and business and is_clinic_type(business["business_type"]) else default_clinic_profile()
        clinic_providers = get_clinic_providers(conn, business_id) if business_id and business and is_clinic_type(business["business_type"]) else []
        clinic_locations = get_clinic_locations(conn, business_id) if business_id and business and is_clinic_type(business["business_type"]) else []
        clinic_holidays = get_clinic_holidays(conn, business_id) if business_id and business and is_clinic_type(business["business_type"]) else []
        knowledge = [
            row
            for row in (get_knowledge(conn, business_id) if business_id else [])
            if (row.get("source") or "agent_builder") in {"agent_builder", "seed_data"}
        ]
    default_type = business_types_for_mode()[0]
    template = template_for_business_type(business["business_type"] if business else default_type)
    business_type_value = business["business_type"] if business else default_type
    module = module_by_key((business or {}).get("module_key")) if business else module_for_business_type(business_type_value)
    type_options = "".join(
        f'<option value="{esc(item)}" {"selected" if item == business_type_value else ""}>{esc(item)}</option>'
        for item in business_types_for_mode()
    )
    module_select = "".join(
        f'<option value="{esc(key)}" {"selected" if key == module["key"] else ""}>{esc(label)}</option>'
        for key, label in module_options()
    )
    tone_value = business["agent_tone"] if business else template["tone"]
    tone_options = "".join(
        f'<option value="{esc(item)}" {"selected" if item == tone_value else ""}>{esc(item)}</option>'
        for item in TONE_OPTIONS
    )
    services_text = "\n".join(
        f"{s['name']} | {s['description']} | {s['duration_minutes'] or 30} | {s['provider_name'] or ''} | {s['location_name'] or ''} | {s['price_note'] or ''} | {s['is_bookable']} | {s['is_emergency']}"
        for s in services
    ) or "Service name | Description | Duration minutes | Provider | Location | Price note | 1 | 0"
    provider_text = "\n".join(
        f"{row['name']} | {row['role'] or ''} | {row['specialty'] or ''} | {row['languages'] or ''} | {row['location_name'] or ''} | {row['working_hours'] or ''}"
        for row in clinic_providers
    ) or "Name | Role | Specialty | Languages | Location | Working hours"
    location_text = "\n".join(
        f"{row['name']} | {row['address'] or ''} | {row['phone'] or ''} | {row['timezone'] or ''} | {row['working_hours'] or ''}"
        for row in clinic_locations
    ) or "Name | Address | Phone | Timezone | Working hours"
    holiday_text = "\n".join(
        f"{row['holiday_type']} | {row['name']} | {row['date_value'] or row['weekday'] or ''} | {row['start_time'] or ''} | {row['end_time'] or ''} | {row['closed_all_day']}"
        for row in clinic_holidays
    ) or "date | Eid closure | 2026-03-20 |  |  | 1\nweekly | Friday half-day | friday | 13:00 | 15:00 | 0"
    faq_text = "\n".join(f"{k['question']} | {k['answer']} | {k['category'] or ''}" for k in knowledge) or (
        "Question | Answer | Category"
    )
    action = f"/agent-builder/{business_id}/update" if business else "/agent-builder/create"
    intake_fields = (business or {}).get("intake_fields") or lines(module["intake_fields"])
    allowed_call_types = (business or {}).get("allowed_call_types") or lines(module["allowed_call_types"])
    blocked_outcomes = (business or {}).get("blocked_outcomes") or lines(module["blocked_outcomes"])
    supported_languages = (business or {}).get("supported_languages") or module["language_policy"]
    compliance_profile = (business or {}).get("compliance_profile") or module["compliance_profile"]
    consent_policy = (business or {}).get("consent_policy") or "Outbound calls require consent, opt-out handling, and client policy approval."
    recording_disclosure = (business or {}).get("recording_disclosure") or "Disclose recording when enabled by the client and required by region."
    quiet_hours = (business or {}).get("quiet_hours") or "09:00-18:00 local time unless the client policy says otherwise."
    max_outbound_attempts = (business or {}).get("max_outbound_attempts")
    if max_outbound_attempts is None:
        max_outbound_attempts = 0 if business_type_value in {"Clinic", "Law Firm"} else 2
    integration_targets = (business or {}).get("integration_targets") or module["integration_targets"]
    qa_checks = (business or {}).get("qa_checks") or comma(module["qa_checks"])
    workflow_version = (business or {}).get("workflow_version") or "v1"
    content = f"""
    <section class="row">
      <div>
        <h1>Agent Builder</h1>
        <p class="muted">Create a flexible AI phone agent for any business.</p>
      </div>
      <div class="actions">
        <a class="btn" href="/businesses">Agents</a>
        {'<a class="btn primary" href="/demo-call?business_id='+str(business_id)+'">Test Call</a>' if business else ''}
      </div>
    </section>
    <section class="grid metrics">
      {metric('Mode', 'Edit' if business else 'Create', 'good' if business else '')}
      {metric('Module', module['label'])}
      {metric('Services', len(services))}
      {metric('Knowledge Items', len(knowledge))}
    </section>
    <section class="callout" style="margin-top:18px;">
      <div class="row">
        <div>
          <div class="kicker" style="color:rgba(255,255,255,.7);">Production guardrails</div>
          <h2 style="margin-top:6px;">Configure the workflow before the voice goes live.</h2>
          <p class="muted" style="margin-bottom:0;">Allowed call types, blocked outcomes, consent rules, QA checks, and handoff paths are saved with each business agent.</p>
        </div>
      </div>
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
      <h2 style="margin-top:22px;">Production Module Configuration</h2>
      <div class="form-grid" style="margin-top:14px;">
        <label>Industry module<select name="module_key">{module_select}</select></label>
        <label>Workflow version<input name="workflow_version" value="{esc(workflow_version)}"></label>
        <label class="full">Intake fields<textarea name="intake_fields">{esc(intake_fields)}</textarea></label>
        <label class="full">Allowed call types<textarea name="allowed_call_types">{esc(allowed_call_types)}</textarea></label>
        <label class="full">Blocked outcomes<textarea name="blocked_outcomes">{esc(blocked_outcomes)}</textarea></label>
        <label>Supported languages<input name="supported_languages" value="{esc(supported_languages)}"></label>
        <label>Quiet hours<input name="quiet_hours" value="{esc(quiet_hours)}"></label>
        <label>Max outbound attempts<input type="number" name="max_outbound_attempts" value="{esc(max_outbound_attempts)}"></label>
        <label class="full">Compliance profile<textarea name="compliance_profile">{esc(compliance_profile)}</textarea></label>
        <label class="full">Consent policy<textarea name="consent_policy">{esc(consent_policy)}</textarea></label>
        <label class="full">Recording disclosure<textarea name="recording_disclosure">{esc(recording_disclosure)}</textarea></label>
        <label class="full">Integration targets<textarea name="integration_targets">{esc(integration_targets)}</textarea></label>
        <label class="full">QA checks<input name="qa_checks" value="{esc(qa_checks)}"></label>
      </div>
      <h2 style="margin-top:22px;">Services</h2>
      <p class="muted">One per line: service name | description | duration minutes | provider | location | price note | is bookable 1/0 | is emergency 1/0</p>
      <textarea name="services">{esc(services_text)}</textarea>
      <h2 style="margin-top:22px;">Clinic Profile</h2>
      <p class="muted">Internal operator setup for C1 clinic onboarding. Applies to Clinic, Hospital, and Dentist businesses.</p>
      <div class="form-grid" style="margin-top:14px;">
        <label>Timezone<select name="clinic_timezone">
          <option value="Asia/Karachi" {"selected" if clinic_profile.get("timezone") == "Asia/Karachi" else ""}>Asia/Karachi</option>
          <option value="Asia/Dubai" {"selected" if clinic_profile.get("timezone") == "Asia/Dubai" else ""}>Asia/Dubai</option>
        </select></label>
        <label>Supported languages<input name="clinic_supported_languages" value="{esc(clinic_profile.get('supported_languages') or 'en,ur')}"></label>
        <label>Default language<input name="clinic_default_language" value="{esc(clinic_profile.get('default_language') or 'ur')}"></label>
        <label>Cancellation window hours<input type="number" name="clinic_cancellation_window_hours" value="{esc(clinic_profile.get('cancellation_window_hours') or 24)}"></label>
        <label>Reminder offset hours<input type="number" name="clinic_reminder_offset_hours" value="{esc(clinic_profile.get('reminder_offset_hours') or 24)}"></label>
        <label>Recording disclosure<select name="clinic_recording_disclosure_enabled">
          <option value="1" {"selected" if clinic_profile.get("recording_disclosure_enabled", 1) else ""}>On</option>
          <option value="0" {"selected" if not clinic_profile.get("recording_disclosure_enabled", 1) else ""}>Off</option>
        </select></label>
        <label>Appointment reminders<select name="clinic_reminders_enabled">
          <option value="0" {"selected" if not clinic_profile.get("reminders_enabled") else ""}>Off</option>
          <option value="1" {"selected" if clinic_profile.get("reminders_enabled") else ""}>On</option>
        </select></label>
        <label class="full">Insurance accepted<textarea name="clinic_insurance_accepted">{esc(clinic_profile.get('insurance_accepted') or '')}</textarea></label>
        <label class="full">After-hours policy<textarea name="clinic_after_hours_policy">{esc(clinic_profile.get('after_hours_policy') or '')}</textarea></label>
        <label class="full">Emergency policy<textarea name="clinic_emergency_policy">{esc(clinic_profile.get('emergency_policy') or '')}</textarea></label>
      </div>
      <h2 style="margin-top:22px;">Providers / Doctors</h2>
      <p class="muted">One per line: name | role | specialty | languages | location | working hours</p>
      <textarea name="clinic_providers">{esc(provider_text)}</textarea>
      <h2 style="margin-top:22px;">Locations</h2>
      <p class="muted">One per line: name | address | phone | timezone | working hours</p>
      <textarea name="clinic_locations">{esc(location_text)}</textarea>
      <h2 style="margin-top:22px;">Holidays / Closures</h2>
      <p class="muted">One per line: date/weekly | name | date or weekday | start | end | closed all day 1/0</p>
      <textarea name="clinic_holidays">{esc(holiday_text)}</textarea>
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
        workspace_id = default_workspace_id(conn)
        if business_id:
            row = conn.execute(
                "select workspace_id from businesses where id = ? and workspace_id = ?",
                (business_id, workspace_id),
            ).fetchone()
            if not row:
                raise ValueError("Business not found in the active workspace.")
            conn.execute(
                """
                update businesses set name=?, business_type=?, description=?, phone=?, email=?, website=?, location=?,
                working_hours=?, agent_name=?, agent_greeting=?, agent_tone=?, fallback_message=?,
                hot_lead_threshold=?, warm_lead_threshold=?, module_key=?, intake_fields=?,
                allowed_call_types=?, blocked_outcomes=?, supported_languages=?, compliance_profile=?,
                consent_policy=?, recording_disclosure=?, quiet_hours=?, max_outbound_attempts=?,
                integration_targets=?, qa_checks=?, workflow_version=?, handoff_name=?, handoff_phone=?,
                handoff_email=?, handoff_instructions=?, updated_at=? where id=? and workspace_id=?
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
                    form.get("module_key"),
                    form.get("intake_fields"),
                    form.get("allowed_call_types"),
                    form.get("blocked_outcomes"),
                    form.get("supported_languages"),
                    form.get("compliance_profile"),
                    form.get("consent_policy"),
                    form.get("recording_disclosure"),
                    form.get("quiet_hours"),
                    int(form.get("max_outbound_attempts") or 0),
                    form.get("integration_targets"),
                    form.get("qa_checks"),
                    form.get("workflow_version") or "v1",
                    form.get("handoff_name"),
                    form.get("handoff_phone"),
                    form.get("handoff_email"),
                    form.get("handoff_instructions"),
                    now(),
                    business_id,
                    workspace_id,
                ),
            )
            conn.execute("delete from services where business_id=?", (business_id,))
            conn.execute(
                """
                delete from knowledge_base
                where business_id=? and coalesce(source, 'agent_builder') in ('agent_builder', 'seed_data')
                """,
                (business_id,),
            )
            conn.execute(
                "delete from knowledge_documents where business_id=? and source_type in ('agent_builder', 'seed')",
                (business_id,),
            )
        else:
            business_id = int(
                conn.execute(
                    """
                    insert into businesses (
                        workspace_id, name, business_type, description, phone, email, website, location, working_hours,
                        agent_name, agent_greeting, agent_tone, fallback_message, hot_lead_threshold,
                        warm_lead_threshold, module_key, intake_fields, allowed_call_types, blocked_outcomes,
                        supported_languages, compliance_profile, consent_policy, recording_disclosure, quiet_hours,
                        max_outbound_attempts, integration_targets, qa_checks, workflow_version, handoff_name,
                        handoff_phone, handoff_email, handoff_instructions, status, created_at, updated_at
                    )
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (
                        workspace_id,
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
                        form.get("module_key"),
                        form.get("intake_fields"),
                        form.get("allowed_call_types"),
                        form.get("blocked_outcomes"),
                        form.get("supported_languages"),
                        form.get("compliance_profile"),
                        form.get("consent_policy"),
                        form.get("recording_disclosure"),
                        form.get("quiet_hours"),
                        int(form.get("max_outbound_attempts") or 0),
                        form.get("integration_targets"),
                        form.get("qa_checks"),
                        form.get("workflow_version") or "v1",
                        form.get("handoff_name"),
                        form.get("handoff_phone"),
                        form.get("handoff_email"),
                        form.get("handoff_instructions"),
                        now(),
                        now(),
                    ),
                ).lastrowid
            )
        conn.execute(
            """
            delete from staff_contacts
            where business_id = ? and role = 'Handoff contact'
            """,
            (business_id,),
        )
        if form.get("handoff_name") or form.get("handoff_phone") or form.get("handoff_email"):
            conn.execute(
                """
                insert into staff_contacts (
                    workspace_id, business_id, name, role, phone, email, escalation_level,
                    receives_handoff, created_at, updated_at
                )
                values (?, ?, ?, 'Handoff contact', ?, ?, 1, 1, ?, ?)
                """,
                (
                    workspace_id,
                    business_id,
                    form.get("handoff_name") or "Handoff Contact",
                    form.get("handoff_phone"),
                    form.get("handoff_email"),
                    now(),
                    now(),
                ),
            )
        for service in parse_service_lines(form.get("services", "")):
            if not service["name"]:
                continue
            conn.execute(
                """
                insert into services (
                    business_id, name, description, price_note, duration_minutes,
                    provider_name, location_name, is_bookable, is_emergency
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    business_id,
                    service["name"],
                    service["description"],
                    service["price_note"],
                    service["duration_minutes"],
                    service["provider_name"],
                    service["location_name"],
                    service["is_bookable"],
                    service["is_emergency"],
                ),
            )
        if is_clinic_type(form.get("business_type")):
            save_clinic_setup(conn, workspace_id, business_id, form)
        faq_rows = [
            (question, answer, category)
            for question, answer, category in parse_lines(form.get("faqs", ""), 3)
            if question.lower() != "question" and question
        ]
        document_id = None
        if faq_rows:
            document_id = conn.execute(
                """
                insert into knowledge_documents (
                    workspace_id, business_id, title, source_type, source, version, status,
                    item_count, approved_by, approved_at, created_at, updated_at
                )
                values (?, ?, 'Agent Builder FAQs', 'agent_builder', 'agent_builder', 1, 'approved', ?, 'operator', ?, ?, ?)
                """,
                (workspace_id, business_id, len(faq_rows), now(), now(), now()),
            ).lastrowid
        for question, answer, category in faq_rows:
            if question.lower() == "question" or not question:
                continue
            conn.execute(
                """
                insert into knowledge_base (
                    business_id, document_id, question, answer, category, tags, source,
                    language, translation_group_id, version, status, approved_at, updated_at, created_at
                )
                values (?, ?, ?, ?, ?, ?, 'agent_builder', 'en', ?, 1, 'approved', ?, ?, ?)
                """,
                (business_id, document_id, question, answer, category, category.lower(), category.lower(), now(), now(), now()),
            )
        create_event(conn, business_id, None, "agent_saved", "Business agent saved from Agent Builder.", {})
        audit_event(conn, workspace_id, "operator", "agent_saved", "business", business_id, {"business_type": form.get("business_type")})
        return business_id
