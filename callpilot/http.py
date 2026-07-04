from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from .analysis import analyze_call
from .config import SCORE_RULES
from .repositories import (
    get_business,
    get_businesses,
    get_knowledge,
    get_lead,
    get_leads,
    get_services,
    production_readiness,
)
from .storage import db
from .telephony import (
    create_twilio_outbound_call,
    get_or_create_call_session,
    next_twilio_prompt,
    should_finish_twilio_call,
    twilio_finish_twiml,
    twilio_gather_twiml,
)
from .utils import lead_temperature, now
from .views import (
    render_agent_builder,
    render_bookings,
    render_business_detail,
    render_businesses,
    render_calls,
    render_dashboard,
    render_demo_call,
    render_lead_detail,
    render_leads,
    render_not_found,
    render_notifications,
    render_real_calling,
    render_settings,
    save_agent,
)
from .workflows import create_event, create_lead_from_analysis, create_notification


class CallPilotHandler(BaseHTTPRequestHandler):
    server_version = "CallPilotAI/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send_html(self, content: str, status: int = 200) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, indent=2, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_xml(self, content: str, status: int = 200) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def body_bytes(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length else b""

    def form(self) -> dict[str, str]:
        parsed = parse_qs(self.body_bytes().decode("utf-8", errors="replace"), keep_blank_values=True)
        return {key: values[0] if values else "" for key, values in parsed.items()}

    def json_body(self) -> dict[str, Any]:
        raw = self.body_bytes().decode("utf-8", errors="replace")
        return json.loads(raw) if raw.strip() else {}

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        if path == "/":
            self.send_html(render_dashboard(query))
        elif path == "/businesses":
            self.send_html(render_businesses())
        elif re.fullmatch(r"/businesses/\d+", path):
            self.send_html(render_business_detail(int(path.rsplit("/", 1)[1])))
        elif path == "/agent-builder":
            self.send_html(render_agent_builder(query))
        elif path == "/demo-call":
            self.send_html(render_demo_call(query))
        elif path == "/real-calling":
            self.send_html(render_real_calling(query))
        elif path == "/leads":
            self.send_html(render_leads(query))
        elif re.fullmatch(r"/leads/\d+", path):
            self.send_html(render_lead_detail(int(path.rsplit("/", 1)[1])))
        elif path == "/bookings":
            self.send_html(render_bookings())
        elif path == "/calls":
            self.send_html(render_calls())
        elif path == "/notifications":
            self.send_html(render_notifications())
        elif path == "/settings":
            self.send_html(render_settings(query.get("saved", ["0"])[0] == "1"))
        elif path == "/api/leads":
            with db() as conn:
                self.send_json({"success": True, "leads": get_leads(conn)})
        elif path == "/api/businesses":
            with db() as conn:
                self.send_json({"success": True, "businesses": get_businesses(conn)})
        elif re.fullmatch(r"/api/businesses/\d+/readiness", path):
            with db() as conn:
                self.send_json(production_readiness(conn, int(path.split("/")[-2])))
        elif path == "/api/twilio/voice":
            self.handle_twilio_voice(query, {})
        else:
            self.send_html(render_not_found(), 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        if path == "/agent-builder/create":
            business_id = save_agent(self.form())
            self.redirect(f"/businesses/{business_id}")
            return
        update_match = re.fullmatch(r"/agent-builder/(\d+)/update", path)
        if update_match:
            business_id = int(update_match.group(1))
            save_agent(self.form(), business_id)
            self.redirect(f"/businesses/{business_id}")
            return
        if path == "/demo-call/analyze":
            form = self.form()
            business_id = int(form.get("business_id") or 1)
            transcript = form.get("transcript", "")
            with db() as conn:
                business = get_business(conn, business_id)
                if not business:
                    self.redirect("/demo-call")
                    return
                analysis = analyze_call(transcript, business, get_services(conn, business_id), get_knowledge(conn, business_id))
                lead = create_lead_from_analysis(conn, business_id, transcript, analysis, provider="demo")
            self.redirect(f"/leads/{lead['id']}")
            return
        if path == "/real-calling/outbound":
            form = self.form()
            business_id = int(form.get("business_id") or 1)
            ok, msg = create_twilio_outbound_call(form.get("to_number", ""), business_id)
            param = "message" if ok else "error"
            self.redirect(f"/real-calling?business_id={business_id}&{param}={urlencode({'x': msg})[2:]}")
            return
        status_match = re.fullmatch(r"/leads/(\d+)/status", path)
        if status_match:
            lead_id = int(status_match.group(1))
            status = self.form().get("status", "new")
            if status not in {"new", "contacted", "follow_up", "won", "lost"}:
                status = "new"
            with db() as conn:
                conn.execute("update leads set status=?, updated_at=? where id=?", (status, now(), lead_id))
                lead = get_lead(conn, lead_id)
                create_event(conn, lead["business_id"] if lead else None, lead_id, "status_changed", f"Lead status changed to {status}.", {"status": status})
            self.redirect(f"/leads/{lead_id}")
            return
        handoff_match = re.fullmatch(r"/leads/(\d+)/handoff", path)
        if handoff_match:
            lead_id = int(handoff_match.group(1))
            with db() as conn:
                lead = get_lead(conn, lead_id)
                if lead:
                    analysis = {
                        "customer_name": lead["customer_name"],
                        "customer_phone": lead["customer_phone"],
                        "request_type": lead["request_type"],
                        "lead_score": lead["lead_score"],
                        "ai_summary": lead["ai_summary"],
                        "recommended_action": lead["recommended_action"],
                    }
                    create_notification(conn, lead["business_id"], lead_id, analysis)
                    conn.execute("update leads set handoff_triggered=1 where id=?", (lead_id,))
            self.redirect(f"/leads/{lead_id}")
            return
        delete_match = re.fullmatch(r"/leads/(\d+)/delete", path)
        if delete_match:
            lead_id = int(delete_match.group(1))
            with db() as conn:
                conn.execute("delete from leads where id=?", (lead_id,))
            self.redirect("/leads")
            return
        booking_match = re.fullmatch(r"/bookings/(\d+)/status", path)
        if booking_match:
            booking_id = int(booking_match.group(1))
            status = self.form().get("status", "requested")
            with db() as conn:
                conn.execute("update bookings set status=?, updated_at=? where id=?", (status, now(), booking_id))
            self.redirect("/bookings")
            return
        if path == "/settings/update":
            form = self.form()
            with db() as conn:
                for key, value in form.items():
                    conn.execute(
                        """
                        insert into settings (key, value, created_at, updated_at)
                        values (?, ?, ?, ?)
                        on conflict(key) do update set value=excluded.value, updated_at=excluded.updated_at
                        """,
                        (key, value, now(), now()),
                    )
            self.redirect("/settings?saved=1")
            return
        if path == "/api/ai/analyze-call":
            data = self.json_body()
            business_id = int(data.get("business_id") or 1)
            transcript = data.get("transcript", "")
            with db() as conn:
                business = get_business(conn, business_id)
                if not business:
                    self.send_json({"success": False, "error": "Business not found"}, 404)
                    return
                analysis = analyze_call(transcript, business, get_services(conn, business_id), get_knowledge(conn, business_id))
            self.send_json(analysis)
            return
        if path == "/api/voice/webhook":
            data = self.json_body()
            business_id = int(data.get("business_id") or 1)
            transcript = data.get("transcript", "")
            with db() as conn:
                business = get_business(conn, business_id)
                if not business:
                    self.send_json({"success": False, "error": "Business not found"}, 404)
                    return
                analysis = analyze_call(transcript, business, get_services(conn, business_id), get_knowledge(conn, business_id))
                lead = create_lead_from_analysis(
                    conn,
                    business_id,
                    transcript,
                    analysis,
                    provider=data.get("provider", "voice_webhook"),
                    call_id=data.get("call_id"),
                    caller_phone=data.get("caller_phone"),
                    recording_url=data.get("recording_url"),
                )
            self.send_json(
                {
                    "success": True,
                    "lead_id": lead["id"],
                    "lead_score": lead["lead_score"],
                    "lead_temperature": lead["lead_temperature"],
                    "booking_requested": bool(lead["booking_requested"]),
                    "handoff_triggered": bool(lead["handoff_triggered"]),
                }
            )
            return
        if path == "/api/twilio/voice":
            self.handle_twilio_voice(query, self.form())
            return
        if path == "/api/twilio/gather":
            self.handle_twilio_gather(query, self.form())
            return
        self.send_html(render_not_found(), 404)

    def handle_twilio_voice(self, query: dict[str, list[str]], form: dict[str, str]) -> None:
        business_id = int((query.get("business_id") or [form.get("business_id") or "1"])[0] or 1)
        call_sid = form.get("CallSid") or f"manual-test-{datetime.now().timestamp()}"
        caller_phone = form.get("From")
        with db() as conn:
            business = get_business(conn, business_id)
            if not business:
                self.send_xml(twilio_finish_twiml("Sorry, this CallPilot business agent was not found."), 404)
                return
            get_or_create_call_session(conn, business_id, call_sid, caller_phone)
        prompt = (
            f"{business.get('agent_greeting') or 'Hi, thanks for calling.'} "
            "Please tell me what you need. Include your name and best callback number if you can."
        )
        self.send_xml(twilio_gather_twiml(business_id, prompt))

    def handle_twilio_gather(self, query: dict[str, list[str]], form: dict[str, str]) -> None:
        business_id = int((query.get("business_id") or [form.get("business_id") or "1"])[0] or 1)
        call_sid = form.get("CallSid") or f"manual-test-{datetime.now().timestamp()}"
        caller_phone = form.get("From")
        speech = form.get("SpeechResult", "").strip()
        if not speech:
            self.send_xml(twilio_gather_twiml(business_id, "I did not catch that. Please say your request again."))
            return

        with db() as conn:
            business = get_business(conn, business_id)
            if not business:
                self.send_xml(twilio_finish_twiml("Sorry, this CallPilot business agent was not found."), 404)
                return
            session = get_or_create_call_session(conn, business_id, call_sid, caller_phone)
            transcript = (session.get("transcript") or "").strip()
            transcript = (transcript + "\n" if transcript else "") + f"Caller: {speech}"
            turn_count = int(session.get("turn_count") or 0) + 1
            analysis = analyze_call(transcript, business, get_services(conn, business_id), get_knowledge(conn, business_id))
            if not analysis.get("customer_phone") and caller_phone:
                analysis["customer_phone"] = caller_phone
                analysis["score_breakdown"]["contact_detail"] = SCORE_RULES["contact_detail"]
                analysis["lead_score"] = min(100, sum(analysis["score_breakdown"].values()))
                analysis["lead_temperature"] = lead_temperature(analysis["lead_score"])

            if should_finish_twilio_call(analysis, turn_count, speech):
                lead = create_lead_from_analysis(
                    conn,
                    business_id,
                    transcript,
                    analysis,
                    provider="twilio",
                    call_id=call_sid,
                    caller_phone=caller_phone,
                )
                conn.execute(
                    "update call_sessions set transcript=?, turn_count=?, lead_id=?, status='completed', updated_at=? where call_sid=?",
                    (transcript, turn_count, lead["id"], now(), call_sid),
                )
                self.send_xml(
                    twilio_finish_twiml(
                        "Thanks. I have captured your request and sent it to the team. Someone will follow up soon. Goodbye."
                    )
                )
                return

            conn.execute(
                "update call_sessions set transcript=?, turn_count=?, updated_at=? where call_sid=?",
                (transcript, turn_count, now(), call_sid),
            )
            self.send_xml(twilio_gather_twiml(business_id, next_twilio_prompt(analysis, business)))
