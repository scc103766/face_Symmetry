# 任务单 #04 开发日志

## 执行摘要

- 已新增脚本：`scripts/build_tiered_weight_feature_disease_rule.py`
- 已生成任务单要求产物：
  - `datasets/yolo_comparison_20260608/tiered_feature_weight_analysis.json`
  - `datasets/yolo_comparison_20260608/tiered_weight_patient_predictions.csv`
  - `datasets/yolo_comparison_20260608/tiered_weight_comparison.csv`
  - `datasets/yolo_comparison_20260608/tiered_weight_report.md`
- 额外生成便于复核的明细：
  - `datasets/yolo_comparison_20260608/tiered_weight_feature_weights.csv`
  - `datasets/yolo_comparison_20260608/tiered_weight_patient_feature_contributions.csv`
  - `datasets/yolo_comparison_20260608/tiered_weight_score_threshold_sweep.csv`

## 实现内容

- 复用规则 62 的基础权重计算、患者级聚合、单特征阈值和触发逻辑。
- 新增 Tier 1/2/3/4 分层权重乘子，并将分层阈值全部参数化。
- 分层判定采用弱特征优先：先降权 Tier 4，再识别 Tier 1/2/3，避免高 FP、高波动或 old-new AUC 明显回落的特征被误提权。
- 评估并纳入 `raw_all_mesh_region_point_spread_asym`：9 个变体中 6 个满足 `combined_directional_auc > 0.58`，选取 `mouth_dynamic + max` 变体。
- 在 combined 全部患者上按 `[0, 1]`、步长 `0.0001` 搜索全局 `score_threshold`。
- 对规则 62 和新规则均输出 `test/val/train/combined` 指标；旧数据按 seed `20260520` 的 `05_patient_splits.csv`，新 20260508 规则测试集按外部 test 纳入。

## 关键结果

- 最优新阈值：`0.467900`
- combined balanced_accuracy：
  - 规则 62：`0.652239`
  - tiered_weight_v1：`0.674761`
  - 差值：`+0.022522`
- test balanced_accuracy：
  - 规则 62：`0.659583`
  - tiered_weight_v1：`0.687793`
  - 差值：`+0.028210`
- 核心特征权重提升：
  - `bsdiff_mouth_abs`：`0.057616 -> 0.113131`
  - `raw_lip_midline_deviation`：`0.054497 -> 0.107007`

## 验证命令

```bash
scripts/run_in_project_env.sh python -m py_compile scripts/build_tiered_weight_feature_disease_rule.py
scripts/run_in_project_env.sh python scripts/build_tiered_weight_feature_disease_rule.py
```

补充校验结果：

- 指定 4 个输出文件均存在。
- `tiered_weight_patient_predictions.csv` 的字段与规则 62 患者级预测字段完全一致。
- 新特征权重归一化总和为 `0.999999`，在 6 位格式化误差内等于 1。
- `tiered_weight_comparison.csv` 覆盖 2 个方法 x 4 个 split。
- 新规则 combined balanced_accuracy 不低于规则 62。

## 注意事项

- `precision` 和 `specificity` 相比规则 62 有所下降，但 `recall` 和 `balanced_accuracy` 提升；本任务的阈值选择目标是 combined balanced accuracy。
- 本规则仍使用患者 outcome 弱标签评估，不能作为临床诊断性能表述。
