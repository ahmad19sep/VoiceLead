from __future__ import annotations

from .layout import layout
from ..config import BUSINESS_TYPES, TONE_OPTIONS
from ..repositories import get_business, get_knowledge, get_services
from ..seed import template_for_business_type
from ..storage import db
from ..utils import esc, now
from ..workflows import create_event


def parse_lines(text: str, parts: int) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        pieces = [piece.strip() for piece in line.split("|")]
        while len(pieces) < parts:
            pieces.append("")
        rows.append(pieces[:parts])
    return rows

def render_agent_builder(query: dict[str, list[str]]) -> str:
    business_id = int(query.get("business_id", ["0"])[0] or 0)
    with db() as conn:
        business = get_business(conn, business_id) if business_id else None
        services = get_services(conn, business_id) if business_id else []
        knowledge = get_knowledge(conn, business_id) if business_id else []
    template = template_for_business_type(business["business_type"] if business else "Hotel")
    business_type_value = business["business_type"] if business else "Hotel"
    type_options = "".join(
        f'<option value="{esc(item)}" {"selected" if item == business_type_value else ""}>{esc(item)}</option>'
        for item in BUSINESS_TYPES
    )
    tone_value = business["agent_tone"] if business else template["tone"]
    tone_options = "".join(
        f'<option value="{esc(item)}" {"selected" if item == tone_value else ""}>{esc(item)}</option>'
        for item in TONE_OPTIONS
    )
    services_text = "\n".join(
        f"{s['name']} | {s['description']} | {s['price_note'] or ''} | {s['is_bookable']} | {s['is_emergency']}"
        for s in services
    ) or "Service name | Description | Price note | 1 | 0"
    faq_text = "\n".join(f"{k['question']} | {k['answer']} | {k['category'] or ''}" for k in knowledge) or (
        "Question | Answer | Category"
    )
    action = f"/agent-builder/{business_id}/update" if business else "/agent-builder/create"
    content = f"""
    <section>
      <h1>Agent Builder</h1>
      <p class="muted">Create a flexible AI phone agent for any business.</p>
    </section>
    <form class="panel pad" method="post" action="{action}" style="margin-top:18px;">
      <h2>Business Info</h2>
      <div class="form-grid" style="margin-top:14px;">
        <label>Business name<input name="name" value="{esc((business or {}).get('name', ''))}" required></label>
        <label>Business type<select name="business_type">{type_options}</select></label>
        <label class="full">Description<textarea name="description">{esc((business or {}).get('description', template['description']))}</textarea></label>
        <label>Phone<input name="phone" value="{esc((business or {}).get('phone', ''))}"></label>
        <label>Email<input name="email" value="{esc((business or {}).get('email', ''))}"></label>
        <label>Location<input name="location" value="{esc((business or {}).get('location', ''))}"></label>
        <label>Working hours<input name="working_hours" value="{esc((business or {}).get('working_hours', ''))}"></label>
        <label>Website<input name="website" value="{esc((business or {}).get('website', ''))}"></label>
      </div>
      <h2 style="margin-top:22px;">Agent Identity</h2>
      <div class="form-grid" style="margin-top:14px;">
        <label>Agent name<input name="agent_name" value="{esc((business or {}).get('agent_name', template['agent_name']))}"></label>
        <label>Agent tone<select name="agent_tone">{tone_options}</select></label>
        <label class="full">Agent greeting<textarea name="agent_greeting">{esc((business or {}).get('agent_greeting', template['greeting']))}</textarea></label>
        <label class="full">Fallback message<textarea name="fallback_message">{esc((business or {}).get('fallback_message', template['fallback']))}</textarea></label>
      </div>
      <h2 style="margin-top:22px;">Services</h2>
      <p class="muted">One per line: service name | description | price note | is bookable 1/0 | is emergency 1/0</p>
      <textarea name="services">{esc(services_text)}</textarea>
      <h2 style="margin-top:22px;">Knowledge Base / FAQs</h2>
      <p class="muted">One per line: question | answer | category</p>
      <textarea name="faqs">{esc(faq_text)}</textarea>
      <h2 style="margin-top:22px;">Human Handoff Rules</h2>
      <div class="form-grid" style="margin-top:14px;">
        <label>Hot lead threshold<input type="number" name="hot_lead_threshold" value="{esc((business or {}).get('hot_lead_threshold', 75))}"></label>
        <label>Warm lead threshold<input type="number" name="warm_lead_threshold" value="{esc((business or {}).get('warm_lead_threshold', 45))}"></label>
        <label>Handoff person name<input name="handoff_name" value="{esc((business or {}).get('handoff_name', ''))}"></label>
        <label>Handoff phone<input name="handoff_phone" value="{esc((business or {}).get('handoff_phone', ''))}"></label>
        <label>Handoff email<input name="handoff_email" value="{esc((business or {}).get('handoff_email', ''))}"></label>
        <label class="full">Handoff instructions<textarea name="handoff_instructions">{esc((business or {}).get('handoff_instructions', 'Alert the assigned team member when handoff rules trigger.'))}</textarea></label>
      </div>
      <div class="actions" style="margin-top:18px;"><button class="btn primary" type="submit">Save Agent</button></div>
    </form>
    """
    return layout("Agent Builder", "Agent Builder", content)

def save_agent(form: dict[str, str], business_id: int | None = None) -> int:
    with db() as conn:
        if business_id:
            conn.execute(
                """
                update businesses set name=?, business_type=?, description=?, phone=?, email=?, website=?, location=?,
                working_hours=?, agent_name=?, agent_greeting=?, agent_tone=?, fallback_message=?,
                hot_lead_threshold=?, warm_lead_threshold=?, handoff_name=?, handoff_phone=?,
                handoff_email=?, handoff_instructions=?, updated_at=? where id=?
                """,
                (
                    form.get("name"),
                    form.get("business_type"),
                    form.get("description"),
                    form.get("phone"),
                    form.get("email"),
                    form.get("website"),
                    form.get("location"),
                    form.get("working_hours"),
                    form.get("agent_name"),
                    form.get("agent_greeting"),
                    form.get("agent_tone"),
                    form.get("fallback_message"),
                    int(form.get("hot_lead_threshold") or 75),
                    int(form.get("warm_lead_threshold") or 45),
                    form.get("handoff_name"),
                    form.get("handoff_phone"),
                    form.get("handoff_email"),
                    form.get("handoff_instructions"),
                    now(),
                    business_id,
                ),
            )
            conn.execute("delete from services where business_id=?", (business_id,))
            conn.execute("delete from knowledge_base where business_id=?", (business_id,))
        else:
            business_id = int(
                conn.execute(
                    """
                    insert into businesses (
                        name, business_type, description, phone, email, website, location, working_hours,
                        agent_name, agent_greeting, agent_tone, fallback_message, hot_lead_threshold,
                        warm_lead_threshold, handoff_name, handoff_phone, handoff_email, handoff_instructions,
                        status, created_at, updated_at
                    )
                    values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                    """,
                    (
                        form.get("name"),
                        form.get("business_type"),
                        form.get("description"),
                        form.get("phone"),
                        form.get("email"),
                        form.get("website"),
                        form.get("location"),
                        form.get("working_hours"),
                        form.get("agent_name"),
                        form.get("agent_greeting"),
                        form.get("agent_tone"),
                        form.get("fallback_message"),
                        int(form.get("hot_lead_threshold") or 75),
                        int(form.get("warm_lead_threshold") or 45),
                        form.get("handoff_name"),
                        form.get("handoff_phone"),
                        form.get("handoff_email"),
                        form.get("handoff_instructions"),
                        now(),
                        now(),
                    ),
                ).lastrowid
            )
        for name, description, price, bookable, emergency in parse_lines(form.get("services", ""), 5):
            if name.lower() == "service name" or not name:
                continue
            conn.execute(
                "insert into services (business_id, name, description, price_note, is_bookable, is_emergency) values (?, ?, ?, ?, ?, ?)",
                (business_id, name, description, price, int(bookable or 1), int(emergency or 0)),
            )
        for question, answer, category in parse_lines(form.get("faqs", ""), 3):
            if question.lower() == "question" or not question:
                continue
            conn.execute(
                "insert into knowledge_base (business_id, question, answer, category, tags, source) values (?, ?, ?, ?, ?, 'agent_builder')",
                (business_id, question, answer, category, category.lower()),
            )
        create_event(conn, business_id, None, "agent_saved", "Business agent saved from Agent Builder.", {})
        return business_id
