# Empirical Research & Methodology Audit Checklist

This checklist enforces scientific rigor across experimental design, statistical testing, baseline fairness, and ablation controls in empirical machine learning and computer science research.

---

## 1. Random Seeds and Variance Reporting

### The Standard
- Every reported metric comparing two methods must be evaluated across **$\ge 3$ independent random seeds** ($\ge 5$ seeds recommended for stochastic deep learning).
- Metrics must be reported as **$\text{Mean} \pm \text{Standard Deviation}$** (e.g., $94.2\% \pm 0.4\%$).

### Red Flags
- Reporting a single decimal point gain (e.g., $91.8\%$ vs $91.2\%$) from a single training run.
- Omitting error bars or standard deviations from bar charts and result tables.
- Cherry-picking the single best seed while discarding lower-performing runs.

### Reviewer Verdict
If a paper reports only single-run metrics:
> *"The observed improvement of 0.6% is within typical random seed variance for Adam/SGD optimization. Without reporting mean and standard deviation over $\ge 3$ seeds, this finding cannot be distinguished from stochastic noise."*

---

## 2. Statistical Significance Testing

### The Standard
- Claims of "significant improvement" require a formal statistical hypothesis test:
  - **Paired t-test**: For normally distributed per-fold or per-subject metric differences.
  - **Wilcoxon signed-rank test**: For non-parametric metric comparisons.
  - **Bootstrap Confidence Intervals (95% CI)**: For test set metric distributions.
- Report exact p-values (e.g., $p = 0.018$) rather than arbitrary asterisks ($*$, $**$).

### Red Flags
- Using the word "significantly" in the abstract or discussion without conducting a statistical test.
- Performing multiple hypothesis tests without correction (e.g., Bonferroni or False Discovery Rate).

---

## 3. Baseline Fairness & The Ruler Principle

### The Standard
- To claim that Method X beats Baseline Y, **Baseline Y must be re-run in your exact local environment** using:
  1. The exact same data split (train/validation/test).
  2. The exact same image resolution, color space, and data augmentation pipeline.
  3. Equal hyperparameter tuning effort (do not tune your method with 50 Optuna trials while running the baseline on default learning rate).

### Red Flags
- Quoting baseline metrics directly from tables in 3-year-old published papers evaluated on different splits.
- Crippling the baseline (e.g., running baseline with no augmentation or a smaller batch size).

---

## 4. Ablation Study Rigor

### The Standard
When a paper introduces multiple modifications (e.g., Data Preprocessing + Loss Function + Attention Module), the contribution of each component must be isolated:

| Experiment | Baseline | Component A (e.g. CLAHE) | Component B (e.g. CBAM Attention) | Component C (e.g. Focal Loss) | Metric ($\text{Mean} \pm \text{Std}$) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| 1. Baseline | ✓ | - | - | - | $91.2 \pm 0.5\%$ |
| 2. + Component A | ✓ | ✓ | - | - | $92.4 \pm 0.4\%$ |
| 3. + Component B | ✓ | - | ✓ | - | $92.9 \pm 0.3\%$ |
| 4. Full Method | ✓ | ✓ | ✓ | ✓ | **$94.1 \pm 0.4\%$** |

### Red Flags
- Introducing 3 components simultaneously and comparing only the baseline against the final combined pipeline.
- Omitting computational cost comparisons (parameter count, GFLOPs, inference latency in milliseconds).
