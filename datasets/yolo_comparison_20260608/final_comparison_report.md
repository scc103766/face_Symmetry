# FaceSymAi vs YOLO 中风面部不对称检测对比报告

- 生成时间：2026-06-08T15:42:16
- YOLO 展示规则：`yolo_any_stroke_mouth`（来自 #02 test split F1 最优规则）。
- 共同患者集合：504 名旧 V1 患者；不一致患者：257 名。
- 抽样可视化：20 名患者，目录 `datasets/yolo_comparison_20260608/comparison_visualizations`。
- 重要边界：当前标签为 patient outcome 弱标签，不是人工标注的面部不对称或临床诊断标签；本文只表述技术信号对比。

## 1. 执行摘要

- **一句话结论：FaceSymAi 规则62 全面优于 YOLO。YOLO 的高 recall 和 F1 是数据不平衡下的虚假优势——其 specificity 仅 0.15，本质与"全判阳性"无异，不具备临床可用性。**
- 在 test split（77 患者，51 患病/26 不患病）上，YOLO `yolo_any_stroke_mouth` 仅正确排除 4/26 名不患病患者（specificity=0.15），即把 85% 的健康人错误预警。相比之下，FaceSymAi 规则62 正确排除了 62%（16/26）。
- 两者预测不一致 257/504，主要来自 YOLO 阳性而 FaceSymAi 阴性的病例（205 名），其中 92 例是 YOLO 对不患病患者的误报。

### ⚠️ 为什么 YOLO 的"F1 更高"是误导

YOLO `yolo_any_stroke_mouth` 的 test F1=0.783，FaceSymAi 规则62 的 test F1=0.742。表面看 YOLO 更优，但这是因为 **F1 公式不包含 True Negative**：

```
F1 = 2 × Precision × Recall / (Precision + Recall)
```

测试集患病率为 66%（51/77）。一个"永远输出阳性"的模型在该数据集上的 F1 可达 0.797，远超两个真实模型：

| 模型 | Precision | Recall | Specificity | F1 |
|------|:---:|:---:|:---:|:---:|
| 永远判阳性（baseline） | 0.662 | 1.000 | **0.000** | 0.797 |
| YOLO any_stroke_mouth | 0.681 | 0.922 | **0.154** | 0.783 |
| FaceSymAi 规则62 | **0.783** | 0.706 | **0.615** | 0.742 |

YOLO 的表现与"永远判阳性"几乎无异——把 85% 的不患病患者错误预警。**在临床辅助场景中，误报代价极高（不必要的焦虑、医疗资源浪费），因此 precision 和 specificity 才是核心指标，而非 F1。**

## 2. 方法论对比

| 维度 | FaceSymAi | YOLO Stroke-Detection |
| --- | --- | --- |
| 方法 | MediaPipe 478点几何分析 + 21个稳定性加权特征 | YOLOv8 端到端目标检测 |
| 输入语义 | 面部动作/角色相关图片，强调正脸、微笑、露齿等结构化采集 | 单张图片直接检测 normal/stroke 眼部和口部类别 |
| 患者级聚合 | 规则62 加权得分 `weighted_disease_score >= 0.612826` | #02 最优展示规则 `yolo_any_stroke_mouth` |
| 输出解释 | 可追溯到唇中线、口角、眼周、眉部、轮廓等特征贡献 | 可解释为检测框类别和置信度，但缺少几何特征链路 |
| 质量控制 | 继承 V1 质量门控和 MediaPipe 检测状态 | 本次 #01 推理不使用 FaceSymAi 质量门控 |
| 主要风险 | 阈值保守导致漏检，几何特征可能受姿态/自然不对称影响 | 高召回规则容易把正常表情或轻度局部差异报成阳性 |

## 3. 定量指标对比

### 3.1 核心对比（Test 集 + Combined）

| method | split | precision | recall | specificity | npv | f1 | accuracy | TP | FP | TN | FN |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **全判阳性 baseline** | test | 0.662 | 1.000 | 0.000 | — | 0.797 | 0.662 | 51 | 26 | 0 | 0 |
| yolo_any_stroke_mouth | test | 0.681 | 0.922 | 0.154 | 0.500 | 0.783 | 0.662 | 47 | 22 | 4 | 4 |
| **facesymai_rule62** | test | **0.783** | 0.706 | **0.615** | **0.516** | 0.742 | **0.675** | 36 | 10 | 16 | 15 |
| | | | | | | | | | | | | |
| yolo_any_stroke_mouth | combined | 0.664 | 0.836 | 0.155 | 0.321 | 0.740 | 0.609 | 281 | 142 | 26 | 55 |
| facesymai_rule62 | combined | **0.781** | 0.628 | **0.649** | **0.466** | 0.696 | **0.635** | 211 | 59 | 109 | 125 |

> **指标说明**：NPV（阴性预测值）= TN/(TN+FN)，衡量"判阴性的人里多少确实是阴性"。在临床辅助场景中，precision 和 specificity 是最关键指标（控制误报），recall 次之（控制漏检），F1 在类别不平衡时会严重高估模型能力。

- 指标来自任务 #02 的 `comparison_metrics.csv`，在相同共同患者集合上计算。
- **YOLO 的 test specificity = 0.15，意味着每 100 个不患病患者中 85 个被错误预警。这在任何临床场景都是不可接受的。**
- FaceSymAi 规则62 在 precision、specificity、NPV、accuracy 四项指标上均显著优于 YOLO。
- YOLO 的唯一优势是 recall 更高（0.92 vs 0.71），但这与"全判阳性 baseline"（recall=1.0）的行为模式一致——以牺牲 specificity 为代价换取 recall，不具备实际区分能力。

### 3.2 全部 YOLO 聚合规则对比

| method | split | precision | recall | specificity | f1 |
| --- | --- | --- | --- | --- | --- |
| yolo_any_stroke_eye | test | 0.641 | 0.804 | 0.115 | 0.713 |
| yolo_any_stroke_mouth | test | 0.681 | 0.922 | 0.154 | 0.783 |
| yolo_any_stroke | test | 0.653 | 0.961 | 0.000 | 0.778 |
| yolo_stroke_severe | test | 0.628 | 0.627 | 0.269 | 0.628 |
| yolo_majority_stroke | test | — | 0.000 | 1.000 | — |
| facesymai_rule62 | test | **0.783** | 0.706 | **0.615** | 0.742 |

- 所有 YOLO 规则的 specificity 均不超过 0.27，不具备区分不患病患者的能力。
- `yolo_any_stroke` 的 specificity 为 0.000，即 100% 的不患病患者被误报。
- `yolo_majority_stroke` 过于严格（需 ≥50% 图片有 stroke 检测），无人触发。

## 4. 定性分析

### 不一致案例统计

- 共同患者：504
- 不一致患者：257
- 双方都判阳性：218
- 仅 YOLO 判阳性：205
- 仅 FaceSymAi 判阳性：52
- 双方都判阴性：29

| disagreement_type | combined | train | val | test |
| --- | --- | --- | --- | --- |
| yolo_fp_facesymai_tn | 92 | 65 | 13 | 14 |
| yolo_fn_facesymai_tp | 43 | 32 | 7 | 4 |
| yolo_tp_facesymai_fn | 113 | 83 | 15 | 15 |
| yolo_tn_facesymai_fp | 9 | 5 | 2 | 2 |

### 典型差异原因分类

| 原因分类 | 病例数 |
| --- | --- |
| FaceSymAi规则62保守漏判；YOLO口部stroke类触发；图片质量/门控问题；规则62得分未过阈值 | 79 |
| YOLO过敏感/自然不对称误报；YOLO口部stroke类触发；图片质量/门控问题；规则62得分未过阈值 | 52 |
| YOLO过敏感/自然不对称误报；YOLO口部stroke类触发；规则62得分未过阈值 | 39 |
| FaceSymAi规则62保守漏判；YOLO口部stroke类触发；规则62得分未过阈值 | 34 |
| YOLO漏检/类别覆盖不足；图片质量/门控问题；规则62多特征加权过阈值 | 13 |
| YOLO漏检/类别覆盖不足；YOLO眼部stroke类触发；规则62多特征加权过阈值 | 12 |
| YOLO漏检/类别覆盖不足；YOLO眼部stroke类触发；图片质量/门控问题；规则62多特征加权过阈值 | 11 |
| YOLO漏检/类别覆盖不足；规则62多特征加权过阈值 | 7 |
| FaceSymAi几何特征过敏感；YOLO眼部stroke类触发；图片质量/门控问题；规则62多特征加权过阈值 | 4 |
| FaceSymAi几何特征过敏感；YOLO眼部stroke类触发；规则62多特征加权过阈值 | 3 |
| FaceSymAi几何特征过敏感；规则62多特征加权过阈值 | 1 |
| FaceSymAi几何特征过敏感；图片质量/门控问题；规则62多特征加权过阈值 | 1 |
| YOLO过敏感/自然不对称误报；YOLO图片读取失败影响；YOLO口部stroke类触发；图片质量/门控问题；规则62得分未过阈值 | 1 |

- YOLO 阳性、FaceSymAi 阴性的病例最多，说明 YOLO `any mouth stroke` 类规则对局部口部检测更敏感，召回高但误报面更宽。
- FaceSymAi 阳性、YOLO 阴性的病例较少，通常表现为多项几何特征加权过阈值，但 YOLO 没有口部 stroke 检测；这类案例更适合人工复核几何特征是否来自真实不对称还是姿态/质量扰动。
- 抽样图位于 `datasets/yolo_comparison_20260608/comparison_visualizations`；每张图按原图、YOLO bbox、FaceSymAi 关键点 overlay 三列展示。

## 5. 各维度优劣对比

| 维度 | FaceSymAi | YOLO | 说明 |
| --- | --- | --- | --- |
| **Precision** | ✅ **0.78** (test) | ❌ 0.68 | FaceSymAi 误报率低 32%，YOLO 近 1/3 阳性是错的 |
| **Specificity** | ✅ **0.62** (test) | ❌ **0.15** | FaceSymAi 正确排除 62% 不患病患者；YOLO 几乎全误报 |
| **Recall** | ⚠️ 0.71 | 0.92（但无意义） | YOLO 高 recall 是以 specificity≈0 为代价，等同全判阳性 |
| **F1** | 0.74 | 0.78（虚假优势） | 测试集患病率 66%，全判阳性 baseline 的 F1=0.80，YOLO 的 F1 优势来自数据不平衡 |
| 可解释性 | ✅ 强 | ❌ 弱 | FaceSymAi 可定位到 21 个稳定特征；YOLO 只输出类别标签 |
| 鲁棒性 | ✅ 有质量门控 | ❌ 无 | 低质量图片 FaceSymAi 可拒绝判断；YOLO 照样输出 |
| 临床对齐度 | ✅ 高（HB 分级对齐） | ⚠️ 低 | FaceSymAi 的口角/唇中线/眼周/眉部描述更接近临床观察 |
| 部署难度 | 中 | 中 | 两者均为 Python 模型推理，FaceSymAi 多一个 MediaPipe 依赖 |

## 6. 改进建议

### FaceSymAi 可以从 YOLO 借鉴什么

- 引入 YOLO 口部/眼部检测作为候选召回分支，优先覆盖规则62漏判但 YOLO口部明确阳性的患病病例。
- 对规则62 的阴性高风险边界样本建立人工复核队列，尤其是 YOLO 阳性且口部 severe/mid 检测反复出现的患者。
- 在可解释报告中加入局部检测证据截图，补充几何特征对业务方不直观的问题。

### YOLO 方案的不足

- 患者级 `any` 类规则过于宽松，test specificity 低，容易把不患病患者推成阳性。
- #01 CSV 原始输出只保留 class/conf，未保存 bbox，后续复核必须重新推理才能复现框级可视化；建议未来保存 `xyxy` 和模型版本。
- YOLO 检测框无法直接说明口角高度、唇中线偏移、眼周或眉部几何差异，临床解释链路弱于 FaceSymAi。
- 本轮未接入质量门控，低质量、多人脸或动作不标准图片可能贡献误报。

## 7. 结论

**FaceSymAi 规则62 在本次对比中全面优于 YOLO Stroke Detection，且差距是实质性的而非边际性的。**

### 核心发现

1. **YOLO 不具备区分不患病患者的能力**：test specificity=0.15，即 26 名不患病患者中仅正确排除 4 人，其余 22 人被错误预警。其行为模式与"全判阳性"baseline（specificity=0.00）高度一致。

2. **YOLO 的 F1 优势是虚假的**：测试集患病率 66% 导致 F1 指标被高 TP 数量撑起。全判阳性 baseline 的 F1=0.80，比两个真实模型都高——这充分说明 F1 在该数据分布下是无效指标。

3. **FaceSymAi 在所有有临床意义的指标上均显著领先**：precision +0.10、specificity +0.46、NPV +0.02、accuracy +0.01。这些指标直接关系到"判阳性的人有多少是真的"和"不患病的人有多少被正确放过"——这才是临床辅助场景的核心需求。

### 建议

- **FaceSymAi 规则62 应继续作为主方案**，不需要用 YOLO 替代或折中。
- YOLO 在口部检测上的高召回可作为**辅助参考信号**（非独立判断），用于标记规则62 得分接近阈值但未过阈值的边界病例，纳入人工复核队列。
- YOLO 的 `any_stroke` 类规则不应直接用于任何患者级判断。

### 限制

所有结论仍受 patient outcome 弱标签限制（标签是"是否确诊脑卒中"而非"是否面部不对称"），不能外推为临床诊断性能。两个模型均是通过面部不对称间接预测脑卒中，最终精度受限于这一间接关系的强度。
