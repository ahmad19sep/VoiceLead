from __future__ import annotations

import gc
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.clinic import get_clinic_profile
from callpilot.repositories import get_businesses
from callpilot.views.agent_builder import render_agent_builder, save_agent
from callpilot.views.businesses import render_business_detail
from callpilot.voice_prompt import build_vapi_prompt


URDU_SCRIPT = re.compile(r"[؀-ۿ]")


class VoicePromptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "callpilot-test.db"
        self.patch = patch.object(storage, "DB_PATH", self.db_path)
        self.patch.start()
        storage.init_db()
        with storage.db() as conn:
            clinic = [row for row in get_businesses(conn) if row["name"] == "BrightCare Dental Clinic"][0]
            self.business_id = int(clinic["id"])

    def tearDown(self) -> None:
        self.patch.stop()
        gc.collect()
        self.temp_dir.cleanup()

    def set_languages(self, supported: str, default: str) -> None:
        with storage.db() as conn:
            conn.execute(
                "update clinic_profiles set supported_languages=?, default_language=? where business_id=?",
                (supported, default, self.business_id),
            )
            conn.commit()

    def test_prompt_follows_selected_languages(self) -> None:
        self.set_languages("en,ur", "ur")
        with storage.db() as conn:
            prompt = build_vapi_prompt(conn, self.business_id)
        self.assertIn("Urdu", prompt["system_prompt"])
        self.assertIn("Roman Urdu", prompt["system_prompt"])
        self.assertNotIn("Arabic", prompt["system_prompt"].split("STRICT RULES")[0])
        self.assertIn("Aap Urdu mein", prompt["first_message"])
        # Urdu-selected output is Roman Urdu: no Urdu/Arabic script in the greeting.
        self.assertIsNone(URDU_SCRIPT.search(prompt["first_message"]))

    def test_arabic_selection_adds_arabic_support(self) -> None:
        self.set_languages("en,ur,ar", "ur")
        with storage.db() as conn:
            prompt = build_vapi_prompt(conn, self.business_id)
        self.assertIn("Arabic", prompt["system_prompt"])
        self.assertIsNotNone(URDU_SCRIPT.search(prompt["first_message"]))  # Arabic greeting hint

    def test_english_only_clinic_has_no_urdu(self) -> None:
        self.set_languages("en", "en")
        with storage.db() as conn:
            prompt = build_vapi_prompt(conn, self.business_id)
        self.assertNotIn("Aap Urdu mein", prompt["first_message"])
        self.assertNotIn("Roman Urdu", prompt["system_prompt"])
        self.assertIn("Speak only: English", prompt["system_prompt"])

    def test_prompt_uses_clinic_facts(self) -> None:
        with storage.db() as conn:
            prompt = build_vapi_prompt(conn, self.business_id)
        self.assertIn("BrightCare Dental Clinic", prompt["system_prompt"])
        self.assertIn("NEVER give medical advice", prompt["system_prompt"])
        self.assertIn("staff confirm all bookings", prompt["system_prompt"])

    def test_language_checkboxes_drive_saved_profile(self) -> None:
        from tests.test_clinic_profile import ClinicProfileTest

        form = ClinicProfileTest.clinic_form(ClinicProfileTest)
        form.pop("clinic_supported_languages", None)
        form["lang_en"] = "1"
        form["lang_ar"] = "1"
        form["clinic_default_language"] = "en"
        business_id = save_agent(form)
        with storage.db() as conn:
            profile = get_clinic_profile(conn, business_id)
        self.assertEqual(profile["supported_languages"], "en,ar")
        self.assertEqual(profile["default_language"], "en")

    def test_agent_builder_renders_language_controls(self) -> None:
        html = render_agent_builder({})
        self.assertIn('name="lang_en"', html)
        self.assertIn('name="lang_ur"', html)
        self.assertIn('name="lang_ar"', html)
        self.assertIn("Urdu (Roman)", html)

    def test_business_detail_shows_vapi_panel(self) -> None:
        html = render_business_detail(self.business_id)
        self.assertIn("Voice Agent Prompt", html)
        self.assertIn("Paste into Vapi", html)
        self.assertIn("NEVER give medical advice", html)


if __name__ == "__main__":
    unittest.main()
