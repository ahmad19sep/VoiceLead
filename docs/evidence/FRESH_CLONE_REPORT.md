# C11 Fresh-Clone Dry-Run Report

Date: 2026-07-05
Commit under test: `20e6144` (Add C10 free-hosting deployment readiness)
Method: `git clone` of the repository into an empty scratch directory on
Windows 11 / Python 3.12; every step below ran inside the fresh clone with no
`.env`, no existing database, and no provider credentials.

## Results

| # | Step | Command | Result |
|---|---|---|---|
| 1 | Clone | `git clone <repo> fresh-clone` | OK |
| 2 | Compile | `python -m compileall app.py worker.py callpilot` | OK |
| 3 | Unit tests | `python -m unittest discover -s tests -p "test*.py"` | **97/97 OK** |
| 4 | Golden call harness | `python -m callpilot.golden` | **10/10 PASS** (en/ur/ar) |
| 5 | Worker smoke | `python worker.py --once --limit 5` | OK ("Processed 0 job(s).") |
| 6 | Server boot + health | `GET /healthz`, `GET /readyz` | 200 / 200 |
| 7 | Dashboard | `GET /` | 200 |
| 8 | Clinic mode freeze | `GET /api/modules` → healthcare only; `GET /modules` | healthcare-only JSON; 404 |
| 9 | Voice runtime API | `GET /api/voice-runtime` | 200, honest `live_ready: false` |
| 10 | Auth-on boot | `AUTH_REQUIRED=true ADMIN_EMAIL=... ADMIN_PASSWORD=...` fresh DB | `GET /` → 303 to `/login`; `GET /login` → 200; valid `POST /login` sets `callpilot_session` cookie |

## Honest state at clone time

- Database: SQLite auto-created and seeded with clinic demo data on first run.
- Providers: Twilio/Vapi/Retell/Google Calendar all report not connected /
  not production-ready. No fake success states appear anywhere.
- Readiness (`/readyz`) reports demo mode warnings and no blockers in local
  mode; production mode enforces SECRET_KEY, auth, HTTPS URL, and Twilio
  signature blockers.

## Conclusion

A fresh clone runs the complete clinic demo (C0-C10) with a single command
(`python app.py`), passes the full test and golden suites, and honestly
reports every unconfigured integration. Remaining production work requires
real credentials only (Twilio, Vapi/Retell, Google Calendar, AI provider).
