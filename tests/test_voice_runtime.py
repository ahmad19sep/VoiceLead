from __future__ import annotations

import gc
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.repositories import get_businesses
from callpilot.voice_runtime import (
    PROMPT_PACKS,
    RUNTIME_LANGUAGES,
    build_runtime_session,
    detect_language_code,
    prompt_pack,
    resolve_language,
    runtime_status,
)


class VoiceRuntimeUnitTest(unittest.TestCase):
    def test_prompt_packs_cover_all_runtime_languages(self) -> None:
        for language in RUNTIME_LANGUAGES:
            self.assertIn(language, PROMPT_PACKS)
            pack = PROMPT_PACKS[language]
            for key in ("greeting", "recording_disclosure", "booking_prompt", "emergency_script", "handoff_script"):
                self.assertIn(key, pack, f"{language} pack missing {key}")

    def test_emergency_scripts_never_offer_medical_advice(self) -> None:
        refusals = {
            "en": "cannot give medical advice",
            "ur": "tibbi mashwara nahi",
            "ar": "لا يمكنني تقديم نصيحة طبية",
        }
        for language, refusal in refusals.items():
            self.assertIn(refusal, PROMPT_PACKS[language]["emergency_script"])

    def test_detect_language_code_trilingual(self) -> None:
        self.assertEqual(detect_language_code("I want to book a cleaning appointment tomorrow."), "en")
        self.assertEqual(detect_language_code("Assalam o alaikum, mujhe appointment chahiye kal ke liye."), "ur")
        self.assertEqual(detect_language_code("ڈاکٹر صاحب سے ملنا ہے"), "ur")
        self.assertEqual(detect_language_code("مرحبا، أريد حجز موعد في العيادة"), "ar")
        self.assertEqual(detect_language_code(""), "en")

    def test_resolve_language_falls_back_to_clinic_default(self) -> None:
        language, fallback = resolve_language("ar", ["en", "ur"], "ur")
        self.assertEqual(language, "ur")
        self.assertTrue(fallback)
        language, fallback = resolve_language("ur", ["en", "ur"], "ur")
        self.assertEqual(language, "ur")
        self.assertFalse(fallback)

    def test_prompt_pack_formats_clinic_and_agent_names(self) -> None:
        pack = prompt_pack("en", "BrightCare Dental Clinic", "Sana AI")
        self.assertIn("BrightCare Dental Clinic", pack["greeting"])
        self.assertIn("Sana AI", pack["greeting"])

    def test_runtime_status_is_honest_without_credentials(self) -> None:
        env = {"VOICE_RUNTIME": "vapi", "VAPI_API_KEY": "", "RETELL_API_KEY": ""}
        with patch.dict(os.environ, env, clear=False):
            status = runtime_status()
        self.assertFalse(status["connected"])
        self.assertFalse(status["live_ready"])
        self.assertTrue(status["blockers"])

    def test_runtime_stays_not_live_even_with_api_key(self) -> None:
        env = {"VOICE_RUNTIME": "retell", "RETELL_API_KEY": "test-key"}
        with patch.dict(os.environ, env, clear=False):
            status = runtime_status()
        self.assertEqual(status["runtime"], "retell")
        self.assertTrue(status["connected"])
        # No live adapter is implemented, so it must not claim a live agent.
        self.assertFalse(status["live_ready"])
        self.assertTrue(any("not implemented" in blocker for blocker in status["blockers"]))


class VoiceRuntimeSessionTest(unittest.TestCase):
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

    def clinic_id(self) -> int:
        with storage.db() as conn:
            clinic = [row for row in get_businesses(conn) if row["name"] == "BrightCare Dental Clinic"][0]
            return int(clinic["id"])

    def test_session_uses_detected_urdu_and_knowledge_language(self) -> None:
        business_id = self.clinic_id()
        with storage.db() as conn:
            session = build_runtime_session(
                conn, business_id, caller_text="Assalam o alaikum, mujhe appointment chahiye."
            )
        self.assertEqual(session["language"], "ur")
        self.assertEqual(session["knowledge_language"], "ur")
        self.assertFalse(session["language_fallback_used"])
        self.assertIn("shukriya", session["prompts"]["greeting"].lower())
        self.assertIn("recording_disclosure", session["prompts"])
        self.assertFalse(session["runtime"]["live_ready"])

    def test_session_falls_back_when_language_unsupported(self) -> None:
        business_id = self.clinic_id()
        with storage.db() as conn:
            # BrightCare backfill supports en,ur; Arabic should fall back to the default.
            session = build_runtime_session(conn, business_id, requested_language="ar")
        self.assertIn(session["language"], session["supported_languages"])
        self.assertTrue(session["language_fallback_used"])

    def test_session_rejects_unknown_business(self) -> None:
        with storage.db() as conn:
            with self.assertRaises(ValueError):
                build_runtime_session(conn, 999999)


if __name__ == "__main__":
    unittest.main()
