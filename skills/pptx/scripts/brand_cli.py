# SPDX-License-Identifier: MIT
"""Alias launcher for brandkit within pptx skill."""
from __future__ import annotations

import sys
from pathlib import Path

# Add current scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from brandkit.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
