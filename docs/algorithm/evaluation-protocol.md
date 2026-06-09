# FaceSymAi 任务定义与评估验收协议

版本：0.1  
日期：2026-05-19  
状态：评估协议草案  

## 1. 任务定义

FaceSymAi 的当前研发任务定义为：

从图片或短视频中提取面部对称性、面瘫相关属性和卒中预警辅助信号，并通过 API 输出可解释结果。

该任务包含三个层次：

- 人脸对称性判断：输出 `symmetry_score`、`affected_side` 和主要不对称证据。
- 面瘫相关属性识别：输出嘴角下垂、闭眼不全、眉部不对称、中线偏移、鼻唇沟变浅代理特征、House-Brackmann 分级和 NIHSS Facial Palsy 项。
- 卒中预警辅助信号：输出 `stroke_probability`、`stroke_warning_level`、质量门控结果、解释项和复核建议。

医学边界：

- API 输出用于预警辅助和解释增强。
- API 不输出“确诊脑卒中”结论。
- 任何高风险结果都应提示结合 BE-FAST、肢体、言语、意识、发病时间、病史和临床流程复核。

## 2. 验收口径

主验收口径：

在冻结测试集上运行模型或 API，输出准确、可复核的 `precision`。

这里的“准确”指计算过程、样本集合、阳性定义、阈值和分母分子均可追踪，而不是只输出一个无法复核的小数。

## 3. Precision 定义

主验收指标为卒中预警辅助阳性 precision：

```text
precision = TP / (TP + FP)
```

其中：

- `TP`：模型/API 输出卒中预警阳性，且测试集标签为阳性。
- `FP`：模型/API 输出卒中预警阳性，但测试集标签为阴性。
- `TP + FP`：模型/API 在测试集中输出阳性的样本总数。

默认阳性预测定义：

```text
prediction_positive = stroke_warning_level in ["elevated", "high", "emergency_review"]
```

默认阳性标签定义：

```text
label_positive = test_label.stroke_confirmed == true
```

如果当前测试集只有面瘫标签、没有临床卒中标签，则主 precision 应切换为面瘫视觉任务：

```text
prediction_positive = facial_asymmetry_abnormal == true
label_positive = test_label.facial_palsy_or_asymmetry == true
```

报告中必须明确实际采用的是“卒中预警 precision”还是“面瘫/对称性 precision”。

## 4. 测试集要求

测试集必须满足：

- 测试集在评估前冻结，不参与训练、调参、阈值选择和错误分析优化。
- 使用患者级划分，同一患者的图片、视频、关键点和多次动作片段不能同时出现在训练集和测试集。
- 每条样本有唯一 `sample_id`，可追踪到采集记录、输入文件、标签和评估结果。
- 测试集包含阳性、阴性和 hard negative 样本。
- 低质量样本应保留，但需单独分层报告，不能只从测试集中删除。

建议测试集字段：

```text
sample_id
patient_id_hash
input_type
input_path_or_object_id
capture_action
quality_label
stroke_confirmed
facial_palsy_or_asymmetry
affected_side_label
house_brackmann_grade_label
nihss_facial_palsy_score_label
label_source
split
```

## 5. 阈值规则

在测试集上计算 precision 前，阈值必须已经固定。

允许的阈值来源：

- 规则模型固定阈值。
- 验证集上选择的阈值。
- 产品策略指定的阈值。

禁止：

- 在测试集上反复调阈值后再报告 precision。
- 只报告最优测试集阈值下的 precision。
- 删除误报样本后重新计算 precision。

报告中必须包含：

```text
model_version
feature_version
quality_gate_version
threshold_version
threshold_value
positive_prediction_rule
test_set_version
```

## 6. Precision 报告格式

每次验收至少输出：

```json
{
  "metric": "precision",
  "task": "stroke_warning",
  "value": 0.9231,
  "tp": 120,
  "fp": 10,
  "predicted_positive": 130,
  "test_samples": 500,
  "threshold": 0.65,
  "positive_rule": "stroke_warning_level in ['elevated', 'high', 'emergency_review']",
  "test_set_version": "test-v1.0",
  "model_version": "facesymai-0.1.0",
  "confidence_interval_95": [0.8672, 0.9589]
}
```

同时建议输出辅助指标：

- recall/sensitivity。
- specificity。
- NPV。
- F1。
- ROC-AUC。
- PR-AUC。
- confusion matrix。
- calibration/Brier score。

原因：只看 precision 可能掩盖漏检。如果模型只对极少数样本报阳性，precision 可以很高，但 recall 可能很低。

## 7. 分层报告

precision 应至少按以下维度分层：

- 输入类型：图片、短视频、关键点序列。
- 采集质量：高质量、中质量、低质量、被质量门控拒绝。
- 场景：医院采集、居家 App 采集、其他。
- 年龄段。
- 性别。
- 设备类型。
- 姿态范围。
- 是否 hard negative。

示例：

```text
overall_precision
precision_by_input_type
precision_by_quality_level
precision_on_hard_negatives
precision_on_video_only
precision_on_image_only
```

## 8. 通过标准

当前版本的基础通过标准：

- 能在冻结测试集上完整跑通评估。
- 能输出 precision、TP、FP、阈值、测试集版本和模型版本。
- precision 计算可由样本级预测明细复核。
- 评估脚本对同一输入重复运行结果一致。

如果后续项目要求“95% 以上精准检测”，建议写成明确上线门槛：

```text
在冻结测试集或外部测试集上，high_warning 策略的 precision >= 0.95；
同时报告该策略下的 recall，且 recall 不得低于另行确认的业务底线。
```

## 9. 样本级预测明细

验收时必须保留样本级结果表：

```text
sample_id
patient_id_hash
y_true
y_score
y_pred
stroke_probability
stroke_warning_level
quality_score
quality_level
hard_reject
affected_side_pred
top_contributions
error_type
```

样本级结果用于：

- 复核 TP/FP。
- 分析误报原因。
- 复现实验报告。
- 医生或审核人员抽样复核。

## 10. 推荐下一步

研发上应优先实现：

1. `dataset_manifest`：固定测试集样本和标签。
2. `evaluation` 模块：读取样本级预测结果并计算 precision。
3. API 输出 `stroke_warning_level` 和 `stroke_probability`，保证能按固定阳性规则计算 precision。
4. 报告生成脚本：输出 JSON 和 Markdown 两种评估报告。
