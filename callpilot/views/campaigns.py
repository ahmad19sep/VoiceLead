from __future__ import annotations

from .errors import render_not_found
from .layout import layout, metric
from ..campaigns import get_campaign, get_campaign_recipients, get_campaigns
from ..repositories import get_businesses
from ..storage import db
from ..ui import badge, status_badge
from ..utils import esc, format_dt, title


def render_campaigns(query: dict[str, list[str]]) -> str:
    saved = query.get("saved", [""])[0]
    with db() as conn:
        businesses = get_businesses(conn)
        campaigns = get_campaigns(conn)
    business_options = "".join(
        f'<option value="{b["id"]}">{esc(b["name"])} - {esc(b["business_type"])}</option>' for b in businesses
    )
    rows = "".join(
        f"""
        <tr>
          <td><strong>{esc(row['name'])}</strong><div class="muted">{esc(row['campaign_type'])}</div></td>
          <td>{esc(row['business_name'])}</td>
          <td>{status_badge(row['status'])}</td>
          <td>{row['total_recipients'] or 0}</td>
          <td>{row['queued_recipients'] or 0} queued / {row['ready_recipients'] or 0} ready</td>
          <td>{row['suppressed_recipients'] or 0}</td>
          <td>{format_dt(row['created_at'])}</td>
          <td><a class="btn" href="/campaigns/{row['id']}">Open</a></td>
        </tr>
        """
        for row in campaigns
    )
    content = f"""
    <section class="row">
      <div><h1>Campaigns</h1><p class="muted">Prepare outbound call campaigns with consent, DNC, and business policy suppression before any dialer runs.</p></div>
      {badge('Plan only', 'status-demo')}
    </section>
    {'<section class="panel pad" style="margin-top:16px;">'+badge('Saved','status-active')+' '+esc(saved)+'</section>' if saved else ''}
    <section class="grid two" style="margin-top:18px;">
      <form class="panel pad" method="post" action="/campaigns/create">
        <h2>Create Campaign</h2>
        <div class="form-grid" style="margin-top:14px;">
          <label>Business<select name="business_id">{business_options}</select></label>
          <label>Campaign name<input name="name" value="Outbound follow-up campaign" required></label>
          <label>Campaign type<select name="campaign_type"><option value="outbound_call">Outbound call</option><option value="reminder">Reminder</option><option value="recall">Recall</option><option value="sales_follow_up">Sales follow-up</option></select></label>
          <label class="full">Script / intent<textarea name="script">Confirm the caller still wants a follow-up and route to staff if they are ready.</textarea></label>
          <label class="full">Targets<textarea name="targets" placeholder="Name | Phone | Notes&#10;Ahmad | +923001234567 | Asked for callback"></textarea></label>
        </div>
        <div class="actions" style="margin-top:14px;"><button class="btn primary" type="submit">Create And Suppress</button></div>
      </form>
      <aside class="panel pad">
        <h2>Suppression Rules</h2>
        <div class="grid">
          <div class="mini"><span>Consent</span><strong>Active outbound consent is required.</strong></div>
          <div class="mini"><span>DNC</span><strong>Do Not Call entries suppress matching phone numbers.</strong></div>
          <div class="mini"><span>Policy</span><strong>Businesses with max attempts set to 0 cannot queue recipients.</strong></div>
          <div class="mini"><span>Dialing</span><strong>No automatic calls are started from this page.</strong></div>
        </div>
      </aside>
    </section>
    <section class="panel table-wrap" style="margin-top:18px;">
      <table><thead><tr><th>Campaign</th><th>Business</th><th>Status</th><th>Total</th><th>Queued</th><th>Suppressed</th><th>Created</th><th>Open</th></tr></thead><tbody>{rows or '<tr><td colspan="8">No campaigns yet.</td></tr>'}</tbody></table>
    </section>
    """
    return layout("Campaigns", "Campaigns", content)


def render_campaign_detail(campaign_id: int) -> str:
    with db() as conn:
        campaign = get_campaign(conn, campaign_id)
        if not campaign:
            return render_not_found()
        recipients = get_campaign_recipients(conn, campaign_id)
    queued = sum(1 for row in recipients if row["status"] == "queued")
    ready = sum(1 for row in recipients if row["status"] == "ready")
    suppressed = sum(1 for row in recipients if row["status"] == "suppressed")
    rows = "".join(
        f"""
        <tr>
          <td><strong>{esc(row['customer_name'] or 'Unknown')}</strong></td>
          <td>{esc(row['customer_phone'] or '')}</td>
          <td>{status_badge(row['status'])}</td>
          <td>{esc(title(row['suppression_reason']) or '')}</td>
          <td>{row['attempts']}</td>
          <td>{esc(row['notes'] or '')}</td>
        </tr>
        """
        for row in recipients
    )
    content = f"""
    <a class="btn" href="/campaigns">Back to Campaigns</a>
    <section class="hero" style="margin-top:16px;">
      <div class="row"><div><h1>{esc(campaign['name'])}</h1><p>{esc(campaign['business_name'])} - {esc(campaign['campaign_type'])}</p></div>{status_badge(campaign['status'])}</div>
      <p>{esc(campaign['script'] or '')}</p>
      <div class="grid metrics">
        {metric('Recipients', len(recipients))}
        {metric('Queued', queued, 'good')}
        {metric('Ready', ready, 'good')}
        {metric('Suppressed', suppressed, 'hot' if suppressed else '')}
        {metric('Max Attempts', campaign['max_attempts'])}
      </div>
    </section>
    <section class="panel table-wrap" style="margin-top:18px;">
      <table><thead><tr><th>Name</th><th>Phone</th><th>Status</th><th>Suppression</th><th>Attempts</th><th>Notes</th></tr></thead><tbody>{rows or '<tr><td colspan="6">No recipients.</td></tr>'}</tbody></table>
    </section>
    """
    return layout(campaign["name"], "Campaigns", content)
