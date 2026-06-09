---
title: "BMAD 输入摘要：FaceSymAi"
project: "FaceSymAi"
status: "updated"
created: "2026-05-18"
last_updated: "2026-05-28"
method: "BMAD-METHOD v6.6.0"
---

# BMAD 输入摘要

## 已确认输入

- 项目路径：`/supercloud/llm-code/scc/scc/FaceSymAi`
- 基础环境：conda env `anti-spoofing_scc_175`
- Python 版本：3.9.25
- BMAD 安装目录：`_bmad`
- BMAD 规划输出：`_bmad-output/planning-artifacts`
- 当前业务资料：
  - `脑卒中数据采集-审核导出-20260119.xlsx`
  - `脑卒中预警报告老来健康app线上_2026-05-08.xlsx`
- 当前本地数据集目录：
  - `datasets/stroke_media_dataset_20260119`
  - `datasets/stroke_warning_app_media_dataset_20260508`
  - `datasets/stroke_patient_outcome_quality_gated_20260119`
  - `datasets/stroke_patient_outcome_by_name_20260119`
  - `datasets/facesym_v1_by_name_20260119`
  - `datasets/facesym_v1_all_images_no_gate_20260119`
- 当前 MediaPipe 模型：
  - `models/mediapipe/face_landmarker.task`

## 当前实现快照

- 项目已形成 Python 包结构：`src/facesymai/`。
- 已实现关键点级人脸对称性 baseline：
  - 结构化 landmark schema。
  - 全局镜像误差、中线偏移、嘴角、眼裂、眉部特征。
  - 预警辅助置信度、解释项、医疗安全声明。
- 已实现质量门控 baseline：
  - 图片/视频基础质量检查。
  - OpenCV Haar 代理人脸检测。
  - 分辨率、清晰度、亮度、曝光、左右光照、人脸数量/大小等规则。
- 已补齐 MediaPipe 本地图片检测运行环境：
  - 环境已验证 `mediapipe 0.10.35`、`cv2 4.13.0`。
  - 当前 MediaPipe 包支持 Tasks API，不支持旧 `mp.solutions.face_mesh`。
  - 已接入 MediaPipe Tasks `Face Landmarker`。
  - 已提供单图/目录检测脚本 `scripts/detect_mediapipe_image.py`。
  - 已提供批量关键点采集脚本 `scripts/collect_v1_keypoint_dataset.py` 的 Face Landmarker 路径。
- 当前验证结果：
  - 单图 smoke test 成功，输出 `478` 个 raw landmarks、`52` 个 blendshape、`1` 个 transformation matrix。
  - 批量采集 smoke test 成功：`--limit 1 --roles front`。
  - by-name V1 数据处理正式运行完成：505 个患者样本、1546 张 `front/smile/teeth` 图片，MediaPipe `detected` 1538、`no_face` 7、`failed` 1，已生成 1538 张特征点绘制图。
  - 静态集合特征已输出总体对称性评分、疑似异常侧，以及口部、眼部、眉部、鼻面中线、面部轮廓五类部件级属性。
  - 坐标标准化已前置到特征层：鼻梁/鼻尖/下巴中线拟合、轻微 roll 校正、双眼外角距离尺度归一化。
  - 全图片无质量门控对比组已完成：5195 张图片、505 个患者，MediaPipe `detected` 5005、`no_face` 189、`failed` 1。
  - V1.1 role-aware 预测已完成：504 个可评分患者，test precision `0.690476`、recall `0.568627`、specificity `0.500000`。
  - HB proxy Grade I-VI 分级和 Grade V+ 人脸不对称输出已完成：Grade V+ 输出 105 例，其中患病 87、不患病 18；test precision `0.727273`、specificity `0.884615`。
  - MediaPipe 全流程汇总已完成：`metadata/20_mediapipe_end_to_end_feature_differences.csv`、`metadata/20_mediapipe_end_to_end_predictions.csv`、`reports/20_mediapipe_end_to_end_summary.md`。
  - 当前已基于旧数据和新数据指定 5 个核心人脸对称判断特征：`bsdiff_mouthFrown_abs`、`raw_all_mesh_region_point_spread_asym`、`bsdiff_mouth_abs`、`raw_lip_midline_deviation`、`raw_mouth_corner_vertical_asym`。旧数据患者级 all+max 口径 5/5 患病更高；新数据 `smile_teeth` role 口径 5/5 患病更高。
  - 单元测试：`52 passed`。

## 当前约束

- 原始 xlsx 文件不修改。
- 医疗相关输出仍限定为“风险提示/辅助分析”，不得表述为诊断结论。
- MediaPipe Face Landmarker 使用 `.task` 模型文件；若部署或验收要求严格复现，需要固定模型版本、来源和 checksum。
- 当前质量门控中的人脸数量/遮挡代理仍有 OpenCV Haar 过渡实现，后续应逐步用 MediaPipe 检测结果补强。
- 当前风险评分、V1.1 预测和 HB proxy 分级均仍基于 patient outcome 弱监督，尚未完成冻结测试集和人工面部不对称标签下的正式验收。
- 当前 baseline/V1.1/HB proxy 已 against patient outcome 标签生成技术报告，但 patient outcome 不是直接面部不对称 ground truth，正式验收前仍需确认标签适用性。
- 核心对称判断特征必须在 MediaPipe 关键点输出完整时计算：`detection_status=detected`、478 个 `raw_landmarks`、mouth blendshape 完整、可拟合面部中线并完成双眼外角距离归一化；不满足时应输出不可评分或需复核。

## 工作假设

- V1 聚焦静态图片分析，优先处理 `front`、`smile`、`teeth` 等面部图像角色。
- V1 输出作为脑卒中/面瘫预警辅助解释，不作为临床诊断。
- 视频和动作时序、生产 API、前端审核页面进入后续阶段。
- 近期最关键工作从“接入检测器/生成数据集”转为：
  1. 将 5 个核心对称特征接入下一版评分/报告规则，并保留 `smile_teeth`/`smile_or_teeth` 等 role-specific 解释。
  2. 通过人工标注网站形成 `16_v11_face_asymmetry_review_labels.csv`。
  3. 确认 patient outcome 标签是否适合作为 V1 弱监督检查，人工面部不对称标签是否作为正式验收标签。
  4. 固化冻结测试集、阈值审批和 FP/FN 复核流程。

## 推荐 BMAD 流程

1. Consolidation：将当前代码、模型、脚本和文档状态固化为实施基线。
2. Data Processing：以 `scripts/build_facesym_v1_dataset_from_by_name.py` 作为当前数据处理流程，所有阶段输出结果和报告。
3. End-to-End Review：基于 `reports/20_mediapipe_end_to_end_summary.md` 和新数据 40 阶段验证产物，复核 5 个核心对称特征、患者级预测和 Grade V+ 人脸不对称输出。
4. Data Understanding：盘点 xlsx 和 media manifest，确认字段、标签和样本角色。
5. Evaluation Planning：定义冻结测试集、阳性规则、阈值和 precision 报告格式。
6. Implementation：基于 `metadata/20_mediapipe_end_to_end_predictions.csv` 复核 baseline/V1.1/HB proxy 的样本级预测明细和失败样本。
