from __future__ import annotations

import sqlite3
from typing import Any

from .config import DB_PATH


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    return conn

def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row else None

def ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"pragma table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"alter table {table} add column {name} {definition}")

def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            create table if not exists businesses (
                id integer primary key autoincrement,
                name text not null,
                business_type text not null,
                description text,
                phone text,
                email text,
                website text,
                location text,
                working_hours text,
                agent_name text,
                agent_greeting text,
                agent_tone text,
                fallback_message text,
                hot_lead_threshold integer default 75,
                warm_lead_threshold integer default 45,
                module_key text default 'custom',
                intake_fields text,
                allowed_call_types text,
                blocked_outcomes text,
                supported_languages text,
                compliance_profile text,
                consent_policy text,
                recording_disclosure text,
                quiet_hours text,
                max_outbound_attempts integer default 0,
                integration_targets text,
                qa_checks text,
                workflow_version text default 'v1',
                handoff_name text,
                handoff_phone text,
                handoff_email text,
                handoff_instructions text,
                status text default 'active',
                created_at text default current_timestamp,
                updated_at text default current_timestamp
            );

            create table if not exists services (
                id integer primary key autoincrement,
                business_id integer not null,
                name text not null,
                description text,
                price_note text,
                is_bookable integer default 1,
                is_emergency integer default 0,
                created_at text default current_timestamp,
                foreign key (business_id) references businesses(id) on delete cascade
            );

            create table if not exists knowledge_base (
                id integer primary key autoincrement,
                business_id integer not null,
                question text not null,
                answer text not null,
                category text,
                tags text,
                source text,
                embedding_id text,
                created_at text default current_timestamp,
                foreign key (business_id) references businesses(id) on delete cascade
            );

            create table if not exists leads (
                id integer primary key autoincrement,
                business_id integer,
                customer_name text,
                customer_phone text,
                customer_email text,
                request_type text,
                service_requested text,
                industry text,
                location text,
                urgency text,
                timeline text,
                budget text,
                intent text,
                extracted_fields text,
                lead_score integer default 0,
                lead_temperature text default 'cold',
                status text default 'new',
                ai_summary text,
                recommended_action text,
                transcript text,
                score_breakdown text,
                safety_notes text,
                handoff_triggered integer default 0,
                booking_requested integer default 0,
                created_at text default current_timestamp,
                updated_at text default current_timestamp,
                foreign key (business_id) references businesses(id) on delete set null
            );

            create table if not exists bookings (
                id integer primary key autoincrement,
                business_id integer not null,
                lead_id integer,
                customer_name text,
                customer_phone text,
                customer_email text,
                booking_type text,
                requested_date text,
                requested_time text,
                number_of_people text,
                service_requested text,
                notes text,
                status text default 'requested',
                created_at text default current_timestamp,
                updated_at text default current_timestamp,
                foreign key (business_id) references businesses(id) on delete cascade,
                foreign key (lead_id) references leads(id) on delete set null
            );

            create table if not exists call_logs (
                id integer primary key autoincrement,
                business_id integer,
                lead_id integer,
                provider text default 'demo',
                call_id text,
                caller_phone text,
                transcript text,
                recording_url text,
                duration_seconds integer,
                call_status text,
                analysis_json text,
                created_at text default current_timestamp,
                foreign key (business_id) references businesses(id) on delete set null,
                foreign key (lead_id) references leads(id) on delete set null
            );

            create table if not exists call_sessions (
                id integer primary key autoincrement,
                business_id integer,
                call_sid text unique,
                caller_phone text,
                transcript text,
                turn_count integer default 0,
                lead_id integer,
                status text default 'active',
                created_at text default current_timestamp,
                updated_at text default current_timestamp,
                foreign key (business_id) references businesses(id) on delete cascade,
                foreign key (lead_id) references leads(id) on delete set null
            );

            create table if not exists notifications (
                id integer primary key autoincrement,
                business_id integer,
                lead_id integer,
                notification_type text,
                channel text default 'dashboard',
                recipient text,
                subject text,
                message text,
                status text default 'sent',
                created_at text default current_timestamp,
                foreign key (business_id) references businesses(id) on delete cascade,
                foreign key (lead_id) references leads(id) on delete set null
            );

            create table if not exists agent_events (
                id integer primary key autoincrement,
                business_id integer,
                lead_id integer,
                event_type text not null,
                description text,
                metadata text,
                created_at text default current_timestamp,
                foreign key (business_id) references businesses(id) on delete cascade,
                foreign key (lead_id) references leads(id) on delete set null
            );

            create table if not exists settings (
                id integer primary key autoincrement,
                key text unique not null,
                value text,
                created_at text default current_timestamp,
                updated_at text default current_timestamp
            );
            """
        )
        ensure_columns(
            conn,
            "businesses",
            {
                "module_key": "text default 'custom'",
                "intake_fields": "text",
                "allowed_call_types": "text",
                "blocked_outcomes": "text",
                "supported_languages": "text",
                "compliance_profile": "text",
                "consent_policy": "text",
                "recording_disclosure": "text",
                "quiet_hours": "text",
                "max_outbound_attempts": "integer default 0",
                "integration_targets": "text",
                "qa_checks": "text",
                "workflow_version": "text default 'v1'",
            },
        )
        from .modules import comma, lines, module_for_business_type

        for row in conn.execute("select id, business_type, module_key from businesses").fetchall():
            module = module_for_business_type(row["business_type"])
            if row["module_key"] and row["module_key"] != "custom":
                continue
            conn.execute(
                """
                update businesses
                set module_key=?,
                    intake_fields=coalesce(intake_fields, ?),
                    allowed_call_types=coalesce(allowed_call_types, ?),
                    blocked_outcomes=coalesce(blocked_outcomes, ?),
                    supported_languages=coalesce(supported_languages, ?),
                    compliance_profile=coalesce(compliance_profile, ?),
                    consent_policy=coalesce(consent_policy, ?),
                    recording_disclosure=coalesce(recording_disclosure, ?),
                    quiet_hours=coalesce(quiet_hours, ?),
                    integration_targets=coalesce(integration_targets, ?),
                    qa_checks=coalesce(qa_checks, ?),
                    workflow_version=coalesce(workflow_version, 'v1')
                where id=?
                """,
                (
                    module["key"],
                    lines(module["intake_fields"]),
                    lines(module["allowed_call_types"]),
                    lines(module["blocked_outcomes"]),
                    module["language_policy"],
                    module["compliance_profile"],
                    "Outbound calls require consent, opt-out handling, and client policy approval.",
                    "Disclose recording when enabled by the client and required by region.",
                    "09:00-18:00 local time unless the client policy says otherwise.",
                    module["integration_targets"],
                    comma(module["qa_checks"]),
                    row["id"],
                ),
            )
        count = conn.execute("select count(*) from businesses").fetchone()[0]
        if count == 0:
            from .seed import seed_data

            seed_data(conn)
