from __future__ import annotations

from .layout import layout
from ..config import APP_NAME
from ..integrations import env_connected
from ..storage import db
from ..ui import badge, integration_badge
from ..utils import esc


def render_settings(saved: bool = False) -> str:
    env_rows = [
        ("SQLite", True, "Connected"),
        ("Supabase", env_connected("SUPABASE_URL", "SUPABASE_ANON_KEY"), None),
        ("Mock AI", True, "Active"),
        ("OpenAI", env_connected("OPENAI_API_KEY"), None),
        ("Claude", env_connected("ANTHROPIC_API_KEY"), None),
        ("Vapi", env_connected("VAPI_API_KEY"), None),
        ("Retell", env_connected("RETELL_API_KEY"), None),
        ("Twilio", env_connected("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"), None),
        ("ElevenLabs", env_connected("ELEVENLABS_API_KEY"), None),
        ("Deepgram", env_connected("DEEPGRAM_API_KEY"), None),
        ("Email SMTP", env_connected("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"), None),
        ("Slack", env_connected("SLACK_WEBHOOK_URL"), None),
        ("WhatsApp", env_connected("WHATSAPP_API_KEY"), None),
    ]
    with db() as conn:
        setting_rows = {row["key"]: row["value"] for row in conn.execute("select key, value from settings").fetchall()}
    integration_html = "".join(
        f'<div class="mini"><span>{esc(name)}</span><strong>{integration_badge(connected, label)}</strong></div>'
        for name, connected, label in env_rows
    )
    content = f"""
    <section><h1>Settings</h1><p class="muted">Integration status and demo mode settings.</p>{'<p>'+badge('Saved','status-active')+'</p>' if saved else ''}</section>
    <section class="panel pad" style="margin-top:18px;">
      <h2>App Settings</h2>
      <form method="post" action="/settings/update" class="form-grid" style="margin-top:14px;">
        <label>App name<input name="app_name" value="{esc(setting_rows.get('app_name', APP_NAME))}"></label>
        <label>Theme<input name="theme" value="{esc(setting_rows.get('theme', 'dark premium'))}"></label>
        <label>Demo mode<select name="demo_mode"><option value="true">true</option><option value="false">false</option></select></label>
        <label>Default hot lead threshold<input name="default_hot_lead_threshold" type="number" value="{esc(setting_rows.get('default_hot_lead_threshold', '75'))}"></label>
        <label>Default warm lead threshold<input name="default_warm_lead_threshold" type="number" value="{esc(setting_rows.get('default_warm_lead_threshold', '45'))}"></label>
        <div class="full"><button class="btn primary" type="submit">Save Settings</button></div>
      </form>
    </section>
    <section class="panel pad" style="margin-top:18px;">
      <h2>Connection Status</h2>
      <p class="muted">Some integrations are running in demo mode because API keys are missing.</p>
      <div class="grid three">{integration_html}</div>
    </section>
    """
    return layout("Settings", "Settings", content)
