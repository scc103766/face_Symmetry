# Diabetes risk evaluation metrics and threshold selection

Use this reference when the project discussion turns to diabetes prediction model evaluation, Pima/NHANES/BRFSS baselines, confusion matrices, AUC, sensitivity/specificity, or why a default 0.5 classification threshold was used.

## Current baseline pattern observed in this project

The Pima/XGBoost baseline evaluates a binary diabetes-risk classifier by:

1. Training on a stratified train split.
2. Predicting positive-class probability with `predict_proba`.
3. Converting probability to a hard class with a default threshold:
   `y_pred = (y_prob >= 0.5).astype(int)`.
4. Computing AUC, accuracy, sensitivity/recall, specificity, precision, F1, and confusion matrix.

Important caveat: the 0.5 threshold is only a reproducible baseline/default binary decision rule. It is not a clinically or product-optimized threshold.

## Confusion matrix explanation

For binary diabetes prediction:

| | Predicted negative | Predicted positive |
|---|---:|---:|
| True negative | TN | FP |
| True positive | FN | TP |

Meanings:
- TP: true positive — actual diabetes/high-risk positive, predicted positive.
- TN: true negative — actual negative, predicted negative.
- FP: false positive — actual negative, predicted positive; an over-alert / false alarm.
- FN: false negative — actual positive, predicted negative; a missed case.

Use the confusion matrix as the transparent “four-cell ledger” before explaining derived metrics. For health-risk tasks, explicitly discuss the different costs of FP and FN.

## Metric formulas

Given TP, TN, FP, FN:

- Accuracy = `(TP + TN) / (TP + TN + FP + FN)`
- Sensitivity / Recall / TPR = `TP / (TP + FN)`
- Specificity / TNR = `TN / (TN + FP)`
- Precision / PPV = `TP / (TP + FP)`
- F1 = `2 * precision * recall / (precision + recall)`
- FPR = `FP / (FP + TN) = 1 - specificity`
- Youden's J = `sensitivity + specificity - 1`

AUC is the ROC curve area across thresholds. Explain intuitively: randomly choose one positive and one negative sample; AUC is the probability the model assigns the positive sample a higher risk score than the negative sample.

## Why AUC is usually the first baseline metric

AUC is useful because:

1. Diabetes risk estimation is primarily a risk-ranking problem, not just a hard yes/no classification.
2. AUC does not depend on a single threshold like 0.5.
3. It is widely used in clinical prediction/risk-score literature, making it easy to compare with FINDRISC, NCDRS, Pima, NHANES, BRFSS, and ML baselines.
4. Accuracy can be misleading under class imbalance; a majority-class model can look accurate while missing all positives.

But AUC is not sufficient for product decisions. It does not choose an operating threshold, and it does not directly encode the relative costs of false positives vs false negatives.

## Threshold-selection guidance for this project

Do not treat 0.5 as the final deployment threshold. Present it as a baseline only.

Recommend at least three threshold views:

1. Screening threshold
   - Goal: reduce missed high-risk users.
   - Choose a threshold satisfying a target sensitivity, e.g. sensitivity >= 0.80 or 0.85.
   - Trade-off: more false positives.

2. Strict-label / high-specificity threshold
   - Goal: minimize false positives, matching the user's preference for conservative health-risk pseudo-labels.
   - Choose a threshold satisfying specificity >= 0.85/0.90 or precision >= a target.
   - Trade-off: fewer positives retained and more false negatives.

3. Balanced threshold
   - Goal: general-purpose model comparison.
   - Use Youden's J maximum or F1 maximum.
   - Caveat: may not match the product's preferred FP/FN cost profile.

For pseudo-labeling or “strict positive” dataset construction, prefer high-specificity/high-precision rules, often combined with lab criteria rather than model probability alone.

## How to explain to the user

Start with the concrete confusion matrix and plain-language interpretation, then derive formulas. Avoid presenting AUC as if it were computed at threshold 0.5. Explicitly separate:

- AUC: threshold-free ranking ability.
- Confusion matrix / sensitivity / specificity / precision: threshold-dependent operating-point behavior.
- Calibration / Brier score: whether predicted probabilities are numerically trustworthy.

Recommended short phrasing:

“0.5 is the current code default for turning probability into a hard label. It is useful for a reproducible baseline, but it is not a medical/product threshold. For this project we should choose thresholds based on the intended use: screening wants high sensitivity; strict pseudo-labeling wants high specificity/precision.”
