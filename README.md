# CallPilot AI

CallPilot AI is currently focused on the clinic launch path: an AI receptionist for clinics that can answer patient calls, capture appointment requests, route urgent cases, and keep demo behavior visibly separate from production success.

The long-term universal platform remains in the codebase behind `PLATFORM_MODE=universal`, but the default `PLATFORM_MODE=clinic` freezes non-healthcare modules while the clinic critical path is built.

- Hotels
- Clinics / doctors
- Home services
- Restaurants
- Software agencies
- Law firms
- Custom businesses

It runs in local demo mode with SQLite and mock AI, so you do not need Node, npm, JavaScript, Supabase, OpenAI, Claude, Vapi, Twilio, or any paid API key.

## Run

Open PowerShell in this folder:

```text
C:\Users\Home_pc\Pictures\VoiceLead
```

Run:

```bash
python app.py
```

Open:

```text
http://127.0.0.1:8000
```

Keep the PowerShell window open while using the app.

## Run With Docker

Build and run the local demo image:

```bash
docker build -t callpilot-ai .
docker run --rm -p 8000:8000 callpilot-ai
```

Open:

```text
http://127.0.0.1:8000
```

The container starts with a fresh SQLite demo database inside the container filesystem.

For a persistent local container setup with the web app and worker sharing the same SQLite volume:

```bash
docker compose up --build
```

Compose stores the database in the `callpilot-data` Docker volume at `/data/callpilot.db`.

## Run Worker

Process due background jobs once:

```bash
python worker.py --once
```

Run the polling worker:

```bash
python worker.py
```

Use `WORKER_POLL_INTERVAL` and `WORKER_BATCH_LIMIT` to tune polling and batch size.

## Platform Mode

`PLATFORM_MODE=clinic` is the default. In clinic mode, the sidebar hides frozen universal surfaces such as Modules and Campaigns, shows the clinic receptionist tagline, and renames Leads to Patients/Inquiries.

Use `PLATFORM_MODE=universal` only when intentionally working on the deferred universal roadmap.

## Main Pages

- `/` - Dashboard
- `/businesses` - Business agents
- `/knowledge` - Versioned business knowledge ingest, approval, and search
- `/demo-call` - Test call transcripts
- `/real-calling` - Connect a real Twilio phone number
- `/leads` - Patients/Inquiries CRM
- `/bookings` - Booking requests
- `/calls` - Call logs
- `/qa` - QA evaluation queue for call safety and workflow review
- `/notifications` - Human handoff alerts
- `/compliance` - Workspace, consent, Do Not Call, staff handoff contacts, and audit logs
- `/settings` - Integration status and demo mode settings

Operator-only or universal-mode pages:

- `/agent-builder` - internal operator tool for configuring clinics
- `/jobs` - operator job queue visibility
- `/modules` - universal-mode module registry
- `/campaigns` - frozen in clinic mode until narrow appointment reminders are implemented
- `/admin` - universal/admin health surface

## Test A Demo Call

1. Open `http://127.0.0.1:8000/demo-call`
2. Select a business
3. Choose a sample transcript
4. Click **Analyze Call**
5. The app creates a lead
6. If the call is ready-to-book or urgent, it creates a booking and notification

## What Works Now

- Multi-business dashboard
- Seed businesses for hotel, clinic, home services, restaurant, software agency, and law firm
- Agent Builder
- PDF-pack aligned industry module configuration
- Per-business language, compliance, consent, recording, QA, and outbound policy settings
- Default workspace foundation with staff contacts, consent records, Do Not Call entries, and audit logs
- Default workspace owner user, role policy metadata, signed workspace selection cookies, workspace-scoped local reads, and local mutation-route RBAC checks
- Clinic mode flag with healthcare-only module visibility and deferred non-healthcare registry status
- Internal clinic onboarding fields for timezone, languages, insurance, cancellation window, after-hours policy, emergency policy, providers/doctors, locations, holidays/weekly closures, and service durations
- Services and FAQs per business
- Versioned knowledge documents with manual, document, URL, and policy ingest
- Approved knowledge search used by call analysis and agent review
- Mock AI call analysis
- Language detection and regulated-advice guardrails in mock analysis
- Universal lead scoring
- Automatic QA scoring for safety, workflow integrity, language handling, and next-step quality
- Hot, warm, and cold lead categories
- Booking request creation
- Human handoff notifications
- Call logs
- Settings page with connected/missing API key status
- Real Twilio Voice webhook endpoints
- Twilio webhook signature validation with production enforcement
- Outbound Twilio test-call starter
- Outbound campaign planning with queued/suppressed recipient lists
- Manual job queue for preparing campaign recipients without auto-dialing

## Demo Mode

If API keys are missing, the app keeps working:

- SQLite is used instead of Supabase
- Mock AI is used instead of OpenAI or Claude
- Demo Call Simulator is used instead of real voice
- Dashboard notifications are saved instead of sending SMS/email/Slack
- Keyword matching is used instead of vector search

## Real Calling With Twilio

Real phone calls require a phone provider. This app now supports Twilio Voice.

You need:

1. A Twilio account
2. A Twilio phone number with Voice enabled
3. Your Twilio Account SID
4. Your Twilio Auth Token
5. A public HTTPS URL for this local Python app

Twilio cannot call `127.0.0.1` directly. For local testing, use a tunnel such as ngrok:

```bash
ngrok http 8000
```

Copy the public HTTPS URL from ngrok, then create a `.env` file in this folder:

```text
APP_URL=https://your-ngrok-url.ngrok-free.app
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+1234567890
```

Restart the app:

```bash
python app.py
```

Then open:

```text
http://127.0.0.1:8000/real-calling
```

Choose a business and copy the Twilio Voice Webhook URL. In the Twilio Console, open your phone number and set:

```text
A call comes in: Webhook
Method: POST
URL: https://your-ngrok-url.ngrok-free.app/api/twilio/voice?business_id=1
```

Now call your Twilio number. CallPilot will answer, gather speech, analyze the call, create a lead, and trigger booking/handoff logic.

You can also use the **Outbound Test Call** form on `/real-calling` after the Twilio keys are in `.env`.

## API Routes

- `GET /healthz`
- `GET /readyz`
- `GET /api/businesses`
- `GET /api/businesses/{id}/readiness`
- `GET /api/workspace`
- `GET /api/modules`
- `GET /api/modules/{module_key}`
- `GET /api/compliance/summary`
- `GET /api/admin/health`
- `GET /api/providers`
- `GET /api/providers/{provider_key}`
- `GET /api/qa/evaluations`
- `GET /api/campaigns`
- `GET /api/jobs`
- `GET /api/knowledge/search?business_id=1&q=refund`
- `GET /api/leads`
- `POST /workspace/switch`
- `POST /api/ai/analyze-call`
- `POST /api/voice/webhook`
- `POST /api/twilio/voice`
- `POST /api/twilio/gather`

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

## Important Files

- `app.py` - small app entry point
- `callpilot/config.py` - app constants, demo transcript samples, and `.env` loading
- `callpilot/clinic.py` - clinic profile, providers/doctors, locations, holidays, and onboarding validation helpers
- `callpilot/campaigns.py` - outbound campaign planning and suppression helpers
- `callpilot/compliance.py` - workspace, consent, Do Not Call, outbound policy, and audit helpers
- `callpilot/jobs.py` - durable job queue and manual worker helpers
- `callpilot/modules.py` - industry module templates from the universal AI calling PDF pack
- `callpilot/providers.py` - provider adapter registry for telephony, AI, voice runtime, STT, and TTS readiness
- `callpilot/security.py` - provider readiness and webhook signature validation helpers
- `callpilot/sessions.py` - signed local session-cookie helpers for active workspace selection
- `callpilot/qa.py` - call QA scoring and evaluation backfill helpers
- `callpilot/storage.py` - SQLite connection and schema setup
- `callpilot/repositories.py` - database read helpers
- `callpilot/analysis.py` - mock AI call analysis, field extraction, and scoring
- `callpilot/workflows.py` - lead, booking, notification, and event creation
- `callpilot/telephony.py` - Twilio/TwiML helpers and outbound-call support
- `callpilot/http.py` - HTTP request handler and route dispatch
- `callpilot/server.py` - local server startup
- `callpilot/views/` - dashboard, CRM, agent builder, calling, and settings pages
- `docs/PROJECT_DOCUMENTATION.md` - full project reference documentation
- `docs/REPOSITORY_STATE.md` - current architecture map and production gaps
- `docs/PRODUCT_DEFINITION.md` - product rules and forbidden fake-success behavior
- `callpilot.db` - SQLite database, created automatically
- `.env.example` - future API key template
- `README.md` - these instructions
- `docs/PDF_IMPLEMENTATION_NOTES.md` - PDF pack implementation notes and next phases

## If Browser Says Refused To Connect

The Python server is not running. Run:

```bash
python app.py
```

Then open:

```text
http://127.0.0.1:8000
```

## Stop The App

In the PowerShell window where the app is running, press:

```text
Ctrl + C
```

## Reset Database

1. Stop the app
2. Delete `callpilot.db`
3. Run again:

```bash
python app.py
```

## Future Integrations

- OpenAI
- Anthropic Claude
- Supabase PostgreSQL
- Supabase pgvector or another vector database
- Vapi and Retell voice calling
- ElevenLabs voice
- Deepgram transcription
- Email, Slack, WhatsApp, and SMS notifications
