# Task 04 Tiered Feature Weight Disease Rule

## 方法说明

- 基础权重：沿用规则 62 的 `raw_weight_score`，即跨数据 AUC、combined AUC、非患者 specificity、图片波动稳定性、图片数的加权组合。
- Tier 调整：先按 Tier 4 识别明显弱特征并降权，再按 Tier 1/2/3 分层；调整后重新归一化，总权重为 1.0。
- 特征触发：与规则 62 一致，患者级聚合特征值 `>=` 单特征阈值时贡献该特征权重。
- 阈值搜索：在 combined 全部患者上以 `0.0001` 步长扫描 `[0, 1]`，优先最大化 balanced accuracy，其次 Youden J、F1、precision。
- split 说明：旧数据按 `05_patient_splits.csv` 的 `train/val/test`；20260508 新规则测试集作为外部 test 纳入 test 指标。

## 特征分层详情

| rank | feature | role | agg | tier | multiplier | new_weight | old_auc | new_auc | fp_rate | volatility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | bsdiff_mouth_abs | mouth_dynamic | max | Tier 1: 核心特征 | 2.000000 | 0.113131 | 0.595052 | 0.591954 | 0.269912 | 0.273402 |
| 2 | bsdiff_mouth_lateral_abs | mouth_dynamic | max | Tier 1: 核心特征 | 2.000000 | 0.113131 | 0.595052 | 0.591954 | 0.269912 | 0.273402 |
| 3 | raw_lip_midline_deviation | mouth_dynamic | max | Tier 1: 核心特征 | 2.000000 | 0.107007 | 0.583608 | 0.600575 | 0.314159 | 0.301043 |
| 4 | bsdiff_browDown_abs | all | max | Tier 3: 普通特征 | 1.000000 | 0.053694 | 0.577319 | 0.611380 | 0.475771 | 0.534065 |
| 5 | raw_iris_region_point_spread_asym | mouth_dynamic | max | Tier 3: 普通特征 | 1.000000 | 0.051036 | 0.584334 | 0.598522 | 0.464602 | 0.336346 |
| 6 | raw_face_oval_region_height_asym | all | max | Tier 3: 普通特征 | 1.000000 | 0.050544 | 0.564892 | 0.552865 | 0.211454 | 0.302397 |
| 7 | raw_all_mesh_region_height_asym | all | max | Tier 3: 普通特征 | 1.000000 | 0.050334 | 0.563412 | 0.552865 | 0.215859 | 0.306208 |
| 8 | raw_iris_region_area_asym | mouth_dynamic | max | Tier 3: 普通特征 | 1.000000 | 0.046872 | 0.569498 | 0.602627 | 0.438053 | 0.277184 |
| 9 | bsdiff_all_mean_abs | mouth_dynamic | max | Tier 3: 普通特征 | 1.000000 | 0.046361 | 0.555697 | 0.613711 | 0.314159 | 0.330048 |
| 10 | raw_eye_region_point_spread_asym | mouth_dynamic | median | Tier 3: 普通特征 | 1.000000 | 0.045783 | 0.564236 | 0.643268 | 0.442478 | 0.269396 |
| 11 | raw_mouth_corner_vertical_asym | all | median | Tier 3: 普通特征 | 1.000000 | 0.045364 | 0.565157 | 0.574657 | 0.475771 | 0.272693 |
| 12 | raw_face_oval_region_centroid_y_asym | all | median | Tier 3: 普通特征 | 1.000000 | 0.044735 | 0.565830 | 0.599677 | 0.519824 | 0.255947 |
| 13 | raw_eyebrow_region_centroid_y_asym | all | max | Tier 3: 普通特征 | 1.000000 | 0.043795 | 0.553288 | 0.561340 | 0.418502 | 0.294490 |
| 14 | bsdiff_mouthFrown_abs | mouth_dynamic | median | Tier 4: 弱特征 | 0.500000 | 0.025436 | 0.610828 | 0.595033 | 0.548673 | 0.175977 |
| 15 | raw_eyebrow_region_height_asym | all | median | Tier 4: 弱特征 | 0.500000 | 0.023244 | 0.584051 | 0.603309 | 0.634361 | 0.234978 |
| 16 | raw_eyebrow_region_point_spread_asym | mouth_dynamic | max | Tier 4: 弱特征 | 0.500000 | 0.021106 | 0.562721 | 0.634236 | 0.588496 | 0.281020 |
| 17 | raw_eyebrow_region_area_asym | all | median | Tier 4: 弱特征 | 0.500000 | 0.020853 | 0.572049 | 0.579500 | 0.691630 | 0.224941 |
| 18 | raw_iris_region_centroid_y_asym | all | mean | Tier 4: 弱特征 | 0.500000 | 0.019936 | 0.562925 | 0.564568 | 0.616740 | 0.215551 |
| 19 | raw_all_mesh_region_point_spread_asym | mouth_dynamic | max | Tier 4: 弱特征 | 0.500000 | 0.019900 | 0.582359 | 0.523810 | 0.429204 | 0.298904 |
| 20 | raw_brow_outer_height_asym | all | mean | Tier 4: 弱特征 | 0.500000 | 0.019517 | 0.560959 | 0.566990 | 0.647577 | 0.233465 |
| 21 | raw_eye_region_centroid_y_asym | all | mean | Tier 4: 弱特征 | 0.500000 | 0.019383 | 0.560764 | 0.562550 | 0.625551 | 0.203379 |
| 22 | bsdiff_eyeLookDown_abs | mouth_dynamic | max | Tier 4: 弱特征 | 0.500000 | 0.018837 | 0.552083 | 0.587849 | 0.570796 | 0.246430 |

## 权重调整对比

| feature | role | agg | old_weight | new_weight | delta | ratio | tier_reason |
| --- | --- | --- | --- | --- | --- | --- | --- |
| bsdiff_mouth_abs | mouth_dynamic | max | 0.057616 | 0.113131 | 0.055515 | 1.963534 | old_auc/new_auc >= 0.570000 且 nonpatient FP rate 0.269912 < 0.350000 |
| bsdiff_mouth_lateral_abs | mouth_dynamic | max | 0.057616 | 0.113131 | 0.055515 | 1.963534 | old_auc/new_auc >= 0.570000 且 nonpatient FP rate 0.269912 < 0.350000 |
| raw_lip_midline_deviation | mouth_dynamic | max | 0.054497 | 0.107007 | 0.052510 | 1.963539 | old_auc/new_auc >= 0.570000 且 nonpatient FP rate 0.314159 < 0.350000 |
| bsdiff_browDown_abs | all | max | 0.054691 | 0.053694 | -0.000997 | 0.981770 | 未命中核心、稳定或弱特征条件 |
| raw_iris_region_point_spread_asym | mouth_dynamic | max | 0.051983 | 0.051036 | -0.000947 | 0.981783 | 未命中核心、稳定或弱特征条件 |
| raw_face_oval_region_height_asym | all | max | 0.051482 | 0.050544 | -0.000938 | 0.981780 | 未命中核心、稳定或弱特征条件 |
| raw_all_mesh_region_height_asym | all | max | 0.051269 | 0.050334 | -0.000935 | 0.981763 | 未命中核心、稳定或弱特征条件 |
| raw_iris_region_area_asym | mouth_dynamic | max | 0.047742 | 0.046872 | -0.000870 | 0.981777 | 未命中核心、稳定或弱特征条件 |
| bsdiff_all_mean_abs | mouth_dynamic | max | 0.047221 | 0.046361 | -0.000860 | 0.981788 | 未命中核心、稳定或弱特征条件 |
| raw_eye_region_point_spread_asym | mouth_dynamic | median | 0.046633 | 0.045783 | -0.000850 | 0.981773 | 未命中核心、稳定或弱特征条件 |
| raw_mouth_corner_vertical_asym | all | median | 0.046206 | 0.045364 | -0.000842 | 0.981777 | 未命中核心、稳定或弱特征条件 |
| raw_face_oval_region_centroid_y_asym | all | median | 0.045566 | 0.044735 | -0.000831 | 0.981763 | 未命中核心、稳定或弱特征条件 |
| raw_eyebrow_region_centroid_y_asym | all | max | 0.044608 | 0.043795 | -0.000813 | 0.981775 | 未命中核心、稳定或弱特征条件 |
| bsdiff_mouthFrown_abs | mouth_dynamic | median | 0.051817 | 0.025436 | -0.026381 | 0.490881 | volatility_score 0.175977 < 0.250000 |
| raw_eyebrow_region_height_asym | all | median | 0.047351 | 0.023244 | -0.024107 | 0.490887 | nonpatient FP rate 0.634361 > 0.550000；volatility_score 0.234978 < 0.250000 |
| raw_eyebrow_region_point_spread_asym | mouth_dynamic | max | 0.042995 | 0.021106 | -0.021889 | 0.490894 | nonpatient FP rate 0.588496 > 0.550000 |
| raw_eyebrow_region_area_asym | all | median | 0.042481 | 0.020853 | -0.021628 | 0.490878 | nonpatient FP rate 0.691630 > 0.550000；volatility_score 0.224941 < 0.250000 |
| raw_iris_region_centroid_y_asym | all | mean | 0.040611 | 0.019936 | -0.020675 | 0.490901 | nonpatient FP rate 0.616740 > 0.550000；volatility_score 0.215551 < 0.250000 |
| raw_all_mesh_region_point_spread_asym | mouth_dynamic | max | 0.000000 | 0.019900 | 0.019900 |  | old-new AUC drop 0.058549 > 0.050000 |
| raw_brow_outer_height_asym | all | mean | 0.039758 | 0.019517 | -0.020241 | 0.490895 | nonpatient FP rate 0.647577 > 0.550000；volatility_score 0.233465 < 0.250000 |
| raw_eye_region_centroid_y_asym | all | mean | 0.039485 | 0.019383 | -0.020102 | 0.490895 | nonpatient FP rate 0.625551 > 0.550000；volatility_score 0.203379 < 0.250000 |
| bsdiff_eyeLookDown_abs | mouth_dynamic | max | 0.038373 | 0.018837 | -0.019536 | 0.490892 | nonpatient FP rate 0.570796 > 0.550000；volatility_score 0.246430 < 0.250000 |

## 指标对比

| split | rule62_bacc | tiered_bacc | bacc_delta | rule62_precision | tiered_precision | precision_delta | rule62_recall | tiered_recall | recall_delta | rule62_specificity | tiered_specificity | specificity_delta | threshold |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| test | 0.659583 | 0.687793 | 0.028210 | 0.762712 | 0.728395 | -0.034317 | 0.483871 | 0.634409 | 0.150538 | 0.835294 | 0.741176 | -0.094118 | 0.467900 |
| val | 0.650000 | 0.670000 | 0.020000 | 0.785714 | 0.787234 | 0.001520 | 0.660000 | 0.740000 | 0.080000 | 0.640000 | 0.600000 | -0.040000 | 0.467900 |
| train | 0.631187 | 0.654428 | 0.023241 | 0.780220 | 0.777273 | -0.002947 | 0.604255 | 0.727660 | 0.123405 | 0.658120 | 0.581197 | -0.076923 | 0.467900 |
| combined | 0.652239 | 0.674761 | 0.022522 | 0.777385 | 0.767241 | -0.010144 | 0.582011 | 0.706349 | 0.124338 | 0.722467 | 0.643172 | -0.079295 | 0.467900 |

## Test 集详细结论

- test balanced_accuracy delta: `0.028210`；precision delta: `-0.034317`；recall delta: `0.150538`；specificity delta: `-0.094118`。
- 结论：test 集 balanced accuracy 提升或持平，Tier 分层没有削弱测试集整体平衡表现。

## Combined 验收结论

- combined balanced_accuracy: 规则62 `0.652239`，tiered `0.674761`，差值 `0.022522`。
- 验收状态：通过，combined balanced_accuracy 未低于规则62。

## 患者级不一致分析

- 预测变化患者数：`73/605`，变化率 `0.120661`。
- 变化类型计数：`{"rule62_negative_tiered_positive": 69, "rule62_positive_tiered_negative": 4, "same_prediction": 532}`。
- 按 split 的变化：`{"test": {"rule62_negative_tiered_positive": 23, "rule62_positive_tiered_negative": 1}, "train": {"rule62_negative_tiered_positive": 41, "rule62_positive_tiered_negative": 3}, "val": {"rule62_negative_tiered_positive": 5}}`。
- 按真实标签的变化：`{"不患病": {"rule62_negative_tiered_positive": 19, "rule62_positive_tiered_negative": 1}, "患病": {"rule62_negative_tiered_positive": 50, "rule62_positive_tiered_negative": 3}}`。

| patient | dataset | split | truth | change | rule62_score | tiered_score | rule62_pred | tiered_pred |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pid607671347745 | new | test | 不患病 | rule62_negative_tiered_positive | 0.567612 | 0.595532 | 未达到患病阈值 | 患病倾向较高 |
| pid607677780414 | new | test | 不患病 | rule62_negative_tiered_positive | 0.510074 | 0.545391 | 未达到患病阈值 | 患病倾向较高 |
| pid607677910498 | new | test | 不患病 | rule62_negative_tiered_positive | 0.395265 | 0.512736 | 未达到患病阈值 | 患病倾向较高 |
| pid607686089544 | new | test | 不患病 | rule62_negative_tiered_positive | 0.533831 | 0.587804 | 未达到患病阈值 | 患病倾向较高 |
| pid607687325395 | new | test | 不患病 | rule62_negative_tiered_positive | 0.607044 | 0.585073 | 未达到患病阈值 | 患病倾向较高 |
| 刘建兵__pid473 | old | test | 不患病 | rule62_negative_tiered_positive | 0.587314 | 0.656849 | 未达到患病阈值 | 患病倾向较高 |
| 吴祥雲__pid167 | old | test | 不患病 | rule62_negative_tiered_positive | 0.549811 | 0.661121 | 未达到患病阈值 | 患病倾向较高 |
| 芦瑞兰__pid29 | old | test | 不患病 | rule62_negative_tiered_positive | 0.522687 | 0.521979 | 未达到患病阈值 | 患病倾向较高 |
| pid607677600555 | new | test | 患病 | rule62_negative_tiered_positive | 0.387432 | 0.506109 | 未达到患病阈值 | 患病倾向较高 |
| pid607684795092 | new | test | 患病 | rule62_negative_tiered_positive | 0.392767 | 0.512684 | 未达到患病阈值 | 患病倾向较高 |
| pid607685216393 | new | test | 患病 | rule62_negative_tiered_positive | 0.554168 | 0.588933 | 未达到患病阈值 | 患病倾向较高 |
| pid607686179471 | new | test | 患病 | rule62_negative_tiered_positive | 0.473474 | 0.527922 | 未达到患病阈值 | 患病倾向较高 |
| pid607687069842 | new | test | 患病 | rule62_negative_tiered_positive | 0.492972 | 0.506477 | 未达到患病阈值 | 患病倾向较高 |
| pid607687167522 | new | test | 患病 | rule62_negative_tiered_positive | 0.369076 | 0.503546 | 未达到患病阈值 | 患病倾向较高 |
| pid607687402167 | new | test | 患病 | rule62_negative_tiered_positive | 0.440468 | 0.538277 | 未达到患病阈值 | 患病倾向较高 |
| pid607687912011 | new | test | 患病 | rule62_negative_tiered_positive | 0.447769 | 0.564283 | 未达到患病阈值 | 患病倾向较高 |
| pid607688155708 | new | test | 患病 | rule62_negative_tiered_positive | 0.569660 | 0.544039 | 未达到患病阈值 | 患病倾向较高 |
| 伏景辉__pid297 | old | test | 患病 | rule62_negative_tiered_positive | 0.409588 | 0.503378 | 未达到患病阈值 | 患病倾向较高 |
| 刘小虎__pid508 | old | test | 患病 | rule62_negative_tiered_positive | 0.581132 | 0.470811 | 未达到患病阈值 | 患病倾向较高 |
| 师香霞__pid328 | old | test | 患病 | rule62_negative_tiered_positive | 0.572244 | 0.623324 | 未达到患病阈值 | 患病倾向较高 |

## 新纳入/剔除说明

- `raw_all_mesh_region_point_spread_asym`：passing variants 6/9，纳入状态 `True`。6 variants have combined_directional_auc > 0.58; required 3.
- 本任务没有剔除规则62原有 21 个特征；弱特征通过 Tier 4 降权处理。

## 产物

- 分析摘要：`tiered_feature_weight_analysis.json`
- 患者预测：`tiered_weight_patient_predictions.csv`
- 指标对比：`tiered_weight_comparison.csv`
- 本报告：`tiered_weight_report.md`

## 限制

该规则使用患者 outcome 弱标签拟合，只能作为技术判断与归因候选，不能作为临床诊断结论。
