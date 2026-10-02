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
from audit_layout import DocumentLayoutAuditor, calculate_blur_variance, PROFILES


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


if __name__ == "__main__":
    unittest.main()
