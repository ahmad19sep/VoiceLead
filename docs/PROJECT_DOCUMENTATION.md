# CallPilot AI — Project Documentation

Project folder: `VoiceLead` &nbsp;|&nbsp; Product name: **CallPilot AI** &nbsp;|&nbsp; Last updated: 2026-07-05

---

## 1. What This Project Is

CallPilot AI is a Python-only, local-first AI calling agent platform. Its current focus is the **clinic launch path**: an AI receptionist for clinics that answers patient calls, captures appointment requests, routes urgent cases to humans, and keeps demo behavior visibly separate from real production success.

The long-term vision is a **universal AI calling agent for any business** (hotels, clinics, home services, restaurants, software agencies, law firms, and more). That universal platform remains in the codebase but is frozen behind `PLATFORM_MODE=universal` while the clinic critical path is built. The default mode is `PLATFORM_MODE=clinic`.

### Core design principles

- **Zero mandatory dependencies.** The app runs entirely on the Python standard library with SQLite and mock AI. No Node, npm, Supabase, OpenAI, Claude, Vapi, Twilio, or paid API key is required for the local demo.
- **No fake success.** Provider integrations report honest status. A booking is never marked calendar-confirmed without a real event id; the voice runtime reports Vapi/Retell as *not live* even when API keys are present, until a real runtime adapter exists. See `docs/PRODUCT_DEFINITION.md` for the full forbidden-behavior rules.
- **Versioned, audited workflows.** Appointment bookings move through the versioned `clinic-v1` state machine with allowed-transition enforcement, terminal locks, idempotency keys, and audit trails.
- **Graceful degradation.** Every external integration has a local fallback: SQLite instead of Postgres, mock AI instead of LLM APIs, keyword matching instead of vector search, dashboard notifications instead of SMS/email/Slack.

---

## 2. Platform Modes

| Mode | How to enable | Behavior |
|---|---|---|
| `clinic` (default) | `PLATFORM_MODE=clinic` or unset | Only healthcare modules are active; all others are `deferred`. Sidebar hides Modules, Campaigns, and Admin Health; Jobs and Agent Builder are role-gated; Leads is relabeled **Patients/Inquiries**. `/modules` and `/campaigns` return `404`. Business types are limited to Clinic, Hospital, Dentist. |
| `universal` | `PLATFORM_MODE=universal` | Full industry module registry, campaigns, and admin surfaces are exposed. Use only when intentionally working on the deferred universal roadmap. |

Mode logic lives in `callpilot/config.py` (`platform_mode()`, `clinic_mode()`, `business_types_for_mode()`).

---

## 3. Quick Start

### Run locally

```bash
python app.py
```

Open `http://127.0.0.1:8000`. The SQLite database `callpilot.db` is created and seeded automatically on first run.

### Run with Docker

```bash
docker build -t callpilot-ai .
docker run --rm -p 8000:8000 callpilot-ai
```

Or, for a persistent setup with the web app and background worker sharing one SQLite volume:

```bash
docker compose up --build
```

Compose stores the database in the `callpilot-data` volume at `/data/callpilot.db`.

### Run the background worker

```bash
python worker.py --once    # process due jobs once and exit
python worker.py           # polling worker
```

Tune with `WORKER_POLL_INTERVAL` and `WORKER_BATCH_LIMIT`.

### Reset the database

Stop the app, delete `callpilot.db`, and start again.

---

## 4. Architecture

The app is a layered, standard-library-only web application:

```
app.py                      entry point
worker.py                   background job runner entry point
callpilot/
  server.py                 HTTP server startup (host/port from env)
  http.py                   request handler and route dispatch (GET/POST)
  views/                    server-rendered HTML pages
  ── domain layer ──
  analysis.py               mock AI call analysis, field extraction, lead scoring
  workflows.py              lead, booking, notification, call log, event creation
  clinic_workflow.py        versioned clinic-v1 appointment state machine
  scheduling.py             booking-transition → calendar action mapping + sync audit
  calendar.py               Google Calendar adapter contract (honest pending state)
  voice_runtime.py          clinic-voice-v1 trilingual (EN/UR/AR) prompt packs,
                            language detection, runtime session assembly
  knowledge.py              versioned knowledge ingest, approval, language-aware search
  campaigns.py              outbound campaign planning and suppression
  jobs.py                   durable job queue and manual worker helpers
  qa.py                     rule-based call QA scoring and evaluation backfill
  compliance.py             workspace, consent, Do Not Call, outbound policy, audit
  clinic.py                 clinic profile/providers/locations/holidays onboarding
  modules.py                PDF-pack industry module registry and workflow states
  ── integration layer ──
  providers.py              provider adapter registry (telephony, AI, voice, STT, TTS)
  telephony.py              Twilio/TwiML helpers and outbound-call starter
  security.py               provider readiness and webhook signature validation
  sessions.py               signed local session cookies for workspace selection
  ── data layer ──
  storage.py                SQLite connection and schema setup
  repositories.py           workspace-scoped database read helpers
  seed.py                   demo data seeding
  ── support ──
  config.py                 constants, PLATFORM_MODE, score rules, .env loading
  stats.py, ui.py, utils.py, integrations.py
```

### Request flow (inbound call, demo or Twilio)

1. A transcript arrives — from the Demo Call Simulator (`/demo-call`), the generic voice webhook (`POST /api/voice/webhook`), or Twilio (`POST /api/twilio/voice` → `/api/twilio/gather`).
2. `analysis.py` extracts fields (name, phone, need, timeline), detects language, applies regulated-advice guardrails, and scores the lead against `SCORE_RULES` (hot/warm/cold).
3. `workflows.py` creates the lead, and — if the call is ready-to-book or urgent — a booking and a human-handoff notification, plus call logs and timeline events.
4. Bookings enter the `clinic-v1` state machine at `requested`. Transitions (confirm, reschedule, cancel, etc.) are validated, audited in `clinic_workflow_transitions`, and mapped by `scheduling.py` to calendar create/reschedule/cancel actions recorded in `booking_calendar_syncs`.
5. `qa.py` scores the call for safety, workflow integrity, language handling, and next-step quality, feeding the `/qa` review queue.

### Multi-tenancy and security (local foundation)

- A default **workspace** with a default **owner user** is seeded; role policy metadata defines owner/staff/viewer capabilities.
- Workspace selection is stored in a **signed session cookie** (`sessions.py`); all repository reads are workspace-scoped.
- Local **mutation-route RBAC** checks return `403` for insufficient roles (e.g., viewer attempting a protected write).
- Twilio webhook **signature validation** is supported and enforced in production (`TWILIO_REQUIRE_SIGNATURE`).
- This is a local demo foundation: real authentication, invitations, and encrypted secret storage are not yet implemented.

---

## 5. Data Model (SQLite)

Schema is defined in `callpilot/storage.py`. Tables by area:

| Area | Tables |
|---|---|
| Tenancy & access | `workspaces`, `workspace_users`, `staff_contacts` |
| Businesses & config | `businesses`, `services`, `settings` |
| Clinic onboarding | `clinic_profiles`, `clinic_providers`, `clinic_locations`, `clinic_holidays` |
| Knowledge | `knowledge_base`, `knowledge_documents` (versioned, approval-gated, per-language with `translation_group_id`) |
| CRM & calls | `leads`, `bookings`, `call_logs`, `call_sessions`, `notifications`, `agent_events` |
| Workflow & scheduling | `clinic_workflow_transitions` (audit trail), `booking_calendar_syncs` (calendar sync attempts) |
| Compliance | `consent_records`, `do_not_call`, `audit_logs` |
| QA | `qa_evaluations` |
| Outbound & jobs | `campaigns`, `campaign_recipients`, `jobs` |

Bookings carry `calendar_sync_status` and `calendar_event_id`; both stay honestly `pending` until a live Google Calendar client is wired.

---

## 6. Web Pages

### Standard pages (clinic mode)

| Route | Purpose |
|---|---|
| `/` | Dashboard |
| `/businesses` | Business agents |
| `/knowledge` | Versioned knowledge ingest, approval, and search |
| `/demo-call` | Demo call simulator with sample transcripts |
| `/real-calling` | Twilio phone number connection and outbound test calls |
| `/leads` | Patients/Inquiries CRM |
| `/bookings` | Booking requests with workflow status and calendar sync column |
| `/calls` | Call logs |
| `/qa` | QA evaluation queue |
| `/notifications` | Human handoff alerts |
| `/compliance` | Consent, Do Not Call, staff handoff contacts, audit logs |
| `/settings` | Integration status and demo mode settings |

### Operator-only or universal-mode pages

| Route | Purpose |
|---|---|
| `/agent-builder` | Internal operator tool for configuring clinics (C1 onboarding fields) |
| `/jobs` | Operator job queue visibility |
| `/modules` | Universal-mode module registry (404 in clinic mode) |
| `/campaigns` | Outbound campaigns (404 in clinic mode until appointment reminders land) |
| `/admin` | Universal/admin health surface |

---

## 7. API Reference

### Health & platform

| Method | Route | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness probe |
| GET | `/readyz` | Readiness probe (includes database check) |
| GET | `/api/workspace` | Active workspace info |
| POST | `/workspace/switch` | Switch active workspace (signed cookie) |
| GET | `/api/admin/health` | Admin health surface |

### Businesses, modules, providers

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/businesses` | List businesses |
| GET | `/api/businesses/{id}/readiness` | Per-business readiness |
| GET | `/api/modules` | Module registry (healthcare-only in clinic mode) |
| GET | `/api/modules/{module_key}` | Single module detail |
| GET | `/api/providers` | Provider adapter registry and health |
| GET | `/api/providers/{provider_key}` | Single provider status |
| GET | `/api/calendar` | Google Calendar adapter status (honest not-connected) |
| GET | `/api/voice-runtime` | Runtime status; with `?business_id=&text=` returns session config with detected language |

### Calls & analysis

| Method | Route | Purpose |
|---|---|---|
| POST | `/api/ai/analyze-call` | Analyze a transcript (mock AI) |
| POST | `/api/voice/webhook` | Generic voice-provider webhook |
| POST | `/api/twilio/voice` | Twilio inbound call webhook (TwiML) |
| POST | `/api/twilio/gather` | Twilio speech-gather callback |

Example voice webhook payload:

```json
{
  "business_id": 1,
  "call_id": "call_123",
  "caller_phone": "0300-1234567",
  "transcript": "Full transcript here",
  "recording_url": "https://example.com/audio.mp3",
  "provider": "vapi"
}
```

### CRM, knowledge, QA, operations

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/leads` | List leads |
| GET | `/api/knowledge/search?business_id=1&q=...` | Approved-knowledge search (language-preferred with English fallback and `translated` flag) |
| GET | `/api/qa/evaluations` | QA evaluation list |
| GET | `/api/campaigns` | Campaign list |
| GET | `/api/jobs` | Job queue list |
| GET | `/api/compliance/summary` | Compliance summary |

### Form-post routes (HTML pages)

`/agent-builder/create`, `/demo-call/analyze`, `/real-calling/outbound`, `/campaigns/create` (404 in clinic mode), `/jobs/run`, `/knowledge/ingest`, `/compliance/consent`, `/compliance/dnc`, `/settings/update`, and booking status transitions via `/bookings/{id}/status` (invalid transitions rejected).

---

## 8. Configuration

All configuration is via environment variables, loaded from `.env` (see `.env.example` for the full template). Everything is optional — missing keys keep the app in demo mode.

| Group | Variables | Notes |
|---|---|---|
| App | `APP_NAME`, `APP_ENV`, `PLATFORM_MODE`, `APP_URL`, `SECRET_KEY` | `PLATFORM_MODE` defaults to `clinic`; `SECRET_KEY` signs workspace cookies |
| Database | `DATABASE_MODE`, `SQLITE_DB_PATH`, `DB_PATH`, `SUPABASE_*` | SQLite by default; Supabase/Postgres not yet implemented |
| Vector search | `VECTOR_MODE`, `QDRANT_*`, `PINECONE_*` | Local keyword matching by default |
| AI | `AI_PROVIDER`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | Mock AI used when absent |
| Voice/telephony | `VOICE_RUNTIME`, `VAPI_API_KEY`, `RETELL_API_KEY`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`, `TWILIO_REQUIRE_SIGNATURE` | Twilio webhooks work today; Vapi/Retell honestly reported not-live |
| Speech | `ELEVENLABS_API_KEY`, `DEEPGRAM_API_KEY` | Future TTS/STT |
| Calendar | `GOOGLE_CALENDAR_ID`, `GOOGLE_CALENDAR_CREDENTIALS` | Adapter contract exists; live client not wired |
| Notifications | `SMTP_*`, `SLACK_WEBHOOK_URL`, `WHATSAPP_API_KEY` | Dashboard notifications used instead |
| Worker | `WORKER_POLL_INTERVAL`, `WORKER_BATCH_LIMIT` | Polling worker tuning |

### Real calling with Twilio (local testing)

Twilio cannot reach `127.0.0.1`, so tunnel first (`ngrok http 8000`), set `APP_URL` and the `TWILIO_*` keys in `.env`, restart, then point your Twilio number's voice webhook at:

```
POST https://<your-tunnel>/api/twilio/voice?business_id=1
```

Full walkthrough in `README.md` → "Real Calling With Twilio".

---

## 9. Voice Runtime & Languages

`callpilot/voice_runtime.py` ships the versioned **`clinic-voice-v1`** prompt packs in **English, Urdu, and Arabic**, each covering: greeting, recording disclosure, booking/contact prompts, a safe emergency script with an explicit no-medical-advice refusal, human handoff, fallback, and closing.

- `detect_language_code` recognizes English, Urdu script, Roman Urdu, and Arabic script; unsupported languages fall back to the clinic's default with a flag.
- `build_runtime_session` assembles a per-clinic session config (prompts, knowledge language, policies), served by `GET /api/voice-runtime`.
- Knowledge items carry `language` (`en`/`ur`/`ar`) and `translation_group_id`; search prefers the caller's language and falls back to English with `translated=true`.
- Runtime status honestly reports Vapi/Retell as **not live** until a real adapter exists — no agent answers a real number yet.

---

## 10. Clinic Critical Path Status (C0–C11)

Tracked in detail in `docs/GOAL_COMPLETION_MATRIX.md`. Summary:

| Phase | Scope | Status |
|---|---|---|
| C0 | Clinic mode freeze (hide non-clinic surface) | ✅ Implemented |
| C1 | Clinic onboarding (profile, services, providers, locations, hours, policies) | 🟡 Partial — local schema and operator save path done; browser E2E evidence and stricter validation remain |
| C2 | Per-language approved knowledge with translation groups | 🟡 Partial |
| C3 | Versioned, audited `clinic-v1` booking state machine | 🟡 Partial — local machine done; remaining lifecycle actors need wiring |
| C4 | Google Calendar create/cancel/reschedule | 🟡 Partial — adapter and sync audit done; live API client not wired |
| C5 | Trilingual voice runtime foundation | 🟡 Partial — prompt packs, detection, session config done; live Vapi/Retell adapter missing |
| C6 | Emergency detection and escalation (EN/UR/AR, PHI-free alerts) | 🔴 Missing |
| C7 | Policy-gated appointment reminders with opt-out | 🔴 Missing |
| C8 | Security hardening (real auth, encrypted secrets, rate limiting) | 🟡 Partial |
| C9 | Golden QA harness per language in CI | 🔴 Missing |
| C10–C11 | Production deployment (Postgres/Redis compose, migrations, fresh-clone dry run) | 🟡 Partial |

### Known production gaps

- No real authentication or user invitations (local session-backed RBAC only).
- SQLite only; no PostgreSQL schema, migrations, or encrypted storage.
- Provider adapters beyond Twilio outbound dispatch are stubs with honest status.
- Notifications are dashboard rows; no SMS/email/Slack/WhatsApp delivery.
- No hosted deployment or secrets management.

---

## 11. Testing & Verification

### Automated tests (stdlib `unittest`)

```bash
python -m compileall app.py worker.py callpilot
python -m unittest discover -s tests -p "test*.py"
```

Test coverage by file:

| Test file | Covers |
|---|---|
| `test_platform_mode.py` | Clinic/universal mode gating and 404s |
| `test_module_registry.py` | Industry module registry, active/deferred status |
| `test_clinic_profile.py` | C1 onboarding persistence (profile, services, providers, locations, closures) |
| `test_knowledge_language.py` | C2 language-preferred retrieval with English fallback |
| `test_clinic_workflow.py` | C3 state machine: valid/invalid/terminal transitions, idempotent replay |
| `test_clinic_scheduling.py` | C4 honest pending calendar sync, no fabricated event ids |
| `test_voice_runtime.py` | C5 prompt packs, language detection, not-live runtime status |
| `test_workspace_rbac.py` | Workspace seeding, scoped reads, mutation RBAC |
| `test_sessions.py` | Signed workspace cookies |
| `test_provider_registry.py` | Provider adapter registry |
| `test_worker.py` | Job worker |
| `test_health_probes.py` | `/healthz`, `/readyz` |
| `test_server_config.py`, `test_storage_config.py` | Server and storage env configuration |

### Smoke checks

Worker: `python worker.py --once --limit 1` · Compose: `docker compose config` · Dashboard: `GET /` · plus the API smoke tests listed in `docs/REPOSITORY_STATE.md` → "Current Verification".

### CI

`.github/workflows/ci.yml` runs compile, unit tests, and local probe smoke checks on push and pull request.

---

## 12. Documentation Map

| Document | Purpose |
|---|---|
| `README.md` | Run instructions, feature list, Twilio setup |
| `docs/PROJECT_DOCUMENTATION.md` | This file — full project reference |
| `docs/REPOSITORY_STATE.md` | Current architecture map and production gaps (kept in sync with code) |
| `docs/PRODUCT_DEFINITION.md` | Product rules and forbidden fake-success behavior |
| `docs/GOAL_COMPLETION_MATRIX.md` | Clinic C0–C11 requirement-by-requirement status with evidence |
| `docs/PDF_IMPLEMENTATION_NOTES.md` | PDF pack implementation notes and next phases |
| `docs/evidence/` | Screenshot and verification evidence |
