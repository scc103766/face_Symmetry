# 任务单 #03

**任务名称**：定性对比分析 + 综合对比报告
**优先级**：P1
**依赖**：任务单 #01、#02

## 📖 技术背景

任务 #01 和 #02 完成了定量指标对比。本任务进行深层定性分析：
1. 找出两个方案判断不一致的案例
2. 分析差异原因
3. 评估两者的方法论优劣
4. 产出最终的综合对比报告

## 📝 任务描述

1. 写脚本 `scripts/analyze_comparison_disagreements.py`，找出 FaceSymAi 和 YOLO（最优规则）判断不一致的患者
2. 对不一致案例抽样，输出可视化对比（原图 + YOLO标注 + FaceSymAi关键点标注）
3. 分析差异原因归类（如：YOLO漏检、FaceSymAi过敏感、图片质量差、角色不匹配等）
4. 写综合对比报告

## 📥 输入

- `datasets/yolo_comparison_20260608/yolo_per_image_predictions.csv`
- `datasets/yolo_comparison_20260608/yolo_patient_predictions.csv`
- FaceSymAi 规则62 的患者级分数/预测数据
- V1 数据集图片和标注图（`datasets/facesym_v1_by_name_20260119/`）

## 📤 输出要求

- [ ] `datasets/yolo_comparison_20260608/disagreement_cases.csv`：不一致案例清单，每行一个患者，包含：
  - `patient_id`, `patient_label`, `split`
  - `yolo_prediction`, `facesymai_prediction`
  - `disagreement_type`：yolo_fp_facesymai_tn / yolo_fn_facesymai_tp
  - `analysis_reason`：差异原因分析
- [ ] `datasets/yolo_comparison_20260608/comparison_visualizations/`：抽样不一致案例的可视化（原图、YOLO框、关键点图对比）
- [ ] `datasets/yolo_comparison_20260608/final_comparison_report.md`：最终综合报告，包含：

### 报告结构

```
# FaceSymAi vs YOLO 中风面部不对称检测对比报告

## 1. 执行摘要
- 一句话结论

## 2. 方法论对比
| 维度 | FaceSymAi | YOLO Stroke-Detection |
|------|-----------|----------------------|
| 方法 | MediaPipe 478点几何分析 | YOLOv8 端到端检测 |
| ...

## 3. 定量指标对比
- 指标对比表（来自任务#02）

## 4. 定性分析
- 不一致案例统计
- 典型差异原因分类

## 5. 各维度优劣对比
| 维度 | FaceSymAi | YOLO | 说明 |
|------|-----------|------|------|
| 精度 | | | |
| 可解释性 | | | |
| 鲁棒性 | | | |
| 速度 | | | |
| 临床对齐度 | | | |
| 部署难度 | | | |

## 6. 改进建议
- FaceSymAi 可以从 YOLO 借鉴什么
- YOLO 方案的不足

## 7. 结论
```

## ✅ 验收标准

1. 不一致案例清单完整，分析归类合理
2. 可视化对比图清晰（至少抽样 20 例不一致患者）
3. 最终报告覆盖所有对比维度，结论有理有据
4. 报告可直接用于向业务方展示

## 🔗 参考资料

- `docs/algorithm/facial-symmetry-technical-solution.md` — FaceSymAi 技术方案
- `docs/algorithm/evaluation-protocol.md` — 评估协议
- `modules/facial_asymmetry_service/` — 当前服务实现
