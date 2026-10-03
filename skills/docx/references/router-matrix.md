# Ultimate Office Suite: Master Decision Router

This reference guide provides the decision criteria and execution pathways for selecting the correct tool in the office automation suite. Follow this matrix before initiating document creation or editing.

---

## 1. Decision Matrix Overview

```
                                  INCOMING USER REQUEST
                                            │
         ┌──────────────────────────────────┼──────────────────────────────────┐
         ▼                                  ▼                                  ▼
   [ON-BRAND MODE]                 [ACADEMIC & MATH MODE]             [DATA PIPELINE MODE]
Company template present           LaTeX math ($$, \frac),           DataFrames, CSV, XLSX,
(.dotx, .potx, .xltx, brandkit)    scientific papers, citations      analytics tables
         │                                  │                                  │
         ▼                                  ▼                                  ▼
    brand-docs                         Pandoc                             python-docx
 (scripts/brandkit/)         (scripts/pandoc/compile_academic)      (scripts/data/dataframe_to_word)
         │                                  │                                  │
         └──────────────────────────────────┼──────────────────────────────────┘
                                            │
         ┌──────────────────────────────────┴──────────────────────────────────┐
         ▼                                                                     ▼
   [EDITORIAL SCRATCH MODE]                                            [LEGAL & ZOTERO SURGERY]
New documents from scratch,                                            Existing Word document,
custom covers, modern layouts, TOC                                     Track Changes (<w:ins>/<w:del>),
         │                                                             live Zotero CSL fields
         ▼                                                                     │
     docx-js                                                                   ▼
 (Node.js engine)                                                          Raw OpenXML
                                                                    (scripts/zotero/ + merge_runs.py)
```

---

## 2. Pathway Specifications

### Pathway 1: On-Brand Corporate Governance (`docx` / `brand-docs`)
* **When to use**:
  - User attaches or references a company template (`.dotx`, `.docx`).
  - Request mentions "sesuai brand kantor", "use our brand kit", or a `./brand-kit` directory exists.
* **Tooling**:
  - `docx` (Word engine powered by `scripts/brandkit/` and `scripts/cli.py`), `brand-pptx` (PowerPoint), `brand-xlsx` (Excel).
* **Execution**:
  1. Extract profile: `python scripts/cli.py extract --name company --template template.dotx`
  2. Verify: `python scripts/cli.py verify --name company`
  3. Generate from `idoc.json`: `python scripts/cli.py generate --name company --input idoc.json -o out.docx`

### Pathway 2: Academic & Mathematical Formulation (Pandoc)
* **When to use**:
  - Document contains LaTeX mathematical notation (`$...$` or `$$...$$`).
  - Academic papers, journal submissions (IEEE, APA, Nature), thesis chapters (*skripsi/tesis*).
  - Bibliography integration from `references.bib` or Zotero export.
* **Tooling**:
  - `scripts/pandoc/compile_academic.py`.
* **Execution**:
  ```bash
  python scripts/pandoc/compile_academic.py manuscript.md -o paper.docx \
    --bibliography references.bib --csl ieee.csl --reference-doc template.docx
  ```
* **Output**: Native Word OMML equations and linked citations.

### Pathway 3: Data Science Tabular Bridge (`python-docx`)
* **When to use**:
  - Generating reports directly from CSV, Excel data sheets, or Pandas output.
  - Adding clean, zebra-striped, auto-aligned summary tables into new or existing `.docx` files.
* **Tooling**:
  - `scripts/data/dataframe_to_word.py`.
* **Execution**:
  ```bash
  python scripts/data/dataframe_to_word.py results.csv -o report.docx \
    --title "Tabel 1: Ringkasan Evaluasi" --header-color "1E2761"
  ```

### Pathway 4: High-Design Editorial Publishing (`docx-js` / `pptxgenjs`)
* **When to use**:
  - Generating complete visual reports, pitch decks, or manuals from scratch with bespoke design.
  - Requires automated Table of Contents (TOC), custom cover pages, and pixel-perfect column layouts (DXA).
* **Tooling**:
  - Node.js script using `docx` or `pptxgenjs`.
* **Gotchas**: Always verify with `soffice.py` + `pdftoppm` for visual QA.

### Pathway 5: Deep Legal Redlining & Live Zotero Surgery (Raw OpenXML)
* **When to use**:
  - Existing `.docx` file with tracked changes (`<w:ins>`, `<w:del>`) and comments.
  - Preserving or injecting live Zotero `CSL_CITATION` field codes (`<w:fldChar>`).
* **Tooling**:
  - `scripts/merge_runs.py` (coalesce fragmented text runs).
  - `scripts/comment.py` (add native Office comments).
  - `scripts/zotero/inspect_zotero.py` (scan active citations).
  - `scripts/zotero/inject_zotero.py` (insert new Zotero CSL field code).
  - `scripts/zotero/validate_zotero.py` (verify field structure).
* **Word Refresh**: The human author clicks **Zotero → Refresh** in the Word Ribbon to re-index all numbers.

### Pathway 6: Reference & Citation Verification (Anti-Hallucination)
* **When to use**:
  - Reviewing AI-written manuscripts, reports, or thesis chapters for fake citations.
  - Validating DOIs, arXiv preprints, PMIDs, or publisher URLs in Word (`.docx`), BibTeX (`.bib`), or Markdown (`.md`).
  - Detecting real DOIs mistakenly or hallucinatorily paired with mismatched paper titles.
* **Tooling**:
  - `scripts/citations/verify_citations.py` (or `citation-verifier` skill).
* **Execution**:
  ```bash
  python scripts/citations/verify_citations.py manuscript.docx --format markdown -o audit_report.md
  ```

---

## 3. Unified Verification Gate

Every output document must pass verification:
1. **Schema Integrity**: `python scripts/office/validate.py out.docx`
2. **Formula Integrity (Excel)**: `python scripts/recalc.py out.xlsx` (must show zero errors)
3. **Zotero Integrity (if citations present)**: `python scripts/zotero/validate_zotero.py out.docx`
4. **Citation Authenticity**: `python scripts/citations/verify_citations.py out.docx` (zero hallucinated citations)
5. **Visual Layout QA**: Render to PDF via `soffice.py` and inspect images via `pdftoppm`.
6. **Publication & Layout Linting**: `python scripts/audit_layout.py out.docx --profile skripsi-id` (or with `--template template.dotx`)
