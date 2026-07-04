from __future__ import annotations

from .errors import render_not_found
from .layout import layout
from ..modules import INDUSTRY_MODULES, comma, module_by_key
from ..ui import badge
from ..utils import esc


def _items(values: list[str] | str | None) -> str:
    if not values:
        return "<li>Not configured.</li>"
    if isinstance(values, str):
        values = [values]
    return "".join(f"<li>{esc(value)}</li>" for value in values)


def _mini_items(values: list[str] | str | None) -> str:
    if not values:
        values = ["Not configured"]
    if isinstance(values, str):
        values = [values]
    return "".join(f'<div class="mini"><strong>{esc(value)}</strong></div>' for value in values)


def render_modules() -> str:
    cards = "".join(
        f"""
        <article class="panel pad">
          <div class="row"><h2>{esc(module['label'])}</h2>{badge(str(len(module['allowed_call_types'])) + ' workflows', 'status-demo')}</div>
          <p class="muted">{esc(module['compliance_profile'])}</p>
          <div class="mini"><span>Business Types</span><strong>{esc(comma(module['business_types']))}</strong></div>
          <div class="mini" style="margin-top:12px;"><span>Integrations</span><strong>{esc(module['integration_targets'])}</strong></div>
          <div class="actions" style="margin-top:14px;">
            <a class="btn primary" href="/modules/{esc(key)}">Open Module</a>
          </div>
        </article>
        """
        for key, module in INDUSTRY_MODULES.items()
    )
    content = f"""
    <section class="hero">
      <h1>Industry Modules</h1>
      <p>Production module registry from the Universal AI Calling Platform PDF pack. Each module defines intake fields, allowed call types, blocked outcomes, compliance profile, language policy, integration targets, and QA checks.</p>
      <div class="actions">
        {badge(str(len(INDUSTRY_MODULES)) + ' modules', 'status-active')}
        {badge('PDF pack mapped', 'status-demo')}
        {badge('Demo-safe registry', 'status-demo')}
      </div>
    </section>
    <section class="grid cards" style="margin-top:18px;">{cards}</section>
    """
    return layout("Industry Modules", "Modules", content)


def render_module_detail(key: str) -> str:
    module = module_by_key(key)
    if module["key"] != key and key != "custom":
        return render_not_found()
    content = f"""
    <a class="btn" href="/modules">Back to Modules</a>
    <section class="hero" style="margin-top:16px;">
      <div class="row">
        <div>
          <h1>{esc(module['label'])}</h1>
          <p>{esc(module['compliance_profile'])}</p>
        </div>
        {badge(module['key'], 'status-demo')}
      </div>
      <div class="actions">
        {badge(str(len(module['allowed_call_types'])) + ' workflows', 'status-active')}
        {badge(str(len(module['blocked_outcomes'])) + ' blocked outcomes', 'status-missing')}
        {badge(str(len(module['qa_checks'])) + ' QA checks', 'status-demo')}
      </div>
    </section>
    <section class="grid two" style="margin-top:18px;">
      <div class="panel pad">
        <h2>Allowed Call Types</h2>
        <div class="grid two" style="margin-top:14px;">{_mini_items(module['allowed_call_types'])}</div>
      </div>
      <div class="panel pad">
        <h2>Client Intake Fields</h2>
        <ul>{_items(module['intake_fields'])}</ul>
      </div>
    </section>
    <section class="grid two" style="margin-top:18px;">
      <div class="panel pad">
        <h2>Blocked Outcomes</h2>
        <ul>{_items(module['blocked_outcomes'])}</ul>
      </div>
      <div class="panel pad">
        <h2>QA Checks</h2>
        <ul>{_items(module['qa_checks'])}</ul>
      </div>
    </section>
    <section class="grid two" style="margin-top:18px;">
      <div class="panel pad">
        <h2>Language Policy</h2>
        <p>{esc(module['language_policy'])}</p>
      </div>
      <div class="panel pad">
        <h2>Integration Targets</h2>
        <p>{esc(module['integration_targets'])}</p>
      </div>
    </section>
    """
    return layout(module["label"], "Modules", content)
