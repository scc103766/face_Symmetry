# FaceSymAi 人脸对称性判断算法详细技术文档

版本：0.1  
日期：2026-05-19  
状态：详细技术版  
对应汇报版：`docs/algorithm/facial-symmetry-technical-solution.md`

## 1. 文档目的

本文档用于指导 FaceSymAi V1 静态图片分析算法的工程实现、联调、评估和后续 V2 扩展。相比领导汇报版，本文档重点说明算法使用的技术核心、计算原理、模块作用、数据流、公式、输出解释和验收依据。

V1 目标：

- 使用 MediaPipe Face Landmarker 完成正脸图和露齿图的人脸关键点检测。
- 基于静态几何特征完成人脸总体对称性评分。
- 输出口部、眼部、眉部、鼻面中线、面部轮廓五类部件级对称性属性。
- 通过质量门控控制输入可用性和结果可信度。
- 通过 API 输出可解释结果。
- 在冻结测试集上计算可复核的 precision。

V2 扩展：

- 短视频动态运动特征。
- 动作时序建模。
- 深度融合模型。
- 多模态卒中预警辅助概率校准。

## 2. 任务边界

### 2.1 输入边界

V1 输入限定为两张静态图片：

| 输入 | 采集要求 | 主要作用 |
| --- | --- | --- |
| 正脸图 | 静息正脸、无遮挡、光照均匀 | 评估总体对称性、眼部、眉部、鼻面中线、面部轮廓 |
| 露齿图 | 正脸露齿或咧嘴，口角和唇部清晰 | 评估口部对称性、口角下垂、露齿口型不对称 |

V1 不处理：

- 多人脸图。
- 严重侧脸图。
- 口罩、墨镜、手部遮挡核心区域的图片。
- 视频时序特征。
- 闭眼、抬眉、鼓腮等动态动作。

### 2.2 输出边界

V1 输出为“视觉辅助分析”，不是临床诊断。

核心输出：

- `overall_symmetry_score`：总体对称性评分，0 到 100，越高越对称。
- `overall_asymmetry_severity`：总体不对称严重度，0 到 1，越高越异常。
- `affected_side`：疑似异常侧，`left`、`right`、`bilateral`、`uncertain`。
- `quality`：输入质量门控结果。
- `attributes`：五类部件属性。
- `stroke_warning_auxiliary`：卒中预警辅助信号。
- `top_contributions`：主要异常贡献项。
- `recommended_action`：复核建议。
- `disclaimer`：医疗边界声明。

## 3. 技术核心总览

V1 算法由 8 个核心模块组成。

| 模块 | 技术核心 | 原理 | 作用 |
| --- | --- | --- | --- |
| 输入管理 | 正脸图、露齿图成对输入 | 同一次采集的两张图减少设备和姿态差异 | 保证口部和整体特征可比较 |
| MediaPipe 检测 | Face Landmarker | 检测人脸网格关键点、blendshape 和变换矩阵 | 提供结构化人脸几何基础 |
| 质量门控 | 姿态、清晰度、光照、遮挡、关键点可信度 | 判断输入是否满足静态几何分析条件 | 防止低质量输入产生高可信结果 |
| 坐标标准化 | 姿态校正、尺度归一化、中线拟合 | 消除拍摄距离、尺寸、轻微旋转差异 | 让左右几何特征可比较 |
| 部件特征 | 口、眼、眉、中线、轮廓 | 用左右成对关键点和中线偏移计算不对称 | 形成可解释的人脸属性 |
| 评分聚合 | severity 归一化 + 加权求和 | 把不同量纲特征转成统一严重度 | 输出总体评分和异常贡献 |
| 预警辅助 | 规则/权重评分 + 质量降权 | 根据面部异常程度输出辅助信号 | 支持卒中预警系统解释 |
| 评估模块 | precision、TP、FP、混淆矩阵 | 冻结测试集上计算指标 | 支撑验收和迭代优化 |

## 4. MediaPipe 关键点检测

### 4.1 为什么 V1 使用 MediaPipe

V1 确定使用 MediaPipe Face Landmarker，原因如下：

- 官方任务支持图片、视频帧和实时流，V1 做图片，V2 可平滑扩展到视频。
- 官方输出包含 3D face landmarks、blendshape scores 和 facial transformation matrixes。
- 官方模型 bundle 包含人脸检测、face mesh 和 blendshape prediction，能覆盖 V1 所需的人脸几何点。
- 工程集成成本低，适合两个月内完成稳定 API。

参考：Google AI Edge MediaPipe Face Landmarker 官方文档说明该任务可处理静态图、视频帧和实时流，并输出完整 face mesh、blendshape 和 facial transformation matrixes。

### 4.2 MediaPipe 输出到 FaceSymAi 的标准化

MediaPipe 原始输出不能直接暴露给业务层，需要转换为 FaceSymAi 语义关键点。

标准结构：

```json
{
  "image_role": "frontal",
  "detector": "mediapipe_face_landmarker",
  "pose": {
    "yaw": 2.1,
    "pitch": -1.4,
    "roll": 0.7
  },
  "landmarks": {
    "left_eye_outer": {"x": 0.341, "y": 0.412, "z": -0.012, "confidence": 0.98},
    "right_eye_outer": {"x": 0.662, "y": 0.410, "z": -0.011, "confidence": 0.98},
    "left_mouth_corner": {"x": 0.392, "y": 0.676, "z": -0.021, "confidence": 0.97},
    "right_mouth_corner": {"x": 0.615, "y": 0.668, "z": -0.019, "confidence": 0.97}
  },
  "blendshapes": {
    "mouthSmileLeft": 0.23,
    "mouthSmileRight": 0.46
  }
}
```

### 4.3 语义关键点分组

| 分组 | 关键点 | 作用 |
| --- | --- | --- |
| 眼部 | 左右内眼角、外眼角、上眼睑、下眼睑、眼中心 | 眼裂、眼宽、眼角高度、眼部镜像误差 |
| 眉部 | 左右眉头、眉峰、眉尾、眉中心 | 眉部高度、眉眼距离、眉部镜像误差 |
| 口部 | 左右口角、上唇中点、下唇中点、上下唇边界 | 口角下垂、口型偏移、露齿口部不对称 |
| 鼻部 | 鼻梁、鼻尖、左右鼻翼 | 中线拟合、鼻翼对称性、鼻尖偏移 |
| 中线 | 鼻梁、鼻尖、上唇中点、下唇中点、下巴 | 建立面部主轴 |
| 轮廓 | 左右脸颊、左右下颌、下巴、脸部边界点 | 面部轮廓和下颌对称性 |

### 4.4 Detector Adapter 的作用

Detector Adapter 是隔离层，作用是让算法核心不依赖 MediaPipe 的原始编号和版本细节。

职责：

- 调用 MediaPipe。
- 处理无人脸、多人脸、低置信检测。
- 将 MediaPipe landmarks 映射到 FaceSymAi 语义关键点。
- 输出统一 schema。
- 记录 `detector_version`、`mapping_version`、`landmark_schema_version`。

这样 V2 即使接入其他检测器，也不需要重写特征层。

## 5. 质量门控

### 5.1 质量门控的作用

质量门控是 V1 算法的前置安全模块。它的核心作用不是“提高分数”，而是判断输入是否具备被分析的条件。

它解决的问题：

- 侧脸会造成伪不对称。
- 模糊会导致关键点漂移。
- 遮挡会导致口部、眼部、眉部特征失效。
- 露齿图不合格会导致口部评分没有意义。
- 多人脸会导致检测目标不稳定。

### 5.2 门控输入

```text
image
face_bbox
pose
landmarks
landmark_confidence
image_quality_metrics
image_role(frontal/teeth)
```

### 5.3 门控输出

```json
{
  "hard_reject": false,
  "quality_score": 0.86,
  "quality_level": "pass",
  "reasons": [],
  "subscores": {
    "face_count": 1.0,
    "face_size": 0.94,
    "pose": 0.91,
    "sharpness": 0.88,
    "illumination": 0.84,
    "occlusion": 0.93,
    "landmark_confidence": 0.89,
    "teeth_compliance": 0.81
  }
}
```

### 5.4 质量子项原理

| 子项 | 原理 | 作用 |
| --- | --- | --- |
| 人脸数量 | 检测结果中 face 数量必须为 1 | 排除无人脸和多人脸 |
| 人脸大小 | bbox 短边像素与阈值比较 | 过小人脸无法稳定定位关键点 |
| 姿态 | yaw/pitch/roll 与阈值比较 | 排除侧脸和大角度俯仰 |
| 清晰度 | Laplacian 方差或边缘清晰度 | 排除运动模糊和失焦 |
| 光照 | 灰度均值、过曝/欠曝比例、左右亮度差 | 排除强阴影和曝光异常 |
| 遮挡 | 核心区域关键点缺失、局部置信度下降 | 排除口罩、墨镜、手遮挡 |
| 关键点置信度 | 核心点 confidence 均值和最小值 | 判断特征可信度 |
| 露齿合规 | 口部开合、口角可见、唇边界完整 | 判断露齿图能否用于口部评分 |

### 5.5 门控策略

硬拒绝：

- 无人脸或多人脸。
- 人脸过小。
- 姿态超过 V1 可接受范围。
- 核心区域严重遮挡。
- 关键点大面积缺失。

软降权：

- 轻微模糊。
- 光照略不均。
- 局部关键点置信度偏低。
- 露齿图动作不充分但仍可看到口角。

综合质量分：

```text
quality_score = weighted_mean(subscores)
final_warning_score = raw_warning_score * quality_score
```

## 6. 坐标标准化与中线构建

### 6.1 为什么要标准化

原图坐标受拍摄距离、分辨率、头部旋转和轻微姿态影响。直接比较左右像素距离会把拍摄误差误判为面部不对称。

标准化目标：

- 把人脸旋转到近似水平。
- 用统一尺度表示距离。
- 建立左右比较的参考中线。
- 减少设备和分辨率差异。

### 6.2 尺度 S

建议 V1 使用双眼外角距离作为基础尺度：

```text
S = distance(left_eye_outer, right_eye_outer)
```

若眼角点低置信，可降级使用：

```text
S = face_bbox_width
```

所有距离特征都除以 `S`，得到无量纲特征，便于跨图片比较。

### 6.3 面部中线 M

中线用于判断左右对称和中轴偏移。

候选点：

- 鼻梁。
- 鼻尖。
- 上唇中点。
- 下唇中点。
- 下巴。

拟合方式：

```text
M = line_fit([nose_bridge, nose_tip, chin])
```

当前实现使用鼻梁、鼻尖、下巴作为稳定中线拟合点。上唇中点、下唇中点继续作为中线偏移特征输入，不参与默认拟合，避免口部牵拉被中线拟合吸收。

拟合得到中线后，将所有关键点转换到标准局部坐标：

```text
x_norm = signed_distance(point, M) / S
y_norm = project_along_midline(point, M) / S
```

该步骤同时完成轻微 roll 姿态校正、尺度归一化和中线对齐。后续口部、眼部、眉部、鼻面中线、轮廓特征均在标准坐标下计算。

若露齿图中唇中点因张口导致不稳定，正脸图中线权重更高；露齿图主要用于口部左右比较。

### 6.4 镜像反射

左右成对点比较时，将右侧点关于中线反射，再与左侧点计算距离。

```text
mirror_error_pair(k) = distance(left_k, reflect(right_k, M)) / S
```

这种方法比直接比较 x 坐标更稳健，因为它以个体面部中线作为参考。

## 7. V1 部件特征计算

### 7.1 严重度归一化

不同特征的物理范围不同，需要统一为 0 到 1 的 severity。

```text
severity(x; low, high) = clamp((x - low) / (high - low), 0, 1)
```

含义：

- `x <= low`：认为无明显异常，severity = 0。
- `x >= high`：认为异常明显，severity = 1。
- 中间线性过渡。

初始阈值来自经验和测试集统计，后续通过验证集校准。

### 7.2 总体镜像误差

作用：反映整张脸左右结构的整体不对称。

使用点：

- 眼角。
- 眉部。
- 口角。
- 鼻翼。
- 脸颊。
- 下颌。

公式：

```text
global_mirror_error =
  mean_k(distance(left_k, reflect(right_k, M)) / S)
```

输出：

- `global_mirror_error`
- `global_mirror_severity`
- `global_asymmetry_side`

### 7.3 口部对称性

作用：识别口角下垂、露齿口型不对称、唇中点偏移。该区域是 V1 最重要的卒中预警辅助特征。

正脸图特征：

```text
mouth_corner_vertical_asymmetry =
  abs(y_left_mouth_corner - y_right_mouth_corner) / S

lip_midline_deviation =
  abs(signed_distance(upper_lip_center, M)) / S
```

露齿图特征：

```text
mouth_width_left = distance(left_mouth_corner, M)
mouth_width_right = distance(right_mouth_corner, M)
mouth_width_asymmetry =
  abs(mouth_width_left - mouth_width_right) / S

teeth_mouth_corner_asymmetry =
  abs(y_left_mouth_corner_teeth - y_right_mouth_corner_teeth) / S
```

方向判断：

```text
mouth_side =
  left if left_corner_lower_or_less_extended
  right if right_corner_lower_or_less_extended
  uncertain otherwise
```

输出：

- `mouth_asymmetry_score`
- `mouth_corner_droop_side`
- `mouth_corner_vertical_asymmetry`
- `mouth_width_asymmetry`
- `lip_midline_deviation`

### 7.4 眼部对称性

作用：识别静态眼裂大小和眼角高度差异。V1 不做闭眼不全判断，闭眼动态放入 V2。

公式：

```text
eye_aperture_left = distance(left_eye_upper, left_eye_lower) / S
eye_aperture_right = distance(right_eye_upper, right_eye_lower) / S

eye_aperture_asymmetry =
  abs(eye_aperture_left - eye_aperture_right) /
  max(eye_aperture_left, eye_aperture_right, eps)

eye_corner_height_asymmetry =
  abs(y_left_eye_outer - y_right_eye_outer) / S
```

输出：

- `eye_asymmetry_score`
- `eye_aperture_asymmetry`
- `eye_corner_height_asymmetry`
- `eye_region_confidence`

### 7.5 眉部对称性

作用：识别静态眉部高度差异和额面部左右差异。V1 不做抬眉动态保留判断。

公式：

```text
brow_eye_distance_left =
  vertical_distance(left_brow_center, left_eye_center) / S
brow_eye_distance_right =
  vertical_distance(right_brow_center, right_eye_center) / S

brow_height_asymmetry =
  abs(brow_eye_distance_left - brow_eye_distance_right) /
  max(brow_eye_distance_left, brow_eye_distance_right, eps)
```

输出：

- `brow_asymmetry_score`
- `brow_height_asymmetry`
- `brow_tail_height_asymmetry`

### 7.6 鼻面中线对称性

作用：评估鼻尖、唇中点、下巴是否偏离面部主轴。它能解释口部牵拉、姿态偏差和面部中轴偏移。

公式：

```text
nose_tip_deviation =
  abs(signed_distance(nose_tip, M)) / S

upper_lip_center_deviation =
  abs(signed_distance(upper_lip_center, M)) / S

chin_deviation =
  abs(signed_distance(chin, M)) / S

midline_deviation =
  weighted_mean([
    nose_tip_deviation,
    upper_lip_center_deviation,
    lower_lip_center_deviation,
    chin_deviation
  ])
```

输出：

- `midline_asymmetry_score`
- `nose_tip_deviation`
- `lip_center_deviation`
- `chin_deviation`

### 7.7 面部轮廓对称性

作用：补充脸颊、下颌、下巴轮廓的左右差异，用于解释整体面部形态是否明显偏斜。

公式：

```text
contour_mirror_error =
  mean_k(distance(left_contour_k, reflect(right_contour_k, M)) / S)

jaw_width_asymmetry =
  abs(distance(left_jaw, M) - distance(right_jaw, M)) / S
```

输出：

- `contour_asymmetry_score`
- `cheek_asymmetry`
- `jaw_asymmetry`
- `contour_confidence`

轮廓容易受发型、姿态和脸部遮挡影响，V1 中权重低于口部和中线。

## 8. 评分与解释

### 8.1 部件级评分

每个部件先计算内部多个特征的 severity，再加权得到部件分。

示例：

```text
mouth_severity =
  0.40 * mouth_corner_vertical_severity
  + 0.25 * mouth_width_severity
  + 0.25 * lip_midline_severity
  + 0.10 * mouth_region_mirror_severity
```

### 8.2 总体评分

建议 V1 初始权重：

| 部件 | 权重 |
| --- | --- |
| 口部 | 0.30 |
| 总体镜像误差 | 0.20 |
| 鼻面中线 | 0.18 |
| 眼部 | 0.12 |
| 眉部 | 0.10 |
| 面部轮廓 | 0.10 |

公式：

```text
weighted_asymmetry =
  0.30 * mouth_severity
  + 0.20 * global_mirror_severity
  + 0.18 * midline_severity
  + 0.12 * eye_severity
  + 0.10 * brow_severity
  + 0.10 * contour_severity

overall_symmetry_score =
  100 * (1 - clamp(weighted_asymmetry, 0, 1))
```

### 8.3 异常侧聚合

每个方向性特征输出 signed severity。

```text
side_score = sum_i(region_weight_i * signed_severity_i * confidence_i)
```

判定：

- `side_score >= t_side`：左侧疑似异常。
- `side_score <= -t_side`：右侧疑似异常。
- `abs(side_score) < t_side`：方向不确定。
- 双侧指标同时异常：`bilateral`。

### 8.4 解释项生成

解释项不是自然语言模板堆叠，而是由贡献度排序生成。

```text
contribution_i = region_weight_i * severity_i * confidence_i
top_contributions = top_k(contribution_i)
```

示例：

```json
{
  "region": "mouth",
  "feature": "mouth_corner_vertical_asymmetry",
  "side": "left",
  "severity": 0.76,
  "explanation": "露齿图中左侧口角低于右侧，口部对称性下降。"
}
```

## 9. 卒中预警辅助信号

### 9.1 作用

该信号用于辅助卒中预警系统解释“为什么关注这次面部采集”。它不是临床诊断概率。

医学依据：

- CDC 将突发单侧面部无力列为卒中警示症状之一，BE-FAST 中 Face 项要求观察微笑时单侧脸是否下垂。
- NIHSS Facial Palsy 项使用面部运动对称性评价面瘫程度。
- House-Brackmann 可作为面神经功能分级参考。

### 9.2 V1 计算

```text
raw_warning_score = sigmoid(
  intercept
  + w_mouth * mouth_severity
  + w_midline * midline_severity
  + w_global * global_mirror_severity
  + w_eye * eye_severity
  + w_brow * brow_severity
  + w_contour * contour_severity
)

warning_score = raw_warning_score * quality_score
```

分层：

| 分数范围 | 等级 | 含义 |
| --- | --- | --- |
| `< 0.25` | `low` | 未见明显面部对称性异常 |
| `0.25 - 0.50` | `watch` | 存在轻度不对称，建议结合质量和历史基线 |
| `0.50 - 0.75` | `elevated` | 存在明显面部异常信号，建议复核 |
| `>= 0.75` | `high` | 面部异常信号强，建议结合 BE-FAST 和临床流程快速复核 |

## 10. API 设计

### 10.1 请求

```http
POST /v1/facial-symmetry/analyze-static
Content-Type: multipart/form-data

frontal_image=<file>
teeth_image=<file>
```

### 10.2 响应

```json
{
  "request_id": "req_001",
  "version": {
    "api": "v1",
    "model": "facesymai-static-v1",
    "detector": "mediapipe-face-landmarker",
    "feature_schema": "static-feature-v1",
    "quality_gate": "quality-v1"
  },
  "quality": {
    "quality_score": 0.88,
    "quality_level": "pass",
    "hard_reject": false,
    "reasons": []
  },
  "symmetry": {
    "overall_symmetry_score": 82.4,
    "overall_asymmetry_severity": 0.176,
    "affected_side": "left",
    "confidence": 0.81
  },
  "attributes": {
    "mouth": {"score": 0.76, "side": "left"},
    "eye": {"score": 0.18, "side": "uncertain"},
    "brow": {"score": 0.12, "side": "uncertain"},
    "midline": {"score": 0.31, "side": "left"},
    "contour": {"score": 0.22, "side": "left"}
  },
  "stroke_warning_auxiliary": {
    "warning_score": 0.63,
    "level": "elevated"
  },
  "top_contributions": [],
  "recommended_action": "建议结合 BE-FAST、言语、肢体、发病时间和病史信息复核。",
  "disclaimer": "本结果仅用于脑卒中/面瘫预警辅助，不替代临床诊断。"
}
```

## 11. 评估原理

V1 主验收指标为 precision。

```text
precision = TP / (TP + FP)
```

阳性预测规则必须在测试前固定。

示例：

```text
prediction_positive =
  stroke_warning_auxiliary.level in ["elevated", "high"]
```

报告必须包含：

- 测试集版本。
- 阈值版本。
- 模型/API 版本。
- TP、FP、TN、FN。
- precision。
- recall。
- confusion matrix。
- 样本级预测明细。

## 12. V2 预留接口

V1 设计时需要为 V2 保留字段：

```json
{
  "input_mode": "static_image_pair",
  "frames": [],
  "dynamic_features": null,
  "temporal_model": null,
  "fusion_model": null
}
```

V2 增强项：

- 视频帧序列输入。
- 微笑动态幅度。
- 闭眼不全。
- 抬眉动态。
- 鼓腮动作。
- 眨眼左右同步。
- 时间延迟和速度特征。
- TCN/GRU/Transformer。
- CNN/ViT ROI 分支。
- 多模态融合和概率校准。

## 13. 参考资料

- Google AI Edge, MediaPipe Face Landmarker: https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker
- Google AI Edge MediaPipe GitHub: https://github.com/google-ai-edge/mediapipe
- NCBI Bookshelf, House-Brackmann Facial Nerve Grading System: https://www.ncbi.nlm.nih.gov/sites/books/NBK482290/table/article-18195.table0/?report=objectonly
- NCBI Bookshelf, NIH Stroke Scale table: https://www.ncbi.nlm.nih.gov/books/NBK499997/table/article-23776.table0/
- CDC, Signs and Symptoms of Stroke: https://www.cdc.gov/stroke/signs-symptoms/
