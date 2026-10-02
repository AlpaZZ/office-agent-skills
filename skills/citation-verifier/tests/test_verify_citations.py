#!/usr/bin/env python3
"""Unit tests for verify_citations.py covering multi-factor identity, caching, and registries."""

import sys
import unittest
from pathlib import Path

# Add scripts directory to path (supporting both skill structures)
script_dir = Path(__file__).resolve().parent.parent / "scripts"
if (script_dir / "citations").exists():
    sys.path.insert(0, str(script_dir / "citations"))
else:
    sys.path.insert(0, str(script_dir))

from verify_citations import (
    normalize_title,
    titles_match,
    authors_match,
    evaluate_identity,
    scan_raw_text,
    extract_from_bibtex,
    CitationVerifier,
)


class TestCitationVerifier(unittest.TestCase):
    def test_normalize_title(self):
        t1 = "Searching for MobileNetV3!"
        self.assertEqual(normalize_title(t1), "searching for mobilenetv3")

        t2 = "<i>Deep</i> Residual Learning for Image Recognition."
        self.assertEqual(normalize_title(t2), "deep residual learning for image recognition")

    def test_titles_match(self):
        t1 = "Searching for MobileNetV3"
        t2 = "Searching for MobileNetV3"
        matched, score = titles_match(t1, t2)
        self.assertTrue(matched)
        self.assertGreaterEqual(score, 0.9)

        # Mismatched titles
        t_fake = "The Art of Baking Sourdough Bread"
        matched_fake, score_fake = titles_match(t1, t_fake)
        self.assertFalse(matched_fake)
        self.assertLess(score_fake, 0.6)

    def test_authors_match(self):
        # String list with semicolon/comma
        doc_authors = "Howard, Andrew; Sandler, Mark"
        registry_authors = ["Howard Andrew", "Sandler Mark", "Chen Bo"]
        self.assertTrue(authors_match(doc_authors, registry_authors))

        # Different authors
        fake_authors = "Smith, John; Doe, Jane"
        self.assertFalse(authors_match(fake_authors, registry_authors))

    def test_evaluate_identity(self):
        # 1. Exact match
        status, score, _ = evaluate_identity(
            expected_title="Searching for MobileNetV3",
            resolved_title="Searching for MobileNetV3",
            expected_authors="Howard, Andrew",
            resolved_authors=["Howard Andrew"],
            expected_year=2019,
            resolved_year=2019,
        )
        self.assertEqual(status, "IDENTITY_CONFIRMED")
        self.assertGreaterEqual(score, 0.9)

        # 2. Borderline / mismatched authors
        status_part, _, _ = evaluate_identity(
            expected_title="Searching for MobileNetV3",
            resolved_title="Searching for MobileNetV3",
            expected_authors="Smith, John",
            resolved_authors=["Howard Andrew"],
            expected_year=2019,
            resolved_year=2019,
        )
        self.assertEqual(status_part, "METADATA_PARTIAL")

        # 3. Completely different paper title
        status_mismatch, _, _ = evaluate_identity(
            expected_title="A History of Roman Roads",
            resolved_title="Searching for MobileNetV3",
        )
        self.assertEqual(status_mismatch, "METADATA_MISMATCH")

    def test_scan_raw_text(self):
        sample = """
        Here is a paper with DOI: 10.1109/ICCV.2019.00140 and another link
        https://doi.org/10.1038/nature12373. Also check arXiv:2301.07041 and PMID: 25760077.
        Finally ISBN: 978-0-13-468599-1.
        """
        items = scan_raw_text(sample)
        types = {i["type"] for i in items}
        identifiers = {i["identifier"] for i in items}

        self.assertIn("DOI", types)
        self.assertIn("arXiv", types)
        self.assertIn("PMID", types)
        self.assertIn("ISBN", types)

        self.assertIn("10.1109/ICCV.2019.00140", identifiers)
        self.assertIn("10.1038/nature12373", identifiers)
        self.assertIn("2301.07041", identifiers)
        self.assertIn("25760077", identifiers)

    def test_extract_bibtex(self):
        bib = """
        @article{mobilenet,
            title = {Searching for MobileNetV3},
            author = {Howard, Andrew and Sandler, Mark},
            doi = {10.1109/ICCV.2019.00140},
            year = {2019}
        }
        @article{arxivpaper,
            title = {Verifiable FHE},
            eprint = {2301.07041},
            year = {2023}
        }
        """
        entries = extract_from_bibtex(bib)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["doi"], "10.1109/ICCV.2019.00140")
        self.assertEqual(entries[0]["title"], "Searching for MobileNetV3")
        self.assertEqual(entries[1]["eprint"], "2301.07041")

    def test_pmid_cache_title_verification(self):
        verifier = CitationVerifier(no_cache=False, timeout=10)
        # First call: populates cache
        res1 = verifier.verify_pmid("25760077", expected_title="Upregulated lncRNA-UCA1")
        self.assertEqual(res1["status"], "IDENTITY_CONFIRMED")

        # Second call with fake expected title: MUST detect mismatch even from cache
        res2 = verifier.verify_pmid("25760077", expected_title="A Fake Nonexistent Title")
        self.assertEqual(res2["status"], "METADATA_MISMATCH")

    def test_live_crossref_verification(self):
        verifier = CitationVerifier(no_cache=True, timeout=10)

        # 1. Real DOI
        res_real = verifier.verify_doi("10.1109/ICCV.2019.00140", expected_title="Searching for MobileNetV3")
        self.assertEqual(res_real["status"], "IDENTITY_CONFIRMED")
        self.assertIn("MobileNetV3", res_real["title"])

        # 2. Fake / Hallucinated DOI
        res_fake = verifier.verify_doi("10.9999/nonexistent.fake.doi.12345")
        self.assertEqual(res_fake["status"], "NOT_FOUND")

        # 3. Real DOI with Mismatched Title (detect hallucinated reference pairing)
        res_mismatch = verifier.verify_doi("10.1109/ICCV.2019.00140", expected_title="Deep Sea Fish Taxonomy")
        self.assertEqual(res_mismatch["status"], "METADATA_MISMATCH")


if __name__ == "__main__":
    unittest.main()
