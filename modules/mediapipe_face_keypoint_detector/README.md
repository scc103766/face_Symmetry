# MediaPipe Face Keypoint Detector Module

本目录是 FaceSymAi 当前 MediaPipe 输入/输出能力抽出的可复用模块，只负责人脸关键点检测。它既可以启动为 HTTP API 服务，也可以把整个文件夹复制到其他机器，作为离线 SDK 直接调用。

它不做人脸对称性判断，不输出患病/不患病结论。后续人脸对称性服务应把本模块输出的 `detection` JSON 作为输入。

## 代码来源

本模块从当前项目已验证的 MediaPipe 代码整理而来，核心来源包括：

- `src/facesymai/landmarks/mediapipe_face_landmarker.py`
- `src/facesymai/landmarks/mediapipe_face_mesh.py`
- `src/facesymai/landmarks/visualization.py`
- `scripts/detect_mediapipe_image.py`

整理时去掉了质量门控、风险评分和人脸对称性分析调用，只保留关键点检测、输出 schema、叠加图绘制和 CLI。

## 模块边界

输入：

- `.jpg`、`.jpeg`、`.png` 静态人脸图片。
- 推荐单人脸、正向或接近正向、无遮挡、光照足够。

输出：

- `status`: `detected`、`no_face`、`multiple_faces`、`failed`
- `detection.raw_landmarks`: MediaPipe Face Landmarker 原始 478 点。
- `detection.landmarks`: FaceSymAi 使用的语义关键点映射。
- `detection.blendshapes`: Face Landmarker 输出的表情 blendshape 分数，当前成功样本通常为 52 个。
- `detection.facial_transformation_matrixes`: Face Landmarker 输出的面部变换矩阵。
- 可选关键点叠加图。

## 目录结构

```text
modules/mediapipe_face_keypoint_detector/
  README.md
  requirements.txt
  runtime.md
  SDK_USAGE.md
  run_detect.py
  serve_api.py
  models/README.md
  models/face_landmarker.task
  face_keypoint_detector/
    __init__.py
    api_server.py
    cli.py
    detector.py
    schema.py
    sdk.py
    visualization.py
  examples/
    offline_sdk_example.py
```

## 运行环境

当前项目已验证环境：

```text
conda env: anti-spoofing_scc_175
python: 3.9.25
mediapipe: 0.10.35
Pillow
numpy
```

模块最小依赖见：

```text
requirements.txt
```

## 模型文件

默认使用模块目录内模型：

```text
modules/mediapipe_face_keypoint_detector/models/face_landmarker.task
```

也可以通过 `--model` 或环境变量指定：

```text
FACESYMAI_MEDIAPIPE_FACE_LANDMARKER_MODEL
```

## 离线 SDK 使用

复制整个目录到目标机器：

```text
modules/mediapipe_face_keypoint_detector
```

在目标机器安装依赖：

```bash
cd mediapipe_face_keypoint_detector
pip install -r requirements.txt
```

Python 直接调用：

```python
from face_keypoint_detector import FaceKeypointDetectorSDK

with FaceKeypointDetectorSDK() as detector:
    result = detector.detect_image("path/to/image.jpg")

print(result["status"])
```

完整离线 SDK 文档见：

```text
SDK_USAGE.md
```

## 单图运行

```bash
scripts/run_in_project_env.sh python modules/mediapipe_face_keypoint_detector/run_detect.py \
  path/to/image.jpg \
  --output tmp/mediapipe_keypoint_result.json \
  --annotated-output tmp/mediapipe_keypoint_overlay \
  --pretty
```

复制到其他机器后直接运行：

```bash
python run_detect.py path/to/image.jpg --output output/result.json --pretty
```

## 目录运行

```bash
scripts/run_in_project_env.sh python modules/mediapipe_face_keypoint_detector/run_detect.py \
  path/to/image_dir \
  --recursive \
  --output tmp/mediapipe_keypoint_results \
  --annotated-output tmp/mediapipe_keypoint_overlay \
  --pretty
```

## API 服务

启动关键点检测 API：

```bash
python modules/mediapipe_face_keypoint_detector/serve_api.py \
  --host 0.0.0.0 \
  --port 18131 \
  --access-token <token>
```

调用：

```bash
curl -X POST "http://127.0.0.1:18131/api/detect?token=<token>" \
  -F "images=@path/to/image.jpg"
```

## JSON 输出示例

```json
{
  "input": {
    "path": "path/to/image.jpg",
    "image_id": "image"
  },
  "runtime": {
    "backend": "mediapipe_face_landmarker",
    "model": "models/mediapipe/face_landmarker.task"
  },
  "status": "detected",
  "detection": {
    "detector": "mediapipe_face_landmarker",
    "face_count": 1,
    "landmark_schema_version": "facesymai-mediapipe-keypoints-v1",
    "mapping_version": "facesymai-mediapipe-face-landmarker-map-v1",
    "raw_landmarks": [],
    "landmarks": {},
    "pose": {
      "yaw": 0.0,
      "pitch": 0.0,
      "roll": 0.0
    },
    "blendshapes": {},
    "facial_transformation_matrixes": []
  }
}
```

## 下游调用约定

人脸对称性判断服务应读取本模块输出的 `detection` 字段，并至少校验：

- `status == "detected"`
- `len(detection.raw_landmarks) == 478`
- `len(detection.blendshapes) > 0`
- `len(detection.facial_transformation_matrixes) >= 1`

不满足上述条件时，不应进入对称性判断主流程。
