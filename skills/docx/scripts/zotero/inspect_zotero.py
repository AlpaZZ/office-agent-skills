#!/usr/bin/env python3
"""Inspect and extract Zotero CSL field codes from a DOCX document.

Accepts either an unpacked directory OR a .docx/.dotx file directly.

Usage:
    python inspect_zotero.py document.docx
    python inspect_zotero.py unpacked/
    python inspect_zotero.py document.docx --json
    python inspect_zotero.py document.docx --export-bib library.bib
"""

import argparse
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

# Add parent directories to sys.path to import office.helpers if needed
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from office.helpers import safe_extract

CSL_ITEM_PATTERN = re.compile(
    r"ADDIN\s+ZOTERO_ITEM\s+CSL_CITATION\s+(\{.*?\})(?=\s*ADDIN|\s*</w:instrText>|\s*$)",
    re.DOTALL,
)
CSL_BIBL_PATTERN = re.compile(
    r"ADDIN\s+ZOTERO_BIBL\s+(?:\{.*?\})?\s*CSL_BIBLIOGRAPHY",
    re.DOTALL,
)


def extract_zotero_fields_from_xml(xml_content: str):
    citations = []
    has_bibliography = bool(CSL_BIBL_PATTERN.search(xml_content))

    # Match all CSL_CITATION json blobs
    matches = list(re.finditer(r"ADDIN\s+ZOTERO_ITEM\s+CSL_CITATION\s+({.+?})(?=\s*</w:instrText>|\s*$|\s*ADDIN)", xml_content, re.DOTALL))
    
    # If the above greedy/non-greedy misses complex nested braces, balance braces:
    start_pos = 0
    while True:
        idx = xml_content.find("ADDIN ZOTERO_ITEM CSL_CITATION", start_pos)
        if idx == -1:
            break
        # Find opening brace
        brace_start = xml_content.find("{", idx)
        if brace_start == -1:
            start_pos = idx + len("ADDIN ZOTERO_ITEM CSL_CITATION")
            continue
        
        # Count braces to find matching closing brace
        depth = 0
        brace_end = -1
        in_string = False
        escape = False
        for i in range(brace_start, len(xml_content)):
            char = xml_content[i]
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string:
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        brace_end = i + 1
                        break
        
        if brace_end != -1:
            raw_json = xml_content[brace_start:brace_end]
            try:
                data = json.loads(raw_json)
                citations.append(data)
            except json.JSONDecodeError:
                # Store raw if failed
                citations.append({"raw": raw_json, "error": "Invalid JSON"})
            start_pos = brace_end
        else:
            start_pos = idx + len("ADDIN ZOTERO_ITEM CSL_CITATION")

    return citations, has_bibliography


def inspect_document(doc_path: Path):
    temp_dir = None
    try:
        if doc_path.is_file():
            temp_dir = tempfile.TemporaryDirectory(prefix="zotero_inspect_")
            unpacked = Path(temp_dir.name)
            with zipfile.ZipFile(doc_path) as zf:
                safe_extract(zf, unpacked)
            xml_file = unpacked / "word" / "document.xml"
        else:
            xml_file = doc_path / "word" / "document.xml"

        if not xml_file.exists():
            print(f"Error: {xml_file} not found.", file=sys.stderr)
            return [], False

        xml_content = xml_file.read_text(encoding="utf-8", errors="surrogateescape")
        return extract_zotero_fields_from_xml(xml_content)
    finally:
        if temp_dir:
            temp_dir.cleanup()


def format_author_list(authors):
    if not authors:
        return "Unknown"
    names = []
    for a in authors:
        if isinstance(a, dict):
            if "family" in a and "given" in a:
                names.append(f"{a['given']} {a['family']}")
            elif "family" in a:
                names.append(a["family"])
            elif "literal" in a:
                names.append(a["literal"])
        elif isinstance(a, str):
            names.append(a)
    return ", ".join(names) if names else "Unknown"


def main():
    parser = argparse.ArgumentParser(description="Inspect Zotero CSL field codes in DOCX")
    parser.add_argument("document", type=Path, help="Path to .docx file or unpacked directory")
    parser.add_argument("--json", action="store_true", help="Output raw citation metadata as JSON")
    parser.add_argument("--export-bib", type=Path, help="Export parsed items to a BibTeX .bib file")

    args = parser.parse_args()

    if not args.document.exists():
        print(f"Error: Path {args.document} does not exist", file=sys.stderr)
        sys.exit(1)

    citations, has_bib = inspect_document(args.document)

    if args.json:
        output = {
            "total_citations": len(citations),
            "has_zotero_bibliography": has_bib,
            "citations": citations,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return

    print("=" * 60)
    print(" ZOTERO CSL CITATION INSPECTION REPORT")
    print("=" * 60)
    print(f"Target: {args.document}")
    print(f"Total In-Text Citations Found: {len(citations)}")
    print(f"Zotero Bibliography Field Detected: {'[YES]' if has_bib else '[NO]'}")
    print("-" * 60)

    for idx, cite in enumerate(citations, 1):
        cid = cite.get("citationID", f"cite_{idx}")
        props = cite.get("properties", {})
        formatted = props.get("formattedCitation", props.get("plainCitation", "[?]"))
        items = cite.get("citationItems", [])

        print(f"\n[{idx}] In-Text: {formatted}  (ID: {cid})")
        for citem in items:
            item_data = citem.get("itemData", {})
            title = item_data.get("title", "No Title")
            authors = format_author_list(item_data.get("author", []))
            year = "N/A"
            date_parts = item_data.get("issued", {}).get("date-parts", [])
            if date_parts and len(date_parts[0]) > 0:
                year = date_parts[0][0]
            doi = item_data.get("DOI", "N/A")
            container = item_data.get("container-title", "N/A")

            print(f"    - Title   : {title}")
            print(f"    - Authors : {authors}")
            print(f"    - Year    : {year} | Venue: {container}")
            if doi != "N/A":
                print(f"    - DOI     : {doi}")

    print("\n" + "=" * 60)

    if args.export_bib:
        exported_count = 0
        with open(args.export_bib, "w", encoding="utf-8") as bf:
            seen_keys = set()
            for cite in citations:
                for citem in cite.get("citationItems", []):
                    item = citem.get("itemData", {})
                    if not item:
                        continue
                    cite_id = item.get("id") or item.get("key") or f"item_{exported_count + 1}"
                    # Make cite key safe
                    key = re.sub(r"[^a-zA-Z0-9_]", "", str(cite_id))
                    if not key or key in seen_keys:
                        authors = item.get("author", [])
                        first_author = authors[0].get("family", "cite") if authors and isinstance(authors[0], dict) else "cite"
                        year = item.get("issued", {}).get("date-parts", [[2024]])[0][0]
                        key = f"{first_author.lower()}{year}_{exported_count + 1}"
                    seen_keys.add(key)

                    item_type = item.get("type", "article-journal")
                    bib_type = "article" if "journal" in item_type else "inproceedings" if "conference" in item_type else "misc"
                    title = item.get("title", "")
                    author_str = " and ".join(
                        f"{a.get('family', '')}, {a.get('given', '')}" for a in item.get("author", []) if isinstance(a, dict)
                    )
                    year = item.get("issued", {}).get("date-parts", [[""]])[0][0]

                    bf.write(f"@{bib_type}{{{key},\n")
                    if title:
                        bf.write(f'  title = "{title}",\n')
                    if author_str:
                        bf.write(f'  author = "{author_str}",\n')
                    if year:
                        bf.write(f'  year = "{year}",\n')
                    if "container-title" in item:
                        bf.write(f'  booktitle = "{item["container-title"]}",\n')
                    if "DOI" in item:
                        bf.write(f'  doi = "{item["DOI"]}",\n')
                    bf.write("}\n\n")
                    exported_count += 1
        print(f"Exported {exported_count} reference(s) to {args.export_bib}")


if __name__ == "__main__":
    main()
