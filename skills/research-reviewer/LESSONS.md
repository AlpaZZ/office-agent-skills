# Research Reviewer Lessons Log (Self-Improvement Memory)

This file contains accumulated rules derived from past review errors and empirical pitfalls.
Read this file at the start of every review task to ensure past mistakes are never repeated.

---

## Core Empirical Review Lessons

### Lesson 1: The Patient Leakage Trap in Medical Vision
- **Mistake**: Praising an architecture that scored 98% accuracy on a public retinal/radiology dataset.
- **Correction**: High accuracy on medical images almost always stems from image-level random splitting where images from the same patient appear in both train and test partitions.
- **Rule**: Whenever evaluating medical imaging experiments, immediately inspect the splitting code or methodology text for `patient_id` or `subject_id`. If splitting is image-level, flag it as a critical leakage risk.

### Lesson 2: The Single-Seed Illusion
- **Mistake**: Accepting a 0.8% accuracy gain as proof that a novel module works.
- **Correction**: Standard deep learning optimization (AdamW with data augmentation) has an intrinsic variance of $\pm 0.5\%$ to $\pm 1.2\%$ across different seeds. A single run is not proof.
- **Rule**: Never label a performance delta as `[SUPPORTED INFERENCE]` unless reported as $\text{Mean} \pm \text{Std}$ over at least 3 random seeds.

### Lesson 3: Verified Citation ≠ Supported Claim
- **Mistake**: Marking a claim as verified simply because the citation has a valid CrossRef DOI.
- **Correction**: AI models and hurried authors often attach legitimate DOIs to assertions that the cited paper never made.
- **Rule**: Distinguish strictly between registry identity validation (`citation-verifier`) and substantive claim support (`research-reviewer`).

### Lesson 4: The Accuracy Metric Trap on Imbalanced Data
- **Mistake**: Evaluating a classifier by accuracy on a dataset with 90% normal cases.
- **Correction**: A naive model predicting "Normal" for everything scores 90% accuracy while failing 100% of diseased patients.
- **Rule**: Demand Macro-F1, PR-AUC, and full confusion matrices on any dataset with class imbalance $> 2:1$.

### Lesson 5: The Unequal Baseline Budget Trap
- **Mistake**: Comparing a proposed method tuned with 50 trials of Optuna/Ray-Tune against a baseline trained with arbitrary default settings.
- **Correction**: Most "architectural gains" vanish when baselines receive equal hyperparameter tuning effort.
- **Rule**: Question whether the baseline received equal tuning budget, learning rate schedules, and data augmentations.

---

## How to Append New Lessons

When you catch a subtle error or when a human researcher corrects a review oversight:
1. Append an entry below using the format:
   - **Mistake**: What was initially missed or misjudged.
   - **Correction**: Why it was wrong and the underlying empirical principle.
   - **Rule**: The concrete actionable check to execute in future reviews.
2. Keep entries concise, technical, and grounded in empirical rigor.
