# MediaPipe Local Image Runtime

## Current State

- Project environment: `anti-spoofing_scc_175`.
- Installed runtime verified locally:
  - `mediapipe 0.10.35`
  - `opencv-python/cv2 4.13.0`
- The installed MediaPipe package exposes the Tasks API (`mp.tasks`) but does not expose the legacy `mp.solutions.face_mesh` API.
- The project now keeps the Face Landmarker model bundle at:

```text
models/mediapipe/face_landmarker.task
```

The model was downloaded from the official MediaPipe Face Landmarker model bundle URL:

```text
https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task
```

## Local Image Detection

Run detection for one image:

```bash
scripts/run_in_project_env.sh python scripts/detect_mediapipe_image.py \
  path/to/local-image.jpg \
  --output tmp/facesymai-mediapipe-result.json \
  --annotated-output tmp/mediapipe_annotated \
  --pretty
```

Run detection and the current symmetry analyzer:

```bash
scripts/run_in_project_env.sh python scripts/detect_mediapipe_image.py \
  path/to/local-image.jpg \
  --output tmp/facesymai-mediapipe-result.json \
  --pretty \
  --include-analysis
```

Run a directory:

```bash
scripts/run_in_project_env.sh python scripts/detect_mediapipe_image.py \
  path/to/image-dir \
  --recursive \
  --output datasets/local_mediapipe_outputs \
  --annotated-output tmp/mediapipe_annotated \
  --pretty
```

Run the current dataset smoke test with face landmark overlays:

```bash
scripts/run_in_project_env.sh python scripts/run_mediapipe_landmarker_dataset_smoke.py \
  --roles front,smile,teeth,front_contour,smile_teeth \
  --limit-per-role 10 \
  --output tmp/mediapipe_landmarker_dataset_test
```

## Model Selection

Default lookup order:

1. `--model /absolute/path/to/face_landmarker.task`
2. `FACESYMAI_MEDIAPIPE_FACE_LANDMARKER_MODEL`
3. `models/mediapipe/face_landmarker.task`

Example with an explicit model:

```bash
scripts/run_in_project_env.sh python scripts/detect_mediapipe_image.py \
  path/to/local-image.jpg \
  --backend face_landmarker \
  --model models/mediapipe/face_landmarker.task \
  --output tmp/facesymai-mediapipe-result.json
```

## Output Contract

The script writes a JSON object per image:

```json
{
  "input": {
    "path": "path/to/local-image.jpg",
    "image_id": "local-image"
  },
  "runtime": {
    "backend": "face_landmarker"
  },
  "status": "detected",
  "detection": {
    "detector": "mediapipe_face_landmarker",
    "face_count": 1,
    "landmark_schema_version": "facesymai-landmarks-v1",
    "landmarks": {},
    "raw_landmarks": [],
    "blendshapes": {},
    "facial_transformation_matrixes": []
  }
}
```

`status` can be:

- `detected`
- `no_face`
- `multiple_faces`
- `failed`

## What The User Needs To Provide

For local smoke tests:

- One or more local image paths.
- Prefer clear front-facing or teeth/smile images; side profiles and tongue images are not V1 scoring inputs.

For strict reproduction:

- The exact Face Landmarker `.task` model if you do not want to use the downloaded official latest bundle.
- Any required checksum or model approval record if the deployment process needs traceability.

For dataset-level evaluation:

- Which media roles should be included, for example `front`, `smile`, `teeth`.
- Label definition and evaluation split rules.
- Acceptance thresholds for `no_face`, `multiple_faces`, quality rejects, and scoring metrics.

## Notes

- The current adapter maps MediaPipe 478-point output into the FaceSymAi semantic landmark schema used by the existing feature extractor.
- Face Landmarker returns blendshape scores and facial transformation matrices when enabled.
- The legacy FaceMesh adapter remains in code as a fallback for environments that still expose `mp.solutions.face_mesh`, but it is not runnable in the current verified environment.
