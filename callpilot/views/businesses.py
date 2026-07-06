from __future__ import annotations

from .errors import render_not_found
from .layout import layout
from ..clinic import get_clinic_holidays, get_clinic_locations, get_clinic_profile, get_clinic_providers, is_clinic_type
from ..knowledge import knowledge_stats
from ..repositories import get_business, get_businesses, get_knowledge, get_leads, get_services
from ..storage import db
from ..ui import badge, status_badge, temp_badge
from ..voice_prompt import build_vapi_prompt
from ..utils import esc, title


def business_counts(conn, business_id: int) -> dict[str, int]:
    lead_count = int(conn.execute("select count(*) from leads where business_id = ?", (business_id,)).fetchone()[0])
    hot_count = int(
        conn.execute(
            "select count(*) from leads where business_id = ? and lead_temperature = 'hot'",
            (business_id,),
        ).fetchone()[0]
    )
    booking_count = int(conn.execute("select count(*) from bookings where business_id = ?", (business_id,)).fetchone()[0])
    call_count = int(conn.execute("select count(*) from call_logs where business_id = ?", (business_id,)).fetchone()[0])
    return {"leads": lead_count, "hot": hot_count, "bookings": booking_count, "calls": call_count}


def render_businesses() -> str:
    with db() as conn:
        businesses = get_businesses(conn)
        cards = []
        for business in businesses:
            counts = business_counts(conn, int(business["id"]))
            initial = (business["name"] or "A")[:1].upper()
            cards.append(
                f"""
                <article class="panel pad entity-card">
                  <div class="entity-head">
                    <div class="entity-title">
                      <span class="avatar">{esc(initial)}</span>
                      <div style="min-width:0;">
                        <div class="kicker">{esc(business['business_type'])}</div>
                        <h2>{esc(business['name'])}</h2>
                        <p class="muted" style="margin:4px 0 0;">{esc(business['agent_name'])}</p>
                      </div>
                    </div>
                    {status_badge(business['status'])}
                  </div>
                  <div class="grid three">
                    <div class="mini"><span>Leads</span><strong>{counts['leads']}</strong></div>
                    <div class="mini"><span>Hot</span><strong>{counts['hot']}</strong></div>
                    <div class="mini"><span>Calls</span><strong>{counts['calls']}</strong></div>
                  </div>
                  <div class="mini"><span>Bookings</span><strong>{counts['bookings']}</strong></div>
                  <div class="actions" style="margin-top:auto;">
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
        k_stats = knowledge_stats(conn, business_id)
        leads = get_leads(conn, {"business_id": str(business_id)})[:5]
        clinic_profile = get_clinic_profile(conn, business_id) if is_clinic_type(business["business_type"]) else None
        clinic_providers = get_clinic_providers(conn, business_id) if clinic_profile else []
        clinic_locations = get_clinic_locations(conn, business_id) if clinic_profile else []
        clinic_holidays = get_clinic_holidays(conn, business_id) if clinic_profile else []
        vapi_prompt = build_vapi_prompt(conn, business_id) if clinic_profile else None
    production_items = [
        ("Module", title(business.get("module_key") or "custom")),
        ("Workflow", business.get("workflow_version") or "v1"),
        ("Languages", business.get("supported_languages") or "Not configured"),
        ("Compliance", business.get("compliance_profile") or "Not configured"),
        ("Consent", business.get("consent_policy") or "Not configured"),
        ("Quiet Hours", business.get("quiet_hours") or "Not configured"),
        ("Max Attempts", business.get("max_outbound_attempts") if business.get("max_outbound_attempts") is not None else "Not configured"),
        ("Integrations", business.get("integration_targets") or "Not configured"),
        ("Knowledge Docs", k_stats["documents"]),
    ]
    production_html = "".join(
        f'<div class="mini"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>' for label, value in production_items
    )
    blocked = [line.strip() for line in (business.get("blocked_outcomes") or "").splitlines() if line.strip()]
    allowed = [line.strip() for line in (business.get("allowed_call_types") or "").splitlines() if line.strip()]
    guardrail_html = "".join(f"<li>{esc(item)}</li>" for item in blocked) or "<li>No blocked outcomes configured.</li>"
    allowed_html = "".join(f"<li>{esc(item)}</li>" for item in allowed) or "<li>No allowed call types configured.</li>"
    services_html = "".join(
        f'<div class="mini"><span>{esc(s["name"])}</span><strong>{esc(s["description"])}</strong><p class="muted">{esc(s["duration_minutes"] or 30)} min - {esc(s["provider_name"] or "Any provider")} - {esc(s["location_name"] or "Any location")}</p><p class="muted">{esc(s["price_note"])}</p></div>'
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
    clinic_html = ""
    if clinic_profile:
        clinic_items = [
            ("Timezone", clinic_profile.get("timezone")),
            ("Languages", clinic_profile.get("supported_languages")),
            ("Default Language", clinic_profile.get("default_language")),
            ("Cancellation Window", str(clinic_profile.get("cancellation_window_hours")) + " hours"),
            ("Recording Disclosure", "On" if clinic_profile.get("recording_disclosure_enabled") else "Off"),
            ("Reminders", "On" if clinic_profile.get("reminders_enabled") else "Off"),
            ("Reminder Offset", str(clinic_profile.get("reminder_offset_hours")) + " hours"),
        ]
        clinic_mini = "".join(
            f'<div class="mini"><span>{esc(label)}</span><strong>{esc(value)}</strong></div>' for label, value in clinic_items
        )
        provider_rows = "".join(
            f"<tr><td><strong>{esc(row['name'])}</strong></td><td>{esc(row['role'] or '')}</td><td>{esc(row['specialty'] or '')}</td><td>{esc(row['languages'] or '')}</td><td>{esc(row['location_name'] or '')}</td><td>{esc(row['working_hours'] or '')}</td></tr>"
            for row in clinic_providers
        )
        location_rows = "".join(
            f"<tr><td><strong>{esc(row['name'])}</strong></td><td>{esc(row['address'] or '')}</td><td>{esc(row['phone'] or '')}</td><td>{esc(row['timezone'] or '')}</td><td>{esc(row['working_hours'] or '')}</td></tr>"
            for row in clinic_locations
        )
        holiday_rows = "".join(
            f"<tr><td>{esc(row['holiday_type'])}</td><td><strong>{esc(row['name'])}</strong></td><td>{esc(row['date_value'] or row['weekday'] or '')}</td><td>{esc(row['start_time'] or '')}</td><td>{esc(row['end_time'] or '')}</td><td>{'Yes' if row['closed_all_day'] else 'No'}</td></tr>"
            for row in clinic_holidays
        )
        clinic_html = f"""
        <section class="panel pad" style="margin-top:18px;">
          <div class="row"><h2>Clinic Profile</h2>{badge('C1 Clinic Intake', 'status-active')}</div>
          <div class="grid four" style="margin-top:14px;">{clinic_mini}</div>
          <div class="grid two" style="margin-top:14px;">
            <div class="mini"><span>Insurance Accepted</span><strong>{esc(clinic_profile.get('insurance_accepted') or 'Not configured')}</strong></div>
            <div class="mini"><span>After Hours Policy</span><strong>{esc(clinic_profile.get('after_hours_policy') or 'Not configured')}</strong></div>
          </div>
          <div class="mini" style="margin-top:14px;"><span>Emergency Policy</span><strong>{esc(clinic_profile.get('emergency_policy') or 'Not configured')}</strong></div>
        </section>
        <section class="panel pad" style="margin-top:18px;">
          <div class="row"><h2>Voice Agent Prompt</h2>{badge('Paste into Vapi', 'status-demo')}</div>
          <p class="muted">Generated from this clinic's Agent Builder settings (languages, hours, services). Urdu output is Roman Urdu. Re-save the agent to refresh it. Setup steps: docs/VAPI_SETUP.md.</p>
          <div class="mini" style="margin-top:12px;"><span>First Message</span></div>
          <pre>{esc(vapi_prompt['first_message']) if vapi_prompt else ''}</pre>
          <div class="mini" style="margin-top:12px;"><span>System Prompt</span></div>
          <pre>{esc(vapi_prompt['system_prompt']) if vapi_prompt else ''}</pre>
        </section>
        <section class="panel table-wrap" style="margin-top:18px;">
          <div class="pad"><h2>Providers / Doctors</h2></div>
          <table><thead><tr><th>Name</th><th>Role</th><th>Specialty</th><th>Languages</th><th>Location</th><th>Hours</th></tr></thead><tbody>{provider_rows or '<tr><td colspan="6">No providers configured.</td></tr>'}</tbody></table>
        </section>
        <section class="grid two" style="margin-top:18px;">
          <div class="panel table-wrap">
            <div class="pad"><h2>Locations</h2></div>
            <table><thead><tr><th>Name</th><th>Address</th><th>Phone</th><th>Timezone</th><th>Hours</th></tr></thead><tbody>{location_rows or '<tr><td colspan="5">No locations configured.</td></tr>'}</tbody></table>
          </div>
          <div class="panel table-wrap">
            <div class="pad"><h2>Holidays / Closures</h2></div>
            <table><thead><tr><th>Type</th><th>Name</th><th>Date/Day</th><th>Start</th><th>End</th><th>Closed</th></tr></thead><tbody>{holiday_rows or '<tr><td colspan="6">No closures configured.</td></tr>'}</tbody></table>
          </div>
        </section>
        """
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
        <a class="btn" href="/knowledge?business_id={business_id}">Manage Knowledge</a>
        <a class="btn" href="/api/businesses/{business_id}/readiness">Readiness JSON</a>
      </div>
    </section>
    <section class="panel pad" style="margin-top:18px;">
      <div class="row"><h2>Production Configuration</h2>{badge('PDF Pack Aligned', 'status-active')}</div>
      <div class="grid four" style="margin-top:14px;">{production_html}</div>
    </section>
    <section class="grid two" style="margin-top:18px;">
      <div class="panel pad"><h2>Allowed Workflows</h2><ul>{allowed_html}</ul></div>
      <div class="panel pad"><h2>Blocked Outcomes</h2><ul>{guardrail_html}</ul></div>
    </section>
    {clinic_html}
    <section class="grid two" style="margin-top:18px;">
      <div class="panel pad"><h2>Services</h2><div class="grid three" style="margin-top:14px;">{services_html}</div></div>
      <div class="panel"><div class="pad"><h2>Knowledge Base / FAQs</h2></div><div class="list">{faq_html}</div></div>
    </section>
    <section class="panel" style="margin-top:18px;"><div class="pad"><h2>Recent Leads</h2></div><div class="list">{lead_html}</div></section>
    """
    return layout(business["name"], "Businesses", content)
