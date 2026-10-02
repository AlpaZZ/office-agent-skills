---
name: citation-verifier
description: "Verify citations and references in scientific documents to detect hallucinated, invalid, or mismatched sources. Extracts DOIs, arXiv IDs, PubMed IDs, ISBNs, and URLs from Word (.docx), BibTeX (.bib), Markdown (.md), LaTeX (.tex), and plain text, then validates them using CrossRef, arXiv, PubMed, and Open Library APIs. Detects AI hallucinations where real identifiers are paired with fabricated paper titles."
license: MIT
---

# Citation & Reference Verifier

Detects and flags hallucinated, broken, or mismatched references in academic manuscripts and office documents.

## Purpose

Large Language Models frequently invent convincing but nonexistent citations or pair real DOIs with fabricated paper titles. This skill scans documents, queries authoritative registries (CrossRef, arXiv, PubMed, Open Library), and produces structured audit reports.

---

## When to Use

- Verifying reference lists in research papers, theses, or technical reports.
- Checking Word documents (`.docx`) containing native Zotero field codes (`ADDIN ZOTERO_ITEM CSL_CITATION`).
- Validating BibTeX libraries (`.bib`) before submitting papers to journals.
- Auditing Markdown (`.md`), LaTeX (`.tex`), or text drafts for broken URLs and hallucinated DOIs.
- Running automated CI/CD citation checks on manuscripts.

---

## Supported Identifiers and Registries

| Identifier | Verification Source | Detection Pattern | Notes |
|---|---|---|---|
| **DOI** | CrossRef REST API | `10.xxxx/...` or `doi.org/...` | Checks registry existence and performs fuzzy title comparison. |
| **arXiv ID** | arXiv API | `arXiv:YYMM.NNNNN` or `arxiv.org/abs/...` | Checks official arXiv feed and resolves preprint titles. |
| **PubMed PMID** | NCBI E-utilities | `PMID: NNNNNNN` | Queries PubMed for biomedical literature. |
| **ISBN** | Open Library API | `ISBN: 978-...` | Validates books and monographs. |
| **Publisher URLs** | HTTP GET/HEAD | Nature, IEEE, Springer, ScienceDirect, etc. | Verifies live HTTP 200/300 status codes. |

---

## Command Line Usage

Run the verification script against any manuscript or bibliography file:

```bash
# 1. Standard terminal check (compatible with Windows cp1252)
python scripts/verify_citations.py manuscript.docx

# 2. Generate a clean Markdown audit report for peer review
python scripts/verify_citations.py draft.md --format markdown --output audit_report.md

# 3. Export machine-readable JSON for CI/CD pipelines
python scripts/verify_citations.py library.bib --format json --output audit.json

# 4. Strict mode: exit code 1 on any failure or title mismatch
python scripts/verify_citations.py paper.tex --strict
```

### Options

- `--format {text,markdown,json}`: Report format (default: `text`).
- `-o, --output PATH`: Write report to file instead of stdout.
- `--email EMAIL`: Contact email for the CrossRef polite API pool.
- `--strict`: Return exit code 1 if any citation is missing or has a mismatched title.
- `--no-cache`: Force live API requests bypassing `.citation_cache.json`.
- `--timeout SECONDS`: Network timeout per request (default: 10).

---

## Anti-Hallucination Logic

When verifying DOIs or arXiv papers with title metadata (e.g. from Zotero field codes or BibTeX entries), the verifier compares the local title against the authoritative title in CrossRef:

1. **`[PASS]`**: Identifier exists and the paper title matches (similarity $\ge 0.65$).
2. **`[WARN] METADATA_MISMATCH`**: Identifier exists, but the registry title differs significantly. This catches AI models that attach real DOIs to fake papers.
3. **`[FAIL] NOT_FOUND`**: Identifier does not exist in the official registry.
4. **`[ERR ] LOOKUP_ERROR`**: Temporary network failure or service downtime (never falsely marked as hallucinated).

---

## Credits

- Concept and regex patterns based on [`jkitchin/skillz`](https://github.com/jkitchin/skillz) by John Kitchin.
