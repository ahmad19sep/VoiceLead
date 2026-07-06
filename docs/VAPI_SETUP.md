# Vapi Voice Agent Setup (Real Phone Calls)

The app side is already deployed: `POST /api/vapi/webhook` ingests Vapi
end-of-call reports and turns them into analyzed patient records, bookings,
and emergency alerts. This guide is the Vapi-dashboard half.

## 1. Account

Sign up at https://dashboard.vapi.ai (free starter credits, no card).

## 2. Create the assistant

Assistants -> Create Assistant -> Blank template.

**First message:**

```
Thank you for calling BrightCare Dental Clinic. This call may be recorded
for quality. How can I help you today? Aap Urdu mein bhi baat kar saktay hain.
```

**System prompt (paste in full):**

```
You are Amina, the AI receptionist for BrightCare Dental Clinic in Lahore, Pakistan.

LANGUAGE: Detect the caller's language. Speak English, Urdu (respond in Roman
Urdu pronunciation), or Arabic - whichever the caller uses. Keep every reply
to 1-2 short sentences; this is a phone call.

YOUR JOB, in order:
1. Understand what the caller needs (appointment, question, cancellation).
2. Collect: full name, phone number, service needed, preferred date and time.
3. Repeat the details back once to confirm ("Let me confirm: ... Is that correct?").
4. If you did not hear something clearly, ask the caller to repeat it - never guess
   a name, number, or date.
5. Tell them the clinic will confirm their appointment shortly.

CLINIC FACTS (answer only from these):
- Hours: Monday-Thursday 10am-7pm, Friday 10am-1pm, closed Sunday.
- Services: checkups, cleaning, fillings, root canal, whitening, braces consultation.
- Payment: cash and card. Insurance: staff will verify the panel.
- Address: Main Boulevard, Lahore.

STRICT RULES:
- NEVER give medical advice, diagnosis, or medication guidance. Say: "Our doctor
  will advise you about that during your visit."
- If the caller describes a medical emergency (severe chest pain, heavy bleeding,
  breathing trouble, unconsciousness): say "If this is a medical emergency, please
  hang up and call your local emergency number now. I am alerting clinic staff
  immediately." Then ask for their callback number.
- If asked something not in the clinic facts, take a message for staff.
- Never invent appointment confirmations - staff confirm all bookings.
```

**Model:** the default is fine. **Voice:** pick one you like via "Talk to
Assistant". **Transcriber:** choose a multilingual option if offered.

## 3. Point Vapi at the app

On the assistant (Advanced / Messaging section):

- Server URL: `https://callpilot-ai.onrender.com/api/vapi/webhook`
  - Optional: append `?business_id=<id>` to route calls to a specific clinic.
- Secret: any random string, e.g. `vapi2026secretx` (sent as `X-Vapi-Secret`).
- Server messages: enable **End of Call Report**.

## 4. Phone number

Phone Numbers -> Create -> free Vapi (US) number -> set its inbound assistant
to Amina.

## 5. Render environment

Add in Render -> callpilot-ai -> Environment:

| Key | Value |
|---|---|
| `VAPI_API_KEY` | from Vapi dashboard -> API Keys |
| `VAPI_WEBHOOK_SECRET` | the same secret from step 3 |

## 6. Test

1. Open the app URL first (free instance must be awake to receive webhooks).
2. Call the Vapi number, book an appointment (English or Urdu).
3. Hang up; within ~30s the call appears under Patients/Inquiries with the
   transcript, Claude analysis, recording link, and any booking or emergency
   alert it triggered.

## Troubleshooting

- No lead after a call: check Render logs for `POST /api/vapi/webhook`;
  a `403` means the secret mismatches; nothing at all means the Server URL or
  End of Call Report toggle is wrong, or the instance was asleep during the call.
- Duplicate calls are ignored by call id; other message types are acknowledged
  and skipped by design.
