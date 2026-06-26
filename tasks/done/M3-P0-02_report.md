## M3-P0-02 Report

### Task

动作检测三轮优化：侧脸多信号融合 + 斜视动态阈值 + 露齿宽松策略。

### Scope

- Modified: `modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`
- No other module was modified for this task.
- Existing `tasks/done/M3-P0-02_superseded.md` was left untouched.

### Implementation

- Side view:
  - Kept yaw thresholds `15/22/35`.
  - Kept eye-distance ratio threshold as `SIDE_VIEW_EYE_RATIO_THRESHOLD = 0.22`.
  - Added `SIDE_VIEW_FACE_RATIO_THRESHOLD = 0.55`.
  - Added `SIDE_VIEW_EYE_ASYMMETRY_THRESHOLD = 0.4`.
  - Combined four signals with OR:
    - `yaw_detected`
    - `eye_ratio_detected`
    - `face_detected`
    - `eye_asymmetry_detected`
  - Added details fields:
    - `face_width_ratio`
    - `eye_width_asymmetry`
    - individual signal booleans
- Strabismus:
  - Replaced fixed threshold with `_strabismus_threshold(yaw_deg)`.
  - Dynamic thresholds:
    - `abs(yaw) <= 10`: `0.5`
    - `abs(yaw) <= 20`: `0.65`
    - otherwise: `0.8`
  - Confidence now divides by dynamic threshold.
  - `head_pose_warning` confidence discount changed from `0.5` to `0.3`.
  - Details include dynamic `threshold` and `yaw`.
- Teeth exposure:
  - Kept base thresholds:
    - `TEETH_JAW_OPEN_THRESHOLD = 0.04`
    - `TEETH_LIP_STRETCH_THRESHOLD = 0.1`
  - Added loose/dominant thresholds:
    - `TEETH_JAW_OPEN_LOOSE = 0.08`
    - `TEETH_LIP_STRETCH_LOOSE = 0.08`
    - `TEETH_LIP_STRETCH_DOMINANT = 0.25`
  - Implemented the requested three-stage visible-teeth logic.

### Core Code References

- Threshold constants: `action_detector.py:8`
- Dynamic strabismus threshold usage: `action_detector.py:72`
- Teeth exposure relaxed strategy: `action_detector.py:132`
- Four-signal side-view fusion: `action_detector.py:193`
- `_strabismus_threshold()`: `action_detector.py:339`

### Verification

- Syntax:
  - `scripts/run_in_project_env.sh python -m py_compile modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`
  - Passed.
- Self-test:
  - `scripts/run_in_project_env.sh python modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`
  - Passed.
  - Mock results included:
    - strabismus: `detected=False`, threshold `0.5`, yaw `8.0`
    - teeth: `detected=True`, `mouth_state=teeth_visible`
    - side view: `detected=True`, yaw `56.31`, level `extreme`
- Tests:
  - `env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi scripts/run_in_project_env.sh pytest -q`
  - Result: `64 passed, 3 warnings`.
- API:
  - Restarted 18432 service with current code.
  - `api_server.py` has no direct module entrypoint, so the service was started via `api_server.main()` without modifying the file.
  - Ran:
    - `scripts/eval_action_api_full.py --api http://127.0.0.1:18432 --delay 0`
  - Full evaluation result:
    - Total images: `4115`
    - Face detection: `4099/4115`, `99.6%`
    - Side view total accuracy: `1572/2565`, `61.3%`
    - Side view left_profile: `263/512`, `51.4%`
    - Side view right_profile: `258/515`, `50.1%`
    - Strabismus total correctness: `2824/4099`, `68.9%`
    - Strabismus left_profile correctness: `33/512`, `6.4%`
    - Strabismus right_profile correctness: `95/515`, `18.4%`
    - Teeth exposure total correctness: `2193/2560`, `85.7%`
    - Teeth role recall: `197/512`, `38.5%`
  - Detailed result file:
    - `tmp/full_eval_action_api.json`

### Problems And Handling

- Full evaluation exposed that profile images are still difficult under the fixed task thresholds. Example checked manually:
  - `row0203_pid532_collect669__left_profile_01.jpg`
  - Required landmark keys are present.
  - Computed side-view details:
    - yaw `-3.209`
    - `face_width_ratio=2.2149`
    - `eye_width_asymmetry=0.9679`
    - no side-view signal triggered
  - This suggests the current MediaPipe projection and the task-provided ratio thresholds do not align for part of this dataset.
- Strabismus false positives remain high on profile-labeled images because the yaw fallback can remain near zero on some profile images, so dynamic threshold stays at `0.5`.
- Teeth role recall improved conservatively but remains below the task target of `50%`; specificity on non-teeth roles is high.

### Result

M3-P0-02 code changes are implemented and verified. Full evaluation shows the requested implementation is in place, but side-profile and teeth recall still need calibration beyond the fixed thresholds in the task.
