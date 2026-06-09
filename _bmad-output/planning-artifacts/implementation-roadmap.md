---
title: "Implementation Roadmap: FaceSymAi"
project: "FaceSymAi"
status: "updated"
created: "2026-05-18"
last_updated: "2026-05-28"
method: "BMAD-METHOD"
---

# Implementation Roadmap

## 当前进度摘要

FaceSymAi 已完成从项目初始化到“本地图片 MediaPipe 检测 + 关键点对称性 baseline + by-name V1 数据处理流程 + 全图片无质量门控对比 + V1.1 role-aware 预测 + HB proxy I-VI 分级 + MediaPipe 全流程汇总”的多阶段闭环。当前已基于旧数据和新数据指定 5 个 MediaPipe 派生特征作为人脸是否对称的核心关键点判断项。当前重点不再是证明检测器可接入或证明数据流程可跑，而是把这 5 个特征接入下一版评分/报告规则、补齐人工面部不对称标签、确认标签适用性、冻结测试集，并把 patient outcome 弱监督技术报告转为可验收报告。

## M0: 基础环境与规划

状态：已完成。

- 固定 conda env `anti-spoofing_scc_175`
- 安装 BMAD-METHOD `bmm`
- 安装 Codex BMAD 技能
- 建立初始规划文档
- 固定项目运行脚本 `scripts/run_in_project_env.sh`

验收状态：通过。

## M1: 人脸对称性算法 baseline

状态：已完成 baseline。

目标：建立可运行、可测试、可解释的关键点级对称性分析算法。

交付：

- `src/facesymai/`
- `examples/landmarks_*.json`
- `tests/test_symmetry_analysis.py`
- `docs/algorithm/facial-symmetry-analysis.md`

验收状态：

- 对合成对称样本输出低风险。
- 对合成嘴角下垂样本输出更高置信度。
- 输出包含特征、贡献项、输入质量和医疗安全声明。
- 当前单元测试通过：`52 passed`。

## M1.5: MediaPipe 检测基座与本地图片运行环境

状态：已完成可运行基线。

目标：按照技术方案指定的 MediaPipe 基座，完成本地图片关键点检测。

交付：

- `src/facesymai/landmarks/mediapipe_face_landmarker.py`
- `models/mediapipe/face_landmarker.task`
- `scripts/detect_mediapipe_image.py`
- `scripts/collect_v1_keypoint_dataset.py`
- `docs/algorithm/mediapipe-local-image-runtime.md`
- `docs/datasets/v1-keypoint-dataset.md`

验收状态：

- 环境已验证 `mediapipe 0.10.35`、`cv2 4.13.0`。
- 已确认当前 MediaPipe 包支持 Tasks API，不支持旧 `mp.solutions.face_mesh`。
- 单图 smoke test 成功，输出 `478` 个 raw landmarks、`52` 个 blendshape、`1` 个 transformation matrix。
- 批量采集 smoke test 成功：`--limit 1 --roles front`。

## M2: 数据理解与标签盘点

状态：部分完成，继续推进。

目标：读取现有 xlsx 和 media manifest，形成数据盘点报告，并明确 V1 标签来源。

交付：

- `reports/data_inventory.md`
- `reports/data_dictionary.md`
- `reports/data_quality.md`
- `reports/label_definition.md`

验收：

- 每个 xlsx sheet 有字段、行数、缺失率。
- 每个 media dataset 有 records/media manifest 规模统计。
- 明确候选标签字段和二值映射。
- 每个未知字段被标记为待确认。
- 原始 xlsx 未被修改。

当前补充：

- `datasets/stroke_patient_outcome_by_name_20260119` 已作为 V1 当前正式输入。
- 当前 by-name 输出覆盖 505 个患者样本、1546 张 V1 图片。
- 两个原始 xlsx 的字段级数据字典仍需单独盘点。

## M3: V1 任务定义与冻结测试集

状态：部分完成，待业务冻结。

目标：把 V1 固化为“静态图片人脸对称性预警辅助解释”，并定义冻结测试集与 precision 验收规则。

交付：

- 更新后的 `prd.md`
- 更新后的 `epics-and-backlog.md`
- `reports/evaluation_plan.md`
- 冻结测试集 manifest
- 阳性判定规则和阈值说明

验收：

- 明确输入 media roles：建议从 `front`、`smile`、`teeth` 开始。
- 明确输出 JSON schema。
- 明确标签、指标、阈值、非目标。
- 明确医疗合规边界。

当前补充：

- 已生成患者级分层切分：train 353、val 75、test 77。
- 当前切分可复跑，但尚未被业务冻结为正式测试集。

## M4: V1 Keypoint Dataset

状态：已完成当前 by-name 全量版本。

目标：建立可复现数据处理脚本，将本地媒体样本转换为关键点级数据集。

交付：

- `scripts/build_facesym_v1_dataset_from_by_name.py`
- `datasets/facesym_v1_by_name_20260119/metadata/01_manifest.csv`
- `datasets/facesym_v1_by_name_20260119/metadata/03_keypoints.csv`
- `datasets/facesym_v1_by_name_20260119/keypoints/.../*.json`
- `datasets/facesym_v1_by_name_20260119/annotated/.../*.jpg`
- `datasets/facesym_v1_by_name_20260119/reports/*.md`

验收：

- 所有命令通过 `scripts/run_in_project_env.sh` 执行。
- 可按 media role 限定范围。
- 每个样本记录 detection status。
- 检测失败、无人脸、多人脸可追踪。
- 数据处理不会覆盖原始文件。

验收状态：

- 处理 1546 张图片，MediaPipe `detected` 1538、`no_face` 7、`failed` 1。
- 已生成 1538 张人脸特征点绘制图。
- 每个阶段均有结果和报告。
- `04_features` 已输出总体对称性评分、疑似异常侧，以及口部、眼部、眉部、鼻面中线、面部轮廓五类部件级属性。
- `04_features` 已前置坐标标准化：鼻梁/鼻尖/下巴中线拟合、轻微 roll 校正、双眼外角距离尺度归一化。

## M5: Precision 评估报告

状态：已生成技术 baseline，待正式验收固化。

目标：根据冻结测试集和 V1 keypoint dataset 建立最小可评估 baseline。

交付：

- `datasets/facesym_v1_by_name_20260119/reports/06_baseline_evaluation.md`
- `datasets/facesym_v1_by_name_20260119/metadata/06_baseline_predictions.csv`
- 阈值配置和模型版本记录

验收：

- 指标计算可重复。
- 报告包含 precision、TP、FP、阈值、阳性规则、测试集版本、模型版本和样本级预测明细。
- 结果不被表述为医学诊断。

当前结果：

- 阈值来源：validation split。
- 阈值：`0.277158`。
- test precision：`0.662338`。
- test recall：`1.000000`。
- test specificity：`0.000000`。
- 限制：当前标签是 patient outcome，不是直接面部不对称 ground truth。

## M5.5: 全图片无质量门控对比组

状态：已完成当前全量版本。

目标：读取所有 `media_type=image` 图片，不做 V1 role 筛选和质量门控，观察非 V1 输入和无门控条件对 MediaPipe、特征和 baseline 指标的影响。

交付：

- `scripts/build_facesym_v1_all_images_no_gate_comparison.py`
- `datasets/facesym_v1_all_images_no_gate_20260119/metadata/01_all_images.csv`
- `datasets/facesym_v1_all_images_no_gate_20260119/metadata/03_keypoints.csv`
- `datasets/facesym_v1_all_images_no_gate_20260119/metadata/04_image_features.csv`
- `datasets/facesym_v1_all_images_no_gate_20260119/metadata/06_baseline_predictions.csv`
- `datasets/facesym_v1_all_images_no_gate_20260119/reports/*.md`

验收状态：

- 输入图片 5195 张，患者 505 个。
- MediaPipe `detected` 5005、`no_face` 189、`failed` 1。
- 质量门控显式 skipped，排除图片 0。
- 当前 baseline test precision `0.662338`、recall `1.000000`、specificity `0.000000`。

## M6: V1.1 Role-Aware 与 HB Proxy 分级

状态：已完成当前弱监督技术版，待人工标签校准。

目标：使用 MediaPipe 478 点和 blendshape 派生特征生成患者级弱监督预测，并将输出扩展为 HB proxy I-VI 技术代理分级和 Grade V+ 人脸不对称输出。

交付：

- `scripts/build_v11_role_aware_quality_weighted_fit.py`
- `scripts/build_v11_hb_proxy_grading.py`
- `scripts/extract_v11_grade_v_plus_nondisease_review.py`
- `scripts/compare_v11_grade_v_plus_18_disease_nondisease.py`
- `scripts/analyze_v11_grade_v_plus_generalization.py`
- `scripts/calibrate_v11_hb_proxy_with_review_labels.py`
- `scripts/serve_face_asymmetry_label_tool.py`
- `tools/face_asymmetry_label_tool.html`
- `datasets/facesym_v1_all_images_no_gate_20260119/metadata/11_v11_role_aware_predictions.csv`
- `datasets/facesym_v1_all_images_no_gate_20260119/metadata/12_v11_hb_proxy_patient_grades.csv`
- `datasets/facesym_v1_all_images_no_gate_20260119/reports/14_v11_hb_proxy_grading_results.md`
- `datasets/facesym_v1_all_images_no_gate_20260119/reports/16_v11_grade_v_plus_18_disease_nondisease_comparison.md`

验收状态：

- V1.1 患病/不患病弱监督预测 test precision `0.690476`、recall `0.568627`、specificity `0.500000`。
- HB proxy grade 分布：Grade I 96、Grade II 102、Grade III 104、Grade IV 97、Grade V 68、Grade VI 37。
- Grade V+ 人脸不对称输出 105 例，其中患病 87、不患病 18；test precision `0.727273`、recall `0.156863`、specificity `0.884615`。
- Grade V+ 患病/不患病 18 对照报告已完成，全部 same split + same grade 匹配。
- 当前无人工面部不对称标签，校准状态为 `insufficient_labels`。

## M7: MediaPipe 全流程特征差异与预测汇总

状态：已完成。

目标：将 09/11/12/14 阶段结果汇总到单一交付层，输出影响患病/不患病差异最大的特征项和患者级预测结果。

交付：

- `scripts/summarize_mediapipe_end_to_end_outputs.py`
- `datasets/facesym_v1_all_images_no_gate_20260119/metadata/20_mediapipe_end_to_end_feature_differences.csv`
- `datasets/facesym_v1_all_images_no_gate_20260119/metadata/20_mediapipe_end_to_end_predictions.csv`
- `datasets/facesym_v1_all_images_no_gate_20260119/metadata/20_mediapipe_end_to_end_summary.json`
- `datasets/facesym_v1_all_images_no_gate_20260119/reports/20_mediapipe_end_to_end_summary.md`

验收状态：

- 特征差异汇总 CSV 108 行数据。
- 患者预测 CSV 504 行可评分患者。
- 报告列出患病/不患病主证据差异、预测模型权重最高特征、HB proxy Grade I-VI 最大差异和高分预测样本。
- 已通过 `py_compile` 和全量测试。

## M7.5: 核心对称特征固化与输入格式约束

状态：已指定核心特征，待接入下一版评分/报告。

目标：将两批数据中稳定出现的 5 个 MediaPipe 派生特征固化为人脸是否对称的核心关键点判断，并明确输入数据必须满足关键点输出要求。

核心特征：

- `bsdiff_mouthFrown_abs`
- `raw_all_mesh_region_point_spread_asym`
- `bsdiff_mouth_abs`
- `raw_lip_midline_deviation`
- `raw_mouth_corner_vertical_asym`

证据状态：

- 旧数据 `facesym_v1_all_images_no_gate_20260119`：患者级 `all + max` 口径 5/5 患病更高；`smile_or_teeth` 口径 5/5 患病更高。
- 新数据 `stroke_warning_app_rule_test_set_20260508`：`smile_teeth` role 口径 5/5 患病更高；患者级全 role `all + max` 只有 2/5 通过。

输入格式要求：

- 输入必须是可读静态人脸图片，`media_type=image`，并具有明确 `media_role`。
- 口部动作判断优先使用 `smile_teeth`、`smile`、`teeth` 或合并后的 `smile_or_teeth` 口径。
- MediaPipe 检测必须为 `detected`，且输出 478 个 `raw_landmarks`。
- `blendshapes` 必须包含 mouth 左右成对字段，至少包括 `mouthFrownLeft/Right` 和 `mouthLeft/Right`。
- 能完成面部中线拟合和双眼外角距离归一化；缺失关键点、缺失 blendshape、`no_face`、`failed`、严重遮挡或侧脸姿态过大时不得输出核心对称判断。

下一步交付：

- 在报告层输出 5 个核心特征值、role、方向、样本 ID 和数据集版本。
- 在可视化层展示关键点叠加图，标出面部中线、左右口角连线、唇中心到中线偏移。
- 在评分层保留 role-specific 解释，不能把新数据全 role 混合结果写成全局有效结论。

## M8: 产品化准备

状态：待人工标签、冻结测试集和验收口径确认后决策。

目标：决定是否进入 API、前端审核页面或部署环境设计。

交付候选：

- API 服务规范
- 前端审核/报告页面需求
- 部署、权限和审计要求
- 模型文件 checksum 与发布记录

## 当前推荐下一步

1. 将 5 个核心对称特征接入下一版评分/报告规则，并在输入校验中强制检查 478 raw landmarks 与 mouth blendshape 完整性。
2. 使用人工标注网站补齐 `metadata/16_v11_face_asymmetry_review_labels.csv`，形成面部不对称/质量复核标签。
3. 盘点 xlsx 与 media manifest 字段，确认 patient outcome 标签只能作为弱监督检查还是可作为阶段性验收标签。
4. 冻结测试集版本和 precision 阳性规则；当前患者级切分可作为候选。
5. 基于 20 阶段预测 CSV 复核 FP/FN 样本并形成评估计划。
