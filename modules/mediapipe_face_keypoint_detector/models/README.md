# Model File

本模块默认使用当前目录内的 Face Landmarker 模型：

```text
models/face_landmarker.task
```

复制 `mediapipe_face_keypoint_detector` 文件夹到其他机器作为离线 SDK 时，必须一并复制该模型文件。

也可以通过以下方式指定其他模型：

```bash
python run_detect.py \
  path/to/image.jpg \
  --model /absolute/path/to/face_landmarker.task
```

或设置环境变量：

```bash
export FACESYMAI_MEDIAPIPE_FACE_LANDMARKER_MODEL=/absolute/path/to/face_landmarker.task
```
