from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from .layout import layout, metric
from ..repositories import get_bookings
from ..storage import db
from ..ui import status_badge
from ..utils import esc


STATUS_COLORS = {
    "requested": "#b8860b",
    "confirmed": "#0e5fd8",
    "reminded": "#6f42c1",
    "rescheduled": "#b8860b",
    "completed": "#1a7f37",
    "cancelled": "#8a94a3",
    "no_show": "#b02a37",
}


def parse_booking_date(value: str | None) -> date | None:
    raw = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def week_start_for(query: dict[str, list[str]], today: date | None = None) -> date:
    today = today or date.today()
    raw = (query.get("start") or [""])[0]
    anchor = parse_booking_date(raw) or today
    return anchor - timedelta(days=anchor.weekday())


def booking_card(booking: dict[str, Any]) -> str:
    status = (booking.get("status") or "requested").lower()
    color = STATUS_COLORS.get(status, "#5b6b80")
    time_text = esc(booking.get("requested_time") or "")
    name = esc(booking.get("customer_name") or "Unknown")
    service = esc(booking.get("service_requested") or booking.get("booking_type") or "")
    on_calendar = (booking.get("calendar_sync_status") or "") == "confirmed"
    calendar_mark = " &#128197;" if on_calendar else ""
    return (
        f'<div class="cal-card" style="border-left:3px solid {color};">'
        f"<strong>{time_text or '&mdash;'}</strong> {name}{calendar_mark}"
        f'<div class="muted">{service} &middot; {esc(status)}</div>'
        "</div>"
    )


def render_calendar(query: dict[str, list[str]]) -> str:
    with db() as conn:
        bookings = get_bookings(conn)

    start = week_start_for(query)
    days = [start + timedelta(days=offset) for offset in range(7)]
    by_day: dict[date, list[dict[str, Any]]] = {day: [] for day in days}
    unscheduled: list[dict[str, Any]] = []
    week_count = 0
    for booking in bookings:
        when = parse_booking_date(booking.get("requested_date"))
        if when is None:
            unscheduled.append(booking)
        elif when in by_day:
            by_day[when].append(booking)
            week_count += 1

    for day in days:
        by_day[day].sort(key=lambda item: item.get("requested_time") or "99:99")

    today = date.today()
    prev_start = (start - timedelta(days=7)).isoformat()
    next_start = (start + timedelta(days=7)).isoformat()
    day_columns = "".join(
        f'<div class="cal-day{" today" if day == today else ""}">'
        f'<div class="cal-day-head">{day.strftime("%a")}<span>{day.strftime("%d %b")}</span></div>'
        + ("".join(booking_card(item) for item in by_day[day]) or '<div class="muted cal-empty">&mdash;</div>')
        + "</div>"
        for day in days
    )
    unscheduled_rows = "".join(
        f"<tr><td>{esc(b.get('customer_name') or 'Unknown')}</td>"
        f"<td>{esc(b.get('service_requested') or b.get('booking_type') or '')}</td>"
        f"<td>{esc(b.get('requested_date') or 'no date')}</td>"
        f"<td>{status_badge(b.get('status') or 'requested')}</td></tr>"
        for b in unscheduled[:20]
    )
    unscheduled_html = (
        f"""
    <section class="panel table-wrap" style="margin-top:18px;">
      <h2 style="margin:0 0 8px;">Needs a confirmed date</h2>
      <p class="muted">These requests came from calls without a clear date. Staff should confirm a slot.</p>
      <table><thead><tr><th>Patient</th><th>Service</th><th>Requested</th><th>Status</th></tr></thead>
      <tbody>{unscheduled_rows}</tbody></table>
    </section>
    """
        if unscheduled
        else ""
    )

    content = f"""
    <style>
      .cal-grid {{ display:grid; grid-template-columns:repeat(7, 1fr); gap:10px; margin-top:16px; }}
      .cal-day {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:8px; min-height:140px; }}
      .cal-day.today {{ outline:2px solid var(--blue); }}
      .cal-day-head {{ font-weight:600; font-size:.85rem; margin-bottom:8px; display:flex; justify-content:space-between; }}
      .cal-day-head span {{ color:var(--muted); font-weight:400; }}
      .cal-card {{ background:var(--blue-soft); border-radius:6px; padding:6px 8px; margin-bottom:6px; font-size:.8rem; }}
      .cal-empty {{ text-align:center; padding-top:24px; }}
      .cal-nav {{ display:flex; gap:8px; align-items:center; }}
      .cal-nav a {{ padding:6px 14px; border:1px solid var(--line-strong); border-radius:8px; text-decoration:none; background:var(--panel); }}
      @media (max-width: 900px) {{ .cal-grid {{ grid-template-columns:repeat(2, 1fr); }} }}
    </style>
    <section class="row">
      <div><h1>Appointment Calendar</h1>
      <p class="muted">Week of {start.strftime('%d %b %Y')} &middot; bookings from real and demo calls. &#128197; = synced to external calendar.</p></div>
      <div class="cal-nav">
        <a href="/calendar?start={prev_start}">&larr; Prev</a>
        <a href="/calendar">Today</a>
        <a href="/calendar?start={next_start}">Next &rarr;</a>
      </div>
    </section>
    <section class="grid metrics">
      {metric('This week', week_count)}
      {metric('Needs date', len(unscheduled), 'warm' if unscheduled else '')}
      {metric('Total bookings', len(bookings))}
    </section>
    <div class="cal-grid">{day_columns}</div>
    {unscheduled_html}
    """
    return layout("Calendar", "Calendar", content)
