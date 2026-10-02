#!/usr/bin/env python3
"""Unit tests for audit_manuscript.py covering multi-domain leakage, variance, and suspicion triggers."""

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

    def test_clinical_patient_leakage_detection(self):
        # Medical text with random split and no patient_id
        text = """
        We evaluated our CNN on 2,000 retinal fundus photographs.
        We applied an 80/20 random split for training and testing.
        The model reached 97.4% accuracy.
        """
        audit = audit_manuscript(text, filename="retina.txt")
        severities = [lr["severity"] for lr in audit["leakage_risks"]]
        self.assertIn("CRITICAL", severities)

    def test_tabular_user_leakage_detection(self):
        # Tabular/fintech text with users and random split
        text = """
        We evaluated our gradient boosting model on 50,000 customer transaction records.
        We used a standard train_test_split with 80/20 ratio to evaluate fraud detection.
        """
        audit = audit_manuscript(text, filename="fraud.txt")
        severities = [lr["severity"] for lr in audit["leakage_risks"]]
        categories = [lr["category"] for lr in audit["leakage_risks"]]
        self.assertIn("CRITICAL", severities)
        self.assertIn("Entity / Subject Identity Leakage", categories)

    def test_temporal_lookahead_detection(self):
        # Time series forecasting with random split
        text = """
        We trained an autoregressive model for daily stock price forecasting across 5 years.
        We applied a 10-fold cross-validation with random split across all trading days.
        """
        audit = audit_manuscript(text, filename="stock.txt")
        severities = [lr["severity"] for lr in audit["leakage_risks"]]
        categories = [lr["category"] for lr in audit["leakage_risks"]]
        self.assertIn("CRITICAL", severities)
        self.assertIn("Temporal Lookahead Bias", categories)

    def test_grouped_split_pass(self):
        # Text with proper user-level grouping
        text = """
        We evaluated our recommender system on 100,000 interactions from 2,000 users.
        To avoid entity contamination, we performed a GroupKFold split grouped by user_id.
        All records from a single user were assigned strictly to either the train or test set.
        """
        audit = audit_manuscript(text, filename="recsys_clean.txt")
        severities = [lr["severity"] for lr in audit["leakage_risks"]]
        self.assertIn("PASS", severities)

    def test_variance_reporting_detection(self):
        text_with_variance = "Model achieved 94.2% ± 0.4% accuracy over 5 random seeds."
        audit = audit_manuscript(text_with_variance, filename="variance.txt")
        self.assertTrue(audit["variance_summary"]["has_adequate_variance"])

    def test_suspicion_trigger_classification(self):
        text = "Our proposed model achieved an accuracy of 99.4% on the test split."
        audit = audit_manuscript(text, filename="anomaly_clf.txt")
        strigs = audit.get("suspicion_triggers", [])
        self.assertGreaterEqual(len(strigs), 1)
        self.assertEqual(strigs[0]["severity"], "CRITICAL_SCRUTINY")
        self.assertIn("99.40%", strigs[0]["metric_found"])

    def test_suspicion_trigger_regression_r2(self):
        text = "The regression model achieved an R2 of 0.991 on energy demand forecasting."
        audit = audit_manuscript(text, filename="anomaly_reg.txt")
        strigs = audit.get("suspicion_triggers", [])
        self.assertGreaterEqual(len(strigs), 1)
        self.assertEqual(strigs[0]["severity"], "CRITICAL_SCRUTINY")
        self.assertIn("99.10%", strigs[0]["metric_found"])


if __name__ == "__main__":
    unittest.main()
