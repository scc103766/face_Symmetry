# 任务单 #02 开发日志

## 执行摘要

- 已新增脚本：`scripts/compare_yolo_vs_facesymai.py`
- 已完成正式运行：`scripts/run_in_project_env.sh python scripts/compare_yolo_vs_facesymai.py`
- 已生成任务要求产物：
  - `datasets/yolo_comparison_20260608/yolo_patient_predictions.csv`
  - `datasets/yolo_comparison_20260608/comparison_metrics.csv`
  - `datasets/yolo_comparison_20260608/comparison_report.md`
- 已生成 one-shot 实现追踪：`_bmad-output/implementation-artifacts/spec-02-yolo-vs-facesymai-rule62-comparison.md`

## 实现内容

- 脚本默认读取：
  - YOLO 图片级预测：`datasets/yolo_comparison_20260608/yolo_per_image_predictions.csv`
  - FaceSymAi 规则62 患者级预测：`datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_patient_predictions.csv`
  - FaceSymAi 规则62 既有指标：`datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_metrics.csv`
  - 患者级切分：`datasets/facesym_v1_by_name_20260119/metadata/05_patient_splits.csv`
- YOLO 患者级聚合实现 5 条规则：
  - `yolo_any_stroke_eye`
  - `yolo_any_stroke_mouth`
  - `yolo_any_stroke`
  - `yolo_stroke_severe`
  - `yolo_majority_stroke`
- `yolo_majority_stroke` 使用 `yolo_stroke_image_count / image_count >= 0.5`，分母包含任务 #01 输出中的全部图片行；YOLO 失败图片计入图片数但不计入 stroke 检测。
- YOLO 患者级输出同时包含图片数、成功/失败图片数、stroke 图片数、stroke 检测数、眼/口/整体最高严重度、检测类别汇总和错误汇总。
- FaceSymAi 规则62 指标从 `62_stable_weighted_feature_disease_rule_patient_predictions.csv` 逐患者重新计算，不从 Markdown 报告复制。
- 对比指标为 6 个 method（5 条 YOLO 规则 + `facesymai_rule62`）在 `train/val/test/combined` 上的 precision、recall、specificity、f1、accuracy、TP/FP/TN/FN。

## 数据对齐与一致性处理

- YOLO 图片级输入：1546 张图片，聚合后 505 名患者。
- FaceSymAi 规则62 的旧 V1 患者级预测：504 名患者。
- 对比指标统一使用 YOLO 与规则62 的共同患者集合：504 名患者。
- 未进入共同集合的 YOLO 患者：`patient_id=19`，对应 `杨思__pid19`，位于 train，规则62 缺少该患者。
- YOLO 图片级文件中 `patient_id=392` 有 3 张图片标签与 `05_patient_splits.csv` 不一致；患者级指标统一按 `05_patient_splits.csv` 的患者级标签和 split 计算。
- test split 共同患者数为 77，标签分布为患病 51、不患病 26，与任务要求的同一测试集对比一致。

## 正式输出摘要

### `yolo_patient_predictions.csv`

- 行数：505 名患者
- 字段数：23
- 关键字段：
  - `patient_id`, `patient_label`, `split`
  - 5 条 YOLO 聚合规则布尔结果
  - `image_count`, `yolo_success_image_count`, `yolo_error_image_count`
  - `yolo_stroke_image_count`, `yolo_stroke_detection_count`
  - `yolo_eye_highest_severity`, `yolo_mouth_highest_severity`, `yolo_highest_severity`

### `comparison_metrics.csv`

- 行数：24
- 字段与任务单一致：
  - `method`, `split`, `precision`, `recall`, `specificity`, `f1`, `accuracy`, `tp`, `fp`, `tn`, `fn`
- FaceSymAi 规则62 combined 复算结果：
  - precision `0.781481`
  - recall `0.627976`
  - specificity `0.648810`
  - f1 `0.696370`
  - TP `211`, FP `59`, TN `109`, FN `125`
- 该复算结果与既有 `62_stable_weighted_feature_disease_rule_metrics.csv` 的 `old` 行完全一致。

### `comparison_report.md`

- 包含数据概览、标签分布、共同患者说明和规则62交叉验证。
- 包含 YOLO 5 条聚合规则的 train/val/test/combined 指标表。
- 包含 YOLO 展示最优规则与 FaceSymAi 规则62 的详细对比。
- 包含初步分析和 patient outcome 弱标签限制说明。

## 关键 test 指标

YOLO 展示最优规则按 test split 的 F1 选择，仅用于报告对比；当前为 `yolo_any_stroke_mouth`。

| method | precision | recall | specificity | f1 | accuracy | TP | FP | TN | FN |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| yolo_any_stroke_mouth | 0.681159 | 0.921569 | 0.153846 | 0.783333 | 0.662338 | 47 | 22 | 4 | 4 |
| facesymai_rule62 | 0.782609 | 0.705882 | 0.615385 | 0.742268 | 0.675325 | 36 | 10 | 16 | 15 |

初步结论：

- FaceSymAi 规则62 在 test precision、specificity、accuracy 上更高。
- YOLO `yolo_any_stroke_mouth` 在 test recall 和 F1 上更高。
- YOLO `any` / `majority` 类规则更容易报阳性，召回更高但不患病误判更多。
- 规则62 使用稳定性加权 MediaPipe 特征和固定加权阈值，更偏保守，因此 precision/specificity 更好但 recall 较低。

## 校验记录

- `scripts/run_in_project_env.sh python scripts/compare_yolo_vs_facesymai.py`：通过，生成 3 个任务要求产物。
- `scripts/run_in_project_env.sh python -m py_compile scripts/compare_yolo_vs_facesymai.py`：通过。
- 输出文件存在性和大小校验：通过。
- `comparison_metrics.csv` 行数校验：24 行，即 6 个 method × 4 个 split。
- 规则62复算交叉验证：combined/old precision、recall、specificity、f1、TP/FP/TN/FN 均与既有规则62 metrics CSV 一致。

## 审查与补丁

- 本地 adversarial review 发现初版报告使用绝对路径，不利于仓库内阅读；已改为项目相对路径。
- 本地 adversarial review 发现“test-F1 最优规则”可能被误解为调参选择；已补充说明仅用于展示对比，不作为重新调参或部署阈值选择。
- one-shot 流程要求使用 sub-agent 审查，但当前 sub-agent 工具规则要求用户显式授权代理协作；本轮用户未授权，因此未启动子代理，改为本地审查并记录该限制。

## 备注

- 当前目录不是 git worktree，`git status` / commit 步骤不可用，已跳过。
- 本任务指标仍基于 patient outcome 弱标签，只能作为技术信号对比，不能表述为临床诊断性能。
