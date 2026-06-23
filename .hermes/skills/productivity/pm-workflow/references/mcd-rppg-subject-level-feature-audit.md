# MCD-rPPG subject-level feature audit and tech-solution alignment

Use this reference when the user asks what `subject_features.csv` contains, why it has many columns, why subject-level aggregation is used, or whether M2 Face-video/rPPG work has drifted from a face-video-first diabetes risk technical plan.

## Trigger phrases

- “subject-level 每个内容是什么”
- “为什么有 349 列 / 为什么这么多列”
- “为什么这样处理”
- “输入是什么得到什么”
- “和 diabetes_tech_solution_final.md 是否偏移”
- “M2 面部视频/rPPG 探索细节”

## Required stance

1. Re-anchor first: final product goal is face-video-first “扫脸看健康”: face video -> diabetes risk assessment.
2. Use the current FaceSym API spec when discussing landmarks: `478 raw landmarks + 25 semantic landmarks`. Treat older “MediaPipe 468 points” wording as historical background only; primary engineering docs should say 478.
3. Explain subject-level as a leakage-control and product-shape step, not just a pandas transformation.
4. Separate training/validation aids from production inference inputs:
   - HbA1c/labels are supervision/validation.
   - PPG reference is rPPG quality validation only.
   - `xgb_diabetes_probability` is teacher/context/contrast only, not final product input.
5. Do not present tiny-sample metrics as model performance. Use “smoke-level feasibility” and “hypothesis-generating”.

## Verified pattern from the Diabetes_Risk_Assessment M2 session

Current subject-level artifact:

```text
features/mcd_rppg_microvascular/subject_features.csv
16 subjects × 349 columns
source: video_features.csv, 87 videos × 360 columns
```

Column accounting:

```text
349 total
= 2 meta fields
+ 5 base/context fields
+ 6 ROI × 51 features per ROI
+ 31 best_* global rPPG quality fields
+ 5 label/clinical fields

2 + 5 + 306 + 31 + 5 = 349
```

Meta fields:

```text
subject_id, split
```

Base/context fields:

```text
fps, n_frames, xgb_diabetes_probability, ppg_hr_bpm, ppg_snr_db
```

Labels/clinical fields:

```text
patient_id, diabetes_strict_label, hba1c_lab_diabetes, hba1c_elevated_risk, hba1c
```

ROI set used in the smoke implementation:

```text
FACE, FOREHEAD, LEFT_CHEEK, RIGHT_CHEEK, NOSE, CHIN
```

Each ROI contributes 51 features:

```text
12 RGB dynamic stats      = r/g/b × mean/std/cv/ptp
12 HSV/Lab color stats    = hsv h/s/v mean/std + lab l/a/b mean/std
27 rPPG metrics           = green/POS/CHROM × 9 metrics
```

The 9 rPPG metrics per method:

```text
hr_bpm
snr_db
peak_power
total_power
pearson_vs_ppg
spearman_vs_ppg
xcorr_max_vs_ppg
hr_ppg_bpm
hr_abs_error_bpm
```

## Why subject-level aggregation is required

Explain in this order:

1. Diabetes/HbA1c is a subject health state, not a frame/video-fragment label.
2. One subject can have multiple videos; random video-level split leaks identity and inflates metrics.
3. Subject-level output matches product behavior: one user -> one risk assessment.
4. It enables subject-level split, aggregation, correlation analysis, and shallow smoke modeling.

Current aggregation logic from the session:

```python
numeric_cols = video_df.select_dtypes(include=[np.number]).columns.tolist()
drop_from_mean = {"patient_id", "diabetes_strict_label", "hba1c_lab_diabetes", "hba1c_elevated_risk", "hba1c"}
agg_cols = [c for c in numeric_cols if c not in drop_from_mean]
subject_df = video_df.groupby(["subject_id", "split"], as_index=False)[agg_cols].mean(numeric_only=True)
first_cols = ["patient_id", "diabetes_strict_label", "hba1c_lab_diabetes", "hba1c_elevated_risk", "hba1c"]
first = video_df.groupby("subject_id", as_index=False)[first_cols].first()
subject_df = subject_df.merge(first, on="subject_id", how="left")
```

Interpretation:

- Numeric face/video features are averaged across videos for the same subject.
- Labels are not averaged; they are subject labels and are carried through.
- This is a simple smoke-stage aggregation, not the final best method.

Future aggregation upgrades to recommend:

- median aggregation
- quality-weighted mean
- best-quality-video selection
- camera/view/step stratified aggregation
- attention pooling or temporal/video encoder once sample size supports it

## Alignment checklist vs a face-video diabetes technical plan

Aligned:

- Face video is the source modality.
- Landmark/ROI extraction is used.
- Lab/HSV/RGB color features exist.
- rPPG/microvascular dynamic features exist.
- HbA1c is used as supervision/validation.
- Subject-level split/aggregation prevents leakage.
- Results retain non-diagnostic caveats.

Not yet reached, but not drift:

- 60-second production windows; smoke used max 120 frames/video.
- 8 refined ROI; smoke used 6 rectangular landmark-aware ROI.
- EVM/Nadimi dynamic erythema features.
- RR/SpO2/SBP/DBP/vascular-age rPPG service outputs.
- Multi-task age/BMI/BP heads.
- MLP/Transformer face-video encoder.
- Production inference API with face video as the only required input.

Potential drift/pitfalls:

- Do not let `xgb_diabetes_probability` become a required product input.
- Do not let PPG reference become a product input.
- Do not call 16-subject RF AUC product performance.
- Do not pivot the project back to pure tabular/health-profile modeling.

## Response/document shape

For user-facing docs, use these sections:

1. subject-level 是什么
2. 349 列怎么来的
3. 每类字段是什么、为什么做
4. video-level 到 subject-level 如何聚合
5. 输入是什么、输出是什么
6. 当前做到了什么程度
7. 与技术方案是否偏移
8. 当前不足与下一步建议

Prefer Chinese for this user/project unless asked otherwise.
