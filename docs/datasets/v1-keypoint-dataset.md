# V1 Keypoint Dataset Collection

V1 builds a keypoint-level dataset from the downloaded media datasets:

- `datasets/stroke_media_dataset_20260119`
- `datasets/stroke_warning_app_media_dataset_20260508`

The collection script indexes each eligible image and the first frame of each eligible video, then runs a MediaPipe detector and writes normalized landmarks.

For the current patient-level V1 data workflow, use the by-name pipeline instead:

```bash
scripts/run_in_project_env.sh python scripts/build_facesym_v1_dataset_from_by_name.py \
  --output datasets/facesym_v1_by_name_20260119 \
  --roles front,smile,teeth
```

That workflow writes per-stage results and reports under `datasets/facesym_v1_by_name_20260119`. See `docs/datasets/facesym-v1-by-name-data-flow.md`.

## MediaPipe Base

The external MediaPipe source tree is expected at:

```text
third_party/mediapipe
```

The runtime detector uses the Python `mediapipe` package API. Install or build that runtime in the project environment before running actual detection:

```bash
scripts/run_in_project_env.sh python -m pip install '.[vision]'
```

The current project environment has `mediapipe 0.10.35`, which exposes the Tasks API but not legacy `mp.solutions.face_mesh`. For the technical solution's Face Landmarker path, keep the model bundle at:

```text
models/mediapipe/face_landmarker.task
```

If MediaPipe is not installed, the collection script can still produce a dry-run sample index.

For ad hoc local image checks, use:

```bash
scripts/run_in_project_env.sh python scripts/detect_mediapipe_image.py \
  path/to/local-image.jpg \
  --output tmp/facesymai-mediapipe-result.json \
  --annotated-output tmp/mediapipe_annotated \
  --pretty
```

Run a dataset smoke test with annotated landmark images:

```bash
scripts/run_in_project_env.sh python scripts/run_mediapipe_landmarker_dataset_smoke.py \
  --roles front,smile,teeth,front_contour,smile_teeth \
  --limit-per-role 10 \
  --output tmp/mediapipe_landmarker_dataset_test
```

This writes:

- `metadata/results.csv`: per-sample status and annotation paths.
- `metadata/summary.json`: aggregate detection counts.
- `detections/<dataset>/<sample_id>.json`: Face Landmarker payload.
- `annotated/<dataset>/<sample_id>.jpg`: source image with 478 raw landmarks and semantic landmarks overlaid.

## Commands

Build only the V1 sample index:

```bash
python scripts/collect_v1_keypoint_dataset.py --dry-run
```

Run MediaPipe extraction:

```bash
scripts/run_in_project_env.sh python scripts/collect_v1_keypoint_dataset.py
```

Limit scope while validating:

```bash
scripts/run_in_project_env.sh python scripts/collect_v1_keypoint_dataset.py --limit 20
```

Include only front-facing roles:

```bash
scripts/run_in_project_env.sh python scripts/collect_v1_keypoint_dataset.py \
  --roles front,front_contour
```

## Output

Default output:

```text
datasets/v1_keypoint_dataset
```

Files:

- `metadata/v1_samples.csv`: one row per image or sampled video frame.
- `metadata/v1_keypoints.jsonl`: one line per detected sample.
- `metadata/v1_summary.json`: aggregate counts.
- `keypoints/<source_dataset>/<sample_id>.json`: per-sample MediaPipe payload.

## Landmark Mapping

`src/facesymai/landmarks/mediapipe_face_landmarker.py` and `src/facesymai/landmarks/mediapipe_face_mesh.py` map MediaPipe landmark indices into the named points used by the current symmetry analyzer, including eye corners, brow points, mouth corners, nostrils, cheeks, jaw points, nose bridge, nose tip, and chin.

V1 uses the first frame for each video. Later versions can add multi-frame sampling, frame quality selection, face tracking, and split generation.
