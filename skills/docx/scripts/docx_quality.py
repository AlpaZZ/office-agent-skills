"""Deterministic DOCX quality checks for the final pre-delivery gate."""
from __future__ import annotations
import argparse, hashlib, json, shutil, subprocess, tempfile, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"w": W, "a": A}

def tag(name): return f"{{{W}}}{name}"
def text(el): return " ".join((el.itertext() if el is not None else []))
def xml(z, name):
    try: return ET.fromstring(z.read(name))
    except KeyError: return None

def parts(path):
    with zipfile.ZipFile(path) as z: return {n: z.read(n) for n in z.namelist()}

def fields(root):
    out = []
    for e in root.iter():
        if e.tag in (tag("instrText"), tag("fldSimple")):
            value = e.text if e.tag == tag("instrText") else e.attrib.get(tag("instr"), "")
            if value: out.append(value.strip())
    return out

def body_paragraphs(root):
    return root.findall(f".//{tag('body')}/{tag('p')}") if root is not None else []

def audit(path):
    data = parts(path)
    root = ET.fromstring(data["word/document.xml"])
    styles = ET.fromstring(data["word/styles.xml"]) if "word/styles.xml" in data else None
    settings = ET.fromstring(data["word/settings.xml"]) if "word/settings.xml" in data else None
    body = body_paragraphs(root)
    findings = []
    def add(level, check, message): findings.append({"level": level, "check": check, "message": message})

    # Structure and page-flow checks.
    headings = []
    for p in body:
        ps = p.find(f".//{tag('pStyle')}")
        if ps is not None and ps.attrib.get(tag("val"), "").lower().startswith("heading"):
            headings.append(p)
    for i, p in enumerate(headings):
        ppr = p.find(tag("pPr")); style = p.find(f".//{tag('pStyle')}").attrib.get(tag("val"), "")
        if ppr is None or ppr.find(tag("keepNext")) is None:
            add("WARN", "heading-flow", f"{style} belum memiliki keep-with-next: {text(p).strip()[:80]}")
        if ppr is None or ppr.find(tag("keepLines")) is None:
            add("WARN", "heading-flow", f"{style} belum memiliki keep-lines: {text(p).strip()[:80]}")
        if i and style.lower().endswith("1") and p.find(f".//{tag('pageBreakBefore')}") is None:
            add("INFO", "heading-flow", f"{style} tidak memakai page-break-before; cek apakah bab perlu halaman baru")
    for p in body:
        if p.find(f".//{tag('pageBreakBefore')}") is not None and not text(p).strip():
            add("WARN", "page-break", "Page break berada di paragraf kosong; gunakan pageBreakBefore pada heading.")

    # Fields, references, captions, TOC.
    all_fields = fields(root)
    refs = [f for f in all_fields if f.upper().startswith(("REF ", "PAGEREF ", "NOTEREF "))]
    bad_refs = [f for f in refs if "#REF!" in f.upper() or "ERROR" in f.upper()]
    if bad_refs: add("FAIL", "cross-reference", f"{len(bad_refs)} cross-reference rusak: {bad_refs[:3]}")
    if refs and not any("TOC" in f.upper() for f in all_fields): add("INFO", "cross-reference", "Ada cross-reference tetapi tidak ada field TOC; pastikan navigasi memang diperlukan.")
    if any("TOC" in f.upper() for f in all_fields) and not settings: add("FAIL", "fields", "TOC ditemukan tetapi settings.xml tidak tersedia.")
    seq = [f for f in all_fields if "SEQ " in f.upper()]
    if any("TOC" in f.upper() for f in all_fields) and not seq: add("WARN", "captions", "TOC ada, tetapi tidak ada field SEQ untuk caption.")

    # Accessibility.
    drawings = root.findall(f".//{{{A}}}docPr")
    missing_alt = [d.attrib.get("id", "?") for d in drawings if not (d.attrib.get("descr") or d.attrib.get("title"))]
    if missing_alt: add("FAIL", "accessibility", f"{len(missing_alt)} gambar tidak memiliki alt text/title.")
    tables = root.findall(f".//{tag('tbl')}")
    for n, table in enumerate(tables, 1):
        rows = table.findall(tag("tr"))
        if not rows: continue
        first = rows[0]
        if first.find(f".//{tag('tblHeader')}") is None:
            add("WARN", "table-accessibility", f"Tabel {n} tidak menandai baris header sebagai repeat/header row.")
        if not any(text(cell).strip() for cell in first.findall(tag("tc"))): add("FAIL", "table-quality", f"Tabel {n} memiliki header kosong.")
        for row in rows:
            if row.find(tag("cantSplit")) is None: add("INFO", "table-quality", f"Tabel {n} memiliki baris yang boleh terbelah antar halaman.")
            break
    core = data.get("docProps/core.xml", b"")
    if not core: add("WARN", "accessibility", "core properties tidak ditemukan; isi title/author/language bila dokumen dibagikan.")

    # Style hygiene: direct font overrides and unused custom styles.
    direct_fonts = len(root.findall(f".//{tag('rPr')}/{tag('rFonts')}"))
    if direct_fonts > max(10, len(body) // 2): add("WARN", "style-hygiene", f"Terlalu banyak font langsung ({direct_fonts}); pindahkan aturan ke Styles.")
    used = {e.attrib.get(tag("val")) for e in root.findall(f".//{tag('pStyle')}")}
    defined = {e.attrib.get(tag("styleId")) for e in styles.findall(f".//{tag('style')}")} if styles is not None else set()
    unused = sorted(x for x in defined if x and not x.startswith(("Heading", "Normal", "DefaultParagraphFont", "Table")) and x not in used)
    if unused: add("INFO", "style-hygiene", f"Style tidak terpakai: {', '.join(unused[:12])}")

    # Notes and headers/footers/page number.
    foot = data.get("word/footnotes.xml", b"")
    end = data.get("word/endnotes.xml", b"")
    note_refs = len(root.findall(f".//{tag('footnoteReference')}")) + len(root.findall(f".//{tag('endnoteReference')}"))
    note_defs = (foot.count(b"<w:footnote ") + end.count(b"<w:endnote "))
    if note_refs and note_defs < note_refs: add("FAIL", "notes", f"Referensi footnote/endnote ({note_refs}) melebihi definisi ({note_defs}).")
    hf = [n for n in data if n.startswith("word/header") or n.startswith("word/footer")]
    hf_fields = sum(1 for n in hf for f in fields(ET.fromstring(data[n])) if "PAGE" in f.upper())
    if hf and not hf_fields: add("WARN", "header-footer", "Header/footer ada tetapi field PAGE tidak ditemukan.")

    result = {"file": str(path), "summary": {"fail": sum(x["level"] == "FAIL" for x in findings), "warn": sum(x["level"] == "WARN" for x in findings), "info": sum(x["level"] == "INFO" for x in findings)}, "findings": findings}
    return result

def template_diff(doc, template):
    a, b = parts(doc), parts(template); keys = sorted(set(a) | set(b)); diffs=[]
    for k in keys:
        if k in {"docProps/core.xml", "docProps/app.xml"}: continue
        if hashlib.sha256(a.get(k,b"")).digest() != hashlib.sha256(b.get(k,b"")).digest(): diffs.append(k)
    return {"document": str(doc), "template": str(template), "changed_parts": diffs, "changed_count": len(diffs)}

def enable_field_updates(path, output=None):
    output = Path(output or path); tmp = output.with_suffix(output.suffix + ".tmp")
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            raw = zin.read(item.filename)
            if item.filename == "word/settings.xml":
                root = ET.fromstring(raw); node = root.find(tag("updateFields"))
                if node is None: ET.SubElement(root, tag("updateFields"), {tag("val"): "true"})
                else: node.set(tag("val"), "true")
                raw = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            zout.writestr(item, raw)
    shutil.move(tmp, output); return output

def render_check(path, out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice: return {"ok": False, "message": "soffice/libreoffice tidak ditemukan"}
    with tempfile.TemporaryDirectory() as td:
        p = subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", td, str(path)], capture_output=True, text=True)
        pdf = Path(td) / (Path(path).stem + ".pdf")
        if p.returncode or not pdf.exists(): return {"ok": False, "message": (p.stderr or p.stdout).strip()}
        target = out / pdf.name; shutil.copy2(pdf, target)
        return {"ok": True, "pdf": str(target), "pdf_bytes": pdf.stat().st_size}

def main():
    ap = argparse.ArgumentParser(description="DOCX quality gate")
    ap.add_argument("docx"); ap.add_argument("--template"); ap.add_argument("--fix-fields", action="store_true"); ap.add_argument("--output"); ap.add_argument("--render-dir"); ap.add_argument("--format", choices=("text","json"), default="text")
    args = ap.parse_args(); path = Path(args.docx)
    report = {"quality": audit(path)}
    if args.template: report["template_diff"] = template_diff(path, Path(args.template))
    if args.fix_fields: report["field_update_output"] = str(enable_field_updates(path))
    if args.render_dir: report["visual_render"] = render_check(path, args.render_dir)
    if args.format == "json": output = json.dumps(report, indent=2, ensure_ascii=False)
    else:
        q = report["quality"]; s = q["summary"]; lines = [f"DOCX quality gate: {path}", f"FAIL={s['fail']} WARN={s['warn']} INFO={s['info']}"]
        lines += [f"[{x['level']}] {x['check']}: {x['message']}" for x in q["findings"]]
        if "template_diff" in report: lines.append(f"Template changed parts: {report['template_diff']['changed_count']}")
        if "visual_render" in report: lines.append(f"Visual render: {report['visual_render']}")
        output = "\n".join(lines)
    if args.output: Path(args.output).write_text(output, encoding="utf-8")
    else: print(output)
    raise SystemExit(1 if report["quality"]["summary"]["fail"] else 0)

if __name__ == "__main__": main()

