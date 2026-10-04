---
name: xlsx
description: "Comprehensive Excel spreadsheet (.xlsx/.xltx/.xlsm) engine. Covers: (1) On-brand corporate workbook generation & template extraction via the Brand Engine (extract, comprehend, verify, generate from .xlsx/.xltx templates and GridDocuments), (2) Programmatic spreadsheet creation and editing via openpyxl, (3) Mandatory headless formula calculation & zero-error verification via scripts/recalc.py, (4) Bulk data processing via pandas, and (5) Financial modeling conventions. Trigger on any mention of spreadsheets, Excel, workbooks, .xlsx, .xlsm, .xltx, financial models, sheet formulas, or Excel template brand enforcement."
license: MIT
---

# Unified XLSX Creation, Editing, Brand & Analysis Suite

Choose your approach based on task requirements:

| Task / Domain | Engine / Approach | When to Choose |
|---|---|---|
| **On-Brand Corporate Workbook** | `scripts/brandkit/` (`scripts/cli.py`) | Extracting reusable Brand Profiles from company `.xlsx`/`.xltx` templates and generating on-brand workbooks fail-closed from GridDocuments. |
| **Create or Edit Models** | `openpyxl` + `scripts/recalc.py` | Building dynamic financial models, budgets, and automated workbooks with live Excel formulas and formatting. |
| **Formula Recalculation** | `scripts/recalc.py output.xlsx` | Mandatory verification computing formula caches via headless LibreOffice and ensuring zero `#NAME?` or `#VALUE!` errors. |
| **Bulk Data In / Out** | `pandas` (`read_excel`, `to_excel`) | Importing/exporting large datasets or performing tabular transformations. |
| **Quick Sheet Inspection** | `markitdown file.xlsx` | Markdown inspection of sheet tabs and high-level contents. |

---

## 1. On-Brand Corporate Workbook Governance (Brand Engine)

Use this pathway when the user provides or references a company workbook template (`.xlsx` / `.xltx`) or asks to "fill this template", "use our workbook brand kit", or generate an on-brand spreadsheet from structured data.

### The Seven Verbs
The engine implements three deterministic core verbs plus four model-assisted learning verbs:

| Verb | Input | Output | CLI Command |
|---|---|---|---|
| **extract** | A company `.xlsx` or `.xltx` template | A reusable Brand Profile (`brand-kit/<name>/`) | `python scripts/cli.py extract --name <brand> --template <template.xlsx>` |
| **comprehend** *(optional)* | Saved profile + model-authored `comprehension.json` | Profile with validated, cached `comprehension` block | `python scripts/cli.py comprehend --name <brand> --input comprehension.json` |
| **verify** | Saved Brand Profile | QA findings + deterministic verdict | `python scripts/cli.py verify --name <brand>` |
| **generate** | Data (`GridDocument`) + profile | New on-brand `.xlsx` | `python scripts/cli.py generate --name <brand> --input grid.json -o out.xlsx` |
| **learn** | Profile's cross-run history | Recurring findings distilled to shell-frozen overrides | `python scripts/cli.py learn --name <brand> --accept` |
| **propose-overrides** | Residual issues + proposal | Shell-backed corrections fail-closed | `python scripts/cli.py propose-overrides --name <brand> --input overrides.json --accept` |
| **refine** | User feedback delta | Comprehension overlaid for future generations | `python scripts/cli.py refine --name <brand> --input refinement.json --accept` |

### Hard Rules for Brand Workbooks
1. `scripts/cli.py` (or `scripts/brand_cli.py`) is the launcher. It automatically resolves the engine root.
2. Run preflight (`python scripts/cli.py doctor`) before extraction or generation to verify system readiness.
3. **Extract** opens the template read-only and saves `brand-kit/<name>/template/shell.xlsx` byte-for-byte.
4. **Generate** opens the saved shell and resolves every named cell/region through `profile.json`.
5. **Author role-first, not style-first**: Do not put font names, pt sizes, hex colors, or raw style names in a `GridDocument`.
6. See [`references/comprehension.md`](references/comprehension.md) and [`references/visual-audit.md`](references/visual-audit.md) for full details.

---

## 2. Requirements for Every Output Workbook

- **Professional font** (Arial, Times New Roman, Calibri) throughout, unless specified otherwise.
- **Zero formula errors.** Never ship while `recalc.py` reports `errors_found`.
- **Use formulas, never hardcoded results.** Write `sheet['B10'] = '=SUM(B2:B9)'`, not the Python-computed total.
- **Follow the user's spec literally.** Exact tab names, exact column headers, and the formula they spelled out.
- **Document every assumption and hardcoded number** in a cell comment or adjacent cell.
- **A workbook created for someone to fill in** needs a short legend naming which cells to edit, and one example row.
- **Editing an existing file: match its conventions exactly.** Leave every existing formula untouched.

---

## 3. Mandatory Recalculation (`recalc.py`)

openpyxl writes formulas as strings with **no cached values**. Until you recalculate, every formula cell reads back as `None` to external readers.

```bash
python scripts/recalc.py output.xlsx [timeout_seconds]   # default 30
```

LibreOffice computes every formula, the file is **rewritten in place**, and you get JSON:
`status` (`success` | `errors_found`), `total_formulas`, `total_errors`, and an `error_summary`. Fix what it names and run again.

---

## 4. Choosing Formulas That Survive Verification

LibreOffice implements fewer functions than Excel. Functions it cannot evaluate become literal `#NAME?`:

- **Prefer Excel-2007-era functions**: `SUMIFS`, `INDEX`, `MATCH`, `IFERROR`, `SUMPRODUCT` (require no prefix).
- **Post-2007 functions require `_xlfn.` prefix**: `_xlfn.TEXTJOIN`, `_xlfn.CONCAT`, `_xlfn.IFS`, `_xlfn.SWITCH`, `_xlfn.MAXIFS`, `_xlfn.MINIFS`. Written bare, each yields `#NAME?`.
- **Never use `XLOOKUP`, `XMATCH`, `SORT`, `FILTER`, `UNIQUE`, or `SEQUENCE`**: The headless LibreOffice runtime cannot evaluate them properly. Use `INDEX`/`MATCH` instead.

---

## 5. openpyxl Gotchas

- **Reading a model takes two loads**: `data_only=True` yields cached values (formulas stripped); default yields formula strings with no values.
- **`data_only=True` is destructive on save**: Saving after `data_only=True` permanently replaces formulas with static numbers.
- **Merged cells**: Write the top-left anchor only. Sibling cells are read-only `MergedCell`.
- **`.xlsm` macros**: Always pass `keep_vba=True` to `load_workbook`.
- **Sheet names with spaces**: Must be quoted in formulas: `='Assumptions Inputs'!$B$5`.

---

## 6. Financial Model Conventions

- **Colors**: Blue text (`0,0,255`) for inputs · black for formulas · green (`0,128,0`) for cross-sheet links · red (`255,0,0`) for external file links · yellow fill (`255,255,0`) for user inputs.
- **Numbers**: Currency `$#,##0`, unit named in header (`Revenue ($mm)`) · zeros as `-` (`$#,##0;($#,##0);-`) · negatives in parentheses · percentages `0.0%` stored as fractions (`0.15` renders `15.0%`).
- **Structure**: Every assumption in its own labeled cell (`=B5*(1+$B$6)`). Guard denominators against division by zero (`IF(B6=0, 0, B5/B6)`).

## Dependencies

`openpyxl` · `pandas` · `markitdown` · `lxml` · `Pillow` · LibreOffice (`soffice`, auto-configured via `scripts/office/soffice.py`)
