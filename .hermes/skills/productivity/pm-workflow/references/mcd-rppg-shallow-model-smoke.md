# MCD-rPPG shallow model smoke workflow

Use this reference when continuing MCD-rPPG / face-health work after ROI cache and microvascular feature extraction, especially tasks like `M2-MODEL-01`.

## Trigger

Use this workflow when the user approves a shallow model feasibility check on MCD-rPPG face/rPPG features.

Do **not** use it as justification to jump to CNN/ViT/Transformer training or clinical claims.

## Proven sequence

1. Recover state from `WORK_STATUS.md`, `mcd_rppg_reference/RESULTS.md`, and recent `tasks/done/task_M2-*` reports.
2. Confirm explicit user approval before training anything. In PM mode, “继续” should lead to a short approval question unless the user already said “批准”.
3. Use existing subject-level features, e.g. `features/mcd_rppg_microvascular/subject_features.csv`.
4. Exclude leakage and non-face columns from model inputs:
   - `hba1c`
   - `hba1c_elevated_risk`
   - `hba1c_lab_diabetes`
   - `diabetes_strict_label`
   - `xgb_diabetes_probability`
   - `subject_id`, `patient_id`, `split`
   - PPG reference columns such as `ppg_*`
5. Split feature groups before fitting:
   - `face_color`: RGB/HSV/Lab ROI summary features
   - `face_rppg`: green/POS/CHROM ROI rPPG features
   - `face_all`: face-derived color + rPPG only
6. Keep models deliberately shallow:
   - dummy prior baseline
   - LogisticRegression + imputer + scaler + SelectKBest
   - shallow RandomForest
   - optional tiny CPU XGBoost only if already installed; do not install new dependencies without approval
7. Use repeated stratified CV and/or LOOCV as smoke checks only. Report variability, not just the best number.
8. Write outputs:
   - metrics CSV
   - fold metrics CSV
   - feature selection frequency CSV
   - summary JSON
   - report Markdown
   - `tasks/done/<task>_report.md`
9. Update `WORK_STATUS.md` with the next approval point and update `PROJECT_CONTEXT.md` only with durable, caveated conclusions.

## Interpretation rules

- With very small subject counts (e.g. n=16), any AUC or balanced accuracy is hypothesis-generating only.
- If `hba1c_elevated_risk` does not beat dummy but `hba1c_lab_diabetes` shows a signal, state the asymmetry plainly and do not average it into a generic "diabetes performance" claim.
- If feature count is much larger than subject count, explicitly call out high overfitting risk.
- Never say the result diagnoses diabetes or proves camera-based glucose measurement.
- Prefer the next step "expand subject coverage / longer ROI-rPPG windows / locked subject-level split" over deep models.

## Full-scale confirmation (600 subjects, June 2026)

The 16-subject smoke test predictions were confirmed at full scale (600 subjects, 3583 videos, 628 face-derived features):

| Experiment | AUC | AUPRC | Note |
|---|---|---|---|
| E0 (age+bmi+sex) | **0.849** [0.690, 0.972] | 0.337 | Strongest model — demographics alone |
| E5 (face color+rPPG+EVM) | 0.715 [0.578, 0.837] | 0.222 | Face-derived, no demographics |
| E6 (E0 + face) | 0.793 [0.627, 0.933] | 0.378 | **Adding face REDUCED AUC vs E0 alone** |

**Key conclusion**: With HbA1c >= 6.5% gold standard (20 positive / 580 negative), face-derived features (color, rPPG, EVM) provide NO incremental value over age+BMI+sex. Adding face features degrades, not improves, the model. This is consistent with the earlier 16-subject smoke test.

**Root cause**: Only 20 positive samples in 600 subjects. Age and BMI are such strong confounders (diabetes patients are older/heavier) that the model learns demographics, not physiological face signals. With 628 features >> 600 samples, overfitting is severe even with SelectKBest.

**Recommendation for future work**: Switch to HbA1c >= 5.7% elevated-risk label (198 positive / 402 negative) for 10x more positive samples, or use continuous HbA1c regression. Do NOT proceed with gold-standard classification on this dataset without substantially more positive samples.

### 20-positive gold-standard pitfall

When the user asks to use "金标准" (HbA1c >= 6.5%) as the positive label on MCD-rPPG:

- Immediately flag that there are only 20 positive subjects (3.3%).
- E0 baseline (age+bmi+sex) MUST be run first — it will almost certainly dominate.
- Do NOT promise that face/rPPG/EVM features will provide incremental value.
- The honest conclusion is: demographics explain the signal; face-derived features at this sample size add noise.
- Suggest switching to elevated-risk label or regression as the more productive path.

## Verification checklist

Before reporting completion:

- `python -m py_compile <script>` passes.
- Metrics files exist and have expected rows.
- Report contains caveats: not diagnosis, not camera glucose measurement, not clinical validation.
- Tests or at least smoke tests pass.
- `tasks/queue` is not left with stale orphan tasks for the completed scope.
