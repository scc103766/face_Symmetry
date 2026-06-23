# MCD-rPPG EVM feature extraction with scale/health supervision

Use this reference when the user wants to push the face-video diabetes-risk pipeline forward after video capture and ROI extraction, especially when they mention MCD-rPPG has scale/health-profile fields that can supervise video training.

## Trigger phrases

- “MCD-rPPG 数据集具有量表”
- “量表数据作为视频训练监督信号”
- “已经完成人脸视频采集和 ROI 区域提取”
- “进行欧拉视频放大的特征提取”
- “EVM / 欧拉视频放大 / 动态红度 / 颜色放大特征”

## PM stance

Treat this as a face-video-first milestone, not a pure tabular-health task. The scale/health fields are supervision or auxiliary-task targets/context; they are not a replacement for the face-video branch.

Use this framing:

```text
face video -> landmarks/ROI -> ROI RGB time series -> EVM/rPPG/color dynamics -> subject-level video features -> supervised by HbA1c/scale/health fields
```

## Practical implementation pattern

If ROI caches already exist, do not wait for a full rendered EVM-video implementation before extracting useful features. A good M2 feature step is:

1. Load existing FaceSym ROI cache `.npz` files.
2. Read `roi_rgb` as `T × ROI × 3` RGB time series.
3. Apply EVM core signal operation per ROI/channel:
   - detrend and mean-normalize channel time series;
   - temporal band-pass in pulse/microvascular range, e.g. `0.7–4.0 Hz`;
   - amplify with `alpha`, e.g. `30`;
   - compute dynamic statistics rather than rendering video.
4. Extract per ROI/channel features:
   - band mean/std/rms/abs_mean/ptp;
   - magnified std/ptp;
   - slope_abs_mean;
   - zero crossings;
   - peak frequency/BPM, peak power, total power, SNR;
   - cross-channel R-G / R-B band correlations;
   - R/G band RMS ratio.
5. Aggregate video-level features to subject-level by subject split.
6. Preserve scale/health/label fields only as targets/context:
   - age, BMI, BP, saturation, temperature, hemoglobin, HbA1c, cholesterol, respiratory, rigidity, pulse, stress;
   - `hba1c_lab_diabetes`, `hba1c_elevated_risk`, `diabetes_strict_label`, model probability if already present.
7. Output both machine-readable features and a PM-readable report.

## Recommended artifacts

```text
scripts/extract_mcd_rppg_evm_features.py
features/mcd_rppg_evm/video_evm_features.csv
features/mcd_rppg_evm/subject_evm_features.csv
features/mcd_rppg_evm/evm_feature_summary.json
reports/mcd_rppg_evm_feature_report.md
reports/mcd_rppg_evm_hba1c_correlation_report.md
tasks/done/task_M2-FEATURE-03_evm_features_report.md
```

Also update `WORK_STATUS.md` and `PROJECT_CONTEXT.md` with a compact, verified summary.

## Validation checklist

Run and report real outputs:

```text
python -m py_compile scripts/extract_mcd_rppg_evm_features.py
python scripts/extract_mcd_rppg_evm_features.py
```

Then verify:

- output files exist;
- video/subject shapes are printed;
- EVM feature column count is nonzero;
- required supervision columns such as `hba1c`, `stress`, `pulse`, `respiratory`, `rigidity` are present;
- no label/scale fields are described as face-derived video input features.

## Exploratory correlation check

After EVM feature extraction, it is useful to compute a lightweight subject-level correlation report against HbA1c or scale targets. Keep this strictly exploratory:

- n is usually small;
- feature count is high;
- apply multiple-comparison correction such as Benjamini-Hochberg FDR;
- a large raw Spearman rho is only a candidate signal if q is not significant.

Phrase carefully:

```text
Top EVM-HbA1c correlations are hypothesis-generating only. They justify the next smoke test, not a clinical/product claim.
```

## Caveats to include in reports

1. This feature-first EVM implementation is ROI time-series EVM core logic, not full spatial pyramid video rendering.
2. Small balanced ROI subsets, e.g. 87 videos / 16 subjects, cannot support product performance claims.
3. Short windows, e.g. ~120 frames, limit spectral resolution; longer windows should be a follow-up.
4. The output is risk-assessment research tooling, not diagnosis and not camera-based glucose/HbA1c measurement.
5. Scale/health fields can supervise or calibrate video models, but the product objective remains face-video-first risk assessment.

## Next-step decision after EVM extraction

Ask for approval before continuing. Recommended next task:

```text
M2-MODEL-02: merge EVM + rPPG + HSV/Lab/color subject-level features, then run leak-safe subject-level smoke tests supervised by HbA1c/scale targets.
```

Suggested ablations:

- EVM only;
- rPPG only;
- static/dynamic color only;
- EVM + rPPG;
- EVM + rPPG + color;
- optional multi-task targets for HbA1c, pulse/stress/respiratory/rigidity if sample size permits.
