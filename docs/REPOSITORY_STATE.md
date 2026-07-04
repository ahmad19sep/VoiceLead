# Repository State

Date: 2026-07-04

## Current Baseline

CallPilot AI is a Python-only local SaaS demo for universal AI calling workflows. The app runs with SQLite, a standard-library HTTP server, mock AI call analysis, multi-business demo data, Twilio Voice webhook helpers, and a modular `callpilot/` package.

## Implemented App Structure

- `app.py` is the small local entry point.
- `callpilot/config.py` stores app constants, demo transcripts, and `.env` loading.
- `callpilot/modules.py` stores the PDF-derived industry module registry, workflow states, language policy, compliance rules, and business-type mapping.
- `callpilot/storage.py` owns SQLite connection and schema setup.
- `callpilot/repositories.py` contains database read helpers.
- `callpilot/analysis.py` extracts call fields, scores leads, adds module metadata, and attaches safety/compliance context.
- `callpilot/workflows.py` creates leads, bookings, notifications, call logs, and events.
- `callpilot/telephony.py` contains Twilio/TwiML helpers and outbound-call starter logic.
- `callpilot/http.py` dispatches HTML pages and JSON endpoints.
- `callpilot/views/` contains dashboard, business, module, CRM, calling, operations, and settings pages.
- `tests/` contains lightweight stdlib regression tests for the production module registry.

## Demo-Only Behavior

- SQLite is the development database; PostgreSQL and migrations are not implemented.
- Mock AI analysis is used; OpenAI/Anthropic/realtime runtime adapters are not implemented.
- Demo call simulator creates local leads and bookings; these are not production success states.
- Twilio webhooks exist, but webhook signature verification, recording consent controls, and production call billing records are not complete.
- Bookings are local records; external calendar/PMS/EHR/POS/CRM confirmation is not implemented.
- Notifications are dashboard rows; production SMS/email/Slack/WhatsApp adapters are not complete.

## Production Gaps From PDF Pack

- Multi-tenant workspaces, users, RBAC, staff contacts, and tenant isolation.
- PostgreSQL schema, migrations, indexes, retention jobs, and encrypted sensitive storage.
- Provider adapter interfaces for telephony, voice runtime, AI models, calendars, CRMs, ticketing, and messaging.
- Versioned workflow engine with nodes, transitions, retries, idempotency, human approval, and audit trails.
- Compliance policy engine for healthcare, outbound calling, legal/finance, fair housing, payments, privacy, and regional recording consent.
- Knowledge ingest/search, prompt packs, multilingual voice model routing, QA scorecards, and human review queues.
- Docker, CI, worker process, health/readiness endpoints, and production deployment config.

## Current Verification

- `python -m compileall app.py callpilot`
- `python -m unittest`
- Dashboard smoke test: `GET /`
- Module catalog smoke test: `GET /modules`
- Module API smoke test: `GET /api/modules`
