# Universal AI Calling Platform PDF Implementation Notes

Source pack reviewed: `00` master architecture plus modules `01` through `12`, dated 2026-07-04.

## Implemented In This Slice

- Added a reusable industry module registry in `callpilot/modules.py` instead of hard-coding one industry.
- Added production configuration fields per business:
  - module key
  - intake fields
  - allowed call types
  - blocked outcomes
  - supported languages
  - compliance profile
  - consent policy
  - recording disclosure
  - quiet hours
  - max outbound attempts
  - integration targets
  - QA checks
  - workflow version
- Added startup SQLite migration/backfill for existing local databases.
- Expanded Agent Builder to edit the new production configuration fields.
- Expanded Business Detail to display module configuration, allowed workflows, and blocked outcomes.
- Added `GET /api/businesses/{id}/readiness` for production readiness checks.
- Updated mock call analysis to carry:
  - detected language
  - module key
  - workflow version
  - compliance profile
  - blocked outcomes
  - unsupported language flag
  - regulated advice-request flag
- Added stronger handoff behavior for regulated advice, unsupported language, emergencies, complaints, and high-value signals.

## Implemented In Next Slice

- Added default workspace foundation for the SaaS multi-tenant roadmap.
- Added workspace-aware schema fields for businesses, leads, bookings, call logs, call sessions, notifications, and agent events.
- Added staff handoff contacts, consent records, Do Not Call entries, and audit logs.
- Added `/compliance` Compliance Center page.
- Added `GET /api/compliance/summary`.
- Added outbound policy enforcement before Twilio calls:
  - phone is required
  - DNC blocks calls
  - max outbound attempts of `0` disables outbound
  - active outbound consent is required
- Added an operator consent checkbox on the outbound test-call form.
- Added audit events for consent, DNC, blocked outbound calls, seeded businesses, and Agent Builder saves.

## Implemented In Provider Hardening Slice

- Added Twilio webhook signature validation.
- Added production enforcement with `APP_ENV=production` or `TWILIO_REQUIRE_SIGNATURE=true`.
- Demo/local mode still accepts unsigned Twilio-style requests but writes audit warnings.
- Added provider readiness checks for Twilio, OpenAI, Vapi, Retell, Deepgram, and ElevenLabs.
- Added `/admin` Admin Health page.
- Added `GET /api/admin/health`.
- Added public URL, signature requirement, provider connection, and launch blocker reporting.

## Implemented In QA Review Slice

- Added `qa_evaluations` storage with automatic startup backfill for existing call logs.
- Added `callpilot/qa.py` with rule-based QA scoring for:
  - transcript presence
  - contact or handoff capture
  - summary quality
  - regulated safety guardrails
  - booking integrity
  - language policy handling
  - actionable next step
- Added automatic QA evaluation after every analyzed call.
- Added QA events into each lead timeline.
- Added `/qa` QA Review page.
- Added `GET /api/qa/evaluations`.
- Added QA summaries to lead detail pages.

## Implemented In Campaign Planning Slice

- Added `campaigns` and `campaign_recipients` tables.
- Added `callpilot/campaigns.py` for target parsing and suppression checks.
- Added `/campaigns` page to create plan-only outbound campaigns.
- Added campaign detail pages showing queued and suppressed recipients.
- Added `GET /api/campaigns`.
- Applied suppression before queueing:
  - missing phone
  - Do Not Call
  - outbound disabled by business policy
  - missing active outbound consent
- Campaigns do not auto-dial; they prepare a compliant queue for a later worker/provider slice.

## Implemented In Job Queue Slice

- Added `jobs` table with durable pending/running/completed/failed states.
- Added `callpilot/jobs.py` manual worker helpers.
- Added campaign recipient preparation jobs when compliant campaign recipients are queued.
- Added `/jobs` page with job counts and a manual `Run Due Jobs` action.
- Added `GET /api/jobs`.
- Running due campaign jobs re-checks DNC, consent, and business max-attempt policy before marking a recipient `ready`.
- The worker still does not place phone calls; it prepares recipients for a future provider dialer adapter.

## Implemented In Provider Adapter Slice

- Added `callpilot/providers.py` with a reusable provider adapter contract.
- Added a real Twilio Voice adapter for outbound-call creation through the existing Twilio implementation.
- Added honest unavailable adapter behavior for OpenAI, Vapi, Retell, Deepgram, and ElevenLabs until their runtime adapters are implemented.
- Moved provider readiness, public URL checks, production environment checks, and Twilio signature validation into the shared provider layer.
- Kept `callpilot/security.py` as the production-readiness policy layer.
- Added `GET /api/providers` and `GET /api/providers/{provider_key}`.
- Expanded Admin Health provider rows with provider category and capabilities.
- Added provider registry and Twilio signature regression tests.

## Implemented In Tenant RBAC Slice

- Added default workspace owner seeding through `workspace_users`.
- Added reusable role metadata and permission checks for owner, admin, operator, reviewer, and viewer roles.
- Added `workspace_context` with active workspace, current demo user, workspace users, and role permissions.
- Scoped business, lead, booking, call log, notification, QA, campaign, job, knowledge, and dashboard-stat reads to the active workspace by default.
- Tightened direct mutation paths for lead status, handoff flags, booking status, Agent Builder saves, consent recording, DNC entries, and worker campaign recipient lookups.
- Added workspace users and permissions to the Compliance Center.
- Added `GET /api/workspace` and expanded `GET /api/compliance/summary` with current user and role policy details.
- Added workspace/RBAC regression tests.

## Implemented In Session Workspace Slice

- Added signed local session cookies for active workspace selection.
- Added request-scoped workspace/user context so existing repository reads follow the selected workspace.
- Added `POST /workspace/switch` and a top-bar workspace selector for local tenant switching.
- Updated workspace context to prefer existing active workspace users before seeding the demo operator.
- Added regression tests for signed session tamper rejection, request-context scoped reads, and HTTP workspace switching.

## Implemented In Route RBAC Slice

- Added central POST-route permission mapping for local operator mutations.
- Enforced role permissions for agent edits, demo analysis, outbound calls, campaigns, jobs, knowledge ingest, compliance updates, lead/booking updates, settings, and the local AI analysis API.
- Added permission-denied audit events and JSON/HTML `403` responses.
- Left provider webhooks outside browser-session RBAC so Twilio and voice-provider callbacks still use provider validation paths.
- Added HTTP regression coverage proving viewer sessions are denied on protected mutation routes.

## Implemented In Clinic C0 Freeze Slice

- Added `PLATFORM_MODE` with `clinic` as the default and `universal` as the explicit long-term-roadmap mode.
- Added clinic-mode tagline: "Your clinic's AI receptionist - never miss a patient call."
- Marked the healthcare module `active` and all non-healthcare modules `deferred` in the registry.
- Filtered module options/API output to healthcare only in clinic mode while preserving full registry access in universal mode.
- Hid clinic-frozen routes in clinic mode: Modules, Campaigns, and Admin Health; kept Jobs and Agent Builder role-gated.
- Updated sidebar labels for clinic mode, including Leads as Patients/Inquiries.
- Added C0 regression tests for default mode, universal opt-in, deferred module status, sidebar filtering, and route/API hiding.

## Implemented In Clinic C1 Local Onboarding Slice

- Added clinic-specific SQLite tables for clinic profiles, providers/doctors, locations, and holidays/weekly closures.
- Extended services with duration, preferred provider, and preferred location fields.
- Added `callpilot/clinic.py` with clinic validation, parsing, persistence, read helpers, and startup backfill.
- Expanded the internal Agent Builder with clinic profile fields:
  - timezone
  - supported/default languages
  - insurance accepted
  - cancellation window
  - after-hours policy
  - emergency policy
  - recording disclosure toggle
  - reminder policy fields
  - providers/doctors
  - locations
  - holidays/weekly closures such as Friday half-day patterns
- Added startup backfill so BrightCare Dental Clinic has a local C1 profile, provider, location, and Friday half-day pattern.
- Expanded business detail pages to show clinic profile, providers, locations, closures, and service durations/provider/location.
- Added regression tests for seeded profile backfill, creating a second real-shaped clinic through the internal save path, validation failure for missing providers, and Agent Builder C1 field rendering.

## Implemented In Clinic C3 Workflow State Machine Slice

- Added `callpilot/clinic_workflow.py` with a versioned (`clinic-v1`) clinic appointment state machine.
- Modeled the appointment lifecycle states: requested, confirmed, reminded, rescheduled, completed, cancelled, no_show.
- Encoded allowed transitions per state, terminal-state locks (completed/cancelled), and safe no-op on same-state.
- Added `clinic_workflow_transitions` SQLite table with a `(booking_id, idempotency_key)` unique index for idempotent replays.
- Added `apply_booking_transition` which validates the move, updates the booking, records the transition row, appends a lead-timeline event, and writes an audit log; rejected moves write a `clinic_workflow_transition_rejected` audit event and raise `WorkflowError`.
- Recorded the opening `requested` state whenever a booking is created from call analysis.
- Routed `POST /bookings/{id}/status` through the state machine, showing only workflow-allowed statuses per booking, locking terminal bookings, and rendering an operator error banner on rejected transitions.
- Added regression tests for valid transition paths, invalid/terminal rejection, idempotent replay with a key, and initial-state recording on booking creation.

## Implemented In Clinic C4 Scheduling Slice

- Added `callpilot/calendar.py` with a calendar adapter contract and a `GoogleCalendarAdapter`.
- Kept the calendar adapter honest: it reports unavailable when credentials are missing, and reports pending (never a fake confirmed event id) when credentials are present but the live Google API client is not wired.
- Added `callpilot/scheduling.py` to attempt create/cancel/reschedule calendar actions for a booking and persist the outcome.
- Added booking calendar columns (`calendar_provider`, `calendar_event_id`, `calendar_sync_status`, `calendar_synced_at`, `calendar_message`) and a `booking_calendar_syncs` attempt/audit table.
- Wired the C3 workflow transitions to calendar actions: confirmed→create, rescheduled→reschedule, cancelled→cancel; calendar failures never roll back a legitimate workflow transition.
- Recorded every calendar attempt as a lead-timeline event and an audit log entry, and made create idempotent when a booking already holds a confirmed event id.
- Added a Calendar column to the Bookings page showing pending vs on-calendar state and any event id.
- Added `GET /api/calendar` and Google Calendar env keys (`GOOGLE_CALENDAR_ID`, `GOOGLE_CALENDAR_CREDENTIALS`).
- Added regression tests proving no fake event id is created without a live client and that confirm/cancel transitions record the mapped calendar sync.

## Implemented In Clinic C5 Voice Runtime Slice

- Added `callpilot/voice_runtime.py` with versioned (`clinic-voice-v1`) trilingual prompt packs for English, Urdu, and Arabic.
- Every prompt pack carries greeting, recording disclosure, booking prompt, contact prompt, safe emergency script, handoff script, fallback, and closing; all three emergency scripts explicitly refuse medical advice.
- Added trilingual `detect_language_code` covering English, Roman Urdu, Urdu script (Urdu-only letters), and Arabic script/terms.
- Added `resolve_language` honoring the clinic's supported-language policy with default-language fallback and an explicit `language_fallback_used` flag.
- Added `build_runtime_session` assembling the real per-clinic session config a live runtime would receive: prompts formatted with clinic/agent names, knowledge retrieval language, emergency/after-hours/cancellation policies, and recording-disclosure toggle.
- Added honest runtime status: `VOICE_RUNTIME` env selects Vapi or Retell (auto prefers whichever has credentials), and the status refuses to claim a live agent even with an API key because no runtime adapter is implemented.
- Added `GET /api/voice-runtime` for runtime status and session config, and `detected_language_code` to mock call analysis output.
- Added regression tests for pack completeness, no-medical-advice refusals in all languages, trilingual detection, policy fallback, honest not-live status, and session assembly.

## Implemented In Clinic C6 Emergency Escalation Slice

- Added `callpilot/emergency.py` with versioned (`clinic-emergency-v1`) trilingual emergency phrase lists covering English, Roman Urdu, Urdu script, and Arabic.
- Added text normalization plus sliding-window fuzzy matching so latin-script typos (for example "chest pian") still trigger detection.
- Wired detection into mock call analysis: a detected medical emergency forces `urgency=emergency`, adds a safety note, and always triggers human handoff.
- Added PHI-free escalation on lead creation: an `emergency_alert` notification carries the business, caller language, masked callback number, and staff instructions — never symptoms, matched phrases, caller names, full numbers, or transcripts.
- Added `emergency_escalated` lead-timeline events and audit logs with PHI-free metadata (language, match type, policy version only).
- Kept the safe spoken responses in the C5 prompt packs, which refuse medical advice in all three languages.
- Added regression tests for trilingual detection, fuzzy typo matching, urgent-but-not-medical negatives, phone masking, PHI-free alert content, and no-alert-on-normal-booking behavior.

## Implemented In Clinic C7 Reminder Slice

- Added `callpilot/reminders.py` with the versioned (`clinic-reminder-v1`) policy-gated appointment reminder job.
- Scheduling: exactly one `appointment_reminder` job per confirmed clinic booking, `max_attempts=1`, scheduled `reminder_offset_hours` before the appointment when the date/time parses, and only when the clinic profile enables reminders.
- Run-time policy gates in order: booking still confirmed, clinic reminders enabled, `outbound_allowed` (missing phone, Do Not Call opt-out, outbound-disabled policy, missing consent — each audited), and the business calling window.
- Quiet-hours deferral reschedules the job to the next window start without consuming the single allowed attempt.
- Trilingual EN/Roman-Urdu/Arabic reminder scripts, each ending with an opt-out sentence, rendered in the clinic default language with clinic name, date, and time.
- Honest delivery: the reminder calls the real Twilio adapter; locally that returns unavailable, so the notification is recorded as `failed`, the booking stays `confirmed`, and no retry happens. Only a real provider call id moves the booking confirmed→reminded through the C3 state machine with an `appointment-reminder-{booking_id}` idempotency key.
- Wired scheduling into the polling worker, `worker.py --once`, and the manual `/jobs/run` action; added `reminder_suppressed`, `reminder_deferred_quiet_hours`, and `reminder_call_attempted` audit events.
- Added regression tests for single-job scheduling, offset computation, policy suppression, quiet-hours deferral without attempt consumption, honest provider-unavailable behavior, and the delivered path transitioning the booking with a mocked provider call id.

## Implemented In Clinic C8 Security Hardening Slice

- Added `callpilot/auth.py` with PBKDF2-SHA256 password hashing (260k iterations, per-user salt, constant-time verify) and a `password_hash` column on workspace users.
- Added real login/logout: `GET/POST /login`, `POST /logout`, signed authenticated session cookies, and audited `login_succeeded`/`login_failed`/`login_locked_out`/`logout` events.
- Added per-IP+email login rate limiting: five failures lock the pair out for fifteen minutes; error messages never reveal whether the email exists.
- Added the `AUTH_REQUIRED` gate (forced on in production): HTML routes redirect to `/login`, API routes return 401, while `/healthz`, `/readyz`, and provider webhooks (which use provider signature validation) stay reachable.
- Added credential bootstrap: `ADMIN_EMAIL`/`ADMIN_PASSWORD` env pair provisions the owner, otherwise a one-time owner password is generated at startup (hash stored, value printed once, audited).
- Added security headers to every response: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, and a Content-Security-Policy.
- Added a production readiness blocker when auth is disabled in production, alongside the existing default-SECRET_KEY blocker.
- Workspace switching preserves the authenticated session flag.
- Added regression tests for hashing, salting, garbage-hash handling, seeded-owner authentication, short-password rejection, lockout behavior, admin bootstrap, one-time password generation, and a live HTTP login → access → logout → blocked flow with security-header assertions.

## Implemented In Clinic C9 Golden QA Harness Slice

- Added `callpilot/golden.py` with the versioned (`clinic-golden-v1`) golden call harness and `tests/golden_calls/` JSON scripts.
- Ten golden scripts cover English, Roman Urdu, Urdu script, and Arabic: per-language bookings, three emergencies including a noisy Roman Urdu call with speech fillers, a noisy-English fillers call, a medication-advice request that must hand off, Urdu-script routing, and a no-contact hallucination guard call.
- Every script additionally passes universal hallucination checks: extracted phone/email/name must appear in the transcript, "contact details" summary claims must be grounded, and lead scores must stay in range.
- Every script additionally passes safety checks: summaries and recommended actions must never contain medical-advice phrasing.
- The harness runs twice in CI: inside the unit suite (`tests/test_golden_calls.py`) and as a dedicated `python -m callpilot.golden` gate that prints a per-script report and fails the build on any regression.
- The first harness run caught two real trilingual regressions, which were fixed: Arabic booking intent was not recognized (booking keywords were English-only) and noisy Roman Urdu was routed to English (missing Roman Urdu markers).

## Implemented In Clinic C10 Free-Hosting Deployment Slice

- Honored platform-injected `PORT` (Render/Railway) in server config and the Docker healthcheck; `APP_PORT` still wins when explicitly set, and the image no longer bakes a fixed port.
- Added `render.yaml` blueprint for a one-click free Render deploy: Docker runtime, `/healthz` health check, `AUTH_REQUIRED=true`, generated `SECRET_KEY`, and dashboard-set admin/demo credentials.
- Added `ensure_demo_viewer`: `DEMO_VIEWER_EMAIL`/`DEMO_VIEWER_PASSWORD` seed a read-only `viewer` account for prospect walkthroughs — proven over HTTP that the viewer can browse the dashboard but receives `403` on mutation routes.
- Added `docs/DEPLOY_FREE.md`: Render free-plan walkthrough (sleep/cold-start and ephemeral-disk caveats stated honestly), laptop+ngrok option for live Twilio call demos, and the upgrade path once a client pays.
- Added regression tests for PORT fallback/precedence and demo-viewer seeding, idempotency, and browse-yes/mutate-no HTTP behavior.

## PDF Pack Mapped Modules

- Healthcare, clinics, hospitals, dentists
- Hotels and hospitality
- Restaurants and food ordering
- Call centers and customer support
- Lead generation, sales, product caller
- Home services and field service
- Legal, insurance, finance
- Real estate and property management
- Ecommerce, retail, automotive, logistics
- Education, recruiting, travel, government
- Custom universal module

## Next Production Phases

- C0-C11 local critical path is complete (fresh-clone dry run recorded in `docs/evidence/FRESH_CLONE_REPORT.md`). Next work is credential-gated: live Twilio/Vapi/Retell/Google Calendar adapters with recorded EN/UR/AR proof calls, then post-revenue postgres/migrations and fake-provider E2E.
- Implement the live Vapi/Retell runtime adapter so the C5 session config answers a real number with recorded EN/UR/AR proof calls.
- Keep non-healthcare modules, generic outbound campaigns, and self-serve client onboarding frozen until the clinic acceptance test passes.
