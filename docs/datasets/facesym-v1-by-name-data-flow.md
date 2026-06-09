# FaceSymAi V1 By-Name Data Flow

本文记录当前推荐数据处理流程。流程面向 V1 静态图片人脸对称性判断，从按患者组织的数据集出发，生成 MediaPipe 关键点、特征点绘制图、对称性特征、患者级切分和 baseline 评估报告。

## Input

- Source dataset: `datasets/stroke_patient_outcome_by_name_20260119`
- V1 roles: `front,smile,teeth`
- Label source: patient outcome group, `患病` / `不患病`
- Runtime: `scripts/run_in_project_env.sh`
- Model: `models/mediapipe/face_landmarker.task`

The label is not a direct facial-asymmetry ground truth label. It can support technical signal checks, but it cannot support diagnostic performance claims by itself.

## Command

```bash
scripts/run_in_project_env.sh python scripts/build_facesym_v1_dataset_from_by_name.py \
  --output datasets/facesym_v1_by_name_20260119 \
  --roles front,smile,teeth
```

Smoke-test command:

```bash
scripts/run_in_project_env.sh python scripts/build_facesym_v1_dataset_from_by_name.py \
  --limit-patients-per-label 2 \
  --output tmp/facesym_v1_by_name_smoke \
  --roles front,smile,teeth
```

The smoke output uses the project-local `tmp/` directory. Do not write FaceSymAi outputs to system `/tmp`.

## Stages

| Stage | Result files | Report |
| --- | --- | --- |
| `01_manifest` | `metadata/01_manifest.csv`, `metadata/01_manifest_summary.json` | `reports/01_manifest.md` |
| `02_quality_gate` | `metadata/02_quality_gate.csv`, `metadata/02_quarantined_images.csv`, `metadata/02_quality_gate_summary.json` | `reports/02_quality_gate.md` |
| `03_keypoints` | `metadata/03_keypoints.csv`, `metadata/03_keypoints_summary.json`, `keypoints/.../*.json`, `annotated/.../*.jpg` | `reports/03_keypoints.md` |
| `04_features` | `metadata/04_image_features.csv`, `metadata/04_patient_features.csv`, `metadata/04_features_summary.json` | `reports/04_features.md` |
| `05_patient_splits` | `metadata/05_patient_splits.csv`, `metadata/05_patient_splits_summary.json` | `reports/05_patient_splits.md` |
| `06_baseline_evaluation` | `metadata/06_baseline_predictions.csv`, `metadata/06_baseline_evaluation.json` | `reports/06_baseline_evaluation.md` |

The dataset-level summary is `metadata/pipeline_summary.json`.

Each stage report includes both aggregate metrics and an inline detail table. The corresponding `metadata/*.csv` file remains the machine-readable source of truth for filtering and follow-up review.

## Current Run

Output dataset:

```text
datasets/facesym_v1_by_name_20260119
```

Run summary:

- Patients: 505
- Images: 1546
- Patients by label: `患病` 336, `不患病` 169
- Images by role/label:
  - `患病/front`: 346
  - `患病/smile`: 342
  - `患病/teeth`: 346
  - `不患病/front`: 170
  - `不患病/smile`: 171
  - `不患病/teeth`: 171

Quality gate:

- `pass`: 938
- `review`: 15
- `reject`: 593
- `accepted_for_scoring=true`: 953
- Quarantined image detail rows: 593, see `metadata/02_quarantined_images.csv` and `reports/02_quality_gate.md`

MediaPipe Face Landmarker:

- `detected`: 1538
- `no_face`: 7
- `failed`: 1
- Raw landmarks per detected face: 478
- Blendshapes per detected face: 52
- Transformation matrix count: 1 or 2
- Annotated landmark images written: 1538

Feature and split outputs:

- Image feature rows: 1546
- Feature-ready images: 1538
- Patient feature rows: 505
- Static V1 symmetry outputs: `overall_symmetry_score`, `overall_asymmetry_severity`, `affected_side`
- Component attributes: `mouth`, `eye`, `brow`, `midline`, `contour`, each with `score`, `symmetry_score`, `side`, and `confidence`
- Coordinate standardization: fitted midline alignment from `nose_bridge/nose_tip/chin`, light roll correction, and eye-distance scale normalization before feature calculation
- Patient split: train 353, val 75, test 77

Current rule baseline:

- Rule: `max(front/smile/teeth advisory_confidence) >= threshold`
- Threshold source: validation split
- Threshold: `0.277158`
- Test precision: `0.662338`
- Test recall: `1.000000`
- Test specificity: `0.000000`

These metrics are a technical baseline against available outcome labels. They should be used to inspect signal, false positives, false negatives, quality issues, and label suitability.

## Comparison Group: All Images, No Quality Gate

新增对比组用于观察“不做 V1 manifest 角色筛选、不做质量门控”时的检测和 baseline 变化。它读取同一 by-name 数据集中的所有 `media_type=image` 图片，而不是只读取 `front,smile,teeth`。

Command:

```bash
scripts/run_in_project_env.sh python scripts/build_facesym_v1_all_images_no_gate_comparison.py \
  --output datasets/facesym_v1_all_images_no_gate_20260119
```

Smoke-test command:

```bash
scripts/run_in_project_env.sh python scripts/build_facesym_v1_all_images_no_gate_comparison.py \
  --limit-patients-per-label 1 \
  --skip-annotations \
  --output tmp/facesym_v1_all_images_no_gate_smoke
```

Output dataset:

```text
datasets/facesym_v1_all_images_no_gate_20260119
```

Stages:

| Stage | Result files | Report |
| --- | --- | --- |
| `01_all_images` | `metadata/01_all_images.csv`, `metadata/01_all_images_summary.json` | `reports/01_all_images.md` |
| `02_quality_gate_skipped` | `metadata/02_quality_gate_skipped.csv`, `metadata/02_quality_gate_skipped_summary.json` | `reports/02_quality_gate_skipped.md` |
| `03_keypoints` | `metadata/03_keypoints.csv`, `metadata/03_keypoints_summary.json`, `keypoints/.../*.json`, `annotated/.../*.jpg` | `reports/03_keypoints.md` |
| `04_features` | `metadata/04_image_features.csv`, `metadata/04_patient_features.csv`, `metadata/04_features_summary.json` | `reports/04_features.md` |
| `05_patient_splits` | `metadata/05_patient_splits.csv`, `metadata/05_patient_splits_summary.json` | `reports/05_patient_splits.md` |
| `06_baseline_evaluation` | `metadata/06_baseline_predictions.csv`, `metadata/06_baseline_evaluation.json` | `reports/06_baseline_evaluation.md` |

Current comparison run:

- Patients: 505
- Images: 5195
- Image roles: `front`, `smile`, `teeth`, `eyes_closed`, `forehead_wrinkle`, `frown`, `left_profile`, `right_profile`, `tongue_bottom`, `tongue_surface`, `auxiliary_exam_image`, `medical_record`
- Quality gate: skipped; excluded images: 0
- MediaPipe Face Landmarker: `detected` 5005, `no_face` 189, `failed` 1
- Annotated landmark images written: 5005
- Feature-ready images: 5005
- Patient feature rows: 505
- Patient score source: `max_image_advisory_confidence_no_quality_gate`
- Patient split: train 353, val 75, test 77
- Threshold source: validation split
- Threshold: `0.555802`
- Test precision: `0.662338`
- Test recall: `1.000000`
- Test specificity: `0.000000`
- Test confusion matrix: `TP=51`, `FP=26`, `TN=0`, `FN=0`

Important interpretation: this comparison group intentionally includes non-V1 and non-face-oriented image roles such as profiles, tongue images, auxiliary exam images, and medical record images. It is useful for checking false positives, detector behavior, and the value of manifest/quality filtering. It is not the formal V1 validation flow.

## Review Points

- Review `reports/03_keypoints.md` and sample `annotated/.../*.jpg` to confirm landmarks sit on the face.
- Review `metadata/03_keypoints.csv` rows with `no_face` and `failed`.
- Review `reports/06_baseline_evaluation.md` together with `metadata/06_baseline_predictions.csv`; do not quote metrics without dataset version, threshold, and label definition.
- Decide whether V1 needs a new human-reviewed facial-asymmetry label instead of patient outcome labels.
