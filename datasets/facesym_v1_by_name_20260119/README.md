# FaceSymAi V1 By-Name Dataset

This dataset is derived from `datasets/stroke_patient_outcome_by_name_20260119` for V1 static-image facial symmetry analysis.

## Stages

1. `01_manifest`: select V1 static-image roles.
2. `02_quality_gate`: record current image quality gate output.
3. `03_keypoints`: run MediaPipe Face Landmarker and write landmark overlays.
4. `04_features`: compute image-level and patient-level FaceSymAi features, including overall symmetry and five component attributes.
5. `05_patient_splits`: create deterministic patient-level train/val/test splits.
6. `06_baseline_evaluation`: evaluate the current rule baseline against available outcome labels.

## Important

The label is patient outcome (`患病`/`不患病`), not a direct facial-asymmetry ground truth label. Metrics are technical signal checks and must not be described as diagnostic performance.
