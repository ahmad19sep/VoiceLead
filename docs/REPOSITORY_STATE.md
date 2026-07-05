# Repository State

Date: 2026-07-05

## Current Baseline

CallPilot AI is a Python-only local SaaS demo now scoped to the clinic launch critical path by default. The app runs with SQLite, a standard-library HTTP server, mock AI call analysis, multi-business demo data, Twilio Voice webhook helpers, and a modular `callpilot/` package.
The current tenant foundation includes a default workspace, default owner user, role policy metadata, workspace-scoped read helpers, signed local session cookies for active workspace selection, local mutation-route RBAC checks, and compliance/audit visibility. It is still a local demo without real authentication or invitation-backed user onboarding.

## Implemented App Structure

- `app.py` is the small local entry point.
- `callpilot/config.py` stores app constants, `PLATFORM_MODE`, demo transcripts, and `.env` loading.
- `callpilot/clinic.py` stores clinic onboarding helpers for profile validation, providers/doctors, locations, holidays, and startup backfill.
- `callpilot/modules.py` stores the PDF-derived industry module registry, workflow states, language policy, compliance rules, business-type mapping, and active/deferred module status.
- `callpilot/clinic_workflow.py` stores the versioned `clinic-v1` appointment state machine, allowed-transition rules, terminal locks, idempotent transition application, and audited booking transitions.
- `callpilot/calendar.py` stores the Google Calendar adapter contract with honest unavailable/pending behavior that never fabricates a confirmed event id.
- `callpilot/scheduling.py` maps clinic workflow transitions to calendar create/cancel/reschedule actions and persists booking calendar sync state and attempt audit rows.
- `callpilot/voice_runtime.py` stores the versioned `clinic-voice-v1` trilingual (EN/UR/AR) prompt packs, language-code detection, clinic language-policy fallback, runtime session assembly, and honest Vapi/Retell not-live status.
- `callpilot/emergency.py` stores the versioned `clinic-emergency-v1` trilingual emergency phrase lists, fuzzy detection, phone masking, and PHI-free staff escalation alerts with audit trails.
- `callpilot/reminders.py` stores the versioned `clinic-reminder-v1` policy-gated appointment reminder job: single-attempt scheduling, opt-out/consent/DNC gates, quiet-hours deferral, trilingual scripts with opt-out sentences, and honest Twilio-backed delivery.
- `callpilot/auth.py` stores PBKDF2 password hashing, login rate limiting with lockout, the `AUTH_REQUIRED` gate, and admin/one-time owner credential bootstrap; `callpilot/views/auth_pages.py` renders the login page.
- `callpilot/golden.py` stores the versioned `clinic-golden-v1` golden call harness (script loader, hallucination and safety checks, suite runner, CI CLI); `tests/golden_calls/` holds the EN/UR/AR golden scripts.
- `render.yaml` and `docs/DEPLOY_FREE.md` support a free Render deploy with auth on, generated secrets, and an optional read-only demo-viewer account; the server honors platform-injected `PORT`.
- `callpilot/google_calendar.py` is the live Google Calendar API client (service-account RS256 JWT via the `cryptography` package — the single non-stdlib dependency in `requirements.txt` — token caching, create/cancel/reschedule with real event ids); `callpilot/views/calendar_page.py` renders the in-app week-grid appointment calendar with a needs-a-date bucket.
- `callpilot/providers.py` stores provider adapters, provider health, Twilio outbound dispatch, and Twilio signature validation helpers.
- `callpilot/sessions.py` stores signed local session-cookie helpers for workspace selection.
- `callpilot/storage.py` owns SQLite connection and schema setup.
- `callpilot/repositories.py` contains database read helpers.
- `callpilot/analysis.py` extracts call fields, scores leads, adds module metadata, and attaches safety/compliance context.
- `callpilot/workflows.py` creates leads, bookings, notifications, call logs, and events.
- `callpilot/telephony.py` contains Twilio/TwiML helpers and outbound-call starter logic.
- `callpilot/worker.py` and `worker.py` run due background jobs once or as a polling worker.
- `callpilot/http.py` dispatches HTML pages and JSON endpoints.
- `callpilot/views/` contains dashboard, business, module, CRM, calling, operations, and settings pages.
- `.github/workflows/ci.yml` runs compile, unit, and local probe smoke checks on push and pull request.
- `Dockerfile` builds a stdlib-only Python image with `/readyz` health checks and env-configurable host/port.
- `docker-compose.yml` runs the web app and worker with a shared persistent SQLite volume.
- `tests/` contains lightweight stdlib regression tests for the production module registry.
- `tests/test_workspace_rbac.py` covers default workspace owner seeding and workspace-scoped repository reads.

## Demo-Only Behavior

- SQLite is the development database; PostgreSQL and migrations are not implemented.
- Mock AI analysis is used; OpenAI/Anthropic/realtime runtime adapters are not implemented.
- Google Calendar sync is live when `GOOGLE_CALENDAR_ID`/`GOOGLE_CALENDAR_CREDENTIALS` are configured: confirmed bookings create real events (real event ids), reschedules patch them, cancellations delete them; without valid credentials the sync stays honestly pending.
- Demo call simulator creates local leads and bookings; these are not production success states.
- Twilio webhooks exist with signature verification support; recording consent controls and production call billing records are not complete.
- Bookings are local records with a Google Calendar sync seam (C4); external calendar confirmation stays honestly pending until the live Google API client is wired, and PMS/EHR/POS/CRM confirmation is not implemented.
- Notifications are dashboard rows; production SMS/email/Slack/WhatsApp adapters are not complete.
- `/healthz` and `/readyz` expose local service and database readiness probes.
- `PLATFORM_MODE=clinic` is the default; universal mode can be enabled explicitly with `PLATFORM_MODE=universal`.
- In clinic mode, Modules, Campaigns, and Admin Health are hidden, Jobs and Agent Builder are role-gated, and Leads is labeled Patients/Inquiries in the sidebar.
- Clinic C1 local onboarding exists for clinic profile fields, services with durations/provider/location, providers/doctors, locations, holidays/weekly closures, insurance, cancellation, after-hours, emergency, language, timezone, reminder, and recording-disclosure policy.
- Clinic C2 local knowledge language metadata exists for approved answers: each knowledge item can store `language` (`en`, `ur`, `ar`) and `translation_group_id`, and knowledge search prefers the caller language before falling back to English with a `translated` flag.
- Clinic C3 versioned appointment workflow exists: bookings move through a `clinic-v1` state machine (requested, confirmed, reminded, rescheduled, completed, cancelled, no_show) with allowed-transition enforcement, terminal locks, idempotency keys, a `clinic_workflow_transitions` audit trail, lead-timeline events, and a booking-status route that only offers valid transitions and rejects invalid ones.
- Clinic C4 scheduling exists locally: a Google Calendar adapter and `callpilot/scheduling.py` map confirmed/rescheduled/cancelled transitions to calendar create/reschedule/cancel actions, persisting `calendar_sync_status` and `calendar_event_id` on bookings plus a `booking_calendar_syncs` audit trail. Because no live Google API client is wired, bookings stay honestly `pending`/`pending_cancel` with no fabricated event ids; a real client is required before bookings become truly confirmed on an external calendar.
- Clinic C5 voice runtime foundation exists locally: versioned EN/UR/AR prompt packs (greeting, recording disclosure, booking/contact prompts, safe emergency script with explicit no-medical-advice refusal, handoff, fallback, closing), trilingual language-code detection, clinic language-policy fallback, and `GET /api/voice-runtime` session config. The runtime status honestly reports Vapi/Retell as not live — even with API keys — until a real runtime adapter is implemented, so no agent answers a real number yet.
- Clinic C6 emergency escalation exists locally: trilingual (EN/Roman Urdu/Urdu script/Arabic) emergency phrase detection with fuzzy typo matching rides every analyzed call, forces emergency urgency and human handoff, and escalates through a PHI-free `emergency_alert` notification (masked callback number, caller language, no symptoms/names/transcripts) plus `emergency_escalated` timeline and audit events. Alerts are dashboard rows; real SMS/call alert channels are not yet implemented.
- Clinic C7 reminders exist locally: the worker and `/jobs/run` schedule exactly one `appointment_reminder` job per confirmed clinic booking when the clinic enables reminders, honoring the reminder offset, opt-out/DNC, consent, outbound policy, and the business calling window (deferral does not consume the single attempt). Reminder scripts are trilingual with opt-out sentences. Delivery is honest: without a configured Twilio account the notification records `failed` and the booking stays `confirmed`; only a real provider call id transitions it to `reminded` through the C3 state machine.
- Clinic C8 security hardening exists: real password login with PBKDF2 hashing, rate-limited and audited login attempts, `AUTH_REQUIRED` enforcement (on by default in production) with public health probes and provider webhooks, `ADMIN_EMAIL`/`ADMIN_PASSWORD` or one-time owner password bootstrap, security headers on every response, and production readiness blockers for default secrets or disabled auth. Locally auth stays off by default so the demo remains one-command; set `AUTH_REQUIRED=true` to enforce login.

## Production Gaps From PDF Pack

- User invitation flows, password reset/change UI, and broader production-grade authorization beyond password login plus mutation-route RBAC.
- PostgreSQL schema, migrations, indexes, retention jobs, and encrypted sensitive storage.
- Provider adapter implementations beyond Twilio outbound dispatch, including Vapi, Retell, realtime AI, calendars, CRMs, ticketing, and messaging.
- Versioned workflow engine with nodes, transitions, retries, idempotency, human approval, and audit trails.
- Compliance policy engine for healthcare, outbound calling, legal/finance, fair housing, payments, privacy, and regional recording consent.
- Knowledge ingest/search, prompt packs, multilingual voice model routing, QA scorecards, and human review queues.
- Hosted production deployment, secrets management, and managed database configuration.
- The C0-C11 local clinic critical path is complete; the fresh-clone dry run is recorded in `docs/evidence/FRESH_CLONE_REPORT.md`. What remains is credential-gated: live Twilio/Vapi/Retell/Google Calendar integrations with recorded proof calls, a hosted production instance, and post-revenue postgres/migrations plus fake-provider E2E in CI. C3 delivered the versioned booking state machine, C4 calendar sync seams, C5 trilingual prompt packs and session config, C6 emergency detection with PHI-free escalation, C7 the policy-gated reminder job, C8 real password authentication, and C9 the golden EN/UR/AR call harness in CI — but the live Google Calendar API client, a live Vapi/Retell runtime adapter, real Twilio delivery, user invitations/password reset, and real alert channels await real credentials.
- C1 still needs richer UI/browser E2E evidence and stricter field-level validation before production, but the local schema, internal operator save path, and persistence tests are implemented.

## Current Verification

- `python -m compileall app.py worker.py callpilot`
- `python -m unittest discover -s tests -p "test*.py"`
- Worker smoke test: `python worker.py --once --limit 1`
- Compose config validation: `docker compose config`
- Dashboard smoke test: `GET /`
- Module catalog smoke test: `GET /modules`
- Module API smoke test: `GET /api/modules`
- Clinic mode freeze smoke test: `/api/modules` returns only healthcare, `/modules` and `/campaigns` return `404`.
- Universal mode smoke test: `/api/modules` returns the full deferred registry when `PLATFORM_MODE=universal`.
- Clinic onboarding persistence test: create a second real-shaped clinic through the Agent Builder save path, then verify profile, service duration/provider/location, providers, locations, and weekly closure rows.
- Multilingual knowledge retrieval test: ingest same FAQ in English, Urdu, and Arabic, prefer requested language, fall back to English with `translated=true`, and exclude unapproved items.
- Clinic workflow state machine test: apply valid booking transitions and verify status/transition/audit rows, reject invalid and terminal-state transitions, confirm idempotent replay with a key writes once, and confirm booking creation records the initial `requested` state.
- Clinic scheduling test: an unconnected and a credentialed-but-clientless Google Calendar both leave a booking `pending` with no fabricated event id, and confirm/cancel transitions record the mapped calendar sync attempt.
- Calendar status smoke test: `GET /api/calendar` reports the Google Calendar adapter as not connected / not production-ready.
- Voice runtime test: prompt packs cover EN/UR/AR with recording disclosure and no-medical-advice emergency scripts, language detection maps English/Roman Urdu/Urdu script/Arabic correctly, unsupported languages fall back to the clinic default with a flag, and runtime status stays not-live even with a Vapi/Retell API key present.
- Voice runtime API smoke test: `GET /api/voice-runtime` (status) and `GET /api/voice-runtime?business_id=&text=` (session config with detected language).
- Emergency escalation test: EN/Roman Urdu/Urdu script/Arabic phrases and latin-script typos are detected, urgent-but-not-medical calls are not flagged, and an emergency call produces a PHI-free alert (masked number, no symptoms/phrase/name/transcript) with audit and timeline events while normal bookings produce none.
- Reminder job test: one job per confirmed booking with `max_attempts=1`, scheduling at the reminder offset, policy suppression (outbound disabled/opt-out/consent), quiet-hours deferral with attempts reset to zero, honest provider-unavailable results with failed notifications and no fake `reminded` state, and a mocked provider call id transitioning the booking to `reminded`.
- Auth test: password hash/verify with unique salts, seeded-owner login, short-password rejection, five-failure lockout with audit, admin env bootstrap, one-time owner password, and live HTTP flows (redirect to `/login`, 401 APIs, login sets session, logout revokes, security headers present).
- Golden call harness: `python -m callpilot.golden` and `tests/test_golden_calls.py` run 10 EN/UR/AR golden scripts with per-language booking/emergency/noise/advice/hallucination expectations plus universal grounding and no-medical-advice checks; CI fails on any regression.
- Demo viewer test: seeded read-only account logs in over HTTP, browses the dashboard, and receives `403` on mutation routes; seeding is idempotent.
- Server port test: platform-injected `PORT` is honored and `APP_PORT` takes precedence.
- Provider API smoke test: `GET /api/providers`
- Workspace API smoke test: `GET /api/workspace`
- Workspace switch smoke test: `POST /workspace/switch`
- RBAC denial smoke test: protected local mutation returns `403` for a viewer role.
- Health probe smoke test: `GET /healthz`
- Readiness probe smoke test: `GET /readyz`
