# Free Live Demo Deployment (Rs 0)

Goal: a public HTTPS URL running CallPilot AI that you can show to Upwork
clients, with you as the operator and an optional read-only login for
prospects. No credit card required.

## Option A: Render free plan (recommended, ~10 minutes)

1. Go to https://render.com and sign up with your GitHub account (free).
2. Click **New + → Blueprint** and pick the `VoiceLead` repository.
   Render reads `render.yaml` automatically.
3. When prompted for environment variables, set:
   - `ADMIN_EMAIL` — your operator login, for example `you@example.com`
   - `ADMIN_PASSWORD` — 10+ characters; this is your login password
   - `DEMO_VIEWER_EMAIL` / `DEMO_VIEWER_PASSWORD` — optional read-only
     account you can hand to a prospect (they can browse, but every
     save/update button is denied by role permissions)
4. Deploy. First build takes a few minutes. Your URL will be
   `https://callpilot-ai-XXXX.onrender.com`.
5. Open the URL → you land on the login page → sign in with the admin
   account. Done: that link is your live demo.
6. After the first deploy, set `APP_URL` to your onrender.com URL in the
   Render dashboard so readiness reporting is accurate.

### What the free plan means

- The service sleeps after ~15 idle minutes; the first visit wakes it in
  ~30-60 seconds. Open the link two minutes before a client call.
- The disk is ephemeral: the SQLite database resets to fresh seeded demo
  data on every deploy or restart. For a demo this is a feature - the
  instance cleans itself. Do not store real client data on the free plan.
- To keep data, attach a paid persistent disk later and set
  `SQLITE_DB_PATH=/data/callpilot.db` (the image already creates `/data`).

## Option B: laptop + ngrok (for live phone-call demos)

Render's free plan is fine for showing the dashboard. For a live Twilio
phone-call demo, run locally and tunnel:

```
python app.py
ngrok http 8000
```

Set `APP_URL` in `.env` to the https ngrok URL and use it as the Twilio
webhook base. Free ngrok URLs change on each restart.

## Showing it to an Upwork client

- Screen share: log in as admin and walk through Dashboard, Patients,
  Bookings, Demo Call simulator, QA, Compliance.
- Hands-on: give them the demo-viewer login. They can look at everything;
  the viewer role cannot change anything.
- The Demo Call page (`/demo-call`) works with zero provider keys: paste an
  English or Urdu transcript and show the lead, booking, emergency alert,
  and QA score appear live.

## When a client pays

Move up: paid Render instance (or a $6/mo VPS) + persistent disk + real
Twilio/Vapi keys + `APP_ENV=production` (which enforces signatures, real
secrets, and auth). See `.env.example` for every key.
