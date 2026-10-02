# Research Reviewer Lessons Log (Curated Empirical Memory)

This file contains accumulated methodological principles derived from past review errors and empirical pitfalls.
Read this file at the start of every review task to ensure past mistakes are never repeated.

---

## Core Empirical Review Lessons

### Lesson 1: The Patient Leakage Trap in Medical Vision
- **Mistake**: Praising an architecture that scored 98% accuracy on a public retinal/radiology dataset.
- **Correction**: High accuracy on multi-sample medical imaging datasets frequently stems from image-level random splitting, where multiple images from the same patient appear in both train and test partitions.
- **Rule**: Whenever evaluating medical imaging experiments with multiple images per subject, inspect the splitting code or methodology text for `patient_id` or `subject_id`. If splitting is image-level rather than grouped, flag it as an entity leakage risk.

### Lesson 2: The Single-Seed Illusion
- **Mistake**: Accepting a minor performance gain as conclusive proof that a novel module works.
- **Correction**: Deep learning optimization has an intrinsic variance across different random seeds. A single run reflects stochastic sampling, not proven algorithmic superiority.
- **Rule**: Never label a comparative performance delta as `[SUPPORTED INFERENCE]` unless reported as $\text{Mean} \pm \text{Std}$ over at least 3 random seeds. A single run is a valid observation of that specific trial, but represents `[INSUFFICIENT_EVIDENCE]` to claim general superiority.

### Lesson 3: Verified Citation ≠ Supported Claim
- **Mistake**: Marking a claim as verified simply because the citation has a valid CrossRef DOI or arXiv ID.
- **Correction**: AI models and hurried authors often attach legitimate DOIs to assertions that the cited paper never made or actively refuted.
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

## Lesson Curation Protocol (Preventing Self-Reinforcing Bias)

To ensure empirical integrity and prevent hallucinated or overly paranoid biases from accumulating:
1. **Human-Curated Memory**: This file is curated by human researchers. AI agents must **never** automatically write unvetted rules directly to `LESSONS.md`.
2. **Proposal Mechanism**: When an agent detects a subtle novel failure mode or when human review corrects an oversight, the agent drafts a proposal formatted as:
   - **Mistake**: What was initially missed or misjudged.
   - **Correction**: Why it was wrong and the underlying empirical principle.
   - **Rule**: The concrete actionable check to execute in future reviews.
3. **Approval**: Candidate lessons are logged under a `## Lesson Proposals` section in the review roadmap or written to a temporary proposal ledger (`LESSON_PROPOSALS.md`), requiring explicit human confirmation before becoming permanent agent rules.

