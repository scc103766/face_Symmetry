## 🎫 任务单 #M4-VIDEO-01 — 待 Engineer 执行

**任务名称**：视频抽帧 + 逐帧 MediaPipe 特征提取
**优先级**：P0
**依赖**：无

---

## 🔧 角色与约束（Engineer 身份）

你是本项目的 Engineer Agent。在本任务中你必须遵守：

### 执行边界
1. **只执行本任务单描述的内容**，不得自行扩展需求。
2. 输出路径严格按任务单规定。

### 决策权限
3. 遇到技术阻塞时：写清原因，停止并回报 PM。
4. 多路径时选最简方案并注明理由。

### 产出规范
5. 完成后写入 `tasks/done/M4-VIDEO-01_report.md`。
6. 报告末尾必须包含「💡 Engineer 建议」节。

### 禁止事项
7. ❌ 不得 commit/push/修改 git 历史。
8. ❌ 不得修改 conda/pip 环境。
9. ❌ 不得新增第三方依赖。

---

## 📝 任务描述

从两个数据集的 1126 个视频中均匀抽帧，对每帧运行 MediaPipe 478 关键点检测 + 规则62 21 维特征提取，输出每帧的特征 CSV。

---

## ✅ 子任务 1：视频发现与清单

扫描两个目录下的所有视频文件，生成处理清单：

```python
# 输入
/supercloud/llm-code/scc/scc/FaceSymAi/datasets/stroke_media_dataset_20260119/media/videos/
/supercloud/llm-code/scc/scc/FaceSymAi/datasets/stroke_warning_app_media_dataset_20260508/media/videos/

# 输出
datasets/video_dynamic_asymmetry/manifest.csv
```

manifest 包含字段：
- `video_path`：绝对路径
- `dataset`：`stroke_media` / `stroke_warning`
- `patient_id`：从 records 中获取
- `label`：`patient` / `non_patient`（从 records 的 `是否患病` / `风险等级` 获取）
- `duration_seconds`：视频时长
- `frame_count`：原始总帧数
- `fps`：原始帧率

---

## ✅ 子任务 2：视频抽帧

对每个视频均匀抽取 **最多 100 帧**（5 fps 等效）：

```python
# 策略：间隔采样
sample_interval = max(1, total_frames // 100)
frames = video[sample_interval * i] for i in range(min(100, total_frames // sample_interval))
```

保存到：
```
datasets/video_dynamic_asymmetry/frames/{dataset}/{patient_id}/{video_name}/
```

每帧命名：`frame_{index:04d}.jpg`

---

## ✅ 子任务 3：逐帧特征提取

对每个抽出的帧，运行与规则62 相同的 MediaPipe 检测 + 特征提取流程：

```python
from facesymai.features import extract_features_from_detection
from modules.mediapipe_face_keypoint_detector.face_keypoint_detector.sdk import FaceKeypointDetectorSDK

sdk = FaceKeypointDetectorSDK()
for frame_path in frames:
    result = sdk.detect_image(frame_path)
    if result["status"] == "detected":
        features = extract_features_from_detection(result["detection"])
        # 保存到逐帧 CSV
```

输出：
```
datasets/video_dynamic_asymmetry/features/{dataset}/{patient_id}/{video_name}_features.csv
```

CSV 列：`frame_index, timestamp_seconds, face_detected, face_asymmetry_confidence, feature_1, ..., feature_21`

---

## ✅ 子任务 4：数据质量报告

生成 `datasets/video_dynamic_asymmetry/quality_report.json`：

```json
{
  "total_videos": 1126,
  "processed_videos": 1100,
  "failed_videos": 26,
  "total_frames_extracted": 98000,
  "frames_with_face": 92000,
  "face_detection_rate": 0.939,
  "per_dataset": {
    "stroke_media": {"videos": 515, "processed": 500, "avg_frames": 85},
    "stroke_warning": {"videos": 611, "processed": 600, "avg_frames": 90}
  },
  "label_distribution": {"patient": 200, "non_patient": 900}
}
```

---

## 环境

```bash
conda activate anti-spoofing_scc_175
cd /supercloud/llm-code/scc/scc/FaceSymAi
export PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi
```

## 产出路径

```
datasets/video_dynamic_asymmetry/
├── manifest.csv
├── quality_report.json
├── frames/
│   └── {dataset}/{patient_id}/{video_name}/frame_XXXX.jpg
└── features/
    └── {dataset}/{patient_id}/{video_name}_features.csv
```

## 验收

1. `manifest.csv` 包含所有视频的路径+标签+时长信息
2. 帧和特征 CSV 覆盖 ≥95% 的视频
3. `quality_report.json` 包含完整统计数据
4. 人脸检出率 ≥90%
