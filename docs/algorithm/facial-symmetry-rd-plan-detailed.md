# FaceSymAi 人脸对称性判断算法详细研发文档

版本：0.1  
日期：2026-05-19  
状态：详细研发版  
对应汇报版：`docs/algorithm/facial-symmetry-rd-plan.md`

## 1. 文档目的

本文档用于把 FaceSymAi V1 两个月研发计划拆解为可执行任务。相比领导汇报版，本文档重点说明每个研发模块的作用、实现内容、验收标准、测试方法、交付文件和 V2 预留边界。

V1 总目标：

- 两个月内交付静态图片分析 API。
- 支持正脸图和露齿图。
- 使用 MediaPipe Face Landmarker。
- 输出总体对称性评分和五类部件级属性。
- 在冻结测试集上输出可复核 precision。

## 2. 研发原则

### 2.1 范围控制原则

V1 必须聚焦静态图片分析，不把视频动态模型放入两个月主交付。

V1 做：

- 正脸图和露齿图。
- MediaPipe 关键点检测。
- 静态几何特征。
- 质量门控。
- 规则/权重评分。
- API 输出。
- 测试集 precision。

V1 不做：

- 视频动态动作分析。
- 动作时序模型。
- 深度融合模型。
- 临床诊断结论。
- 多检测器并行比较。

### 2.2 可解释优先原则

所有输出必须能追溯到具体特征。

示例：

```text
总体对称性下降
  -> 主要贡献：口部
  -> 具体特征：左侧口角低于右侧
  -> 输入来源：露齿图
  -> 质量状态：pass
```

### 2.3 可验收原则

每个阶段必须有明确交付和验收，不以“模型效果不错”作为验收描述。

核心验收：

```text
precision = TP / (TP + FP)
```

必须同时输出样本级明细，便于复核 TP 和 FP。

## 3. 两个月里程碑

| 周期 | 里程碑 | 目标 | 验收点 |
| --- | --- | --- | --- |
| 第 1 周 | M1 需求冻结 | 固定 V1/V2 边界、输入输出、precision 口径 | 文档确认、测试集字段确认 |
| 第 2 周 | M2 MediaPipe 接入 | 正脸图、露齿图关键点输出 | 标准 schema 可生成 |
| 第 3 周 | M3 质量门控 | 低质量输入可拒绝或降权 | 错误码和质量分可输出 |
| 第 4 周 | M4 核心特征 A | 总体、口部、中线特征可用 | 合成样本符合预期 |
| 第 5 周 | M5 核心特征 B | 眼部、眉部、轮廓、受累侧可用 | 部件级全量输出 |
| 第 6 周 | M6 API | 外部可调用 JSON API | API 契约测试通过 |
| 第 7 周 | M7 评估 | 冻结测试集 precision 报告 | TP/FP 可复核 |
| 第 8 周 | M8 验收 | 汇报演示和 V2 规划 | 验收报告完成 |

## 4. 第 1 周：需求冻结与数据盘点

### 4.1 目标

把 V1 范围固定为静态图片分析，确认输入、输出、测试集标签和验收指标。

### 4.2 任务

| 任务 | 内容 | 产出 |
| --- | --- | --- |
| V1 范围确认 | 明确只支持正脸图和露齿图 | V1 scope checklist |
| V2 后置确认 | 视频动态、时序模型、深度融合进入 V2 | V2 backlog |
| 输入字段确认 | 定义 frontal_image、teeth_image | API 请求草案 |
| 输出字段确认 | 定义 quality、symmetry、attributes、warning | API 响应草案 |
| 测试集字段确认 | 定义 sample_id、patient_id_hash、label 等 | dataset manifest 草案 |
| precision 口径确认 | 固定 TP/FP 和阳性规则 | 评估协议 |

### 4.3 测试集字段

```text
sample_id
patient_id_hash
frontal_image_path
teeth_image_path
label_positive
label_type
affected_side_label
quality_label
source
split
```

### 4.4 验收标准

- V1/V2 范围写入文档。
- 测试集 manifest 字段确认。
- precision 公式、阳性规则、阈值策略确认。
- 所有成员明确 V1 不包含视频动态模型。

## 5. 第 2 周：MediaPipe 接入

### 5.1 目标

将输入图片转换为 FaceSymAi 标准关键点结构。

### 5.2 模块设计

建议文件：

```text
src/facesymai/detectors/base.py
src/facesymai/detectors/mediapipe_adapter.py
src/facesymai/landmark_mapping.py
src/facesymai/schemas_detection.py
tests/test_mediapipe_adapter.py
```

### 5.3 核心接口

```python
class FaceDetector:
    def detect_image(self, image: ImageInput) -> DetectionResult:
        ...

class MediaPipeFaceLandmarkerAdapter(FaceDetector):
    def detect_image(self, image: ImageInput) -> DetectionResult:
        ...

def to_facesymai_landmarks(result: DetectionResult) -> FaceLandmarks:
    ...
```

### 5.4 输出 schema

```json
{
  "image_id": "sample_001_frontal",
  "image_role": "frontal",
  "detector_version": "mediapipe-face-landmarker-pinned",
  "mapping_version": "facesymai-mediapipe-map-v1",
  "pose": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
  "landmarks": {},
  "blendshapes": {}
}
```

### 5.5 验收标准

- 正脸图可输出眼、眉、鼻、口、轮廓语义点。
- 露齿图可输出口角、上唇中点、下唇中点、唇边界点。
- 无人脸、多人脸、低置信检测能返回错误码。
- adapter 不影响现有 `FaceLandmarks` JSON baseline。

## 6. 第 3 周：质量门控

### 6.1 目标

建立 V1 输入可信度判断，保证低质量图片不会产生高可信预警。

### 6.2 建议文件

```text
src/facesymai/quality.py
src/facesymai/quality_config.py
tests/test_quality_gate.py
docs/algorithm/quality-gate-spec.md
```

### 6.3 质量门控项

| 门控项 | 实现任务 | 验收方式 |
| --- | --- | --- |
| 人脸数量 | 检测 face count | 无人脸/多人脸返回 hard reject |
| 人脸大小 | bbox 短边阈值 | 小脸样本被拒绝 |
| 姿态 | yaw/pitch/roll 阈值 | 侧脸样本降权或拒绝 |
| 清晰度 | Laplacian 方差 | 模糊样本返回重采 |
| 光照 | 亮度均值和曝光比例 | 过曝/欠曝样本降权或拒绝 |
| 遮挡 | 核心区域关键点完整性 | 口眼眉遮挡拒绝 |
| 关键点置信度 | 区域置信度均值 | 低置信区域不评分 |
| 露齿合规 | 口部开合和口角可见性 | 不合格露齿图不启用口部露齿特征 |

### 6.4 验收标准

- 每个 hard reject 有明确错误码。
- API 返回 `quality_score`、`quality_level`、`hard_reject`、`reasons`。
- 质量分独立于对称性分数。
- 低质量输入不会输出高可信 `stroke_warning_auxiliary_score`。

## 7. 第 4 周：静态特征 V1-A

### 7.1 目标

完成总体对称性、口部、鼻面中线三类核心特征。

### 7.2 建议文件

```text
src/facesymai/features_static.py
src/facesymai/features_mouth.py
src/facesymai/features_midline.py
tests/test_static_features_core.py
```

### 7.3 核心特征

总体镜像误差：

```text
global_mirror_error = mean(distance(left_k, reflect(right_k, M)) / S)
```

口部：

```text
mouth_corner_vertical_asymmetry =
  abs(y_left_mouth_corner - y_right_mouth_corner) / S

mouth_width_asymmetry =
  abs(distance(left_mouth_corner, M) -
      distance(right_mouth_corner, M)) / S
```

鼻面中线：

```text
midline_deviation =
  mean(abs(signed_distance(midline_point_j, M)) / S)
```

### 7.4 验收样例

| 样例 | 期望 |
| --- | --- |
| 对称正脸 | overall_symmetry_score 高，severity 低 |
| 左口角下垂 | mouth_asymmetry 高，affected_side 为 left |
| 右口角下垂 | mouth_asymmetry 高，affected_side 为 right |
| 唇中点偏移 | midline_asymmetry 高 |

## 8. 第 5 周：静态特征 V1-B

### 8.1 目标

补齐眼部、眉部、面部轮廓特征，并完成总体评分和异常侧聚合。

### 8.2 建议文件

```text
src/facesymai/features_eye.py
src/facesymai/features_brow.py
src/facesymai/features_contour.py
src/facesymai/scoring.py
src/facesymai/side.py
tests/test_static_features_regions.py
tests/test_scoring.py
```

### 8.3 特征清单

眼部：

- 左右眼裂高度差。
- 左右眼宽差。
- 左右眼角高度差。
- 眼部镜像误差。

眉部：

- 左右眉头高度差。
- 左右眉尾高度差。
- 左右眉眼距离差。
- 眉部镜像误差。

轮廓：

- 左右脸颊镜像误差。
- 左右下颌镜像误差。
- 下巴偏移。

### 8.4 评分聚合

```text
weighted_asymmetry =
  0.30 * mouth
  + 0.20 * global
  + 0.18 * midline
  + 0.12 * eye
  + 0.10 * brow
  + 0.10 * contour
```

### 8.5 验收标准

- 五类部件均可单独输出 `score`、`side`、`features`、`confidence`。
- 总体评分可由部件分复算。
- `top_contributions` 能按贡献排序。
- 缺失低置信区域时可降级，不导致整体崩溃。

## 9. 第 6 周：API 与报告输出

### 9.1 目标

提供外部系统可调用的静态图片分析 API。

### 9.2 建议文件

```text
src/facesymai/pipeline.py
src/facesymai/api/app.py
src/facesymai/api/schemas.py
src/facesymai/api/errors.py
docs/api/facial-symmetry-api.md
tests/test_api_contract.py
```

### 9.3 API 路由

```text
POST /v1/facial-symmetry/analyze-static
GET /v1/facial-symmetry/health
GET /v1/facial-symmetry/version
```

### 9.4 API 验收标准

- 支持上传正脸图和露齿图。
- 成功返回标准 JSON。
- 失败返回稳定错误码。
- 响应包含版本信息。
- 响应包含质量结果、评分、部件属性、解释项和免责声明。

## 10. 第 7 周：测试集评估

### 10.1 目标

在冻结测试集上输出 precision 报告。

### 10.2 建议文件

```text
src/facesymai/evaluation/metrics.py
src/facesymai/evaluation/run_static_eval.py
reports/v1_precision_report.md
reports/v1_prediction_details.csv
reports/v1_error_analysis.md
```

### 10.3 评估流程

```text
加载 test manifest
  -> 逐样本调用 pipeline/API
  -> 保存样本级 prediction_details
  -> 根据固定阈值生成 y_pred
  -> 计算 TP/FP/TN/FN
  -> 计算 precision、recall、specificity
  -> 输出 Markdown/CSV 报告
```

### 10.4 样本级结果字段

```text
sample_id
patient_id_hash
y_true
y_score
y_pred
quality_score
quality_level
affected_side_pred
top_region
top_feature
error_type
```

### 10.5 验收标准

- precision 可由 `v1_prediction_details.csv` 复核。
- 报告包含 TP、FP、TN、FN。
- 报告包含阈值和阳性规则。
- 报告记录模型/API/特征/质量门控版本。

## 11. 第 8 周：验收与汇报

### 11.1 目标

完成 V1 交付验收，并准备 V2 研发入口。

### 11.2 交付物

```text
docs/algorithm/facial-symmetry-technical-solution.md
docs/algorithm/facial-symmetry-technical-solution-detailed.md
docs/algorithm/facial-symmetry-rd-plan.md
docs/algorithm/facial-symmetry-rd-plan-detailed.md
docs/api/facial-symmetry-api.md
reports/v1_precision_report.md
reports/v1_error_analysis.md
```

### 11.3 演示内容

- 输入一组正脸图和露齿图。
- 展示 MediaPipe 关键点检测结果。
- 展示质量门控结果。
- 展示总体对称性评分。
- 展示五类部件属性。
- 展示 top contributions。
- 展示 precision 报告。
- 说明 V1 边界和 V2 计划。

## 12. V2 Backlog

V2 不影响 V1 两个月验收，但需要预留接口和数据结构。

V2 任务池：

| 方向 | 内容 | 价值 |
| --- | --- | --- |
| 视频输入 | 5 到 10 秒短视频 | 支持动态面瘫表现 |
| 动作检测 | 微笑、闭眼、抬眉、鼓腮、眨眼 | 增强面神经功能判断 |
| 时序特征 | 幅度、速度、延迟、峰值时间 | 区分静态不对称和运动能力异常 |
| 深度模型 | CNN/ViT ROI、TCN/GRU/Transformer | 提升复杂场景表现 |
| 多模态融合 | 人脸 + BE-FAST + 言语/肢体 + 病史 | 提升卒中预警可靠性 |
| 概率校准 | Brier score、校准曲线 | 输出更可信的风险概率 |

## 13. 风险清单

| 风险 | 发生阶段 | 影响 | 控制措施 |
| --- | --- | --- | --- |
| 测试集无可靠标签 | 第 1/7 周 | precision 无法解释 | 先明确 label_type，必要时先评估面瘫/对称性 precision |
| MediaPipe 低质图漂移 | 第 2/3 周 | 特征误判 | 强化质量门控，低置信区域不评分 |
| 露齿图不合规 | 第 3/4 周 | 口部误判 | 增加露齿合规检查 |
| 静态图召回不足 | 第 7 周 | 漏检 | 明确 V1 是静态筛查，V2 做动态 |
| 权重经验性强 | 第 5/7 周 | 指标波动 | 测试集误差分析，后续用验证集校准 |
| 医疗表述不当 | 全阶段 | 合规风险 | 所有输出使用辅助预警，不写诊断 |

## 14. 完成定义

V1 完成定义：

- MediaPipe 静态图片检测接入完成。
- 正脸图和露齿图能完成关键点映射。
- 质量门控可用。
- 总体对称性和五类部件属性可输出。
- API 可调用。
- 冻结测试集 precision 报告可复核。
- 文档、示例、错误码和免责声明完整。

V1 未完成定义：

- 只能跑 CLI，不能 API 调用。
- 只有总体分，没有部件解释。
- 只有 precision 小数，没有 TP/FP 明细。
- 低质量输入仍输出高可信结果。
- 输出中存在“诊断脑卒中”等医学结论。

## 15. 参考资料

- Google AI Edge, MediaPipe Face Landmarker: https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker
- Google AI Edge MediaPipe GitHub: https://github.com/google-ai-edge/mediapipe
- NCBI Bookshelf, NIH Stroke Scale table: https://www.ncbi.nlm.nih.gov/books/NBK499997/table/article-23776.table0/
- CDC, Signs and Symptoms of Stroke: https://www.cdc.gov/stroke/signs-symptoms/
