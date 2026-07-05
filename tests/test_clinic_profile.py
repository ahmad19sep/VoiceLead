from __future__ import annotations

import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.clinic import (
    get_clinic_holidays,
    get_clinic_locations,
    get_clinic_profile,
    get_clinic_providers,
)
from callpilot.repositories import get_businesses, get_services
from callpilot.views.agent_builder import render_agent_builder, save_agent


class ClinicProfileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "callpilot-test.db"
        self.patch = patch.object(storage, "DB_PATH", self.db_path)
        self.patch.start()
        storage.init_db()

    def tearDown(self) -> None:
        self.patch.stop()
        gc.collect()
        self.temp_dir.cleanup()

    def test_seeded_clinic_has_c1_profile_backfilled(self) -> None:
        with storage.db() as conn:
            clinic = [row for row in get_businesses(conn) if row["name"] == "BrightCare Dental Clinic"][0]
            profile = get_clinic_profile(conn, int(clinic["id"]))
            providers = get_clinic_providers(conn, int(clinic["id"]))
            locations = get_clinic_locations(conn, int(clinic["id"]))
            holidays = get_clinic_holidays(conn, int(clinic["id"]))

        self.assertEqual(profile["timezone"], "Asia/Karachi")
        self.assertTrue(providers)
        self.assertTrue(locations)
        self.assertEqual(holidays[0]["holiday_type"], "weekly")

    def test_operator_can_create_real_shaped_second_clinic(self) -> None:
        business_id = save_agent(self.clinic_form())

        with storage.db() as conn:
            businesses = {row["name"]: row for row in get_businesses(conn)}
            services = get_services(conn, business_id)
            profile = get_clinic_profile(conn, business_id)
            providers = get_clinic_providers(conn, business_id)
            locations = get_clinic_locations(conn, business_id)
            holidays = get_clinic_holidays(conn, business_id)

        self.assertIn("NorthStar Family Clinic", businesses)
        self.assertEqual(profile["timezone"], "Asia/Karachi")
        self.assertEqual(profile["supported_languages"], "en,ur")
        self.assertEqual(profile["default_language"], "ur")
        self.assertEqual(profile["cancellation_window_hours"], 12)
        self.assertEqual(profile["recording_disclosure_enabled"], 1)
        self.assertEqual(profile["reminders_enabled"], 1)
        self.assertEqual(services[0]["duration_minutes"], 20)
        self.assertEqual(services[0]["provider_name"], "Dr. Sara Khan")
        self.assertEqual(providers[0]["specialty"], "Family medicine")
        self.assertEqual(locations[0]["timezone"], "Asia/Karachi")
        self.assertEqual(holidays[0]["weekday"], "friday")

    def test_clinic_setup_requires_provider_and_location(self) -> None:
        form = self.clinic_form()
        form["clinic_providers"] = ""

        with self.assertRaises(ValueError) as raised:
            save_agent(form)

        self.assertIn("provider", str(raised.exception).lower())
        with storage.db() as conn:
            names = {row["name"] for row in get_businesses(conn)}
        self.assertNotIn("NorthStar Family Clinic", names)

    def test_agent_builder_renders_clinic_onboarding_fields(self) -> None:
        html = render_agent_builder({})

        self.assertIn("Clinic Profile", html)
        self.assertIn("Providers / Doctors", html)
        self.assertIn("Holidays / Closures", html)
        self.assertIn("Asia/Karachi", html)

    def clinic_form(self) -> dict[str, str]:
        return {
            "name": "NorthStar Family Clinic",
            "business_type": "Clinic",
            "description": "Family clinic for appointment scheduling and approved administrative questions.",
            "phone": "+92 300 2223344",
            "email": "reception@northstar.example",
            "website": "https://northstar.example",
            "location": "Johar Town Lahore",
            "working_hours": "Mon-Thu 09:00-18:00, Fri 09:00-13:00",
            "agent_name": "Amina AI Receptionist",
            "agent_greeting": "Hi, thanks for calling NorthStar Family Clinic.",
            "agent_tone": "Clinic receptionist style",
            "fallback_message": "I can collect your details and ask clinic staff to call back.",
            "hot_lead_threshold": "75",
            "warm_lead_threshold": "45",
            "module_key": "healthcare",
            "intake_fields": "Patient name\nPhone\nService\nPreferred doctor\nPreferred date/time",
            "allowed_call_types": "Book appointments\nAnswer approved FAQs\nEscalate urgent calls",
            "blocked_outcomes": "No diagnosis\nNo medication advice",
            "supported_languages": "English, Urdu",
            "compliance_profile": "Clinic administrative receptionist; no medical advice.",
            "consent_policy": "Outbound reminders require active consent.",
            "recording_disclosure": "Disclose recording at call start.",
            "quiet_hours": "09:00-20:00",
            "max_outbound_attempts": "0",
            "integration_targets": "Google Calendar, staff handoff",
            "qa_checks": "No medical advice, appointment confirmation, emergency escalation",
            "workflow_version": "clinic-v1",
            "services": "General consultation | Routine family medicine appointment | 20 | Dr. Sara Khan | Johar Main | Rs. 3000 | 1 | 0\nUrgent callback | Staff callback for urgent concern | 10 | Dr. Sara Khan | Johar Main | Staff confirmation | 1 | 1",
            "clinic_timezone": "Asia/Karachi",
            "clinic_supported_languages": "en,ur",
            "clinic_default_language": "ur",
            "clinic_cancellation_window_hours": "12",
            "clinic_reminder_offset_hours": "24",
            "clinic_recording_disclosure_enabled": "1",
            "clinic_reminders_enabled": "1",
            "clinic_insurance_accepted": "Cash, card, Jubilee panel",
            "clinic_after_hours_policy": "Capture caller name and callback number for next-business-day staff follow-up.",
            "clinic_emergency_policy": "Use safe emergency script and alert staff immediately without medical advice.",
            "clinic_providers": "Dr. Sara Khan | Doctor | Family medicine | en,ur | Johar Main | Mon-Thu 09:00-15:00",
            "clinic_locations": "Johar Main | 12 Medical Avenue, Lahore | +92 300 2223344 | Asia/Karachi | Mon-Thu 09:00-18:00, Fri 09:00-13:00",
            "clinic_holidays": "weekly | Friday half-day | friday | 13:00 | 15:00 | 0",
            "faqs": "What are timings? | We are open Monday to Thursday 9 AM to 6 PM and Friday until 1 PM. | Hours",
            "handoff_name": "Clinic Reception",
            "handoff_phone": "+92 300 2223344",
            "handoff_email": "reception@northstar.example",
            "handoff_instructions": "Alert reception for urgent or uncertain calls.",
        }


if __name__ == "__main__":
    unittest.main()
