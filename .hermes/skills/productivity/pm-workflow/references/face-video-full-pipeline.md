# Face-video diabetes risk: full pipeline (labels → ROI → features → model → API)

Captures the proven end-to-end workflow for building a face-video-based diabetes risk
assessment system, from gold-standard label definition through to a deployable API.

## Phase 1: Gold-standard labels

- Use ADA criteria: HbA1c ≥ 6.5% = diabetes (gold), HbA1c ≥ 5.7% = elevated risk.
- HbA1c alone is not a clinical diagnosis without FPG/OGTT/doctor confirmation.
- For strict labels: `diabetes_gold_label = (glycated_hemoglobin >= 6.5).astype(int)`.
- Output to a new CSV (e.g. `mcd_rppg_gold.csv`) rather than modifying the original.
- On MCD-rPPG (600 subjects): 20 positive (3.3%). On any young-skewed dataset expect ≤5%.

## Phase 2: FaceSym ROI caching

- FaceSym API endpoint: `http://<host>:18432/api/detect?token=<token>`.
- Per frame: POST JPEG → receive 478 raw_landmarks + 25 semantic_landmarks.
- Compute 6 landmark-aware ROI boxes: FACE, FOREHEAD, LEFT_CHEEK, RIGHT_CHEEK, NOSE, CHIN.
- Cache per-video as `.npz` with `roi_rgb` (T,6,3), `raw_landmarks_xy` (T,478,2), `semantic_landmarks_xy` (T,25,2), `roi_boxes` (T,6,4), `ppg_aligned` (T,), `frame_indices` (T,).
- Build checkpoint/resume: skip .npz if exists AND passes shape validation.
- Expected throughput: ~10s/video (120 frames) via single-process sequential HTTP.
- Full 3600 videos ≈ 10 hours. Use `--start N` for manual resume.

## Phase 3: Feature extraction

Three feature groups extracted from ROI caches:

| Group   | Contents                                      | Dim    |
|---------|-----------------------------------------------|--------|
| Color   | Per-ROI RGB mean/std/cv/ptp + HSV + Lab stats | ~150   |
| rPPG    | green/POS/CHROM waveforms, HR, SNR, xcorr     | ~200   |
| EVM     | Bandpass 0.7-4.0 Hz, alpha=30, per-channel    | ~300   |

- Aggregation: video-level mean → subject-level (group by patient_id).
- Exclude from features: `diabetes_gold_label`, `glycated_hemoglobin`, `patient_id`, `fold`, `age`, `bmi`, `sex`, all clinical columns. These are either labels or leakage risks.
- Use `mcd_rppg_gold.csv` to merge health/label metadata into feature tables.

## Phase 4: Modeling

- GroupKFold(patient_id), 5-fold. Never random row split — one patient's 6 videos must stay in one fold.
- Model: LogisticRegression(C=0.1, class_weight='balanced') + SelectKBest(k=60) for >40 features.
- Must-run experiments: E0 (age+bmi+sex baseline), E1 (clinical), E2 (color), E3 (rPPG), E4 (EVM), E5 (all face), E6 (E0+E5).
- Main metric: AUPRC (not AUC) due to severe class imbalance. Report Bootstrap 95% CI.
- **Critical finding (MCD-rPPG, 20 pos/580 neg)**: age+bmi+sex alone gives AUC=0.849; pure face features AUC=0.715; adding face to demographics REDUCES AUC to 0.793. Face-derived features provide NO incremental value at this sample size and demographic distribution.
- **Reason**: MCD-rPPG median age is 20. The 20 diabetes-range subjects are concentrated in age 60+. Age is an overwhelming confound. The model learns age, not face physiology.
- For elevated-risk label (HbA1c≥5.7, 198 pos/402 neg): demographics don't separate either (AUC ~0.57) because elevated HbA1c is spread across young ages. Face features still don't help.

## Phase 5: API deployment

- Save: full sklearn Pipeline as `pipeline.pkl`, feature metadata as JSON with columns + coefficients + risk thresholds.
- Inference pipeline: video → extract 120 uniform frames → FaceSym per frame → 6 ROI RGB means → color stats (RGB/HSV/Lab per ROI) → model.predict_proba.
- Risk thresholds computed from training-data probability percentiles (33rd/67th).
- Feature contributions: for LogisticRegression, `coef_ * X_scaled` per feature.
- FastAPI endpoints: POST /predict (multipart video upload), GET /health, GET /docs.
- Response: `{risk_probability, risk_level (低/中/高), top_factors, video_info, model_info}`.

## Key pitfalls

1. **python3 -c blocked**: The host may block `python3 -c` script execution. Write small `.py` scripts instead and run them via `python3 script.py`.
2. **conda run buffering**: stdout from `conda run -n env python3 script.py` may not appear until exit. Check output files (logs, CSVs) for progress.
3. **Do NOT claim diagnosis**: output is risk probability, not clinical diagnosis. Risk labels: 低/中/高, not 糖尿病/非糖尿病.
4. **20 positives is not enough**: if <50 positive subjects, face features will underperform demographics. Need 体检中心 data (≥200 subjects, ≥20 confirmed diabetes).
5. **XGBoost circular leakage**: old Pima XGBoost bridged Glucose from HbA1c via eAG formula. Using this to "predict diabetes" is circular. Gold standard must come from raw lab values.
