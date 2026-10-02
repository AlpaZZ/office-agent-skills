#!/usr/bin/env python3
"""audit_manuscript.py - Pre-review empirical auditor for academic manuscripts & theses.

Scans Word documents (.docx), Markdown (.md), LaTeX (.tex), and plain text to extract:
1. Candidate empirical claims (causal, comparative, and superiority assertions).
2. Reported metrics and numbers (flagging metrics reported without variance/seeds).
3. Data leakage red flags (checking patient-level grouping in clinical/imaging datasets).
4. Class imbalance and metric adequacy red flags.

Outputs a structured pre-review audit report to guide the research-reviewer agent.
"""

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Linguistic triggers for empirical claims
CAUSAL_CLAIM_PATTERNS = [
    re.compile(r"\b(?:outperforms?|improves?|increases?|enhances?|boosts?)\b.*?\bby\s+([0-9\.]+%)", re.IGNORECASE),
    re.compile(r"\b(?:achieves?|obtained|reached)\b.*?\b(?:accuracy|f1|auc|score)\b.*?\bof\s+([0-9\.]+%)", re.IGNORECASE),
    re.compile(r"\b(?:superior to|better than|outperforms)\b.*?\b(?:baseline|prior|existing|sota|state-of-the-art)\b", re.IGNORECASE),
    re.compile(r"\b(?:proves?|demonstrates conclusively|undeniably proves)\b", re.IGNORECASE),
    re.compile(r"\bsignificantly\s+(?:improves?|outperforms?|reduces?|increases?)\b", re.IGNORECASE),
    re.compile(r"\bnovel\s+(?:architecture|method|approach|framework)\b", re.IGNORECASE),
]

METRIC_PATTERNS = [
    re.compile(r"\b([0-9]{1,3}\.[0-9]{1,3})\s*(?:%|percent)\b", re.IGNORECASE),
    re.compile(r"\b(?:AUC|F1|Accuracy|Sensitivity|Specificity|Precision|Recall)\s*[:=]\s*([0-9\.]+)", re.IGNORECASE),
]

VARIANCE_PATTERNS = [
    re.compile(r"[±\+\/\-]\s*[0-9\.]+", re.IGNORECASE),
    re.compile(r"\b(?:std|std dev|standard deviation|confidence interval|95%\s*CI)\b", re.IGNORECASE),
]

MEDICAL_IMAGING_KEYWORDS = [
    "fundus", "retina", "retinopathy", "chest", "x-ray", "radiograph",
    "ct scan", "mri", "dermoscopy", "skin lesion", "histopathology",
    "patient", "clinical", "hospital", "ultrasound", "biopsy"
]

PATIENT_GROUPING_KEYWORDS = [
    "patient_id", "patient id", "subject_id", "subject id", "groupkfold",
    "stratifiedgroupkfold", "patient-level", "subject-level", "per-patient"
]


def extract_text_from_docx(doc_path: Path) -> str:
    """Extract plain text from word/document.xml, footnotes, and tables."""
    texts = []
    if not zipfile.is_zipfile(doc_path):
        return ""
    with zipfile.ZipFile(doc_path, "r") as zf:
        for name in zf.namelist():
            if name.startswith("word/") and name.endswith(".xml"):
                try:
                    content = zf.read(name).decode("utf-8", errors="replace")
                    extracted = re.findall(r"<w:t(?:[^>]*)>([^<]+)</w:t>", content)
                    if extracted:
                        texts.append(" ".join(extracted))
                except Exception:
                    pass
    return "\n".join(texts)


def extract_sentences(text: str) -> List[str]:
    """Split text into reasonably clean sentences."""
    cleaned = re.sub(r"\s+", " ", text)
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", cleaned)
    return [s.strip() for s in sentences if len(s.strip()) > 15]


def audit_manuscript(text: str, filename: str = "manuscript") -> Dict[str, Any]:
    """Perform pre-review audit across claims, metrics, variance, and leakage."""
    sentences = extract_sentences(text)
    lower_text = text.lower()

    # 1. Claim Detection
    candidate_claims = []
    for s in sentences:
        matched_triggers = []
        for pat in CAUSAL_CLAIM_PATTERNS:
            m = pat.search(s)
            if m:
                matched_triggers.append(m.group(0))

        if matched_triggers:
            # Check if this sentence includes variance indicators
            has_variance = any(vp.search(s) for vp in VARIANCE_PATTERNS)
            has_numbers = any(mp.search(s) for mp in METRIC_PATTERNS)

            if "significantly" in s.lower() and "p =" not in s.lower() and "p <" not in s.lower():
                risk = "HIGH: Claims significance without stating p-value"
                status = "NEEDS_STATISTICAL_TEST"
            elif has_numbers and not has_variance:
                risk = "MEDIUM: Single-run metric reported without variance (no mean +- std)"
                status = "NEEDS_SEED_VARIANCE"
            elif "proves" in s.lower() or "undeniably" in s.lower():
                risk = "HIGH: Overclaiming tone; requires epistemic downgrade"
                status = "TONE_OVERCLAIM"
            else:
                risk = "LOW: Empirical claim requiring verification"
                status = "REQUIRES_VERIFICATION"

            candidate_claims.append({
                "sentence": s,
                "triggers": matched_triggers,
                "has_variance": has_variance,
                "risk": risk,
                "suggested_status": status,
            })

    # 2. Leakage & Domain Audit
    is_medical_domain = any(k in lower_text for k in MEDICAL_IMAGING_KEYWORDS)
    has_patient_grouping = any(k in lower_text for k in PATIENT_GROUPING_KEYWORDS)
    has_image_split_cue = bool(re.search(r"\b(?:80/20|70/30|70/15/15|random split|train_test_split)\b", lower_text))

    leakage_risks = []
    if is_medical_domain:
        if not has_patient_grouping:
            leakage_risks.append({
                "severity": "CRITICAL",
                "category": "Patient-Level Identity Leakage",
                "finding": "Medical/clinical domain detected, but no mention of patient-level grouping (GroupKFold or patient_id). High risk of left/right eye or multi-visit patient leakage into test set.",
                "action": "Demand verification that train and test splits do not share images from the same patient.",
            })
        else:
            leakage_risks.append({
                "severity": "PASS",
                "category": "Patient-Level Grouping",
                "finding": "Document explicitly mentions subject/patient grouping in data partition.",
                "action": "Verify splitting implementation in code.",
            })

    # 3. Class Imbalance & Metric Gaming Check
    has_accuracy = bool(re.search(r"\baccuracy\b", lower_text))
    has_imbalance_cue = bool(re.search(r"\b(?:imbalance|minority|skewed|ratio|prevalence)\b", lower_text))
    has_robust_metrics = bool(re.search(r"\b(?:f1|auc|pr-auc|precision-recall|kappa|confusion matrix)\b", lower_text))

    metric_risks = []
    if has_accuracy and has_imbalance_cue and not has_robust_metrics:
        metric_risks.append({
            "severity": "HIGH",
            "category": "Metric Gaming on Imbalanced Data",
            "finding": "Dataset mentions class imbalance, but reports primarily raw accuracy without Macro-F1 or PR-AUC.",
            "action": "Demand Macro-F1, confusion matrices, and Area Under Precision-Recall Curve.",
        })

    # 4. Variance Reporting Across Document
    total_metrics_found = len(re.findall(r"\b[0-9]{1,3}\.[0-9]{1,2}%\b", text))
    total_variance_found = len(re.findall(r"[±\+\/\-]\s*[0-9\.]+", text))

    variance_summary = {
        "metrics_count": total_metrics_found,
        "variance_count": total_variance_found,
        "has_adequate_variance": (total_variance_found > 0 and total_variance_found >= (total_metrics_found // 4)),
    }

    return {
        "filename": filename,
        "total_sentences": len(sentences),
        "claims_found": candidate_claims,
        "leakage_risks": leakage_risks,
        "metric_risks": metric_risks,
        "variance_summary": variance_summary,
    }


def format_text_report(audit: Dict[str, Any]) -> str:
    """Format audit results as safe ASCII terminal report."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"PRE-REVIEW EMPIRICAL AUDIT REPORT: {audit['filename']}")
    lines.append("=" * 80)

    # Leakage Section
    lines.append("1. DATA LEAKAGE & INTEGRITY AUDIT")
    if not audit["leakage_risks"]:
        lines.append("   [INFO] No domain-specific identity leakage red flags triggered.")
    for lr in audit["leakage_risks"]:
        sev = lr["severity"]
        lines.append(f"   [{sev:8s}] {lr['category']}")
        lines.append(f"              Finding: {lr['finding']}")
        lines.append(f"              Action : {lr['action']}")
    lines.append("-" * 80)

    # Metric & Variance Section
    lines.append("2. METRIC RIGOR & VARIANCE AUDIT")
    vsum = audit["variance_summary"]
    lines.append(f"   Percentage Metrics Extracted : {vsum['metrics_count']}")
    lines.append(f"   Variance Markers (+/- or std): {vsum['variance_count']}")
    if not vsum["has_adequate_variance"] and vsum["metrics_count"] > 3:
        lines.append("   [WARN] Most metrics appear to be single-run without error bars (+- std).")
    else:
        lines.append("   [PASS] Variance indicators detected across reported figures.")

    for mr in audit["metric_risks"]:
        lines.append(f"   [{mr['severity']:8s}] {mr['category']}")
        lines.append(f"              Finding: {mr['finding']}")
        lines.append(f"              Action : {mr['action']}")
    lines.append("-" * 80)

    # Claims Section
    claims = audit["claims_found"]
    lines.append(f"3. EMPIRICAL CLAIMS EXTRACTED ({len(claims)} candidate claims)")
    if not claims:
        lines.append("   [INFO] No strong causal or superiority claims detected.")
    else:
        for idx, c in enumerate(claims[:10], 1):
            lines.append(f"   {idx:2d}. [{c['suggested_status']}]")
            lines.append(f"       Quote: \"{c['sentence']}\"")
            lines.append(f"       Risk : {c['risk']}")
            lines.append("")
        if len(claims) > 10:
            lines.append(f"   ... and {len(claims) - 10} more claims in document.")

    lines.append("=" * 80)
    lines.append("SUMMARY RECOMMENDATION FOR REVIEWER AGENT:")
    critical_leak = any(lr["severity"] == "CRITICAL" for lr in audit["leakage_risks"])
    if critical_leak:
        lines.append("CRITICAL: Suspected data leakage detected. Must demand patient-level split confirmation.")
    elif len(claims) > 0 and not vsum["has_adequate_variance"]:
        lines.append("MAJOR CONCERN: Multiple causal claims reported without seed variance or statistical tests.")
    else:
        lines.append("PROCEED: No fatal structural leakage detected; evaluate methodology and citations.")
    lines.append("=" * 80)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Audit manuscripts for empirical claims, variance reporting, and data leakage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input_path", help="Path to manuscript file (.docx, .md, .tex, .txt)")
    parser.add_argument("-o", "--output", help="Path to write report (.txt, .md, or .json)")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format (default: text)")

    args = parser.parse_args()
    input_path = Path(args.input_path).resolve()

    if not input_path.exists():
        print(f"Error: Input file '{input_path}' not found.", file=sys.stderr)
        sys.exit(2)

    ext = input_path.suffix.lower()
    if ext in (".docx", ".dotx"):
        text = extract_text_from_docx(input_path)
    else:
        with open(input_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()

    audit = audit_manuscript(text, filename=input_path.name)

    if args.format == "json":
        report = json.dumps(audit, indent=2)
    else:
        report = format_text_report(audit)

    if args.output:
        out_path = Path(args.output).resolve()
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Audit report saved to: {out_path}")
    else:
        print(report)


if __name__ == "__main__":
    main()
