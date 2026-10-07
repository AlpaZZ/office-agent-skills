"""Render a DOCX through Microsoft Word when Word COM is available."""
from __future__ import annotations
import argparse
from pathlib import Path

def main() -> int:
    ap = argparse.ArgumentParser(description="Microsoft Word visual QA")
    ap.add_argument("docx")
    ap.add_argument("--pdf", required=True)
    args = ap.parse_args()
    try:
        import win32com.client  # type: ignore
    except Exception:
        print("Word COM is unavailable; run docx_quality.py --render-dir for LibreOffice fallback.")
        return 2
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    doc = None
    try:
        doc = word.Documents.Open(str(Path(args.docx).resolve()), ReadOnly=True, AddToRecentFiles=False)
        doc.Repaginate()
        pages = int(doc.ComputeStatistics(2))
        out = Path(args.pdf).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.ExportAsFixedFormat(str(out), 17)
        print(f"PASS Word render: {out} ({pages} pages)")
        return 0
    finally:
        if doc is not None: doc.Close(False)
        word.Quit()

if __name__ == "__main__":
    raise SystemExit(main())
