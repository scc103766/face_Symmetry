# 运行环境

该服务依赖 `modules/mediapipe_face_keypoint_detector` 的运行环境。

## 主要依赖

- Python 3.10+。
- `mediapipe`：MediaPipe Tasks Face Landmarker。
- `Pillow`：图片读取和关键点可视化。
- `numpy`：MediaPipe/Pillow fallback 路径使用。

## 模型文件

默认模型路径：

```text
models/mediapipe/face_landmarker.task
```

也可以通过环境变量覆盖：

```bash
export FACESYMAI_MEDIAPIPE_FACE_LANDMARKER_MODEL=/path/to/face_landmarker.task
```

## 规则文件

默认读取：

```text
datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_feature_weights.csv
datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_score_threshold.csv
```

可以通过 `--rule-dir` 指向包含上述文件的目录。

## 推荐运行方式

使用项目环境包装脚本：

```bash
scripts/run_in_project_env.sh python modules/facial_asymmetry_service/run_analyze.py --help
```

网页上传服务：

```bash
scripts/run_in_project_env.sh python modules/facial_asymmetry_service/serve_web.py \
  --port 8790 \
  --access-token <token>
```

网页服务默认绑定 `0.0.0.0`，可被局域网/外部网络访问；如果只允许本机访问，可显式传 `--host 127.0.0.1`。

网页/API 默认同一人最少 2 张、最多 10 张；动作不强制限制。

默认上传和分析结果写入：

```text
tmp/facial_asymmetry_service_uploads/
```
