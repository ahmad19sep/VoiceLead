from __future__ import annotations

from .layout import layout, metric
from ..config import APP_NAME, APP_TAGLINE, BUSINESS_TYPES
from ..repositories import get_events, get_leads
from ..stats import stats
from ..storage import db
from ..ui import temp_badge
from ..utils import esc, format_dt


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
