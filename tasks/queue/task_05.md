# 任务单 #05

**任务名称**：极低误检率下的特征发现与严格规则构建
**优先级**：P0
**依赖**：无

## 📖 技术背景

任务 #04 的分层权重方案提升了 balanced accuracy (+2.8%) 和 recall (+15%)，但 specificity 有所下降（-9.4%）。当前要求转向**极低误检场景**：在非患病患者中误报率控制在千分之一以内（FP ≤ 1，约 227 非患病患者中最多误报 0~1 人），在此约束下最大化召回率。

**核心思路转变**：不再依赖加权求和 + 平衡阈值，而是寻找"非患病患者绝不会超过"的极端特征阈值。

## 📝 任务描述

### S1: 全量特征尾部扫描

从 60 阶段全量特征（`60_combined_disease_feature_all_metrics.csv` + 原始患者级特征值）中，对每个特征计算：

| 指标 | 含义 | 
|------|------|
| `nonpatient_P99` | 非患病患者特征值的第 99 百分位 |
| `nonpatient_P995` | 第 99.5 百分位 |
| `nonpatient_P999` | 第 99.9 百分位 |
| `nonpatient_max` | 非患病患者最大值 |
| `patient_above_P99_rate` | 患病患者中超过 nonpatient_P99 的比例 |
| `patient_above_P995_rate` | 同上（P99.5） |
| `tail_separation_ratio` | patient_P90 / nonpatient_P99，>1 表示患病长尾明显高于非患病上界 |
| `combined_fp_at_P99` | 在 P99 阈值下的 combined 误报数（应为 combined_negative_n × 0.01 ≈ 2.3） |
| `cross_data_tail_consistent` | old 和 new 数据集上 tail 模式是否一致 |

筛选条件（初步，参数化）：

```python
patient_above_P99_rate >= 0.15        # 至少 15% 患病患者在非患病 P99 之上
tail_separation_ratio >= 1.5          # 患病长尾明显超过非患病上界
cross_data_tail_consistent == True    # 两批数据模式一致
```

输出全部通过筛选的特征列表，按 `tail_separation_ratio` 降序排列。

### S2: 极端阈值设定

对筛选出的每个特征，设定触发阈值为 `nonpatient_P99`（即非患病患者只有 1% 会超过的值）。

可选：也测试 `nonpatient_P995`（0.5%）和 `nonpatient_P999`（0.1%）。

### S3: 两种规则组合

#### 方案 A: AND 严格逻辑

```
患者阳性 = (feature_A_value >= threshold_A)
         AND (feature_B_value >= threshold_B)  
         AND (feature_C_value >= threshold_C)
```

从 S1 结果中选取 tail_separation_ratio 最高的 3 个特征。需同时触发才算阳性。

#### 方案 B: 核心加权 + 极高阈值

仅用 Tier 1 核心特征（跨数据 AUC≥0.57 且 FP<0.35，约 3-5 个），权重按 `tail_separation_ratio` 比例分配。

全局阈值搜索条件：**combined specificity ≥ 0.995**（即 combined FP ≤ 1），在此约束下最大化：
- 优先：recall（找到更多患病患者）
- 其次：precision

### S4: 评估

| 评估项 | 说明 |
|--------|------|
| FP count | 非患病患者中被误报的人数（目标 ≤ 1） |
| FP rate | FP / 非患病患者总数（目标 ≤ 0.001） |
| Recall | 患病患者中正确检出的比例 |
| Precision | 阳性预测中真阳性的比例 |
| 与规则 62 对比 | FP、recall、precision 的绝对差值 |

输出 test/val/train/combined 四个分片上的指标。

## 📥 输入文件

- 60 阶段全量特征指标：`datasets/combined_disease_feature_candidates_20260529/metadata/60_combined_disease_feature_all_metrics.csv`
- 60 阶段推荐特征：`datasets/combined_disease_feature_candidates_20260529/metadata/60_combined_disease_feature_recommended_distinct.csv`
- 患者级特征值：`datasets/combined_disease_feature_candidates_20260529/metadata/60_combined_disease_feature_candidates.csv`
- 旧数据患者级特征：`datasets/facesym_v1_by_name_20260119/metadata/09_mediapipe_full_features.csv`
- 新数据患者级特征：`datasets/combined_disease_feature_candidates_20260529/metadata/40_mediapipe_evidence_image_features.csv`
- 患者切分：`datasets/facesym_v1_by_name_20260119/metadata/05_patient_splits.csv`
- 规则 62 患者预测（baseline）：`datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_patient_predictions.csv`

## 📤 输出要求

- [ ] `scripts/build_low_fpr_feature_rule.py` — 构建脚本
- [ ] `datasets/yolo_comparison_20260608/low_fpr_tail_features.csv` — S1 尾部扫描结果，所有候选特征的尾部指标
- [ ] `datasets/yolo_comparison_20260608/low_fpr_selected_features.csv` — 通过筛选的特征列表
- [ ] `datasets/yolo_comparison_20260608/low_fpr_patient_predictions.csv` — 方案 A 和方案 B 的患者级预测
- [ ] `datasets/yolo_comparison_20260608/low_fpr_comparison.csv` — 指标对比表

| method | split | fp_count | fp_rate | recall | precision | specificity | f1 | threshold/rule |
|--------|-------|----------|---------|--------|-----------|-------------|-----|----------------|
| facesymai_rule62 | test | ... | ... | ... | ... | ... | ... | 0.612826 |
| low_fpr_and_3 | test | ... | ... | ... | ... | ... | ... | AND(featA,featB,featC) |
| low_fpr_weighted | test | ... | ... | ... | ... | ... | ... | 搜索值 |

- [ ] `datasets/yolo_comparison_20260608/low_fpr_report.md` — Markdown 报告：
  - 尾部特征分析（哪些特征有"非患病绝不会超过"的极端区域）
  - 方案 A vs 方案 B vs 规则 62 的详细对比
  - FP count 和 FP rate 作为首要指标
  - 结论：是否达到千分之一误检率目标

## ✅ 验收标准

1. 脚本可运行
2. S1 尾部扫描覆盖全部 60 阶段候选特征（至少 100+ 个变体）
3. 至少发现 3 个满足 tail_separation_ratio ≥ 1.5 的特征
4. 方案 A 和/或方案 B 的 combined FP ≤ 1（含 ≤1）
5. 报告清晰展示每个方案的 FP count（不是 rate，是具体人数）

## ⚠️ 需要关注

- nonpatient_P99 等百分位计算需在 combined 非患病患者上进行
- 如果非患病患者少于 100 人，P99 取第 2 大值更合理（至少 100 人时 P99=第2大 ≈ 2%误报率上限）
- 跨数据一致性：old 和 new 的非患病患者分别计算 P99，如果两者差异 > 30% 则标记为不一致
- 方案 B 的阈值搜索应在满足 FP ≤ 1 的约束下进行

## 🔗 参考资料

- `docs/algorithm/evaluation-protocol.md`
- `datasets/combined_disease_feature_candidates_20260529/reports/62_stable_weighted_feature_disease_rule.md`
