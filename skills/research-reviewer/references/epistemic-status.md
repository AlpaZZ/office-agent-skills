# Epistemic Status Framework for Scientific Review

This reference document defines the epistemic status tiers used to audit claims, results, and conclusions in research manuscripts and thesis drafts.

---

## 1. Epistemic Status Tiers

Every empirical assertion in an abstract, discussion, or conclusion belongs to one of eight tiers:

| Status Tier | Definition | Required Evidence | Action if Violated |
| :--- | :--- | :--- | :--- |
| **`[FACT]`** | Direct observation, ground-truth dataset property, or mathematical identity/proof. | Verifiable provenance, exact counts, or formal derivation. | Verify against raw numbers or dataset documentation. |
| **`[SUPPORTED INFERENCE]`** | Empirical conclusion backed by controlled experiments, credible baselines, variance ($\text{Mean} \pm \text{Std}$ over $\ge 3$ seeds), effect size, and appropriate statistical tests. | Controlled comparison, isolated variables, reported variance, and statistical evaluation (considering effect size, not just $p < 0.05$). | Valid as stated. |
| **`[PLAUSIBLE INFERENCE]`** | Reasonable interpretation consistent with findings and theory, but alternative explanations or confounding remain. | Theoretical alignment, consistent trends, or qualitative visualization. | Must soften language: replace "proves" or "guarantees" with "suggests" or "is consistent with". |
| **`[HYPOTHESIS]`** | Proposed mechanism or tentative prediction framed for future testing. | Explicitly framed as an open question, conjecture, or future work. | Ensure phrasing does not state hypothesis as an established finding. |
| **`[INSUFFICIENT_EVIDENCE]`** | Plausible claim, but data, sample size, or comparative ablations in the manuscript are insufficient to establish or refute it. | Lacks isolated controls, external benchmarks, or sample depth. | Request supplementary experiments or downgrade claim scope. |
| **`[NOT_ASSESSED]`** | Claim cannot be evaluated because underlying code, data partition mapping, or critical artifacts are unavailable to the reviewer. | Proprietary data, omitted split code, or unreleased models. | State clearly in review that the claim remains unassessed pending code/data audit. |
| **`[UNSUPPORTED]`** | Strong claim presented as established fact without isolating experiments, baseline controls, or evidence. | Missing baseline, missing ablation, single lucky run generalized to superiority, or unverified citation. | **Critical Flag**: Demand ablation, cross-validation, or tone downgrade. |
| **`[CONTRADICTED]`** | Claim directly refuted by table data, figures, or established scientific consensus. | Data in document shows opposite result or non-significant difference. | **Fatal Flag**: Reject claim; correct narrative to match reported numbers. |

---

## 2. Claim-to-Evidence Mapping Rules

### Rule 1: The Isolation Principle (Causal Claims)
- **Claim pattern**: *"Adding module X improves performance by Y%"*.
- **Requirement**: An ablation study where the only difference between Run A and Run B is module X.
- **Violation**: If learning rate, batch size, or image resolution were changed simultaneously with module X, the claim is `[UNSUPPORTED]`.

### Rule 2: The Fair Baseline Principle (Superiority Claims)
- **Claim pattern**: *"Our proposed architecture outperforms Baseline Z"*.
- **Requirement**: Baseline Z must be re-run in the local environment using the same preprocessing, data split, training epochs, and compute budget.
- **Violation**: Comparing a locally tuned model against a number copied from an external paper evaluated on an unknown or different split is `[UNSUPPORTED]`.

### Rule 3: The Variance & Effect Size Principle (Significance Claims)
- **Claim pattern**: *"Model A significantly outperforms Model B"*.
- **Requirement**: Reporting mean and standard deviation over at least 3 random seeds ($\ge 5$ preferred), plus a paired statistical test (e.g., Wilcoxon signed-rank test or paired t-test) and practical effect size (e.g. Cohen's $d$).
- **Nuance ($p < 0.05$ is not a mechanical rubber stamp)**: A low p-value on a massive sample size can be statistically significant while clinically or practically meaningless. Conversely, on small clinical cohorts, non-parametric permutation tests and effect sizes matter more than arbitrary alpha thresholds.
- **Single-run status**: If only a single run is conducted, the metric is a valid **observation** of that run, but cannot substantiate a generalized superiority inference (`[UNSUPPORTED]` for superiority, `[FACT]` only for that single execution).

### Rule 4: The Generalization Principle (Scope Claims)
- **Claim pattern**: *"Our model provides robust clinical diabetic retinopathy detection"*.
- **Requirement**: Evaluation on an external test set collected from a different hospital, scanner, or patient demographic.
- **Violation**: Evaluating only on a single public dataset with no cross-center validation limits the claim to: *"Demonstrates competitive performance on the [Dataset Name] benchmark"*.

---

## 3. Epistemic Fairness: The Dual Duty of Reviewer 2

Rigor is not cynicism:
1. **Neither accept nor reject claims before evidence is examined**: A reviewer who rejects sound work out of ungrounded suspicion is just as unscientific as an agreeable AI that flatters the author.
2. **Affirm solid methodological practice**: If the manuscript explicitly specifies `GroupKFold` by patient ID, reports multi-seed variance with standard deviations, and provides fair baseline comparisons, explicitly recognize this rigor in the review report.
3. **Calibrate scrutiny to domain difficulty**: Do not demand clinical-grade cross-center splits for synthetic toy problems (e.g. synthetic Gaussian clusters or MNIST). Match the audit rigor to the domain's real-world consequence and complexity.

---

## 4. Calibrating Academic Tone

Reviewers must flag and rewrite puffed-up narrative claims:

| Overclaimed Phrasing (AI Slop / Uncalibrated) | Calibrated Scientific Phrasing |
| :--- | :--- |
| "Our novel approach completely solves the problem of..." | "Our approach addresses the challenge of... under [specific conditions]." |
| "This undeniably proves that attention is essential." | "Ablation experiments show a 2.1% performance gain when attention is added." |
| "The model exhibits flawless diagnostic capabilities." | "The model achieves an AUC of 0.94 on the internal test split." |
| "Our method achieves state-of-the-art results." | "Our method outperforms the tested baselines on this benchmark." |

