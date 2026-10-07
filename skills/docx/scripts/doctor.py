"""Check optional tools required by the Office skills."""
from __future__ import annotations
import importlib.util
import shutil
import sys

TOOLS = ("soffice", "libreoffice", "pandoc", "pdftoppm", "node")
MODULES = ("docx", "fitz", "lxml", "PIL", "numpy", "pandas", "pypandoc")

def main() -> int:
    print("Office skills doctor")
    missing = []
    for tool in TOOLS:
        found = shutil.which(tool)
        print(f"{'PASS' if found else 'WARN'} tool {tool}: {found or 'not found'}")
    for module in MODULES:
        ok = importlib.util.find_spec(module) is not None
        print(f"{'PASS' if ok else 'WARN'} python {module}: {'installed' if ok else 'not installed'}")
        if not ok: missing.append(module)
    try:
        import win32com.client  # type: ignore
        print("PASS Word COM: available")
    except Exception:
        print("INFO Word COM: unavailable (visual QA will use LibreOffice)")
    print(f"Python: {sys.version.split()[0]}")
    return 0 if not missing else 1

if __name__ == "__main__":
    raise SystemExit(main())
