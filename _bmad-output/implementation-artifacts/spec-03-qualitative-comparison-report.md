---
title: 'Task 03 Qualitative Comparison Report'
type: 'feature'
created: '2026-06-08'
status: 'in-review'
baseline_commit: 'NO_VCS'
context:
  - '{project-root}/docs/algorithm/facial-symmetry-technical-solution.md'
  - '{project-root}/docs/algorithm/evaluation-protocol.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** 任务 #01/#02 已完成 YOLO 图片级预测、患者级聚合和定量指标对比，但还缺少逐患者不一致清单、典型不一致案例可视化、差异原因归类，以及可直接面向业务方展示的最终综合报告。

**Approach:** 新增独立脚本读取既有 YOLO 与 FaceSymAi 规则62 输出，以 #02 的 test-F1 最优 YOLO 规则 `yolo_any_stroke_mouth` 作为展示规则，找出共同患者中 YOLO 与规则62 判断不一致的病例；结合患者标签、预测类型、YOLO 检测统计、规则62 得分/贡献和图片质量信息生成归因，并抽样生成原图、YOLO bbox 标注、FaceSymAi 关键点 overlay 的横向对比图，最后写出综合 Markdown 报告。

## Boundaries & Constraints

**Always:** 使用 `datasets/yolo_comparison_20260608` 的现有 #01/#02 输出；FaceSymAi 规则62 只使用 `source_dataset == old` 的患者；患者标签和 split 以 `datasets/facesym_v1_by_name_20260119/metadata/05_patient_splits.csv` 为准；报告必须说明 patient outcome 是弱标签，不能表述为临床诊断性能；脚本重复运行应覆盖自身产物且保持确定性抽样。

**Ask First:** 如果要重新定义 YOLO 最优规则、重新运行全量 YOLO 预测、修改 #01/#02 已生成指标、或改变规则62 阈值，需要先征得用户确认。

**Never:** 不在测试集上调阈值；不把弱标签指标包装成医学诊断准确率；不修改原始数据集图片、YOLO 图片级 CSV、YOLO 患者级 CSV 或规则62 源文件。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path | #01/#02 输出、规则62 old 患者预测、V1 manifest/keypoints/annotated 图均存在 | 写出 `disagreement_cases.csv`、至少 20 例患者可视化、`final_comparison_report.md` | N/A |
| Missing bbox in #01 CSV | `yolo_detections` 只有 class/conf | 抽样可视化阶段用本地 YOLO 模型对抽样图片重新推理获取 bbox；CSV 指标仍沿用 #01/#02 结果 | 若模型不可用，则降级为标签叠加并在报告中说明 |
| Missing FaceSymAi patient | YOLO 患者不在规则62 old 集合 | 不进入共同患者不一致统计，在报告数据范围中说明 | 不报错 |
| Missing image/overlay | 抽样患者某张原图或关键点 overlay 不存在 | 跳过该图片或显示缺失占位，继续生成同患者其他图片 | 在 visualization index/报告备注缺失数 |

</frozen-after-approval>

## Code Map

- `scripts/compare_yolo_vs_facesymai.py` -- #02 的患者对齐、规则62 读取、指标计算和最优 YOLO 规则选择逻辑来源。
- `scripts/run_yolo_on_v1_test_set.py` -- YOLO 模型加载、类别语义和 #01 图片级检测语义来源。
- `datasets/yolo_comparison_20260608/yolo_per_image_predictions.csv` -- YOLO 图片级检测结果。
- `datasets/yolo_comparison_20260608/yolo_patient_predictions.csv` -- YOLO 患者级 5 条聚合规则。
- `datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_patient_predictions.csv` -- 规则62 患者级得分/预测/原因。
- `datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_patient_feature_contributions.csv` -- 规则62 逐特征触发贡献，用于归因。
- `datasets/facesym_v1_by_name_20260119/metadata/01_manifest.csv` and `metadata/03_keypoints.csv` -- 原图、样本、关键点 overlay 映射。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/analyze_comparison_disagreements.py` -- 新增分析脚本，生成不一致清单、抽样可视化、最终报告。
- [x] `datasets/yolo_comparison_20260608/disagreement_cases.csv` -- 写出共同患者中 YOLO 最优规则与规则62 预测不一致的患者清单和归因。
- [x] `datasets/yolo_comparison_20260608/comparison_visualizations/` -- 写出至少 20 例不一致患者的横向对比图和 index。
- [x] `datasets/yolo_comparison_20260608/final_comparison_report.md` -- 写出任务单指定 7 节结构的综合报告。
- [ ] `tasks/done/task_03_report.md` -- 写出开发日志、运行命令、输出摘要和校验记录。

**Acceptance Criteria:**
- Given #01/#02 和规则62 输出存在, when 运行 `scripts/run_in_project_env.sh python scripts/analyze_comparison_disagreements.py`, then 生成任务单要求的 3 个正式产物且脚本退出码为 0。
- Given 共同患者集合, when 读取 `disagreement_cases.csv`, then 每行包含 `patient_id`, `patient_label`, `split`, `yolo_prediction`, `facesymai_prediction`, `disagreement_type`, `analysis_reason`。
- Given 不一致患者数不少于 20, when 查看 `comparison_visualizations`, then 至少存在 20 张患者级可视化图片，且每张包含原图、YOLO 标注和 FaceSymAi 关键点 overlay。
- Given 最终报告, when 审阅结构, then 包含执行摘要、方法论对比、定量指标、定性分析、优劣对比、改进建议和结论。

## Spec Change Log

## Design Notes

不一致类型按业务对比语义定义：`yolo_fp_facesymai_tn` 表示真实标签为不患病、YOLO 判阳性、FaceSymAi 判阴性；`yolo_fn_facesymai_tp` 表示真实标签为患病、YOLO 判阴性、FaceSymAi 判阳性。其他预测不一致但相对标签不是上述两类的患者仍应进入清单，并使用 `yolo_tp_facesymai_fn` / `yolo_tn_facesymai_fp` 保留完整性。

## Verification

**Commands:**
- `scripts/run_in_project_env.sh python scripts/analyze_comparison_disagreements.py` -- expected: writes all requested task #03 outputs.
- `scripts/run_in_project_env.sh python -m py_compile scripts/analyze_comparison_disagreements.py` -- expected: syntax check passes.
