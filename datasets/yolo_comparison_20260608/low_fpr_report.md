# Task 05 极低误检率尾部特征规则

## 输入与口径

- 60 阶段全量特征组合：`1089` 行。
- 旧数据 detected 图片：`1538`，患者：`504`。
- 新数据 detected 图片：`325`，患者：`101`。
- 旧数据 split 来自 `05_patient_splits.csv`；新数据作为外部 test 纳入 test 分片。
- 指标基于患者 outcome 弱标签，只能作为技术规则对比。

## S1 尾部特征分析

- 严格筛选条件：`patient_above_P99_rate >= 0.150000`、`tail_separation_ratio >= 1.500000`、`cross_data_tail_consistent == True`。
- 严格通过特征数：`0`。
- 当前数据没有出现“患病 P90 超过非患病 P99 1.5 倍”的极端尾部区域；方案 A 使用 top-tail fallback 仅用于完成可复核的低 FP 对比。

### Top Tail Features

| rank | feature | role | agg | direction | tail_ratio | patient>P99 | nonpatient_P99 | fp@P99 | consistent | strict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | raw_eyebrow_region_centroid_y_asym | mouth_dynamic | max | patient_higher | 0.924832 | 0.068783 | 0.106998 | 3 | true | false |
| 2 | raw_brow_outer_height_asym | mouth_dynamic | max | patient_higher | 0.915086 | 0.071429 | 0.149459 | 3 | true | false |
| 3 | raw_face_oval_region_point_spread_asym | all | mean | patient_higher | 0.904898 | 0.034392 | 0.080182 | 3 | true | false |
| 4 | bs_browInnerUp | all | max | patient_higher | 0.903394 | 0.023810 | 0.943993 | 3 | true | false |
| 5 | raw_face_oval_region_point_spread_asym | all | median | patient_higher | 0.900880 | 0.044974 | 0.081398 | 3 | false | false |
| 6 | raw_eyebrow_region_centroid_y_asym | all | max | patient_higher | 0.897443 | 0.066138 | 0.112205 | 3 | true | false |
| 7 | bs_eyeSquintLeft | all | max | patient_higher | 0.894643 | 0.010582 | 0.861946 | 3 | true | false |
| 8 | raw_face_oval_region_point_spread_asym | front_like | max | patient_higher | 0.894010 | 0.042328 | 0.080049 | 3 | false | false |
| 9 | raw_face_oval_region_point_spread_asym | front_like | median | patient_higher | 0.893382 | 0.039683 | 0.080049 | 3 | false | false |
| 10 | raw_face_oval_region_point_spread_asym | front_like | mean | patient_higher | 0.893382 | 0.039683 | 0.080049 | 3 | false | false |
| 11 | raw_brow_outer_height_asym | all | max | patient_higher | 0.892972 | 0.060847 | 0.155865 | 3 | true | false |
| 12 | bs_browInnerUp | mouth_dynamic | max | patient_higher | 0.886275 | 0.026455 | 0.940957 | 3 | true | false |

## S2/S3 规则构建

| feature | role | agg | strict | for_AND | for_weighted | tail_ratio | P99 | P995 | P999 | selection |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| raw_eyebrow_region_centroid_y_asym | mouth_dynamic | max | false | true | false | 0.924832 | 0.106998 | 0.108792 | 0.127105 | fallback_top_tail |
| raw_brow_outer_height_asym | mouth_dynamic | max | false | true | false | 0.915086 | 0.149459 | 0.155443 | 0.176630 | fallback_top_tail |
| raw_face_oval_region_point_spread_asym | all | mean | false | true | false | 0.904898 | 0.080182 | 0.084354 | 0.093755 | fallback_top_tail |
| raw_lip_midline_deviation | mouth_dynamic | max | false | false | true | 0.726098 | 0.028893 | 0.035584 | 0.065324 | scheme_b_tier1_core |
| bsdiff_mouth_abs | mouth_dynamic | max | false | false | true | 0.155365 | 0.189780 | 0.235801 | 0.455706 | scheme_b_tier1_core |
| bsdiff_mouth_lateral_abs | mouth_dynamic | max | false | false | true | 0.155365 | 0.189780 | 0.235801 | 0.455706 | scheme_b_tier1_core |

## S4 指标对比

- FP count 是首要指标；FP rate 按 `FP / (TN + FP)` 计算。
- 规则 62 combined：FP `63`，recall `0.582011`，precision `0.777385`。
- AND 方案 combined：FP `0`，recall `0.007937`，precision `1.000000`。
- Weighted 方案 combined：FP `1`，recall `0.026455`，precision `0.909091`。

| method | split | patients | TP | FP | TN | FN | fp_rate | recall | precision | specificity | f1 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| facesymai_rule62 | test | 178 | 45 | 14 | 71 | 48 | 0.164706 | 0.483871 | 0.762712 | 0.835294 | 0.592105 |
| facesymai_rule62 | val | 75 | 33 | 9 | 16 | 17 | 0.360000 | 0.660000 | 0.785714 | 0.640000 | 0.717391 |
| facesymai_rule62 | train | 352 | 142 | 40 | 77 | 93 | 0.341880 | 0.604255 | 0.780220 | 0.658120 | 0.681055 |
| facesymai_rule62 | combined | 605 | 220 | 63 | 164 | 158 | 0.277533 | 0.582011 | 0.777385 | 0.722467 | 0.665658 |
| low_fpr_and_3 | test | 178 | 0 | 0 | 85 | 93 | 0.000000 | 0.000000 | 0.000000 | 1.000000 | 0.000000 |
| low_fpr_and_3 | val | 75 | 2 | 0 | 25 | 48 | 0.000000 | 0.040000 | 1.000000 | 1.000000 | 0.076923 |
| low_fpr_and_3 | train | 352 | 1 | 0 | 117 | 234 | 0.000000 | 0.004255 | 1.000000 | 1.000000 | 0.008475 |
| low_fpr_and_3 | combined | 605 | 3 | 0 | 227 | 375 | 0.000000 | 0.007937 | 1.000000 | 1.000000 | 0.015748 |
| low_fpr_weighted | test | 177 | 2 | 0 | 84 | 91 | 0.000000 | 0.021505 | 1.000000 | 1.000000 | 0.042105 |
| low_fpr_weighted | val | 75 | 1 | 1 | 24 | 49 | 0.040000 | 0.020000 | 0.500000 | 0.960000 | 0.038462 |
| low_fpr_weighted | train | 352 | 7 | 0 | 117 | 228 | 0.000000 | 0.029787 | 1.000000 | 1.000000 | 0.057851 |
| low_fpr_weighted | combined | 604 | 10 | 1 | 225 | 368 | 0.004425 | 0.026455 | 0.909091 | 0.995575 | 0.051414 |

## 与规则 62 的 combined 差值

| method | FP_delta | recall_delta | precision_delta | specificity_delta |
| --- | --- | --- | --- | --- |
| low_fpr_and_3 | -63 | -0.574074 | 0.222615 | 0.277533 |
| low_fpr_weighted | -62 | -0.555556 | 0.131706 | 0.273108 |

## 结论

- 在 `combined FP <= 1` 约束下，最佳正预测方案为 `low_fpr_weighted`：FP `1`，recall `0.026455`，precision `0.909091`。
- 按验收口径 `FP <= 1`：达到。
- 按字面 `FP rate <= 0.001`：未达到；当前非患病样本量下 1 个 FP 的 rate 高于 0.001，除非 FP 为 0。

## 产物

- `low_fpr_tail_features.csv`：S1 全量尾部扫描。
- `low_fpr_selected_features.csv`：严格筛选和规则选用特征。
- `low_fpr_patient_predictions.csv`：方案 A/B 患者级预测。
- `low_fpr_comparison.csv`：规则 62、AND、Weighted 的 split 指标对比。

## 限制

这里的 `患病/不患病` 是患者 outcome 弱标签，不是人工面部不对称标签，也不是临床诊断标签。
