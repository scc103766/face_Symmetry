# 任务单 #01

**任务名称**：YOLO 模型在 FaceSymAi V1 测试集上运行
**优先级**：P0
**依赖**：无

## 📖 技术背景

对比项目 `third_party/stroke_detection_yolo/` 是一个 YOLOv8 检测模型，训练用于检测人脸眼部和口部的中风不对称迹象，输出 8 个类别：
- `normalEye`, `normalMouth`
- `strokeEyeMid`, `strokeEyeSevere`, `strokeEyeWeak`
- `strokeMouthMid`, `strokeMouthSevere`, `strokeMouthWeak`

模型文件位于 `third_party/stroke_detection_yolo/best.pt`。

我们要用这个模型跑 FaceSymAi V1 测试集的所有图片，为后续指标对比做准备。

## 📝 任务描述

1. 写一个脚本 `scripts/run_yolo_on_v1_test_set.py`，读取 FaceSymAi V1 by-name 测试集图片
2. 对每张图片用 YOLO 模型推理，记录检测结果
3. 输出到指定目录

## 📥 输入

- YOLO 模型：`third_party/stroke_detection_yolo/best.pt`
- V1 by-name 数据集 manifest：`datasets/facesym_v1_by_name_20260119/metadata/01_manifest.csv`
- 测试集患者切分：`datasets/facesym_v1_by_name_20260119/metadata/05_patient_splits.csv`
- 图片目录：`datasets/facesym_v1_by_name_20260119/` 下的图片文件

## 📤 输出要求

- [ ] `datasets/yolo_comparison_20260608/yolo_per_image_predictions.csv`：每张图片一行，列包括：
  - `patient_id`：患者ID
  - `image_path`：图片路径
  - `role`：图片角色（front/smile/teeth）
  - `split`：train/val/test
  - `patient_label`：患病/不患病
  - `yolo_detections`：JSON 字符串，记录所有检测到的类别和置信度，格式如 `[{"class":"strokeEyeSevere","conf":0.92},{"class":"normalMouth","conf":0.83}]`
  - `yolo_eye_max_severity`：眼部最高严重度（none/normal/weak/mid/severe），从检测中汇总
  - `yolo_mouth_max_severity`：口部最高严重度（none/normal/weak/mid/severe）
  - `yolo_any_stroke`：是否有任何 stroke 检测（True/False）
  - `yolo_error`：如果推理失败，记录错误信息
- [ ] `datasets/yolo_comparison_20260608/yolo_run_summary.json`：汇总统计（总图片数、成功数、失败数、各类别分布等）

## ✅ 验收标准

1. 脚本可在项目环境下运行（`scripts/run_in_project_env.sh python scripts/run_yolo_on_v1_test_set.py`）
2. 输出 CSV 覆盖 V1 by-name 数据集的所有图片（约 1546 张，含 train/val/test）
3. YOLO 在 CPU 上运行（`device='cpu'`，避免 GPU 显存冲突），`conf=0.25`
4. CSV 每列按规范填写，无缺失值
5. 运行日志输出到 `datasets/yolo_comparison_20260608/run.log`

## ⚠️ 需要关注

- ultralytics 已安装在 conda 环境中
- 图片路径从 manifest/patient splits 中获取，不要硬编码
- 有些图片可能是 `.jpg` 或其他格式，注意兼容
- YOLO 检测结果可能为空（无检测），需正常处理

## 🔗 参考资料

- `third_party/stroke_detection_yolo/best.pt` — YOLO 模型文件
- `third_party/stroke_detection_yolo/app.py` — 参考推理代码
- `datasets/facesym_v1_by_name_20260119/` — V1 数据集目录
- `docs/datasets/facesym-v1-by-name-data-flow.md` — 数据流程说明
