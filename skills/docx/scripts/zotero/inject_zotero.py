#!/usr/bin/env python3
"""Inject a native Zotero CSL field code into a DOCX document.

Accepts either an unpacked directory OR a .docx/.dotx file directly.

Usage:
    python inject_zotero.py document.docx --after "some anchor text" \\
        --citation-text "[39]" \\
        --title "Searching for MobileNetV3" \\
        --authors "Howard, Andrew; Sandler, Mark; Chu, Grace" \\
        --year 2019 \\
        --venue "ICCV" \\
        --doi "10.1109/ICCV.2019.00140" \\
        -o output.docx

    # Or provide a pre-built CSL itemData JSON file:
    python inject_zotero.py document.docx --after "some anchor text" \\
        --citation-text "[39]" \\
        --csl-json item.json \\
        -o output.docx
"""

import argparse
import json
import random
import re
import string
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path

# Add parent directory to sys.path to import office.helpers
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from office.helpers import rezip, safe_extract


def generate_citation_id(title="cite"):
    slug = re.sub(r"[^a-zA-Z0-9]", "", title.lower())[:15] or "cite"
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"zotero_{slug}_{rand}"


def build_csl_payload(citation_id, citation_text, title, authors, year, venue="", doi="", item_type="paper-conference"):
    author_list = []
    if authors:
        # Expected format: "Family, Given; Family2, Given2" or "Given Family; Given2 Family2"
        for entry in authors.split(";"):
            entry = entry.strip()
            if not entry:
                continue
            if "," in entry:
                fam, given = entry.split(",", 1)
                author_list.append({"family": fam.strip(), "given": given.strip()})
            else:
                parts = entry.split()
                if len(parts) > 1:
                    author_list.append({"family": parts[-1], "given": " ".join(parts[:-1])})
                else:
                    author_list.append({"family": entry})

    issued = {"date-parts": [[int(year)]]} if year and str(year).isdigit() else {"date-parts": [[year]]}

    item_data = {
        "id": random.randint(100, 999999),
        "type": item_type,
        "title": title,
        "author": author_list,
        "issued": issued,
    }
    if venue:
        item_data["container-title"] = venue
    if doi:
        item_data["DOI"] = doi

    payload = {
        "citationID": citation_id,
        "properties": {
            "formattedCitation": citation_text,
            "plainCitation": citation_text,
            "dontUpdate": False,
        },
        "citationItems": [
            {
                "id": item_data["id"],
                "uris": [f"http://zotero.org/users/local/{uuid.uuid4().hex[:8]}/items/{uuid.uuid4().hex[:8].upper()}"],
                "itemData": item_data,
            }
        ],
        "schema": "https://github.com/citation-style-language/schema/raw/master/csl-citation.json",
    }
    return payload


def format_zotero_xml_field(payload, citation_text):
    payload_json = json.dumps(payload, ensure_ascii=False)
    # XML-escape any & or < in the JSON
    escaped_json = payload_json.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    xml_snippet = (
        f'<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        f'<w:r><w:instrText xml:space="preserve"> ADDIN ZOTERO_ITEM CSL_CITATION {escaped_json} </w:instrText></w:r>'
        f'<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        f'<w:r><w:t>{citation_text}</w:t></w:r>'
        f'<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    )
    return xml_snippet


def inject_into_document_xml(xml_content: str, anchor_text: str, xml_snippet: str, position: str = "after"):
    # First coalesce Fragmented Runs or search for the anchor in <w:t>
    # If exact anchor exists in a <w:t>...</w:t>
    escaped_anchor = re.escape(anchor_text)
    pattern = re.compile(rf"(<w:t[^>]*>.*?{escaped_anchor}.*?</w:t>)", re.DOTALL)

    match = pattern.search(xml_content)
    if not match:
        # Fallback: search without tags
        simple_idx = xml_content.find(anchor_text)
        if simple_idx == -1:
            raise ValueError(f"Anchor text '{anchor_text}' not found in document.xml.")
        # Find closing </w:r> or </w:p>
        if position == "after":
            insert_pos = xml_content.find("</w:r>", simple_idx)
            if insert_pos != -1:
                insert_pos += len("</w:r>")
            else:
                insert_pos = simple_idx + len(anchor_text)
        else:
            insert_pos = xml_content.rfind("<w:r", 0, simple_idx)
            if insert_pos == -1:
                insert_pos = simple_idx
        return xml_content[:insert_pos] + xml_snippet + xml_content[insert_pos:]

    # Found within run tag
    matched_run = match.group(1)
    full_run_pattern = re.compile(rf"(<w:r\b[^>]*>.*?{escaped_anchor}.*?</w:r>)", re.DOTALL)
    run_match = full_run_pattern.search(xml_content)

    if run_match:
        span_start, span_end = run_match.span()
        if position == "after":
            return xml_content[:span_end] + xml_snippet + xml_content[span_end:]
        else:
            return xml_content[:span_start] + xml_snippet + xml_content[span_start:]
    else:
        # Insert right after the <w:t> match
        span_start, span_end = match.span()
        if position == "after":
            return xml_content[:span_end] + xml_snippet + xml_content[span_end:]
        else:
            return xml_content[:span_start] + xml_snippet + xml_content[span_start:]


def main():
    parser = argparse.ArgumentParser(description="Inject native Zotero CSL field codes into DOCX")
    parser.add_argument("document", type=Path, help="Input DOCX file or unpacked directory")
    parser.add_argument("--after", type=str, help="Insert citation immediately after this anchor text")
    parser.add_argument("--before", type=str, help="Insert citation immediately before this anchor text")
    parser.add_argument("--citation-text", type=str, default="[1]", help="Formatted in-text citation, e.g. '[39]' or '(Howard et al., 2019)'")
    parser.add_argument("--title", type=str, default="", help="Publication title")
    parser.add_argument("--authors", type=str, default="", help="Authors separated by semicolon (e.g. 'Howard, Andrew; Sandler, Mark')")
    parser.add_argument("--year", type=str, default="2024", help="Year of publication")
    parser.add_argument("--venue", type=str, default="", help="Journal, conference, or book title")
    parser.add_argument("--doi", type=str, default="", help="Digital Object Identifier (DOI)")
    parser.add_argument("--type", type=str, default="article-journal", help="CSL item type (e.g. article-journal, paper-conference, book)")
    parser.add_argument("--csl-json", type=Path, help="Path to custom CSL citation JSON file")
    parser.add_argument("-o", "--output", type=Path, help="Output DOCX path (required if input is a .docx file)")

    args = parser.parse_args()

    if not args.after and not args.before:
        print("Error: Either --after or --before anchor text is required.", file=sys.stderr)
        sys.exit(1)

    anchor = args.after if args.after else args.before
    position = "after" if args.after else "before"

    if args.csl_json and args.csl_json.exists():
        with open(args.csl_json, "r", encoding="utf-8") as f:
            payload = json.load(f)
    else:
        cid = generate_citation_id(args.title or "cite")
        payload = build_csl_payload(
            citation_id=cid,
            citation_text=args.citation_text,
            title=args.title or "Untitled Publication",
            authors=args.authors,
            year=args.year,
            venue=args.venue,
            doi=args.doi,
            item_type=args.type,
        )

    xml_snippet = format_zotero_xml_field(payload, args.citation_text)

    is_file = args.document.is_file()
    if is_file and not args.output:
        print("Error: -o / --output path is required when input is a .docx file.", file=sys.stderr)
        sys.exit(1)

    temp_dir = None
    try:
        if is_file:
            temp_dir = tempfile.TemporaryDirectory(prefix="zotero_inject_")
            unpacked = Path(temp_dir.name)
            with zipfile.ZipFile(args.document) as zf:
                safe_extract(zf, unpacked)
            xml_file = unpacked / "word" / "document.xml"
        else:
            unpacked = args.document
            xml_file = unpacked / "word" / "document.xml"

        if not xml_file.exists():
            print(f"Error: {xml_file} not found.", file=sys.stderr)
            sys.exit(1)

        xml_content = xml_file.read_text(encoding="utf-8", errors="surrogateescape")
        new_xml = inject_into_document_xml(xml_content, anchor, xml_snippet, position=position)
        xml_file.write_text(new_xml, encoding="utf-8", errors="surrogateescape")

        if is_file:
            rezip(unpacked, args.output)
            print(f"Successfully injected Zotero citation '{args.citation_text}' into {args.output}")
        else:
            print(f"Successfully injected Zotero citation '{args.citation_text}' into {unpacked}")

    finally:
        if temp_dir:
            temp_dir.cleanup()


if __name__ == "__main__":
    main()
