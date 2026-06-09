---
title: "Epics and Backlog: FaceSymAi"
project: "FaceSymAi"
status: "updated"
created: "2026-05-18"
last_updated: "2026-05-28"
method: "BMAD-METHOD"
---

# Epics and Backlog

## Epic 0: 项目基础与环境

状态：已完成。

- Story 0.1：固定 conda 环境入口。已完成。
- Story 0.2：安装 BMAD-METHOD 并生成 Codex 技能。已完成。
- Story 0.3：建立项目上下文和规划产物。已完成。
- Story 0.4：确认原始数据目录和只读策略。已完成原则，原始 xlsx 保持只读。
- Story 0.5：固定运行脚本和 Python path。已完成。

## Epic 1: 数据盘点

状态：待优先执行。

- Story 1.1：读取两个 xlsx 的 workbook/sheet 元数据。
- Story 1.2：生成字段列表、类型推断、行数和缺失率。
- Story 1.3：识别疑似 ID、时间、标签、评分、审核状态字段。
- Story 1.4：盘点 `datasets/*/metadata` 下 records 和 media manifest。
- Story 1.5：输出数据字典草案。

## Epic 2: 数据质量与输入门控

状态：部分完成。

- Story 2.1：检查重复记录、空值、异常枚举和时间范围。待完成。
- Story 2.2：输出字段级质量问题清单。待完成。
- Story 2.3：输出样本分布和潜在偏差。待完成。
- Story 2.4：确认是否需要脱敏。待确认。
- Story 2.5：实现基础图片/视频质量门控。已完成 baseline。
- Story 2.6：用 MediaPipe 检测结果增强人脸数量、姿态和关键点可信度门控。待完成。

## Epic 3: MVP 任务定义与验收

状态：部分完成，待固化评估规则。

- Story 3.1：确认人脸对称性用于脑卒中/面瘫预警辅助解释。已形成 V1 假设。
- Story 3.2：定义输入、输出、标签、评估指标和医疗安全边界。部分完成。
- Story 3.3：确认风险提示与医疗合规边界。已按“辅助分析非诊断”处理，待最终确认。
- Story 3.4：形成可实施验收标准。precision 口径已写入 PRD，待冻结测试集。
- Story 3.5：定义冻结测试集切分规则。待完成。
- Story 3.6：定义阳性判定阈值和样本级预测明细格式。待完成。

## Epic 4: 人脸对称性算法 baseline

状态：已完成 baseline。

- Story 4.1：定义人脸关键点输入 schema。已完成。
- Story 4.2：实现全局镜像误差、中线偏移、嘴角不对称、眼裂不对称、眉部不对称。已完成。
- Story 4.3：实现预警辅助置信度和解释项输出。已完成。
- Story 4.4：实现输入质量门控和医疗安全声明。已完成 baseline。
- Story 4.5：补充样例和单元测试。已完成。
- Story 4.6：检测层与核心算法解耦。已完成。

## Epic 5: MediaPipe 检测基座

状态：已完成可运行基线。

- Story 5.1：确认当前 MediaPipe runtime 能力。已完成，当前包支持 Tasks API，不支持旧 `mp.solutions.face_mesh`。
- Story 5.2：引入 Face Landmarker `.task` 模型。已完成：`models/mediapipe/face_landmarker.task`。
- Story 5.3：实现 Face Landmarker adapter。已完成：`src/facesymai/landmarks/mediapipe_face_landmarker.py`。
- Story 5.4：提供单张本地图片检测 CLI。已完成：`scripts/detect_mediapipe_image.py`。
- Story 5.5：批量数据集脚本切换到 Face Landmarker。已完成：`scripts/collect_v1_keypoint_dataset.py`。
- Story 5.6：补充运行文档。已完成：`docs/algorithm/mediapipe-local-image-runtime.md`。
- Story 5.7：记录模型 checksum、版本和审批信息。待完成。

## Epic 6: V1 Keypoint Dataset

状态：已完成当前 by-name 全量版本，待人工抽样复核。

- Story 6.1：按 `front,smile,teeth` 跑限定范围 keypoint extraction。已完成。
- Story 6.2：生成 by-name 版本化输出：`datasets/facesym_v1_by_name_20260119`。已完成。
- Story 6.3：统计 detected/no_face/failed 分布。已完成：`detected` 1538、`no_face` 7、`failed` 1。
- Story 6.4：抽样人工复核关键点质量。待完成，优先查看 `annotated/.../*.jpg`。
- Story 6.5：记录模型、脚本、参数和运行结果。已完成，见 `reports/*.md` 与 `metadata/pipeline_summary.json`。
- Story 6.6：每个数据处理阶段输出结果和报告。已完成。

## Epic 7: Precision 评估

状态：已生成技术 baseline，待标签和冻结测试集确认。

- Story 7.1：确认标签来源和二值映射。当前使用 patient outcome，待确认是否作为验收标签。
- Story 7.2：生成冻结测试集 manifest。已生成患者级分层切分，待业务冻结。
- Story 7.3：定义阳性判定阈值。当前由 validation split 自动选择阈值 `0.277158`，待业务确认。
- Story 7.4：运行 baseline scoring。已完成。
- Story 7.5：输出 precision、TP、FP、阈值、测试集版本、模型版本和样本级预测明细。已完成技术版，见 `datasets/facesym_v1_by_name_20260119/reports/06_baseline_evaluation.md` 和 `metadata/06_baseline_predictions.csv`。
- Story 7.6：复核 FP 样本并归因：质量问题、标签问题、检测漂移或规则阈值问题。

## Epic 8: 全图片对比、V1.1 预测与 HB Proxy 分级

状态：已完成当前技术版，待人工标签校准。

- Story 8.1：构建全图片无质量门控对比组。已完成：`datasets/facesym_v1_all_images_no_gate_20260119`。
- Story 8.2：生成 MediaPipe 478 点和 blendshape 全量特征矩阵。已完成：`metadata/09_mediapipe_full_features.csv`。
- Story 8.3：输出患病/不患病特征差异。已完成：`metadata/09_mediapipe_feature_differences.csv`。
- Story 8.4：构建 V1.1 role-aware 弱监督患者级预测。已完成：`metadata/11_v11_role_aware_predictions.csv`。
- Story 8.5：构建 HB proxy I-VI 技术代理分级。已完成：`metadata/12_v11_hb_proxy_patient_grades.csv`。
- Story 8.6：输出 Grade V+ 人脸不对称清单。已完成：105 例，其中患病 87、不患病 18。
- Story 8.7：生成 Grade V+ 不患病复核和患病/不患病 18 对照报告。已完成。
- Story 8.8：验证 18 对差异普适性并防止小样本规则过拟合。已完成，当前主规则不调整。
- Story 8.9：提供人工面部不对称/质量复核标注网站。已完成本地/远程入口，待填充标签。
- Story 8.10：生成 MediaPipe 全流程最大差异特征和预测汇总。已完成：`reports/20_mediapipe_end_to_end_summary.md`。
- Story 8.11：固化当前人脸是否对称的核心关键点判断特征。已指定 5 项：`bsdiff_mouthFrown_abs`、`raw_all_mesh_region_point_spread_asym`、`bsdiff_mouth_abs`、`raw_lip_midline_deviation`、`raw_mouth_corner_vertical_asym`；待接入下一版评分/报告，并要求输入满足 MediaPipe `detected`、478 raw landmarks、mouth blendshape 完整和关键点可视化复核。

## Epic 9: 人工标签校准与正式验收

状态：待执行。

- Story 9.1：组织人工复核人员使用标注网站填充 `metadata/16_v11_face_asymmetry_review_labels.csv`。
- Story 9.2：重新运行人工标签校准脚本，生成 calibration summary/config。
- Story 9.3：基于人工标签复核 Grade V+ 阈值、组件权重和误报来源。
- Story 9.4：冻结正式测试集版本、阳性规则和阈值审批流程。
- Story 9.5：输出正式验收报告，明确 patient outcome 弱监督指标与人工面部不对称指标的边界。

## Epic 10: 后续产品化准备

状态：待评估闭环后决策。

- Story 10.1：确认是否需要 API 服务。
- Story 10.2：确认是否需要正式前端审核/报告页面。
- Story 10.3：确认部署环境、权限和审计要求。
- Story 10.4：拆分 Sprint 计划。

## 当前推荐下一步

优先将 Epic 8.11 的 5 个核心对称特征接入下一版评分/报告，并在输入校验中强制检查关键点输出完整性；同时推进 Epic 9 的人工标签填充、冻结测试集和验收口径确认。当前数据处理流程已经可复跑，下一步应把 patient outcome 弱监督技术报告转为人工标签支撑的可验收评估。
