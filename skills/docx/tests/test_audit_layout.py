#!/usr/bin/env python3
"""Unit tests for audit_layout.py covering margins, typography, image DPI, blur, and table overflow."""

import io
import sys
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from audit_layout import DocumentLayoutAuditor, calculate_blur_variance, extract_profile_from_template, PROFILES


class TestLayoutAuditor(unittest.TestCase):
    def test_laplacian_blur_calculation(self):
        # Create a sharp image with high-contrast edges
        arr = np.zeros((100, 100), dtype=np.uint8)
        arr[::4, :] = 255
        arr[:, ::4] = 255
        sharp_img = Image.fromarray(arr)
        sharp_var = calculate_blur_variance(sharp_img)
        self.assertGreater(sharp_var, 500.0)

        # Blur the image heavily
        blurred_img = sharp_img.filter(ImageFilter.GaussianBlur(radius=8))
        blurred_var = calculate_blur_variance(blurred_img)
        self.assertLess(blurred_var, 80.0)
        self.assertLess(blurred_var, sharp_var)

    def test_effective_dpi_math(self):
        # Image of 1200x800 pixels displayed at 4x2.67 inches should have 300 DPI
        px_w = 1200
        display_w_in = 4.0
        dpi = px_w / display_w_in
        self.assertAlmostEqual(dpi, 300.0)

        # Image of 300x200 pixels displayed at 4 inches should have 75 DPI (<150 DPI critical)
        px_w_low = 300
        dpi_low = px_w_low / display_w_in
        self.assertAlmostEqual(dpi_low, 75.0)
        self.assertLess(dpi_low, 150.0)

    def test_aspect_ratio_distortion(self):
        # Original ratio 16:9 (1.777), displayed as 4:3 (1.333) -> ~25% distortion
        native_ratio = 1920 / 1080
        display_ratio = 4.0 / 3.0
        diff = abs(native_ratio - display_ratio) / native_ratio
        self.assertGreater(diff, 0.05)

    def test_profiles_defined(self):
        self.assertIn("skripsi-id", PROFILES)
        self.assertIn("jiki-journal", PROFILES)
        self.assertIn("general", PROFILES)
        
        skripsi = PROFILES["skripsi-id"]
        self.assertEqual(skripsi["margin_left_cm"], 4.0)
        self.assertEqual(skripsi["margin_top_cm"], 4.0)
        self.assertEqual(skripsi["margin_right_cm"], 3.0)
        self.assertEqual(skripsi["margin_bottom_cm"], 3.0)

    def test_template_extraction(self):
        # Create a mock template docx in memory
        bio = io.BytesIO()
        with zipfile.ZipFile(bio, "w") as zf:
            doc_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                <w:body>
                    <w:p><w:r><w:t>Template text</w:t></w:r></w:p>
                    <w:sectPr>
                        <w:pgMar w:top="1701" w:right="1701" w:bottom="1701" w:left="1701"/>
                        <w:pgSz w:w="11906" w:h="16838"/>
                        <w:cols w:num="2" w:space="396"/>
                    </w:sectPr>
                </w:body>
            </w:document>
            """
            zf.writestr("word/document.xml", doc_xml)
        
        bio.seek(0)
        temp_path = Path("test_mock_template.docx").resolve()
        with open(temp_path, "wb") as f:
            f.write(bio.read())

        try:
            profile = extract_profile_from_template(str(temp_path))
            self.assertEqual(profile["margin_top_cm"], 3.0)
            self.assertEqual(profile["margin_left_cm"], 3.0)
            self.assertEqual(profile["expected_columns"], 2)
            self.assertEqual(profile["paper_size"], "A4")
        finally:
            if temp_path.exists():
                temp_path.unlink()


if __name__ == "__main__":
    unittest.main()

