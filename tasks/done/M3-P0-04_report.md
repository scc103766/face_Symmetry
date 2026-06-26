# M3-P0-04 Completion Report

## Scope

- Source task: `tasks/queue/M3-P0-04.md`
- Goal: add a tooth-lip color channel to `/louyachi` while preserving existing geometry-only callers.
- Primary files changed:
  - `modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`
  - `modules/facial_asymmetry_service/facial_asymmetry_service/web_server.py`
  - `modules/mediapipe_face_keypoint_detector/face_keypoint_detector/api_server.py`

## Implementation

- Added mouth-interior color analysis behind `detect_teeth_exposure(detection, image_path=None)`.
- Added `INNER_LIP_INDICES`, `_crop_mouth_interior(...)`, `_teeth_color_score(...)`, `_analyze_mouth_color(...)`, plus a small landmark-to-pixel helper.
- Kept backward compatibility:
  - Existing calls without `image_path` still return the original geometry-only details.
  - Calls with `image_path` include `details.color_features`.
- Wired image paths through both HTTP services:
  - `facial_asymmetry_service` `/louyachi`
  - `mediapipe_face_keypoint_detector` `/louyachi`
- Color fusion behavior:
  - Geometry remains the primary detector.
  - Color can rescue likely open-mouth teeth cases.
  - Color can veto weak geometry only when mouth geometry is small/uncertain and tooth color is very low.

## Calibration Notes

The literal task seed thresholds (`S < 40`, `V > 150`, dark `V < 60`) were too strict on this dataset. A first HTTP full-eval attempt drove teeth recall down to `30/512 = 5.9%`, because many true teeth samples have warmer/dimmer tooth pixels or strong lip-color dominance inside the polygon.

Final constants were loosened and guarded by geometry:

- tooth-like: low saturation + bright enough value
- dark-mouth normalization: value below a darker threshold
- rescue requires sufficient `lip_gap` and `lip_area`
- veto is limited to small/uncertain mouth geometry

This produced the best observed balance for the requested targets without changing non-`/louyachi` action semantics.

## Validation

Commands passed:

```bash
scripts/run_in_project_env.sh python -m py_compile \
  modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py \
  modules/facial_asymmetry_service/facial_asymmetry_service/web_server.py \
  modules/mediapipe_face_keypoint_detector/face_keypoint_detector/api_server.py

scripts/run_in_project_env.sh python \
  modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py

env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi \
  scripts/run_in_project_env.sh pytest -q
```

Result: `64 passed, 3 warnings`.

HTTP smoke:

- Service port used: `18433`
- Reason: `18432` was already occupied by an existing unknown Python process, left untouched.
- `/api/health`: OK
- `/louyachi` sample:
  - `status=detected`
  - `teeth_exposure.detected=true`
  - `details.color_features` present
  - sample color features: `teeth_color_score=0.5529`, `teeth_ratio=0.6169`, `lip_ratio=0.7798`, `dark_ratio=0.1038`

Full API eval:

```bash
env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi \
  scripts/run_in_project_env.sh python scripts/eval_action_api_full.py \
  --api http://127.0.0.1:18433 --delay 0
```

Detailed output: `tmp/full_eval_action_api.json`

### /louyachi Result

| Role | Expected | Correct | Total | Acc |
| --- | --- | ---: | ---: | ---: |
| eyes_closed | False | 498 | 512 | 97.3% |
| forehead_wrinkle | False | 468 | 511 | 91.6% |
| front | False | 502 | 514 | 97.7% |
| frown | False | 482 | 511 | 94.3% |
| teeth | True | 384 | 512 | 75.0% |
| TOTAL | - | 2334 | 2560 | 91.2% |

Task target status:

- teeth recall `75.0%`: met minimum target `>=75%`.
- front `97.7%`: met target `>=97%`.
- eyes_closed `97.3%`: met target `>=97%`.
- forehead_wrinkle `91.6%`: below target `>=94%`.
- frown `94.3%`: below target `>=96%`.

## Constraints And Residual Risk

- The implementation is intentionally limited to teeth exposure and `/louyachi` path plumbing.
- The current `action_detector.py` already contained side-view behavior based on `eye_gaze_blendshape` before this task run; it was not changed for M3-P0-04.
- Full eval still reports side-view and strabismus sections, but those are outside this task's requested modification.
- The remaining forehead/frown false positives overlap with true teeth on the available geometry/color features. Pushing them to the requested targets with the current color-only channel is likely to reduce teeth recall below 75%.

## Optimization Recommendations

1. Add a second non-color discriminator before raising thresholds: use upper/lower incisor edge contrast or connected bright-region width inside the mouth polygon, not just HSV ratios.
2. Split teeth exposure into front-facing and non-front-facing calibration buckets, because yaw/pose changes the visible tooth/lip color mix.
3. Add a small manually reviewed hard-negative set for forehead/frown false positives and tune against it separately from generic non-teeth samples.
4. Keep the current color channel as a guarded rescue/veto signal rather than a dominant classifier until the above features are added.

