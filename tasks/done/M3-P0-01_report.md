## M3-P0-01 Report

### Task

62 规则软评分 + 姿态校准。

### Scope

- Modified: `modules/facial_asymmetry_service/facial_asymmetry_service/rule62.py`
- Not modified: `feature_extractor.py`, `web_server.py`, `api_server.py`, CSV metadata.
- Note: `rule62.py` already had unrelated uncommitted changes before this task; they were preserved.

### Implementation

- Added `SCORE_SCALE_FACTOR = 0.65`.
- Kept binary attribution semantics:
  - `triggered`
  - `weighted_contribution`
  - `triggered_weight`
- Changed final `weighted_disease_score` accumulation to use `medical_priority_evidence_score` instead of binary feature contribution.
- Added adjusted decision threshold:
  - `adjusted_threshold = config.score_threshold * SCORE_SCALE_FACTOR`
  - `predicted = bool(detected_rows) and score >= adjusted_threshold`
- Added yaw calibration:
  - `_yaw_discount(detected_rows)` reads `features["pose_yaw_abs_deg"]`.
  - No yaw values: `1.0`
  - `avg_abs_yaw <= 15`: `1.0`
  - Otherwise: `max(0.5, 1.0 - (avg_yaw - 15.0) / 60.0)`
- Applied yaw discount only to geometry-like features:
  - prefix: `raw_`
  - keyword: `region`
- Added output fields for internal analysis:
  - `raw_score_threshold`
  - `score_scale_factor`
  - `yaw_discount`
  - per-feature `is_geometry_feature`

### Core Code References

- Constants and geometry matching: `rule62.py:17`
- Adjusted threshold in config summary: `rule62.py:54`
- Soft score accumulation and geometry yaw discount: `rule62.py:131`
- Adjusted prediction threshold and analysis output: `rule62.py:201`
- `_yaw_discount()` helper: `rule62.py:238`

### Verification

- Syntax:
  - `scripts/run_in_project_env.sh python -m py_compile modules/facial_asymmetry_service/facial_asymmetry_service/rule62.py modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`
  - Passed.
- Tests:
  - `env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi scripts/run_in_project_env.sh pytest -q`
  - Result: `64 passed, 3 warnings`.
- API:
  - Restarted 8790 service with current code.
  - POSTed front + left_profile + right_profile images from `row0203_pid532_collect669` to `/api/analyze`.
  - HTTP status: `200`
  - Top-level status: `analyzed`
  - `detected_image_count`: `3`
  - `weighted_disease_score`: `0.540004`
  - adjusted `score_threshold`: `0.357163`
  - `score_margin`: `0.182841`
  - `predicted_high_asymmetry`: `true`

### Problems And Handling

- First full pytest run failed because the project root was not on `PYTHONPATH`; reran with `PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi`, and the suite passed.
- The public `/api/analyze` response filters some internal diagnostic fields, so `raw_score_threshold` and `yaw_discount` are not visible in the public report. The adjusted threshold and `score_margin` are visible and validated.

### Result

M3-P0-01 is implemented and verified.
