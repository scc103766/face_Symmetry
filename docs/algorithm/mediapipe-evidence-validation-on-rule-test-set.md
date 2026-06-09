# MediaPipe 主证据特征在规则测试集上的有效性验证

本文记录 `docs/algorithm/mediapipe-largest-feature-difference-evidence-explanation.md` 中“患病更高”的主证据特征，在新构建的脑卒中预警 App 规则测试集上的验证结果。

## 验证对象

测试集：

```text
datasets/stroke_warning_app_rule_test_set_20260508
```

标签规则：

- 患病：同一条记录同时满足 `风险等级=紧急风险`、`曾经得过中风=是`、`家人得过脑卒中=有`。
- 不患病：无阳性记录，且至少一条 `低风险` 全指标正常记录。

可用人脸 role：

- `front_contour`
- `smile_teeth`
- `eyes_right`

该测试集没有原证据文档中的 `forehead_wrinkle`、`frown`、`eyes_closed` role，因此不能完整复验那些依赖眉额/皱眉/闭眼动作的结论。

## 验证产物

构建脚本：

```text
scripts/validate_mediapipe_evidence_on_rule_test_set.py
```

运行命令：

```bash
scripts/run_in_project_env.sh python scripts/validate_mediapipe_evidence_on_rule_test_set.py \
  --dataset datasets/stroke_warning_app_rule_test_set_20260508
```

输出文件：

- `metadata/40_mediapipe_evidence_keypoints.csv`
- `metadata/40_mediapipe_evidence_image_features.csv`
- `metadata/40_mediapipe_evidence_patient_features.csv`
- `metadata/40_mediapipe_evidence_feature_validation.csv`
- `metadata/40_mediapipe_evidence_validation_summary.json`
- `reports/40_mediapipe_evidence_feature_validation.md`

## 样本覆盖

- 入选待检测图片：327
- MediaPipe detected 图片：325
- no_face：2
- detected label 分布：`患病` 141 张，`不患病` 184 张
- detected role 分布：`front_contour` 109、`smile_teeth` 108、`eyes_right` 108

主判断使用患者级 `all` role 的 `max` 聚合，避免把同一患者多图当成独立样本。患者级样本为 `患病` 42、`不患病` 59。

## 主判断结果

判断标准：

- 目标方向为 `患病均值 > 不患病均值`。
- `strong_supported`：方向正确且 AUC >= 0.60。
- `supported`：方向正确且 AUC >= 0.55。
- `weak_supported`：方向正确且 AUC > 0.50。
- `not_supported`：方向不符合，或区分度未超过随机。

| feature | 结果 | 患病均值 | 不患病均值 | 差值 | AUC | 结论 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| `raw_lip_midline_deviation` | supported | 0.011438 | 0.010652 | 0.000785 | 0.583939 | 支持，唇中线偏移在新测试集上仍表现为患病更高 |
| `raw_eyebrow_region_height_asym` | supported | 0.094024 | 0.086890 | 0.007134 | 0.550847 | 支持，眉区高度不对称方向成立 |
| `raw_all_mesh_region_point_spread_asym` | weak_supported | 0.016698 | 0.015881 | 0.000817 | 0.514124 | 弱支持，全脸点云离散差方向成立但区分度弱 |
| `raw_face_oval_region_centroid_y_asym` | weak_supported | 0.054362 | 0.053656 | 0.000706 | 0.527038 | 弱支持，脸轮廓 y 质心方向成立但区分度弱 |
| `bsdiff_mouthFrown_abs` | not_supported | 0.005742 | 0.006816 | -0.001073 | 0.546207 | 主口径未支持，均值方向与预期相反 |
| `bsdiff_mouth_abs` | not_supported | 0.014226 | 0.014348 | -0.000122 | 0.627119 | 主口径未支持，均值方向与预期相反 |
| `raw_mouth_corner_vertical_asym` | not_supported | 0.031150 | 0.031161 | -0.000011 | 0.539548 | 主口径未支持，均值几乎相同且方向不成立 |
| `raw_iris_region_centroid_y_asym` | not_supported | 0.034721 | 0.034946 | -0.000224 | 0.532284 | 主口径未支持 |
| `raw_lip_region_centroid_y_asym` | not_supported | 0.019378 | 0.019645 | -0.000267 | 0.539548 | 主口径未支持 |
| `raw_eye_region_centroid_y_asym` | not_supported | 0.034039 | 0.034828 | -0.000790 | 0.528652 | 主口径未支持 |

主口径下支持数为 4/10，支持率 0.400。

## Role 分层补充结论

虽然患者级 `all + max` 主判断只支持 4/10 个特征，但 role 分层显示部分证据在特定采集动作中更稳定：

- `front_contour` 中，`bsdiff_mouthFrown_abs`、`bsdiff_mouth_abs`、`raw_eyebrow_region_height_asym`、`raw_face_oval_region_centroid_y_asym`、`raw_iris_region_centroid_y_asym`、`raw_eye_region_centroid_y_asym` 达到 supported，`raw_lip_midline_deviation` 和 `raw_lip_region_centroid_y_asym` 为 weak_supported。
- `smile_teeth` 中，`raw_lip_midline_deviation` 达到 strong_supported；`bsdiff_mouthFrown_abs`、`bsdiff_mouth_abs`、`raw_eyebrow_region_height_asym` 达到 supported。
- `eyes_right` 中，`raw_mouth_corner_vertical_asym`、`raw_eyebrow_region_height_asym`、`raw_lip_region_centroid_y_asym` 达到 supported。

这说明特征有效性不是全局无条件成立，而是依赖 role、动作执行强度和患者级聚合方式。

## 有效性判断

在当前三条件规则测试集上，可以认为以下证据得到独立弱监督支持：

1. `raw_lip_midline_deviation`：最值得保留。它是几何点证据，主判断达到 supported，且在 `smile_teeth` 达到 strong_supported。
2. `raw_eyebrow_region_height_asym`：主判断 supported，三个可用 role 中均 supported，说明它在新测试集上相对稳定。
3. `raw_all_mesh_region_point_spread_asym` 和 `raw_face_oval_region_centroid_y_asym`：方向成立但区分度弱，可作为辅助证据，不适合作为单独强规则。
4. `bsdiff_mouthFrown_abs`、`bsdiff_mouth_abs`：role 分层中有支持，但患者级 all+max 均值方向未通过，不能作为当前规则测试集上的主证据。
5. `raw_mouth_corner_vertical_asym`：只在 `eyes_right` role 支持，主判断未通过，后续需要结合动作 role 或质量控制复核。

## 解释边界

该验证证明的是“这些 MediaPipe 特征在规则标签测试集上与最终 `患病/不患病` 反馈存在或不存在统计关联”。它不能证明临床因果，也不能证明这些特征就是脑卒中或面瘫真值。

由于当前患病标签是三条件强筛选弱标签，样本从 300 人收紧到 101 人，阳性样本只有 42 人。部分原始数据集上成立的特征在这个测试集上未通过，可能来自：

- 新测试集缺少 `frown`、`forehead_wrinkle`、`eyes_closed` 等原证据高贡献 role。
- 患病标签变窄后，阳性人群不再等同于原始 patient outcome 分布。
- `front_contour/smile_teeth/eyes_right` 的动作执行强度和采集姿态差异会影响 blendshape 和 y 质心统计。
- 单个患者多条记录和多图聚合方式会改变均值方向。

因此，当前可作为“特征筛选有效性证据”，不能作为最终医学诊断性能声明。
