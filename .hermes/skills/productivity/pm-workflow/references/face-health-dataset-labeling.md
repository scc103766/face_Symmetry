# Face-health dataset labeling and strict pseudo-label workflow

Use this reference when the project needs to turn a local biomedical/video dataset into the project’s standard `subject.csv` / `visit.csv` / `health_profile.csv` / `face_video.csv` / `clinical_label.csv` format, especially when labels are derived from local risk models plus lab measurements.

## Core principles

1. **Inspect the saved model before predicting**
   - Load the model bundle and preprocessor.
   - Record model type, feature count, feature order, imputer statistics, and training-domain assumptions.
   - Do not infer feature order from memory or column names alone.

2. **Preserve clinical/lab labels separately from model pseudo-labels**
   - Keep raw lab-derived labels, e.g. `hba1c_lab_diabetes = HbA1c >= 6.5` and `hba1c_elevated_risk = HbA1c >= 5.7`.
   - Store model probability as `xgb_diabetes_probability` or equivalent.
   - Store final pseudo-label as a separate field such as `diabetes_strict_label`.

3. **For high-precision labels, require agreement between evidence sources**
   - If the user says labels must be strict / avoid false positives, prefer a conjunctive rule:
     `positive iff lab_criterion AND model_probability >= high_threshold`.
   - Example from MCD-rPPG: `HbA1c >= 6.5 AND local_xgboost_probability >= 0.80`.
   - Verify `bad strict positives = 0` where a strict positive violates any required criterion.

4. **Make feature bridges explicit**
   - If applying a model trained on another schema (e.g. Pima-style XGBoost) to a new dataset, write the exact bridge into outputs and reports.
   - Example: `Glucose = estimated average glucose from HbA1c = 28.7*HbA1c - 46.7`; unavailable fields are median-imputed by the saved preprocessor.
   - State clearly that probabilities are auxiliary pseudo-risk scores, not clinical diagnosis.

5. **Output project-standard tables**
   - `subject.csv` — one row per person.
   - `visit.csv` — one row per visit/capture step.
   - `health_profile.csv` — health and physiological measurements.
   - `face_video.csv` — one row per video, with probability and pseudo-label fields for direct joins.
   - `clinical_label.csv` — visit-level label summary.
   - `model_predictions.csv` — per-video probabilities, raw label evidence, and feature-bridge values.
   - `dataset_summary.json` and `README.md` — generation metadata, counts, caveats.

## Verification checklist

- [ ] Output files all exist.
- [ ] Row counts match expected subject/visit/video granularity.
- [ ] Subject-level split keys are present; no random row-level split for multi-video patients.
- [ ] Strict positives satisfy every strict-label criterion.
- [ ] Lab labels, model probabilities, and pseudo-labels are all retained separately.
- [ ] The report warns when the model is used out-of-domain or with bridged/imputed features.

## Pitfalls

- Do not overwrite lab labels with model predictions.
- Do not call strict negatives "clinically non-diabetic"; call them strict-rule negatives or unconfirmed negatives.
- Do not use a model trained on one dataset as if it were calibrated for another dataset unless calibration has been validated.
- Do not randomly split rows when each subject has multiple videos; split by subject/group.
- **CRITICAL: Circular leakage via feature bridges.** If the model's input features are derived from the same lab value you're trying to predict, the model produces a recoded version of the input, not an independent signal. Example: Pima XGBoost uses Glucose as a feature. If Glucose is computed from HbA1c via `eAG = 28.7*HbA1c - 46.7`, then `xgb_diabetes_probability` is just HbA1c passed through a non-linear transform — it contains zero independent information. Using this probability as a "strict" label for face-video training is circular: you're asking the face model to learn something the XGBoost already encoded from the same lab value. The only way a bridged model provides independent signal is if its inputs are NOT derived from the target lab value. Always trace every feature in the bridge back to its source column and flag any that originate from the label.
