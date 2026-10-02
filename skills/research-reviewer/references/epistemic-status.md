# Epistemic Status Framework for Scientific Review

This reference document defines the epistemic status tiers used to audit claims, results, and conclusions in research manuscripts and thesis drafts.

---

## 1. Epistemic Status Tiers

Every empirical assertion in an abstract, discussion, or conclusion belongs to one of six tiers:

| Status Tier | Definition | Required Evidence | Action if Violated |
| :--- | :--- | :--- | :--- |
| **`[FACT]`** | Direct observation, ground-truth dataset property, or mathematical identity. | Verifiable provenance, exact counts, or formal derivation. | Verify against raw numbers or dataset documentation. |
| **`[SUPPORTED INFERENCE]`** | Empirical conclusion backed by controlled experiments. | $\ge 3$ seeds ($\text{Mean} \pm \text{Std}$), fair baseline, and statistical test ($p < 0.05$). | Valid as stated. |
| **`[PLAUSIBLE INFERENCE]`** | Reasonable interpretation consistent with findings, but unproven. | Theoretical alignment or qualitative visualization (e.g. Grad-CAM). | Must soften language: replace "proves" with "suggests" or "is consistent with". |
| **`[HYPOTHESIS]`** | Proposed mechanism or tentative prediction framed for future testing. | Explicitly framed as open question or future work. | Remove conclusive phrasing. |
| **`[UNSUPPORTED]`** | Strong claim presented as fact without isolating experiments or controls. | Missing ablation, missing baseline, single lucky seed, or unverified citation. | **Critical Flag**: Demand ablation, cross-validation, or tone downgrade. |
| **`[CONTRADICTED]`** | Claim directly refuted by table data, figures, or authoritative literature. | Data in document shows opposite or insignificant difference. | **Fatal Flag**: Reject claim; correct narrative to match reported numbers. |

---

## 2. Claim-to-Evidence Mapping Rules

### Rule 1: The Isolation Principle (Causal Claims)
- **Claim pattern**: *"Adding module X improves performance by Y%"*.
- **Requirement**: An ablation study where the only difference between Run A and Run B is module X.
- **Violation**: If learning rate, batch size, or image resolution were changed simultaneously with module X, the claim is `[UNSUPPORTED]`.

### Rule 2: The Fair Baseline Principle (Superiority Claims)
- **Claim pattern**: *"Our proposed architecture outperforms Baseline Z"*.
- **Requirement**: Baseline Z must be re-run in the local environment using the same preprocessing, data split, training epochs, and compute budget.
- **Violation**: Comparing a locally tuned model against a number copied from a 2018 paper evaluated on a different split is `[UNSUPPORTED]`.

### Rule 3: The Variance Principle (Significance Claims)
- **Claim pattern**: *"Model A significantly outperforms Model B"*.
- **Requirement**: Reporting mean and standard deviation over at least 3 random seeds ($\ge 5$ preferred), plus a paired statistical test (e.g., Wilcoxon signed-rank test or paired t-test).
- **Violation**: A 0.4% higher accuracy from a single run without confidence intervals is `[PLAUSIBLE INFERENCE]` at best, never `[SUPPORTED INFERENCE]`.

### Rule 4: The Generalization Principle (Scope Claims)
- **Claim pattern**: *"Our model provides robust clinical diabetic retinopathy detection"*.
- **Requirement**: Evaluation on an external test set collected from a different hospital, scanner, or patient demographic.
- **Violation**: Evaluating only on a single public dataset with no cross-center validation limits the claim to: *"Demonstrates competitive performance on the [Dataset Name] benchmark"*.

---

## 3. Calibrating Academic Tone

Reviewers must flag and rewrite puffed-up narrative claims:

| Overclaimed Phrasing (AI Slop / Uncalibrated) | Calibrated Scientific Phrasing |
| :--- | :--- |
| "Our novel approach completely solves the problem of..." | "Our approach addresses the challenge of... under [specific conditions]." |
| "This undeniably proves that attention is essential." | "Ablation experiments show a 2.1% performance gain when attention is added." |
| "The model exhibits flawless diagnostic capabilities." | "The model achieves an AUC of 0.94 on the internal test split." |
| "Our method achieves state-of-the-art results." | "Our method outperforms the tested baselines on this benchmark." |
