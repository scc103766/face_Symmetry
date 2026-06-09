# 任务单 #04

**任务名称**：特征权重分层优化 — 强调跨数据一致性强的核心特征
**优先级**：P0
**依赖**：无（使用已有的 60 阶段特征数据和规则62 作为 baseline）

## 📖 技术背景

规则 62 使用 21 个去重推荐特征 + 稳定性加权判断患者是否有患病倾向。当前权重公式为等权组合：

```
0.30×跨数据AUC稳定分 + 0.20×合并AUC分 + 0.25×非患者specificity分 + 0.15×图片波动稳定分 + 0.10×图片数分
```

问题：**平均主义**——跨数据一致性极强的核心特征（如 `bsdiff_mouth_abs`、`raw_lip_midline_deviation`）与波动大的弱特征权重差异不大，导致核心特征的区分能力被稀释。

## 📝 任务描述

基于现有 60 阶段数据，重新设计特征权重，强调：

1. **跨数据一致性强的特征大幅提权**（old AUC 和 new AUC 都高，且差异小）
2. **波动性高的特征降权**（图片间 IQR/robust CV 大）
3. **对不患病患者误判多的特征降权**（nonpatient FP rate 高）
4. 评估是否纳入当前未在 21 推荐中但 Cohen's d 高的特征

### 分层规则

| 层级 | 条件 | 权重策略 |
|------|------|---------|
| **Tier 1: 核心特征** | old_directional_auc >= 0.57 AND new_directional_auc >= 0.57 AND nonpatient_fp_rate < 0.35 | 基础权重 × 2.0 |
| **Tier 2: 稳定特征** | volatility_score > 0.70 (即低波动) AND direction_consistent == true AND 不在 Tier 1 | 基础权重 × 1.5 |
| **Tier 3: 普通特征** | 不在 Tier 1/2/4 | 基础权重 × 1.0 |
| **Tier 4: 弱特征** | (abs(old_auc - new_auc) > 0.05 AND old_auc > new_auc) OR nonpatient_fp_rate > 0.55 OR volatility_score < 0.25 (即高波动) | 基础权重 × 0.5 |

- "基础权重" 沿用规则 62 的 raw_weight_score（`0.30×跨数据AUC + 0.20×合并AUC + 0.25×非患者specificity + 0.15×波动稳定 + 0.10×图片数`）
- 最终权重归一化为总和 1.0

### 候选特征评估

额外评估以下未在 21 推荐中的特征，满足条件则纳入：

- `raw_all_mesh_region_point_spread_asym`：Cohen's d = 0.33（21 推荐中最高之一），old AUC ~0.58，new AUC ~0.51（偏弱但仍有信号）
  - 纳入条件：至少 3 个聚合变体中 combined_directional_auc > 0.58
  - 若纳入，选取 combined_directional_auc 最高的变体

### 全局阈值搜索

权重调整后，在 combined 全部患者上重新搜索全局阈值 `score_threshold`：

1. 计算每位患者的 `weighted_disease_score`（触发特征权重之和）
2. 在 [0, 1] 范围以 0.0001 步长扫描阈值
3. 按以下优先级选择最佳阈值：
   - 优先：balanced_accuracy 最高
   - 其次：Youden J 最高
   - 再次：F1 最高
   - 最后：precision 最高（打破平局）

### 评估

在 train/val/test 上评估新规则，与规则 62 对比：

| 指标 | 含义 |
|------|------|
| precision | 判阳性中真阳性的比例 |
| recall | 真阳性中判出的比例 |
| specificity | 真阴性中正确排除的比例 |
| f1 | 调和平均 |
| balanced_accuracy | (recall + specificity) / 2 |
| youden_j | recall + specificity - 1 |

## 📥 输入文件

- 60 阶段全量特征指标：`datasets/combined_disease_feature_candidates_20260529/metadata/60_combined_disease_feature_all_metrics.csv`
- 60 阶段推荐特征：`datasets/combined_disease_feature_candidates_20260529/metadata/60_combined_disease_feature_recommended_distinct.csv`
- 60 阶段特征阈值：`datasets/combined_disease_feature_candidates_20260529/metadata/60_combined_disease_feature_thresholds.csv`
- 患者级特征值：`datasets/combined_disease_feature_candidates_20260529/metadata/60_combined_disease_feature_candidates.csv`
- 患者切分：`datasets/facesym_v1_by_name_20260119/metadata/05_patient_splits.csv`
- 规则 62 患者级预测（baseline 对比）：`datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_patient_predictions.csv`
- 规则 62 特征权重（baseline 对比）：`datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_feature_weights.csv`

## 📤 输出要求

- [ ] `scripts/build_tiered_weight_feature_disease_rule.py` — 新规则构建脚本
- [ ] `datasets/yolo_comparison_20260608/tiered_feature_weight_analysis.json` — 分析摘要，包含：
  - 各特征的分层归属（Tier 1/2/3/4）
  - 调整前后的权重对比
  - 新纳入/剔除的特征说明
- [ ] `datasets/yolo_comparison_20260608/tiered_weight_patient_predictions.csv` — 患者级预测，字段对齐规则62格式
- [ ] `datasets/yolo_comparison_20260608/tiered_weight_comparison.csv` — 与规则62的指标对比表

| method | split | precision | recall | specificity | f1 | balanced_accuracy | youden_j | threshold |
|--------|-------|-----------|--------|-------------|-----|-------------------|----------|-----------|
| facesymai_rule62 | test/val/train/combined | ... | ... | ... | ... | ... | ... | 0.612826 |
| tiered_weight_v1 | test/val/train/combined | ... | ... | ... | ... | ... | ... | 搜索值 |

- [ ] `datasets/yolo_comparison_20260608/tiered_weight_report.md` — Markdown 报告，包含：
  - 方法说明（分层规则）
  - 特征分层详情表
  - 权重调整对比表
  - 指标对比表（含提升/下降的差值列）
  - test 集详细结论
  - 与规则 62 的患者级不一致分析

## ✅ 验收标准

1. 脚本可运行：`scripts/run_in_project_env.sh python scripts/build_tiered_weight_feature_disease_rule.py`
2. 新规则的 combined balanced_accuracy >= 规则62（否则说明分层策略无效，需分析原因）
3. 指标计算正确，与规则62 baseline 可交叉验证
4. 报告包含完整的权重调整理由和对比分析
5. 核心特征（bsdiff_mouth_abs、raw_lip_midline_deviation）在新规则中的权重明显提高

## ⚠️ 需要关注

- 分层阈值（AUC>=0.57、FP<0.35）是初步设定，脚本应参数化，方便后续调整
- `raw_all_mesh_region_point_spread_asym` 在 all_metrics 中有多个聚合变体，需选取 combined_directional_auc 最高的
- 确保 train/val/test 切分一致（seed=20260520）
- 新规则的特征触发机制与规则 62 相同：患者级特征值 >= 单特征阈值时触发
- 全局阈值搜索应在 combined 全部患者上进行，不应只看 test

## 🔗 参考资料

- `datasets/combined_disease_feature_candidates_20260529/reports/62_stable_weighted_feature_disease_rule.md` — 规则62详细说明
- `docs/algorithm/facial-symmetry-technical-solution.md` — 技术方案
- `docs/algorithm/evaluation-protocol.md` — 评估协议
