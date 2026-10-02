#!/usr/bin/env python3
"""Inject tabular data (CSV / Excel / JSON) into a Word (.docx) document using python-docx.

Applies professional typography, header shading, zebra striping, and column auto-width.

Usage:
    # Append to existing document or create a new one:
    python dataframe_to_word.py data.csv -o report.docx --title "Ringkasan Hasil Evaluasi"
    python dataframe_to_word.py data.xlsx --sheet "Results" -o existing.docx --append
"""

import argparse
import csv
import json
import sys
from pathlib import Path

try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
    from docx.oxml import OxmlElement, parse_xml
    from docx.oxml.ns import nsdecls, qn
except ImportError:
    print("Error: python-docx is not installed. Please install python-docx.", file=sys.stderr)
    sys.exit(1)


def set_cell_shading(cell, color_hex: str):
    shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    cell._tc.get_or_add_tcPr().append(shading_elm)


def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def load_data(file_path: Path, sheet_name: str | None = None):
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        with open(file_path, "r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)
            if not rows:
                return [], []
            return rows[0], rows[1:]
    elif suffix in (".xlsx", ".xls"):
        import openpyxl
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active
        all_rows = list(ws.iter_rows(values_only=True))
        if not all_rows:
            return [], []
        headers = [str(c or "") for c in all_rows[0]]
        data = [[str(c if c is not None else "") for c in row] for row in all_rows[1:]]
        return headers, data
    elif suffix == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            items = json.load(f)
        if isinstance(items, list) and items and isinstance(items[0], dict):
            headers = list(items[0].keys())
            data = [[str(item.get(h, "")) for h in headers] for item in items]
            return headers, data
        elif isinstance(items, dict) and "headers" in items and "rows" in items:
            return items["headers"], items["rows"]
    raise ValueError(f"Unsupported file format: {suffix}")


def insert_styled_table(doc: Document, headers: list, rows: list, header_bg="1E2761", zebra_bg="F8F9FA"):
    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER

    # Format Header Row
    hdr_cells = table.rows[0].cells
    for i, title in enumerate(headers):
        hdr_cells[i].text = title
        set_cell_shading(hdr_cells[i], header_bg)
        set_cell_margins(hdr_cells[i], top=120, bottom=120, left=150, right=150)
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in p.runs:
            run.font.bold = True
            run.font.color.rgb = RGBColor(255, 255, 255)
            run.font.size = Pt(10)
            run.font.name = "Arial"

    # Format Data Rows
    for r_idx, row_data in enumerate(rows):
        row_cells = table.rows[r_idx + 1].cells
        bg_color = zebra_bg if r_idx % 2 == 1 else "FFFFFF"
        for c_idx, val in enumerate(row_data):
            row_cells[c_idx].text = str(val)
            if bg_color != "FFFFFF":
                set_cell_shading(row_cells[c_idx], bg_color)
            set_cell_margins(row_cells[c_idx], top=80, bottom=80, left=120, right=120)
            p = row_cells[c_idx].paragraphs[0]
            # Detect numbers for right-alignment
            val_str = str(val).strip().replace(",", "").replace("%", "")
            try:
                float(val_str)
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            except ValueError:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            for run in p.runs:
                run.font.size = Pt(9.5)
                run.font.name = "Arial"

    # Add spacing after table
    doc.add_paragraph()
    return table


def main():
    parser = argparse.ArgumentParser(description="Insert structured tabular data into Word document")
    parser.add_argument("data_file", type=Path, help="CSV, XLSX, or JSON data file")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output .docx file")
    parser.add_argument("--title", type=str, help="Optional table title / heading")
    parser.add_argument("--sheet", type=str, help="Sheet name for Excel input")
    parser.add_argument("--append", action="store_true", help="Append to existing output document")
    parser.add_argument("--header-color", type=str, default="1E2761", help="Header background hex color (default: 1E2761)")
    parser.add_argument("--zebra-color", type=str, default="F8F9FA", help="Zebra background hex color (default: F8F9FA)")

    args = parser.parse_args()

    if not args.data_file.exists():
        print(f"Error: {args.data_file} not found", file=sys.stderr)
        sys.exit(1)

    headers, rows = load_data(args.data_file, sheet_name=args.sheet)
    if not headers:
        print("Warning: No tabular data found in input file.", file=sys.stderr)
        sys.exit(1)

    if args.append and args.output.exists():
        doc = Document(args.output)
    else:
        doc = Document()

    if args.title:
        h = doc.add_heading(args.title, level=2)
        h.paragraph_format.space_before = Pt(12)
        h.paragraph_format.space_after = Pt(6)

    insert_styled_table(doc, headers, rows, header_bg=args.header_color, zebra_bg=args.zebra_color)
    doc.save(args.output)
    print(f"[+] Successfully wrote {len(rows)} rows x {len(headers)} columns into {args.output}")


if __name__ == "__main__":
    main()
