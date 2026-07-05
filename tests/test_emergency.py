from __future__ import annotations

import gc
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from callpilot import storage
from callpilot.analysis import analyze_call
from callpilot.emergency import detect_emergency, mask_phone
from callpilot.repositories import get_business, get_businesses, get_services
from callpilot.workflows import create_lead_from_analysis


class EmergencyDetectionTest(unittest.TestCase):
    def test_detects_english_emergency_phrases(self) -> None:
        detection = detect_emergency("My father has chest pain and can't breathe properly.")
        self.assertTrue(detection["detected"])
        self.assertEqual(detection["language"], "en")

    def test_detects_english_typo_with_fuzzy_match(self) -> None:
        detection = detect_emergency("please help he has chest pian right now")
        self.assertTrue(detection["detected"])
        self.assertEqual(detection["match_type"], "fuzzy")

    def test_detects_roman_urdu_and_urdu_script(self) -> None:
        roman = detect_emergency("Hello, meri ammi ko saans nahi aa rahi, jaldi karein.")
        script = detect_emergency("میرے والد کو سینے میں درد ہے")
        self.assertTrue(roman["detected"])
        self.assertEqual(roman["language"], "ur")
        self.assertTrue(script["detected"])
        self.assertEqual(script["language"], "ur")

    def test_detects_arabic_emergency(self) -> None:
        detection = detect_emergency("أرجوكم، والدي لا أستطيع التنفس وهو يفقد وعيه")
        self.assertTrue(detection["detected"])
        self.assertEqual(detection["language"], "ar")

    def test_urgent_but_not_medical_is_not_flagged(self) -> None:
        self.assertFalse(detect_emergency("I need a cleaning appointment today, urgent please.")["detected"])
        self.assertFalse(detect_emergency("")["detected"])

    def test_mask_phone(self) -> None:
        self.assertEqual(mask_phone("+92 300 1234567"), "***4567")
        self.assertEqual(mask_phone(None), "unavailable")


class EmergencyEscalationTest(unittest.TestCase):
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

    def test_emergency_call_escalates_with_phi_free_alert(self) -> None:
        business_id = self.clinic_id()
        transcript = (
            "Hello, my name is Ayesha Malik, my number is 0300 1234567. "
            "My husband has severe chest pain, please help."
        )
        with storage.db() as conn:
            business = get_business(conn, business_id)
            analysis = analyze_call(transcript, business, get_services(conn, business_id), [])
            self.assertTrue(analysis["handoff_triggered"])
            self.assertTrue(analysis["extracted_fields"]["medical_emergency"]["detected"])
            self.assertEqual(analysis["urgency"], "emergency")

            lead = create_lead_from_analysis(conn, business_id, transcript, analysis)
            conn.commit()
            alert = conn.execute(
                "select * from notifications where notification_type = 'emergency_alert' and lead_id = ?",
                (lead["id"],),
            ).fetchone()
            audit = conn.execute(
                "select count(*) from audit_logs where action = 'emergency_escalated'"
            ).fetchone()[0]
            events = conn.execute(
                "select count(*) from agent_events where event_type = 'emergency_escalated' and lead_id = ?",
                (lead["id"],),
            ).fetchone()[0]

        self.assertIsNotNone(alert)
        message = alert["message"]
        # PHI-free: no symptoms, no matched phrase, no name, no full number, no transcript.
        self.assertNotIn("chest pain", message.lower())
        self.assertNotIn("Ayesha", message)
        self.assertNotIn("Malik", message)
        self.assertNotIn("0300 1234567", message)
        self.assertNotIn(transcript, message)
        # But it carries what staff need to act.
        self.assertIn("***4567", message)
        self.assertIn("call the patient back immediately", message)
        self.assertEqual(audit, 1)
        self.assertEqual(events, 1)

    def test_non_emergency_call_creates_no_emergency_alert(self) -> None:
        business_id = self.clinic_id()
        transcript = "Hi, this is Bilal, I want to book a cleaning appointment next week. My number is 0301 7654321."
        with storage.db() as conn:
            business = get_business(conn, business_id)
            analysis = analyze_call(transcript, business, get_services(conn, business_id), [])
            create_lead_from_analysis(conn, business_id, transcript, analysis)
            conn.commit()
            alerts = conn.execute(
                "select count(*) from notifications where notification_type = 'emergency_alert'"
            ).fetchone()[0]
        self.assertEqual(alerts, 0)

    def test_urdu_emergency_alert_reports_language_without_phrase(self) -> None:
        business_id = self.clinic_id()
        transcript = "Assalam o alaikum, mere walid ko dil ka daura par gaya hai, jaldi madad karein."
        with storage.db() as conn:
            business = get_business(conn, business_id)
            analysis = analyze_call(transcript, business, get_services(conn, business_id), [])
            lead = create_lead_from_analysis(conn, business_id, transcript, analysis)
            conn.commit()
            alert = conn.execute(
                "select * from notifications where notification_type = 'emergency_alert' and lead_id = ?",
                (lead["id"],),
            ).fetchone()

        self.assertIsNotNone(alert)
        self.assertIn("Caller language: ur", alert["message"])
        self.assertNotIn("dil ka daura", alert["message"].lower())


if __name__ == "__main__":
    unittest.main()
