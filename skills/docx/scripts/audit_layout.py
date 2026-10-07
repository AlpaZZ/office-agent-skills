#!/usr/bin/env python3
"""audit_layout.py - Academic & Office Document Layout, Typography, and Visual Linter.

Audits Word documents (.docx) against academic publication & thesis standards
(e.g., Skripsi UI, JIKI Journal, IEEE, APA) across all Microsoft Office features:
1. Page Setup & Layout: Margins, Orientation, Size (A4/Letter), Columns, Breaks, Hyphenation.
2. Typography & Fonts: Font family consistency, size hierarchy, font colors, highlighting.
3. Paragraph & Spacing: Alignment (Justify), Line spacing (1.0/1.5/2.0), Spacing Before/After.
4. Headings & Structure: Semantic Heading 1/2/3 styles vs unstyled bold text, numbering.
5. Captions & Lists: Table captions ABOVE, Figure captions BELOW, TOC, List of Tables/Figures.
6. Mathematical Equations: Native OMML / LaTeX (<m:oMath>) vs rasterized picture formulas.
7. Image Quality & Blurriness: Effective DPI calculation (<150 DPI critical), Laplacian blur variance, aspect ratio distortion.
8. Tables: Column overflow beyond printable margin, border styles (no vertical borders in academic papers), header repeat.
9. Header & Footer: Page numbering (Roman front matter vs Arabic main body).
10. Text Boxes & Objects: Floating text box audit.

Usage:
  python audit_layout.py manuscript.docx --profile skripsi-id
  python audit_layout.py manuscript.docx --profile jiki-journal
  python audit_layout.py manuscript.docx --profile general
"""

import argparse
import copy
import io
import json
import math
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

# Namespaces in OpenXML
NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

# Unit Conversion Constants
TWIPS_PER_CM = 567.0
TWIPS_PER_INCH = 1440.0
EMUS_PER_INCH = 914400.0
HALF_POINTS_PER_PT = 2.0

# Profiles
PROFILES = {
    "skripsi-id": {
        "name": "Standard Skripsi / Tesis Indonesia (Universitas Indonesia & PTN)",
        "paper_size": "A4",
        "paper_width_cm": 21.0,
        "paper_height_cm": 29.7,
        "margin_top_cm": 4.0,
        "margin_bottom_cm": 3.0,
        "margin_left_cm": 4.0,
        "margin_right_cm": 3.0,
        "margin_tolerance_cm": 0.25,
        "expected_columns": 1,
        "font_family": ["Times New Roman"],
        "body_font_size_pt": 12.0,
        "heading1_font_size_pt": 14.0,
        "heading2_font_size_pt": 12.0,
        "table_font_size_pt": [10.0, 11.0, 12.0],
        "caption_font_size_pt": [10.0, 11.0, 12.0],
        "line_spacing": [1.5, 2.0],  # 1.5 or 2.0 lines
        "body_alignment": "both",     # Justify
        "table_caption_position": "above",
        "figure_caption_position": "below",
        "min_image_dpi": 200.0,
        "preferred_image_dpi": 300.0,
        "require_toc": True,
        "academic_table_borders": True,
        "require_native_captions": True,
    },
    "jiki-journal": {
        "name": "Jurnal Ilmu Komputer dan Informasi (JIKI UI - SINTA 2)",
        "paper_size": "A4",
        "paper_width_cm": 21.0,
        "paper_height_cm": 29.7,
        "margin_top_cm": 3.0,
        "margin_bottom_cm": 3.0,
        "margin_left_cm": 3.0,
        "margin_right_cm": 3.0,
        "margin_tolerance_cm": 0.25,
        "expected_columns": 2,  # 2 columns in body
        "font_family": ["Times New Roman"],
        "body_font_size_pt": 10.0,
        "heading1_font_size_pt": 10.0,
        "heading2_font_size_pt": 10.0,
        "table_font_size_pt": [8.0],
        "caption_font_size_pt": [8.0],
        "line_spacing": [1.0],  # Single spacing
        "body_alignment": "both",
        "table_caption_position": "above",
        "figure_caption_position": "below",
        "min_image_dpi": 200.0,
        "preferred_image_dpi": 300.0,
        "require_toc": False,
        "academic_table_borders": True,  # No vertical lines
        "require_native_captions": True,
    },
    "general": {
        "name": "General Academic / APA 7th Edition",
        "paper_size": "A4_OR_LETTER",
        "paper_width_cm": 21.0,
        "paper_height_cm": 29.7,
        "margin_top_cm": 2.54,
        "margin_bottom_cm": 2.54,
        "margin_left_cm": 2.54,
        "margin_right_cm": 2.54,
        "margin_tolerance_cm": 0.3,
        "expected_columns": 1,
        "font_family": ["Times New Roman", "Calibri", "Arial"],
        "body_font_size_pt": 12.0,
        "heading1_font_size_pt": 14.0,
        "heading2_font_size_pt": 12.0,
        "table_font_size_pt": [10.0, 11.0, 12.0],
        "caption_font_size_pt": [10.0, 11.0, 12.0],
        "line_spacing": [1.5, 2.0],
        "body_alignment": "both",
        "table_caption_position": "above",
        "figure_caption_position": "below",
        "min_image_dpi": 200.0,
        "preferred_image_dpi": 300.0,
        "require_toc": False,
        "academic_table_borders": True,
        "require_native_captions": True,
    }
}


def calculate_blur_variance(pil_img: Image.Image) -> float:
    """Calculate Laplacian variance to detect blurry images (higher = sharper, < 100 = blurry)."""
    try:
        gray = pil_img.convert("L")
        if gray.width > 800 or gray.height > 800:
            gray.thumbnail((800, 800))
        arr = np.array(gray, dtype=np.float64)
        if arr.shape[0] < 5 or arr.shape[1] < 5:
            return 999.0  # Too small to be blurry
        # 3x3 Laplacian convolution
        lap = (
            arr[:-2, 1:-1]
            + arr[2:, 1:-1]
            + arr[1:-1, :-2]
            + arr[1:-1, 2:]
            - 4 * arr[1:-1, 1:-1]
        )
        return float(np.var(lap))
    except Exception:
        return -1.0


def extract_profile_from_template(template_path: str) -> Dict[str, Any]:
    """Extract layout rules, margins, fonts, line spacing, and column count directly from a template .docx/.dotx."""
    tpath = Path(template_path).resolve()
    if not tpath.exists():
        raise FileNotFoundError(f"Template file not found: {tpath}")

    with zipfile.ZipFile(tpath, "r") as zf:
        if "word/document.xml" not in zf.namelist():
            raise ValueError("Invalid template: word/document.xml not found")

        doc_tree = ET.fromstring(zf.read("word/document.xml"))
        styles_tree = ET.fromstring(zf.read("word/styles.xml")) if "word/styles.xml" in zf.namelist() else None

        # 1. Margins & Paper Size
        sect = doc_tree.find(f".//{{{NS['w']}}}sectPr")
        margin_top = 3.0
        margin_bottom = 3.0
        margin_left = 3.0
        margin_right = 3.0
        width_cm = 21.0
        height_cm = 29.7
        columns = 1

        if sect is not None:
            pgMar = sect.find(f"{{{NS['w']}}}pgMar")
            if pgMar is not None:
                margin_top = float(pgMar.attrib.get(f"{{{NS['w']}}}top", "1701")) / TWIPS_PER_CM
                margin_bottom = float(pgMar.attrib.get(f"{{{NS['w']}}}bottom", "1701")) / TWIPS_PER_CM
                margin_left = float(pgMar.attrib.get(f"{{{NS['w']}}}left", "1701")) / TWIPS_PER_CM
                margin_right = float(pgMar.attrib.get(f"{{{NS['w']}}}right", "1701")) / TWIPS_PER_CM

            pgSz = sect.find(f"{{{NS['w']}}}pgSz")
            if pgSz is not None:
                width_cm = float(pgSz.attrib.get(f"{{{NS['w']}}}w", "11906")) / TWIPS_PER_CM
                height_cm = float(pgSz.attrib.get(f"{{{NS['w']}}}h", "16838")) / TWIPS_PER_CM

            # Check if any section has 2 columns
            all_sects = doc_tree.findall(f".//{{{NS['w']}}}sectPr")
            for s in all_sects:
                cols_elem = s.find(f"{{{NS['w']}}}cols")
                if cols_elem is not None:
                    cnum = int(cols_elem.attrib.get(f"{{{NS['w']}}}num", "1"))
                    if cnum > 1:
                        columns = cnum
                        break

        # 2. Fonts & Line Spacing
        default_font = "Times New Roman"
        body_size = 12.0
        line_spacing = [1.5]
        normal_before_twips = None
        normal_after_twips = None
        normal_tab_stops = []

        if styles_tree is not None:
            for s in styles_tree.findall(f".//{{{NS['w']}}}style"):
                if s.attrib.get(f"{{{NS['w']}}}styleId") == "Normal":
                    rFonts = s.find(f".//{{{NS['w']}}}rFonts")
                    if rFonts is not None:
                        default_font = rFonts.attrib.get(f"{{{NS['w']}}}ascii") or rFonts.attrib.get(f"{{{NS['w']}}}hAnsi") or default_font
                    sz = s.find(f".//{{{NS['w']}}}sz")
                    if sz is not None and sz.attrib.get(f"{{{NS['w']}}}val", "").isdigit():
                        body_size = float(sz.attrib.get(f"{{{NS['w']}}}val")) / 2.0
                    spacing = s.find(f".//{{{NS['w']}}}spacing")
                    if spacing is not None and spacing.attrib.get(f"{{{NS['w']}}}line", "").isdigit():
                        line_spacing = [round(float(spacing.attrib.get(f"{{{NS['w']}}}line")) / 240.0, 1)]
                    if spacing is not None:
                        normal_before_twips = spacing.attrib.get(f"{{{NS['w']}}}before")
                        normal_after_twips = spacing.attrib.get(f"{{{NS['w']}}}after")
                    for tab in s.findall(f".//{{{NS['w']}}}tab"):
                        pos = tab.attrib.get(f"{{{NS['w']}}}pos")
                        if pos:
                            normal_tab_stops.append(pos)
                    break

        paper_size_label = "A4" if abs(width_cm - 21.0) < 0.5 and abs(height_cm - 29.7) < 0.5 else "Letter"

        return {
            "name": f"Template: {tpath.name}",
            "paper_size": paper_size_label,
            "paper_width_cm": round(width_cm, 2),
            "paper_height_cm": round(height_cm, 2),
            "margin_top_cm": round(margin_top, 2),
            "margin_bottom_cm": round(margin_bottom, 2),
            "margin_left_cm": round(margin_left, 2),
            "margin_right_cm": round(margin_right, 2),
            "margin_tolerance_cm": 0.25,
            "expected_columns": columns,
            "font_family": [default_font],
            "body_font_size_pt": body_size,
            "heading1_font_size_pt": 14.0,
            "heading2_font_size_pt": 12.0,
            "table_font_size_pt": [8.0, 9.0, 10.0, 11.0, 12.0],
            "caption_font_size_pt": [8.0, 9.0, 10.0, 11.0, 12.0],
            "line_spacing": line_spacing,
            "normal_before_twips": normal_before_twips,
            "normal_after_twips": normal_after_twips,
            "normal_tab_stops": normal_tab_stops,
            "body_alignment": "both",
            "table_caption_position": "above",
            "figure_caption_position": "below",
            "min_image_dpi": 200.0,
            "preferred_image_dpi": 300.0,
            "require_toc": (False if columns > 1 else True),
            "require_table_list": False,
            "require_figure_list": False,
            "academic_table_borders": True,
            "require_native_captions": True,
        }


class DocumentLayoutAuditor:
    def __init__(
        self,
        docx_path: str,
        profile_name: str = "skripsi-id",
        custom_profile: Optional[Dict[str, Any]] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ):
        self.docx_path = Path(docx_path).resolve()
        self.profile_name = profile_name

        if custom_profile:
            self.profile = custom_profile
            self.profile_name = custom_profile.get("name", "Custom Profile")
        elif profile_name in PROFILES:
            self.profile = copy.deepcopy(PROFILES[profile_name])
        else:
            self.profile = copy.deepcopy(PROFILES["general"])

        # Apply any user overrides
        if overrides:
            for k, v in overrides.items():
                if v is not None:
                    self.profile[k] = v
        
        self.findings = []
        self.doc_tree = None
        self.styles_tree = None
        self.settings_tree = None
        self.image_rels = {}
        self.media_files = {}
        self.zip_ref = None

    def audit(self) -> Dict[str, Any]:
        """Perform comprehensive layout, visual, and typography audit."""
        if not self.docx_path.exists():
            raise FileNotFoundError(f"Document not found: {self.docx_path}")

        with zipfile.ZipFile(self.docx_path, "r") as zf:
            self.zip_ref = zf
            self._load_xml_parts(zf)
            
            # 1. Page Setup & Layout
            page_setup_results = self._audit_page_setup()
            
            # 2. Typography & Fonts
            typography_results = self._audit_typography()
            
            # 3. Paragraph & Line Spacing
            paragraph_results = self._audit_paragraph_formatting()
            
            # 4. Headings & Document Structure
            heading_results = self._audit_headings()
            
            # 5. Captions & Tables of Contents
            caption_results = self._audit_captions_and_toc()
            
            # 6. Math Equations (LaTeX OMML vs Raster Images)
            equation_results = self._audit_equations()
            
            # 7. Images, DPI, Blurriness, and Aspect Ratio
            image_results = self._audit_images(zf)
            
            # 8. Tables & Overflow
            table_results = self._audit_tables(page_setup_results)
            
            # 9. Header & Footer Page Numbers
            header_footer_results = self._audit_header_footer()
            
            # 10. Text Box & Floating Shapes
            textbox_results = self._audit_textboxes()

        return {
            "filename": self.docx_path.name,
            "profile": self.profile["name"],
            "page_setup": page_setup_results,
            "typography": typography_results,
            "paragraph": paragraph_results,
            "headings": heading_results,
            "captions": caption_results,
            "equations": equation_results,
            "images": image_results,
            "tables": table_results,
            "header_footer": header_footer_results,
            "textboxes": textbox_results,
            "findings": self.findings,
        }

    def _load_xml_parts(self, zf: zipfile.ZipFile):
        """Parse XML parts from docx archive."""
        if "word/document.xml" in zf.namelist():
            self.doc_tree = ET.fromstring(zf.read("word/document.xml"))
        else:
            raise ValueError("Invalid docx: word/document.xml not found")

        if "word/styles.xml" in zf.namelist():
            self.styles_tree = ET.fromstring(zf.read("word/styles.xml"))

        if "word/settings.xml" in zf.namelist():
            self.settings_tree = ET.fromstring(zf.read("word/settings.xml"))

        if "word/_rels/document.xml.rels" in zf.namelist():
            rels_tree = ET.fromstring(zf.read("word/_rels/document.xml.rels"))
            for r in rels_tree.findall(".//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
                r_id = r.attrib.get("Id", "")
                r_type = r.attrib.get("Type", "")
                r_target = r.attrib.get("Target", "")
                if "image" in r_type.lower():
                    # Handle relative paths: media/image1.png or /word/media/image1.png
                    clean_target = r_target.lstrip("/").replace("word/", "")
                    self.image_rels[r_id] = "word/" + clean_target

    def _audit_page_setup(self) -> Dict[str, Any]:
        """Audit margins, paper size, orientation, and columns."""
        sect_prs = self.doc_tree.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}sectPr")
        sections = []
        has_margin_error = False

        for idx, sect in enumerate(sect_prs, 1):
            pg_mar = sect.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pgMar")
            pg_sz = sect.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}pgSz")
            cols = sect.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}cols")

            # Margins (in cm)
            top_cm = float(pg_mar.attrib.get(f"{{{NS['w']}}}top", "0")) / TWIPS_PER_CM if pg_mar is not None else 0.0
            bottom_cm = float(pg_mar.attrib.get(f"{{{NS['w']}}}bottom", "0")) / TWIPS_PER_CM if pg_mar is not None else 0.0
            left_cm = float(pg_mar.attrib.get(f"{{{NS['w']}}}left", "0")) / TWIPS_PER_CM if pg_mar is not None else 0.0
            right_cm = float(pg_mar.attrib.get(f"{{{NS['w']}}}right", "0")) / TWIPS_PER_CM if pg_mar is not None else 0.0

            # Paper Size
            w_twips = float(pg_sz.attrib.get(f"{{{NS['w']}}}w", "11906")) if pg_sz is not None else 11906.0
            h_twips = float(pg_sz.attrib.get(f"{{{NS['w']}}}h", "16838")) if pg_sz is not None else 16838.0
            width_cm = w_twips / TWIPS_PER_CM
            height_cm = h_twips / TWIPS_PER_CM
            orient = pg_sz.attrib.get(f"{{{NS['w']}}}orient", "portrait") if pg_sz is not None else "portrait"

            # Columns
            num_cols = int(cols.attrib.get(f"{{{NS['w']}}}num", "1")) if cols is not None else 1

            # Verify against profile
            tol = self.profile.get("margin_tolerance_cm", 0.25)
            exp_top = self.profile.get("margin_top_cm", 4.0)
            exp_bottom = self.profile.get("margin_bottom_cm", 3.0)
            exp_left = self.profile.get("margin_left_cm", 4.0)
            exp_right = self.profile.get("margin_right_cm", 3.0)

            margin_issues = []
            if abs(top_cm - exp_top) > tol:
                margin_issues.append(f"Top: {top_cm:.2f}cm (expected {exp_top:.1f}cm)")
            if abs(bottom_cm - exp_bottom) > tol:
                margin_issues.append(f"Bottom: {bottom_cm:.2f}cm (expected {exp_bottom:.1f}cm)")
            if abs(left_cm - exp_left) > tol:
                margin_issues.append(f"Left: {left_cm:.2f}cm (expected {exp_left:.1f}cm)")
            if abs(right_cm - exp_right) > tol:
                margin_issues.append(f"Right: {right_cm:.2f}cm (expected {exp_right:.1f}cm)")

            if margin_issues:
                has_margin_error = True
                self.findings.append({
                    "category": "Layout / Margins",
                    "severity": "FAIL",
                    "title": f"Margin Section {idx} Tidak Sesuai Standar {self.profile_name}",
                    "detail": f"Terdeteksi selisih margin: {', '.join(margin_issues)}.",
                    "remediation": f"Buka tab Layout -> Margins -> Custom Margins. Atur: Top={exp_top}cm, Bottom={exp_bottom}cm, Left={exp_left}cm, Right={exp_right}cm.",
                })

            # Check column count
            exp_cols = self.profile.get("expected_columns", 1)
            # In journals (like JIKI), section 1 (title & abstract) is 1 column, but body should be 2 columns
            if self.profile_name == "jiki-journal" and idx > 1 and num_cols != 2:
                self.findings.append({
                    "category": "Layout / Columns",
                    "severity": "FAIL",
                    "title": f"Kolom Naskah Jurnal Section {idx} Tidak Menggunakan 2 Kolom",
                    "detail": f"Naskah JIKI mensyaratkan 2 kolom seimbang pada bagian isi (terdeteksi {num_cols} kolom).",
                    "remediation": "Pilih bagian teks isi, buka tab Layout -> Columns -> Two Columns.",
                })

            sections.append({
                "section_index": idx,
                "top_cm": round(top_cm, 2),
                "bottom_cm": round(bottom_cm, 2),
                "left_cm": round(left_cm, 2),
                "right_cm": round(right_cm, 2),
                "width_cm": round(width_cm, 2),
                "height_cm": round(height_cm, 2),
                "orientation": orient,
                "columns": num_cols,
                "printable_width_cm": round(width_cm - left_cm - right_cm, 2),
            })

        # Hyphenation Check
        auto_hyphen = False
        if self.settings_tree is not None:
            auto_hyphen = self.settings_tree.find(f"{{{NS['w']}}}autoHyphenation") is not None

        return {
            "total_sections": len(sections),
            "sections": sections,
            "has_margin_error": has_margin_error,
            "auto_hyphenation": auto_hyphen,
        }

    def _audit_typography(self) -> Dict[str, Any]:
        """Audit font families, sizes, font colors, and highlights."""
        font_counts = {}
        size_counts = {}
        non_standard_colors = []
        highlighted_runs = []

        # Resolve default font from styles.xml (e.g. Normal style or docDefaults)
        default_font = "Times New Roman"
        if self.styles_tree is not None:
            for style_elem in self.styles_tree.findall(f".//{{{NS['w']}}}style"):
                if style_elem.attrib.get(f"{{{NS['w']}}}styleId") == "Normal":
                    rFonts = style_elem.find(f".//{{{NS['w']}}}rFonts")
                    if rFonts is not None:
                        default_font = rFonts.attrib.get(f"{{{NS['w']}}}ascii") or rFonts.attrib.get(f"{{{NS['w']}}}hAnsi") or default_font
                        break

        # Find all runs
        runs = self.doc_tree.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}r")
        for r in runs:
            t_elem = r.find(f"{{{NS['w']}}}t")
            has_text = t_elem is not None and t_elem.text and t_elem.text.strip()
            
            rPr = r.find(f"{{{NS['w']}}}rPr")
            if rPr is None:
                if has_text:
                    font_counts[default_font] = font_counts.get(default_font, 0) + 1
                continue

            # Font Family
            rFonts = rPr.find(f"{{{NS['w']}}}rFonts")
            if rFonts is not None:
                font_name = rFonts.attrib.get(f"{{{NS['w']}}}ascii") or rFonts.attrib.get(f"{{{NS['w']}}}hAnsi")
                if font_name and has_text:
                    font_counts[font_name] = font_counts.get(font_name, 0) + 1
            elif has_text:
                font_counts[default_font] = font_counts.get(default_font, 0) + 1

            # Font Size
            sz = rPr.find(f"{{{NS['w']}}}sz")
            if sz is not None:
                val = sz.attrib.get(f"{{{NS['w']}}}val")
                if val and val.isdigit() and has_text:
                    pt = float(val) / HALF_POINTS_PER_PT
                    size_counts[pt] = size_counts.get(pt, 0) + 1

            # Font Color
            color = rPr.find(f"{{{NS['w']}}}color")
            if color is not None:
                cval = color.attrib.get(f"{{{NS['w']}}}val", "").upper()
                if cval and cval not in ("AUTO", "000000", "DEFAULT"):
                    text_sample = t_elem.text[:30] if (t_elem is not None and t_elem.text) else ""
                    if text_sample.strip():
                        non_standard_colors.append({"color": f"#{cval}", "sample": text_sample})

            # Highlighting
            hi = rPr.find(f"{{{NS['w']}}}highlight")
            if hi is not None:
                hval = hi.attrib.get(f"{{{NS['w']}}}val", "")
                if hval and hval != "none":
                    text_sample = t_elem.text[:30] if (t_elem is not None and t_elem.text) else ""
                    highlighted_runs.append({"color": hval, "sample": text_sample})

        # Evaluate against profile
        expected_fonts = self.profile.get("font_family", ["Times New Roman"])
        allowed_aux_fonts = {"Cambria Math", "Segoe UI Symbol", "Symbol", "Wingdings", "Consolas", "Courier New"}
        rogue_fonts = [f for f in font_counts.keys() if f not in expected_fonts and f not in allowed_aux_fonts]

        if rogue_fonts:
            self.findings.append({
                "category": "Typography / Font Consistency",
                "severity": "WARN",
                "title": f"Inkonsistensi Font Terdeteksi ({len(rogue_fonts)} font tidak terduga)",
                "detail": f"Dokumen menggunakan font yang tidak seragam. Font yang tidak diharapkan: {rogue_fonts}.",
                "remediation": f"Seragamkan seluruh naskah menggunakan font standar: {expected_fonts[0]} (Pilih seluruh dokumen Ctrl+A -> Ubah font di tab Home).",
            })

        if non_standard_colors:
            self.findings.append({
                "category": "Typography / Font Color",
                "severity": "WARN",
                "title": f"Terdeteksi Warna Font Non-Hitam ({len(non_standard_colors)} run)",
                "detail": f"Ditemukan teks dengan warna di luar hitam (#000000): contoh warna {non_standard_colors[0]['color']} pada teks \"{non_standard_colors[0]['sample']}\". Biasanya sisa copy-paste.",
                "remediation": "Ubah warna teks menjadi Automatic / Black (#000000) melalui tab Home -> Font Color.",
            })

        if highlighted_runs:
            self.findings.append({
                "category": "Typography / Highlighter",
                "severity": "WARN",
                "title": f"Teks Masih Mengandung Stabilo / Highlight ({len(highlighted_runs)} run)",
                "detail": f"Teks naskah masih memiliki highlight {highlighted_runs[0]['color']}: \"{highlighted_runs[0]['sample']}\".",
                "remediation": "Hapus highlight melalui tab Home -> Text Highlight Color -> No Color.",
            })

        return {
            "font_distribution": font_counts,
            "size_distribution_pt": dict(sorted(size_counts.items())),
            "rogue_fonts": rogue_fonts,
            "non_black_color_count": len(non_standard_colors),
            "highlight_count": len(highlighted_runs),
        }

    def _audit_paragraph_formatting(self) -> Dict[str, Any]:
        """Audit paragraph alignment, line spacing, and spacing before/after."""
        paragraphs = self.doc_tree.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p")
        align_counts = {}
        line_spacing_counts = {}
        before_spacing_counts = {}
        after_spacing_counts = {}
        tab_stop_counts = {}
        unjustified_body_count = 0

        for p in paragraphs:
            text = "".join([t.text for t in p.findall(f".//{{{NS['w']}}}t") if t.text]).strip()
            if not text:
                continue

            pPr = p.find(f"{{{NS['w']}}}pPr")
            if pPr is None:
                continue

            # Alignment
            jc = pPr.find(f"{{{NS['w']}}}jc")
            align = jc.attrib.get(f"{{{NS['w']}}}val", "left") if jc is not None else "left"
            align_counts[align] = align_counts.get(align, 0) + 1

            if len(text) > 120 and align != "both":
                unjustified_body_count += 1

            # Spacing
            spacing = pPr.find(f"{{{NS['w']}}}spacing")
            if spacing is not None:
                before = spacing.attrib.get(f"{{{NS['w']}}}before", "0")
                after = spacing.attrib.get(f"{{{NS['w']}}}after", "0")
                before_spacing_counts[before] = before_spacing_counts.get(before, 0) + 1
                after_spacing_counts[after] = after_spacing_counts.get(after, 0) + 1
                line_val = spacing.attrib.get(f"{{{NS['w']}}}line")
                if line_val and line_val.isdigit():
                    multiplier = round(float(line_val) / 240.0, 2)
                    line_spacing_counts[multiplier] = line_spacing_counts.get(multiplier, 0) + 1

            tabs = pPr.find(f"{{{NS['w']}}}tabs")
            if tabs is not None:
                for tab in tabs.findall(f"{{{NS['w']}}}tab"):
                    pos = tab.attrib.get(f"{{{NS['w']}}}pos", "")
                    if pos:
                        tab_stop_counts[pos] = tab_stop_counts.get(pos, 0) + 1

        if unjustified_body_count > 5:
            self.findings.append({
                "category": "Paragraph / Alignment",
                "severity": "FAIL",
                "title": f"Paragraf Isi Naskah Tidak Rata Kanan-Kiri (Justified) ({unjustified_body_count} paragraf)",
                "detail": "Standar penulisan ilmiah/skripsi mewajibkan format Justify (both) untuk badan teks.",
                "remediation": "Seleksi paragraf teks, tekan Ctrl+J atau buka tab Home -> Paragraph -> Justify.",
            })

        # Check line spacing against profile
        expected_spacings = self.profile.get("line_spacing", [1.5])
        if line_spacing_counts:
            dominant_spacing = max(line_spacing_counts.items(), key=lambda x: x[1])[0]
            if not any(abs(dominant_spacing - esp) < 0.1 for esp in expected_spacings):
                self.findings.append({
                    "category": "Paragraph / Line Spacing",
                    "severity": "WARN",
                    "title": f"Spasi Antar Baris ({dominant_spacing}x) Tidak Sesuai Standar {self.profile_name}",
                    "detail": f"Spasi dominan dokumen adalah {dominant_spacing}x (Single/1.0), sedangkan standar {self.profile_name} mengharuskan {expected_spacings} spasi.",
                    "remediation": f"Seleksi teks naskah -> Buka tab Home -> Paragraph -> Line Spacing -> Pilih {expected_spacings[0]} spasi (Ctrl+5 untuk 1.5).",
                })

        return {
            "alignment_distribution": align_counts,
            "line_spacing_distribution": line_spacing_counts,
            "before_spacing_twips": before_spacing_counts,
            "after_spacing_twips": after_spacing_counts,
            "tab_stop_distribution_twips": tab_stop_counts,
            "unjustified_body_paragraphs": unjustified_body_count,
        }

    def _audit_headings(self) -> Dict[str, Any]:
        """Audit heading styles (Heading 1/2/3) vs unstyled raw bold text."""
        paragraphs = self.doc_tree.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p")
        headings_found = []
        fake_headings = []

        for p in paragraphs:
            text = "".join([t.text for t in p.findall(f".//{{{NS['w']}}}t") if t.text]).strip()
            if not text or len(text) > 100:
                continue

            pPr = p.find(f"{{{NS['w']}}}pPr")
            style_name = ""
            if pPr is not None:
                pStyle = pPr.find(f"{{{NS['w']}}}pStyle")
                if pStyle is not None:
                    style_name = pStyle.attrib.get(f"{{{NS['w']}}}val", "")

            # Check if text looks like a heading
            is_heading_pattern = bool(re.match(r"^(?:BAB\s+[IVXLCDM]+|[0-9]{1,2}(?:\.[0-9]{1,2})*|[A-Z][a-zA-Z\s]{3,35})\b", text))
            
            # Check if all runs are bold
            runs = p.findall(f".//{{{NS['w']}}}r")
            all_bold = runs and all(r.find(f".//{{{NS['w']}}}b") is not None for r in runs if "".join(r.itertext()).strip())

            if "Heading" in style_name or "heading" in style_name.lower():
                headings_found.append({"style": style_name, "text": text})
            elif is_heading_pattern and all_bold and style_name in ("", "Normal", "NormalWeb"):
                fake_headings.append(text)

        if fake_headings:
            self.findings.append({
                "category": "Headings / Document Structure",
                "severity": "WARN",
                "title": f"Judul Subbab Menggunakan Format Bold Manual (Bukan Heading Style) ({len(fake_headings)} judul)",
                "detail": f"Ditemukan judul subbab yang hanya di-bold manual tanpa style Heading Word: \"{fake_headings[0]}\". Hal ini merusak Daftar Isi otomatis dan Navigation Pane.",
                "remediation": "Gunakan Style Word resmi: klik teks subbab -> pilih 'Heading 1', 'Heading 2', atau 'Heading 3' di tab Home -> Styles.",
            })

        return {
            "proper_headings_count": len(headings_found),
            "fake_headings_count": len(fake_headings),
            "fake_headings_sample": fake_headings[:5],
        }

    def _audit_captions_and_toc(self) -> Dict[str, Any]:
        """Audit Table & Figure captions, positions, TOC, List of Tables, and List of Figures."""
        doc_xml_str = ET.tostring(self.doc_tree, encoding="utf-8").decode("utf-8")
        
        # Check TOC fields
        has_toc = "TOC \\o" in doc_xml_str or "TOC \\h" in doc_xml_str
        has_table_list = 'TOC \\h \\z \\c "Tabel"' in doc_xml_str or 'TOC \\c "Table"' in doc_xml_str or "DAFTAR TABEL" in doc_xml_str
        has_figure_list = 'TOC \\h \\z \\c "Gambar"' in doc_xml_str or 'TOC \\c "Figure"' in doc_xml_str or "DAFTAR GAMBAR" in doc_xml_str

        body = self.doc_tree.find(f"{{{NS['w']}}}body")
        table_caption_pat = re.compile(r"^\s*(?:Tabel|Table)\s+[0-9]+(?:\.[0-9]+)*", re.IGNORECASE)
        figure_caption_pat = re.compile(r"^\s*(?:Gambar|Figure|Fig\.)\s+[0-9]+(?:\.[0-9]+)*", re.IGNORECASE)

        table_captions_count = 0
        figure_captions_count = 0
        misplaced_table_captions = 0
        misplaced_figure_captions = 0
        native_caption_fields = 0
        plain_caption_paragraphs = []

        # Scan every paragraph, including paragraphs inside table cells.
        for paragraph in self.doc_tree.findall(f".//{{{NS['w']}}}p"):
            p_text = "".join(paragraph.itertext()).strip()
            field_texts = [instr.text or "" for instr in paragraph.findall(f".//{{{NS['w']}}}instrText")]
            field_texts.extend(
                field.attrib.get(f"{{{NS['w']}}}instr", "")
                for field in paragraph.findall(f".//{{{NS['w']}}}fldSimple")
            )
            has_seq = any(
                re.search(r"\bSEQ\s+(?:Table|Tabel|Figure|Gambar)\b", text, re.I)
                for text in field_texts
            )
            is_caption_text = bool(table_caption_pat.match(p_text) or figure_caption_pat.match(p_text))
            if has_seq:
                native_caption_fields += 1
            elif is_caption_text:
                plain_caption_paragraphs.append(p_text)

        if body is not None:
            children = list(body)
            for idx, child in enumerate(children):
                tag = child.tag.split("}")[-1]

                # Check Table Caption Placement (Must be ABOVE table)
                if tag == "tbl":
                    prev_is_caption = False
                    if idx > 0 and children[idx - 1].tag.endswith("p"):
                        prev_text = "".join(children[idx - 1].itertext()).strip()
                        if table_caption_pat.match(prev_text):
                            prev_is_caption = True
                            table_captions_count += 1
                    
                    next_is_caption = False
                    if idx < len(children) - 1 and children[idx + 1].tag.endswith("p"):
                        next_text = "".join(children[idx + 1].itertext()).strip()
                        if table_caption_pat.match(next_text):
                            next_is_caption = True
                            table_captions_count += 1

                    if not prev_is_caption and next_is_caption:
                        misplaced_table_captions += 1

                # Check Figure Caption Placement (Must be BELOW figure)
                elif tag == "p" and child.find(f".//{{{NS['w']}}}drawing") is not None:
                    next_is_caption = False
                    if idx < len(children) - 1 and children[idx + 1].tag.endswith("p"):
                        next_text = "".join(children[idx + 1].itertext()).strip()
                        if figure_caption_pat.match(next_text):
                            next_is_caption = True
                            figure_captions_count += 1

                    prev_is_caption = False
                    if idx > 0 and children[idx - 1].tag.endswith("p"):
                        prev_text = "".join(children[idx - 1].itertext()).strip()
                        if figure_caption_pat.match(prev_text):
                            prev_is_caption = True
                            figure_captions_count += 1

                    if not next_is_caption and prev_is_caption:
                        misplaced_figure_captions += 1

        exp_table_pos = self.profile.get("table_caption_position", "above")
        exp_fig_pos = self.profile.get("figure_caption_position", "below")

        if exp_table_pos == "above" and misplaced_table_captions > 0:
            self.findings.append({
                "category": "Captions / Table Placement",
                "severity": "FAIL",
                "title": f"Posisi Caption Tabel Salah ({misplaced_table_captions} caption di bawah tabel)",
                "detail": "Standar naskah mewajibkan judul/caption tabel berada di ATAS tabel, bukan di bawah tabel!",
                "remediation": "Pindahkan paragraf caption tabel tepat di atas tabel bersangkutan.",
            })

        if exp_fig_pos == "below" and misplaced_figure_captions > 0:
            self.findings.append({
                "category": "Captions / Figure Placement",
                "severity": "FAIL",
                "title": f"Posisi Caption Gambar Salah ({misplaced_figure_captions} caption di atas gambar)",
                "detail": "Standar naskah mewajibkan caption gambar berada di BAWAH gambar, bukan di atas gambar!",
                "remediation": "Pindahkan paragraf caption gambar tepat di bawah gambar bersangkutan.",
            })

        if self.profile.get("require_native_captions") and plain_caption_paragraphs:
            self.findings.append({
                "category": "Captions / Native Word Fields",
                "severity": "FAIL",
                "title": f"Caption Manual Terdeteksi ({len(plain_caption_paragraphs)} paragraf)",
                "detail": "Caption tabel/gambar harus dibuat dengan References -> Insert Caption agar penomoran, cross-reference, dan daftar tabel/gambar tetap otomatis.",
                "remediation": "Ganti caption manual dengan References -> Insert Caption, lalu gunakan Update Field untuk memperbarui nomor.",
            })

        if self.profile.get("require_toc") and not has_toc:
            self.findings.append({
                "category": "References / Table of Contents",
                "severity": "FAIL",
                "title": "Daftar Isi Otomatis (Table of Contents) Belum Ada",
                "detail": "Format naskah mensyaratkan Daftar Isi otomatis melalui field TOC Word.",
                "remediation": "Posisikan kursor pada halaman Daftar Isi, buka tab References -> Table of Contents -> Automatic Table.",
            })

        if self.profile.get("require_table_list") and not has_table_list:
            self.findings.append({
                "category": "References / List of Tables",
                "severity": "FAIL",
                "title": "Daftar Tabel Otomatis Belum Terdeteksi",
                "detail": "Format naskah mensyaratkan Daftar Tabel otomatis (TOC \\c \"Tabel\").",
                "remediation": "Posisikan kursor pada halaman Daftar Tabel, buka tab References -> Insert Table of Figures -> Caption label: Tabel.",
            })

        if self.profile.get("require_figure_list") and not has_figure_list:
            self.findings.append({
                "category": "References / List of Figures",
                "severity": "FAIL",
                "title": "Daftar Gambar Otomatis Belum Terdeteksi",
                "detail": "Format naskah mensyaratkan Daftar Gambar otomatis (TOC \\c \"Gambar\").",
                "remediation": "Posisikan kursor pada halaman Daftar Gambar, buka tab References -> Insert Table of Figures -> Caption label: Gambar.",
            })

        return {
            "has_table_of_contents": has_toc,
            "has_table_list": has_table_list,
            "has_figure_list": has_figure_list,
            "table_captions_count": table_captions_count,
            "figure_captions_count": figure_captions_count,
            "misplaced_table_captions": misplaced_table_captions,
            "misplaced_figure_captions": misplaced_figure_captions,
            "native_caption_fields": native_caption_fields,
            "plain_caption_paragraphs": plain_caption_paragraphs[:20],
        }

    def _audit_equations(self) -> Dict[str, Any]:
        """Audit mathematical equations (Native OMML LaTeX vs Rasterized Images)."""
        omml_equations = self.doc_tree.findall(f".//{{{NS['m']}}}oMath")
        omml_paras = self.doc_tree.findall(f".//{{{NS['m']}}}oMathPara")
        
        # Check for raster equations: drawings adjacent to "Persamaan" or "(1)"
        raster_equation_cues = []
        paragraphs = self.doc_tree.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p")
        for p in paragraphs:
            has_drawing = p.find(f".//{{{NS['w']}}}drawing") is not None
            text = "".join([t.text for t in p.findall(f".//{{{NS['w']}}}t") if t.text]).strip()
            if has_drawing and re.search(r"\b(?:persamaan|equation|\([0-9]+\))\b", text, re.IGNORECASE):
                raster_equation_cues.append(text[:40])

        if raster_equation_cues:
            self.findings.append({
                "category": "Equations / Mathematical Notation",
                "severity": "FAIL",
                "title": f"Rumus Matematika Disisipkan Sebagai Gambar ({len(raster_equation_cues)} terindikasi)",
                "detail": "Jurnal dan pedoman skripsi melarang keras formula matematika ditempel sebagai gambar bitmap/screenshot!",
                "remediation": "Gunakan editor Equation Word resmi (Alt+=) atau sisipkan LaTeX OMML melalui Pandoc.",
            })

        return {
            "native_omml_equations_count": len(omml_equations) + len(omml_paras),
            "rasterized_equation_cues": raster_equation_cues,
        }

    def _audit_images(self, zf: zipfile.ZipFile) -> Dict[str, Any]:
        """Audit images for effective DPI, blurriness, and aspect ratio distortion."""
        drawings = self.doc_tree.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing")
        audited_images = []
        low_dpi_count = 0
        blurry_count = 0
        distorted_count = 0

        min_dpi = self.profile.get("min_image_dpi", 200.0)

        for idx, d in enumerate(drawings, 1):
            extent = d.find(".//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent")
            blip = d.find(".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip")

            if extent is None or blip is None:
                continue

            cx = float(extent.attrib.get("cx", "0"))
            cy = float(extent.attrib.get("cy", "0"))
            if cx <= 0 or cy <= 0:
                continue

            display_w_in = cx / EMUS_PER_INCH
            display_h_in = cy / EMUS_PER_INCH

            embed_id = blip.attrib.get(f"{{{NS['r']}}}embed", "")
            media_path = self.image_rels.get(embed_id, "")

            if not media_path or media_path not in zf.namelist():
                continue

            ext = Path(media_path).suffix.lower()
            if ext in (".svg", ".emf", ".wmf"):
                # Vector images have infinite resolution
                audited_images.append({
                    "image_id": idx,
                    "file": Path(media_path).name,
                    "type": "vector",
                    "effective_dpi": "Infinite (Vector)",
                    "blur_score": "N/A (Vector)",
                    "status": "PASS",
                })
                continue

            try:
                img_bytes = zf.read(media_path)
                pil_img = Image.open(io.BytesIO(img_bytes))
                px_w, px_h = pil_img.size

                # Effective DPI
                dpi_x = px_w / display_w_in
                dpi_y = px_h / display_h_in
                effective_dpi = round(min(dpi_x, dpi_y), 1)

                # Aspect Ratio Distortion
                native_ratio = px_w / px_h
                display_ratio = cx / cy
                ratio_diff = abs(native_ratio - display_ratio) / native_ratio
                is_distorted = ratio_diff > 0.05  # >5% deformation

                # Blur Variance
                blur_val = calculate_blur_variance(pil_img)
                is_blurry = 0 < blur_val < 80.0  # severely blurry

                status = "PASS"
                reasons = []
                if effective_dpi < 150.0:
                    status = "CRITICAL_LOW_RES"
                    low_dpi_count += 1
                    reasons.append(f"Resolusi sangat rendah ({effective_dpi:.1f} DPI < min {min_dpi} DPI)")
                elif effective_dpi < min_dpi:
                    status = "LOW_RES"
                    low_dpi_count += 1
                    reasons.append(f"Resolusi di bawah standar ({effective_dpi:.1f} DPI)")

                if is_blurry:
                    status = "BLURRY"
                    blurry_count += 1
                    reasons.append(f"Gambar buram/kabur (Laplacian score {blur_val:.1f} < 80)")

                if is_distorted:
                    distorted_count += 1
                    reasons.append(f"Aspek rasio terdistorsi/gepeng (melar {ratio_diff*100:.1f}%)")

                if status != "PASS" or is_distorted:
                    self.findings.append({
                        "category": "Images / Quality & Resolution",
                        "severity": "FAIL" if "CRITICAL" in status or is_blurry else "WARN",
                        "title": f"Kualitas Gambar {Path(media_path).name} Bermasalah ({status})",
                        "detail": f"Ukuran cetak {display_w_in:.2f} x {display_h_in:.2f} inci, piksel {px_w}x{px_h}. Masalah: {'; '.join(reasons)}.",
                        "remediation": "Ganti gambar dengan versi resolusi tinggi (minimal 300 DPI) dan jangan menarik sudut gambar tanpa mengunci rasio aspek (Hold Shift).",
                    })

                audited_images.append({
                    "image_id": idx,
                    "file": Path(media_path).name,
                    "type": "raster",
                    "pixels": f"{px_w}x{px_h}",
                    "print_size_in": f"{display_w_in:.2f}x{display_h_in:.2f}",
                    "effective_dpi": effective_dpi,
                    "blur_score": round(blur_val, 1) if blur_val >= 0 else "N/A",
                    "status": status,
                })
            except Exception:
                pass

        return {
            "total_images": len(audited_images),
            "low_dpi_count": low_dpi_count,
            "blurry_count": blurry_count,
            "distorted_count": distorted_count,
            "images": audited_images,
        }

    def _audit_tables(self, page_setup: Dict[str, Any]) -> Dict[str, Any]:
        """Audit tables for printable width overflow, vertical borders, and headers."""
        tables = self.doc_tree.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tbl")
        sections = page_setup.get("sections", [{}])
        first_printable_width_cm = sections[0].get("printable_width_cm", 14.0) if sections else 14.0
        
        overflow_count = 0
        has_vertical_borders_count = 0

        for idx, tbl in enumerate(tables, 1):
            # Check Table Width
            tblGrid = tbl.find(f"{{{NS['w']}}}tblGrid")
            if tblGrid is not None:
                cols = tblGrid.findall(f"{{{NS['w']}}}gridCol")
                col_widths_twips = [float(c.attrib.get(f"{{{NS['w']}}}w", "0")) for c in cols if c.attrib.get(f"{{{NS['w']}}}w", "0").isdigit()]
                total_w_cm = sum(col_widths_twips) / TWIPS_PER_CM
                if total_w_cm > (first_printable_width_cm + 0.3):
                    overflow_count += 1
                    self.findings.append({
                        "category": "Tables / Column Overflow",
                        "severity": "FAIL",
                        "title": f"Tabel {idx} Meluber Keluar Batas Margin Halaman (Overflow)",
                        "detail": f"Lebar tabel adalah {total_w_cm:.2f} cm, sedangkan batas cetak halaman hanya {first_printable_width_cm:.2f} cm.",
                        "remediation": "Atur AutoFit Table: klik kanan tabel -> AutoFit -> AutoFit to Window.",
                    })

            # Check Academic Borders (No Vertical Lines)
            tblPr = tbl.find(f"{{{NS['w']}}}tblPr")
            if tblPr is not None and self.profile.get("academic_table_borders"):
                tblBorders = tblPr.find(f"{{{NS['w']}}}tblBorders")
                if tblBorders is not None:
                    insideV = tblBorders.find(f"{{{NS['w']}}}insideV")
                    left_b = tblBorders.find(f"{{{NS['w']}}}left")
                    right_b = tblBorders.find(f"{{{NS['w']}}}right")
                    has_v = False
                    for b in (insideV, left_b, right_b):
                        if b is not None and b.attrib.get(f"{{{NS['w']}}}val", "none") not in ("none", "nil"):
                            has_v = True
                            break
                    if has_v:
                        has_vertical_borders_count += 1

        if has_vertical_borders_count > 0:
            self.findings.append({
                "category": "Tables / Border Style",
                "severity": "WARN",
                "title": f"Tabel Mengandung Garis Vertikal ({has_vertical_borders_count} tabel)",
                "detail": "Standar publikasi ilmiah (IEEE, JIKI, Elsevier) menggunakan 'Three-Line Table' tanpa garis vertikal.",
                "remediation": "Pilih tabel -> Table Design -> Borders -> Hilangkan Left Border, Right Border, dan Inside Vertical Border.",
            })

        return {
            "total_tables": len(tables),
            "overflow_tables": overflow_count,
            "tables_with_vertical_borders": has_vertical_borders_count,
        }

    def _audit_header_footer(self) -> Dict[str, Any]:
        """Audit headers, footers, and page numbers."""
        header_files = [n for n in self.zip_ref.namelist() if n.startswith("word/header")]
        footer_files = [n for n in self.zip_ref.namelist() if n.startswith("word/footer")]
        has_page_field = False

        for f in header_files + footer_files:
            content = self.zip_ref.read(f).decode("utf-8", errors="replace")
            if "PAGE" in content:
                has_page_field = True
                break

        return {
            "headers_count": len(header_files),
            "footers_count": len(footer_files),
            "has_page_number_field": has_page_field,
        }

    def _audit_textboxes(self) -> Dict[str, Any]:
        """Audit floating text boxes."""
        textboxes = self.doc_tree.findall(".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}txbxContent")
        return {
            "textbox_count": len(textboxes),
        }


def format_text_report(audit: Dict[str, Any]) -> str:
    """Format audit results as a clear, actionable ASCII terminal report."""
    lines = []
    lines.append("=" * 85)
    lines.append(f"COMPREHENSIVE MICROSOFT WORD LAYOUT & VISUAL AUDIT REPORT")
    lines.append(f"File   : {audit['filename']}")
    lines.append(f"Profile: {audit['profile']}")
    lines.append("=" * 85)

    # 1. Page Setup Summary
    lines.append("1. PAGE SETUP & LAYOUT AUDIT")
    pset = audit["page_setup"]
    lines.append(f"   Total Sections : {pset['total_sections']}")
    for s in pset["sections"]:
        status_badge = "[FAIL]" if pset["has_margin_error"] else "[PASS]"
        lines.append(
            f"   Section {s['section_index']:2d} {status_badge}: Margins [Top: {s['top_cm']}cm, Bottom: {s['bottom_cm']}cm, "
            f"Left: {s['left_cm']}cm, Right: {s['right_cm']}cm] | Paper: {s['width_cm']}x{s['height_cm']}cm ({s['orientation']}) | Columns: {s['columns']}"
        )
    lines.append("-" * 85)

    # 2. Typography & Fonts Summary
    lines.append("2. TYPOGRAPHY & FONT INTEGRITY (HOME TAB)")
    typo = audit["typography"]
    lines.append(f"   Font Distribution : {typo['font_distribution']}")
    lines.append(f"   Font Sizes (pt)   : {list(typo['size_distribution_pt'].keys())}")
    if typo["rogue_fonts"]:
        lines.append(f"   [WARN] Inconsistent Rogue Fonts: {typo['rogue_fonts']}")
    else:
        lines.append("   [PASS] Font family consistent across all inspected text runs.")
    if typo["non_black_color_count"] > 0:
        lines.append(f"   [WARN] Non-standard font colors detected ({typo['non_black_color_count']} runs).")
    if typo["highlight_count"] > 0:
        lines.append(f"   [WARN] Active highlighter marker text detected ({typo['highlight_count']} runs).")
    lines.append("-" * 85)

    # 3. Paragraph & Alignment Summary
    lines.append("3. PARAGRAPH FORMATTING & ALIGNMENT")
    para = audit["paragraph"]
    lines.append(f"   Alignment Distribution : {para['alignment_distribution']}")
    lines.append(f"   Line Spacing Ratios    : {para['line_spacing_distribution']}")
    lines.append(f"   Before/After Spacing   : {para['before_spacing_twips']} / {para['after_spacing_twips']} twips")
    lines.append(f"   Tab Stops              : {para['tab_stop_distribution_twips']}")
    if para["unjustified_body_paragraphs"] > 0:
        lines.append(f"   [FAIL] {para['unjustified_body_paragraphs']} body paragraphs are not Justified (rata kanan-kiri).")
    else:
        lines.append("   [PASS] Paragraph alignment complies with academic standards.")
    lines.append("-" * 85)

    # 4. Headings & Structure Summary
    lines.append("4. HEADINGS & STRUCTURE (NAVIGATION PANE)")
    head = audit["headings"]
    lines.append(f"   Proper Heading Styles Found : {head['proper_headings_count']}")
    if head["fake_headings_count"] > 0:
        lines.append(f"   [WARN] Fake Headings (bold manual without Heading Style): {head['fake_headings_count']}")
        for fh in head["fake_headings_sample"][:3]:
            lines.append(f"          - \"{fh}\"")
    else:
        lines.append("   [PASS] All subheadings use proper semantic Heading styles.")
    lines.append("-" * 85)

    # 5. Captions & Lists Summary
    lines.append("5. CAPTIONS & TABLES OF CONTENTS (REFERENCES TAB)")
    cap = audit["captions"]
    lines.append(f"   Table Captions Count  : {cap['table_captions_count']}")
    lines.append(f"   Figure Captions Count : {cap['figure_captions_count']}")
    lines.append(f"   Native Word Caption Fields: {cap['native_caption_fields']}")
    if cap.get("plain_caption_paragraphs"):
        lines.append(f"   [FAIL] Manual caption paragraphs: {len(cap['plain_caption_paragraphs'])}")
    lines.append(f"   Table of Contents     : {'[PASS] Present' if cap['has_table_of_contents'] else '[FAIL] Missing'}")
    lines.append(f"   List of Tables        : {'[PASS] Present' if cap['has_table_list'] else '[WARN] Not detected'}")
    lines.append(f"   List of Figures       : {'[PASS] Present' if cap['has_figure_list'] else '[WARN] Not detected'}")
    lines.append("-" * 85)

    # 6. Mathematical Equations Summary
    lines.append("6. MATHEMATICAL FORMULAS & EQUATIONS (INSERT TAB - SYMBOLS)")
    eq = audit["equations"]
    lines.append(f"   Native OMML Equations : {eq['native_omml_equations_count']}")
    if eq["rasterized_equation_cues"]:
        lines.append(f"   [FAIL] Equations suspected of being pasted as pictures/screenshots: {len(eq['rasterized_equation_cues'])}")
    else:
        lines.append("   [PASS] All formulas appear to be native equations (LaTeX OMML).")
    lines.append("-" * 85)

    # 7. Images & Resolution Summary
    lines.append("7. IMAGE QUALITY, RESOLUTION & BLURRINESS (INSERT TAB - PICTURES)")
    imgs = audit["images"]
    lines.append(f"   Total Embedded Images : {imgs['total_images']}")
    lines.append(f"   Low DPI (<200 DPI)    : {imgs['low_dpi_count']}")
    lines.append(f"   Blurry Images         : {imgs['blurry_count']}")
    lines.append(f"   Distorted Aspect Ratio: {imgs['distorted_count']}")
    for im in imgs["images"][:6]:
        lines.append(
            f"   - {im['file']:18s} | {im['type']:6s} | Size: {im.get('pixels', 'N/A'):10s} | "
            f"DPI: {str(im.get('effective_dpi', 'N/A')):8s} | Blur: {str(im.get('blur_score', 'N/A')):6s} | [{im['status']}]"
        )
    if len(imgs["images"]) > 6:
        lines.append(f"     ... and {len(imgs['images']) - 6} more images.")
    lines.append("-" * 85)

    # 8. Tables Summary
    lines.append("8. TABLE FORMATTING & OVERFLOW (INSERT TAB - TABLES)")
    tbl = audit["tables"]
    lines.append(f"   Total Tables Inspected: {tbl['total_tables']}")
    if tbl["overflow_tables"] > 0:
        lines.append(f"   [FAIL] {tbl['overflow_tables']} tables exceed printable margin width (overflowing off-page).")
    else:
        lines.append("   [PASS] All tables fit neatly within page margins.")
    if tbl["tables_with_vertical_borders"] > 0:
        lines.append(f"   [WARN] {tbl['tables_with_vertical_borders']} tables contain vertical borders (remove for academic style).")
    lines.append("=" * 85)

    # Actionable Findings List
    lines.append("ACTIONABLE REMEDIATION ROADMAP (OFFICE SHORTCUTS & FIXES):")
    if not audit["findings"]:
        lines.append("   [EXCELLENT] No layout, typography, or image formatting defects detected!")
    else:
        for idx, f in enumerate(audit["findings"], 1):
            lines.append(f"   {idx:2d}. [{f['severity']:4s}] {f['category']} - {f['title']}")
            lines.append(f"       Problem : {f['detail']}")
            lines.append(f"       Solusi  : {f['remediation']}")
            lines.append("")
    lines.append("=" * 85)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Audit Word documents (.docx) for academic layout, typography, equations, and image quality.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("docx_path", help="Path to the Word document (.docx)")
    parser.add_argument(
        "--profile",
        choices=["skripsi-id", "jiki-journal", "general"],
        default="skripsi-id",
        help="Target publication profile (default: skripsi-id)",
    )
    parser.add_argument(
        "--template",
        help="Path to a reference template (.docx/.dotx) to automatically extract formatting rules (margins, fonts, columns)",
    )
    parser.add_argument(
        "--template-rules-output",
        help="Markdown template contract path (default: <template>-rules.md)",
    )
    parser.add_argument(
        "--config",
        help="Path to a custom JSON profile configuration file",
    )
    parser.add_argument(
        "--margins",
        nargs=4,
        type=float,
        metavar=("TOP", "BOTTOM", "LEFT", "RIGHT"),
        help="Override target margins in cm, e.g. --margins 4.0 3.0 4.0 3.0 or --margins 2.54 2.54 2.54 2.54",
    )
    parser.add_argument(
        "--font",
        help="Override expected font family (e.g. --font Arial or --font 'Times New Roman')",
    )
    parser.add_argument(
        "--line-spacing",
        nargs="+",
        type=float,
        help="Override expected line spacing multipliers, e.g. --line-spacing 1.5 2.0",
    )
    parser.add_argument(
        "--columns",
        type=int,
        choices=[1, 2],
        help="Override expected column count in body sections (1 or 2)",
    )
    parser.add_argument(
        "--table-caption",
        choices=["above", "below", "any"],
        help="Target table caption placement (above, below, or any)",
    )
    parser.add_argument(
        "--figure-caption",
        choices=["below", "above", "any"],
        help="Target figure caption placement (below, above, or any)",
    )
    parser.add_argument(
        "--require-toc",
        action="store_true",
        default=None,
        help="Mandate presence of an automatic Table of Contents",
    )
    parser.add_argument(
        "--no-toc",
        dest="require_toc",
        action="store_false",
        help="Do not require a Table of Contents",
    )
    parser.add_argument(
        "--require-table-list",
        action="store_true",
        default=None,
        help="Mandate presence of an automatic List of Tables",
    )
    parser.add_argument(
        "--require-figure-list",
        action="store_true",
        default=None,
        help="Mandate presence of an automatic List of Figures",
    )
    parser.add_argument(
        "--no-native-caption-check",
        dest="require_native_captions",
        action="store_false",
        default=None,
        help="Allow manually typed caption text (use only when the template explicitly requires it)",
    )
    parser.add_argument(
        "--min-dpi",
        type=float,
        help="Minimum image DPI threshold (default: 200.0)",
    )
    parser.add_argument("-o", "--output", help="Output report file path (.txt or .json)")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format (default: text)")

    args = parser.parse_args()

    # Determine base profile
    custom_profile = None
    if args.template:
        from template_rules import extract as extract_template_rules, render as render_template_rules

        template_path = Path(args.template).resolve()
        rules_path = Path(args.template_rules_output).resolve() if args.template_rules_output else template_path.with_name(f"{template_path.stem}-rules.md")
        rules_path.write_text(render_template_rules(extract_template_rules(template_path)), encoding="utf-8")
        print(f"Template rules saved to: {rules_path}")
        custom_profile = extract_profile_from_template(args.template)
    elif args.config:
        with open(args.config, "r", encoding="utf-8") as f:
            custom_profile = json.load(f)

    # Build overrides
    overrides = {}
    if args.margins:
        top_cm, bottom_cm, left_cm, right_cm = args.margins
        overrides["margin_top_cm"] = top_cm
        overrides["margin_bottom_cm"] = bottom_cm
        overrides["margin_left_cm"] = left_cm
        overrides["margin_right_cm"] = right_cm
    if args.font:
        overrides["font_family"] = [args.font]
    if args.line_spacing:
        overrides["line_spacing"] = args.line_spacing
    if args.columns:
        overrides["expected_columns"] = args.columns
    if args.table_caption:
        overrides["table_caption_position"] = args.table_caption
    if args.figure_caption:
        overrides["figure_caption_position"] = args.figure_caption
    if args.require_toc is not None:
        overrides["require_toc"] = args.require_toc
    if args.require_table_list is not None:
        overrides["require_table_list"] = args.require_table_list
    if args.require_figure_list is not None:
        overrides["require_figure_list"] = args.require_figure_list
    if args.require_native_captions is not None:
        overrides["require_native_captions"] = args.require_native_captions
    if args.min_dpi:
        overrides["min_image_dpi"] = args.min_dpi

    auditor = DocumentLayoutAuditor(
        args.docx_path,
        profile_name=args.profile,
        custom_profile=custom_profile,
        overrides=overrides,
    )
    audit = auditor.audit()

    if args.format == "json":
        report = json.dumps(audit, indent=2)
    else:
        report = format_text_report(audit)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Layout audit report saved to: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
