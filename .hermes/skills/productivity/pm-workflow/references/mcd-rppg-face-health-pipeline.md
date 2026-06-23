# MCD-rPPG face-health data pipeline notes

Use this reference when PM workflow tasks involve constructing conservative face/rPPG health datasets from MCD-rPPG-style video + physiological CSV data.

## Workflow pattern

1. Recover state first:
   - Read `WORK_STATUS.md`.
   - Check `tasks/done/` for prior reports.
   - Verify expected artifacts before regenerating them.
2. Build labels before feature extraction:
   - Create a standard dataset layout (`subject.csv`, `visit.csv`, `health_profile.csv`, `face_video.csv`, `clinical_label.csv`).
   - Preserve raw measurement-derived labels separately from model-derived pseudo-labels.
   - For diabetes, prefer high-precision conservative pseudo-labels when the user asks for strictness/minimal false positives.
3. Split before large preprocessing:
   - Use subject-level or patient-level splits only.
   - Verify train/val/test subject sets are disjoint.
   - With very few positive subjects, manually distribute positives across splits, then stratify remaining strata.
4. Run small smoke tests before full preprocessing:
   - Sample from each split and label class.
   - Limit frames per video.
   - Write `.npz` caches plus `summary.csv`, `summary.json`, and a compact stats JSON.
   - Verify shapes, success rates, no subject leakage, and no malformed IDs before reporting done.

## Conservative diabetes pseudo-labeling pattern

When using a local tabular model trained on a different dataset/domain, treat model output as auxiliary risk score, not diagnosis.

Example strict rule used successfully:

```text
diabetes_strict_label = 1 iff HbA1c >= 6.5 AND local_model_probability >= 0.80
```

Also preserve:

```text
hba1c_lab_diabetes = HbA1c >= 6.5
hba1c_elevated_risk = HbA1c >= 5.7
xgb_diabetes_probability = model risk score
```

Report explicitly that strict negatives are "not strict positive / unconfirmed" rather than medically confirmed non-diabetes.

## Pima-style XGBoost bridge caution

If a local Pima-style XGBoost model expects:

```text
Pregnancies, Glucose, BloodPressure, SkinThickness, Insulin, BMI, DiabetesPedigreeFunction, Age
```

and MCD-rPPG has incomplete fields, bridge conservatively:

```text
Glucose = 28.7 * HbA1c - 46.7  # estimated average glucose, not fasting glucose
BloodPressure = lower_ap
BMI = bmi
Age = age
Unavailable fields = NaN for the saved preprocessor to median-impute
```

Document this as a domain bridge and avoid clinical claims.

## Pandas row attribute pitfall

Avoid `row.view`, `row.step`, etc. in `DataFrame.apply` when generating IDs; pandas Series attributes/methods can collide with column names. Use bracket access:

```python
row["view"]
row["step"]
row["patient_id"]
```

Always validate generated IDs do not contain strings such as `<bound method` before downstream use.

## FaceSym / MediaPipe ROI smoke pattern

For FaceSym API landmark-aware ROI smoke tests:

1. Use the split manifests, not raw dataset order.
2. Sample at least one positive and one negative per split when possible.
3. For each frame, call the API and store:
   - `raw_landmarks_xy` as `(frames, 478, 2)`
   - `semantic_landmarks_xy` as `(frames, 25, 2)`
   - `roi_boxes` as `(frames, n_rois, 4)`
   - `roi_rgb` as `(frames, n_rois, 3)`
   - `ppg_aligned` as `(frames,)`
4. Use landmark-aware rectangular ROIs for smoke tests, e.g. `FACE`, `FOREHEAD`, `LEFT_CHEEK`, `RIGHT_CHEEK`, `NOSE`, `CHIN`.
5. Verify:
   - all expected `.npz` files exist
   - face success rate
   - expected array shapes
   - all ROI areas are positive
   - labels and splits are represented

Do not jump directly to all videos when the API is per-frame HTTP POST; first estimate throughput and stability on a balanced subset.

## Full-scale deployment: balanced subset → all videos

When scaling from an 87-video balanced subset to all 3600 MCD-rPPG videos:

### Phase structure

| Phase | Tasks | Key artifacts |
|-------|-------|---------------|
| **Phase 1** — Data prep | Gold-standard label construction (`HbA1c >= 6.5` → `diabetes_gold_label`); full FaceSym ROI caching (3600 videos, ~10h, checkpoint/resume) | `mcd_rppg_gold.csv`, `facesym_roi_full/*.npz` |
| **Phase 2** — Features | rPPG (green/POS/CHROM) + color (RGB/HSV/Lab 6ROI) stats; EVM dynamic color (bandpass 0.7-4.0Hz, alpha=30) | `features/mcd_rppg_full/`, `features/mcd_rppg_evm_full/` |
| **Phase 3** — Modeling | Subject-level 5-fold GroupKFold; E0 baseline (age+BMI+sex) first; AUPRC+Bootstrap CI | `reports/` |

### Script adaptation pattern

Existing balanced-subset scripts (`extract_facesym_roi_balanced_subset.py`, `extract_mcd_rppg_microvascular_features.py`, `extract_mcd_rppg_evm_features.py`) should be adapted, not rewritten from scratch:

1. **Input change**: Point `--cache-dir` to `facesym_roi_full/` (all .npz) instead of the balanced subset directory.
2. **Metadata source**: Use `mcd_rppg_gold.csv` as the single source of truth for labels + health fields. Build a `video_id → row` lookup keyed by `mcd_video_{patient_id}_{camera}_{step}_{view}`.
3. **Grouping key**: Use `patient_id` (not `subject_id`). There are 600 patients × 6 videos = 3600 rows.
4. **Label column**: Use `diabetes_gold_label` (int, 0/1). Preserve `glycated_hemoglobin` for regression tasks but exclude from feature input.
5. **Remove old dependencies**: Skip `sample_selection.csv`, `clinical_label.csv`, `health_profile.csv`, `diabetes_strict_label`, `hba1c_lab_diabetes`, `hba1c_elevated_risk`, `xgb_diabetes_probability` — these were from the old pseudo-label pipeline.
6. **Subject aggregation**: `df.groupby("patient_id")[agg_cols].mean()` — exclude label/health/key columns from averaging, then merge them back via `.first()`.

### Checkpoint/resume for batch processing

For long-running batch jobs (e.g., FaceSym API ROI extraction):
- **On start**: Check which output `.npz` files already exist AND validate their structure (shape check required keys).
- **Valid cache → skip**: Don't re-process. Log as `ok_cached`.
- **Invalid/missing → process**: Write `.npz` immediately after each video completes.
- **Progress log**: Append timestamped per-video line to `cache_progress.log`.
- **Resume**: `--start=N` CLI argument to skip first N rows of the input CSV.
- **Wrapper**: Use `bash` wrapper scripts calling `conda run -n anti-spoofing_scc_175 python3 scripts/<name>.py` — do not run with system Python (no cv2).

### Video ID convention

```python
video_id = f"mcd_video_{int(patient_id)}_{camera}_{step}_{view}"
```

This matches the `.npz` filename stem in `facesym_roi_full/`. Use the same key for metadata lookups from `mcd_rppg_gold.csv`.