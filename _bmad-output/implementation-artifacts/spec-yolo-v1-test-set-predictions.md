---
title: 'YOLO V1 Test Set Predictions'
type: 'feature'
created: '2026-06-08'
status: 'done'
route: 'one-shot'
---

# YOLO V1 Test Set Predictions

## Intent

**Problem:** FaceSymAi V1 by-name 数据集需要一份来自第三方 YOLOv8 模型的逐图片检测结果，用于后续与现有 MediaPipe/规则输出做指标对比。

**Approach:** 新增独立批处理脚本读取 V1 manifest 和患者 split，在 CPU 上以 `conf=0.25` 对每张图片推理，输出逐图片 CSV、汇总 JSON 和运行日志。

## Suggested Review Order

**Batch Entry Point**

- Defaults pin the requested model, manifest, split file, output directory, CPU device, and confidence.
  [`run_yolo_on_v1_test_set.py:16`](../../scripts/run_yolo_on_v1_test_set.py#L16)

- Main flow loads inputs, runs YOLO, writes CSV and summary.
  [`run_yolo_on_v1_test_set.py:330`](../../scripts/run_yolo_on_v1_test_set.py#L330)

**Prediction Semantics**

- Detection extraction keeps only required class and confidence fields.
  [`run_yolo_on_v1_test_set.py:176`](../../scripts/run_yolo_on_v1_test_set.py#L176)

- Severity aggregation maps YOLO classes to eye/mouth maximum severities.
  [`run_yolo_on_v1_test_set.py:194`](../../scripts/run_yolo_on_v1_test_set.py#L194)

- Per-image rows exactly match the task CSV schema.
  [`run_yolo_on_v1_test_set.py:214`](../../scripts/run_yolo_on_v1_test_set.py#L214)

**Failure Accounting**

- One bad image is isolated to its own row instead of aborting the run.
  [`run_yolo_on_v1_test_set.py:258`](../../scripts/run_yolo_on_v1_test_set.py#L258)

- Summary separates inference failures from successful empty detections.
  [`run_yolo_on_v1_test_set.py:281`](../../scripts/run_yolo_on_v1_test_set.py#L281)

**Generated Artifacts**

- Review the machine-readable per-image predictions first.
  [`yolo_per_image_predictions.csv:1`](../../datasets/yolo_comparison_20260608/yolo_per_image_predictions.csv#L1)

- Review aggregate counts, class distribution, and failed image details.
  [`yolo_run_summary.json:1`](../../datasets/yolo_comparison_20260608/yolo_run_summary.json#L1)

- Confirm the final run used CPU and completed with expected counts.
  [`run.log:1`](../../datasets/yolo_comparison_20260608/run.log#L1)
