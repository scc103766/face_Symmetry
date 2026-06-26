# MediaPipe 人脸关键点检测离线 SDK 文档

> 模块路径：`modules/mediapipe_face_keypoint_detector/`
> 当前版本：M3-P0-05
> 更新日期：2026-06-24

---

## 1. 模块概览

本 SDK 封装了 MediaPipe Face Landmarker，提供**离线可用**的 478 点人脸关键点检测，以及侧视、露齿两项动作判断能力。可独立复制到其他项目使用。

### 目录结构

```
modules/mediapipe_face_keypoint_detector/
├── serve_api.py                          # API 服务启动入口
├── models/
│   └── face_landmarker.task              # MediaPipe 模型文件
├── action_detect.html                    # Web 上传页面
├── offline_sdk_copy/                     # 可独立复制的 SDK 副本
└── face_keypoint_detector/
    ├── __init__.py
    ├── sdk.py                            # SDK 主入口（FaceKeypointDetectorSDK）
    ├── detector.py                       # MediaPipe 检测器封装
    ├── api_server.py                     # HTTP API 服务（18432）
    ├── cli.py                            # 命令行工具
    └── visualization.py                  # 关键点可视化
```

### 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Python | ≥3.9 | — |
| mediapipe | 0.10.35 | Tasks API（`mp.tasks`），非 legacy `mp.solutions` |
| opencv-python | 4.13.0 | 图像读取 + HSV 色差分析 |
| numpy | — | 数值计算 |
| conda env | `anti-spoofing_scc_175` | 项目专用环境 |

---

## 2. 模型文件

MediaPipe Face Landmarker 模型（`face_landmarker.task`），支持 478 关键点 + 52 blendshapes + 面部变换矩阵。

### 模型查找顺序

1. 命令行 `--model /path/to/face_landmarker.task`
2. 环境变量 `FACESYMAI_MEDIAPIPE_FACE_LANDMARKER_MODEL`
3. 模块内置 `modules/mediapipe_face_keypoint_detector/models/face_landmarker.task`
4. 项目目录 `models/mediapipe/face_landmarker.task`

### 模型下载

```bash
# 官方下载
wget https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task
```

---

## 3. SDK Python API

### 3.1 快速使用

```python
from face_keypoint_detector.sdk import FaceKeypointDetectorSDK

sdk = FaceKeypointDetectorSDK()

# 检测单张图片
result = sdk.detect_image("face.jpg")
print(result["status"])           # detected / no_face / multiple_faces / failed
print(result["detection"]["raw_landmarks"])  # 478 个关键点
print(result["detection"]["blendshapes"])     # 52 维 blendshape
print(result["detection"]["landmarks"])       # 25 个语义关键点

# 批量检测
results = sdk.detect_images(["img1.jpg", "img2.jpg"])

# 带标注输出
result = sdk.detect_image("face.jpg", annotated_output="annotated.jpg")

sdk.close()
```

### 3.2 构造函数

```python
FaceKeypointDetectorSDK(
    model_path=None,                    # 模型路径，默认自动查找
    max_num_faces=2,                    # 最大检测人脸数
    min_face_detection_confidence=0.5,  # 人脸检测置信度阈值
    min_face_presence_confidence=0.5,   # 人脸存在置信度阈值
    min_tracking_confidence=0.5,        # 追踪置信度阈值
)
```

### 3.3 返回结构

```json
{
  "input": { "path": "/path/to/image.jpg", "image_id": "image" },
  "runtime": { "backend": "mediapipe_face_landmarker", "model": "models/face_landmarker.task" },
  "status": "detected",
  "detection": {
    "face_count": 1,
    "raw_landmarks": [{"x": 0.512, "y": 0.423, "z": -0.031, "confidence": 1.0}, ...],
    "landmarks": {
      "nose_tip": {"x": 0.501, "y": 0.512},
      "left_eye_outer": {"x": 0.398, "y": 0.401},
      "right_mouth_corner": {"x": 0.583, "y": 0.589},
      ...
    },
    "blendshapes": {"jawOpen": 0.035, "eyeLookInLeft": 0.012, ...},
    "facial_transformation_matrixes": [...],
    "pose": {"yaw": -5.05, "pitch": 2.13, "roll": -0.87}
  }
}
```

---

## 4. API 服务（18432）

### 4.1 启动服务

```bash
cd /supercloud/llm-code/scc/scc/FaceSymAi
source $(conda info --base)/etc/profile.d/conda.sh && conda activate anti-spoofing_scc_175
PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi \
  python modules/mediapipe_face_keypoint_detector/serve_api.py \
  --host 0.0.0.0 --port 18432
```

### 4.2 端点总览

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/action` | GET | Web 上传页面（浏览器打开） |
| `/action` | POST | 一键三合一：上传图片，同时返回关键点+侧视+露齿 |
| `/keypoint` | POST | 478 点关键点检测 |
| `/ceshi` | POST | 眼球侧视检测 |
| `/louyachi` | POST | 露齿检测 |
| `/api/detect` | POST | 批量关键点检测（多图上传） |
| `/api/detect-folder` | POST | 文件夹批量检测 |

### 4.3 一键三合一 `/action`

```bash
curl -X POST http://192.168.17.175:18432/action -F "images=@face.jpg"
```

```json
{
  "status": "detected",
  "keypoint": { "landmarks": {...}, "blendshapes": {...} },
  "side_view": { "detected": true, "direction": "left", "level": "moderate" },
  "teeth_exposure": { "detected": false, "mouth_state": "mouth_closed", "confidence": 0.08 }
}
```

### 4.4 单独调用

```bash
# 关键点
curl -X POST http://192.168.17.175:18432/keypoint -F "images=@face.jpg"

# 侧视
curl -X POST http://192.168.17.175:18432/ceshi -F "images=@face.jpg"

# 露齿
curl -X POST http://192.168.17.175:18432/louyachi -F "images=@face.jpg"

# 文件夹批量
curl -X POST http://192.168.17.175:18432/api/detect-folder \
  -H "Content-Type: application/json" \
  -d '{"image_dir": "/data/images", "recursive": true}'
```

---

## 5. 动作检测能力

本 SDK 内置两项动作判断，代码位于 `face_keypoint_detector/` 目录通过动态导入调用 `facial_asymmetry_service` 中的 `action_detector` 模块。

| 检测 | 方法 | 准确率 | 说明 |
|------|------|:---:|------|
| 侧视 | eyeLook blendshape 眼球凝视 | left 95.9% / right 86.4% | 检测眼球看向侧方，非头部转动 |
| 露齿 | 口唇几何 + HSV色差 + 切牙边缘 + Pose分桶 | 75.0% | 多信号融合，闭嘴准确 97.9% |

详细指标见 `docs/current_metrics_20260624.md`，接口文档见 `docs/api_interface_doc.md`。

---

## 6. CLI 脚本

### 单图检测

```bash
scripts/run_in_project_env.sh python scripts/detect_mediapipe_image.py \
  path/to/image.jpg \
  --output result.json --pretty
```

### 目录批量

```bash
scripts/run_in_project_env.sh python scripts/detect_mediapipe_image.py \
  path/to/image-dir --recursive \
  --output datasets/outputs --annotated-output tmp/annotated
```

### 数据集烟雾测试

```bash
scripts/run_in_project_env.sh python scripts/run_mediapipe_landmarker_dataset_smoke.py \
  --roles front,smile,teeth --limit-per-role 10 \
  --output tmp/smoke_test
```

---

## 7. 独立复制 SDK

SDK 可脱离项目独立使用。复制 `offline_sdk_copy/` 目录到目标项目：

```bash
cp -r modules/mediapipe_face_keypoint_detector/offline_sdk_copy/ /target/project/
```

复制后包含：
- 完整的 `face_keypoint_detector` Python 包
- `face_landmarker.task` 模型文件
- 入口脚本和示例

---

## 变更记录

| 日期 | 变更 |
|------|------|
| 2026-06-24 | 更新为当前项目状态：SDK API + 18432 服务 + 动作检测 + POST /action |
| — | 初版：MediaPipe Tasks API 验证 + 本地检测脚本 |
