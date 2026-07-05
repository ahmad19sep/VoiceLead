from __future__ import annotations

from .layout import layout, metric
from ..config import APP_NAME, app_tagline, business_types_for_mode
from ..repositories import get_businesses, get_events, get_leads
from ..stats import stats
from ..storage import db
from ..ui import temp_badge
from ..utils import esc, format_dt


def pct(part: int, total: int) -> int:
    return round((part / total) * 100) if total else 0


def render_dashboard(query: dict[str, list[str]]) -> str:
    selected = query.get("type", ["All Businesses"])[0]
    with db() as conn:
        s = stats(conn, selected)
        events = get_events(conn)
        leads = get_leads(conn, {"temperature": "hot"})[:5]
        selected_businesses = get_businesses(conn, selected)
        businesses = selected_businesses[:5]
        ids = [business["id"] for business in selected_businesses]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            weekly_calls = conn.execute(
                f"""
                select strftime('%w', created_at) as day, count(*) as total
                from call_logs
                where business_id in ({placeholders})
                  and datetime(created_at) >= datetime('now', '-7 days')
                group by strftime('%w', created_at)
                """,
                ids,
            ).fetchall()
        else:
            weekly_calls = []
    day_totals = {row["day"]: int(row["total"]) for row in weekly_calls}
    day_labels = [("0", "Sun"), ("1", "Mon"), ("2", "Tue"), ("3", "Wed"), ("4", "Thu"), ("5", "Fri"), ("6", "Sat")]
    peak = max([*day_totals.values(), 1])
    bars = "".join(
        f'<div class="chart-bar"><i style="height:{max(18, round((day_totals.get(day, 0) / peak) * 100))}%; background:{("#113d2a" if day_totals.get(day, 0) == peak and peak > 1 else "var(--accent)")};"></i><span>{label}</span></div>'
        for day, label in day_labels
    )
    options = "".join(
        f'<option value="{esc(item)}" {"selected" if selected == item else ""}>{esc(item)}</option>'
        for item in ["All Businesses", *business_types_for_mode()]
    )
    event_html = "".join(
        f'<div class="item"><strong>{esc(e["description"])}</strong><div class="muted">{esc(e["event_type"])} - {format_dt(e["created_at"])}</div></div>'
        for e in events
    )
    lead_html = "".join(
        f"""
        <a class="item" href="/leads/{lead["id"]}">
          <div class="row">
            <div style="display:flex;align-items:center;gap:12px;min-width:0;">
              <span class="avatar">{esc((lead["customer_name"] or "U")[:1].upper())}</span>
              <div style="min-width:0;">
                <strong>{esc(lead["customer_name"] or "Unknown caller")}</strong> {temp_badge(lead["lead_temperature"])}
                <div class="muted">{esc(lead["business_name"])} - {esc(lead["request_type"])}</div>
              </div>
            </div>
            <strong>{lead["lead_score"]}/100</strong>
          </div>
        </a>
        """
        for lead in leads
    )
    agent_html = "".join(
        f"""
        <a class="item" href="/businesses/{business["id"]}">
          <div style="display:flex;align-items:center;gap:12px;">
            <span class="avatar">{esc((business["name"] or "A")[:1].upper())}</span>
            <div style="min-width:0;">
              <strong>{esc(business["agent_name"] or business["name"])}</strong>
              <div class="muted">{esc(business["name"])} - {esc(business["business_type"])}</div>
            </div>
          </div>
        </a>
        """
        for business in businesses
    )
    conversion = pct(s["bookings"], s["total_leads"])
    dash = round(258 * conversion / 100)
    content = f"""
    <section class="row">
      <div>
        <h1>{APP_NAME}</h1>
        <p class="muted" style="margin:6px 0 0;">{esc(app_tagline())}</p>
      </div>
      <div class="actions">
        <a class="btn primary" href="/agent-builder">Create Agent</a>
        <a class="btn" href="/demo-call">Test Call</a>
        <a class="btn" href="/leads">Leads</a>
      </div>
    </section>
    <form method="get" class="actions" style="margin-top:18px;">
      <select style="max-width:260px" name="type">{options}</select>
      <button class="btn" type="submit">Filter</button>
    </form>
    <section class="grid metrics">
      {metric('Active Agents', s['active_agents'], 'good')}
      {metric('Total Leads', s['total_leads'])}
      {metric('Hot Leads', s['hot_leads'], 'hot')}
      {metric('Bookings', s['bookings'], 'warm')}
    </section>
    <section class="dashboard-grid" style="margin-top:18px;">
      <div class="grid">
        <div class="panel pad">
          <div class="row">
            <div>
              <h2>Call Analytics</h2>
              <p class="muted" style="margin:4px 0 0;">Last 7 days across the selected workspace.</p>
            </div>
            <strong>{s['total_calls']} total calls</strong>
          </div>
          <div class="chart-bars">{bars}</div>
        </div>
        <div class="grid two">
          <div class="panel">
            <div class="pad"><h2>Recent Hot Leads</h2></div>
            <div class="list">{lead_html or '<div class="item muted">No hot leads yet.</div>'}</div>
          </div>
          <div class="panel">
            <div class="pad"><h2>Latest Call Activity</h2></div>
            <div class="list">{event_html or '<div class="item muted">No activity yet.</div>'}</div>
          </div>
        </div>
      </div>
      <aside class="grid">
        <div class="callout">
          <div class="muted" style="font-size:12px;font-weight:850;text-transform:uppercase;">Next action</div>
          <h2 style="margin-top:8px;">Review pending handoffs</h2>
          <p class="muted">{s['pending_handoffs']} lead(s) are waiting for a human follow-up decision.</p>
          <a class="btn primary" style="background:#fff;color:var(--deep);border-color:#fff;" href="/notifications">Open Handoffs</a>
        </div>
        <div class="panel">
          <div class="pad row"><h2>Agents</h2><a class="btn" href="/agent-builder">New</a></div>
          <div class="list">{agent_html or '<div class="item muted">No agents yet.</div>'}</div>
        </div>
        <div class="panel pad">
          <h2>Lead Conversion</h2>
          <div class="progress-ring">
            <svg viewBox="0 0 220 140" aria-label="Lead conversion">
              <path d="M30 116 A80 80 0 0 1 190 116" fill="none" stroke="#edf1ef" stroke-width="18" stroke-linecap="round"></path>
              <path d="M30 116 A80 80 0 0 1 190 116" fill="none" stroke="var(--accent)" stroke-width="18" stroke-linecap="round" stroke-dasharray="{dash} 258"></path>
              <text x="110" y="92" text-anchor="middle" style="font-size:34px;font-weight:850;fill:var(--ink);">{conversion}%</text>
              <text x="110" y="114" text-anchor="middle" style="font-size:12px;font-weight:750;fill:var(--muted);">booked leads</text>
            </svg>
          </div>
          <div class="grid two">
            <div class="mini"><span>Average Score</span><strong>{s['avg_score']}/100</strong></div>
            <div class="mini"><span>Calls Today</span><strong>{s['calls_today']}</strong></div>
          </div>
        </div>
      </aside>
    </section>
    """
    return layout("Dashboard", "Dashboard", content)
