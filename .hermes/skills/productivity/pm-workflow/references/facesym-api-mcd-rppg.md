# FaceSym API + MCD-rPPG Preprocessing Pattern

Use this when a project uses an external FaceSymAi / MediaPipe face detection API to process face-video datasets such as MCD-rPPG.

## API shape discovered

Root endpoint with token can self-describe service capabilities:

```text
GET http://<host>:<port>/?token=<token>
```

Detection endpoint:

```text
POST http://<host>:<port>/api/detect?token=<token>
Content-Type: multipart/form-data
field: images  # repeatable; accepts jpg/jpeg/png
```

Returned structure includes:

- `results[].status`: `detected`, `no_face`, `multiple_faces`, `failed`.
- `results[].detection.backend`: e.g. `mediapipe_face_landmarker`.
- `results[].detection.raw_landmarks`: 478 MediaPipe normalized landmarks `{x,y,z,confidence}`.
- `results[].detection.landmarks`: semantic FaceSymAi keypoint mapping.
- `results[].detection.blendshapes`: expression/blendshape scores.
- `results[].detection.facial_transformation_matrixes`: face transform matrix.

Note: `/api/health` may require auth or return 401 without token; a 401 health check does not imply `/api/detect?token=...` is unusable.

## Safe integration pattern

1. Probe the root endpoint first to confirm endpoint shape and model path.
2. Extract one video frame with OpenCV and POST it as JPEG to `/api/detect?token=...`.
3. Inspect returned keys and save a temporary raw response for schema confirmation.
4. Add API support behind an explicit backend flag (e.g. `--face-backend facesym-api`) rather than replacing local fallback paths.
5. Convert normalized landmarks to pixel coordinates using current frame width/height.
6. Save `face_backend` in every cache (`facesym_api_mediapipe`) so downstream code knows the landmark source.
7. Run tiny smoke tests before larger batches:
   - 2 samples × 5 frames for schema/cache validation.
   - 10 samples × 30 frames for stability.
   - only then consider 10 × 120 or 100-sample tests.
8. Do not jump directly to all videos: per-frame HTTP POST can be much slower than local inference and can overload the service.

## Cache expectations after successful API integration

For a 30-frame smoke test:

```text
roi_rgb       shape=(30, 8, 3)
landmarks_xy  shape=(30, 478, 2)
face_bboxes   shape=(30, 4)
ppg_aligned   shape=(30,)
face_backend  facesym_api_mediapipe
```

## Pitfalls

- A local `mediapipe` import succeeding does not guarantee `mp.solutions.face_mesh` exists; newer installs may expose only Tasks API and may not ship model assets.
- OpenCV Haar fallback is acceptable for I/O smoke tests but not final ROI features.
- A bbox-derived 8-ROI feature is still approximate even with 478 landmarks; the next refinement should define forehead/cheek/nose/chin ROIs from semantic or raw landmarks.
- Preserve fallback paths (`opencv-haar`, local mediapipe if available) so the script remains usable when the external service is down.
