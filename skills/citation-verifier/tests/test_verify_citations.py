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
    extract_mendeley_citations_from_docx,
    audit_claim_support,
    load_local_evidence,
)


class TestCitationVerifier(unittest.TestCase):
    def test_claim_audit_requires_mapped_evidence(self):
        results = [{"identifier": "10.1234/example", "evidence_text": "The model improves image classification accuracy on skin disease datasets."}]
        supported = audit_claim_support("The model improves skin disease image classification accuracy (doi:10.1234/example).", results)
        self.assertEqual(supported[0]["status"], "ABSTRACT_SUPPORT")
        unmapped = audit_claim_support("The model cures cancer [1].", results)
        self.assertEqual(unmapped[0]["status"], "UNMAPPED_CITATION")
        unavailable = audit_claim_support("The model improves accuracy (doi:10.1234/example).", [{"identifier": "10.1234/example"}])
        self.assertEqual(unavailable[0]["status"], "EVIDENCE_UNAVAILABLE")

    def test_numeric_claim_uses_citation_map_and_local_evidence(self):
        evidence_dir = Path(self.id())
        evidence_dir.mkdir(exist_ok=True)
        try:
            (evidence_dir / "10.1234-example.txt").write_text("The model improves skin disease image classification accuracy.", encoding="utf-8")
            local = load_local_evidence(evidence_dir)
            result = audit_claim_support("The model improves skin disease image classification accuracy [1].", [{"identifier": "10.1234/example"}], local, {"1": "10.1234/example"})
            self.assertEqual(result[0]["status"], "ABSTRACT_SUPPORT")
            self.assertEqual(result[0]["evidence_refs"][0]["page"], None)
        finally:
            for child in evidence_dir.iterdir(): child.unlink()
            evidence_dir.rmdir()

    def test_normalize_title(self):
        t1 = "Searching for MobileNetV3!"
        self.assertEqual(normalize_title(t1), "searching for mobilenetv3")

        t2 = "<i>Deep</i> Residual Learning for Image Recognition."
        self.assertEqual(normalize_title(t2), "deep residual learning for image recognition")

    def test_titles_match(self):
        t1 = "Searching for MobileNetV3"
        t2 = "Searching for MobileNetV3"
        matched, score, reason = titles_match(t1, t2)
        self.assertTrue(matched)
        self.assertGreaterEqual(score, 0.9)

        # Mismatched titles
        t_fake = "The Art of Baking Sourdough Bread"
        matched_fake, score_fake, _ = titles_match(t1, t_fake)
        self.assertFalse(matched_fake)
        self.assertLess(score_fake, 0.6)

        # Domain conflict: Skin Disease vs Lung Disease
        t_skin = "Deep Learning for Skin Disease Classification"
        t_lung = "Deep Learning for Lung Disease Classification"
        matched_clash, score_clash, reason_clash = titles_match(t_skin, t_lung)
        self.assertFalse(matched_clash)
        self.assertIn("Contradictory domain tokens", reason_clash)

    def test_authors_match(self):
        # First author match
        doc_authors = "Howard, Andrew; Sandler, Mark"
        registry_authors = ["Howard Andrew", "Sandler Mark", "Chen Bo"]
        matched, detail = authors_match(doc_authors, registry_authors)
        self.assertTrue(matched)
        self.assertIn("matches", detail)

        # Completely different authors
        fake_authors = "Smith, John; Doe, Jane"
        matched_fake, detail_fake = authors_match(fake_authors, registry_authors)
        self.assertFalse(matched_fake)
        self.assertIn("mismatch", detail_fake.lower())

        # Weak overlap (single generic surname match with different first author)
        # Expected: Alice Smith, Bob Jones. Registry: Charlie Smith, David White.
        # First author differs, only 1 surname overlap -> should NOT falsely match
        weak_exp = "Alice Smith; Bob Jones"
        weak_reg = ["Charlie Smith", "David White"]
        matched_weak, detail_weak = authors_match(weak_exp, weak_reg)
        self.assertFalse(matched_weak)

    def test_evaluate_identity(self):
        # 1. Exact match (Title, Author, Year all align)
        overall, id_st, meta_st, score, details = evaluate_identity(
            expected_title="Searching for MobileNetV3",
            resolved_title="Searching for MobileNetV3",
            expected_authors="Howard, Andrew",
            resolved_authors=["Howard Andrew"],
            expected_year=2019,
            resolved_year=2019,
        )
        self.assertEqual(overall, "IDENTITY_CONFIRMED")
        self.assertEqual(id_st, "RESOLVED")
        self.assertEqual(meta_st, "MATCH")
        self.assertGreaterEqual(score, 0.9)

        # 2. Epistemic honesty: Identifier resolved, but no in-document title or author provided
        overall_unv, id_unv, meta_unv, _, det_unv = evaluate_identity(
            expected_title="",
            resolved_title="Searching for MobileNetV3",
            expected_authors="",
            resolved_authors=["Howard Andrew"],
        )
        self.assertEqual(overall_unv, "METADATA_UNVERIFIED")
        self.assertEqual(id_unv, "RESOLVED")
        self.assertEqual(meta_unv, "UNVERIFIED")
        self.assertIn("no in-document title or author", det_unv)

        # 3. Year discrepancy (>1 year diff even with matching title and author)
        overall_yr, _, meta_yr, _, _ = evaluate_identity(
            expected_title="Searching for MobileNetV3",
            resolved_title="Searching for MobileNetV3",
            expected_authors="Howard, Andrew",
            resolved_authors=["Howard Andrew"],
            expected_year=2019,
            resolved_year=2025,
        )
        self.assertEqual(overall_yr, "METADATA_PARTIAL")
        self.assertEqual(meta_yr, "PARTIAL")

        # 4. Author discrepancy
        overall_auth, _, meta_auth, _, _ = evaluate_identity(
            expected_title="Searching for MobileNetV3",
            resolved_title="Searching for MobileNetV3",
            expected_authors="Smith, John",
            resolved_authors=["Howard Andrew"],
            expected_year=2019,
            resolved_year=2019,
        )
        self.assertEqual(overall_auth, "METADATA_PARTIAL")
        self.assertEqual(meta_auth, "PARTIAL")

        # 5. Completely different paper title
        overall_mismatch, _, meta_mismatch, _, _ = evaluate_identity(
            expected_title="A History of Roman Roads",
            resolved_title="Searching for MobileNetV3",
        )
        self.assertEqual(overall_mismatch, "METADATA_MISMATCH")
        self.assertEqual(meta_mismatch, "MISMATCH")

    def test_scan_raw_text(self):
        sample = """
        Here is a paper with DOI: 10.1109/ICCV.2019.00140 and another link
        https://doi.org/10.1038/nature12373. Also check arXiv:2301.07041 and PMID: 25760077.
        Finally ISBN: 978-0-13-468599-1 and URL https://www.nature.com/articles/s41586-020-2649-2.
        """
        items = scan_raw_text(sample)
        types = {i["type"] for i in items}
        identifiers = {i["identifier"] for i in items}

        self.assertIn("DOI", types)
        self.assertIn("arXiv", types)
        self.assertIn("PMID", types)
        self.assertIn("ISBN", types)
        self.assertIn("URL", types)

        self.assertIn("10.1109/ICCV.2019.00140", identifiers)
        self.assertIn("10.1038/nature12373", identifiers)
        self.assertIn("2301.07041", identifiers)
        self.assertIn("25760077", identifiers)
        self.assertIn("https://www.nature.com/articles/s41586-020-2649-2", identifiers)

    def test_extract_bibtex_multi_identifier(self):
        import tempfile
        from verify_citations import harvest_document_citations

        bib = """
        @article{mobilenet,
            title = {Searching for {MobileNetV3}},
            author = {Howard, Andrew and Sandler, Mark},
            doi = {10.1109/ICCV.2019.00140},
            pmid = {25760077},
            eprint = {1905.02244},
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
        # Check brace removal for protected capitalization
        self.assertEqual(entries[0]["title"], "Searching for MobileNetV3")
        self.assertEqual(entries[0]["doi"], "10.1109/ICCV.2019.00140")
        self.assertEqual(entries[0]["pmid"], "25760077")
        self.assertEqual(entries[0]["eprint"], "1905.02244")

        # Test harvest_document_citations expands all coexisting identifiers without elif skipping
        with tempfile.NamedTemporaryFile("w", suffix=".bib", delete=False, encoding="utf-8") as tf:
            tf.write(bib)
            tpath = Path(tf.name)

        try:
            candidates = harvest_document_citations(tpath)
            cand_types = {c["type"] for c in candidates if c.get("title") == "Searching for MobileNetV3"}
            self.assertIn("DOI", cand_types)
            self.assertIn("PMID", cand_types)
            self.assertIn("arXiv", cand_types)
        finally:
            if tpath.exists():
                tpath.unlink()

    def test_extract_mendeley_csl_field(self):
        import json
        import tempfile
        import zipfile

        field = {
            "citationItems": [{
                "itemData": {
                    "DOI": "10.1234/example",
                    "title": "Mendeley field paper",
                    "author": [{"family": "Doe", "given": "Jane"}],
                    "issued": {"date-parts": [[2024]]},
                }
            }]
        }
        xml = f"<w:instrText>ADDIN CSL_CITATION {json.dumps(field)} CSL_CITATION</w:instrText>"
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tf:
            path = Path(tf.name)
        try:
            with zipfile.ZipFile(path, "w") as zf:
                zf.writestr("word/document.xml", xml)
            items = extract_mendeley_citations_from_docx(path)
            self.assertEqual(items[0]["source"], "Mendeley (word/document.xml)")
            self.assertEqual(items[0]["doi"], "10.1234/example")
        finally:
            path.unlink(missing_ok=True)

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

        # 1. Real DOI with matching title
        res_real = verifier.verify_doi("10.1109/ICCV.2019.00140", expected_title="Searching for MobileNetV3")
        self.assertEqual(res_real["status"], "IDENTITY_CONFIRMED")
        self.assertEqual(res_real["metadata_status"], "MATCH")
        self.assertIn("MobileNetV3", res_real["title"])

        # 2. Real DOI without in-doc title (epistemic honesty: METADATA_UNVERIFIED)
        res_no_title = verifier.verify_doi("10.1109/ICCV.2019.00140")
        self.assertEqual(res_no_title["status"], "METADATA_UNVERIFIED")
        self.assertEqual(res_no_title["identifier_status"], "RESOLVED")
        self.assertEqual(res_no_title["metadata_status"], "UNVERIFIED")

        # 3. Fake / Hallucinated DOI
        res_fake = verifier.verify_doi("10.9999/nonexistent.fake.doi.12345")
        self.assertEqual(res_fake["status"], "NOT_FOUND")
        self.assertEqual(res_fake["identifier_status"], "NOT_FOUND")

        # 4. Real DOI with Mismatched Title (detect hallucinated reference pairing)
        res_mismatch = verifier.verify_doi("10.1109/ICCV.2019.00140", expected_title="Deep Sea Fish Taxonomy")
        self.assertEqual(res_mismatch["status"], "METADATA_MISMATCH")
        self.assertEqual(res_mismatch["metadata_status"], "MISMATCH")

    def test_url_verification_status(self):
        verifier = CitationVerifier(no_cache=True, timeout=5)
        res = verifier.verify_url("https://www.google.com")
        if res["status"] != "LOOKUP_ERROR":
            # Accessible URL MUST be URL_ACCESSIBLE, never falsely IDENTITY_CONFIRMED
            self.assertEqual(res["status"], "URL_ACCESSIBLE")
            self.assertEqual(res["identifier_status"], "ACCESSIBLE")
            self.assertEqual(res["metadata_status"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
