from __future__ import annotations

from .layout import layout
from ..security import system_readiness
from ..ui import badge, integration_badge
from ..utils import esc


def render_admin_health() -> str:
    readiness = system_readiness()
    providers = readiness["providers"]
    provider_rows = "".join(
        f"""
        <tr>
          <td><strong>{esc(row['provider'])}</strong></td>
          <td>{esc(row['category'])}</td>
          <td>{integration_badge(row['connected'])}</td>
          <td>{integration_badge(row['production_ready'], 'Ready' if row['production_ready'] else 'Not Ready')}</td>
          <td>{esc(', '.join(row['capabilities']))}</td>
          <td>{esc(', '.join(row['requirements']))}</td>
        </tr>
        """
        for row in providers
    )
    blockers = "".join(f"<li>{esc(item)}</li>" for item in readiness["blockers"]) or "<li>No production blockers detected.</li>"
    warnings = "".join(f"<li>{esc(item)}</li>" for item in readiness["warnings"]) or "<li>No warnings.</li>"
    ready_badge = (
        badge("Production Ready", "status-active")
        if readiness["ready_for_production"]
        else badge("Not Production Ready", "status-missing")
    )
    content = f"""
    <section class="hero">
      <div class="row">
        <div>
          <h1>Admin Health</h1>
          <p>Provider status, deployment readiness, webhook signature policy, and launch blockers.</p>
        </div>
        {ready_badge}
      </div>
      <div class="grid four" style="margin-top:14px;">
        <div class="mini"><span>Environment</span><strong>{esc(readiness['app_env'])}</strong></div>
        <div class="mini"><span>Public URL</span><strong>{'Ready' if readiness['public_app_url_ready'] else 'Local/demo'}</strong></div>
        <div class="mini"><span>Twilio Signatures</span><strong>{'Required' if readiness['twilio_signature_required'] else 'Demo optional'}</strong></div>
        <div class="mini"><span>Provider Count</span><strong>{len(providers)}</strong></div>
      </div>
    </section>
    <section class="grid two" style="margin-top:18px;">
      <div class="panel pad"><h2>Launch Blockers</h2><ul>{blockers}</ul></div>
      <div class="panel pad"><h2>Warnings</h2><ul>{warnings}</ul></div>
    </section>
    <section class="panel table-wrap" style="margin-top:18px;">
      <div class="pad"><h2>Provider Readiness</h2></div>
      <table><thead><tr><th>Provider</th><th>Category</th><th>Connected</th><th>Production</th><th>Capabilities</th><th>Requirements</th></tr></thead><tbody>{provider_rows}</tbody></table>
    </section>
    <section class="panel pad" style="margin-top:18px;">
      <h2>Health API</h2>
      <p><code>GET /api/admin/health</code></p>
      <p><code>GET /api/providers</code></p>
    </section>
    """
    return layout("Admin Health", "Admin", content)
