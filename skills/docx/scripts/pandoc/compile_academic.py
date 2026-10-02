#!/usr/bin/env python3
"""Compile Markdown with LaTeX Math and Zotero/BibTeX citations to native Word (.docx).

Usage:
    python compile_academic.py draft.md -o paper.docx
    python compile_academic.py draft.md -o paper.docx --bibliography references.bib --csl ieee.csl
    python compile_academic.py draft.md -o paper.docx --reference-doc template.docx
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_default_bibliography(start_dir: Path) -> Path | None:
    candidates = ["references.bib", "references.json", "library.bib", "zotero.bib"]
    for curr in [start_dir] + list(start_dir.parents):
        for name in candidates:
            p = curr / name
            if p.is_file():
                return p
    return None


def compile_markdown_to_docx(
    input_md: Path,
    output_docx: Path,
    reference_doc: Path | None = None,
    bibliography: Path | None = None,
    csl: Path | None = None,
    toc: bool = False,
):
    pandoc_cmd = shutil.which("pandoc")
    if not pandoc_cmd:
        # Check python Scripts or pypandoc
        script_pandoc = Path(sys.executable).parent / "Scripts" / "pandoc.exe"
        if script_pandoc.exists():
            pandoc_cmd = str(script_pandoc)
        else:
            try:
                import pypandoc
                pandoc_cmd = pypandoc.get_pandoc_path()
                if not Path(pandoc_cmd).suffix and os.name == "nt":
                    pandoc_cmd += ".exe"
            except Exception:
                pass

    if not pandoc_cmd or not Path(pandoc_cmd).exists():
        raise RuntimeError("Pandoc binary not found. Please ensure pandoc is installed and on PATH.")

    cmd = [
        str(pandoc_cmd),
        str(input_md),
        "-o",
        str(output_docx),
        "--from",
        "markdown+tex_math_dollars+raw_tex+citations",
    ]

    if toc:
        cmd.append("--toc")

    if reference_doc and reference_doc.exists():
        cmd.extend(["--reference-doc", str(reference_doc)])

    bib_path = bibliography or find_default_bibliography(input_md.parent)
    if bib_path and bib_path.exists():
        cmd.extend(["--citeproc", f"--bibliography={bib_path}"])
        if csl and csl.exists():
            cmd.extend([f"--csl={csl}"])
        print(f"[*] Applied Bibliography: {bib_path}")
        if csl:
            print(f"[*] Applied CSL Style: {csl}")

    print(f"[*] Compiling {input_md} -> {output_docx} via Pandoc...")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"[X] Pandoc compilation error:\n{proc.stderr}", file=sys.stderr)
        sys.exit(proc.returncode)

    print(f"[+] Success! Native Word document generated: {output_docx}")
    print("    - LaTeX math formulas ($...$ and $$...$$) converted to native Word OMML Equations.")
    if bib_path:
        print("    - Citations resolved and Bibliography generated.")


def main():
    parser = argparse.ArgumentParser(description="Compile Markdown + Math + Citations to DOCX")
    parser.add_argument("input", type=Path, help="Input markdown file (.md)")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Output .docx file")
    parser.add_argument("--reference-doc", type=Path, help="Reference template .docx for styles")
    parser.add_argument("--bibliography", type=Path, help="Path to .bib or .json bibliography file")
    parser.add_argument("--csl", type=Path, help="Path to Citation Style Language (.csl) file")
    parser.add_argument("--toc", action="store_true", help="Generate Table of Contents")

    args = parser.parse_args()

    if not args.input.exists():
        print(f"Error: Input file {args.input} does not exist.", file=sys.stderr)
        sys.exit(1)

    compile_markdown_to_docx(
        input_md=args.input,
        output_docx=args.output,
        reference_doc=args.reference_doc,
        bibliography=args.bibliography,
        csl=args.csl,
        toc=args.toc,
    )


if __name__ == "__main__":
    main()
