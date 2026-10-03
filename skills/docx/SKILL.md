---
name: docx
description: "Comprehensive Word document (.docx/.dotx) engine for creating, editing, styling, and reviewing documents. Covers: (1) On-brand corporate document generation and template extraction via the Brand Engine (extract, comprehend, verify, generate from .dotx/.docx templates and IntermediateDocuments), (2) Layout, margins, typography, and visual image blur/DPI linting via audit_layout.py (Indonesian Skripsi 4-4-3-3 cm, JIKI SINTA 2 2-column, APA 7th, or auto-extracted template profiles), (3) Academic papers with LaTeX math equations and Zotero/BibTeX citations via Pandoc, (4) Editorial document generation from scratch via docx-js, (5) Data science tabular injection via python-docx, (6) Legal redlining with Tracked Changes and native comments via OpenXML surgery, (7) Live Zotero CSL field code inspection and injection, and (8) Automated citation verification against CrossRef, arXiv, and PubMed. Trigger on any mention of Word documents, reports, proposals, memos, templates, thesis/skripsi formatting, brand kits, matching templates, or DOCX manipulation."
license: MIT
---

# Unified DOCX Creation, Editing, Brand & Analysis Suite

The definitive Microsoft Word (`.docx` / `.dotx`) engine for AI coding agents. Choose the optimal execution pathway based on user requirements:

| Task / Domain | Engine / Approach | When to Choose |
|---|---|---|
| **On-Brand Corporate** | `scripts/brandkit/` (`scripts/cli.py`) | Preserving company brand profiles, official fonts, colors, and layout shells fail-closed from templates. |
| **Layout & Visual Linter** | `scripts/audit_layout.py` | Auditing margins (4-4-3-3 cm skripsi / 3-3-3-3 cm journal), fonts, line spacing, image DPI (<150 DPI), Laplacian blur, caption positions, and TOC. |
| **Academic & Math** | `scripts/pandoc/compile_academic.py` | Papers with LaTeX math formulas (`$$...$$`), footnotes, and linked Zotero/BibTeX bibliographies. |
| **Citation Verification** | `scripts/citations/verify_citations.py` | Auditing documents for fake/hallucinated DOIs, broken URLs, and metadata mismatches against CrossRef/arXiv/PubMed. |
| **Zotero Citations** | `scripts/zotero/` | Inspecting, injecting, or validating live dynamic `ADDIN ZOTERO_ITEM CSL_CITATION` fields without unlinking. |
| **Data Science Tables** | `scripts/data/dataframe_to_word.py` | Injecting CSV, Excel, or JSON data into styled, zebra-striped Word tables with right-aligned numbers. |
| **Editorial Scratch** | `docx-js` (Node.js script) | New documents from scratch requiring bespoke visual layouts, cover pages, and automated TOCs. |
| **Legal Redline** | Raw OpenXML (`<w:ins>`, `<w:del>`) | Contract reviews, tracked revisions, and multi-file comments (`scripts/comment.py`). |

> Detailed decision logic and routing criteria are in [`references/router-matrix.md`](references/router-matrix.md).

---

## 1. On-Brand Corporate Governance & Generation (Brand Engine)

Use this pathway when the user provides or references a company template (`.dotx` / `.docx`) or asks to "match our template", "use our brand kit", or generate an on-brand document from variable content.

### The Seven Verbs
The engine implements three deterministic core verbs plus four model-assisted learning verbs:

| Verb | Input | Output | CLI Command |
|---|---|---|---|
| **extract** | A company `.docx` or `.dotx` template | A reusable Brand Profile (`brand-kit/<name>/`) | `python scripts/cli.py extract --name <brand> --template <template.docx>` |
| **comprehend** *(optional)* | Saved profile + model-authored `comprehension.json` | Profile with validated, cached `comprehension` block | `python scripts/cli.py comprehend --name <brand> --input comprehension.json` |
| **verify** | Saved Brand Profile | QA findings + deterministic verdict | `python scripts/cli.py verify --name <brand>` |
| **generate** | Content (`IntermediateDocument`) + profile | New on-brand `.docx` | `python scripts/cli.py generate --name <brand> --input idoc.json -o out.docx` |
| **learn** | Profile's cross-run history | Recurring findings distilled to shell-frozen overrides | `python scripts/cli.py learn --name <brand> --accept` |
| **propose-overrides** | Residual issues + proposal | Shell-backed corrections fail-closed | `python scripts/cli.py propose-overrides --name <brand> --input overrides.json --accept` |
| **refine** | User feedback delta | Comprehension overlaid for future generations | `python scripts/cli.py refine --name <brand> --input refinement.json --accept` |

### Hard Rules for Brand Generation
1. `scripts/cli.py` (or `scripts/brand_cli.py`) is the launcher. It automatically resolves the engine root.
2. Run preflight (`python scripts/cli.py doctor`) before extraction or generation to verify system readiness.
3. **Extract** opens the template read-only and saves `brand-kit/<name>/template/shell.docx` byte-for-byte.
4. **Generate** opens the saved shell and resolves every semantic block through `profile.json`.
5. **Author role-first, not style-first**: Do not put font names, pt sizes, hex colors, or raw style names in an `IntermediateDocument` (`idoc.json`). Consult `brand-kit/<name>/PROFILE.md` for role vocabulary (`heading`, `paragraph`, `list`, `table`, `caption`, `callout`).
6. See [`references/comprehension.md`](references/comprehension.md), [`references/profile-schema.md`](references/profile-schema.md), and [`examples/intermediate-document.example.json`](examples/intermediate-document.example.json) for full schemas.

---

## 2. Comprehensive Layout, Typography & Visual Linter

Audits Word documents against publication guidelines, institutional templates, or thesis guidelines:

```bash
# 1. Audit Indonesian thesis / skripsi format (UI: 4-4-3-3 cm margins, 1.5/2.0 spacing, 300 DPI images)
python scripts/audit_layout.py manuscript.docx --profile skripsi-id

# 2. Audit academic journal format (JIKI UI / SINTA 2: 2 columns, 3-3-3-3 cm margins, single space)
python scripts/audit_layout.py manuscript.docx --profile jiki-journal

# 3. Auto-extract layout criteria directly from any reference template (.docx/.dotx)
python scripts/audit_layout.py manuscript.docx --template AuthorGuideline_JIKI.docx

# 4. Explicit CLI overrides for custom guidelines
python scripts/audit_layout.py manuscript.docx \
  --margins 4.0 4.0 3.0 3.0 \
  --font "Times New Roman" \
  --line-spacing 1.5 \
  --columns 1 \
  --table-caption above \
  --figure-caption below \
  --require-toc \
  --min-dpi 300

# 5. Export structured JSON for automated pipelines
python scripts/audit_layout.py manuscript.docx --format json -o layout_audit.json
```

**Checked Dimensions & Standards**:
- **Layout & Page Setup**: Margins (Top, Bottom, Left, Right in cm), Paper Size (A4 vs Letter), Orientation, Columns (1 vs 2 columns), Section Breaks, Hyphenation.
- **Typography & Font Integrity**: Font family consistency, size hierarchy, accidental non-black text (#000000 check), lingering highlight markers.
- **Paragraph & Line Spacing**: Alignment (Justify / `both`), line spacing (Single vs 1.5 vs Double), paragraph spacing before/after.
- **Headings & Structure**: Proper `Heading 1/2/3` styles vs raw unstyled bold text ("Fake Headings" that break Navigation Pane and TOC).
- **Captions & TOC**: Table captions ABOVE table (`Tabel X.Y...`), Figure captions BELOW figure (`Gambar X.Y...`), Table of Contents (`TOC`), List of Tables, List of Figures.
- **Math Equations**: Native OMML / LaTeX (`<m:oMath>`) vs formulas pasted as raster pictures or screenshots.
- **Image Quality & Blurriness**: Effective DPI calculation (<150 DPI critical failure), Laplacian blur variance, aspect ratio distortion (squished/stretched images).
- **Table Formatting**: Column overflow beyond printable margin width, academic three-line tables (no vertical borders), header repeat.
- **Header & Footer**: Page numbering configuration.

---

## 3. Academic & LaTeX Math Pathway (Pandoc)

Converts Markdown with LaTeX math syntax (`$...$` and `$$...$$`) directly to native Word OMML Equations and resolves citations:

```bash
# Basic compile with native Word equations
python scripts/pandoc/compile_academic.py draft.md -o paper.docx

# Academic compile with Zotero/BibTeX citations and journal CSL style
python scripts/pandoc/compile_academic.py draft.md -o paper.docx \
  --bibliography references.bib \
  --csl ieee.csl \
  --reference-doc template.docx
```

---

## 4. Citation & Reference Verification (Anti-Hallucination)

Detects fake, broken, or mismatched citations in Word documents, BibTeX files, and Markdown drafts against CrossRef, arXiv, PubMed, and Open Library:

```bash
# 1. Audit a Word document (checks Zotero CSL XML and body references)
python scripts/citations/verify_citations.py manuscript.docx

# 2. Generate a clean Markdown audit report for peer review
python scripts/citations/verify_citations.py draft.md --format markdown -o audit_report.md

# 3. Export machine-readable JSON for CI/CD checks
python scripts/citations/verify_citations.py references.bib --format json -o audit.json
```

---

## 5. Dynamic Zotero CSL Field Code Management

Never flatten Zotero citations into static text. Manage dynamic OpenXML field codes (`ADDIN ZOTERO_ITEM CSL_CITATION`) directly:

```bash
# 1. Inspect existing citations in a document
python scripts/zotero/inspect_zotero.py manuscript.docx

# 2. Inject a new Zotero CSL citation with metadata
python scripts/zotero/inject_zotero.py manuscript.docx \
  --after "MobileNetV3" \
  --citation-text "[39]" \
  --title "Searching for MobileNetV3" \
  --authors "Howard, Andrew; Sandler, Mark" \
  --year 2019 \
  --venue "ICCV" \
  --doi "10.1109/ICCV.2019.00140" \
  -o updated_manuscript.docx

# 3. Validate XML integrity
python scripts/zotero/validate_zotero.py updated_manuscript.docx
```

After modifying citations, the human author simply opens the document in Microsoft Word and clicks **Zotero → Refresh** in the Ribbon. Detailed guide in [`references/zotero.md`](references/zotero.md).

---

## 6. Data Science Tabular Pathway (python-docx)

Injects structured data into professionally styled tables with auto-fitted column widths and number alignment:

```bash
# Append a styled table from CSV or Excel into a document
python scripts/data/dataframe_to_word.py results.csv -o report.docx \
  --title "Tabel 1: Ringkasan Hasil Evaluasi" \
  --header-color "1E2761"
```

---

## 7. Editorial Creation with docx-js

For bespoke documents created from scratch, write a Node.js script using `docx`:

- **Page size:** Default is A4. For US Letter: `page: { size: { width: 12240, height: 15840 } }` (DXA).
- **Tables:** Set `columnWidths` on the table AND `width` on every cell in `WidthType.DXA`.
- **Shading:** Use `ShadingType.CLEAR`, never `SOLID`.
- **Lists:** Use a `numbering` configuration with `LevelFormat.BULLET`, never literal bullets.
- **TOC:** Headings must use built-in `HeadingLevel.*` or set `outlineLevel`.
- **Dot-leader tabs:** Use `PositionalTab` with `leader: PositionalTabLeader.DOT`.

---

## 8. Legal Redlining & Document Surgery (Raw OpenXML)

For contract reviews and deep XML modifications:

```bash
unzip -q doc.docx -d unpacked/
python scripts/merge_runs.py unpacked/          # coalesce fragmented text runs
# edit unpacked/word/document.xml in place
(cd unpacked && rm -f ../out.docx && zip -Xr ../out.docx .)
python scripts/office/validate.py out.docx --original doc.docx
```

- **Tracked changes:** Wrap modified text in `<w:ins>` / `<w:del>` with `w:id`, `w:author`, and `w:date`.
- **Comments:** Use `python scripts/comment.py unpacked/ "Komentar hukum..."` to manage the six cross-linked XML comment files cleanly.

---

## 9. Unified Verification Gate

Every output document must pass verification before returning to the user:
1. **Schema Integrity**: `python scripts/office/validate.py out.docx`
2. **Layout & Standards Linting**: `python scripts/audit_layout.py out.docx --profile skripsi-id` (or `--template guideline.docx`)
3. **Citation Authenticity**: `python scripts/citations/verify_citations.py out.docx` (zero hallucinated citations)
4. **Zotero Integrity (if citations present)**: `python scripts/zotero/validate_zotero.py out.docx`
5. **Visual Layout QA**: Render to PDF via `soffice.py` and inspect images via `pdftoppm`.

## Dependencies

`docx` (npm) · `pandoc` · `python-docx` · `openpyxl` · `Pillow` · `numpy` · LibreOffice (`soffice`) · `pdftoppm` (Poppler)
