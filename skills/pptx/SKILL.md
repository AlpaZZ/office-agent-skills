---
name: pptx
description: "Comprehensive PowerPoint (.pptx/.potx) presentation engine. Covers: (1) On-brand corporate deck generation & template extraction via the Brand Engine (extract, comprehend, verify, generate from .pptx/.potx templates and IntermediateDocuments), (2) Creating bespoke decks from scratch via pptxgenjs, (3) Editing, duplicating, and cleaning existing slides via OpenXML surgery (add_slide.py, clean.py), (4) Slide thumbnail analysis & visual grid (thumbnail.py), (5) Native chart and schema validation (validate.py), and (6) Headless PDF rendering (soffice.py). Trigger on any mention of slide decks, presentations, pitch decks, .pptx, .potx, brand deck templates, or PowerPoint manipulation."
license: MIT
---

# Unified PPTX Creation, Editing, Brand & Analysis Suite

A `.pptx` is a ZIP archive of OpenXML files. Choose your approach based on task requirements:

| Task / Domain | Engine / Approach | When to Choose |
|---|---|---|
| **On-Brand Corporate Deck** | `scripts/brandkit/` (`scripts/cli.py`) | Extracting reusable Brand Profiles from company `.pptx`/`.potx` templates and generating on-brand decks fail-closed from IntermediateDocuments. |
| **Create Bespoke Deck** | `pptxgenjs` (Node.js script) | Building brand-new decks from scratch with complete programmatic design, shapes, and custom layouts. |
| **Edit Existing Deck / Duplicate** | `scripts/add_slide.py`, `clean.py` | Duplicating layout slides, removing orphaned media, reordering slides, or surgical OpenXML edits. |
| **Slide Thumbnails & Inspection** | `scripts/thumbnail.py` | Generating visual overview grids of template slides to select master layouts. |
| **Validate Schema & Charts** | `scripts/office/validate.py` | Validating OpenXML schema compliance, slide relationships, and native chart configurations. |

---

## 1. On-Brand Corporate Deck Governance (Brand Engine)

Use this pathway when the user provides or references a company presentation template (`.pptx` / `.potx`) or asks to "match our deck template", "use our brand kit", or generate an on-brand presentation from an outline or draft.

### The Seven Verbs
The engine implements three deterministic core verbs plus four model-assisted learning verbs:

| Verb | Input | Output | CLI Command |
|---|---|---|---|
| **extract** | A company `.pptx` or `.potx` template | A reusable Brand Profile (`brand-kit/<name>/`) | `python scripts/cli.py extract --name <brand> --template <template.pptx>` |
| **comprehend** *(optional)* | Saved profile + model-authored `comprehension.json` | Profile with validated, cached `comprehension` block | `python scripts/cli.py comprehend --name <brand> --input comprehension.json` |
| **verify** | Saved Brand Profile | QA findings + deterministic verdict | `python scripts/cli.py verify --name <brand>` |
| **generate** | Content (`IntermediateDocument`) + profile | New on-brand `.pptx` | `python scripts/cli.py generate --name <brand> --input idoc.json -o out.pptx` |
| **learn** | Profile's cross-run history | Recurring findings distilled to shell-frozen overrides | `python scripts/cli.py learn --name <brand> --accept` |
| **propose-overrides** | Residual issues + proposal | Shell-backed corrections fail-closed | `python scripts/cli.py propose-overrides --name <brand> --input overrides.json --accept` |
| **refine** | User feedback delta | Comprehension overlaid for future generations | `python scripts/cli.py refine --name <brand> --input refinement.json --accept` |

### Hard Rules for Brand Decks
1. `scripts/cli.py` (or `scripts/brand_cli.py`) is the launcher. It automatically resolves the engine root.
2. Run preflight (`python scripts/cli.py doctor`) before extraction or generation to verify system readiness.
3. **Extract** opens the template read-only and saves `brand-kit/<name>/template/shell.pptx` byte-for-byte.
4. **Generate** opens the saved shell and resolves every semantic block through `profile.json`.
5. **Author role-first, not layout-first**: Do not put style names, colors, fonts, or raw geometry in an `IntermediateDocument` (`idoc.json`). Consult `brand-kit/<name>/PROFILE.md` for role vocabulary.
6. See [`references/comprehension.md`](references/comprehension.md) and [`references/visual-audit.md`](references/visual-audit.md) for full details.

---

## 2. Scripts Reference

Paths are relative to this skill's directory. Everything else is plain Python, `node`, or shell.

| Script | What it does |
|---|---|
| `scripts/cli.py` | Brand engine launcher for `doctor`, `extract`, `comprehend`, `verify`, `generate`, `learn`, `refine`. |
| `scripts/thumbnail.py deck.pptx [prefix]` | Labeled grid of every slide, for picking template layouts. `.pptx` only. Pass `prefix` — it defaults to `thumbnails`. |
| `scripts/add_slide.py unpacked/ slide2.xml [--after slideN.xml]` | Duplicate a slide (or a `slideLayoutN.xml`) with package bookkeeping. Also takes a `.pptx` directly with `-o out.pptx`. |
| `scripts/clean.py unpacked/` | Delete slides, media, and rels no longer referenced. Run **after** `<p:sldIdLst>` is final. |
| `scripts/office/validate.py deck.pptx [--original src.pptx]` | Schema, relationship, content-type, chart, and slide checks. Pass `--original` for template-derived decks to baseline. |
| `scripts/office/soffice.py --headless --convert-to pdf deck.pptx` | Headless LibreOffice wrapper for PDF generation and visual QA. |

---

## 3. Creating with pptxgenjs — Gotchas & Rules

`pptxgenjs` is preinstalled — write the script and `require('pptxgenjs')` directly. Only if that require fails: `npm install pptxgenjs`.

- **Set `pres.layout` before adding slides.** The default canvas is `LAYOUT_16x9` = **10" × 5.625"**, not 13.3" wide. (`LAYOUT_WIDE` is 13.3" × 7.5".)
- **Hex colors: never `#`, never 8 digits.** `color: "FF0000"`. Both `"#FF0000"` and alpha baked into hex (`"00000020"`) **corrupt the file**. For translucency: `transparency: 0-100` on fills and images, `opacity: 0.0-1.0` on shadows.
- **pptxgenjs mutates option objects in place** (converts values to EMU on first use). Never share one options object across two calls.
- **Shadow `offset` must be ≥ 0** — negative offset corrupts the file.
- **`letterSpacing` is silently ignored** — use `charSpacing`.
- **Lists:** `bullet: true` on each item, never a literal `•`. Space bulleted paragraphs with `paraSpaceAfter`, not `lineSpacing`.
- **One `new pptxgen()` per output file** — never reuse an instance.
- **`rectRadius` only works on `ROUNDED_RECTANGLE`**, not `RECTANGLE`.
- **Text boxes have built-in internal padding** — set `margin: 0` whenever text must align with a shape or line.
- **Speaker notes go in `slide.addNotes("...")`** (plain text, once per slide).
- **Keep charts native.** Use `addChart()` with `{type, data, options}`. On a stacked bar/column chart, `dataLabelPosition` must be `ctr`, `inEnd`, or `inBase` (`outEnd` corrupts the file).
- **A combo series using `secondaryValAxis`/`secondaryCatAxis` needs both `valAxes` and `catAxes` on the chart options, two entries each.**
- **After `writeFile()`, run `python scripts/office/validate.py deck.pptx`.**

---

## 4. Editing Existing Decks & Templates

Pick layouts first:
```bash
python scripts/thumbnail.py template.pptx template-thumbs
```

Perform slide surgery:
```bash
python3 -c "import sys,zipfile; zipfile.ZipFile(sys.argv[1]).extractall('unpacked')" deck.pptx
python scripts/add_slide.py unpacked/ slide2.xml --after slide2.xml   # duplicate slide
# edit slide content in ppt/slides/slideN.xml
python scripts/clean.py unpacked/                                     # clean orphaned media/rels
(cd unpacked && rm -f ../out.pptx && zip -Xr ../out.pptx .)
python scripts/office/validate.py out.pptx --original deck.pptx
```

---

## 5. Visual QA & Verification

```bash
# 1. Content check
markitdown output.pptx

# 2. Check for leftover placeholder text
markitdown output.pptx | grep -iE "\bx{3,}\b|lorem|ipsum|\bTODO|\[insert|this.*(page|slide).*layout"

# 3. Schema & integrity validation
python scripts/office/validate.py output.pptx

# 4. Render to images for visual review
python scripts/office/soffice.py --headless --convert-to pdf output.pptx
rm -f slide-*.jpg
pdftoppm -jpeg -r 150 output.pdf slide
ls -1 "$PWD"/slide-*.jpg
```

## Dependencies

`pptxgenjs` (npm) · `python-pptx` · `openpyxl` · `markitdown[pptx]` · `Pillow` · `defusedxml` · `lxml` · LibreOffice (`soffice`) · `pdftoppm` (Poppler)
