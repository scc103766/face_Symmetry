# MediaPipe 人脸关键点检测离线 SDK 使用说明

`modules/mediapipe_face_keypoint_detector` 可以作为独立文件夹复制到其他机器使用，不依赖 FaceSymAi 主项目代码。

## 目录内容

```text
mediapipe_face_keypoint_detector/
  README.md
  SDK_USAGE.md
  requirements.txt
  run_detect.py
  serve_api.py
  models/
    face_landmarker.task
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

其中 `models/face_landmarker.task` 是默认模型。复制目录时必须一并复制。

## 离线机器环境准备

推荐 Python 3.9 到 3.11。

```bash
cd mediapipe_face_keypoint_detector
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果不能联网安装依赖，需要提前在可联网机器下载 wheel 包，并在目标机器离线安装。

## Python SDK 调用

```python
from pathlib import Path

from face_keypoint_detector import FaceKeypointDetectorSDK


image_path = Path("person.jpg")

with FaceKeypointDetectorSDK() as detector:
    result = detector.detect_image(image_path)

if result["status"] == "detected":
    detection = result["detection"]
    print("raw landmarks:", len(detection["raw_landmarks"]))
    print("blendshapes:", len(detection["blendshapes"]))
    print("matrixes:", len(detection["facial_transformation_matrixes"]))
else:
    print("not detected:", result["status"])
```

运行示例：

```bash
python examples/offline_sdk_example.py path/to/image.jpg
```

## 命令行调用

单张图片：

```bash
python run_detect.py path/to/image.jpg \
  --output output/result.json \
  --annotated-output output/annotated \
  --pretty
```

目录批量：

```bash
python run_detect.py path/to/images \
  --recursive \
  --output output/detections \
  --annotated-output output/annotated \
  --pretty
```

## API 服务调用

启动服务：

```bash
python serve_api.py \
  --host 0.0.0.0 \
  --port 18131 \
  --access-token <token>
```

健康检查：

```bash
curl "http://127.0.0.1:18131/api/health?token=<token>"
```

上传检测：

```bash
curl -X POST "http://127.0.0.1:18131/api/detect?token=<token>" \
  -F "images=@person_front.jpg" \
  -F "images=@person_smile.jpg"
```

也可以通过请求头传 token：

```bash
curl -X POST "http://127.0.0.1:18131/api/detect" \
  -H "X-Access-Token: <token>" \
  -F "images=@person_front.jpg"
```

## 输出格式

单张图片检测成功时：

```json
{
  "status": "detected",
  "detection": {
    "face_count": 1,
    "raw_landmarks": [],
    "landmarks": {},
    "blendshapes": {},
    "facial_transformation_matrixes": []
  }
}
```

常见状态：

- `detected`：识别人脸并输出关键点。
- `no_face`：未识别人脸。
- `multiple_faces`：检测到多张人脸，默认不当作单人脸成功结果；可通过 `--allow-multiple-faces` 放开。
- `failed`：图片读取或推理异常。

下游如果用于人脸对称性分析，至少应检查：

- `status == "detected"`
- `len(detection.raw_landmarks) == 478`
- `len(detection.blendshapes) > 0`
- `len(detection.facial_transformation_matrixes) >= 1`

## 模型路径覆盖

默认使用：

```text
models/face_landmarker.task
```

也可以通过命令行参数指定：

```bash
python run_detect.py image.jpg --model /path/to/face_landmarker.task
python serve_api.py --model /path/to/face_landmarker.task
```

或通过环境变量：

```bash
export FACESYMAI_MEDIAPIPE_FACE_LANDMARKER_MODEL=/path/to/face_landmarker.task
```

## 边界

本 SDK 只做人脸关键点检测，输出 MediaPipe 关键点、blendshape 和 transformation matrix。它不做人脸对称性判断，不输出患病/不患病结论。
