# Machine Learning & Medical Imaging Leakage Audit Checklist

Data leakage is the most frequent cause of artificially inflated ML metrics. When a model achieves suspiciously high accuracy (>95% on complex real-world imagery), the reviewer must systematically audit for the following six leakage vectors.

---

## 1. Patient & Subject-Level Leakage (Identity Contamination)

In clinical and biological imaging (retinal fundus, chest radiography, dermoscopy, histopathology, brain MRI), a single subject often has multiple images (left/right eye, serial visits, multiple magnification tiles).

### The Red Flag
- The paper reports an image-level random split (e.g. `train_test_split(images, test_size=0.2, random_state=42)`).
- The dataset description does not mention `patient_id` or subject grouping.

### The Mechanism
Convolutional networks easily memorize individual anatomical signatures (retinal vascular tree branching, choroidal patterns, unique skin texture, scanner sensor noise). When images from the same patient appear in both train and test partitions, the model identifies the patient rather than generalizable disease pathology.

### The Audit Test
```python
# Verify zero intersection of patient identifiers between splits
train_patients = set(train_df["patient_id"])
test_patients = set(test_df["patient_id"])
leakage = train_patients.intersection(test_patients)
assert len(leakage) == 0, f"Critical Leakage: {len(leakage)} patients appear in both train and test sets!"
```

### Remediation
- Enforce `GroupKFold` or `StratifiedGroupKFold` on `patient_id`.
- If patient IDs are unavailable in a legacy dataset, explicitly acknowledge image-level grouping as a major limitation in the manuscript.

---

## 2. Preprocessing & Augmentation Leakage

### The Red Flags
- Applying dataset-wide normalization (mean and standard deviation) before splitting.
- Applying adaptive histogram equalization (CLAHE) or contrast stretching across the pooled dataset prior to cross-validation.
- Performing data augmentation (rotation, flipping, cropping) before splitting the dataset.

### The Mechanism
Augmenting before splitting guarantees that synthetic duplicates of training images end up in the validation and test sets. Calculating dataset-wide statistics leaks distribution parameters from the test set into training.

### Remediation
- Always split raw data first: `Train`, `Validation`, `Test`.
- Fit scalers, tokenizers, and normalization transforms **strictly on the Train split**.
- Transform Validation and Test splits using the fitted Train parameters.
- Apply augmentation layers exclusively inside the training pipeline.

---

## 3. Test Set Optimization Contamination

### The Red Flags
- Model checkpoints selected based on the lowest test loss.
- Early stopping triggered by test set performance.
- Classification threshold (e.g. Youden's Index on ROC) tuned on the test set.
- Hyperparameter search (grid search / Optuna) evaluated directly on the test set.

### The Mechanism
Any optimization loop that reads test set metrics converts the test set into a training signal. The reported metric no longer measures generalization.

### Remediation
- Enforce a strict three-way split: **Train (60-70%)**, **Validation (15-20%)**, **Test (15-20%)**.
- All checkpoint selection, early stopping, and threshold tuning must use the **Validation split only**.
- The Test split is evaluated exactly once at the very end of the project.

---

## 4. Class Imbalance & Metric Gaming

### The Red Flag
- A paper claims: *"Our model achieves 96.8% accuracy on disease detection"*, but the dataset contains 95% healthy controls and 5% positive cases.

### The Mechanism
A dummy classifier that predicts "healthy" for every sample achieves 95.0% accuracy with zero diagnostic utility.

### The Audit Test
Check whether the paper reports:
1. Macro-averaged F1-Score (unweighted).
2. Area Under the Precision-Recall Curve (PR-AUC), which is sensitive to minority class performance.
3. Confusion matrix showing True Positives and False Negatives explicitly.
4. Balanced Accuracy or Cohen's Kappa ($\kappa$).

---

## 5. Scanner, Site, and Device Leakage

### The Red Flag
- Positive disease cases were collected from Hospital A (using Topcon camera), while negative controls were collected from Hospital B (using Canon camera).

### The Mechanism
Deep neural networks readily pick up camera resolution, color temperature, vignetting, and black border cropping. The model predicts the camera manufacturer rather than the disease.

### Remediation
- Cross-center external validation: train on Hospital A data, test on Hospital B data.
- Domain adversarial training or camera artifact masking (circular crop of retinal area).

---

## 6. Duplicate & Near-Duplicate Contamination

### The Red Flag
- Public datasets scraped from the web or composite databases (e.g. Kaggle compilations) that aggregate multiple sources.

### The Audit Test
- Check image perceptual hashes (`imagehash.phash`) across train and test splits to detect identical or slightly cropped images.
