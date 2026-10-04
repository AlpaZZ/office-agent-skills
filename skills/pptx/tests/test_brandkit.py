# SPDX-License-Identifier: MIT
import subprocess
import sys
import unittest
from pathlib import Path


class TestPptxBrandkitIntegration(unittest.TestCase):
    def setUp(self):
        self.pptx_dir = Path(__file__).resolve().parents[1]
        self.cli_py = self.pptx_dir / "scripts" / "cli.py"
        self.brand_cli_py = self.pptx_dir / "scripts" / "brand_cli.py"

    def test_cli_exists(self):
        self.assertTrue(self.cli_py.exists(), f"Missing {self.cli_py}")
        self.assertTrue(self.brand_cli_py.exists(), f"Missing {self.brand_cli_py}")

    def test_cli_doctor(self):
        res = subprocess.run(
            [sys.executable, str(self.cli_py), "doctor"],
            capture_output=True,
            text=True,
            cwd=str(self.pptx_dir)
        )
        self.assertEqual(res.returncode, 0, f"Doctor failed: {res.stderr}")
        self.assertIn("python:pptx: ok", res.stdout)
        self.assertIn("python:lxml: ok", res.stdout)


if __name__ == "__main__":
    unittest.main()
