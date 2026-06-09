# MediaPipe 最大差异主证据来源与数据集形成原因说明

本文解释当前 MediaPipe 全流程中差异最大的几类主证据来自哪里、如何计算，以及为什么它们会在 `facesym_v1_all_images_no_gate_20260119` 数据集上形成当前的患病/不患病差异。

分析对象：

```text
datasets/facesym_v1_all_images_no_gate_20260119
```

主要依据：

```text
metadata/09_mediapipe_full_features.csv
metadata/09_mediapipe_feature_differences.csv
metadata/11_v11_role_aware_feature_set.csv
metadata/12_v11_hb_proxy_mediapipe_grade_differences.csv
metadata/20_mediapipe_end_to_end_feature_differences.csv
reports/20_mediapipe_end_to_end_summary.md
```

## 解释边界

当前 `患病/不患病` 是 patient outcome 弱监督标签，不是人工面瘫标签，也不是人工人脸不对称真值。因此下列差异应解释为“在当前数据集和当前处理流程下与患病标签共同出现的面部几何/表情差异”，不能直接解释为临床因果。

同时，`all-images/no-gate` 数据集没有启用严格质量门控。它保留了更多真实采集差异，也会把 role 执行强度、姿态残留、闭眼/皱眉/微笑配合程度等因素带入统计。20 阶段主证据已经排除 `matrix_*`、`pose_*`、采集距离/尺度、`*_centroid_z_asym` 等明显姿态或距离变量，但剩余特征仍可能包含采集和动作执行差异。

## 证据来源总览

| 证据组 | 代表特征 | 来源 | 当前方向 | 主要含义 |
| --- | --- | --- | --- | --- |
| 口部 blendshape 左右差 | `bsdiff_mouthFrown_abs`、`bsdiff_mouth_abs` | MediaPipe 52 个 blendshape 中 Left/Right 成对系数 | 患病更高 | 口部表情控制左右不一致 |
| 全脸 478 点点云差 | `raw_all_mesh_region_point_spread_asym` | 478 个 raw landmarks 按面部中线切成左右点云 | 患病更高 | 左右半脸点云离散程度不一致 |
| 唇中线偏移 | `raw_lip_midline_deviation` | 上下唇中心点 13/14 到中线 168/1/152 的偏移 | 患病更高 | 唇中心偏离面部中线 |
| 口角高低差 | `raw_mouth_corner_vertical_asym` | 左右口角点 291/61 的 y 坐标差，按眼外角距离归一化 | 患病更高 | 左右口角垂直高度不一致 |
| 微笑 blendshape 左右差 | `bsdiff_mouthSmile_abs` | `mouthSmileLeft` 与 `mouthSmileRight` 的绝对差 | 不患病更高 | 微笑动作强度和左右笑容激活差异 |
| 眉额/轮廓/眼唇区域 y 质心差 | `raw_eyebrow_region_height_asym`、`raw_face_oval_region_centroid_y_asym`、`raw_iris_region_centroid_y_asym`、`raw_lip_region_centroid_y_asym`、`raw_eye_region_centroid_y_asym` | 478 点区域统计 | 模型权重或 HB grade 中更高 | 垂直方向区域位置不对称 |

## 患病更高的主证据

### `bsdiff_mouthFrown_abs`

来源：

- 从 MediaPipe blendshape 读取 `mouthFrownLeft` 与 `mouthFrownRight`。
- 计算 `abs(mouthFrownLeft - mouthFrownRight)`。
- 字段名前缀 `bsdiff_` 表示左右 blendshape 差值，后缀 `_abs` 表示只看差异大小，不看左高还是右高。

数据表现：

| role | 患病均值 | 不患病均值 | 差值 | sep_auc |
| --- | ---: | ---: | ---: | ---: |
| all | 0.005388 | 0.004103 | 0.001286 | 0.558638 |
| smile | 0.003202 | 0.001424 | 0.001778 | 0.583299 |
| teeth | 0.005804 | 0.003547 | 0.002258 | 0.603156 |

形成原因：

- 口部是当前数据集中最稳定出现差异的区域之一。患病组在 smile、teeth、frown 等动态 role 中更容易出现左右口部牵拉、下垂或闭合控制不一致。
- `mouthFrown` 本身不是“皱眉”动作，而是口角下拉/口部下垂相关 blendshape。它在 `teeth` 中排名高，说明示齿动作下的口部左右负向牵拉差异更明显。
- 该特征是绝对差，方向不区分左侧或右侧异常，因此适合做“不对称强度”证据，不适合单独判断病侧。

### `bsdiff_mouth_abs`

来源：

- 当前脚本在存在 `mouthLeft` 与 `mouthRight` 时生成 `bsdiff_mouth_lateral_abs = abs(mouthLeft - mouthRight)`。
- 20 阶段中 `bsdiff_mouth_abs` 与 `bsdiff_mouth_lateral_abs` 数值表现一致，均表达口部横向/侧向 blendshape 左右差。

数据表现：

| role | 患病均值 | 不患病均值 | 差值 | sep_auc |
| --- | ---: | ---: | ---: | ---: |
| all | 0.011621 | 0.005490 | 0.006131 | 0.551084 |
| forehead_wrinkle | 0.012142 | 0.004044 | 0.008097 | 0.585096 |
| frown | 0.013583 | 0.006350 | 0.007233 | 0.594290 |

形成原因：

- 口部横向控制差异在多个非微笑 role 中也出现，说明它不只是“笑得不对称”，还可能反映静息或非目标动作下的口部偏斜。
- forehead_wrinkle、frown role 本来主要要求眉额动作，但口部差异仍然突出，可能来自患病组在用力表情时出现联带口部偏移，也可能来自非目标区域代偿动作。
- 该字段是 blendshape 层面的动作估计，受表情执行强度影响较大，需要和 `raw_lip_midline_deviation`、`raw_mouth_corner_vertical_asym` 这类几何点证据共同解释。

### `raw_lip_midline_deviation`

来源：

- 用 MediaPipe 点 168、1、152 拟合面部中线。
- 读取上唇中心 13、下唇中心 14。
- 计算 13/14 到中线 signed distance 的平均绝对偏移，并按左右外眼角距离归一化。

数据表现：

| role | 患病均值 | 不患病均值 | 差值 | sep_auc |
| --- | ---: | ---: | ---: | ---: |
| all | 0.008622 | 0.006793 | 0.001830 | 0.548580 |
| forehead_wrinkle | 0.008546 | 0.006029 | 0.002517 | 0.586536 |
| frown | 0.008254 | 0.005855 | 0.002399 | 0.581646 |

形成原因：

- 唇中心偏离中线是口部不对称最直观的几何证据之一。它不依赖 blendshape 分类，而是直接由 478 点坐标计算。
- 在 forehead_wrinkle 和 frown 中权重高，说明即使目标动作不是微笑，患病组也更容易表现出口唇中心偏移。
- 该特征在 V1.1 模型权重中排名最高，原因是它在 train split 的多个动态 role 中满足 `患病均值 > 不患病均值`，且 AUC 与效应量相对稳定。

### `raw_mouth_corner_vertical_asym`

来源：

- 读取左口角 291、右口角 61。
- 计算 `abs(y_291 - y_61) / scale`。
- `scale` 是左右外眼角 263/33 的 3D 距离，用于降低拍摄距离和人脸大小影响。

数据表现：

| role | 患病均值 | 不患病均值 | 差值 | sep_auc |
| --- | ---: | ---: | ---: | ---: |
| all | 0.030388 | 0.026289 | 0.004099 | 0.548207 |
| eyes_closed | 0.030496 | 0.025243 | 0.005253 | 0.579945 |
| frown | 0.028723 | 0.024090 | 0.004633 | 0.572555 |

形成原因：

- 口角高低差直接对应“嘴角一侧更低或更高”的可观察不对称。
- eyes_closed role 中该项靠前，说明闭眼动作时口部静态偏斜仍被保留，不完全依赖微笑动作。
- HB Grade I-VI 差异中它也是 top 特征，Grade I 均值 0.012217，Grade VI 均值 0.055840，差值 0.043623，说明代理等级越高，口角垂直差越明显。

### `raw_all_mesh_region_point_spread_asym`

来源：

- 读取 0..477 全部 raw landmarks。
- 用 168/1/152 中线将全脸点云切成左右两侧。
- 分别计算左右点云围绕各自质心的平均 3D 离散度 `spread`。
- 输出 `abs(left_spread - right_spread) / (abs(left_spread) + abs(right_spread))`。

数据表现：

| role | 患病均值 | 不患病均值 | 差值 | sep_auc |
| --- | ---: | ---: | ---: | ---: |
| all | 0.021195 | 0.018560 | 0.002636 | 0.551960 |
| eyes_closed | 0.025024 | 0.020804 | 0.004219 | 0.571216 |
| forehead_wrinkle | 0.020907 | 0.017346 | 0.003561 | 0.582353 |

形成原因：

- 该项不是单个点差，而是全脸左右半边整体“紧散程度”的差异。嘴、眼、眉、轮廓多个局部偏移会共同推高这个指标。
- 患病组在口部、眼部、眉额、轮廓 y 质心等区域同时偏高时，全脸点云 spread 差也会随之变大。
- 它对局部噪声不如单点特征敏感，但也更容易混入整体表情用力方式、脸部遮挡和残余姿态差异，因此更适合作为整体佐证，而不是唯一主证据。

## 不患病更高的反向证据

### `bsdiff_mouthSmile_abs`

来源：

- 从 MediaPipe blendshape 读取 `mouthSmileLeft` 与 `mouthSmileRight`。
- 计算 `abs(mouthSmileLeft - mouthSmileRight)`。

数据表现：

| role | 患病均值 | 不患病均值 | 差值 | sep_auc |
| --- | ---: | ---: | ---: | ---: |
| all | 0.015365 | 0.019295 | -0.003930 | 0.560892 |
| smile | 0.023513 | 0.033542 | -0.010029 | 0.601410 |
| forehead_wrinkle | 0.007630 | 0.010863 | -0.003232 | 0.599922 |
| frown | 0.010632 | 0.015514 | -0.004882 | 0.591082 |

形成原因：

- 该项在 `smile` 中最突出，但方向是“不患病更高”。这不等于不患病组人脸更异常，更可能说明不患病组能做出更强、更充分的笑容动作；当整体 `mouthSmile` 激活更强时，左右两个 smile 系数之间的绝对差也更容易被放大。
- 患病组可能存在动作幅度下降或运动缺失，导致 `mouthSmileLeft/Right` 两侧都偏低，绝对差反而不如能充分微笑的不患病组大。
- 因此 `bsdiff_mouthSmile_abs` 在当前流程中应被解释为“微笑动作执行强度与左右激活差的混合指标”。它适合作为反向证据或质量/动作强度提示，不适合作为患病高风险的正向主证据。
- 在 forehead_wrinkle、frown 这类非微笑 role 中仍出现不患病更高，提示非目标口部动作、表情习惯或 role 执行差异会影响 blendshape 统计。

## 模型权重最高特征为什么集中在这些项

V1.1 模型不是直接把 20 阶段 top 表照搬进预测，而是在 train split 上重新筛选候选特征：

1. 只考虑 `raw_*` 中包含 `asym/deviation` 的几何特征，以及 `bsdiff_*` 左右差特征。
2. 硬屏蔽 `matrix_*`、`pose_*`、yaw/pitch/roll、scale/distance/bbox/translation、`*_centroid_z_asym`。
3. 只保留 `患病均值 > 不患病均值` 的特征。
4. 要求 train AUC 达到阈值，并按 `(AUC - 0.5) * effect_size` 形成特征权重。
5. 按 role 分别建模，再聚合到患者级。

因此模型权重最高的特征具有两个共同点：一是方向必须是患病更高，二是要在特定 role 中稳定区分。

| rank | role | feature | 患病均值 | 不患病均值 | AUC | weight | 解释 |
| ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | forehead_wrinkle | `raw_lip_midline_deviation` | 0.008572 | 0.005905 | 0.598864 | 0.037482 | 非口部目标动作中仍存在唇中线偏移，说明口部偏斜具有跨 role 稳定性 |
| 2 | frown | `raw_lip_midline_deviation` | 0.008279 | 0.005488 | 0.595019 | 0.036963 | 皱眉/用力动作下口唇中线偏移稳定 |
| 3 | forehead_wrinkle | `raw_eyebrow_region_height_asym` | 0.078962 | 0.058993 | 0.598063 | 0.035727 | 眉额动作是面神经相关动态区域，患病组眉区高度不对称更明显 |
| 4 | frown | `raw_face_oval_region_centroid_y_asym` | 0.050253 | 0.037238 | 0.595570 | 0.034782 | 轮廓 y 质心差体现整体面部垂直不对称 |
| 5 | teeth | `bsdiff_mouthFrown_abs` | 0.006120 | 0.002703 | 0.618148 | 0.034613 | 示齿动作下口角下拉/口部下垂左右差明显 |

这里的关键点是：模型权重代表“当前训练集上可用于区分患病标签的弱监督证据强度”，不是单项临床重要性排序。`raw_lip_midline_deviation` 排在前面，是因为它同时具备几何可解释性、跨 role 稳定性和正向区分；`raw_eyebrow_region_height_asym` 与 `raw_face_oval_region_centroid_y_asym` 补充了眉额和整体轮廓证据，减少模型只依赖口部特征。

## HB Grade I-VI 差异为什么最大集中在 y 质心和口角

HB proxy grade 是工程代理等级，不是人工 HB 真值。它由以下组件加权得到：

| 组件 | 权重 |
| --- | ---: |
| `resting_symmetry_score` | 0.18 |
| `eye_closure_score` | 0.16 |
| `brow_forehead_score` | 0.18 |
| `smile_mouth_score` | 0.24 |
| `gross_asymmetry_score` | 0.16 |
| `movement_absence_score` | 0.08 |

这些组件来自 V1.1 role-aware 分数、动态表达强度和整体不对称分数。随后根据 train/val 分布阈值映射到 Grade I-VI。因此 HB Grade I-VI 差异最大的特征，天然会集中在能推动这些组件升高的几何不对称项上。

| rank | feature | Grade I 均值 | Grade VI 均值 | I->VI 差值 | corr | 最大跳变 |
| ---: | --- | ---: | ---: | ---: | ---: | --- |
| 1 | `raw_face_oval_region_centroid_y_asym` | 0.019335 | 0.096004 | 0.076669 | 0.723493 | Grade V->VI |
| 2 | `raw_iris_region_centroid_y_asym` | 0.012608 | 0.065256 | 0.052647 | 0.716602 | Grade IV->V |
| 3 | `raw_lip_region_centroid_y_asym` | 0.006799 | 0.032272 | 0.025473 | 0.722267 | Grade V->VI |
| 4 | `raw_eye_region_centroid_y_asym` | 0.012568 | 0.065387 | 0.052819 | 0.716808 | Grade IV->V |
| 5 | `raw_mouth_corner_vertical_asym` | 0.012217 | 0.055840 | 0.043623 | 0.707116 | Grade V->VI |

形成原因：

- `centroid_y_asym` 类特征表达左右区域在垂直方向上的质心差。面部下垂、眼裂高低差、眉额抬升不对称、口唇偏斜都会把对应区域的 y 质心拉开。
- Grade VI 代表代理分数最高的一组，通常同时具有静息不对称、动态不对称和整体不对称，因此 face oval、iris、eye、lip、mouth corner 这些跨区域 y 方向指标会同步变大。
- 最大跳变集中在 Grade IV->V 或 Grade V->VI，说明当前代理等级的高端区间主要由“明显整体/动态不对称”拉开。
- 这组统计不是独立验证，因为 grade 本身由相关特征和组件生成。它更适合说明“当前代理等级内部的证据结构是否符合人脸不对称直觉”，而不是证明 HB grade 的临床准确性。

## 新建规则测试集验证结果

已使用新建的脑卒中预警 App 规则测试集复测上述主证据特征：

```text
datasets/stroke_warning_app_rule_test_set_20260508
```

运行入口：

```bash
scripts/run_in_project_env.sh python scripts/validate_mediapipe_evidence_on_rule_test_set.py
```

输出产物：

```text
datasets/stroke_warning_app_rule_test_set_20260508/metadata/40_mediapipe_evidence_keypoints.csv
datasets/stroke_warning_app_rule_test_set_20260508/metadata/40_mediapipe_evidence_image_features.csv
datasets/stroke_warning_app_rule_test_set_20260508/metadata/40_mediapipe_evidence_patient_features.csv
datasets/stroke_warning_app_rule_test_set_20260508/metadata/40_mediapipe_evidence_feature_validation.csv
datasets/stroke_warning_app_rule_test_set_20260508/metadata/40_mediapipe_evidence_validation_summary.json
datasets/stroke_warning_app_rule_test_set_20260508/reports/40_mediapipe_evidence_feature_validation.md
```

验证口径：

- 测试集患者数 101，其中 `患病` 42、`不患病` 59。
- 本次只评估 App 中可对应人脸的图片 role：`front_contour`、`smile_teeth`、`eyes_right`。
- 入选图片 327 张，MediaPipe detected 325 张，`no_face` 2 张。
- 主判断采用患者级 `all` role 的 `max` 聚合，避免把同一患者多张图当作独立样本。
- 本轮按“图片中患病者更高”的 5 个主证据复测：`bsdiff_mouthFrown_abs`、`raw_all_mesh_region_point_spread_asym`、`bsdiff_mouth_abs`、`raw_lip_midline_deviation`、`raw_mouth_corner_vertical_asym`。
- 有效标准为方向符合 `患病均值 > 不患病均值`，且 AUC 高于随机区分；AUC 达到 0.55 以上记为 `supported`，0.60 以上记为 `strong_supported`。

主判断结果：

| feature | status | 患病均值 | 不患病均值 | 差值 | AUC |
| --- | --- | ---: | ---: | ---: | ---: |
| `raw_all_mesh_region_point_spread_asym` | weak_supported | 0.016698 | 0.015881 | 0.000817 | 0.514124 |
| `raw_lip_midline_deviation` | supported | 0.011438 | 0.010652 | 0.000785 | 0.583939 |
| `bsdiff_mouthFrown_abs` | not_supported | 0.005742 | 0.006816 | -0.001073 | 0.546207 |
| `bsdiff_mouth_abs` | not_supported | 0.014226 | 0.014348 | -0.000122 | 0.627119 |
| `raw_mouth_corner_vertical_asym` | not_supported | 0.031150 | 0.031161 | -0.000011 | 0.539548 |

结论：

1. 在新建规则测试集上，患者级 `all + max` 主判断支持 2/5 个主证据，支持率为 0.400。
2. `raw_lip_midline_deviation` 满足有效方向，且 AUC 为 0.583939，是本轮 5 个特征中最稳定的正向证据。
3. `raw_all_mesh_region_point_spread_asym` 满足患病均值更高，但 AUC 只有 0.514124，只能作为弱支持的辅助证据。
4. `bsdiff_mouthFrown_abs`、`bsdiff_mouth_abs`、`raw_mouth_corner_vertical_asym` 在患者级 `all + max` 主判断下未满足有效方向，即非患者均值不低于患者均值，因此不能作为当前这批新数据上的全局有效指标。
5. 按 role 看，`front_contour` 中 `bsdiff_mouthFrown_abs`、`bsdiff_mouth_abs`、`raw_lip_midline_deviation` 有正向支持；`smile_teeth` 中 5 个特征全部为患病均值更高，其中 `raw_lip_midline_deviation` 达到 `strong_supported`；`eyes_right` 只支持 `raw_all_mesh_region_point_spread_asym` 和 `raw_mouth_corner_vertical_asym`。这说明这 5 个特征更适合做 role-specific 验证，不适合直接用 all-role max 混合成统一主指标。

因此，当前指标的有效性结论应写为：在这批新数据上，`raw_lip_midline_deviation` 可作为全局正向主证据，`raw_all_mesh_region_point_spread_asym` 可作为弱辅助证据；口部 blendshape 和口角垂直差需要按 `front_contour`、`smile_teeth`、`eyes_right` 分 role 使用，不能直接宣称患者整体更高、非患者整体更低。

## 核心对称阈值与归因输出

在上述 5 个“患病更高”的核心特征确定后，新增统一阈值与归因分析：

```bash
scripts/run_in_project_env.sh python scripts/build_core_symmetry_threshold_and_attribution.py
```

输出产物：

```text
datasets/core_symmetry_threshold_attribution_20260529/metadata/50_core_symmetry_patient_scores.csv
datasets/core_symmetry_threshold_attribution_20260529/metadata/50_core_symmetry_patient_face_asymmetry_outputs.csv
datasets/core_symmetry_threshold_attribution_20260529/metadata/50_core_symmetry_feature_reference_stats.csv
datasets/core_symmetry_threshold_attribution_20260529/metadata/50_core_symmetry_threshold_sweep.csv
datasets/core_symmetry_threshold_attribution_20260529/metadata/50_core_symmetry_supporting_feature_analysis.csv
datasets/core_symmetry_threshold_attribution_20260529/metadata/50_core_symmetry_high_asymmetry_attributions.csv
datasets/core_symmetry_threshold_attribution_20260529/metadata/50_core_symmetry_threshold_summary.json
datasets/core_symmetry_threshold_attribution_20260529/reports/50_core_symmetry_threshold_and_attribution.md
```

阈值计算口径：

- 旧数据使用 `smile/teeth` 合并为 `smile_or_teeth`；新数据使用 `smile_teeth`。
- 每个核心特征先做患者级 role 内 `max` 聚合。
- 每个数据集分别建立不患病和患病两套稳健参考分布。
- 只保留 `患病中位数 > 不患病中位数` 的稳健特征；默认方向为患病者更高。旧数据 5/5 保留，新数据 4/5 保留，`raw_mouth_corner_vertical_asym` 在新数据中位数方向不满足，因此不参与新数据核心插值评分。
- 单特征插值为 `(患者特征值 - 不患病中位数) / (患病中位数 - 不患病中位数)`；`0` 近似不患病稳健中心，`1` 近似患病稳健中心，高于 `1` 表示超过患病稳健中心。
- 单特征插值贡献截断到 `[0, 6.0]`；`core_asymmetry_score` 为活跃稳健特征的插值贡献均值。
- 当前阈值为 `core_asymmetry_score >= 2.500922`，输出 `人脸不对称性较高`。阈值选择先要求两批数据合并 specificity `>= 0.75`，再最大化 Youden J。
- 患者级判断输出字段为 `face_asymmetry_output`，取值为 `人脸不对称` 或 `未见明显人脸不对称`；`face_asymmetry_reason` 输出分数、阈值、活跃核心特征和主要归因。这里的 `患病` 标签只作为默认人脸不对称代理阳性来选择阈值。

当前弱监督结果：

| scope | n | TP | FP | TN | FN | precision | recall | specificity | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| combined | 604 | 142 | 56 | 170 | 236 | 0.717172 | 0.375661 | 0.752212 | 0.493056 |
| old_20260119 | 504 | 126 | 39 | 129 | 210 | 0.763636 | 0.375000 | 0.767857 | 0.502994 |
| new_20260508 | 100 | 16 | 17 | 41 | 26 | 0.484848 | 0.380952 | 0.706897 | 0.426667 |

归因规则：

- 高不对称样本固定输出活跃核心特征作为主归因：`bsdiff_mouthFrown_abs`、`raw_all_mesh_region_point_spread_asym`、`bsdiff_mouth_abs`、`raw_lip_midline_deviation`，以及在旧数据中活跃的 `raw_mouth_corner_vertical_asym`。
- 每个归因项输出特征值、不患病参考值、患病参考值、插值位置、贡献分和触发该特征最大值的 role/sample。
- 额外支撑归因只使用绝对不对称或偏移类字段：`bsdiff_*` 绝对差、`raw_*asym`、`raw_*deviation`；排除 `*_signed_left_minus_right` 这类方向性字段。
- 支撑归因要求高不对称组均值更高且 `AUC >= 0.60`，用于解释“为何高不对称”，不作为独立诊断规则。

该阈值仍然是基于 patient outcome 标签的弱监督阈值，不是人工面部不对称标签或临床 HB 标签校准阈值。它可以作为下一版报告中的辅助不对称风险提示和归因入口，但不能描述为医学诊断结论。

## 当前推荐规则：62 稳定性加权特征患病判断

从 61、62、63 三组规则的结果看，当前默认推荐采用 62 阶段规则。原因不是 62 的 recall 最高，而是它在当前两批数据上同时保持了更高 precision 和 specificity，尤其对新数据的不患病误判控制最好，更适合作为“高置信患病倾向/面部不对称风险提示”的默认规则。

62 阶段入口：

```bash
scripts/run_in_project_env.sh python scripts/build_stable_weighted_feature_disease_rule.py
```

主报告：

```text
datasets/combined_disease_feature_candidates_20260529/reports/62_stable_weighted_feature_disease_rule.md
```

核心产物：

```text
datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_feature_weights.csv
datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_score_threshold.csv
datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_patient_predictions.csv
datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_patient_feature_contributions.csv
datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_metrics.csv
```

### 62 阶段如何得到

1. 数据来源

   - 旧数据：`datasets/facesym_v1_all_images_no_gate_20260119/metadata/09_mediapipe_full_features.csv`
   - 新数据：`datasets/stroke_warning_app_rule_test_set_20260508/metadata/40_mediapipe_evidence_image_features.csv`
   - 两批数据都只使用 MediaPipe `detected` 且具备 `label_binary` 的图片。

2. 继承 60 阶段去重后的 21 个推荐特征

   60 阶段先在旧/新两批数据的共同 MediaPipe 特征上做筛选：

   - 排除 `matrix_*`、`pose_*`、yaw/pitch/roll、距离、尺度、开口宽度、signed 方向字段等采集条件或姿态字段。
   - 只保留几何不对称和左右 blendshape 差异类字段。
   - 按患者级聚合后，要求旧数据和新数据方向一致，且方向均为 `patient_higher`。
   - 在 `all`、`mouth_dynamic`、`front_like` 等 role scope 和 `max/mean/median` 聚合中筛选。
   - 最终得到 21 个去重推荐特征，作为 62 阶段的输入。

3. 单特征阈值

   对每个特征，62 沿用 60 阶段选出的 role scope 和聚合方式，构造患者级特征值。因为这 21 个特征均为 `patient_higher`，所以单特征触发规则统一为：

   ```text
   feature_value >= feature_threshold
   ```

   单特征阈值搜索方法：

   - 遍历该特征在旧+新全部患者上的患者级取值作为候选阈值。
   - 每个候选阈值计算 TP、FP、TN、FN、precision、recall、specificity、F1、balanced accuracy、Youden J。
   - 优先选择 Youden J 最大的阈值；并列时依次比较 balanced accuracy、F1、precision、specificity。
   - 选中阈值后，同时记录 old/new/combined 的 specificity 和不患病误判率。

4. 特征稳定性和权重

   62 不是简单统计“患者中高不高”，而是同时看非患者中是否也容易高、特征在所有图片中是否波动大、以及该特征在旧/新数据中是否都具备区分能力。

   每个特征的权重来自以下部分：

   ```text
   raw_weight =
     0.30 * 跨数据AUC稳定分
   + 0.20 * 合并AUC分
   + 0.25 * 非患者specificity分
   + 0.15 * 图片波动稳定分
   + 0.10 * 图片数分
   ```

   其中：

   - 跨数据 AUC 稳定分使用 old/new directional AUC 的较小值，避免某个特征只在单一数据集有效。
   - 非患者 specificity 分来自 old/new/combined specificity 的较小值，非患者越少过阈值，权重越高。
   - 图片波动稳定分在对应 role scope 的全部图片上计算 IQR、robust CV、IQR/患者中位数差距；波动越大，权重越低。
   - 图片数分使用图片数量的 log 因子，样本覆盖更多的特征获得小幅加权。
   - 所有 raw weight 最后归一化，使 21 个特征权重总和为 1。

5. 患者级加权得分

   对单个患者，逐一检查 21 个特征是否达到各自阈值。触发的特征贡献其归一化权重，未触发或缺失的特征贡献 0：

   ```text
   weighted_disease_score = sum(feature_weight_i for triggered feature_i)
   ```

   该分数越高，表示越多稳定的、患者更高且非患者较少触发的证据同时出现。

6. 最终加权分阈值

   在旧+新全部患者的 `weighted_disease_score` 上搜索最终阈值：

   - 遍历全部患者加权得分作为候选阈值。
   - 优先最大化 Youden J。
   - 并列时依次比较 balanced accuracy、F1、precision、specificity 和更高阈值。
   - 当前选中阈值为：

   ```text
   weighted_disease_score >= 0.612826
   ```

   达到该阈值时输出：

   ```text
   患病倾向较高
   ```

   未达到阈值时输出：

   ```text
   未达到患病阈值
   ```

### 62 阶段当前特征权重

| rank | feature | role | aggregation | threshold | weight | grade |
| ---: | --- | --- | --- | ---: | ---: | --- |
| 1 | `bsdiff_mouth_abs` | `mouth_dynamic` | max | 0.003855 | 0.057616 | high |
| 2 | `bsdiff_mouth_lateral_abs` | `mouth_dynamic` | max | 0.003855 | 0.057616 | high |
| 3 | `bsdiff_browDown_abs` | `all` | max | 0.013388 | 0.054691 | medium |
| 4 | `raw_lip_midline_deviation` | `mouth_dynamic` | max | 0.008995 | 0.054497 | medium |
| 5 | `raw_iris_region_point_spread_asym` | `mouth_dynamic` | max | 0.009759 | 0.051983 | medium |
| 6 | `bsdiff_mouthFrown_abs` | `mouth_dynamic` | median | 0.000216 | 0.051817 | medium |
| 7 | `raw_face_oval_region_height_asym` | `all` | max | 0.017991 | 0.051482 | medium |
| 8 | `raw_all_mesh_region_height_asym` | `all` | max | 0.017991 | 0.051269 | medium |
| 9 | `raw_iris_region_area_asym` | `mouth_dynamic` | max | 0.019940 | 0.047742 | medium |
| 10 | `raw_eyebrow_region_height_asym` | `all` | median | 0.036786 | 0.047351 | medium |

完整 21 个特征、阈值、权重、非患者误判率和图片波动分见：

```text
datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_feature_weights.csv
```

### 62、63 和 61 的指标取舍

| rule | 规则口径 | combined precision | combined recall | combined specificity | new precision | new recall | new specificity |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 61 | 前 10 特征，至少 5 个触发 | 0.736181 | 0.775132 | 0.537445 | 0.648649 | 0.571429 | 0.779661 |
| 62 | 21 特征稳定性加权，合并 Youden 阈值 | 0.777385 | 0.582011 | 0.722467 | 0.692308 | 0.214286 | 0.932203 |
| 63 | role-specific + 非患者 P85 + bootstrap 稳定性 | 0.719626 | 0.611111 | 0.603524 | 0.653846 | 0.404762 | 0.847458 |

因此当前判断为：

- 如果目标是尽可能提高召回，61 或 63 会更敏感，但不患病误判会更多。
- 如果目标是作为默认规则输出高置信的 `患病倾向较高`，当前应采用 62。
- 62 在 combined precision、combined specificity 和 new specificity 上都是三者中最高；new 数据不患病误判为 4/59，明显低于 63 的 9/59。
- 62 的主要代价是 new recall 较低，即它会漏掉一部分患病样本；因此 62 应解释为“高置信阳性规则”，不是“尽可能发现所有患病者”的筛查规则。

### 62 阶段规范输入

62 阶段以患者为输入单位，不是单张图片直接给最终结论。规范输入应满足：

- 同一患者的一组静态人脸图片。
- 必需 role：`smile_teeth`，或旧 V1 兼容格式的 `smile + teeth`。
- 推荐 role：`front_contour/front + smile_teeth/smile,teeth + eyes_right`。
- 图片格式：`.jpg`、`.jpeg`、`.png`。
- 排除：视频、舌像、病历图、辅助检查图。
- 单图要求：清晰单人脸，正向或接近正向，嘴部、眉眼区域无遮挡，光照足够。
- MediaPipe 必须能输出 `478` 个 raw landmarks、`52` 个 blendshapes、至少 1 个 facial transformation matrix。
- 推理字段至少包含 `patient_sample_id`、`media_role`、`image_path`；训练/验证时额外需要 `label_binary` 或 `label_group`。

### 62 阶段解释边界

62 使用的是 patient outcome 弱标签拟合，不是人工面部不对称真值，也不是临床诊断标签。它可以作为当前系统的默认技术规则，用于输出高置信的患病倾向和特征归因；但不能描述为临床诊断结论，也不能替代人工复核或独立冻结测试集验证。

## 当前数据集上形成这些差异的总体原因

1. 患病组在口部相关几何和 blendshape 左右差上更高，说明当前 patient outcome 标签与口部不对称存在弱关联。最稳定的证据是唇中线偏移、口角高低差、口部 frown/lateral blendshape 左右差。
2. 患病组在全脸点云、脸轮廓、眼/虹膜、眉额区域 y 方向不对称上也偏高，说明差异不只存在于嘴部，而是会扩展到整体垂直不对称和动态表情区域。
3. 不患病组 `bsdiff_mouthSmile_abs` 更高，主要反映微笑动作强度和左右 smile 激活差的混合效应。它是当前流程中需要谨慎解释的反向证据。
4. V1.1 模型权重偏向 `raw_lip_midline_deviation`、`raw_eyebrow_region_height_asym`、`raw_face_oval_region_centroid_y_asym`、`bsdiff_mouthFrown_abs`，因为它们在 train split 中方向为患病更高，并且在对应 role 上有相对稳定的 AUC 与效应量。
5. HB Grade I-VI 差异集中在 `centroid_y_asym` 和 `raw_mouth_corner_vertical_asym`，是因为代理 grade 的高端区间主要由整体不对称、眼闭合/眼区差异、眉额动态、微笑口部动态共同推高。

## 使用建议

- 对外解释时，优先用几何点证据：`raw_lip_midline_deviation`、`raw_mouth_corner_vertical_asym`、`raw_face_oval_region_centroid_y_asym`、`raw_eye/iris_region_centroid_y_asym`。这些字段更容易映射到可视化点位。
- `bsdiff_mouthFrown_abs`、`bsdiff_mouth_abs` 可作为口部动态左右差证据，但需要说明它们来自模型估计的 blendshape，不是人工标注动作幅度。
- `bsdiff_mouthSmile_abs` 应标记为反向证据或动作强度提示，不能作为患病更高的主证据。
- HB Grade I-VI 差异用于解释代理等级的内部证据结构；最终仍需要人工人脸不对称标签或人工 HB 标签做校准验证。
