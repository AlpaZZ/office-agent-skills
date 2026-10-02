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
    re.compile(r"\b([0-9]{1,3}(?:\.[0-9]+)?)\s*(?:%|percent\b)", re.IGNORECASE),
    re.compile(r"\b(?:AUC|F1|Accuracy|Sensitivity|Specificity|Precision|Recall|R2|R-squared)\s*[:=]\s*([0-9\.]+)", re.IGNORECASE),
]

VARIANCE_PATTERNS = [
    re.compile(r"(?:±|\+\/\-|\+\-)\s*[0-9\.]+", re.IGNORECASE),
    re.compile(r"\b(?:std|std dev|standard deviation|confidence interval|95%\s*CI)\b", re.IGNORECASE),
]

# Multi-domain entity grouping cues (Clinical, Behavioral/Users, Organizations, Devices)
ENTITY_GROUPING_DOMAINS = [
    # Clinical / Biological
    "patient", "clinical", "hospital", "subject", "retina", "fundus", "chest", "x-ray", "radiograph",
    "ct scan", "mri", "dermoscopy", "skin lesion", "histopathology", "ultrasound", "biopsy",
    # User / Behavioral / Financial / Systems
    "user", "client", "customer", "student", "household", "account", "participant", "sensor", "station", "device", "school", "firm",
]

ENTITY_GROUPING_KEYWORDS = [
    "patient_id", "patient id", "subject_id", "subject id", "user_id", "user id",
    "client_id", "customer_id", "device_id", "school_id", "entity_id",
    "groupkfold", "stratifiedgroupkfold", "group k-fold", "grouped split",
    "leave-one-group-out", "patient-level", "subject-level", "user-level", "per-patient", "per-subject"
]

TEMPORAL_DOMAINS = [
    "time series", "time-series", "forecasting", "temporal", "sequential", "stock", "crypto",
    "energy demand", "sensor stream", "longitudinal", "traffic flow", "weather forecast"
]

TEMPORAL_GROUPING_KEYWORDS = [
    "timeseriessplit", "temporal split", "chronological", "rolling window",
    "expanding window", "walk-forward", "walk forward", "out-of-time", "oot split"
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

    # 2. Leakage & Domain Partition Audit
    is_entity_domain = any(k in lower_text for k in ENTITY_GROUPING_DOMAINS)
    has_entity_grouping = any(k in lower_text for k in ENTITY_GROUPING_KEYWORDS)
    has_random_split_cue = bool(re.search(r"\b(?:80/20|70/30|70/15/15|random split|train_test_split|randomly partitioned)\b", lower_text))

    is_temporal_domain = any(k in lower_text for k in TEMPORAL_DOMAINS)
    has_temporal_grouping = any(k in lower_text for k in TEMPORAL_GROUPING_KEYWORDS)

    leakage_risks = []
    if is_entity_domain:
        if not has_entity_grouping:
            leakage_risks.append({
                "severity": "CRITICAL",
                "category": "Entity / Subject Identity Leakage",
                "finding": "Repeated entity domain detected (e.g. subjects, users, patients, or devices), but no grouped partitioning (GroupKFold or entity ID) was specified. High risk of multi-sample identity leakage between train and test partitions.",
                "action": "Demand verification that train and test splits do not share records from the same entity/subject.",
            })
        else:
            leakage_risks.append({
                "severity": "PASS",
                "category": "Entity-Level Grouping",
                "finding": "Document explicitly mentions entity/subject grouping in data partition (GroupKFold or entity IDs specified).",
                "action": "Verify splitting implementation in code.",
            })

    if is_temporal_domain:
        if not has_temporal_grouping and (has_random_split_cue or "k-fold" in lower_text):
            leakage_risks.append({
                "severity": "CRITICAL",
                "category": "Temporal Lookahead Bias",
                "finding": "Time-series or sequential domain detected, but data split appears random rather than chronological. High risk of future data leaking into past predictions.",
                "action": "Enforce strict forward-chaining chronological split (TimeSeriesSplit or walk-forward validation).",
            })
        elif has_temporal_grouping:
            leakage_risks.append({
                "severity": "PASS",
                "category": "Temporal Order Preservation",
                "finding": "Document explicitly specifies chronological or temporal forward-chaining split.",
                "action": "Verify out-of-time test cutoff in code.",
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
    total_metrics_found = len(re.findall(r"\b[0-9]{1,3}(?:\.[0-9]+)?\s*(?:%|percent\b)", text, re.IGNORECASE))
    total_variance_found = len(re.findall(r"(?:±|\+\/\-|\+\-)\s*[0-9\.]+", text)) + len(
        re.findall(r"\b(?:std|std dev|standard deviation|confidence interval|95%\s*CI)\b", text, re.IGNORECASE)
    )

    variance_summary = {
        "metrics_count": total_metrics_found,
        "variance_count": total_variance_found,
        "has_adequate_variance": (total_variance_found > 0 and total_variance_found >= max(1, total_metrics_found // 3)),
    }

    # 5. Suspicion Trigger (Performance Anomaly Audit)
    # Triggered when empirical performance is unusually extreme in noisy real-world domains.
    suspicion_triggers = []
    high_metric_pat = re.compile(
        r"\b(?:accuracy|auc|f1|sensitivity|specificity|precision|recall|dice|r2|r-squared|r\^2)\b[^\.\n\?!]*?([0-9]{1,3}(?:\.[0-9]+)?)\s*(%|percent)?",
        re.IGNORECASE,
    )
    for s in sentences:
        for m in high_metric_pat.finditer(s):
            val_str = m.group(1)
            is_pct = bool(m.group(2))
            try:
                val = float(val_str)
                val_pct = val if (is_pct or val > 1.0) else val * 100.0
                if 95.0 <= val_pct <= 100.0:
                    suspicion_triggers.append({
                        "severity": "CRITICAL_SCRUTINY",
                        "metric_found": f"{val_pct:.2f}%",
                        "sentence": s,
                        "category": "Performance Anomaly (>95%) - Epistemic Suspicion Trigger",
                        "finding": f"Reported metric of {val_pct:.2f}% is exceptionally high for noisy empirical/real-world data.",
                        "action": (
                            "DO NOT PRAISE YET. Near-perfect performance in empirical/noisy environments "
                            "is overwhelmingly a symptom of leakage, lookahead bias, or confounding. "
                            "Audit: (1) Entity/group identity leakage, (2) Target/outcome bleed, "
                            "(3) Temporal lookahead, (4) Preprocessing/feature selection leakage, "
                            "(5) Benchmark/train-test contamination, (6) Spurious shortcuts/artifacts, "
                            "(7) Class imbalance gaming, (8) Baseline tuning fairness, "
                            "(9) External validation, (10) Multi-seed variance."
                        ),
                    })
                    break
            except ValueError:
                pass

    return {
        "filename": filename,
        "total_sentences": len(sentences),
        "claims_found": candidate_claims,
        "leakage_risks": leakage_risks,
        "metric_risks": metric_risks,
        "variance_summary": variance_summary,
        "suspicion_triggers": suspicion_triggers,
    }


def format_text_report(audit: Dict[str, Any]) -> str:
    """Format audit results as safe ASCII terminal report."""
    lines = []
    lines.append("=" * 80)
    lines.append(f"PRE-REVIEW EMPIRICAL AUDIT REPORT: {audit['filename']}")
    lines.append("=" * 80)

    # Leakage Section
    lines.append("1. DATA LEAKAGE & PARTITION AUDIT")
    if not audit["leakage_risks"]:
        lines.append("   [INFO] No domain-specific identity or temporal leakage red flags triggered.")
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
    if vsum["metrics_count"] == 0:
        lines.append("   [INFO] No percentage metrics extracted.")
    elif vsum["variance_count"] == 0 and vsum["metrics_count"] > 0:
        lines.append("   [WARN] Metrics reported as single-run numbers without error bars (+- std) or confidence intervals.")
    elif not vsum["has_adequate_variance"]:
        lines.append("   [WARN] Most metrics appear to be single-run without adequate error bars (+- std).")
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
    lines.append("-" * 80)

    # Suspicion Trigger Section
    lines.append("4. PERFORMANCE ANOMALY AUDIT (SUSPICION TRIGGERS)")
    strigs = audit.get("suspicion_triggers", [])
    if not strigs:
        lines.append("   [PASS] No anomalous performance (>95%) detected.")
    else:
        for st in strigs:
            lines.append(f"   [{st['severity']:17s}] {st['category']}")
            lines.append(f"                      Metric : {st['metric_found']}")
            lines.append(f"                      Quote  : \"{st['sentence']}\"")
            lines.append(f"                      Finding: {st['finding']}")
            lines.append(f"                      Action : {st['action']}")
    lines.append("=" * 80)

    lines.append("SUMMARY RECOMMENDATION FOR REVIEWER AGENT:")
    critical_leak = any(lr["severity"] == "CRITICAL" for lr in audit["leakage_risks"])
    has_suspicion = len(strigs) > 0
    if critical_leak:
        lines.append("CRITICAL: Suspected data leakage detected. Must demand entity-level grouped split or temporal ordering verification.")
    elif has_suspicion:
        lines.append("ELEVATED SCRUTINY: Performance >95% detected. Freeze praise and mandate empirical leakage/confounder audit.")
    elif len(claims) > 0 and not vsum["has_adequate_variance"]:
        lines.append("MAJOR CONCERN: Multiple causal claims reported without seed variance or statistical tests.")
    else:
        lines.append("PROCEED: No fatal structural leakage detected; evaluate methodology and citations.")
    lines.append("=" * 80)

    lines.append("EPISTEMIC AXIOMS:")
    lines.append("  * CANNOT VERIFY != FALSE")
    lines.append("  * VERIFIED != TRUE")
    lines.append("  * EXISTS != SUPPORTS CLAIM")
    lines.append("  * NEAR-PERFECT METRIC != SOUND METHOD")
    lines.append("  * NO DETECTED ERROR != NO ERROR EXISTS")
    lines.append("  * PLAUSIBLE != PROVEN")
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
