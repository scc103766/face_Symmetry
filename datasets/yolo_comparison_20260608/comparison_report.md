# YOLO 患者级聚合与 FaceSymAi 规则62 对比报告

- 生成时间：2026-06-08T15:31:28
- YOLO 图片级输入：`datasets/yolo_comparison_20260608/yolo_per_image_predictions.csv`
- FaceSymAi 规则62 患者级输入：`datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_patient_predictions.csv`
- 患者切分：`datasets/facesym_v1_by_name_20260119/metadata/05_patient_splits.csv`
- 阳性标签：`patient_label == 患病`。
- YOLO `yolo_majority_stroke` 使用 `yolo_stroke_image_count / image_count >= 0.5`，分母包含任务 #01 输出中的全部图片行；YOLO 失败图片计入图片数但不会计入 stroke 检测。

## 数据概览

- YOLO 图片级记录：1546 张图片；患者级聚合：505 名患者。
- YOLO 图片级失败：3 张。
- FaceSymAi 规则62 旧 V1 患者级预测：504 名患者。
- 对比指标统一使用共同患者：504 名。
- 未进入规则62共同集合的 YOLO 患者：1 名（19）。
- YOLO 图片级标签与患者切分标签不一致：3 张；患者级指标统一按 `05_patient_splits.csv` 标签计算。
- YOLO 图片级 split 与患者切分 split 不一致：0 张。

### YOLO 全量患者标签分布


标签不一致影响患者：392。

| split | patients | 患病 | 不患病 |
| --- | --- | --- | --- |
| train | 353 | 235 | 118 |
| val | 75 | 50 | 25 |
| test | 77 | 51 | 26 |
| combined | 505 | 336 | 169 |

### 指标共同患者标签分布

| split | patients | 患病 | 不患病 |
| --- | --- | --- | --- |
| train | 352 | 235 | 117 |
| val | 75 | 50 | 25 |
| test | 77 | 51 | 26 |
| combined | 504 | 336 | 168 |

### 规则62交叉验证

脚本从 `62_stable_weighted_feature_disease_rule_patient_predictions.csv` 逐患者重新计算规则62指标；与既有 `62_stable_weighted_feature_disease_rule_metrics.csv` 的 `old` 行对照如下。

| metric | recomputed_old_common | existing_old |
| --- | --- | --- |
| precision | 0.781481 | 0.781481 |
| recall | 0.627976 | 0.627976 |
| specificity | 0.648810 | 0.648810 |
| f1 | 0.696370 | 0.696370 |
| tp | 211 | 211 |
| fp | 59 | 59 |
| tn | 109 | 109 |
| fn | 125 | 125 |

## YOLO 各聚合规则指标

| method | split | precision | recall | specificity | f1 | accuracy | TP | FP | TN | FN |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| yolo_any_stroke_eye | train | 0.646840 | 0.740426 | 0.188034 | 0.690476 | 0.556818 | 174 | 95 | 22 | 61 |
| yolo_any_stroke_eye | val | 0.654545 | 0.720000 | 0.240000 | 0.685714 | 0.560000 | 36 | 19 | 6 | 14 |
| yolo_any_stroke_eye | test | 0.640625 | 0.803922 | 0.115385 | 0.713043 | 0.571429 | 41 | 23 | 3 | 10 |
| yolo_any_stroke_eye | combined | 0.646907 | 0.747024 | 0.184524 | 0.693370 | 0.559524 | 251 | 137 | 31 | 85 |
| yolo_any_stroke_mouth | train | 0.658703 | 0.821277 | 0.145299 | 0.731061 | 0.596591 | 193 | 100 | 17 | 42 |
| yolo_any_stroke_mouth | val | 0.672131 | 0.820000 | 0.200000 | 0.738739 | 0.613333 | 41 | 20 | 5 | 9 |
| yolo_any_stroke_mouth | test | 0.681159 | 0.921569 | 0.153846 | 0.783333 | 0.662338 | 47 | 22 | 4 | 4 |
| yolo_any_stroke_mouth | combined | 0.664303 | 0.836310 | 0.154762 | 0.740448 | 0.609127 | 281 | 142 | 26 | 55 |
| yolo_any_stroke | train | 0.659574 | 0.923404 | 0.042735 | 0.769504 | 0.630682 | 217 | 112 | 5 | 18 |
| yolo_any_stroke | val | 0.652174 | 0.900000 | 0.040000 | 0.756303 | 0.613333 | 45 | 24 | 1 | 5 |
| yolo_any_stroke | test | 0.653333 | 0.960784 | 0.000000 | 0.777778 | 0.636364 | 49 | 26 | 0 | 2 |
| yolo_any_stroke | combined | 0.657505 | 0.925595 | 0.035714 | 0.768850 | 0.628968 | 311 | 162 | 6 | 25 |
| yolo_stroke_severe | train | 0.648069 | 0.642553 | 0.299145 | 0.645299 | 0.528409 | 151 | 82 | 35 | 84 |
| yolo_stroke_severe | val | 0.625000 | 0.600000 | 0.280000 | 0.612245 | 0.493333 | 30 | 18 | 7 | 20 |
| yolo_stroke_severe | test | 0.627451 | 0.627451 | 0.269231 | 0.627451 | 0.506494 | 32 | 19 | 7 | 19 |
| yolo_stroke_severe | combined | 0.641566 | 0.633929 | 0.291667 | 0.637725 | 0.519841 | 213 | 119 | 49 | 123 |
| yolo_majority_stroke | train | 0.657343 | 0.800000 | 0.162393 | 0.721689 | 0.588068 | 188 | 98 | 19 | 47 |
| yolo_majority_stroke | val | 0.661017 | 0.780000 | 0.200000 | 0.715596 | 0.586667 | 39 | 20 | 5 | 11 |
| yolo_majority_stroke | test | 0.661538 | 0.843137 | 0.153846 | 0.741379 | 0.610390 | 43 | 22 | 4 | 8 |
| yolo_majority_stroke | combined | 0.658537 | 0.803571 | 0.166667 | 0.723861 | 0.591270 | 270 | 140 | 28 | 66 |

## YOLO 最优规则 vs FaceSymAi 规则62

YOLO 展示最优规则按 test split 的 F1 选择；当前为 `yolo_any_stroke_mouth`。该选择只用于报告对比，不作为重新调参或部署阈值选择。

| method | split | precision | recall | specificity | f1 | accuracy | TP | FP | TN | FN |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| yolo_any_stroke_mouth | train | 0.658703 | 0.821277 | 0.145299 | 0.731061 | 0.596591 | 193 | 100 | 17 | 42 |
| yolo_any_stroke_mouth | val | 0.672131 | 0.820000 | 0.200000 | 0.738739 | 0.613333 | 41 | 20 | 5 | 9 |
| yolo_any_stroke_mouth | test | 0.681159 | 0.921569 | 0.153846 | 0.783333 | 0.662338 | 47 | 22 | 4 | 4 |
| yolo_any_stroke_mouth | combined | 0.664303 | 0.836310 | 0.154762 | 0.740448 | 0.609127 | 281 | 142 | 26 | 55 |
| facesymai_rule62 | train | 0.780220 | 0.604255 | 0.658120 | 0.681055 | 0.622159 | 142 | 40 | 77 | 93 |
| facesymai_rule62 | val | 0.785714 | 0.660000 | 0.640000 | 0.717391 | 0.653333 | 33 | 9 | 16 | 17 |
| facesymai_rule62 | test | 0.782609 | 0.705882 | 0.615385 | 0.742268 | 0.675325 | 36 | 10 | 16 | 15 |
| facesymai_rule62 | combined | 0.781481 | 0.627976 | 0.648810 | 0.696370 | 0.634921 | 211 | 59 | 109 | 125 |

## 初步分析

- test precision：FaceSymAi 规则62 更高（yolo_any_stroke_mouth=0.681159，facesymai_rule62=0.782609）。
- test recall：YOLO 更高（yolo_any_stroke_mouth=0.921569，facesymai_rule62=0.705882）。
- test specificity：FaceSymAi 规则62 更高（yolo_any_stroke_mouth=0.153846，facesymai_rule62=0.615385）。
- test f1：YOLO 更高（yolo_any_stroke_mouth=0.783333，facesymai_rule62=0.742268）。
- test accuracy：FaceSymAi 规则62 更高（yolo_any_stroke_mouth=0.662338，facesymai_rule62=0.675325）。

- YOLO 的 `any` 与 `majority` 类规则只要图片中出现 stroke 类检测就容易判阳性，覆盖面宽，通常换来更高 recall，但会把较多不患病患者推成阳性，specificity 和 precision 受影响。
- FaceSymAi 规则62 使用 21 个稳定性加权 MediaPipe 特征和固定加权阈值，阳性更保守，因此更偏向 precision/specificity；代价是 recall 较低。
- 本对比仍使用 patient outcome 弱标签，只能解释为技术信号对比，不能表述为临床诊断性能。
