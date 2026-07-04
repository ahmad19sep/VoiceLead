# Product Definition

Date: 2026-07-04

## Product

CallPilot AI is moving from a local demo into a Universal AI Calling Platform: a configurable SaaS system for inbound calls, outbound calls, bookings, cancellations, reschedules, reminders, lead qualification, follow-ups, human handoff, reporting, and client-specific voice workflows.

## Core Rule

Workflows, prompts, tools, integrations, languages, policies, handoff rules, and compliance restrictions must be configured per client. The platform must not hard-code one industry or pretend that demo providers are production systems.

## Supported Module Families

- Healthcare clinics, hospitals, and dentists
- Hotels and hospitality
- Restaurants and food ordering
- Call centers and customer support
- Lead generation, sales, and product callers
- Home services and field service
- Legal, insurance, and finance
- Real estate and property management
- Ecommerce, retail, automotive, and logistics
- Education, recruiting, travel, and government
- Custom businesses

## Inbound Calling

Inbound agents answer real phone calls, identify the caller, understand intent, collect approved fields, answer approved FAQs, perform safe tool actions, escalate when required, summarize the call, and sync records. A production inbound call requires a real provider call id, status metadata, and audit record.

## Outbound Calling

Outbound agents run reminders, callbacks, follow-ups, surveys, recall campaigns, sales campaigns, and status updates only when consent and policy allow. A production outbound call requires consent checks, do-not-call suppression, quiet hours, retry limits, opt-out handling, provider status, and audit logs.

## Forbidden Fake Success

- No fake production calls.
- No fake production bookings.
- No unsafe medical, legal, financial, insurance, housing, or eligibility advice.
- No illegal outbound campaigns.
- No raw platform passwords or unencrypted production secrets.
- No silent demo mode.
- No one-size-fits-all scripts.

## Production Acceptance Direction

The finished platform must support real provider webhooks, provider signature verification, external booking/CRM/ticket confirmation, workflow state persistence, compliance audits, multilingual voice behavior, human review queues, and clear evidence for every completed production phase.
