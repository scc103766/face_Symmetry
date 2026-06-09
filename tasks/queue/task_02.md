# 任务单 #02

**任务名称**：患者级聚合 + FaceSymAi 规则62 对比指标计算
**优先级**：P0
**依赖**：任务单 #01（YOLO 图片级预测结果就绪）

## 📖 技术背景

任务 #01 产生了 YOLO 模型的图片级预测。本任务需要：
1. 将 YOLO 图片级输出聚合为患者级预测
2. 获取 FaceSymAi 规则 62 在同样测试集上的患者级预测
3. 计算两者的对比指标

**YOLO 患者级聚合逻辑**：YOLO 本身没有多图片聚合机制，需要设计合理的映射规则。建议以下多条规则并行评估：

| 规则名 | 逻辑 |
|--------|------|
| `yolo_any_stroke_eye` | 患者任一图片检测到 strokeEye* → 阳性 |
| `yolo_any_stroke_mouth` | 患者任一图片检测到 strokeMouth* → 阳性 |
| `yolo_any_stroke` | 患者任一图片检测到任何 stroke* → 阳性 |
| `yolo_stroke_severe` | 患者任一图片检测到 strokeEyeSevere 或 strokeMouthSevere → 阳性 |
| `yolo_majority_stroke` | 患者 stroke 检测比例 >= 0.5 → 阳性 |

## 📝 任务描述

1. 写脚本 `scripts/compare_yolo_vs_facesymai.py`
2. 从任务 #01 输出加载 YOLO 图片级预测
3. 实现患者级聚合（上述 5 条规则），产生患者级预测
4. 从已有数据加载 FaceSymAi 规则 62 的患者级结果
5. 计算对比指标表
6. 输出报告

## 📥 输入

- YOLO 图片级预测：`datasets/yolo_comparison_20260608/yolo_per_image_predictions.csv`（来自任务#01）
- FaceSymAi 规则62 患者级结果：`datasets/combined_disease_feature_candidates_20260529/reports/62_stable_weighted_feature_disease_rule.md` 及对应数据文件
- 患者级切分：`datasets/facesym_v1_by_name_20260119/metadata/05_patient_splits.csv`

## 📤 输出要求

- [ ] `datasets/yolo_comparison_20260608/yolo_patient_predictions.csv`：患者级 YOLO 预测，列为：
  - `patient_id`, `patient_label`, `split`
  - 每种聚合规则的预测结果（True/False）
  - 每患者的 YOLO 检测统计（图片数、stroke检测数、最高严重度等）
- [ ] `datasets/yolo_comparison_20260608/comparison_metrics.csv`：对比指标表

| 列 | 说明 |
|-----|------|
| `method` | yolo_any_stroke / yolo_stroke_severe / ... / facesymai_rule62 |
| `split` | train / val / test / combined |
| `precision` | TP/(TP+FP) |
| `recall` | TP/(TP+FN) |
| `specificity` | TN/(TN+FP) |
| `f1` | 2*P*R/(P+R) |
| `accuracy` | (TP+TN)/total |
| `tp`, `fp`, `tn`, `fn` | 计数 |

- [ ] `datasets/yolo_comparison_20260608/comparison_report.md`：Markdown 格式的对比报告，内容包括：
  - 数据概览（患者数、图片数、标签分布）
  - YOLO 各聚合规则的指标表
  - YOLO 最优规则 vs FaceSymAi 规则62 的详细对比
  - 初步分析（谁在哪个指标上更好、为什么）

## ✅ 验收标准

1. 脚本可运行，所有输出文件生成
2. 指标计算正确（可与已有 FaceSymAi 报告中的数字交叉验证）
3. 报告包含完整的数字对比和分析
4. FaceSymAi 规则62 的指标需从实际数据重新计算（不从文档复制），确保可复现

## ⚠️ 需要关注

- FaceSymAi 规则 62 的数据可能在 `datasets/combined_disease_feature_candidates_20260529/` 下，需要定位其患者级分数文件
- 两个方案的测试集必须一致（同样的患者ID）
- 注意 train/val/test 是患者级切分，确保不跨分片泄漏

## 🔗 参考资料

- `datasets/combined_disease_feature_candidates_20260529/reports/62_stable_weighted_feature_disease_rule.md` — 规则62详细说明
- `docs/algorithm/evaluation-protocol.md` — 评估协议
- `datasets/facesym_v1_by_name_20260119/metadata/05_patient_splits.csv` — 患者切分
