# SPDX-License-Identifier: MIT
from __future__ import annotations

import os
import sys
from pathlib import Path


def _root(start: Path) -> Path:
    env_root = os.environ.get("BRAND_DOCS_ROOT")
    if env_root:
        root = Path(env_root).expanduser().resolve()
        if (root / "scripts" / "brandkit").is_dir():
            return root
        if (root / "brandkit").is_dir():
            return root

    for parent in [start] + list(start.parents):
        if (parent / ".claude-plugin").is_dir():
            return parent
        if (parent / "brandkit").is_dir():
            return parent.parent
        if (parent / "scripts" / "brandkit").is_dir():
            return parent
    return start.parents[3] if len(start.parents) > 3 else start.parent


ROOT = _root(Path(__file__).resolve())
if (ROOT / "scripts").is_dir():
    sys.path.insert(0, str(ROOT / "scripts"))
else:
    sys.path.insert(0, str(ROOT))

from brandkit.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
