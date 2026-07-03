from __future__ import annotations

from .layout import layout
from ..repositories import get_bookings, get_call_logs, get_notifications
from ..storage import db
from ..ui import status_badge
from ..utils import esc, format_dt, title


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
