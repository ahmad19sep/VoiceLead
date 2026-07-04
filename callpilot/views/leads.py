from __future__ import annotations

from .errors import render_not_found
from .layout import layout
from ..config import SCORE_LABELS, SCORE_RULES
from ..repositories import get_businesses, get_events, get_lead, get_leads, get_qa_for_lead
from ..storage import db
from ..ui import badge, status_badge, temp_badge
from ..utils import esc, format_dt, from_json, title


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
        qa_rows = get_qa_for_lead(conn, lead_id)
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
    qa_html = ""
    for row in qa_rows:
        failures = from_json(row.get("critical_failures"), [])
        findings = from_json(row.get("findings"), [])
        status_kind = {"pass": "status-active", "review": "status-follow_up", "fail": "status-missing"}.get(row["qa_status"], "status-new")
        qa_html += f"""
        <div class="item">
          <div class="row"><strong>QA {row['qa_score']}/100</strong>{badge(title(row['qa_status']), status_kind)}</div>
          <div class="muted">{esc((failures or findings or ['No issues detected.'])[0])}</div>
        </div>
        """
    qa_html = qa_html or '<div class="item"><strong>No QA evaluation yet.</strong></div>'
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
        <div class="panel"><div class="pad"><h2>QA Evaluation</h2></div><div class="list">{qa_html}</div></div>
        <div class="panel pad"><h2>Call Transcript</h2><pre>{esc(lead['transcript'])}</pre></div>
        <div class="panel"><div class="pad"><h2>Event Timeline</h2></div><div class="list">{event_html}</div></div>
      </div>
    </section>
    """
    return layout("Lead Detail", "Leads", content)
