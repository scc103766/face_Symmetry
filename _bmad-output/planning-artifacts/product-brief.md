---
title: "Product Brief: FaceSymAi"
project: "FaceSymAi"
status: "updated"
created: "2026-05-18"
last_updated: "2026-05-28"
method: "BMAD-METHOD"
---

# Product Brief

## 背景

FaceSymAi 已从空项目推进到可运行的 MediaPipe 全流程分析阶段。项目当前使用 conda env `anti-spoofing_scc_175`，已有两个脑卒中相关 xlsx 文件、本地 media 数据集目录、质量门控产物、基于 MediaPipe Face Landmarker 的本地图片关键点检测入口、V1/V1.1 患者级预测产物和 HB proxy 技术代理分级产物。

## 问题陈述

当前最大风险已从“没有可运行检测器/算法”转为“patient outcome 弱监督标签与人工面部不对称真值之间的口径差异、冻结测试集、precision 验收和医疗合规边界尚未完全固化”。项目现在需要基于已跑通的 20 阶段 MediaPipe 全流程汇总，推进人工复核标签、FP/FN 归因和正式验收口径冻结。

## 当前进展

- 已建立 Python 包：`src/facesymai/`。
- 已实现结构化 landmark 输入下的人脸对称性分析和风险解释。
- 已实现图片/视频基础质量门控。
- 已接入 MediaPipe Tasks `Face Landmarker` 作为 V1 检测基座。
- 已下载并放置模型：`models/mediapipe/face_landmarker.task`。
- 已新增本地图片检测命令：`scripts/detect_mediapipe_image.py`。
- 已更新 V1 关键点数据集采集脚本：`scripts/collect_v1_keypoint_dataset.py`。
- 已固化当前推荐数据处理流程：`scripts/build_facesym_v1_dataset_from_by_name.py`。
- 已生成正式 V1 by-name 数据处理结果：`datasets/facesym_v1_by_name_20260119`。
- 已生成全图片无质量门控对比组：`datasets/facesym_v1_all_images_no_gate_20260119`，覆盖 5195 张图片、505 个患者。
- 已落地 V1.1 role-aware 患病/不患病弱监督预测、HB proxy I-VI 技术代理分级、Grade V+ 人脸不对称输出、18 对患病/不患病配对对比和人工复核标注入口。
- 已新增 MediaPipe 全流程特征差异与预测汇总：`scripts/summarize_mediapipe_end_to_end_outputs.py`，输出 `metadata/20_mediapipe_end_to_end_feature_differences.csv`、`metadata/20_mediapipe_end_to_end_predictions.csv` 和 `reports/20_mediapipe_end_to_end_summary.md`。
- 已基于旧数据 `facesym_v1_all_images_no_gate_20260119` 和新数据 `stroke_warning_app_rule_test_set_20260508` 指定当前人脸是否对称的 5 个核心关键点判断特征：`bsdiff_mouthFrown_abs`、`raw_all_mesh_region_point_spread_asym`、`bsdiff_mouth_abs`、`raw_lip_midline_deviation`、`raw_mouth_corner_vertical_asym`。
- 当前测试通过：`52 passed`。

## 目标

- 固化 FaceSymAi V1 为“静态图片人脸对称性预警辅助解释”MVP。
- 使用 MediaPipe Face Landmarker 输出 landmarks、blendshapes 和 transformation matrix，作为检测层基座。
- 将本地媒体数据转换为 V1 关键点数据集。
- 将 5 个核心 MediaPipe 派生特征作为当前人脸对称性判断的主要解释证据，并保留 role-specific 口径，尤其是 `smile_teeth`/`smile_or_teeth`。
- 为每个数据处理阶段输出 CSV/JSON 结果和 Markdown 报告。
- 明确标签口径、冻结测试集、阈值和 precision 评估报告。
- 保持医疗安全边界：输出风险提示和解释，不输出诊断。

## 非目标

- 暂不宣称具备医学诊断能力。
- 暂不训练生产级临床模型。
- 暂不建设用户端应用或在线推理服务。
- 暂不把侧脸、舌像或视频动作时序纳入 V1 主评分。
- 暂不修改原始 xlsx 文件。

## 初始用户与使用场景

- 算法/数据人员：批量提取人脸关键点，生成样本级评分和评估报告。
- 业务/医学复核人员：查看样本级异常解释、质量拒绝原因和预警辅助信号。
- 项目研发人员：基于固定脚本和模型复现实验结果。

## 成功指标草案

- 任意本地正脸/示齿图片可通过脚本输出 MediaPipe 检测 JSON。
- 批量媒体样本可生成 V1 keypoint dataset；当前 by-name 流程已处理 505 个患者样本、1546 张 V1 图片。
- 输出包含 face count、semantic landmarks、raw landmarks、blendshapes、transformation matrix、可选质量门控和对称性分析结果。
- 静态几何特征已输出总体对称性评分和五类部件级属性：口部、眼部、眉部、鼻面中线、面部轮廓。
- 每个处理阶段均有结果和报告：`datasets/facesym_v1_by_name_20260119/metadata/*` 与 `datasets/facesym_v1_by_name_20260119/reports/*`。
- 当前技术 baseline、V1.1 患病/不患病预测和 Grade V+ 人脸不对称输出均已生成报告；正式验收仍需冻结标签、测试集版本和人工面部不对称标签。
- 20 阶段汇总已输出最大差异特征和患者级预测：V1.1 test precision `0.690476`、recall `0.568627`、specificity `0.500000`；Grade V+ 人脸不对称 test precision `0.727273`、specificity `0.884615`。
- 核心对称特征的可评分输入必须能产出 MediaPipe `detected` 结果、478 个 raw landmarks 和 mouth blendshape；缺失关键点或 blendshape 时必须标记为不可评分或需复核。
- 全部结果包含医疗辅助声明，不产生诊断结论。

## 待确认问题

1. V1 评估使用哪些 media roles：`front`、`smile`、`teeth` 是否作为首批范围？
2. 当前 patient outcome 标签是否可作为 V1 验收标签，还是需要人工面部不对称标签？
3. 当前患者级分层切分是否可被冻结，还是需要按采集批次、时间或业务规则重新切分？
4. precision 的阳性判定阈值由谁确认，是否需要同时报告 recall、specificity 和混淆矩阵？
5. 当前官方 latest `face_landmarker.task` 是否满足验收要求，还是需要固定指定版本和 checksum？
6. Grade V+ 人脸不对称输出是否作为当前业务输出阈值，还是等待人工标签校准后再冻结？
