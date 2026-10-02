#!/usr/bin/env python3
"""Unit tests for audit_manuscript.py"""

import sys
import unittest
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from audit_manuscript import audit_manuscript, extract_sentences


class TestManuscriptAuditor(unittest.TestCase):
    def test_extract_sentences(self):
        text = "This is sentence one. Here is sentence two with more details! And sentence three?"
        sentences = extract_sentences(text)
        self.assertGreaterEqual(len(sentences), 2)

    def test_claim_detection(self):
        text = """
        Our proposed model significantly improves classification accuracy by 4.2% over the baseline.
        The novel architecture achieves an accuracy of 98.5%.
        This undeniably proves that our method solves diabetic retinopathy screening.
        """
        audit = audit_manuscript(text, filename="test.txt")
        claims = audit["claims_found"]
        self.assertGreaterEqual(len(claims), 2)
        
        statuses = {c["suggested_status"] for c in claims}
        self.assertIn("NEEDS_STATISTICAL_TEST", statuses)
        self.assertIn("TONE_OVERCLAIM", statuses)

    def test_patient_leakage_detection(self):
        # Medical text with random split and no patient_id
        text = """
        We evaluated our CNN on 2,000 retinal fundus photographs.
        We applied an 80/20 random split for training and testing.
        The model reached 97.4% accuracy.
        """
        audit = audit_manuscript(text, filename="retina.txt")
        severities = [lr["severity"] for lr in audit["leakage_risks"]]
        self.assertIn("CRITICAL", severities)

    def test_patient_split_pass(self):
        # Medical text with proper patient-level grouping
        text = """
        We evaluated our CNN on 2,000 retinal fundus photographs from 500 patients.
        To prevent data contamination, we performed a GroupKFold split grouped by patient_id.
        All images from a single patient were assigned exclusively to either the train or test set.
        """
        audit = audit_manuscript(text, filename="retina_clean.txt")
        severities = [lr["severity"] for lr in audit["leakage_risks"]]
        self.assertIn("PASS", severities)

    def test_variance_reporting_detection(self):
        text_with_variance = "Model achieved 94.2% ± 0.4% accuracy over 5 random seeds."
        audit = audit_manuscript(text_with_variance, filename="variance.txt")
        self.assertTrue(audit["variance_summary"]["has_adequate_variance"])

    def test_suspicion_trigger_detection(self):
        text = "Our proposed vision model achieved an accuracy of 99.4% on the test split."
        audit = audit_manuscript(text, filename="anomaly.txt")
        strigs = audit.get("suspicion_triggers", [])
        self.assertGreaterEqual(len(strigs), 1)
        self.assertEqual(strigs[0]["severity"], "CRITICAL_SCRUTINY")
        self.assertIn("99.40%", strigs[0]["metric_found"])


if __name__ == "__main__":
    unittest.main()
