# MCD-rPPG ROI visualization, FaceSym 478 landmarks, and geometry features

Use this reference when the user asks to visualize face-video ROIs, explain how a frame becomes ROI/rPPG/color features, or reconcile MediaPipe 468-point language with current FaceSym API results.

## Durable correction

Current Diabetes_Risk_Assessment engineering must treat FaceSym API output as the interface of record:

```text
raw_landmarks_xy:      T × 478 × 2
semantic_landmarks_xy: T × 25 × 2
roi_boxes:             T × 6 × 4
roi_rgb:               T × 6 × 3
ppg_aligned:           T
frame_indices:         T
```

Traditional “MediaPipe FaceMesh 468 points” is only historical/paper background. For current docs, task specs, code comments, and explanations, say:

```text
FaceSym API / MediaPipe Face Landmarker: 478 raw landmarks + 25 semantic landmarks
```

If `docs/diabetes_tech_solution_final.md` or a derived document still says 468, update it to 478 and note that implementation follows FaceSym API results.

## ROI visualization pattern

When the user asks for “从一个视频取一张图，把 6 个 ROI 画在人脸上”:

1. Pick a sample row from `mcd_rppg_reference/facesym_roi_balanced_subset/sample_selection.csv` whose source video and `.npz` cache exist.
2. Load the matching cache from `mcd_rppg_reference/facesym_roi_balanced_subset/<video_id>.npz`.
3. Choose a valid frame index, often the middle detected frame: `idx = len(frame_indices)//2`.
4. Read that frame from `video_path` with OpenCV.
5. Draw:
   - raw 478 landmarks as small gray dots,
   - 25 semantic landmarks as red dots,
   - six ROI boxes with labels: `FACE`, `FOREHEAD`, `LEFT_CHEEK`, `RIGHT_CHEEK`, `NOSE`, `CHIN`.
6. Save a JPG plus a JSON metadata file containing `video_id`, `subject_id`, `frame_index`, landmark shapes, ROI names, and ROI coordinates.
7. Verify the image exists and report image size/bytes.

A reusable project script from the session:

```text
scripts/visualize_mcd_rppg_6roi_example.py
```

Expected outputs:

```text
reports/roi_visualization/mcd_rppg_6roi_landmark_example.jpg
reports/roi_visualization/mcd_rppg_6roi_landmark_example_metadata.json
```

## Current 6 ROI derivation

The current smoke-stage ROI boxes are landmark-aware rectangular ROIs:

```text
FACE, FOREHEAD, LEFT_CHEEK, RIGHT_CHEEK, NOSE, CHIN
```

Core function location/pattern:

```text
scripts/extract_facesym_roi_smoke.py::landmark_aware_roi_boxes
scripts/extract_facesym_roi_balanced_subset.py imports the same function
```

Logic:

```python
x0, y0 = raw_points.min(axis=0)
x1, y1 = raw_points.max(axis=0)
face_w = x1 - x0
face_h = y1 - y0

FACE = whole raw-landmark bbox
FOREHEAD = brow_center shifted upward by 0.14 * face_h
LEFT_CHEEK = box around semantic left_cheek, 0.24 * face_w × 0.20 * face_h
RIGHT_CHEEK = box around semantic right_cheek, 0.24 * face_w × 0.20 * face_h
NOSE = box around mean(nose_tip, nose_bridge), 0.20 * face_w × 0.22 * face_h
CHIN = box around semantic chin, 0.28 * face_w × 0.16 * face_h
```

Clarify left/right carefully: FaceSym semantic left/right may not match visual image-left/image-right if camera mirroring is involved. For product docs, define whether left/right means anatomical subject-side or image-side.

## Feature extraction explanation

Explain frame-to-feature as:

```text
video frame -> FaceSym detection -> 478 raw landmarks + 25 semantic landmarks
-> 6 ROI boxes -> per-frame ROI RGB mean -> ROI RGB time series
-> color stats + HSV/Lab stats + green/POS/CHROM rPPG metrics
-> video_features.csv -> subject_features.csv
```

Per ROI feature groups:

- RGB dynamic stats: `r/g/b × mean/std/cv/ptp` = 12.
- HSV/Lab color stats: `h/s/v/l/a/b × mean/std` = 12.
- rPPG metrics: `green/POS/CHROM × 9 metrics` = 27.

The 9 rPPG metrics are:

```text
hr_bpm, snr_db, peak_power, total_power,
pearson_vs_ppg, spearman_vs_ppg, xcorr_max_vs_ppg,
hr_ppg_bpm, hr_abs_error_bpm
```

PPG-derived fields are research/quality validation only. They must not become required product inference inputs.

## Geometry status and next step

Current caches already preserve geometry signals:

```text
raw_landmarks_xy, semantic_landmarks_xy, roi_boxes
```

Current subject features mainly use color/rPPG; full geometry features are not yet systematically engineered into `subject_features.csv`.

When explaining status, use:

```text
关键点已经缓存；几何信息已经用于 ROI 定位和 ROI 稳定性检查；但系统性的 478 点几何特征尚未完整进入 subject-level 模型。
```

Recommended next geometry features:

- face bbox width/height/area and aspect ratio
- cheek-to-cheek distance
- nose-to-chin distance
- brow-to-chin distance
- ROI area mean/std/CV
- landmark motion mean/std across frames
- pose proxies from eye/nose/jaw asymmetry
- quality flags for hair/eye/lip/background overlap once masks are available

## Documentation pitfall

If the user asks to update a technical plan, do not leave mixed 468/478 wording in primary project docs. Update all primary engineering statements to 478 and reserve 468 only for literature background with an explicit caveat.
