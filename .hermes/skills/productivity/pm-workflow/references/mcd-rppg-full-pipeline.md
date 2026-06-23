# MCD-rPPG full pipeline: gold label → ROI → features → model

Proven end-to-end workflow for taking MCD-rPPG (or similar video+health-record dataset) from raw data to subject-level model evaluation. This was validated on 600 subjects / 3600 videos / 20-positive HbA1c>=6.5% gold standard.

## Phase 1: Data preparation

### P1-01: Gold label
- Read `mcd_rppg.csv`, add `diabetes_gold_label = (glycated_hemoglobin >= 6.5).astype(int)`.
- Write to new file `mcd_rppg_gold.csv` (never modify original).
- Verify: same patient always same label, fold column unchanged.
- Script: `scripts/build_gold_label.py`.

### P1-02: Full ROI cache
- Input: `mcd_rppg_gold.csv`, FaceSym API endpoint.
- Process all 3600 videos → 3583 .npz (17 USBVideo+left no-face, all gold=0).
- Checkpoint/resume: skip valid cached .npz. Progress log: `cache_progress.log`.
- Each .npz: `roi_rgb (T,6,3)`, `raw_landmarks_xy (T,478,2)`, `semantic_landmarks_xy (T,25,2)`, `roi_boxes (T,6,4)`, `ppg_aligned (T,)`, `frame_indices (T,)`.
- Runtime: ~10 hours at 32-35 fps. Use `conda run -n <env>` with cv2 available.
- Script: `scripts/extract_facesym_roi_full.py`, wrapper: `scripts/run_p1_02.sh`.
- Key pitfall: default Python may lack cv2; use conda environment `anti-spoofing_scc_175`.

## Phase 2: Feature extraction

### P2-01/02: rPPG + color microvascular features
- Read all 3583 .npz from ROI cache.
- Per video: 6 ROI × (green/POS/CHROM rPPG + RGB/HSV/Lab color stats).
- Aggregate to subject-level via `patient_id` mean.
- Exclude label/leakage columns from aggregation (diabetes_gold_label, glycated_hemoglobin, age, bmi, etc. attached via first()).
- Script: `scripts/extract_microvascular_features_full.py`.

### P2-03: EVM dynamic color features
- Same .npz input, apply bandpass 0.7-4.0Hz + alpha=30 amplification.
- Per ROI per RGB channel: band stats, magnified stats, spectral features, cross-channel correlations.
- Aggregate to subject-level same pattern.
- Script: `scripts/extract_evm_features_full.py`.

### Output dimensions
- Microvascular: ~600 subjects × ~353 cols (341 usable features).
- EVM: ~600 subjects × ~299 cols (287 usable features).
- Combined: ~628 features after dedup.

## Phase 3: Modeling

### Setup
- Merge microvascular + EVM subject features on `patient_id`.
- Target: `diabetes_gold_label` (20 positive / 580 negative).
- MUST use GroupKFold(patient_id), 5-fold — never random row split.

### Feature groups
Use regex-based classification to separate feature columns into groups:
- `clinical`: age, bmi, upper_ap, lower_ap, cholesterol, pulse, stress.
- `color`: columns with `roi_*`, `_mean`, `_std`, `_cv`, `_ptp`, `_hsv_`, `_lab_`.
- `rppg`: columns with `_method_`, `_hr_`, `_snr_`, `_peak_`, `_xcorr_`, `_pearson_`, `_spearman_`, `best_`, `ppg_`, `_green_`, `_pos_`, `_chrom_`.
- `evm`: columns with `_evm_`.
- Everything else → `other` (exclude from features).

### Experiment matrix
| ID | Features | Purpose |
|----|----------|---------|
| E0 | age + bmi + sex | Demographic baseline (MUST run) |
| E1 | clinical cols | Health-record upper bound |
| E2 | color features | Face color signal |
| E3 | rPPG features | Micro-blood-flow signal |
| E4 | EVM features | Dynamic color signal |
| E5 | color + rPPG + EVM | All face-derived |
| E6 | E0 + E5 | Incremental value of face over demographics |

### Model pipeline
- LogisticRegression(C=0.1, class_weight='balanced') or shallow RF(max_depth=6).
- Preprocessing: SimpleImputer(median) + RobustScaler.
- If features > 40: SelectKBest(f_classif, k=min(features, 60)).
- Bootstrap 95% CI (500 iterations) on AUROC, AUPRC.
- Main metric: AUPRC (not AUC, due to 1:29 imbalance).

### Interpretation
- If E0 dominates and E6 < E0: face features add noise, not signal. This is the expected outcome with only 20 positive samples.
- Demographics (age, BMI) are strong confounders — diabetes patients are older/heavier.
- 628 features >> 600 samples → severe overfitting risk even with selection.
- Recommendation: switch to elevated-risk label (HbA1c >= 5.7%, 198 positive) or HbA1c regression for more productive modeling.

## Key scripts produced
- `scripts/build_gold_label.py`
- `scripts/extract_facesym_roi_full.py` + `scripts/run_p1_02.sh`
- `scripts/extract_microvascular_features_full.py`
- `scripts/extract_evm_features_full.py`
- `scripts/train_phase3_model.py`

## Output locations
- Labels: `mcd_rppg_gold.csv`
- ROI cache: `mcd_rppg_reference/facesym_roi_full/`
- Microvascular features: `features/mcd_rppg_full/`
- EVM features: `features/mcd_rppg_evm_full/`
- Model results: `reports/phase3_model_eval_report.md`, `reports/phase3_summary.csv`
