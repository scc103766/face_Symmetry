# Runtime Requirements

## 已验证项目环境

```text
conda env: anti-spoofing_scc_175
python: 3.9.25
mediapipe: 0.10.35
```

推荐通过项目封装脚本运行：

```bash
scripts/run_in_project_env.sh python modules/mediapipe_face_keypoint_detector/run_detect.py --help
```

## Python 依赖

最小依赖：

```text
mediapipe>=0.10
numpy>=1.23
Pillow>=9
```

安装示例：

```bash
python -m pip install -r modules/mediapipe_face_keypoint_detector/requirements.txt
```

离线 SDK 拷贝到其他机器后：

```bash
cd mediapipe_face_keypoint_detector
python -m pip install -r requirements.txt
```

## 模型依赖

Face Landmarker 需要 `.task` 模型文件。离线 SDK 默认路径：

```text
models/face_landmarker.task
```

模型查找顺序：

1. CLI 参数 `--model`
2. 环境变量 `FACESYMAI_MEDIAPIPE_FACE_LANDMARKER_MODEL`
3. SDK 目录内 `models/face_landmarker.task`
4. FaceSymAi 项目根目录 `models/mediapipe/face_landmarker.task`

## 运行输入要求

- 输入必须是本地静态图片。
- 支持后缀：`.jpg`、`.jpeg`、`.png`。
- 推荐单人脸；默认检测到多张脸时标记为 `multiple_faces`。
- 该模块不会做质量门控，不会判断人脸对称性。

## 输出稳定性要求

下游人脸对称性服务调用前应确认：

```text
status == detected
raw landmarks == 478
blendshapes available
facial transformation matrixes >= 1
```
