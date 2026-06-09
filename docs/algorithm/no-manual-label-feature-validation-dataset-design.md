# 不使用人工轻微不对称标注的特征验证集构建方案

本文整理当前 FaceSymAi 项目下一阶段验证集建设思路：放弃“人工轻微不对称标签校准”，改为基于客观量化、正常分布基线、动作差异、弱监督稳健学习和一致性约束来验证 MediaPipe 特征是否有效。

适用对象：

```text
datasets/facesym_v1_all_images_no_gate_20260119
```

关联文档：

```text
docs/algorithm/mediapipe-pair-and-feature-difference-processing.md
docs/algorithm/mediapipe-largest-feature-difference-evidence-explanation.md
```

## 1. 为什么不做人工轻微不对称标签

轻微人脸不对称靠肉眼标注不稳定，主要问题是：

1. 正常人天然存在轻微左右差异，标注者很难判断“正常轻微不对称”和“病理性不对称”的边界。
2. 静态照片中姿态、表情执行、拍摄角度、光照和脸部遮挡都会影响肉眼判断。
3. 对轻微不对称做二分类标注，标注者间一致性很难保证；即使有多数票，也可能只是主观平均，不是可靠真值。
4. 当前业务标签是 patient outcome 的 `患病/不患病`，不是人工面瘫或人脸不对称标签。强行补一个肉眼轻微不对称标签，容易引入新的噪声。

因此，本阶段目标不是让人判断“是否轻微不对称”，而是构建一个不依赖人工不对称标注的验证体系：

- 用高质量不患病样本建立正常分布。
- 用同一患者静息到动作 role 的变化验证运动障碍。
- 用 patient-level 多实例聚合适配多 role 图片。
- 用 noisy-label / PU learning 承认 `患病/不患病` 是弱标签。
- 用一致性约束过滤偶发姿态、遮挡和检测误差。

## 2. 验证集目标

验证集需要回答四个问题：

| 问题 | 不使用人工标签的验证方式 |
| --- | --- |
| 特征是否偏离正常人群 | 使用高质量不患病样本建立 median/MAD 正常范围 |
| 特征是否反映运动障碍 | 比较同一患者 `front -> action role` 的动作差异 |
| 多张图如何汇总到患者级 | 使用 role max、mean+max、top-k 或 MIL 聚合 |
| 异常是否稳定可靠 | 使用同患者重复图、水平翻转、跨 role 一致性验证 |

最终输出不再是“人工标注校准准确率”，而是：

```text
normal_reference_z_score
abnormality_percentile
role_specific_outlier_score
delta_motion_asymmetry_score
patient_level_outlier_score
consistency_pass_rate
weak_label_recall_at_fixed_specificity
```

## 3. 数据集分层设计

所有划分都必须以 patient 为单位，不能让同一患者的不同图片跨集合泄漏。

### 3.1 Normal Reference Set

用途：建立“不患病高质量样本”的正常分布基线。

纳入条件：

- `label_group = 不患病`
- MediaPipe `detection_status = detected`
- raw landmarks 数量满足 478 点
- 至少包含核心 role 中的 `front`，优先要求 `front/smile/teeth/eyes_closed/forehead_wrinkle/frown`
- 质量权重高、姿态/距离控制变量不异常
- 不用于模型训练、不用于阈值最终验证

该集合只负责计算每个 role、每个 feature 的：

```text
median
MAD
robust_sigma = 1.4826 * MAD
percentile distribution
```

### 3.2 Threshold Calibration Set

用途：固定输出阈值。

策略：

- 从未进入 Normal Reference Set 的患者中抽取。
- 包含 `患病` 与 `不患病`。
- 使用不患病样本固定 specificity，例如 0.85、0.90、0.95。
- 在 specificity 固定后观察患病弱标签下 recall、PR-AUC、不同 role 覆盖率。

注意：这里的 recall 是对 patient outcome 弱标签的召回，不是人工不对称真值召回。

### 3.3 Lockbox Validation Set

用途：最终报告，不参与任何阈值、特征、权重选择。

要求：

- patient-level 锁定。
- 覆盖不同 split、role 完整度、质量分层、患病/不患病。
- 阈值、特征公式、聚合方式全部冻结后才能评估。

报告内容：

```text
specificity on non-disease proxy normal
weak-label recall on disease patients
score distribution shift
feature direction stability
role coverage and missingness
consistency metrics
```

### 3.4 External / Temporal Validation Set

用途：验证泛化。

建议后续新增一批完全未参与特征发现的数据：

- 新采集日期
- 新设备或新操作者
- 新患者
- 不参与 Normal Reference、阈值选择和模型训练

该集合比内部 lockbox 更重要，因为它能暴露采集流程、设备和人群变化带来的漂移。

## 4. 正常分布基线

### 4.1 基本公式

对每个 role、每个特征，在 Normal Reference Set 中计算：

```text
median_ref(role, feature)
MAD_ref(role, feature) = median(abs(x - median_ref))
robust_sigma = max(1.4826 * MAD_ref, epsilon)
feature_z = (current_value - median_ref) / robust_sigma
```

对于当前大多数不对称强度特征，数值越大表示越异常，因此可定义：

```text
positive_outlier_z = max(0, feature_z)
abnormality_percentile = percentile_rank(current_value in reference distribution)
```

### 4.2 role-specific outlier score

每张图先得到 role 内特征异常分：

```text
role_specific_outlier_score =
  weighted_top_k_mean(clipped_positive_outlier_z)
```

建议先不复杂化权重：

1. 第一版用 top-k mean，例如取最高 5 个特征 z-score 平均。
2. 第二版再按 feature family 分组，避免口部特征数量过多导致口部支配全部分数。
3. 第三版再引入 V1.1 训练得到的 feature weight。

### 4.3 patient-level normal deviation score

患者级分数按核心 role 聚合：

```text
patient_normal_deviation_score =
  aggregate(front, smile, teeth, eyes_closed, forehead_wrinkle, frown)
```

第一版建议同时比较三种聚合：

| 聚合方式 | 解释 |
| --- | --- |
| max | 任一 role 强异常即提示风险，召回更高 |
| mean | 整体稳定异常才提示风险，特异性更高 |
| mean + max | 兼顾稳定性和局部高风险 |

## 5. 从静态不对称转向动作差异

单张图的左右差异会混入每个人天然脸型差异。更稳的方式是比较同一患者的静息图与动作图：

```text
front -> smile
front -> teeth
front -> eyes_closed
front -> forehead_wrinkle
front -> frown
```

### 5.1 口部动作差异

以口角为例：

```text
left_motion  = dist(point_action[291], point_front[291]) / scale
right_motion = dist(point_action[61],  point_front[61])  / scale

delta_mouth_corner_motion_asym =
  abs(left_motion - right_motion) / (abs(left_motion) + abs(right_motion) + epsilon)
```

同时保留垂直方向版本：

```text
left_y_delta  = y_action[291] - y_front[291]
right_y_delta = y_action[61]  - y_front[61]

delta_mouth_corner_vertical_motion_asym =
  abs(left_y_delta - right_y_delta) / (abs(left_y_delta) + abs(right_y_delta) + epsilon)
```

优先 role：

```text
front -> smile
front -> teeth
front -> frown
```

### 5.2 唇部动作差异

建议新增：

```text
delta_lip_midline_deviation
delta_lip_opening_asym
delta_lip_region_centroid_y_asym
```

解释：

- `delta_lip_midline_deviation` 观察动作后唇中心是否更偏离中线。
- `delta_lip_opening_asym` 观察示齿或张口动作是否左右打开不均。
- `delta_lip_region_centroid_y_asym` 观察整个唇部区域的垂直位置是否发生不对称变化。

### 5.3 闭眼动作差异

闭眼应从 `front -> eyes_closed` 比较：

```text
left_eye_closure_motion =
  eye_aperture_front_left - eye_aperture_eyes_closed_left

right_eye_closure_motion =
  eye_aperture_front_right - eye_aperture_eyes_closed_right

delta_eye_closure_asym =
  abs(left_eye_closure_motion - right_eye_closure_motion)
  / (abs(left_eye_closure_motion) + abs(right_eye_closure_motion) + epsilon)
```

同时计算：

```text
movement_absence_eyes_closed =
  1 - normalized(max(left_eye_closure_motion, right_eye_closure_motion))
```

### 5.4 眉额和皱眉动作差异

眉额动作建议分两类：

```text
front -> forehead_wrinkle
front -> frown
```

新增：

```text
delta_brow_raise_asym
delta_frown_brow_asym
delta_eyebrow_region_height_asym
movement_absence_forehead_wrinkle
movement_absence_frown
```

这些特征比单张图上的 `raw_eyebrow_region_height_asym` 更接近“动态控制能力”，也能减少天然眉形差异的影响。

## 6. Patient-Level 多实例学习

当前每个患者有多张 role 图片，标签是患者级 `患病/不患病`。因此患者应视为 bag，图片或 role 视为 instance：

```text
patient = bag
image/role = instance
```

建议实验：

| 实验 | 方法 | 目的 |
| --- | --- | --- |
| A | 当前 HB proxy 规则 | 作为 baseline |
| B | role max 聚合 | 验证任一 role 强异常是否更有召回 |
| C | role mean + max 聚合 | 验证稳定异常与局部异常的组合 |
| D | LightGBM / logistic regression + top-k role features | 轻量 MIL |
| E | attention/MIL 聚合 | 后续可选，不作为第一版 |

第一版不需要深度模型。可以先用以下患者级特征：

```text
front_outlier_score
smile_outlier_score
teeth_outlier_score
eyes_closed_outlier_score
forehead_wrinkle_outlier_score
frown_outlier_score
max_role_outlier_score
mean_role_outlier_score
top2_role_outlier_score
delta_mouth_corner_motion_asym
delta_eye_closure_asym
delta_brow_raise_asym
movement_absence_by_role
consistency_score
```

比较指标：

```text
precision
recall
specificity
balanced_accuracy
ROC-AUC
PR-AUC
recall_at_specificity_0.85
recall_at_specificity_0.90
recall_at_specificity_0.95
```

## 7. Noisy-Label / PU Learning

当前 `患病/不患病` 不是人脸不对称真值，因此不能把它当干净标签。

建议口径：

```text
患病 = noisy positive
不患病 = unlabeled / noisy negative
```

含义：

- 不假设所有患病患者都有明显人脸不对称。
- 不假设所有不患病患者都完全正常。
- 模型目标是学习“与患病 outcome 弱相关且偏离正常分布的稳定面部运动异常”，不是学习临床诊断本身。

可先做三种轻量实验：

| 实验 | 做法 |
| --- | --- |
| label smoothing | 患病目标值设为 0.8-0.9，不患病目标值设为 0.0-0.2 |
| sample reweighting | 高质量、role 完整、稳定异常样本权重更高 |
| PU-style ranking | 将不患病当 unlabeled，训练患病分数相对更高，但不强制每个不患病为真阴性 |

报告时必须标注：这些是弱监督性能，不等于人工人脸不对称准确率。

## 8. 一致性约束

不使用人工标签时，一致性是判断特征可靠性的关键。

### 8.1 同患者同 role 重复一致性

如果同一患者同一 role 有多张图，异常分应稳定：

```text
same_role_score_cv
same_role_score_range
same_role_top_feature_overlap
```

规则：

- 同 role 分数波动过大，降权。
- 同 role top 特征完全不一致，标记为不稳定。

### 8.2 水平翻转一致性

对图片做水平翻转后：

```text
abs_asymmetry_feature(original) ~= abs_asymmetry_feature(flipped)
signed_left_right_feature(original) ~= -signed_left_right_feature(flipped)
```

输出：

```text
flip_abs_invariance_error
flip_signed_direction_error
flip_consistency_pass
```

规则：

- 绝对不对称强度在翻转前后应基本不变。
- 有方向的 left-minus-right 特征应反号。
- 翻转不一致的样本不用于正常基线，可在验证集中单独报告。

### 8.3 跨 role 一致性

口部异常应在 `smile/teeth/frown` 中有一定一致性，眼部异常应在 `front/eyes_closed` 中有解释关系，眉额异常应在 `forehead_wrinkle/frown` 中有解释关系。

建议指标：

```text
mouth_role_consistency = consistency(smile, teeth, frown)
eye_role_consistency = consistency(front, eyes_closed)
brow_role_consistency = consistency(forehead_wrinkle, frown)
overall_role_consistency_score
```

规则：

- 单张图异常但同患者其他 role 完全不支持，应降权。
- 多个相关 role 同时异常，患者级分数上调。

## 9. 推荐实验顺序

### Step 1：正常分布基线

构建高质量不患病 Normal Reference Set，输出：

```text
metadata/30_no_manual_normal_reference_stats.csv
metadata/30_no_manual_image_feature_z_scores.csv
metadata/30_no_manual_patient_outlier_scores.csv
```

验证：

- 不患病 lockbox specificity 是否能稳定达到 0.85/0.90/0.95。
- 患病弱标签 recall 是否高于当前 Grade V+ 规则。
- top outlier features 是否与当前主证据一致。

### Step 2：动作差异特征

新增 `front -> action role` delta 特征，输出：

```text
metadata/31_no_manual_delta_motion_features.csv
metadata/31_no_manual_delta_motion_patient_scores.csv
```

优先特征：

```text
delta_mouth_corner_motion_asym
delta_lip_opening_asym
delta_eye_closure_asym
delta_brow_raise_asym
delta_frown_brow_asym
movement_absence_by_role
```

验证：

- 动作差异分数是否比静态不对称分数有更高 recall at fixed specificity。
- 口部、眼部、眉额动作差异是否分别在对应 role 中更突出。

### Step 3：阈值重扫

对比：

```text
current Grade III+
current Grade IV+
current Grade V+
normal_reference_outlier_score
delta_motion_outlier_score
combined static + delta score
```

输出：

```text
metadata/32_no_manual_threshold_sweep.csv
reports/32_no_manual_threshold_sweep.md
```

### Step 4：patient-level MIL

比较：

```text
A: 当前 HB proxy 规则
B: role max 聚合
C: role mean + max 聚合
D: LightGBM / logistic regression + top-k role features
```

输出：

```text
metadata/33_no_manual_mil_patient_predictions.csv
metadata/33_no_manual_mil_metrics.json
reports/33_no_manual_mil_validation.md
```

### Step 5：Noisy-label / PU learning

输出：

```text
metadata/34_no_manual_noisy_label_predictions.csv
metadata/34_no_manual_pu_metrics.json
reports/34_no_manual_noisy_label_pu_validation.md
```

验证：

- 是否降低不患病高分误报。
- 是否保留患病弱标签召回。
- 是否比干净二分类假设更稳定。

### Step 6：一致性约束

输出：

```text
metadata/35_no_manual_consistency_metrics.csv
reports/35_no_manual_consistency_validation.md
```

验证：

- 同患者同 role 稳定性。
- 水平翻转不变性和方向反转。
- 口部/眼部/眉额跨 role 一致性。
- 一致性降权后 FP 是否下降。

## 10. 推荐验收口径

不使用人工不对称标签时，不能只用单一 accuracy 判断有效性。建议按以下组合验收：

| 验收项 | 通过标准 |
| --- | --- |
| 正常基线特异性 | 在 lockbox 不患病样本上达到预设 specificity 0.85/0.90/0.95 |
| 弱标签召回 | 在同一 specificity 下，患病 recall 高于当前 Grade V+ 规则 |
| 动作差异增益 | delta motion score 相比静态 score 提升 recall 或 PR-AUC |
| 特征方向稳定 | top 特征方向在 train/val/test/lockbox 不反转 |
| role 稳定性 | 口部、眼部、眉额特征在对应 role 中最强 |
| 一致性 | 翻转一致性、同 role 重复一致性、跨 role 一致性达到阈值 |
| 抗质量干扰 | 性能不是由 pose、distance、bbox、matrix 类变量驱动 |

## 11. 最小可落地版本

第一阶段最值得先做：

```text
动作差异特征 + 正常分布 z-score
```

原因：

1. 不依赖人工主观标签。
2. 能减少静态天然脸型差异的影响。
3. 能把“轻微静态不对称”和“真实动作障碍”分开。
4. 可以直接复用当前 09/11/12/20 阶段产物。
5. 可以用固定 specificity 的方式和当前 Grade V+ 规则公平比较。

第一版最小产物：

```text
metadata/30_no_manual_normal_reference_stats.csv
metadata/30_no_manual_image_feature_z_scores.csv
metadata/30_no_manual_patient_outlier_scores.csv
metadata/31_no_manual_delta_motion_features.csv
metadata/31_no_manual_delta_motion_reference_stats.csv
metadata/31_no_manual_delta_motion_patient_scores.csv
metadata/32_no_manual_threshold_sweep.csv
metadata/32_no_manual_validation_summary.json
reports/32_no_manual_validation_summary.md
```

第一版最小结论模板：

```text
在不使用人工人脸不对称标签的条件下，
以高质量不患病样本建立正常分布，
并通过 front->action role 的动作差异衡量运动障碍。
在 specificity 固定为 0.90 时，
比较当前 Grade V+ 规则、正常分布 outlier score、delta motion score 和二者组合的患病弱标签 recall。
```

### 11.1 已落地脚本

当前已新增无人工轻微不对称标注验证入口：

```text
scripts/build_no_manual_feature_validation.py
```

运行命令：

```bash
scripts/run_in_project_env.sh python scripts/build_no_manual_feature_validation.py \
  --dataset datasets/facesym_v1_all_images_no_gate_20260119
```

脚本读取：

```text
metadata/05_patient_splits.csv
metadata/09_mediapipe_full_features.csv
metadata/12_v11_hb_proxy_patient_grades.csv
metadata/03_keypoints.csv
```

脚本输出：

```text
metadata/30_no_manual_normal_reference_stats.csv
metadata/30_no_manual_image_feature_z_scores.csv
metadata/30_no_manual_patient_outlier_scores.csv
metadata/31_no_manual_delta_motion_features.csv
metadata/31_no_manual_delta_motion_reference_stats.csv
metadata/31_no_manual_delta_motion_patient_scores.csv
metadata/32_no_manual_threshold_sweep.csv
metadata/32_no_manual_validation_summary.json
reports/32_no_manual_validation_summary.md
```

当前默认参数：

```text
reference_splits = train
calibration_splits = val
specificity_targets = 0.85, 0.90, 0.95
top_k = 5
z_cap = 10
min_reference_roles = 6
```

说明：

- `30_no_manual_normal_reference_stats.csv` 使用 train split 中高质量不患病、核心 role 完整患者建立 role-feature 正常范围。
- `30_no_manual_image_feature_z_scores.csv` 保留原始 `feature_z`，并额外生成 `clipped_positive_outlier_z` 用于评分，避免 MAD 极小的特征支配总分。
- `31_no_manual_delta_motion_features.csv` 计算 `front -> smile/teeth/eyes_closed/forehead_wrinkle/frown` 的动作差异。
- `32_no_manual_threshold_sweep.csv` 对比当前 Grade III+/IV+/V+、正常分布 outlier、delta motion outlier 和静态+动作组合分数。

## 12. 关键注意事项

- 不患病样本只能作为“代理正常分布”，不能假设绝对正常。
- 患病样本只能作为 noisy positive，不能假设每个患病者都有面部运动异常。
- 正常分布、阈值、模型权重、lockbox 验证必须分开，避免验证集被反复调参污染。
- 所有结果都应标注为“无人工标签弱监督验证”，不要写成临床诊断准确率。
- 如果后续有专家标注，应优先标明显中重度不对称或 HB 等级，不建议回到轻微不对称二分类标注。
