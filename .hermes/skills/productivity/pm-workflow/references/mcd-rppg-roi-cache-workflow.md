# MCD-rPPG FaceSym ROI cache workflow

Use this reference when continuing the face-health / MCD-rPPG pipeline after strict split creation, especially tasks like `M2-ROI-*` and `M2-FEATURE-*`.

## Proven staged sequence

1. **Do not jump from dataset audit directly to model training.** Use a staged engineering ladder:
   - dataset audit + label caveats
   - strict subject-level split
   - tiny ROI smoke test
   - small balanced ROI cache expansion
   - rPPG / color feature quality analysis
   - shallow feature models and ablations
   - only later DNN / Transformer models
2. **Always preserve subject-level split.** MCD-rPPG has 600 subjects and 3600 videos; the same subject has multiple videos. Random video-level split causes identity leakage.
3. **Treat MCD-rPPG labels as exploratory risk labels.** `glycated_hemoglobin` supports HbA1c risk labels, but it is not full clinical diagnosis. Keep lab labels, model probabilities, and strict pseudo-labels separate.

## M2-ROI-01 smoke test pattern

Purpose: prove the end-to-end FaceSym -> landmarks -> ROI -> RGB/PPG cache path works before scaling.

Recommended scope:
- sample train/val/test
- include both strict positive and strict negative where available
- use very small max frames, e.g. 20
- output `.npz` plus `summary.csv/json` and stats

Required cache arrays:
- `roi_rgb`: `(T, 6, 3)`
- `raw_landmarks_xy`: `(T, 478, 2)`
- `semantic_landmarks_xy`: `(T, 25, 2)`
- `roi_boxes`: `(T, 6, 4)`
- `ppg_aligned`: `(T,)`
- `frame_indices`: `(T,)`

Standard ROI order:
`FACE`, `FOREHEAD`, `LEFT_CHEEK`, `RIGHT_CHEEK`, `NOSE`, `CHIN`.

## M2-ROI-02 balanced subset pattern

Purpose: validate engineering stability and throughput, not model performance.

Proven scope used successfully:
- train: 20 strict positive + 40 strict negative/low-risk videos
- val: 6 strict positive + 12 strict negative/low-risk videos
- test: 3 strict positive + 6 strict negative/low-risk videos
- max frames: 120
- total: 87 videos, about 10k frame calls

Expected outputs:
- `sample_selection.csv`
- `summary.csv` / `summary.json`
- `smoke_stats.json`
- `api_timing_summary.json`
- `roi_stability_summary.csv` / `.json`
- one `.npz` per successful video

Required summary metrics:
- video success rate
- `frames_read`
- `frames_with_face`
- frame-level face success rate
- API call count / fail count / latency
- estimated full-run time for 3600 videos × configured frames
- bad cache count
- split × label counts

Required ROI stability metrics per video × ROI:
- mean/std/min/max area
- area coefficient of variation
- missing rate
- box center jitter
- bad area frame count
- suspicious ROI flag

A successful run in this environment processed 87/87 videos, 10413 frames read, 10341 frames with face, face success rate ≈ 0.993, API fail count 0, bad cache count 0, suspicious ROI flag 0. Treat these as sanity checks, not hard invariants.

## Throughput and timeout handling

The balanced subset can exceed a 10-minute foreground tool timeout. If foreground execution times out but `.npz` caches were written, do **not** discard the partial work. Improve the extractor to be resumable:

- If an output `.npz` already exists and validates, load it and compute summary/stability rows instead of re-calling the FaceSym API.
- Continue processing missing/invalid caches only.
- Write final summary/stats after the resumed pass completes.

This captures the useful retry pattern without encoding a permanent claim that the API or tool is broken.

## Important pitfalls

- Do not report M2-ROI results as diabetes prediction performance. ROI cache tasks do not produce AUC/sensitivity/specificity.
- Do not go directly to CNN/ViT or Transformer after ROI cache success. First extract rPPG/color features and verify signal quality against PPG ground truth.
- Current landmark-aware ROIs are rectangular regions, not skin segmentation masks. Later feature work may need skin masks, white-balance normalization, and highlight removal.
- Avoid `row.attr`/`r.view` style access when generating IDs from pandas rows; use bracket access such as `row["view"]` because column names can collide with Series methods.

## Recommended next task after M2-ROI-02

`M2-FEATURE-01`: use the balanced ROI caches to extract rPPG and color features, validate rPPG quality against PPG ground truth, and only then consider shallow diabetes-risk association models.

## P1-02 full-scale pattern (3600 videos)

Purpose: scale FaceSym ROI extraction to all 3600 MCD-rPPG videos after smoke/balanced-subset validation succeeds. This is the bridge from engineering validation to model-ready data.

Key differences from M2-ROI-02:
- Input: reads all rows directly from `mcd_rppg_gold.csv` (or equivalent manifest with `diabetes_gold_label`), not from split-based balanced sampling.
- Video ID format: `mcd_video_{patient_id}_{camera}_{step}_{view}` — use bracket access (`row["view"]`, not `row.view`) to avoid pandas method collisions.
- Labels: use `diabetes_gold_label` (HbA1c >= 6.5) instead of the old multi-source `diabetes_strict_label`/`xgb_diabetes_probability` system.

Checkpoint/resume design:
- `validate_cache(npz_path)` — checks file existence + required key presence + array shapes. Any valid cache is skipped.
- `--start N` flag for manual resume from a specific row index.
- Progress logged to `cache_progress.log` with timestamp, status, video_id, gold label, frame/face counts, elapsed time.
- Summary written to `summary.csv` and `run_stats.json` after completion.

Expected runtime: ~3.7 hours for 3600 videos × 120 frames at ~32.7 fps (based on balanced subset benchmark). Run in background with checkpoint/resume; the user can interrupt and restart anytime.

Script template: `scripts/extract_facesym_roi_full.py` in the project — adapt the API URL and input CSV path for each project.

After completion: proceed to P2 feature extraction (rPPG + color + EVM) using the full ROI cache.
