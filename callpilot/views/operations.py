from __future__ import annotations

from .layout import layout, metric
from ..clinic_workflow import allowed_transitions, normalize_status
from ..repositories import get_bookings, get_call_logs, get_notifications
from ..storage import db
from ..ui import status_badge
from ..utils import esc, format_dt, title


def booking_action_cell(booking: dict) -> str:
    options = sorted(allowed_transitions(booking["status"]))
    if not options:
        return '<span class="muted">Locked (terminal)</span>'
    option_html = "".join(f"<option>{esc(option)}</option>" for option in options)
    return (
        f'<form method="post" action="/bookings/{booking["id"]}/status" class="actions">'
        f'<select name="status">{option_html}</select>'
        f'<button class="btn" type="submit">Update</button></form>'
    )


def booking_calendar_cell(booking: dict) -> str:
    status = (booking.get("calendar_sync_status") or "none").strip() or "none"
    labels = {
        "none": '<span class="muted">Not synced</span>',
        "pending": '<span class="badge warm">Pending calendar</span>',
        "pending_cancel": '<span class="badge warm">Cancel pending</span>',
        "confirmed": '<span class="badge good">On calendar</span>',
        "cancelled": '<span class="badge">Removed</span>',
    }
    cell = labels.get(status, f'<span class="badge">{esc(status)}</span>')
    event_id = booking.get("calendar_event_id")
    if event_id:
        cell += f'<div class="muted">{esc(str(event_id))}</div>'
    return cell


def render_bookings(error: str | None = None) -> str:
    with db() as conn:
        bookings = get_bookings(conn)
    requested = sum(1 for b in bookings if normalize_status(b["status"]) == "requested")
    confirmed = sum(1 for b in bookings if normalize_status(b["status"]) == "confirmed")
    rows = "".join(
        f"""
        <tr>
          <td><div style="display:flex;align-items:center;gap:12px;"><span class="avatar">{esc((b['customer_name'] or 'B')[:1].upper())}</span><div><strong>{esc(b['customer_name'] or 'Unknown')}</strong><div class="muted">{esc(b['business_name'])}</div></div></div></td>
          <td>{esc(b['booking_type'])}</td><td>{esc(b['requested_date'] or '')}</td><td>{esc(b['requested_time'] or '')}</td><td>{esc(b['number_of_people'] or '')}</td><td>{status_badge(b['status'])}</td><td>{booking_calendar_cell(b)}</td><td>{booking_action_cell(b)}</td>
        </tr>
        """
        for b in bookings
    )
    banner = (
        '<section class="panel" style="margin-top:12px;border-color:#f5c2c7;color:#b02a37;">'
        "That status change is not allowed by the clinic workflow.</section>"
        if error == "invalid_transition"
        else ""
    )
    content = f"""
    <section class="row"><div><h1>Bookings</h1><p class="muted">Booking requests created by AI agents.</p></div>{status_badge('requested') if requested else ''}</section>
    {banner}
    <section class="grid metrics">
      {metric('Bookings', len(bookings))}
      {metric('Requested', requested, 'warm' if requested else '')}
      {metric('Confirmed', confirmed, 'good')}
    </section>
    <section class="panel table-wrap" style="margin-top:18px;"><table><thead><tr><th>Customer</th><th>Type</th><th>Date</th><th>Time</th><th>People</th><th>Status</th><th>Calendar</th><th>Action</th></tr></thead><tbody>{rows or '<tr><td colspan="8">No bookings yet.</td></tr>'}</tbody></table></section>
    """
    return layout("Bookings", "Bookings", content)

def render_calls() -> str:
    with db() as conn:
        calls = get_call_logs(conn)
    providers = {c["provider"] for c in calls if c["provider"]}
    rows = "".join(
        f"<tr><td><div style='display:flex;align-items:center;gap:12px;'><span class='avatar'>{esc((c['business_name'] or 'C')[:1].upper())}</span><div><strong>{esc(c['business_name'])}</strong><div class='muted'>{esc(c['customer_name'] or 'Unknown')}</div></div></div></td><td>{esc(c['provider'])}</td><td>{esc(c['caller_phone'] or '')}</td><td>{status_badge(c['call_status'] or 'completed')}</td><td>{esc(c['duration_seconds'])}s</td><td>{format_dt(c['created_at'])}</td><td><a class='btn' href='/leads/{c['lead_id']}'>Lead</a></td></tr>"
        for c in calls
    )
    content = f"""
    <section><h1>Call Logs</h1><p class="muted">Demo calls and future voice provider webhook logs.</p></section>
    <section class="grid metrics">
      {metric('Calls', len(calls))}
      {metric('Providers', len(providers))}
    </section>
    <section class="panel table-wrap" style="margin-top:18px;"><table><thead><tr><th>Business / Customer</th><th>Provider</th><th>Caller Phone</th><th>Status</th><th>Duration</th><th>Created</th><th>Open</th></tr></thead><tbody>{rows or '<tr><td colspan="7">No calls yet.</td></tr>'}</tbody></table></section>
    """
    return layout("Calls", "Calls", content)

def render_notifications() -> str:
    with db() as conn:
        notes = get_notifications(conn)
    sent = sum(1 for n in notes if n["status"] == "sent")
    rows = "".join(
        f"<tr><td><div style='display:flex;align-items:center;gap:12px;'><span class='avatar'>{esc((n['customer_name'] or 'N')[:1].upper())}</span><div><strong>{esc(n['customer_name'] or 'Unknown')}</strong><div class='muted'>{esc(n['business_name'])}</div></div></div></td><td>{esc(title(n['notification_type']))}</td><td>{esc(n['channel'])}</td><td>{esc(n['recipient'])}</td><td>{esc(n['subject'])}</td><td>{status_badge(n['status'])}</td><td><a class='btn' href='/leads/{n['lead_id']}'>Open</a></td></tr>"
        for n in notes
    )
    content = f"""
    <section><h1>Notifications</h1><p class="muted">Dashboard alerts for human handoff. Email, WhatsApp, SMS, and Slack can be connected later.</p></section>
    <section class="grid metrics">
      {metric('Notifications', len(notes))}
      {metric('Sent', sent, 'good')}
      {metric('Pending', len(notes) - sent, 'warm' if len(notes) - sent else '')}
    </section>
    <section class="panel table-wrap" style="margin-top:18px;"><table><thead><tr><th>Lead</th><th>Type</th><th>Channel</th><th>Recipient</th><th>Preview</th><th>Status</th><th>Open</th></tr></thead><tbody>{rows or '<tr><td colspan="7">No notifications yet.</td></tr>'}</tbody></table></section>
    """
    return layout("Notifications", "Notifications", content)
