---
title: 'Task 02 YOLO vs FaceSymAi Rule62 Comparison'
type: 'feature'
created: '2026-06-08'
status: 'done'
route: 'one-shot'
---

# Task 02 YOLO vs FaceSymAi Rule62 Comparison

## Intent

**Problem:** 任务 #01 已生成 YOLO 图片级预测，但缺少患者级聚合结果，也缺少与 FaceSymAi 规则62 在同一患者集合上的可复现指标对比。

**Approach:** 新增独立比较脚本，从 YOLO 图片级 CSV 聚合 5 条患者级规则，读取规则62真实患者级预测并按患者切分对齐共同旧 V1 患者，输出患者级 YOLO CSV、对比指标 CSV 和 Markdown 报告。

## Suggested Review Order

**Entry Point And Defaults**

- Confirm the script defaults point at task #01 output, rule62 patient predictions, rule62 metrics, split CSV, and the requested output directory.
  [`compare_yolo_vs_facesymai.py:15`](../../scripts/compare_yolo_vs_facesymai.py#L15)

- Review the main flow: load inputs, detect label/split mismatches, align common patients, compute metrics, and write three required outputs.
  [`compare_yolo_vs_facesymai.py:649`](../../scripts/compare_yolo_vs_facesymai.py#L649)

**YOLO Patient Aggregation**

- Verify the five task-specified YOLO rules are emitted as patient-level booleans, including the documented majority denominator.
  [`compare_yolo_vs_facesymai.py:252`](../../scripts/compare_yolo_vs_facesymai.py#L252)

- Check patient-level stats: image counts, success/error counts, stroke image/detection counts, highest severities, class summary, and error summary.
  [`compare_yolo_vs_facesymai.py:262`](../../scripts/compare_yolo_vs_facesymai.py#L262)

- Confirm patient labels and splits come from `05_patient_splits.csv`, with YOLO image-level mismatches reported instead of silently driving metrics.
  [`compare_yolo_vs_facesymai.py:294`](../../scripts/compare_yolo_vs_facesymai.py#L294)

**FaceSymAi Rule62 Alignment**

- Confirm only `source_dataset == old` rule62 rows are used and patient IDs are extracted from `source_patient_sample_id`.
  [`compare_yolo_vs_facesymai.py:326`](../../scripts/compare_yolo_vs_facesymai.py#L326)

- Verify labels and splits are validated before metrics are calculated.
  [`compare_yolo_vs_facesymai.py:669`](../../scripts/compare_yolo_vs_facesymai.py#L669)

**Metrics And Report**

- Review metric formulas and zero-denominator behavior.
  [`compare_yolo_vs_facesymai.py:360`](../../scripts/compare_yolo_vs_facesymai.py#L360)

- Confirm all six methods are evaluated over train/val/test/combined on the same 504 common patients.
  [`compare_yolo_vs_facesymai.py:385`](../../scripts/compare_yolo_vs_facesymai.py#L385)

- Review report generation for data overview, rule62 cross-check, YOLO metric table, best-YOLO-vs-rule62 table, and initial analysis.
  [`compare_yolo_vs_facesymai.py:477`](../../scripts/compare_yolo_vs_facesymai.py#L477)

**Generated Artifacts**

- YOLO patient-level predictions.
  [`yolo_patient_predictions.csv:1`](../../datasets/yolo_comparison_20260608/yolo_patient_predictions.csv#L1)

- Full comparison metrics table.
  [`comparison_metrics.csv:1`](../../datasets/yolo_comparison_20260608/comparison_metrics.csv#L1)

- Markdown comparison report.
  [`comparison_report.md:1`](../../datasets/yolo_comparison_20260608/comparison_report.md#L1)
