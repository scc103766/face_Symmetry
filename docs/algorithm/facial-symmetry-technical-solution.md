# FaceSymAi 人脸对称性判断算法技术方案

版本：0.2  
日期：2026-05-19  
状态：领导汇报版  

## 1. 汇报结论

FaceSymAi 当前阶段建议采用“两阶段技术路线”：

- **V1：静态图片分析版本，两个月内完成。** 输入正脸图和露齿图，使用 MediaPipe 完成人脸关键点检测，输出人脸总体对称性评分，以及口部、眼部、眉部、鼻面中线、面部轮廓等器官部件的对称性属性分析。V1 重点完成可调用 API、可解释结果和测试集 precision 评估。
- **V2：视频动态与深度融合版本，V1 稳定后启动。** 引入短视频、动作时序特征、动态运动幅度、时间延迟、深度融合模型和多模态卒中预警模型，用于提升鲁棒性和临床解释能力。

V1 不做医学诊断，不承诺单靠人脸确诊脑卒中。系统输出为“面部对称性/面瘫相关属性/卒中预警辅助信号”，用于辅助筛查和解释。

## 2. 项目任务定义

从图片或短视频中提取面部对称性、面瘫相关属性和卒中预警辅助信号，并通过 API 输出可解释结果。

V1 的任务收敛为：

- 输入：正脸静息图、露齿图。
- 算法：MediaPipe 关键点检测 + 静态几何特征 + 质量门控 + 规则/权重评分。
- 输出：总体对称性评分、部件级对称性属性、疑似异常侧、质量结果、解释项、预警辅助分。
- 验收：在冻结测试集上输出准确、可复核的 `precision = TP / (TP + FP)`。

## 3. V1 与 V2 范围划分

| 维度 | V1 静态分析版本 | V2 动态融合版本 |
| --- | --- | --- |
| 周期 | 两个月内完成 | V1 验收后规划 |
| 输入 | 正脸图、露齿图 | 短视频、动作序列、多帧图像 |
| 关键点检测 | MediaPipe Face Landmarker | MediaPipe + 其他检测器对照 |
| 主要算法 | 静态几何对称性分析 | 动态运动特征、时序建模、深度融合 |
| 重点部位 | 口部、眼部、眉部、鼻面中线、面部轮廓 | 微笑、闭眼、抬眉、鼓腮、眨眼等动作过程 |
| 模型复杂度 | 规则/权重评分，可解释优先 | 关键点时序模型 + 图像模型 + 融合模型 |
| 输出目标 | 可解释 API 和测试集 precision | 更高鲁棒性、动态面瘫识别、校准概率 |
| 风险控制 | 质量门控、重采建议、非诊断声明 | 外部验证、模型校准、误差闭环 |

## 4. V1 技术架构

```text
正脸图 / 露齿图
  -> 输入质量门控
  -> MediaPipe Face Landmarker
  -> 关键点语义映射
  -> 姿态与尺度标准化
  -> 静态对称性特征提取
  -> 部件级评分
  -> 总体对称性评分
  -> 卒中预警辅助信号
  -> API 可解释输出
  -> 测试集 precision 评估
```

### 4.1 关键点检测方案

V1 关键点检测确定使用 **MediaPipe Face Landmarker**。

选择原因：

- 支持人脸 3D landmarks、面部变换矩阵和 blendshape 输出。
- 支持图片和视频场景，便于 V1 向 V2 演进。
- 工程接入成本低，适合两个月内完成 API 和测试集评估。
- 能覆盖口部、眼部、眉部、鼻部、脸颊、下颌等 V1 需要的核心区域。

V1 不再并行接入 InsightFace、OpenFace、Py-Feat 等检测器，避免两个月周期内分散研发资源。这些工具保留为 V2 或离线对照方案。

### 4.2 V1 输入要求

| 输入 | 要求 | 用途 |
| --- | --- | --- |
| 正脸图 | 静息正脸，无遮挡，光照均匀 | 总体对称性、眼部、眉部、鼻面中线、轮廓 |
| 露齿图 | 正脸露齿或咧嘴，口角清晰可见 | 口部对称性、口角下垂、露齿口型不对称 |

建议采集要求：

- 单人脸。
- 人脸框短边不低于 256 px，推荐不低于 384 px。
- `abs(yaw) <= 15`、`abs(pitch) <= 15`、`abs(roll) <= 15`。
- 口部、眼部、眉部、鼻翼、下巴无遮挡。
- 无严重模糊、过曝、欠曝和强阴影。
- 正脸图和露齿图应来自同一次采集，尽量保持设备、距离、光照一致。

## 5. 质量门控单元

质量门控是 V1 的安全边界。它决定图片是否可以进入评分流程，并防止低质量输入产生高可信结果。

### 5.1 门控职责

- 判断是否存在单一有效人脸。
- 判断姿态、清晰度、光照、遮挡是否满足分析条件。
- 判断 MediaPipe 关键点置信度和区域完整性。
- 对不可用输入直接返回重采建议。
- 对可用但质量一般的输入降低结果可信度。
- 在 API 中单独返回 `quality_score` 和 `quality_warnings`。

### 5.2 V1 门控项

| 门控项 | 判定方式 | 失败处理 |
| --- | --- | --- |
| 人脸数量 | MediaPipe 检测结果 | 无人脸/多人脸直接拒绝 |
| 人脸大小 | 人脸框短边像素 | 过小重采 |
| 头部姿态 | yaw/pitch/roll | 超出范围重采或低可信 |
| 清晰度 | Laplacian 方差或等价清晰度指标 | 模糊重采 |
| 光照 | 灰度均值、过曝/欠曝比例 | 严重异常重采 |
| 遮挡 | 核心区域关键点缺失或异常 | 口眼眉鼻被遮挡则拒绝 |
| 关键点稳定性 | 核心关键点置信度 | 低置信区域不参与评分 |
| 露齿合规 | 口部开合、牙齿/口型可见代理 | 不合规时口部露齿特征不可用 |

### 5.3 质量输出

```json
{
  "quality_score": 0.86,
  "quality_level": "pass",
  "hard_reject": false,
  "warnings": [],
  "subscores": {
    "pose": 0.91,
    "sharpness": 0.88,
    "illumination": 0.84,
    "occlusion": 0.93,
    "landmark_confidence": 0.89,
    "teeth_image_compliance": 0.81
  }
}
```

## 6. V1 特征层设计

V1 只做静态图片特征，不做视频动态运动和动作时序建模。特征计算基于 MediaPipe 关键点，经姿态校正和尺度归一化后完成。

基础定义：

```text
S = 双眼外角距离或标准化面宽
M = 鼻梁、鼻尖、唇中点、下巴拟合得到的面部中线
severity(x; low, high) = clamp((x - low) / (high - low), 0, 1)
```

当前实现中，标准化前置于全部静态几何特征：

```text
M = line_fit([nose_bridge, nose_tip, chin])
x_norm = signed_distance(point, M) / S
y_norm = project_along_midline(point, M) / S
```

该标准坐标系把鼻面中线对齐为纵轴，并用双眼外角距离消除尺寸差异。唇中点不参与默认中线拟合，而是作为鼻面中线偏移特征，避免口部牵拉被拟合过程抵消。

### 6.1 人脸总体对称性评分

目标：输出整张脸的总体对称程度。

计算思路：

```text
mirror_error_pair(k) = distance(left_k, reflect(right_k, M)) / S
global_mirror_error = mean(mirror_error_pair(k))
overall_symmetry_score = 100 * (1 - clamp(weighted_asymmetry, 0, 1))
```

左右成对点包括：

- 眼角。
- 眉头、眉尾。
- 口角。
- 鼻翼。
- 脸颊。
- 下颌轮廓。

输出：

- `overall_symmetry_score`：0 到 100，越高越对称。
- `overall_asymmetry_severity`：0 到 1，越高越异常。
- `top_asymmetric_regions`：贡献最大的异常部件。

### 6.2 口部对称性属性

输入：正脸图 + 露齿图。

核心特征：

- 左右口角高度差。
- 左右口角到中线距离差。
- 露齿图中左右口角外展差。
- 上下唇中点相对面部中线偏移。
- 口部区域镜像误差。

计算示例：

```text
mouth_corner_vertical_asymmetry =
  abs(y_left_mouth_corner - y_right_mouth_corner) / S

mouth_width_asymmetry =
  abs(distance(left_mouth_corner, M) -
      distance(right_mouth_corner, M)) / S

lip_midline_deviation =
  abs(signed_distance(upper_lip_center, M)) / S
```

输出：

- `mouth_asymmetry_score`
- `mouth_corner_droop_side`
- `lip_midline_deviation`
- `mouth_explanation`

口部是 V1 与脑卒中预警最相关的静态区域，权重建议高于眼部、眉部和轮廓。

### 6.3 眼部对称性属性

输入：正脸图。

核心特征：

- 左右眼裂高度差。
- 左右眼宽差。
- 左右眼角高度差。
- 左右眼部区域镜像误差。

计算示例：

```text
eye_aperture_left = distance(left_upper_eyelid, left_lower_eyelid) / S
eye_aperture_right = distance(right_upper_eyelid, right_lower_eyelid) / S

eye_aperture_asymmetry =
  abs(eye_aperture_left - eye_aperture_right) /
  max(eye_aperture_left, eye_aperture_right, eps)
```

输出：

- `eye_asymmetry_score`
- `eye_aperture_asymmetry`
- `eye_region_warning`

V1 不判断闭眼不全，闭眼动作留到 V2 视频动态版本。

### 6.4 眉部对称性属性

输入：正脸图。

核心特征：

- 左右眉头高度差。
- 左右眉尾高度差。
- 左右眉眼距离差。
- 眉部区域镜像误差。

计算示例：

```text
brow_eye_distance_left =
  vertical_distance(left_brow_center, left_eye_center) / S
brow_eye_distance_right =
  vertical_distance(right_brow_center, right_eye_center) / S

brow_asymmetry =
  abs(brow_eye_distance_left - brow_eye_distance_right) /
  max(brow_eye_distance_left, brow_eye_distance_right, eps)
```

输出：

- `brow_asymmetry_score`
- `brow_height_asymmetry`
- `brow_region_warning`

V1 只做静态眉部高度对称性；抬眉动态保留能力留到 V2。

### 6.5 鼻面中线对称性属性

输入：正脸图 + 露齿图。

核心特征：

- 鼻梁、鼻尖、唇中点、下巴拟合中线。
- 鼻尖相对中线偏移。
- 上唇中点相对中线偏移。
- 下唇中点相对中线偏移。
- 下巴相对中线偏移。

计算示例：

```text
midline_deviation =
  mean(abs(signed_distance(point_j, M)) / S)
```

输出：

- `midline_asymmetry_score`
- `nose_tip_deviation`
- `lip_center_deviation`
- `chin_deviation`

该区域主要用于解释脸部结构是否受姿态或表情牵拉影响。

### 6.6 面部轮廓对称性属性

输入：正脸图。

核心特征：

- 左右脸颊轮廓镜像误差。
- 左右下颌轮廓镜像误差。
- 左右脸宽差。
- 下巴偏移。

计算示例：

```text
contour_mirror_error =
  mean(distance(left_contour_k, reflect(right_contour_k, M)) / S)
```

输出：

- `contour_asymmetry_score`
- `jaw_asymmetry`
- `cheek_asymmetry`
- `contour_region_warning`

面部轮廓容易受发型、姿态、拍摄角度影响，V1 中权重应低于口部和鼻面中线。

## 7. V1 评分策略

V1 采用规则/权重评分，不引入深度训练模型作为主流程。

建议初始权重：

| 部件 | 权重 | 理由 |
| --- | --- | --- |
| 口部 | 0.30 | 与口角下垂、露齿不对称最相关 |
| 总体镜像误差 | 0.20 | 反映整脸左右偏差 |
| 鼻面中线 | 0.18 | 解释唇中点、鼻尖、下巴偏移 |
| 眼部 | 0.12 | 静态眼裂和眼角差异 |
| 眉部 | 0.10 | 静态额面部差异 |
| 面部轮廓 | 0.10 | 补充脸颊和下颌对称性 |

总体异常分：

```text
weighted_asymmetry =
  0.30 * mouth_severity
  + 0.20 * global_mirror_severity
  + 0.18 * midline_severity
  + 0.12 * eye_severity
  + 0.10 * brow_severity
  + 0.10 * contour_severity
```

总体对称性评分：

```text
overall_symmetry_score = 100 * (1 - clamp(weighted_asymmetry, 0, 1))
```

预警辅助分：

```text
warning_score = sigmoid(intercept + sum(weight_i * severity_i)) * quality_score
```

V1 的 `warning_score` 只作为卒中预警辅助信号，不作为诊断概率。最终是否升级为临床风险概率，需要 V2 标注数据、模型训练和校准支持。

## 8. V1 API 输出

```json
{
  "request_id": "req_001",
  "model_version": "facesymai-static-v1",
  "detector": {
    "name": "mediapipe_face_landmarker",
    "version": "pinned"
  },
  "quality": {
    "quality_score": 0.88,
    "quality_level": "pass",
    "warnings": []
  },
  "symmetry": {
    "overall_symmetry_score": 82.4,
    "overall_asymmetry_severity": 0.176,
    "affected_side": "left",
    "confidence": 0.81
  },
  "attributes": {
    "mouth": {
      "score": 0.76,
      "side": "left",
      "features": {
        "mouth_corner_vertical_asymmetry": 0.071,
        "lip_midline_deviation": 0.035
      }
    },
    "eye": {
      "score": 0.18,
      "side": "uncertain"
    },
    "brow": {
      "score": 0.12,
      "side": "uncertain"
    },
    "midline": {
      "score": 0.31,
      "side": "left"
    },
    "contour": {
      "score": 0.22,
      "side": "left"
    }
  },
  "stroke_warning_auxiliary": {
    "warning_score": 0.63,
    "level": "elevated",
    "medical_boundary": "auxiliary_warning_not_diagnosis"
  },
  "top_contributions": [
    {
      "region": "mouth",
      "feature": "mouth_corner_vertical_asymmetry",
      "explanation": "露齿图中左侧口角低于右侧，口部对称性下降。"
    }
  ],
  "recommended_action": "建议结合 BE-FAST、言语、肢体、发病时间和病史信息复核。",
  "disclaimer": "本结果仅用于脑卒中/面瘫预警辅助，不替代临床诊断。"
}
```

## 9. V1 验收指标

主验收指标：

```text
precision = TP / (TP + FP)
```

验收要求：

- 在冻结测试集上计算 precision。
- 测试前固定阈值和阳性规则，不能在测试集上调参。
- 报告 TP、FP、预测阳性数量、测试集总量、模型版本、阈值版本和测试集版本。
- 同时输出 recall、specificity、confusion matrix，防止只看 precision 掩盖漏检。

V1 测试集阳性定义建议：

- 若有卒中临床标签：以 `stroke_confirmed == true` 作为阳性标签。
- 若暂时没有卒中标签：以 `facial_palsy_or_asymmetry == true` 作为面瘫/对称性任务阳性标签。

## 10. V2 延展方向

V2 不纳入两个月 V1 交付范围，只做技术预研和接口预留。

V2 重点：

- 输入短视频，覆盖静息、露齿微笑、闭眼、抬眉、鼓腮、自然眨眼。
- 增加动态运动特征：幅度、速度、左右延迟、峰值时间、动作完成度。
- 增加动作时序模型：TCN、GRU、Transformer。
- 增加图像深度模型：CNN/ViT ROI 分支。
- 增加多模态融合：人脸视觉 + BE-FAST 问卷 + 言语/肢体信息 + 病史。
- 完成概率校准，把 V1 的辅助分升级为更可信的风险概率。

## 11. 风险与控制

| 风险 | 影响 | 控制措施 |
| --- | --- | --- |
| 静态图无法覆盖所有面瘫表现 | V1 召回可能不足 | 明确 V1 是静态筛查，V2 引入动态视频 |
| 姿态造成伪不对称 | 误报 | 姿态门控、正脸重采、尺度归一化 |
| 露齿图动作不标准 | 口部误判 | 增加露齿合规检查和重采提示 |
| 自然面部不对称 | precision 下降 | 测试集加入 hard negative，输出解释和低可信提示 |
| MediaPipe 个别场景关键点漂移 | 特征不稳定 | 核心区域置信度门控，低置信区域不评分 |
| 医疗表述风险 | 合规风险 | 全部输出使用“辅助预警”，不写“诊断” |

## 12. 开源和参考资料

V1 确定使用：

- MediaPipe Face Landmarker: https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker
- MediaPipe GitHub: https://github.com/google-ai-edge/mediapipe

V2 可选参考：

- InsightFace: https://github.com/deepinsight/insightface
- OpenFace: https://github.com/TadasBaltrusaitis/OpenFace
- Py-Feat: https://github.com/cosanlab/py-feat
- LibreFace: https://github.com/ihp-lab/LibreFace
- ONNX Runtime: https://github.com/microsoft/onnxruntime

医学分级参考：

- House-Brackmann Facial Nerve Grading System: https://www.ncbi.nlm.nih.gov/sites/books/NBK482290/table/article-18195.table0/?report=objectonly
- NIH Stroke Scale: https://www.ninds.nih.gov/health-information/stroke/assess-and-treat/nih-stroke-scale
