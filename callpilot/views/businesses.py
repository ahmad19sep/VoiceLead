from __future__ import annotations

from .errors import render_not_found
from .layout import layout
from ..knowledge import knowledge_stats
from ..repositories import get_business, get_businesses, get_knowledge, get_leads, get_services
from ..stats import stats
from ..storage import db
from ..ui import badge, status_badge, temp_badge
from ..utils import esc, title


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
        k_stats = knowledge_stats(conn, business_id)
        leads = get_leads(conn, {"business_id": str(business_id)})[:5]
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
    <section class="grid two" style="margin-top:18px;">
      <div class="panel pad"><h2>Services</h2><div class="grid three" style="margin-top:14px;">{services_html}</div></div>
      <div class="panel"><div class="pad"><h2>Knowledge Base / FAQs</h2></div><div class="list">{faq_html}</div></div>
    </section>
    <section class="panel" style="margin-top:18px;"><div class="pad"><h2>Recent Leads</h2></div><div class="list">{lead_html}</div></section>
    """
    return layout(business["name"], "Businesses", content)
