#!/usr/bin/env python3
"""Extract a reviewable DOCX template contract as Markdown.

The report records observed Word settings and turns them into conservative rules.
It never invents missing template requirements.
"""
from __future__ import annotations

import argparse
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}

def q(name: str) -> str:
    return f"{{{W}}}{name}"

def val(node: ET.Element | None, name: str, default: str = "") -> str:
    return node.attrib.get(q(name), default) if node is not None else default

def txt(node: ET.Element) -> str:
    return "".join(node.itertext()).strip()

def cm(twips: str) -> float | None:
    try:
        return round(float(twips) / 567.0, 2)
    except (TypeError, ValueError):
        return None

def style_summary(style: ET.Element) -> dict[str, Any]:
    rpr = style.find(q("rPr"))
    ppr = style.find(q("pPr"))
    fonts = rpr.find(q("rFonts")) if rpr is not None else None
    size = rpr.find(q("sz")) if rpr is not None else None
    spacing = ppr.find(q("spacing")) if ppr is not None else None
    ind = ppr.find(q("ind")) if ppr is not None else None
    tabs = ppr.find(q("tabs")) if ppr is not None else None
    tab_values = []
    if tabs is not None:
        for tab in tabs.findall(q("tab")):
            tab_values.append({"val": val(tab, "val"), "pos_twips": val(tab, "pos")})
    return {
        "name": val(style.find(q("name")), "val", val(style, "styleId")),
        "style_id": val(style, "styleId"),
        "type": val(style, "type"),
        "based_on": val(style.find(q("basedOn")), "val"),
        "font": val(fonts, "ascii") or val(fonts, "hAnsi") or val(fonts, "eastAsia"),
        "size_pt": round(int(val(size, "val")) / 2, 1) if val(size, "val").isdigit() else None,
        "bold": rpr is not None and rpr.find(q("b")) is not None,
        "italic": rpr is not None and rpr.find(q("i")) is not None,
        "line_twips": val(spacing, "line"),
        "line_rule": val(spacing, "lineRule"),
        "before_twips": val(spacing, "before"),
        "after_twips": val(spacing, "after"),
        "left_twips": val(ind, "left"),
        "right_twips": val(ind, "right"),
        "first_line_twips": val(ind, "firstLine"),
        "tabs": tab_values,
    }

def extract(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        parts: dict[str, ET.Element] = {}
        for name in names:
            if name.endswith(".xml"):
                try:
                    parts[name] = ET.fromstring(zf.read(name))
                except ET.ParseError:
                    continue

    doc = parts.get("word/document.xml")
    if doc is None:
        raise ValueError("word/document.xml not found")
    styles = parts.get("word/styles.xml")
    settings = parts.get("word/settings.xml")
    sections = []
    for sect in doc.findall(f".//{q('sectPr')}"):
        mar = sect.find(q("pgMar")); size = sect.find(q("pgSz")); cols = sect.find(q("cols"))
        sections.append({
            "paper_width_cm": cm(val(size, "w")), "paper_height_cm": cm(val(size, "h")),
            "orientation": val(size, "orient", "portrait"),
            "top_cm": cm(val(mar, "top")), "bottom_cm": cm(val(mar, "bottom")),
            "left_cm": cm(val(mar, "left")), "right_cm": cm(val(mar, "right")),
            "columns": int(val(cols, "num", "1") or 1),
        })

    style_rows = []
    if styles is not None:
        style_rows = [style_summary(s) for s in styles.findall(q("style"))]
    heading_rows = [s for s in style_rows if s["style_id"].lower().startswith("heading") or s["name"].lower().startswith("heading")]
    caption_rows = [s for s in style_rows if "caption" in s["name"].lower() or "caption" in s["style_id"].lower()]

    paragraphs = doc.findall(f".//{q('p')}")
    paragraph_styles = {}
    plain_captions = []
    native_caption_fields = []
    for p in paragraphs:
        pstyle = p.find(f"./{q('pPr')}/{q('pStyle')}")
        style_id = val(pstyle, "val")
        paragraph_styles[style_id or "Normal"] = paragraph_styles.get(style_id or "Normal", 0) + 1
        text = txt(p)
        if re.match(r"^(?:Table|Tabel|Figure|Gambar|Fig\.)\s+\d", text, re.I):
            field_texts = [n.text or "" for n in p.findall(f".//{q('instrText')}")]
            field_texts.extend(val(n, "instr") for n in p.findall(f".//{q('fldSimple')}"))
            if any(re.search(r"\bSEQ\s+(?:Table|Tabel|Figure|Gambar)\b", field, re.I) for field in field_texts):
                native_caption_fields.append(text)
            else:
                plain_captions.append(text)
    numbering_rows = []
    numbering = parts.get("word/numbering.xml")
    if numbering is not None:
        for abstract in numbering.findall(q("abstractNum")):
            levels = []
            for lvl in abstract.findall(q("lvl")):
                levels.append({"ilvl": val(lvl, "ilvl"), "format": val(lvl.find(q("numFmt")), "val"), "text": val(lvl.find(q("lvlText")), "val"), "p_style": val(lvl.find(q("pStyle")), "val")})
            numbering_rows.append({"abstract_id": val(abstract, "abstractNumId"), "levels": levels})

    header_parts = [n for n in names if n.startswith("word/header") and n.endswith(".xml")]
    footer_parts = [n for n in names if n.startswith("word/footer") and n.endswith(".xml")]
    header_footer_text = {
        n: txt(parts[n])[:500]
        for n in header_parts + footer_parts
        if n in parts and txt(parts[n])
    }
    image_parts = [n for n in names if n.startswith("word/media/")]
    tables = doc.findall(f".//{q('tbl')}")
    fields = " ".join((el.text or "") for el in doc.findall(f".//{q('instrText')}"))
    return {
        "template": path.name,
        "parts": names,
        "sections": sections,
        "styles": style_rows,
        "headings": heading_rows,
        "captions": caption_rows,
        "paragraph_styles": paragraph_styles,
        "numbering": numbering_rows,
        "tables": len(tables),
        "images": len(image_parts),
        "headers": header_parts,
        "footers": footer_parts,
        "header_footer_text": header_footer_text,
        "has_toc": bool(re.search(r"\bTOC\b", fields, re.I)),
        "has_table_of_figures": bool(re.search(r"\bTOC.*\\c\s+\"?(?:Table|Tabel|Figure|Gambar)", fields, re.I)),
        "has_track_revisions": settings is not None and settings.find(q("trackRevisions")) is not None,
        "native_caption_fields": native_caption_fields,
        "plain_captions": plain_captions,
    }

def render(data: dict[str, Any]) -> str:
    first = data["sections"][0] if data["sections"] else {}
    lines = [f"# Template rules: `{data['template']}`", "", "This contract was extracted from every readable XML part in the Word package. Observed values are facts; operational rules below are conservative safeguards.", "", "## Observed template contract", "", f"- Package parts inspected: {len(data['parts'])}", f"- Sections: {len(data['sections'])}", f"- Tables: {data['tables']}", f"- Images: {data['images']}", f"- Headers: {len(data['headers'])}", f"- Footers: {len(data['footers'])}", f"- Automatic TOC field: {'yes' if data['has_toc'] else 'not detected'}", f"- Automatic table/figure list field: {'yes' if data['has_table_of_figures'] else 'not detected'}", f"- Track revisions setting: {'enabled' if data['has_track_revisions'] else 'not enabled'}"]
    if first:
        lines += ["", "### Page setup", "", f"- Paper: {first.get('paper_width_cm')} x {first.get('paper_height_cm')} cm ({first.get('orientation')})", f"- Margins: top {first.get('top_cm')} cm, bottom {first.get('bottom_cm')} cm, left {first.get('left_cm')} cm, right {first.get('right_cm')} cm", f"- Columns: {first.get('columns')}"]
    lines += ["", "### Styles", "", "| Style | Type | Font | Size | Line spacing | Before | After | Tabs |", "|---|---|---|---:|---:|---:|---:|---|"]
    for s in data["styles"]:
        line = s["line_twips"] or "auto"
        lines.append(f"| {s['name']} | {s['type']} | {s['font'] or 'inherited'} | {s['size_pt'] or 'inherited'} | {line} | {s['before_twips'] or 0} | {s['after_twips'] or 0} | {len(s['tabs'])} |")
    lines += ["", "### Heading styles", "", ", ".join(s["name"] for s in data["headings"]) or "No Heading styles detected.", "", "### Numbering definitions", ""]
    lines += ["", "### Paragraph style usage", ""]
    lines.extend(f"- `{name}`: {count} paragraph(s)" for name, count in sorted(data["paragraph_styles"].items()))
    if data["header_footer_text"]:
        lines += ["", "### Header and footer content", ""]
        lines.extend(f"- `{name}`: {content}" for name, content in data["header_footer_text"].items())
    if data["numbering"]:
        for n in data["numbering"]:
            levels = "; ".join(f"{x['ilvl']}: {x['format']} {x['text']}" for x in n["levels"])
            lines.append(f"- abstractNum {n['abstract_id']}: {levels}")
    else:
        lines.append("No numbering definitions detected.")
    lines += ["", "## Allowed", "", "- Use the observed page size, margins, columns, styles, heading hierarchy, numbering definitions, tabs, headers, and footers from this report.", "- Add body content through paragraph styles already present in the template.", "- Use Word Heading styles for sections so the Navigation Pane and TOC remain functional.", "- Use Word's References → Insert Caption feature for every table and figure caption.", "- Keep tables inside the printable width reported above; split or rotate only when the template already demonstrates that pattern.", "- Use Word's automatic TOC, Table of Figures, cross-reference, and page-number fields when the template contains those fields.", "", "## Not allowed", "", "- Do not invent fonts, margins, spacing, tabs, numbering formats, colors, or heading sizes that are absent from the observed contract.", "- Do not replace Heading styles with manual bold, manual numbering, or blank paragraphs used as spacing.", "- Do not type table or figure captions as plain text when a Word caption field is required.", "- Do not place tables, images, captions, or text outside the printable page area.", "- Do not flatten fields, tracked changes, headers, footers, or template styles into static text.", "- Do not return a modified document before running schema validation, layout audit, and a rendered visual check.", ""]
    if data["plain_captions"]:
        lines += ["## Existing template warning", "", "The template contains caption-like paragraphs without a detected Word SEQ field. Preserve them as-is during extraction, but confirm with the user whether they are intentional before generating new captions.", ""]
    return "\n".join(lines)

def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Word template rules to Markdown")
    parser.add_argument("template", type=Path, help=".docx or .dotx template")
    parser.add_argument("-o", "--output", type=Path, help="Markdown output path")
    args = parser.parse_args()
    if not args.template.exists():
        parser.error(f"template not found: {args.template}")
    output = args.output or args.template.with_name(f"{args.template.stem}-rules.md")
    output.write_text(render(extract(args.template)), encoding="utf-8")
    print(f"Template rules saved to: {output}")

if __name__ == "__main__":
    main()
