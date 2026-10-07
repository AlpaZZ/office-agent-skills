# Ultimate Office Suite: Master Decision Router

This reference guide provides the decision criteria and execution pathways for selecting the correct tool in the office automation suite. Follow this matrix before initiating document creation or editing.

## 0. Template gate

Before any DOCX authoring or formatting change, ask whether a `.docx`/`.dotx` template, institutional guide, or example document exists. If one exists, inspect the complete package and create a contract first:

```bash
python scripts/template_rules.py template.docx -o template-rules.md
```

If none exists, ask the user to choose a named baseline such as APA 7, a journal guide, the `general` profile, or an institutional standard. Record that choice before formatting. Never assume a country, university, publisher, or language-specific convention.

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
  - `docx` (Word), `pptx` (PowerPoint), `xlsx` (Excel) — each equipped with native `scripts/brandkit/` and `scripts/cli.py` engines.
* **Execution**:
  1. Extract profile: `python scripts/cli.py extract --name company --template template.dotx`
  2. Verify: `python scripts/cli.py verify --name company`
  3. Generate from `idoc.json`: `python scripts/cli.py generate --name company --input idoc.json -o out.docx`

### Pathway 2: Academic & Mathematical Formulation (Pandoc)
* **When to use**:
  - Document contains LaTeX mathematical notation (`$...$` or `$$...$$`).
  - Academic papers, journal submissions, theses, and technical reports with a named style guide.
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

### Pathway 5: Deep Legal Redlining & Live Zotero/Mendeley Surgery (Raw OpenXML)
* **When to use**:
  - Existing `.docx` file with tracked changes (`<w:ins>`, `<w:del>`) and comments.
  - Preserving live Zotero or legacy Mendeley `CSL_CITATION` field codes (`<w:fldChar>`).
* **Tooling**:
  - `scripts/merge_runs.py` (coalesce fragmented text runs).
  - `scripts/comment.py` (add native Office comments).
  - `scripts/zotero/inspect_zotero.py` (scan active citations).
  - `scripts/zotero/inject_zotero.py` (insert new Zotero CSL field code).
  - `scripts/zotero/validate_zotero.py` (verify field structure).
* **Word Refresh**: The human author refreshes the owning manager in Word: **Zotero → Refresh** or **Mendeley Cite → refresh/update**.

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

Run the checks that apply to the output:
1. **Schema Integrity**: `python scripts/office/validate.py out.docx`
2. **Template/Layout Contract**: `python scripts/audit_layout.py out.docx --template template.dotx` when a template exists.
3. **Final DOCX Quality**: `python scripts/docx_quality.py out.docx --template template.dotx --fix-fields --render-dir qa-render`.
4. **Native Captions**: confirm captions use Word `SEQ` fields and the correct placement.
5. **Citation Authenticity**: run `scripts/citations/verify_citations.py` when citations or identifiers exist; it reads Zotero and Mendeley fields.
6. **Zotero Integrity**: run `scripts/zotero/validate_zotero.py` only when Zotero fields exist.
7. **Formula Integrity (Excel)**: `python scripts/recalc.py out.xlsx` for workbooks.
8. **Visual Layout QA**: inspect the PDF produced by `docx_quality.py` whenever visual layout is part of the request.
