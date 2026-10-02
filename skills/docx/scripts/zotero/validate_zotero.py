#!/usr/bin/env python3
"""Validate the integrity of Zotero CSL field codes in a DOCX document.

Usage:
    python validate_zotero.py document.docx
    python validate_zotero.py unpacked/
"""

import argparse
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from office.helpers import safe_extract


def validate_document(doc_path: Path):
    temp_dir = None
    errors = []
    warnings = []
    try:
        if doc_path.is_file():
            temp_dir = tempfile.TemporaryDirectory(prefix="zotero_val_")
            unpacked = Path(temp_dir.name)
            with zipfile.ZipFile(doc_path) as zf:
                safe_extract(zf, unpacked)
            xml_file = unpacked / "word" / "document.xml"
        else:
            xml_file = doc_path / "word" / "document.xml"

        if not xml_file.exists():
            return [f"File {xml_file} does not exist"], []

        xml = xml_file.read_text(encoding="utf-8", errors="surrogateescape")

        # 1. Check Bibliography
        if "ADDIN ZOTERO_BIBL" not in xml:
            warnings.append("No 'ADDIN ZOTERO_BIBL' bibliography block found. Word will need to generate it on first Refresh.")

        # 2. Check CSL_CITATION instances
        citations_found = 0
        start_pos = 0
        while True:
            idx = xml.find("ADDIN ZOTERO_ITEM CSL_CITATION", start_pos)
            if idx == -1:
                break
            citations_found += 1

            # Check for surrounding fldChar begin
            prev_begin = xml.rfind('w:fldCharType="begin"', 0, idx)
            if prev_begin == -1 or idx - prev_begin > 500:
                errors.append(f"Citation #{citations_found}: Missing preceding <w:fldChar w:fldCharType='begin'/>")

            # Check JSON
            brace_start = xml.find("{", idx)
            if brace_start == -1:
                errors.append(f"Citation #{citations_found}: No JSON opening brace found")
                start_pos = idx + len("ADDIN ZOTERO_ITEM CSL_CITATION")
                continue

            # Bracket matching
            depth = 0
            brace_end = -1
            in_str = False
            esc = False
            for i in range(brace_start, min(len(xml), brace_start + 15000)):
                c = xml[i]
                if esc:
                    esc = False
                    continue
                if c == "\\":
                    esc = True
                    continue
                if c == '"':
                    in_str = not in_str
                    continue
                if not in_str:
                    if c == "{":
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0:
                            brace_end = i + 1
                            break

            if brace_end == -1:
                errors.append(f"Citation #{citations_found}: Unbalanced or unclosed JSON payload")
                start_pos = idx + len("ADDIN ZOTERO_ITEM CSL_CITATION")
                continue

            raw_json = xml[brace_start:brace_end]
            # Replace escaped XML entities back to parse JSON
            unescaped_json = raw_json.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            try:
                data = json.loads(unescaped_json)
                if "citationID" not in data:
                    warnings.append(f"Citation #{citations_found}: Missing 'citationID' in payload")
                if "citationItems" not in data or not data["citationItems"]:
                    warnings.append(f"Citation #{citations_found}: Empty 'citationItems'")
            except json.JSONDecodeError as e:
                errors.append(f"Citation #{citations_found}: JSON syntax error: {e}")

            # Check following separate and end
            next_sep = xml.find('w:fldCharType="separate"', brace_end)
            next_end = xml.find('w:fldCharType="end"', brace_end)
            if next_sep == -1 or next_end == -1 or next_sep > next_end:
                errors.append(f"Citation #{citations_found}: Missing or disordered 'separate'/'end' fldChar")

            start_pos = brace_end

        return errors, warnings, citations_found
    finally:
        if temp_dir:
            temp_dir.cleanup()


def main():
    parser = argparse.ArgumentParser(description="Validate Zotero CSL field codes in DOCX")
    parser.add_argument("document", type=Path, help="DOCX file or unpacked directory")
    args = parser.parse_args()

    if not args.document.exists():
        print(f"Error: {args.document} not found", file=sys.stderr)
        sys.exit(1)

    errors, warnings, total_cites = validate_document(args.document)

    print("=" * 60)
    print(" ZOTERO XML INTEGRITY VALIDATION")
    print("=" * 60)
    print(f"Document : {args.document}")
    print(f"Citations: {total_cites} detected")

    if warnings:
        print("\n[!] WARNINGS:")
        for w in warnings:
            print(f"  - {w}")

    if errors:
        print("\n[X] ERRORS FOUND:")
        for e in errors:
            print(f"  - {e}")
        print("\nResult: [FAIL] FAILED")
        sys.exit(1)
    else:
        print("\nResult: [PASS] PASSED - All Zotero CSL field codes are intact and valid.")
        sys.exit(0)


if __name__ == "__main__":
    main()
