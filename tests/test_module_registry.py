from __future__ import annotations

import unittest

from callpilot.modules import INDUSTRY_MODULES, module_by_key, module_for_business_type, module_options


class ModuleRegistryTest(unittest.TestCase):
    def test_pdf_pack_modules_are_registered(self) -> None:
        self.assertGreaterEqual(len(INDUSTRY_MODULES), 11)
        self.assertIn("healthcare", INDUSTRY_MODULES)
        self.assertIn("hospitality", INDUSTRY_MODULES)
        self.assertIn("restaurant", INDUSTRY_MODULES)
        self.assertIn("sales", INDUSTRY_MODULES)
        self.assertIn("admin_services", INDUSTRY_MODULES)

    def test_every_module_has_required_contract_fields(self) -> None:
        for key, module in INDUSTRY_MODULES.items():
            with self.subTest(module=key):
                self.assertTrue(module["label"])
                self.assertTrue(module["business_types"])
                self.assertTrue(module["intake_fields"])
                self.assertTrue(module["allowed_call_types"])
                self.assertTrue(module["blocked_outcomes"])
                self.assertTrue(module["compliance_profile"])
                self.assertTrue(module["language_policy"])
                self.assertTrue(module["integration_targets"])
                self.assertTrue(module["qa_checks"])

    def test_business_type_mapping_uses_custom_fallback(self) -> None:
        self.assertEqual(module_for_business_type("Clinic")["key"], "healthcare")
        self.assertEqual(module_for_business_type("Hotel")["key"], "hospitality")
        self.assertEqual(module_for_business_type("Software Agency")["key"], "sales")
        self.assertEqual(module_for_business_type("Unknown New Industry")["key"], "custom")

    def test_module_options_expose_labels(self) -> None:
        options = dict(module_options())

        self.assertIn("healthcare", options)
        self.assertIn("real_estate", options)
        self.assertIn("commerce", options)

    def test_module_detail_payload(self) -> None:
        module = module_by_key("healthcare")

        self.assertEqual(module["key"], "healthcare")
        self.assertIn("Urgent", " ".join(module["qa_checks"]))
        self.assertIn("HIPAA", module["compliance_profile"])


if __name__ == "__main__":
    unittest.main()
