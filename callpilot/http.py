from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from .analysis import analyze_call
from .auth import auth_required, authenticate
from .campaigns import create_campaign, get_campaign_recipients, get_campaigns
from .compliance import (
    add_dnc_entry,
    audit_event,
    default_workspace_id,
    get_audit_logs,
    get_consent_records,
    get_dnc_entries,
    get_staff_contacts,
    outbound_allowed,
    record_consent,
    role_allows,
    set_request_context,
    workspace_context,
)
from .calendar import calendar_statuses
from .clinic_workflow import WorkflowError, apply_booking_transition
from .voice_runtime import build_runtime_session, runtime_status
from .config import SCORE_RULES, clinic_mode
from .jobs import get_jobs, run_due_jobs
from .knowledge import ingest_knowledge_document, search_knowledge
from .modules import module_by_key, visible_modules
from .providers import create_outbound_call, provider_by_key, provider_statuses
from .repositories import (
    get_business,
    get_businesses,
    get_knowledge,
    get_lead,
    get_leads,
    get_qa_evaluations,
    get_services,
    production_readiness,
)
from .security import health_probe, readiness_probe, system_readiness, twilio_signature_required, validate_twilio_signature
from .sessions import build_session_cookie, session_from_cookie_header
from .storage import db
from .telephony import (
    app_url,
    get_or_create_call_session,
    next_twilio_prompt,
    should_finish_twilio_call,
    twilio_finish_twiml,
    twilio_gather_twiml,
)
from .utils import lead_temperature, now
from .views.auth_pages import render_login
from .views import (
    render_agent_builder,
    render_admin_health,
    render_bookings,
    render_business_detail,
    render_businesses,
    render_calls,
    render_campaign_detail,
    render_campaigns,
    render_compliance,
    render_dashboard,
    render_demo_call,
    render_jobs,
    render_knowledge,
    render_knowledge_document,
    render_lead_detail,
    render_leads,
    render_module_detail,
    render_modules,
    render_not_found,
    render_notifications,
    render_qa,
    render_real_calling,
    render_settings,
    save_agent,
)
from .workflows import create_event, create_lead_from_analysis, create_notification


class CallPilotHandler(BaseHTTPRequestHandler):
    server_version = "CallPilotAI/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))

    def send_security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; form-action 'self'",
        )

    def send_html(self, content: str, status: int = 200) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, indent=2, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def send_xml(self, content: str, status: int = 200) -> None:
        body = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_security_headers()
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location: str, cookie: str | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_security_headers()
        self.end_headers()

    PUBLIC_PATHS = {"/login", "/healthz", "/readyz"}
    WEBHOOK_PATHS = {"/api/twilio/voice", "/api/twilio/gather"}

    def apply_request_context(self) -> None:
        session = session_from_cookie_header(self.headers.get("Cookie"))
        self.session = session
        workspace_id = None
        try:
            workspace_id = int(session.get("workspace_id") or 0) or None
        except (TypeError, ValueError):
            workspace_id = None
        user_email = str(session.get("user_email") or "").strip().lower() or None
        set_request_context(workspace_id, user_email)

    def is_authenticated(self) -> bool:
        return bool(self.session.get("authenticated") and self.session.get("user_email"))

    def require_login(self, path: str) -> bool:
        """Return True when the request may proceed."""
        if not auth_required():
            return True
        if path in self.PUBLIC_PATHS or path in self.WEBHOOK_PATHS:
            return True
        if self.is_authenticated():
            return True
        if path.startswith("/api/"):
            self.send_json({"success": False, "error": "Authentication required"}, 401)
        else:
            self.redirect("/login")
        return False

    def permission_for_post_route(self, path: str) -> str | None:
        exact = {
            "/agent-builder/create": "manage_agents",
            "/demo-call/analyze": "place_calls",
            "/real-calling/outbound": "place_calls",
            "/campaigns/create": "manage_campaigns",
            "/jobs/run": "run_jobs",
            "/knowledge/ingest": "manage_agents",
            "/compliance/consent": "manage_compliance",
            "/compliance/dnc": "manage_compliance",
            "/settings/update": "manage_workspace",
            "/api/ai/analyze-call": "place_calls",
        }
        if path in exact:
            return exact[path]
        regex_permissions = [
            (r"/agent-builder/\d+/update", "manage_agents"),
            (r"/leads/\d+/status", "place_calls"),
            (r"/leads/\d+/handoff", "place_calls"),
            (r"/leads/\d+/delete", "manage_agents"),
            (r"/bookings/\d+/status", "place_calls"),
        ]
        for pattern, permission in regex_permissions:
            if re.fullmatch(pattern, path):
                return permission
        return None

    def require_permission(self, permission: str, path: str) -> bool:
        with db() as conn:
            context = workspace_context(conn)
            user = context["current_user"]
            allowed = role_allows(user.get("role"), permission)
            if allowed:
                return True
            workspace = context["workspace"] or {}
            audit_event(
                conn,
                workspace.get("id"),
                "operator",
                "permission_denied",
                "http_route",
                path,
                {"permission": permission, "user_email": user.get("email"), "role": user.get("role")},
            )
        if path.startswith("/api/"):
            self.send_json({"success": False, "error": "Forbidden", "required_permission": permission}, 403)
        else:
            self.send_html(
                "<!doctype html><html><head><title>Forbidden</title></head>"
                "<body><h1>Forbidden</h1><p>Your workspace role cannot perform this action.</p></body></html>",
                403,
            )
        return False

    def current_user_allows(self, permission: str) -> bool:
        with db() as conn:
            context = workspace_context(conn)
            return role_allows(context["current_user"].get("role"), permission)

    def send_clinic_hidden(self) -> None:
        self.send_html(render_not_found(), 404)

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
        self.apply_request_context()
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        if not self.require_login(path):
            return
        if path == "/login":
            if not auth_required() or self.is_authenticated():
                self.redirect("/")
                return
            self.send_html(render_login())
            return
        if path == "/":
            self.send_html(render_dashboard(query))
        elif path == "/healthz":
            self.send_json(health_probe())
        elif path == "/readyz":
            probe = readiness_probe()
            self.send_json(probe, 200 if probe["success"] else 503)
        elif path == "/businesses":
            self.send_html(render_businesses())
        elif re.fullmatch(r"/businesses/\d+", path):
            self.send_html(render_business_detail(int(path.rsplit("/", 1)[1])))
        elif path == "/modules":
            if clinic_mode():
                self.send_clinic_hidden()
                return
            self.send_html(render_modules())
        elif re.fullmatch(r"/modules/[a-z0-9_]+", path):
            if clinic_mode():
                self.send_clinic_hidden()
                return
            self.send_html(render_module_detail(path.rsplit("/", 1)[1]))
        elif path == "/agent-builder":
            if clinic_mode() and not self.current_user_allows("manage_agents"):
                self.send_clinic_hidden()
                return
            self.send_html(render_agent_builder(query))
        elif path == "/knowledge":
            self.send_html(render_knowledge(query))
        elif re.fullmatch(r"/knowledge/\d+", path):
            self.send_html(render_knowledge_document(int(path.rsplit("/", 1)[1])))
        elif path == "/demo-call":
            self.send_html(render_demo_call(query))
        elif path == "/real-calling":
            self.send_html(render_real_calling(query))
        elif path == "/campaigns":
            if clinic_mode():
                self.send_clinic_hidden()
                return
            self.send_html(render_campaigns(query))
        elif re.fullmatch(r"/campaigns/\d+", path):
            if clinic_mode():
                self.send_clinic_hidden()
                return
            self.send_html(render_campaign_detail(int(path.rsplit("/", 1)[1])))
        elif path == "/jobs":
            if clinic_mode() and not self.current_user_allows("run_jobs"):
                self.send_clinic_hidden()
                return
            self.send_html(render_jobs(query))
        elif path == "/leads":
            self.send_html(render_leads(query))
        elif re.fullmatch(r"/leads/\d+", path):
            self.send_html(render_lead_detail(int(path.rsplit("/", 1)[1])))
        elif path == "/bookings":
            self.send_html(render_bookings(query.get("error", [None])[0]))
        elif path == "/calls":
            self.send_html(render_calls())
        elif path == "/qa":
            self.send_html(render_qa(query))
        elif path == "/notifications":
            self.send_html(render_notifications())
        elif path == "/compliance":
            self.send_html(render_compliance(query))
        elif path == "/admin":
            if clinic_mode():
                self.send_clinic_hidden()
                return
            self.send_html(render_admin_health())
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
        elif path == "/api/modules":
            self.send_json(
                {
                    "success": True,
                    "modules": [{"key": key, **module} for key, module in visible_modules().items()],
                }
            )
        elif re.fullmatch(r"/api/modules/[a-z0-9_]+", path):
            key = path.rsplit("/", 1)[1]
            if key not in visible_modules():
                self.send_json({"success": False, "error": "Module not found"}, 404)
                return
            self.send_json({"success": True, "module": module_by_key(key)})
        elif path == "/api/compliance/summary":
            with db() as conn:
                context = workspace_context(conn)
                self.send_json(
                    {
                        "success": True,
                        "workspace": context["workspace"],
                        "current_user": context["current_user"],
                        "workspace_users": context["users"],
                        "role_permissions": context["role_permissions"],
                        "staff_contacts": get_staff_contacts(conn),
                        "consent_records": get_consent_records(conn),
                        "do_not_call": get_dnc_entries(conn),
                        "audit_logs": get_audit_logs(conn),
                    }
                )
        elif path == "/api/workspace":
            with db() as conn:
                self.send_json({"success": True, **workspace_context(conn)})
        elif path == "/api/admin/health":
            self.send_json({"success": True, **system_readiness()})
        elif path == "/api/providers":
            self.send_json({"success": True, "providers": provider_statuses()})
        elif path == "/api/calendar":
            self.send_json({"success": True, "calendars": calendar_statuses()})
        elif path == "/api/voice-runtime":
            business_id = int(query.get("business_id", ["0"])[0] or 0)
            if not business_id:
                self.send_json({"success": True, "runtime": runtime_status()})
            else:
                with db() as conn:
                    try:
                        session = build_runtime_session(
                            conn,
                            business_id,
                            caller_text=query.get("text", [None])[0],
                            requested_language=query.get("language", [None])[0],
                        )
                    except ValueError:
                        self.send_json({"success": False, "error": "Business not found"}, 404)
                        return
                self.send_json({"success": True, "session": session})
        elif re.fullmatch(r"/api/providers/[a-z0-9_]+", path):
            key = path.rsplit("/", 1)[1]
            provider = provider_by_key(key)
            if provider.key != key:
                self.send_json({"success": False, "error": "Provider not found"}, 404)
                return
            self.send_json({"success": True, "provider": provider.health()})
        elif path == "/api/qa/evaluations":
            with db() as conn:
                self.send_json({"success": True, "evaluations": get_qa_evaluations(conn, query.get("status", ["all"])[0])})
        elif path == "/api/campaigns":
            if clinic_mode():
                self.send_json({"success": False, "error": "Feature deferred in clinic mode"}, 404)
                return
            with db() as conn:
                self.send_json({"success": True, "campaigns": get_campaigns(conn)})
        elif path == "/api/jobs":
            if clinic_mode() and not self.current_user_allows("run_jobs"):
                self.send_json({"success": False, "error": "Feature hidden in clinic mode"}, 404)
                return
            with db() as conn:
                self.send_json({"success": True, "jobs": get_jobs(conn, query.get("status", ["all"])[0])})
        elif path == "/api/knowledge/search":
            business_id = int(query.get("business_id", ["0"])[0] or 0)
            language = query.get("language", ["en"])[0]
            with db() as conn:
                self.send_json(
                    {
                        "success": True,
                        "business_id": business_id,
                        "language": language,
                        "results": search_knowledge(conn, business_id, query.get("q", [""])[0], language) if business_id else [],
                    }
                )
        elif path == "/api/twilio/voice":
            self.handle_twilio_voice(query, {})
        else:
            self.send_html(render_not_found(), 404)

    def do_POST(self) -> None:
        self.apply_request_context()
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        if not self.require_login(path):
            return
        if path == "/login":
            form = self.form()
            email = form.get("email", "")
            password = form.get("password", "")
            client_ip = self.client_address[0] if self.client_address else "unknown"
            with db() as conn:
                user, message = authenticate(conn, email, password, client_ip)
            if not user:
                self.send_html(render_login(message, email), 401)
                return
            cookie = build_session_cookie(
                {
                    "workspace_id": int(user["workspace_id"]),
                    "user_email": user["email"],
                    "authenticated": True,
                }
            )
            self.redirect("/", cookie)
            return
        if path == "/logout":
            with db() as conn:
                context = workspace_context(conn)
                audit_event(
                    conn,
                    (context["workspace"] or {}).get("id"),
                    "operator",
                    "logout",
                    "workspace_user",
                    context["current_user"].get("email"),
                    {},
                )
            self.redirect("/login" if auth_required() else "/", build_session_cookie({}, max_age=0))
            return
        if path == "/workspace/switch":
            form = self.form()
            try:
                workspace_id = int(form.get("workspace_id") or 0)
            except ValueError:
                workspace_id = 0
            with db() as conn:
                context = workspace_context(conn, workspace_id or None)
                workspace = context["workspace"]
                current_user = context["current_user"]
                if not workspace:
                    self.redirect("/compliance?saved=workspace+not+found")
                    return
                cookie = build_session_cookie(
                    {
                        "workspace_id": int(workspace["id"]),
                        "user_email": current_user.get("email"),
                        "authenticated": bool(self.session.get("authenticated")),
                    }
                )
            self.redirect(form.get("next") or "/", cookie)
            return
        permission = self.permission_for_post_route(path)
        if permission and not self.require_permission(permission, path):
            return
        if clinic_mode() and path == "/campaigns/create":
            self.send_clinic_hidden()
            return
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
            to_number = form.get("to_number", "")
            with db() as conn:
                business = get_business(conn, business_id)
                if not business:
                    self.redirect("/real-calling?error=business+not+found")
                    return
                if form.get("consent_confirmed") == "yes":
                    record_consent(
                        conn,
                        business_id,
                        to_number,
                        "outbound_call",
                        "real_calling_form",
                        "Operator checked consent confirmation before outbound test call.",
                    )
                allowed, policy_msg = outbound_allowed(conn, business, to_number)
            if allowed:
                result = create_outbound_call(form.get("provider") or "twilio", to_number, business_id)
                ok, msg = result.success, result.message
            else:
                ok, msg = False, policy_msg
            param = "message" if ok else "error"
            self.redirect(f"/real-calling?business_id={business_id}&{param}={urlencode({'x': msg})[2:]}")
            return
        if path == "/campaigns/create":
            form = self.form()
            business_id = int(form.get("business_id") or 1)
            with db() as conn:
                campaign = create_campaign(
                    conn,
                    business_id,
                    form.get("name") or "Outbound campaign",
                    form.get("campaign_type") or "outbound_call",
                    form.get("targets") or "",
                    form.get("script") or "",
                )
                recipients = get_campaign_recipients(conn, int(campaign["id"]))
                queued = sum(1 for row in recipients if row["status"] == "queued")
                suppressed = sum(1 for row in recipients if row["status"] == "suppressed")
            self.redirect(f"/campaigns/{campaign['id']}?saved=queued+{queued}+suppressed+{suppressed}")
            return
        if path == "/jobs/run":
            from .reminders import schedule_appointment_reminders

            with db() as conn:
                schedule_appointment_reminders(conn)
                results = run_due_jobs(conn)
            self.redirect(f"/jobs?ran={len(results)}")
            return
        if path == "/knowledge/ingest":
            form = self.form()
            business_id = int(form.get("business_id") or 0)
            with db() as conn:
                result = ingest_knowledge_document(
                    conn,
                    business_id,
                    form.get("title") or "Knowledge document",
                    form.get("source_type") or "manual",
                    form.get("source") or "",
                    form.get("content") or "",
                )
            if result.get("success"):
                message = f"{result['items']} items added"
            else:
                message = str(result.get("error") or "Unable to add knowledge")
            self.redirect(f"/knowledge?business_id={business_id}&{urlencode({'saved': message})}")
            return
        if path == "/compliance/consent":
            form = self.form()
            business_id = int(form.get("business_id") or 1)
            with db() as conn:
                record_consent(
                    conn,
                    business_id,
                    form.get("phone", ""),
                    form.get("consent_type") or "outbound_call",
                    form.get("source") or "operator",
                    form.get("proof") or "Operator recorded consent.",
                )
            self.redirect("/compliance?saved=consent+recorded")
            return
        if path == "/compliance/dnc":
            form = self.form()
            with db() as conn:
                add_dnc_entry(conn, form.get("phone", ""), form.get("reason", ""), form.get("source") or "operator")
            self.redirect("/compliance?saved=do+not+call+updated")
            return
        status_match = re.fullmatch(r"/leads/(\d+)/status", path)
        if status_match:
            lead_id = int(status_match.group(1))
            status = self.form().get("status", "new")
            if status not in {"new", "contacted", "follow_up", "won", "lost"}:
                status = "new"
            with db() as conn:
                lead = get_lead(conn, lead_id)
                if not lead:
                    self.redirect("/leads")
                    return
                workspace_id = int(lead["workspace_id"] or default_workspace_id(conn))
                conn.execute(
                    "update leads set status=?, updated_at=? where id=? and workspace_id=?",
                    (status, now(), lead_id, workspace_id),
                )
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
                    workspace_id = int(lead["workspace_id"] or default_workspace_id(conn))
                    conn.execute(
                        "update leads set handoff_triggered=1 where id=? and workspace_id=?",
                        (lead_id, workspace_id),
                    )
            self.redirect(f"/leads/{lead_id}")
            return
        delete_match = re.fullmatch(r"/leads/(\d+)/delete", path)
        if delete_match:
            lead_id = int(delete_match.group(1))
            with db() as conn:
                workspace_id = default_workspace_id(conn)
                conn.execute("delete from leads where id=? and workspace_id=?", (lead_id, workspace_id))
            self.redirect("/leads")
            return
        booking_match = re.fullmatch(r"/bookings/(\d+)/status", path)
        if booking_match:
            booking_id = int(booking_match.group(1))
            form = self.form()
            status = form.get("status", "requested")
            idempotency_key = (form.get("idempotency_key") or "").strip() or None
            with db() as conn:
                try:
                    apply_booking_transition(
                        conn,
                        booking_id,
                        status,
                        actor="operator",
                        idempotency_key=idempotency_key,
                        note=form.get("note") or None,
                    )
                    self.redirect("/bookings")
                except WorkflowError:
                    self.redirect("/bookings?error=invalid_transition")
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
            form = self.form()
            if not self.validate_twilio_or_send_error(query, form):
                return
            self.handle_twilio_voice(query, form)
            return
        if path == "/api/twilio/gather":
            form = self.form()
            if not self.validate_twilio_or_send_error(query, form):
                return
            self.handle_twilio_gather(query, form)
            return
        self.send_html(render_not_found(), 404)

    def validate_twilio_or_send_error(self, query: dict[str, list[str]], form: dict[str, str]) -> bool:
        signature = self.headers.get("X-Twilio-Signature")
        url = f"{self.headers.get('X-Forwarded-Proto', app_url().split(':', 1)[0])}://{self.headers.get('Host')}{self.path}"
        if app_url().startswith("https://"):
            url = f"{app_url()}{self.path}"
        ok, message = validate_twilio_signature(url, form, signature)
        required = twilio_signature_required()
        business_id = int((query.get("business_id") or [form.get("business_id") or "1"])[0] or 1)
        if ok:
            return True
        with db() as conn:
            business = get_business(conn, business_id)
            workspace_id = (business or {}).get("workspace_id") or default_workspace_id(conn)
            audit_event(
                conn,
                workspace_id,
                "provider",
                "twilio_signature_warning" if not required else "twilio_signature_rejected",
                "twilio_webhook",
                form.get("CallSid"),
                {"message": message, "required": required, "path": self.path},
            )
        if required:
            self.send_xml(twilio_finish_twiml("Sorry, this call could not be verified."), 403)
            return False
        return True

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
