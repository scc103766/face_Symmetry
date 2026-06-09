---
title: "All Images No Gate Comparison Dataset"
type: "feature"
created: "2026-05-21"
status: "done"
baseline_commit: "NO_VCS"
context:
  - "../project-context.md"
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** 当前正式 V1 流程只处理 `front,smile,teeth` 并运行质量门控，无法对比“读取每个患者所有图片且不做质量门控”时 MediaPipe 检测、特征和 baseline 指标的变化。

**Approach:** 新增一个独立对比组脚本，默认读取 by-name 源数据集中所有 `media_type=image` 图片，不做角色筛选和质量门控，继续执行 Face Landmarker 检测/绘制、图片级/患者级特征、患者级切分和当前规则 baseline 技术评估。

## Boundaries & Constraints

**Always:** 输出写入项目内 `datasets/` 或 `tmp/`；保留正式 V1 流程不变；患者级切分仍按患者分层，避免图片级泄漏；baseline 指标只能表述为 patient outcome 技术信号检查。

**Ask First:** 需要删除已有正式数据集、改动原始 xlsx、改动 MediaPipe 模型或改动当前 V1 scoring 权重时必须先询问。

**Never:** 不把无质量门控结果表述为医学诊断性能；不默认写入系统 `/tmp`；不把病历/辅助检查/舌像图片静默排除。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Full comparison | by-name 数据集存在 505 个患者、所有图片 roles | 输出独立 comparison 目录，包含全图片索引、quality skipped 报告、keypoints、annotated、features、splits、baseline | 单图检测失败记录为 `failed` 并继续 |
| Duplicate role images | 同一患者同一 role 有多张图片 | 图片级保留全部；患者级每个 role 取最高 `advisory_confidence`，总体取全图片最高分 | 无分数时该患者 baseline `skipped` |
| Non-face images | 病历、辅助检查、舌像等图片 | 仍运行 Face Landmarker；`no_face` 不生成特征；若误检则照常进入对比组特征 | 报告中保留检测状态 |

</frozen-after-approval>

## Code Map

- `scripts/build_facesym_v1_dataset_from_by_name.py` -- 现有正式 V1 by-name 流程，可复用检测、分层切分、metric 计算和报告 helper。
- `scripts/build_facesym_v1_all_images_no_gate_comparison.py` -- 新增对比组入口。
- `datasets/stroke_patient_outcome_by_name_20260119/metadata/media_index.csv` -- 对比组输入索引。
- `src/facesymai/landmarks/mediapipe_face_landmarker.py` -- 当前 V1 MediaPipe 检测基座。
- `src/facesymai/features.py` 与 `src/facesymai/risk.py` -- 当前特征和规则 baseline。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/build_facesym_v1_all_images_no_gate_comparison.py` -- 新增全图片无质量门控对比流程 -- 避免影响正式 V1 流程。
- [x] `scripts/build_facesym_v1_all_images_no_gate_comparison.py` -- 患者级聚合支持同一患者同一 role 多图 -- 避免图片被覆盖。
- [x] `scripts/build_facesym_v1_all_images_no_gate_comparison.py` -- 输出 per-stage metadata/report/README -- 满足结果可复核。
- [x] `docs/project-context.md` 与 `_bmad-output/project-context.md` -- 同步新增对比组流程和输出目录 -- 保持项目上下文一致。

**Acceptance Criteria:**
- Given by-name 源数据集, when 运行对比组脚本, then 处理所有 `media_type=image` 图片且不执行质量门控。
- Given 检测成功图片, when 特征阶段运行, then 输出图片级总体对称性和五类部件级属性。
- Given 患者有多张同 role 图片, when 聚合患者级特征, then 不覆盖图片级行并按最高分记录 role-best 和 patient-best。
- Given baseline 阶段完成, when 查看报告, then 可复核阈值、TP/FP/TN/FN 和 precision。

## Spec Change Log

## Design Notes

对比组保留“质量门控 skipped”作为显式阶段，而不是删除阶段编号。这样报告链路仍与正式流程可对齐，但不会用质量结果过滤或影响特征计算。

## Verification

**Commands:**
- `scripts/run_in_project_env.sh python scripts/build_facesym_v1_all_images_no_gate_comparison.py --limit-patients-per-label 1 --skip-annotations --output tmp/facesym_v1_all_images_no_gate_smoke` -- expected: smoke output succeeds.
- `scripts/run_in_project_env.sh python scripts/build_facesym_v1_all_images_no_gate_comparison.py --output datasets/facesym_v1_all_images_no_gate_20260119` -- expected: full comparison output succeeds.
- `env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi scripts/run_in_project_env.sh pytest -q` -- expected: `52 passed`.

**Latest Full Run:**
- 2026-05-27: full comparison rerun completed for 5195 images and 505 patients.
- MediaPipe detection: `detected` 5005、`no_face` 189、`failed` 1。
- Downstream 20 阶段汇总已读取该 dataset 并输出 `metadata/20_mediapipe_end_to_end_predictions.csv`。
