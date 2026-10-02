# Scientific Peer Review & Revision Roadmap Template

Use this markdown structure when compiling the final report for a manuscript, thesis chapter, or research draft.

---

```markdown
# Scientific Peer Review Report: [Manuscript Title]

- **Review Mode**: [Full Review | Methodology Focus | Adversarial / Devil's Advocate | Re-Review]
- **Target Venue / Context**: [e.g. IEEE TMI / MICCAI / Thesis Defense]
- **Overall Recommendation**: [ACCEPT WITH MINOR REVISIONS | REVISE AND RESUBMIT (MAJOR REVISIONS) | REJECT]

---

## 1. Executive Editorial Assessment

[2-3 concise paragraphs summarizing: (1) what the paper attempts, (2) the core strength of the work, and (3) the primary scientific or methodological blocker that prevents immediate acceptance.]

---

## 2. Claim-by-Claim Epistemic Audit

| # | Stated Claim / Conclusion | Document Section | Epistemic Status | Required Remediation |
|---|---|---|---|---|
| 1 | "Adding CLAHE improves classification accuracy by 3.2%." | Section 4.2 | `[UNSUPPORTED]` | Run isolated ablation; report $\text{Mean} \pm \text{Std}$ over $\ge 3$ seeds. |
| 2 | "Model achieves 94.5% AUC on diabetic retinopathy." | Abstract | `[SUPPORTED INFERENCE]` | Ensure ROC curve and 95% CI are included in Section 4. |
| 3 | "Our architecture outperforms all prior methods." | Section 5 | `[PLAUSIBLE INFERENCE]` | Soften claim: "Outperforms tested baselines on this dataset split." |

---

## 3. Methodological Rigor & Leakage Audit

### 3.1 Dataset Integrity & Split Protocol
- **Patient/Subject Split**: [PASS | WARN | FAIL]
  - *Details*: [Explain whether split is patient-level or image-level].
- **Preprocessing & Augmentation Isolation**: [PASS | WARN | FAIL]
  - *Details*: [Confirm transformers were fitted strictly on training data].
- **Class Imbalance & Metric Adequacy**: [PASS | WARN | FAIL]
  - *Details*: [Assess whether Macro-F1 / PR-AUC were reported].

### 3.2 Experimental Rigor & Baseline Fairness
- **Seed Variance**: [Reported ($\ge 3$ seeds) | Single run only]
- **Statistical Significance**: [Formal p-value test reported | None]
- **Fairness of Baselines**: [Locally reproduced under identical pipeline | Quoted from prior literature]
- **Ablation Completeness**: [All novel components isolated | Combined only]

---

## 4. Devil's Advocate Challenges (Adversarial Stress Test)

The author must provide empirical evidence or revised text addressing these 3 critical challenges:

1. **Rival Explanation 1**: [Challenge the primary performance driver].
2. **Rival Explanation 2**: [Challenge the baseline fairness or compute disparity].
3. **Failure Analysis**: [Demand discussion and visualization of negative / failure cases].

---

## 5. Prioritized Revision Roadmap

### Tier 1: Critical Blockers (Must fix before defense/submission)
- [ ] **[Leakage / Split]**: Re-partition dataset by `patient_id` using `GroupKFold` if subject IDs exist.
- [ ] **[Variance]**: Re-train final model and baseline across 3 random seeds; report $\text{Mean} \pm \text{Std}$.

### Tier 2: Required Experimental Controls
- [ ] **[Ablation]**: Add a row to Table 2 isolating Component A from Component B.
- [ ] **[Significance]**: Run Wilcoxon signed-rank test comparing per-fold scores; report exact p-value.

### Tier 3: Narrative & Epistemic Calibration
- [ ] **[Tone]**: Replace causal phrases ("proves", "guarantees") with calibrated empirical language ("shows an improvement under tested conditions").
- [ ] **[Citations]**: Verify DOIs and references using `citation-verifier` to eliminate any broken or hallucinated sources.
```
