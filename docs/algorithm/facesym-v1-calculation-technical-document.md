# FaceSymAi V1 静态图片人脸对称性计算技术文档

版本日期：2026-05-21

本文档整理当前 FaceSymAi V1 的实际计算过程。范围包括 MediaPipe Face Landmarker 检测输出、坐标标准化、静态几何特征、五类部件级对称性属性、总体对称性评分、患者级 baseline 聚合、阈值选择和本轮 `test precision = 0.662338` 的计算来源。

当前结果是基于 patient outcome 标签（`患病`/`不患病`）的技术信号检查，不是医学诊断性能，也不是直接面部不对称 ground truth 的验证结果。

## 1. 当前运行基线

| 项目 | 当前值 |
| --- | --- |
| 源数据集 | `datasets/stroke_patient_outcome_by_name_20260119` |
| V1 输出目录 | `datasets/facesym_v1_by_name_20260119` |
| 图片角色 | `front, smile, teeth` |
| 检测器 | MediaPipe Tasks `Face Landmarker` |
| 模型文件 | `models/mediapipe/face_landmarker.task` |
| Python 环境 | conda env `anti-spoofing_scc_175` |
| 主流程脚本 | `scripts/build_facesym_v1_dataset_from_by_name.py` |
| 当前测试 | `25 passed` |

运行命令：

```bash
scripts/run_in_project_env.sh python scripts/build_facesym_v1_dataset_from_by_name.py \
  --output datasets/facesym_v1_by_name_20260119 \
  --roles front,smile,teeth
```

## 2. 数据流程与产物

当前推荐流程按患者维度组织，所有阶段均输出 metadata 和 report：

| 阶段 | 目标 | 主要产物 |
| --- | --- | --- |
| `01_manifest` | 筛选 V1 静态图片 | `metadata/01_manifest.csv`, `reports/01_manifest.md` |
| `02_quality_gate` | 图像质量门控和隔离 | `metadata/02_quality_gate.csv`, `metadata/02_quarantined_images.csv`, `reports/02_quality_gate.md` |
| `03_keypoints` | MediaPipe 检测与特征点绘制 | `keypoints/.../*.json`, `annotated/.../*.jpg`, `reports/03_keypoints.md` |
| `04_features` | 图片级和患者级对称性特征 | `metadata/04_image_features.csv`, `metadata/04_patient_features.csv`, `reports/04_features.md` |
| `05_patient_splits` | 患者级 train/val/test 切分 | `metadata/05_patient_splits.csv`, `reports/05_patient_splits.md` |
| `06_baseline_evaluation` | 当前规则 baseline 评估 | `metadata/06_baseline_predictions.csv`, `metadata/06_baseline_evaluation.json`, `reports/06_baseline_evaluation.md` |

本轮正式处理规模：

| 指标 | 数值 |
| --- | ---: |
| 患者数 | 505 |
| 图片数 | 1546 |
| 患病患者 | 336 |
| 不患病患者 | 169 |
| `front` 图片 | 516 |
| `smile` 图片 | 513 |
| `teeth` 图片 | 517 |
| 质量门控 `pass` | 938 |
| 质量门控 `review` | 15 |
| 质量门控 `reject` | 593 |
| MediaPipe `detected` | 1538 |
| MediaPipe `no_face` | 7 |
| MediaPipe `failed` | 1 |
| 已绘制 landmark 图片 | 1538 |
| 可生成特征图片 | 1538 |

## 3. MediaPipe 输出与语义点映射

MediaPipe Face Landmarker 对每张图片输出：

- `raw_landmarks`：当前成功样本为 478 个归一化关键点。
- `blendshapes`：当前成功样本为 52 个表情 blendshape 分数。
- `facial_transformation_matrixes`：当前样本为 1 或 2 个矩阵。
- `landmarks`：FaceSymAi 从 raw landmarks 中抽取 V1 语义关键点。
- `pose`：当前 adapter 基于左右外眼角估计 roll，yaw/pitch 当前记为 0.0；matrix 保留用于后续增强。

当前 V1 语义点映射：

| FaceSymAi 语义点 | MediaPipe index |
| --- | ---: |
| `nose_bridge` | 168 |
| `nose_tip` | 1 |
| `chin` | 152 |
| `left_eye_outer` | 263 |
| `left_eye_inner` | 362 |
| `left_eye_upper` | 386 |
| `left_eye_lower` | 374 |
| `right_eye_outer` | 33 |
| `right_eye_inner` | 133 |
| `right_eye_upper` | 159 |
| `right_eye_lower` | 145 |
| `left_brow_inner` | 336 |
| `left_brow_outer` | 276 |
| `right_brow_inner` | 107 |
| `right_brow_outer` | 46 |
| `left_mouth_corner` | 291 |
| `right_mouth_corner` | 61 |
| `upper_lip_center` | 13 |
| `lower_lip_center` | 14 |
| `left_nostril` | 327 |
| `right_nostril` | 98 |
| `left_cheek` | 454 |
| `right_cheek` | 234 |
| `left_jaw` | 365 |
| `right_jaw` | 136 |

坐标使用 MediaPipe 归一化图像坐标，`x` 和 `y` 通常位于 `[0, 1]`。图像坐标中 `y` 向下增大。

## 4. 坐标标准化

V1 特征计算前先做几何标准化，目标是消除拍摄距离、图片尺寸、平移和轻微 roll 差异，使左右几何特征可比较。

### 4.1 中线拟合

输入关键点记为二维点：

```text
p_i = (x_i, y_i)
```

当前用于拟合鼻面中线的点集为：

```text
P_mid = {nose_bridge, nose_tip, chin}
```

若可用点数小于 2，或拟合退化，则使用 `nose_bridge -> chin` 直线作为中线。正常情况下使用主方向拟合：

```text
mu_x = (1 / N) * sum_i x_i
mu_y = (1 / N) * sum_i y_i

s_xx = sum_i (x_i - mu_x)^2
s_yy = sum_i (y_i - mu_y)^2
s_xy = sum_i (x_i - mu_x) * (y_i - mu_y)

theta = 0.5 * atan2(2 * s_xy, s_xx - s_yy)
u = (cos(theta), sin(theta))
```

其中 `u` 是拟合中线方向向量。为保证方向从脸部上方指向下方，使用 `nose_bridge -> chin` 方向校正：

```text
if dot(u, chin - nose_bridge) < 0:
    u = -u
```

中线原点：

```text
o = (mu_x, mu_y)
```

单位法向量：

```text
n = (-u_y, u_x)
```

中线表达式：

```text
M(t) = o + t * u
```

### 4.2 点到中线的纵向坐标、横向距离与镜像

任意点 `p` 相对中线的纵向坐标：

```text
along(p, M) = dot(p - o, u)
```

任意点 `p` 到中线的有符号横向距离：

```text
dist_signed(p, M) = dot(p - o, n)
```

点 `p` 关于中线的镜像点：

```text
reflect(p, M) = p - 2 * dist_signed(p, M) * n
```

### 4.3 尺度归一化

当前尺度使用左右外眼角距离：

```text
s = ||left_eye_outer - right_eye_outer||_2
```

如果 `s <= 1e-9`，认为人脸尺度退化，特征计算失败。

### 4.4 标准化坐标

每个原始语义点 `p` 转成标准化坐标 `p' = (x', y')`：

```text
x' = dist_signed(p, M) / s
y' = along(p, M) / s
```

标准化后：

- 鼻面中线被拉直到 `x' = 0`。
- 脸部纵轴沿 `y'` 方向。
- 左右横向距离已经按双眼外角距离归一。
- 轻微 roll 通过投影到中线坐标系被消除。

后续所有特征都在标准化坐标系中计算，因此公式里不再额外除以原始尺度。代码中返回的标准化 `scale = 1.0`。

当前 V1 尚未做完整 3D yaw/pitch 校正。yaw/pitch/大 roll 主要通过质量惩罚降低可信度。

## 5. 输入质量分

输入质量分 `q` 来自关键点平均置信度和姿态惩罚：

```text
q = clamp(avg_confidence - pose_penalty, 0, 1)
```

当前 MediaPipe Face Landmarker adapter 将 raw landmark confidence 记为 `1.0`，语义点继承该值。因此现阶段 `avg_confidence` 通常为 1.0，`q` 的主要扣分来自姿态惩罚。外部质量门控作为并行字段 `quality_level/quality_accepted` 输出，当前不直接进入 `q` 公式。

姿态惩罚：

```text
pose_penalty = yaw_penalty + pitch_penalty + roll_penalty

yaw_penalty   = min((abs(yaw)   - 15) / 30, 0.35), if abs(yaw)   > 15 else 0
pitch_penalty = min((abs(pitch) - 15) / 35, 0.25), if abs(pitch) > 15 else 0
roll_penalty  = min((abs(roll)  - 20) / 40, 0.25), if abs(roll)  > 20 else 0
```

当 `q < 0.45` 时，结果会附加低可信 warning。

## 6. 特征严重度函数

每个原始特征值 `v_k` 先映射为 `[0, 1]` 严重度 `severity_k`：

```text
severity_k = clamp((v_k - low_k) / (high_k - low_k), 0, 1)
```

其中 `low_k` 表示开始计入异常的软阈值，`high_k` 表示达到满严重度的阈值。

当前阈值：

| 特征 | low | high |
| --- | ---: | ---: |
| `global_mirror_error` | 0.025 | 0.120 |
| `midline_deviation` | 0.015 | 0.080 |
| `mouth_corner_vertical_asymmetry` | 0.015 | 0.090 |
| `mouth_width_asymmetry` | 0.025 | 0.120 |
| `lip_midline_deviation` | 0.015 | 0.080 |
| `eye_aperture_asymmetry` | 0.080 | 0.400 |
| `eye_corner_height_asymmetry` | 0.015 | 0.080 |
| `brow_vertical_asymmetry` | 0.020 | 0.100 |
| `brow_outer_vertical_asymmetry` | 0.020 | 0.100 |
| `contour_mirror_error` | 0.025 | 0.140 |
| `jaw_width_asymmetry` | 0.025 | 0.140 |

## 7. 特征计算公式

以下公式均在标准化坐标中计算。记：

```text
x(p) = p 的标准化横向坐标
y(p) = p 的标准化纵向坐标
d(a, b) = sqrt((x(a) - x(b))^2 + (y(a) - y(b))^2)
eps = 1e-9
```

对于标准化中线 `x = 0`，点 `p = (x, y)` 的中线镜像点为：

```text
mirror(p) = (-x, y)
```

### 7.1 全局镜像误差

镜像点对：

```text
P_global = {
  (left_eye_outer, right_eye_outer),
  (left_eye_inner, right_eye_inner),
  (left_brow_inner, right_brow_inner),
  (left_brow_outer, right_brow_outer),
  (left_mouth_corner, right_mouth_corner),
  (left_nostril, right_nostril),
  (left_cheek, right_cheek),
  (left_jaw, right_jaw)
}
```

单个点对镜像误差：

```text
e_pair(L, R) = d(L, mirror(R))
             = sqrt((x(L) + x(R))^2 + (y(L) - y(R))^2)
```

全局镜像误差：

```text
global_mirror_error = mean_{(L,R) in P_global} e_pair(L, R)
```

该特征没有单侧输出，主要用于总体对称性聚合。

### 7.2 鼻面中线偏移

中线结构点：

```text
P_center = {nose_tip, upper_lip_center, lower_lip_center}
```

公式：

```text
midline_deviation = mean_{p in P_center} abs(x(p))
```

该特征没有单侧输出。

### 7.3 口部：嘴角上下不对称

左右口角：

```text
L = left_mouth_corner
R = right_mouth_corner
```

公式：

```text
signed = y(L) - y(R)
mouth_corner_vertical_asymmetry = abs(signed)
```

单侧规则：

```text
if signed > 0: side = left_lower
if signed < 0: side = right_lower
```

由于 `y` 沿脸部上方向下方增大，`signed > 0` 表示左口角更靠下。

### 7.4 口部：左右口角宽度不对称

左右口角到中线的横向距离：

```text
w_L = abs(x(left_mouth_corner))
w_R = abs(x(right_mouth_corner))
signed = w_L - w_R
mouth_width_asymmetry = abs(signed)
```

单侧规则：

```text
if signed < 0: side = left_narrower
if signed > 0: side = right_narrower
```

### 7.5 口部：唇中线偏移

上下唇中点：

```text
P_lip = {upper_lip_center, lower_lip_center}
```

公式：

```text
signed = mean_{p in P_lip} x(p)
lip_midline_deviation = abs(signed)
```

单侧规则：

```text
if signed > 0: side = left_shift
if signed < 0: side = right_shift
```

### 7.6 眼部：眼裂开合不对称

左右眼裂高度：

```text
open_L = d(left_eye_upper, left_eye_lower)
open_R = d(right_eye_upper, right_eye_lower)
```

公式：

```text
signed = (open_L - open_R) / max(open_L, open_R, eps)
eye_aperture_asymmetry = abs(signed)
```

单侧规则：

```text
if signed < 0: side = left_smaller
if signed > 0: side = right_smaller
```

### 7.7 眼部：外眼角高度不对称

```text
signed = y(left_eye_outer) - y(right_eye_outer)
eye_corner_height_asymmetry = abs(signed)
```

单侧规则：

```text
if signed > 0: side = left_lower
if signed < 0: side = right_lower
```

### 7.8 眉部：眉头高度不对称

```text
signed = y(left_brow_inner) - y(right_brow_inner)
brow_vertical_asymmetry = abs(signed)
```

单侧规则：

```text
if signed > 0: side = left_lower
if signed < 0: side = right_lower
```

### 7.9 眉部：眉尾高度不对称

```text
signed = y(left_brow_outer) - y(right_brow_outer)
brow_outer_vertical_asymmetry = abs(signed)
```

单侧规则：

```text
if signed > 0: side = left_lower
if signed < 0: side = right_lower
```

### 7.10 面部轮廓：脸颊和下颌镜像误差

轮廓点对：

```text
P_contour = {
  (left_cheek, right_cheek),
  (left_jaw, right_jaw)
}
```

公式：

```text
contour_mirror_error = mean_{(L,R) in P_contour} d(L, mirror(R))
```

单侧使用轮廓宽度差均值：

```text
signed = mean_{(L,R) in P_contour} (abs(x(L)) - abs(x(R)))

if signed < 0: side = left_narrower
if signed > 0: side = right_narrower
```

### 7.11 面部轮廓：下颌宽度不对称

```text
w_L = abs(x(left_jaw))
w_R = abs(x(right_jaw))
signed = w_L - w_R
jaw_width_asymmetry = abs(signed)
```

单侧规则：

```text
if signed < 0: side = left_narrower
if signed > 0: side = right_narrower
```

## 8. 五类部件级对称性属性

V1 输出五类部件：

```text
mouth, eye, brow, midline, contour
```

每个部件的异常分 `component_score_c` 由该部件下可用特征严重度加权得到：

```text
component_score_c =
  sum_{k in available(c)} weight_{c,k} * severity_k
  / sum_{k in available(c)} weight_{c,k}
```

若该部件无可用特征，则 `component_score_c = 0`。

部件对称分：

```text
component_symmetry_score_c = 100 * (1 - clamp(component_score_c, 0, 1))
```

部件置信度：

```text
component_confidence_c =
  input_quality * available_feature_count_c / expected_feature_count_c
```

当前部件内特征权重：

| 部件 | 特征 | 权重 |
| --- | --- | ---: |
| mouth | `mouth_corner_vertical_asymmetry` | 0.45 |
| mouth | `mouth_width_asymmetry` | 0.30 |
| mouth | `lip_midline_deviation` | 0.25 |
| eye | `eye_aperture_asymmetry` | 0.70 |
| eye | `eye_corner_height_asymmetry` | 0.30 |
| brow | `brow_vertical_asymmetry` | 0.60 |
| brow | `brow_outer_vertical_asymmetry` | 0.40 |
| midline | `midline_deviation` | 0.75 |
| midline | `lip_midline_deviation` | 0.25 |
| contour | `contour_mirror_error` | 0.65 |
| contour | `jaw_width_asymmetry` | 0.35 |

部件侧别聚合：

```text
left_score_c  = sum severity_k for feature side starting with left_
right_score_c = sum severity_k for feature side starting with right_
```

侧别阈值：

```text
side_threshold = 0.08
```

侧别输出规则：

```text
if left_score >= 0.08 and right_score >= 0.08 and abs(left_score - right_score) < 0.08:
    side = bilateral
elif left_score - right_score >= 0.08:
    side = left
elif right_score - left_score >= 0.08:
    side = right
else:
    side = uncertain
```

## 9. 总体对称性评分

总体异常严重度由五类部件和全局镜像误差加权得到：

```text
overall_asymmetry_severity =
  0.30 * mouth_score
  + 0.20 * severity(global_mirror_error)
  + 0.18 * midline_score
  + 0.12 * eye_score
  + 0.10 * brow_score
  + 0.10 * contour_score
```

当前权重和为 1.00，因此无需再除以总权重。代码仍保留通用写法：

```text
overall_asymmetry_severity =
  clamp(sum(weight_i * severity_i) / sum(weight_i), 0, 1)
```

总体对称性评分：

```text
overall_symmetry_score = 100 * (1 - overall_asymmetry_severity)
```

总体置信度：

```text
overall_confidence = input_quality
```

总体疑似侧别按部件侧别和总体权重聚合：

```text
left_overall =
  sum component_weight_c * component_score_c
  for component c where component_side_c == left

right_overall =
  sum component_weight_c * component_score_c
  for component c where component_side_c == right
```

然后复用 `side_threshold = 0.08` 输出 `left/right/bilateral/uncertain`。

## 10. 预警辅助分

V1 当前使用可解释规则/权重 baseline，不是训练完成的临床概率模型。

原始 logit：

```text
logit = intercept + sum_k advisory_weight_k * severity_k
intercept = -2.2
```

sigmoid 分数：

```text
raw_score = sigmoid(logit) = 1 / (1 + exp(-logit))
```

预警辅助置信度：

```text
advisory_confidence = clamp(raw_score * input_quality, 0, 1)
```

当前 advisory feature 权重：

| 特征 | 权重 |
| --- | ---: |
| `global_mirror_error` | 1.5 |
| `midline_deviation` | 1.0 |
| `mouth_corner_vertical_asymmetry` | 2.4 |
| `mouth_width_asymmetry` | 1.4 |
| `lip_midline_deviation` | 1.2 |
| `eye_aperture_asymmetry` | 1.6 |
| `eye_corner_height_asymmetry` | 0.9 |
| `brow_vertical_asymmetry` | 1.2 |
| `brow_outer_vertical_asymmetry` | 0.8 |
| `contour_mirror_error` | 0.8 |
| `jaw_width_asymmetry` | 0.7 |

风险等级：

| 条件 | `risk_level` |
| --- | --- |
| `advisory_confidence >= 0.75` | `high` |
| `advisory_confidence >= 0.50` | `elevated` |
| `advisory_confidence >= 0.25` | `watch` |
| 其他 | `low` |

## 11. 图片级输出字段

图片级结果写入：

```text
datasets/facesym_v1_by_name_20260119/metadata/04_image_features.csv
```

核心字段：

| 字段 | 含义 |
| --- | --- |
| `overall_symmetry_score` | 总体对称性评分，0 到 100，越高越对称 |
| `overall_asymmetry_severity` | 总体异常严重度，0 到 1，越高越异常 |
| `affected_side` | 总体疑似异常侧 |
| `advisory_confidence` | 当前预警辅助置信度 |
| `raw_score` | sigmoid 后、质量修正前的规则分 |
| `risk_level` | `low/watch/elevated/high` |
| `input_quality` | 输入质量分 |
| `{component}_score` | 部件异常分，0 到 1 |
| `{component}_symmetry_score` | 部件对称分，0 到 100 |
| `{component}_side` | 部件疑似侧别 |
| `{component}_confidence` | 部件置信度 |
| `{feature}_value` | 特征原始值 |
| `{feature}_severity` | 特征严重度 |

五类部件字段前缀：

```text
mouth, eye, brow, midline, contour
```

11 个特征字段前缀：

```text
global_mirror_error
midline_deviation
mouth_corner_vertical_asymmetry
mouth_width_asymmetry
lip_midline_deviation
eye_aperture_asymmetry
eye_corner_height_asymmetry
brow_vertical_asymmetry
brow_outer_vertical_asymmetry
contour_mirror_error
jaw_width_asymmetry
```

## 12. 患者级聚合

患者级结果写入：

```text
datasets/facesym_v1_by_name_20260119/metadata/04_patient_features.csv
```

对每个患者 `p`，保留 `front/smile/teeth` 三个角色的图片级字段，字段名前加 role 前缀，例如：

```text
front_advisory_confidence
smile_advisory_confidence
teeth_advisory_confidence
front_mouth_score
smile_eye_score
teeth_contour_score
```

当前 baseline 的患者级分数使用三类图片中最高的预警辅助置信度：

```text
score_{p,r} = advisory_confidence of patient p and role r

v1_symmetry_score_p = max(
  front_advisory_confidence_p,
  smile_advisory_confidence_p,
  teeth_advisory_confidence_p
)
```

字段名 `v1_symmetry_score` 是历史命名；在当前 baseline evaluation 中它实际承载的是 `max_role_advisory_confidence`，不是 `overall_symmetry_score`。

如果患者三个角色均无可用 `advisory_confidence`，则该患者在 baseline evaluation 中标记为 `skipped`。

## 13. 训练/验证/测试切分

患者级切分写入：

```text
datasets/facesym_v1_by_name_20260119/metadata/05_patient_splits.csv
```

当前切分参数：

```text
seed = 20260520
train_ratio = 0.70
val_ratio = 0.15
test_ratio = 0.15
```

当前切分结果：

| split | 患者数 | 患病 | 不患病 |
| --- | ---: | ---: | ---: |
| train | 353 | 235 | 118 |
| val | 75 | 50 | 25 |
| test | 77 | 51 | 26 |

切分按患者维度完成，避免同一患者的不同图片同时出现在不同 split 中。

## 14. 阈值选择

baseline prediction 写入：

```text
datasets/facesym_v1_by_name_20260119/metadata/06_baseline_predictions.csv
```

当前阳性规则：

```text
predicted_positive_p = 1 if v1_symmetry_score_p >= threshold else 0
```

阈值只在 validation split 上选择。候选阈值为验证集中所有唯一的患者级 `v1_symmetry_score`：

```text
T = sorted(unique(v1_symmetry_score_p for p in val if score exists))
```

对每个候选阈值 `t`，计算验证集 metrics，并按以下排序选择最优阈值：

```text
primary objective: maximize F1
tie-break: maximize precision
```

即代码中的比较：

```text
if (f1, precision) > (best_f1, best_precision):
    best_threshold = t
```

本轮选出的阈值：

```text
threshold = 0.277158
threshold_source = validation split
```

## 15. Precision 与混淆矩阵计算

标签口径：

```text
label_binary = 1 代表 患病
label_binary = 0 代表 不患病
```

混淆矩阵定义：

| truth | pred | cell |
| ---: | ---: | --- |
| 1 | 1 | TP |
| 0 | 1 | FP |
| 0 | 0 | TN |
| 1 | 0 | FN |

指标公式：

```text
precision = TP / (TP + FP), if TP + FP > 0 else 0
recall = TP / (TP + FN), if TP + FN > 0 else 0
specificity = TN / (TN + FP), if TN + FP > 0 else 0
F1 = 2 * precision * recall / (precision + recall), if precision + recall > 0 else 0
```

本轮 evaluation 结果：

| split | patients | evaluated | skipped | TP | FP | TN | FN | precision | recall | specificity | F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| train | 353 | 352 | 1 | 232 | 116 | 1 | 3 | 0.666667 | 0.987234 | 0.008547 | 0.795883 |
| val | 75 | 75 | 0 | 50 | 24 | 1 | 0 | 0.675676 | 1.000000 | 0.040000 | 0.806452 |
| test | 77 | 77 | 0 | 51 | 26 | 0 | 0 | 0.662338 | 1.000000 | 0.000000 | 0.796875 |

本轮用户给出的 `test precision = 0.662338` 来自测试集：

```text
TP = 51
FP = 26

precision = TP / (TP + FP)
          = 51 / (51 + 26)
          = 51 / 77
          = 0.6623376623376623
          ~= 0.662338
```

同时：

```text
recall = 51 / (51 + 0) = 1.0
specificity = 0 / (0 + 26) = 0.0
F1 = 2 * 0.6623376623376623 * 1.0 / (0.6623376623376623 + 1.0)
   = 0.796875
```

需要特别注意：当前 test split 中 77 个患者全部被预测为阳性，因此 `TN = 0`、`FN = 0`。这说明当前规则 baseline 在 patient outcome 标签上没有有效排除阴性样本，`precision` 实际等于测试集阳性占比 `51 / 77`。该结果只能说明检测和计算链路可复现，不能证明模型有医学判别能力。

## 16. 当前结果解释边界

当前 V1 已完成：

- MediaPipe Face Landmarker 本地图片检测。
- 人脸 raw landmarks 与语义 landmarks 输出。
- 人脸特征点绘制，符合 Face Landmarker 输出结果的可视化核查要求。
- 坐标标准化：中线拟合、轻微 roll 校正、尺度归一化。
- 图片级总体对称性评分。
- 口部、眼部、眉部、鼻面中线、面部轮廓五类部件级属性。
- 患者级 role 聚合。
- train/val/test 患者级切分。
- baseline threshold、prediction detail、confusion matrix 和 precision 报告。

当前限制：

- patient outcome 标签不是直接人工面部不对称标签。
- 当前 baseline 使用规则权重，没有完成监督训练和概率校准。
- yaw/pitch 未做 3D 矫正，仅通过质量项处理。
- 当前 adapter 的 landmark confidence 为统一 `1.0`，区域关键点置信度还需要后续从更细粒度检测信号中增强。
- 当前测试集 precision 必须与数据集版本、阈值、阳性规则、样本级明细一起报告，不能单独作为医学性能指标引用。

## 17. 复现入口

完整流程：

```bash
scripts/run_in_project_env.sh python scripts/build_facesym_v1_dataset_from_by_name.py \
  --output datasets/facesym_v1_by_name_20260119 \
  --roles front,smile,teeth
```

单图 MediaPipe 检测与分析：

```bash
scripts/run_in_project_env.sh python scripts/detect_mediapipe_image.py \
  path/to/local-image.jpg \
  --output tmp/facesymai-mediapipe-result.json \
  --annotated-output tmp/mediapipe_annotated \
  --pretty \
  --include-analysis
```

注意：项目输出和临时文件默认写入项目内 `tmp/` 或正式数据集目录，不写入系统 `/tmp`。
