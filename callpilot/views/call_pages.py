from __future__ import annotations

from .layout import layout, metric
from ..config import SAMPLE_TRANSCRIPTS
from ..integrations import env_connected
from ..repositories import get_businesses
from ..security import twilio_signature_required
from ..storage import db
from ..telephony import app_url
from ..ui import badge, integration_badge
from ..utils import esc


def render_demo_call(query: dict[str, list[str]]) -> str:
    with db() as conn:
        businesses = get_businesses(conn)
    business_id = int(query.get("business_id", [businesses[0]["id"] if businesses else 1])[0] or 1)
    sample_key = query.get("sample", ["hotel"])[0]
    selected = next((b for b in businesses if int(b["id"]) == business_id), businesses[0])
    transcript = SAMPLE_TRANSCRIPTS.get(sample_key) or SAMPLE_TRANSCRIPTS.get(selected["business_type"].lower().split()[0], SAMPLE_TRANSCRIPTS["custom"])
    options = "".join(
        f'<option value="{b["id"]}" {"selected" if int(b["id"]) == business_id else ""}>{esc(b["name"])} - {esc(b["business_type"])}</option>'
        for b in businesses
    )
    sample_links = "".join(
        f'<a class="btn" href="/demo-call?business_id={business_id}&sample={key}">{esc(label)}</a>'
        for key, label in [
            ("hotel", "Hotel Booking"),
            ("clinic", "Clinic Appointment"),
            ("home", "Home Emergency"),
            ("restaurant", "Restaurant Reservation"),
            ("software", "Software Inquiry"),
            ("law", "Law Consultation"),
            ("custom", "Custom Business"),
        ]
    )
    content = f"""
    <section class="row">
      <div>
        <h1>Demo Call Simulator</h1>
        <p class="muted">Select a business, test a sample transcript, and create leads, bookings, call logs, and handoff alerts.</p>
      </div>
      {badge('Mock AI', 'status-demo')}
    </section>
    <section class="grid metrics">
      {metric('Businesses', len(businesses))}
      {metric('Samples', len(SAMPLE_TRANSCRIPTS))}
      {metric('Selected', esc(selected['business_type']), 'good')}
    </section>
    <section class="grid two" style="margin-top:18px;">
      <form class="panel pad" method="post" action="/demo-call/analyze">
        <label>Business<select name="business_id">{options}</select></label>
        <p class="muted"><strong>Agent greeting:</strong> {esc(selected.get('agent_greeting'))}</p>
        <div class="actions" style="margin-bottom:12px;">{sample_links}</div>
        <label>Transcript<textarea name="transcript" style="min-height:360px;">{esc(transcript)}</textarea></label>
        <div class="actions" style="margin-top:14px;"><button class="btn primary" type="submit">Analyze Call</button></div>
      </form>
      <aside class="callout">
        <div class="kicker" style="color:rgba(255,255,255,.7);">Demo pipeline</div>
        <h2>Mock AI Agent Pipeline</h2>
        <p class="muted">Router Agent, Knowledge Agent, Lead Qualification Agent, Booking Agent, Scoring Agent, Handoff Agent, Safety Agent, and Notification Agent run in demo mode.</p>
        <div class="grid">
          <div class="mini"><span>AI Provider</span><strong>Mock AI active unless keys exist</strong></div>
          <div class="mini"><span>Database</span><strong>SQLite local mode</strong></div>
          <div class="mini"><span>Voice</span><strong>Webhook-ready demo mode</strong></div>
        </div>
      </aside>
    </section>
    """
    return layout("Demo Call", "Demo Call", content)

def render_real_calling(query: dict[str, list[str]]) -> str:
    selected_id = int(query.get("business_id", ["1"])[0] or 1)
    message = query.get("message", [""])[0]
    error = query.get("error", [""])[0]
    public_url = app_url()
    with db() as conn:
        businesses = get_businesses(conn)
    selected = next((b for b in businesses if int(b["id"]) == selected_id), businesses[0])
    options = "".join(
        f'<option value="{b["id"]}" {"selected" if int(b["id"]) == selected_id else ""}>{esc(b["name"])} - {esc(b["business_type"])}</option>'
        for b in businesses
    )
    webhook_url = f"{public_url}/api/twilio/voice?business_id={selected_id}"
    gather_url = f"{public_url}/api/twilio/gather?business_id={selected_id}"
    can_twilio_reach = not (public_url.startswith("http://127.0.0.1") or public_url.startswith("http://localhost"))
    status_note = (
        integration_badge(True, "Public URL set")
        if can_twilio_reach
        else integration_badge(False, "Needs public HTTPS URL")
    )
    content = f"""
    <section class="hero">
      <h1>Real Calling</h1>
      <p>Connect a real Twilio phone number to CallPilot AI. Twilio will call these webhooks when someone phones your number, CallPilot will gather speech, analyze the call, create a lead, create a booking when needed, and trigger handoff notifications.</p>
      <div class="actions">{status_note} {integration_badge(env_connected('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_PHONE_NUMBER'), 'Twilio keys ready' if env_connected('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_PHONE_NUMBER') else 'Twilio keys missing')} {integration_badge(twilio_signature_required(), 'Signature required' if twilio_signature_required() else 'Signature demo-optional')}</div>
    </section>
    {'<section class="panel pad" style="margin-top:16px;">'+badge('Success','status-active')+' '+esc(message)+'</section>' if message else ''}
    {'<section class="panel pad" style="margin-top:16px;">'+badge('Error','status-missing')+' '+esc(error)+'</section>' if error else ''}
    <section class="grid metrics">
      {metric('Businesses', len(businesses))}
      {metric('Public URL', 'Ready' if can_twilio_reach else 'Local', 'good' if can_twilio_reach else 'warm')}
      {metric('Twilio', 'Ready' if env_connected('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_PHONE_NUMBER') else 'Missing', 'good' if env_connected('TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_PHONE_NUMBER') else 'hot')}
      {metric('Signatures', 'Required' if twilio_signature_required() else 'Optional', 'good' if twilio_signature_required() else 'warm')}
    </section>
    <section class="grid two" style="margin-top:18px;">
      <div class="panel pad">
        <h2>Inbound Calling Setup</h2>
        <form method="get" action="/real-calling" class="actions" style="margin-top:14px;">
          <select style="max-width:360px" name="business_id">{options}</select>
          <button class="btn" type="submit">Show Webhook</button>
        </form>
        <p class="muted">Selected business: <strong>{esc(selected['name'])}</strong></p>
        <label>Twilio Voice Webhook URL<input readonly value="{esc(webhook_url)}"></label>
        <p class="muted">In Twilio Console, open your phone number, set **A call comes in** to Webhook, method POST, and paste the URL above.</p>
        <div class="mini" style="margin-top:12px;">
          <span>Important</span>
          <strong>Twilio cannot call 127.0.0.1 directly.</strong>
          <p class="muted">Use ngrok or another tunnel, set APP_URL in `.env` to that public HTTPS URL, restart `python app.py`, then copy the webhook again.</p>
        </div>
      </div>
      <div class="panel pad">
        <h2>Outbound Test Call</h2>
        <p class="muted">This makes Twilio call your phone, then CallPilot speaks and gathers your answer.</p>
        <form method="post" action="/real-calling/outbound" class="grid" style="margin-top:14px;">
          <label>Business<select name="business_id">{options}</select></label>
          <label>Your phone number<input name="to_number" placeholder="+923001234567"></label>
          <label class="checkline"><input type="checkbox" name="consent_confirmed" value="yes"> I have consent to place this outbound test call.</label>
          <button class="btn primary" type="submit">Start Real Test Call</button>
        </form>
        <div class="mini" style="margin-top:12px;">
          <span>Outbound Policy</span>
          <strong>Consent, DNC, and max-attempt checks run before Twilio starts.</strong>
          <p class="muted">Use Compliance Center to record consent or add opt-outs. Businesses with max outbound attempts set to 0 cannot start outbound calls.</p>
        </div>
      </div>
    </section>
    <section class="panel pad" style="margin-top:18px;">
      <h2>What Happens During A Real Call</h2>
      <div class="grid three" style="margin-top:14px;">
        <div class="mini"><span>1</span><strong>Caller phones Twilio number</strong><p class="muted">Twilio requests CallPilot's voice webhook.</p></div>
        <div class="mini"><span>2</span><strong>CallPilot asks questions</strong><p class="muted">Twilio speech recognition sends spoken answers back.</p></div>
        <div class="mini"><span>3</span><strong>Lead is created</strong><p class="muted">The same scoring, booking, call log, and notification engine runs.</p></div>
      </div>
    </section>
    <section class="panel pad" style="margin-top:18px;">
      <h2>Developer Endpoints</h2>
      <p><strong>Initial Twilio webhook:</strong> <code>{esc(webhook_url)}</code></p>
      <p><strong>Speech gather webhook:</strong> <code>{esc(gather_url)}</code></p>
    </section>
    """
    return layout("Real Calling", "Real Calling", content)
