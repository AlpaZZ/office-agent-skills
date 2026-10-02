---
name: docx
description: "Comprehensive Word document (.docx/.dotx) engine for creating, editing, styling, and reviewing documents. Covers: (1) Layout, margins, typography, and visual image blur/DPI linting via audit_layout.py, (2) Editorial document generation from scratch via docx-js, (3) Academic papers with LaTeX math equations and Zotero/BibTeX citations via Pandoc, (4) Data science tabular injection via python-docx, (5) Legal redlining with Tracked Changes and native comments via OpenXML surgery, (6) Live Zotero CSL field code inspection and injection, and (7) Automated citation verification against CrossRef, arXiv, and PubMed. Trigger on any mention of Word documents, reports, proposals, memos, templates, thesis/skripsi formatting, or DOCX manipulation."
license: MIT
---

# DOCX Creation, Editing, and Analysis Suite

Choose the optimal execution pathway based on task requirements:

| Task / Domain | Engine / Approach | When to Choose |
|---|---|---|
| **Editorial Scratch** | `docx-js` (npm script) | New documents from scratch requiring bespoke visual layouts, cover pages, and automated TOCs. |
| **Academic & Math** | `scripts/pandoc/compile_academic.py` | Papers with LaTeX math formulas (`$$...$$`), footnotes, and linked Zotero/BibTeX bibliographies. |
| **Data Science Tables** | `scripts/data/dataframe_to_word.py` | Injecting CSV, Excel, or JSON data into styled, zebra-striped Word tables. |
| **On-Brand Corporate** | `brand-docx` (`scripts/brandkit/`) | Preserving company brand profiles, official fonts, colors, and layout shells fail-closed. |
| **Legal Redline** | Raw OpenXML (`<w:ins>`, `<w:del>`) | Contract reviews, tracked revisions, and multi-file comments (`scripts/comment.py`). |
| **Zotero Citations** | `scripts/zotero/` | Inspecting, injecting, or validating live `CSL_CITATION` fields without unlinking. |
| **Citation Verification** | `scripts/citations/` | Auditing documents for fake/hallucinated DOIs, broken URLs, and metadata mismatches against CrossRef/arXiv/PubMed. |

> Detailed decision logic and routing criteria are in [`references/router-matrix.md`](references/router-matrix.md).

---

## 1. Academic & LaTeX Math Pathway (Pandoc)

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

## 2. Data Science Tabular Pathway (python-docx)

Injects structured data into professionally styled tables with auto-fitted column widths and number alignment:

```bash
# Append a styled table from CSV or Excel into a document
python scripts/data/dataframe_to_word.py results.csv -o report.docx \
  --title "Tabel 1: Ringkasan Hasil Evaluasi" \
  --header-color "1E2761"
```

---

## 3. Zotero CSL Field Code Management

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

## 4. Citation & Reference Verification (Anti-Hallucination)

Detects fake, broken, or mismatched citations in Word documents, BibTeX files, and Markdown drafts against CrossRef, arXiv, and PubMed:

```bash
# 1. Audit a Word document (checks Zotero CSL XML and body references)
python scripts/citations/verify_citations.py manuscript.docx

# 2. Generate a clean Markdown audit report for peer review
python scripts/citations/verify_citations.py draft.md --format markdown -o audit_report.md

# 3. Export machine-readable JSON for CI/CD checks
python scripts/citations/verify_citations.py references.bib --format json -o audit.json
```

---

## 5. Comprehensive Layout, Typography & Visual Linter

Audits Word documents against publication standards (margins, font hierarchy, line spacing, image DPI, equation types, table overflow, captions, and TOC):

```bash
# 1. Audit Indonesian thesis / skripsi format (4-4-3-3 cm margins, 1.5/2.0 spacing, 300 DPI images)
python scripts/audit_layout.py manuscript.docx --profile skripsi-id

# 2. Audit academic journal format (JIKI UI / SINTA 2 - 2 columns, 3-3-3-3 cm margins, single space)
python scripts/audit_layout.py manuscript.docx --profile jiki-journal

# 3. Audit general academic format (APA 7th - 1 inch margins, double spaced)
python scripts/audit_layout.py manuscript.docx --profile general

# 4. Export structured JSON for automated pipelines
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

## 6. Editorial Creation with docx-js

For bespoke documents created from scratch, write a Node.js script using `docx`:

- **Page size:** Default is A4. For US Letter: `page: { size: { width: 12240, height: 15840 } }` (DXA).
- **Tables:** Set `columnWidths` on the table AND `width` on every cell in `WidthType.DXA`.
- **Shading:** Use `ShadingType.CLEAR`, never `SOLID`.
- **Lists:** Use a `numbering` configuration with `LevelFormat.BULLET`, never literal bullets.
- **TOC:** Headings must use built-in `HeadingLevel.*` or set `outlineLevel`.
- **Dot-leader tabs:** Use `PositionalTab` with `leader: PositionalTabLeader.DOT`.

---

## 7. Legal Redlining & Document Surgery (Raw OpenXML)

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

## 8. Schema Validation & Visual Quality Assurance

Always verify document deliverables before presenting to the user:

1. **Schema Check:** `python scripts/office/validate.py output.docx`
2. **Visual Inspection:**
   ```bash
   python scripts/office/soffice.py --headless --convert-to pdf output.docx
   pdftoppm -jpeg -r 100 output.pdf page
   ls page-*.jpg   # inspect rendered images for layout defects
   ```

## Dependencies

`docx` (npm) · `pandoc` · `python-docx` · `openpyxl` · `Pillow` · `numpy` · LibreOffice (`soffice`) · `pdftoppm` (Poppler)

