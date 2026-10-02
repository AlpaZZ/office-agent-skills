# Office Agent Skills Suite 📑🚀

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://www.python.org/)
[![Compatible: Antigravity / Claude Code / Codex](https://img.shields.io/badge/AI%20Agents-Antigravity%20%7C%20Claude%20Code%20%7C%20Codex-orange.svg)](#installation)

An enterprise-grade, multi-format Office automation suite designed specifically for AI agents (**Antigravity**, **Claude Code**, **Codex**, **Cursor**).

Combines **strict corporate brand governance**, **native academic publishing with LaTeX equations & live Zotero integration**, **data science reporting**, **editorial layout creation**, and **legal redlining (Tracked Changes)** across Microsoft Word (`.docx`), PowerPoint (`.pptx`), and Excel (`.xlsx`).

---

## 🏛️ System Architecture: The 5 Execution Pathways

```
                                  USER REQUEST / TASK
                                           │
         ┌─────────────────────────────────┼─────────────────────────────────┐
         ▼                                 ▼                                 ▼
   [PATHWAY 1: ON-BRAND]         [PATHWAY 2: ACADEMIC]             [PATHWAY 3: DATA BRIDGE]
Company template present        LaTeX math ($$, \frac),           DataFrames, CSV, XLSX,
(.dotx, .potx, .xltx, brandkit) scientific papers, citations      analytics tables
         │                                 │                                 │
         ▼                                 ▼                                 ▼
    brand-docs                        Pandoc                            python-docx
 (scripts/brandkit/)        (scripts/pandoc/compile_academic)     (scripts/data/dataframe_to_word)
         │                                 │                                 │
         └─────────────────────────────────┼─────────────────────────────────┘
                                           │
         ┌─────────────────────────────────┴─────────────────────────────────┐
         ▼                                                                   ▼
   [PATHWAY 4: EDITORIAL]                                            [PATHWAY 5: LEGAL & ZOTERO]
New documents from scratch,                                       Existing Word document,
custom covers, modern layouts, TOC                                Track Changes (<w:ins>/<w:del>),
         │                                                        live Zotero CSL field codes
         ▼                                                                   │
     docx-js                                                                 ▼
 (Node.js engine)                                                        Raw OpenXML
                                                                  (scripts/zotero/ + merge_runs.py)
```

---

## 📦 What's Included

| Skill Name | Supported Formats | Primary Superpower |
| :--- | :--- | :--- |
| **[`docx`](skills/docx/)** | `.docx`, `.dotx` | **Master Word Suite**: Pandoc LaTeX math, live Zotero CSL fields, python-docx data tables, docx-js editorial design, and legal redlining. |
| **[`brand-docx`](skills/brand-docx/)** | `.docx`, `.dotx` | **Corporate Word Guardian**: Extracts brand profiles (fonts, colors, logos) from company templates with fail-closed enforcement. |
| **[`brand-pptx`](skills/brand-pptx/)** | `.pptx`, `.potx` | **Corporate PowerPoint**: Generates slides adhering strictly to company master layouts and native chart styling. |
| **[`brand-xlsx`](skills/brand-xlsx/)** | `.xlsx`, `.xltx` | **Corporate Excel**: Fills branded financial sheets while preserving formulas, cell extensions, and number formats. |
| **[`pptx`](skills/pptx/)** | `.pptx`, `.potx` | **Presentation Engine**: Full slide deck authoring via pptxgenjs, layout thumbnailing, and native chart corrupt-proofing. |
| **[`xlsx`](skills/xlsx/)** | `.xlsx`, `.xlsm`, `.csv` | **Spreadsheet Engine**: Complex formula writing with background recalculation (`recalc.py`) guaranteeing zero `#REF!` errors. |

---

## ⚡ Key Highlights

### 1. 🎓 Academic Papers with LaTeX Math & Live Zotero Integration
* **LaTeX $\rightarrow$ Native Word OMML**: Converts `$E=mc^2$` and `$$\mathcal{L} = -\sum y \log(\hat{y})$$` directly to editable Microsoft Word Equation objects (never low-res images).
* **Live Zotero CSL Field Codes**: Injects genuine `<w:fldChar>` + `ADDIN ZOTERO_ITEM CSL_CITATION` XML payloads. The author simply clicks **Zotero $\rightarrow$ Refresh** in the Word Ribbon to re-index all numbers and bibliography.
* **Auto-Sync via Better BibTeX**: Automatically reads project `references.bib` files and resolves citations via Pandoc citeproc.

### 2. 🛡️ Enterprise Brand Governance (*Fail-Closed*)
* Extracts corporate brand tokens into reusable Brand Profiles.
* AI writes brand-agnostic content (`idoc.json`); the deterministic engine injects it into the original template shell.
* Output is on-brand by construction: arbitrary hallucinated fonts or colors are strictly forbidden.

### 3. ⚖️ Legal Redlining & Contract Review
* Supports native Microsoft Word **Tracked Changes** (`<w:ins>`, `<w:del>`) with author metadata and timestamps.
* Cross-linked 6-file comment system (`scripts/comment.py`) anchors comments to exact character spans without breaking OpenXML relationships.

### 4. 📊 Data Science to Document Bridge
* Instantly injects CSV, Excel, or Pandas data into beautiful, zebra-striped, auto-aligned Word tables.

### 5. 🔍 Deterministic & Visual Quality Assurance
* **Schema Validation**: Automated XSD verification via `validate.py`.
* **Formula Proofing**: Mandatory headless formula calculation (`recalc.py`) ensures 0 formula errors.
* **Visual QA Gate**: Headless LibreOffice conversion to PDF followed by Poppler rasterization (`pdftoppm`) checks for layout clipping and table overflows.

---

## 🚀 Installation & Quick Start

### Prerequisites
* **Python**: 3.10 to 3.13
* **Node.js**: (Optional, for docx-js and pptxgenjs)

Install Python dependencies:
```bash
pip install -r requirements.txt
```

### Installation for Antigravity

Clone or copy the skills into your Antigravity skills directory:

```bash
# Clone the repository
git clone https://github.com/AlpaZZ/office-agent-skills.git

# Copy to Workspace skills (.agents/skills)
mkdir -p .agents/skills
cp -r office-agent-skills/skills/* .agents/skills/

# Or install globally for Antigravity IDE:
# Windows: %USERPROFILE%\.gemini\antigravity\skills\
# Linux/macOS: ~/.gemini/antigravity/skills/
```

### Installation for Claude Code

```bash
# Symlink or copy to ~/.claude/skills
for s in docx brand-docx brand-pptx brand-xlsx pptx xlsx; do
  ln -s $(pwd)/skills/$s ~/.claude/skills/$s
done
```

---

## 🛠️ CLI Quick Reference

```bash
# 1. Compile Markdown + LaTeX Math + Citations to Word (.docx)
python skills/docx/scripts/pandoc/compile_academic.py paper.md -o paper.docx \
  --bibliography references.bib --csl ieee.csl

# 2. Inspect active Zotero citations in a manuscript
python skills/docx/scripts/zotero/inspect_zotero.py manuscript.docx

# 3. Inject a new native Zotero citation
python skills/docx/scripts/zotero/inject_zotero.py manuscript.docx \
  --after "ConvNeXtV2" --citation-text "[40]" \
  --title "ConvNeXt V2: Co-designing and Scaling ConvNets with Masked Autoencoders" \
  --authors "Woo, Sanghyun; Debnath, Shoubhik" --year 2023 --venue "CVPR" \
  -o updated_manuscript.docx

# 4. Inject DataFrame / CSV to a styled Word table
python skills/docx/scripts/data/dataframe_to_word.py results.csv -o report.docx \
  --title "Tabel 1: Ringkasan Hasil Eksperimen"

# 5. Extract a Corporate Brand Profile from a Word template
python skills/brand-docx/scripts/cli.py extract --name my_company --template template.dotx

# 6. Recalculate and verify Excel formulas
python skills/xlsx/scripts/recalc.py financial_model.xlsx
```

---

## 📄 License

Distributed under the [MIT License](LICENSE).
Copyright (c) 2026 AlpaZZ.
