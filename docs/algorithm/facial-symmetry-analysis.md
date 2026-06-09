# 人脸对称性分析算法设计

## 定位

该算法输出“脑卒中/面瘫预警辅助解释信号”，不输出医学诊断结论。结果用于解释预警系统为什么关注某一次采集的人脸，而不是替代医生或急救流程。

## 输入

核心算法输入为结构化人脸关键点：

```json
{
  "image_id": "example",
  "pose": {"yaw": 0, "pitch": 0, "roll": 0},
  "landmarks": {
    "nose_bridge": [0.50, 0.24, 0.99],
    "chin": [0.50, 0.88, 0.99],
    "left_mouth_corner": [0.38, 0.68, 0.98],
    "right_mouth_corner": [0.62, 0.68, 0.98]
  }
}
```

检测器不写死在核心算法里。后续可接：

- MediaPipe Face Mesh
- dlib 68 点
- InsightFace/RetinaFace + landmark head
- 自研医学场景关键点模型

## 特征

当前实现位于 `src/facesymai`，包含：

- 坐标标准化：先用鼻梁、鼻尖、下巴拟合鼻面中线，再把关键点投影到以中线为纵轴的局部坐标系，并用双眼外角距离做尺度归一化。
- 全局镜像误差：左右成对关键点相对面部中线的镜像差异。
- 中线偏移：鼻尖、唇中点等中线结构相对鼻梁-下巴中线的偏移。
- 嘴角上下不对称：识别口角下垂或表情控制差异。
- 眼裂开合不对称：识别左右眼开合差异。
- 眉部高度不对称：识别额面部肌群控制差异。
- 输入质量：关键点置信度和头部姿态质量。

## 输出

输出字段：

- `symmetry`：总体对称性结果，包含 `overall_symmetry_score`、`overall_asymmetry_severity`、`affected_side` 和 `confidence`。
- `attributes`：口部、眼部、眉部、鼻面中线、面部轮廓五类部件级属性。
- `advisory_confidence`：预警辅助置信度，范围 0 到 1。
- `risk_level`：`low`、`watch`、`elevated`、`high`。
- `features`：全部特征值和严重度。
- `top_contributions`：主要解释项。
- `warnings`：采集质量或使用限制。
- `recommended_action`：业务动作建议。
- `disclaimer`：医疗安全声明。

## 置信度定义

当前版本使用规则/线性加权 + sigmoid 的可解释 baseline：

```text
raw_score = sigmoid(intercept + sum(weight_i * severity_i))
advisory_confidence = raw_score * input_quality
```

这不是已校准临床模型。后续如果有标注数据，应使用训练集/验证集进行校准，并输出 AUC、敏感性、特异性、PPV、NPV 和置信区间。

## 运行

```bash
scripts/run_in_project_env.sh python -m facesymai examples/landmarks_symmetric.json --pretty
scripts/run_in_project_env.sh python -m facesymai examples/landmarks_mouth_droop.json --pretty
```

## 医学依据与边界

- CDC 将“突发面部、手臂或腿部麻木/无力，尤其单侧”列为卒中症状之一，并强调需要快速急救处理。
- NINDS NIH Stroke Scale 包含 Facial Palsy 项，使用面部运动和对称性作为卒中严重程度评估的一部分。
- House-Brackmann 分级用于面神经麻痹严重程度评估，可作为面瘫侧解释参考。

参考资料：

- CDC Stroke Signs and Symptoms: https://www.cdc.gov/stroke/signs-symptoms/
- NINDS NIH Stroke Scale: https://www.ninds.nih.gov/health-information/stroke/assess-and-treat/nih-stroke-scale
- NIH Stroke Scale PDF: https://www.ninds.nih.gov/sites/default/files/documents/NIH-Stroke-Scale_updatedFeb2024_508.pdf
- NCBI Bookshelf House-Brackmann table: https://www.ncbi.nlm.nih.gov/books/NBK549815/table/article-21555.table1/

## 后续增强

1. 接入真实关键点检测器。
2. 增加视频动态特征：微笑、闭眼、鼓腮、皱眉动作前后差异。
3. 建立个体历史基线，降低先天不对称和年龄因素影响。
4. 加入质量门控：遮挡、侧脸、光照、模糊、表情非中立。
5. 使用标注数据训练并校准风险模型。
