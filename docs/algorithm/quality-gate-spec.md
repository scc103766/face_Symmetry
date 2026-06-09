# FaceSymAi V1 输入质量门控规范

V1 质量门控用于阻断不合理输入进入高可信评分流程。它只判断输入是否满足图片/视频分析条件，不输出医学诊断结论，也不等同于完整法律合规审查。

## 输入范围

- 图片：`jpg`、`jpeg`、`png`、`webp`、`bmp`、`tif`、`tiff`
- 视频：`mp4`、`mov`、`m4v`、`avi`、`mkv`、`webm`、`3gp`
- V1 静态算法优先使用正脸图和露齿图；视频当前只做容器和抽样帧质量门控，不做动态特征评分。

## 门控项

| 项目 | 默认策略 | 失败结果 |
| --- | --- | --- |
| 文件可读性 | 文件存在、非空、格式受支持、大小不超过 350 MB | `reject` |
| 图片尺寸 | 短边不低于 256 px | `reject` |
| 视频时长 | 0.3 到 30 秒 | `reject` |
| 单人脸 | OpenCV Haar 代理检测，默认要求单人脸 | `reject` |
| 人脸大小 | 人脸框短边不低于 180 px，推荐 256 px | `reject` 或降分 |
| 清晰度 | Laplacian 方差不低于 45，140 以上视为较好 | `reject` 或降分 |
| 光照 | 灰度均值 35 到 220，推荐 70 到 190 | `reject` 或降分 |
| 曝光 | 过暗/过曝像素比例不超过 35% | `reject` 或降分 |
| 左右光照差 | 左右半图亮度差超过 55 触发告警 | `review` |
| 遮挡代理 | 眼部 Haar 检测作为核心区域可见性粗代理 | 默认 `review`，可配置为 `reject` |
| 露齿合规 | 当前仅返回提示；精确口部合规依赖后续关键点检测 | `info` |

## 输出字段

质量门控输出：

```json
{
  "quality_score": 0.86,
  "quality_level": "pass",
  "hard_reject": false,
  "accepted_for_scoring": true,
  "reasons": [],
  "metrics": {},
  "frame_results": []
}
```

质量等级：

- `pass`：可进入评分流程。
- `review`：可进入评分流程，但应降权或人工复核。
- `reject`：不可进入评分流程，应重采或排查输入。

## 运行方式

检查单个数据集并生成输入门控目录：

```bash
scripts/run_in_project_env.sh python scripts/run_quality_gate.py \
  --source datasets/stroke_patient_outcome_by_name_20260119 \
  --output datasets/stroke_patient_outcome_quality_gated_20260119
```

只生成报告，不物化文件：

```bash
scripts/run_in_project_env.sh python scripts/run_quality_gate.py --mode none
```

快速验证前 20 个样本：

```bash
scripts/run_in_project_env.sh python scripts/run_quality_gate.py --limit 20
```

## 重要限制

- 当前人脸数量和眼部可见性使用 OpenCV Haar 作为 V1 可运行代理，不等同于最终 MediaPipe Face Landmarker 质量门控。
- 口罩、墨镜、手部遮挡等合规项需要关键点、分割或专门遮挡模型才能稳定判断；当前实现只提供粗粒度代理。
- 视频当前只按抽样帧做输入质量控制，不评价动态面瘫动作。
