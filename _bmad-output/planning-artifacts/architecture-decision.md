---
title: "Architecture Decision: FaceSymAi MVP"
project: "FaceSymAi"
status: "updated"
created: "2026-05-18"
last_updated: "2026-05-28"
method: "BMAD-METHOD"
---

# Architecture Decision Document

## ADR-001: 基础运行环境

**决策**：项目基础环境使用 conda env `anti-spoofing_scc_175`。

**理由**：

- 环境已存在且可用。
- Python 版本为 3.9.25。
- 当前已验证 `mediapipe 0.10.35` 与 `cv2 4.13.0` 可导入。

**实现**：

- `scripts/activate_project_env.sh`
- `scripts/run_in_project_env.sh`
- `scripts/codex_facesymai.sh`
- `.vscode/settings.json`

## ADR-002: BMAD 规划结构

**决策**：使用 BMAD-METHOD v6.6.0，模块 `bmm`，Codex 技能安装到 `.agents/skills`。

**路径**：

- `_bmad`
- `_bmad-output/planning-artifacts`
- `_bmad-output/implementation-artifacts`
- `docs`

**理由**：

- 项目仍处在 MVP 形成阶段，需要持续同步上下文、PRD、架构和 Epic。
- BMAD 输出结构能降低后续 AI 代理实现时的上下文漂移。

## ADR-003: 数据处理优先级

**决策**：第一阶段先实现关键点级对称性分析 baseline 和 MediaPipe 检测基座，再进入冻结测试集 precision 评估，不直接训练临床模型。

**理由**：

- 已具备本地媒体数据和关键点检测能力，但标签口径、冻结测试集和临床验证尚未固化。
- 先完成可解释 baseline 能快速验证业务输出形态。
- 关键点级核心算法与检测器解耦，便于后续替换 MediaPipe 模型、InsightFace 或自研检测器。

## ADR-003A: 算法分层

**决策**：算法分为三层：

1. 采集/检测层：图片或视频帧到人脸关键点、姿态、blendshape、变换矩阵和质量指标。
2. 特征层：关键点到对称性、局部属性和质量门控。
3. 风险解释层：特征到预警辅助置信度、解释项和建议动作。

**当前实现**：

- 检测层：
  - `src/facesymai/landmarks/mediapipe_face_landmarker.py`
  - `src/facesymai/landmarks/mediapipe_face_mesh.py`
  - `scripts/detect_mediapipe_image.py`
  - `scripts/collect_v1_keypoint_dataset.py`
- 特征层：
  - `src/facesymai/features.py`
  - `src/facesymai/quality.py`
- 风险解释层：
  - `src/facesymai/risk.py`
  - `src/facesymai/cli.py`

## ADR-004: 原始数据保护

**决策**：原始 xlsx 只读，所有派生产物输出到后续约定目录。

**当前目录约定**：

```text
datasets/        # 已下载或派生的数据集、媒体、质量门控结果
models/          # 本地模型文件，例如 MediaPipe .task
reports/         # 数据理解、质量、评估报告
src/             # 项目代码
tests/           # 单元测试
docs/            # 算法、数据和运行说明
```

当前两个 xlsx 已在项目根目录，迁移或重命名前需用户确认。

## ADR-005: 医疗相关输出边界

**决策**：所有输出使用“风险提示/辅助分析”表述，不使用“诊断”表述。

**理由**：

- 文件名和数据集涉及脑卒中预警，属于高风险健康场景。
- 医疗结论需要数据、模型、临床验证和合规审查支撑。

## ADR-006: V1 检测基座使用 MediaPipe Face Landmarker

**决策**：V1 关键点检测基座使用 MediaPipe Tasks `Face Landmarker`，模型文件位于 `models/mediapipe/face_landmarker.task`。

**理由**：

- 技术方案已指定 MediaPipe 作为检测基座。
- 当前环境中的 `mediapipe 0.10.35` 支持 Tasks API，但不支持旧 `mp.solutions.face_mesh`。
- Face Landmarker 能输出 V1 所需的 3D landmarks、blendshape 和 facial transformation matrix。
- 使用 `.task` 模型文件更利于模型版本追踪和部署复现。

**实现**：

- `src/facesymai/landmarks/mediapipe_face_landmarker.py`
- `models/mediapipe/face_landmarker.task`
- `scripts/detect_mediapipe_image.py`
- `docs/algorithm/mediapipe-local-image-runtime.md`

## ADR-007: 保留旧 FaceMesh 适配器作为兼容 fallback

**决策**：保留 `MediaPipeFaceMeshDetector`，但当前环境默认不使用。

**理由**：

- 部分历史 MediaPipe 环境仍可能暴露 `mp.solutions.face_mesh`。
- 当前项目环境没有该 API，因此默认路径应是 Face Landmarker。
- 保留 fallback 可以降低后续迁移成本，但不得把它作为当前可运行基座。

## ADR-008: 下一阶段以评估闭环为主线

**决策**：下一阶段优先生成 V1 keypoint dataset、确认标签、冻结测试集和 precision 报告。

**理由**：

- 检测与 scoring 已跑通，继续堆功能前应先建立可复核的评估闭环。
- precision 是当前 PRD 验收口径，必须有样本级明细、阈值和模型版本支撑。

## ADR-009: 当前 V1 数据处理流程使用 by-name 患者数据集

**决策**：当前推荐数据处理流程以 `datasets/stroke_patient_outcome_by_name_20260119` 为输入，以 `front,smile,teeth` 静态图片为 V1 范围，输出到 `datasets/facesym_v1_by_name_20260119`。

**实现**：

- 脚本：`scripts/build_facesym_v1_dataset_from_by_name.py`
- 数据流程文档：`docs/datasets/facesym-v1-by-name-data-flow.md`
- 输出结果：`datasets/facesym_v1_by_name_20260119/metadata/*`
- 阶段报告：`datasets/facesym_v1_by_name_20260119/reports/*`
- 人脸特征点绘制：`datasets/facesym_v1_by_name_20260119/annotated/.../*.jpg`
- MediaPipe 输出 JSON：`datasets/facesym_v1_by_name_20260119/keypoints/.../*.json`

**阶段**：

1. manifest 筛选。
2. 质量门控。
3. MediaPipe Face Landmarker 检测和绘制。
4. 图片级/患者级对称性特征。
5. 患者级 train/val/test 分层切分。
6. 当前规则 baseline 技术评估。

**当前结果**：

- 505 个患者样本，1546 张 V1 图片。
- MediaPipe `detected` 1538、`no_face` 7、`failed` 1。
- 已生成 1538 张特征点绘制图。
- 已生成总体对称性评分、疑似异常侧，以及口部、眼部、眉部、鼻面中线、面部轮廓五类部件级属性。
- 特征层已前置坐标标准化：鼻梁/鼻尖/下巴中线拟合、轻微 roll 校正、双眼外角距离尺度归一化。
- 患者级切分为 train 353、val 75、test 77。
- 当前 test precision 为 `0.662338`，但标签是 patient outcome，不是直接面部不对称 ground truth。

**理由**：

- 该数据集已经按患者组织，天然支持患者级切分，避免图片级泄漏。
- `front,smile,teeth` 与 V1 静态图片人脸对称性目标最匹配。
- 每个阶段都有 CSV/JSON 结果和 Markdown 报告，便于人工复核和后续冻结。

## ADR-010: 全图片无质量门控对比组作为归因数据集

**决策**：保留 `datasets/facesym_v1_all_images_no_gate_20260119` 作为独立对比组，读取 by-name 数据集所有 `media_type=image` 图片，跳过 manifest role 筛选和质量门控。

**实现**：

- 脚本：`scripts/build_facesym_v1_all_images_no_gate_comparison.py`
- 输出：`datasets/facesym_v1_all_images_no_gate_20260119/metadata/*` 与 `reports/*`
- 当前规模：5195 张图片、505 个患者；MediaPipe `detected` 5005、`no_face` 189、`failed` 1。

**理由**：

- 该对比组能观察侧脸、舌像、闭眼、病历和辅助检查等非 V1 输入对 MediaPipe 检测、特征和误报的影响。
- 质量门控 skipped 必须作为显式阶段保留，便于和正式 V1 流程逐阶段对照。
- 该对比组只用于归因和规则探索，不作为正式 V1 验收流程。

## ADR-011: V1.1 使用 role-aware 弱监督特征与 HB proxy 技术代理分级

**决策**：在全图片对比组上构建 V1.1 role-aware 质量加权拟合，并在患者级输出 HB proxy I-VI 技术代理等级。

**实现**：

- V1.1 role-aware：`scripts/build_v11_role_aware_quality_weighted_fit.py`
- HB proxy 分级：`scripts/build_v11_hb_proxy_grading.py`
- Grade V+ 复核与对比：`scripts/extract_v11_grade_v_plus_nondisease_review.py`、`scripts/compare_v11_grade_v_plus_18_disease_nondisease.py`、`scripts/analyze_v11_grade_v_plus_generalization.py`
- 人工标签校准与标注网站：`scripts/calibrate_v11_hb_proxy_with_review_labels.py`、`scripts/serve_face_asymmetry_label_tool.py`、`tools/face_asymmetry_label_tool.html`

**当前结果**：

- V1.1 患病/不患病弱监督预测 test precision `0.690476`、recall `0.568627`、specificity `0.500000`。
- HB proxy grade 分布：Grade I 96、Grade II 102、Grade III 104、Grade IV 97、Grade V 68、Grade VI 37。
- Grade V+ 人脸不对称输出 105 例；test precision `0.727273`、specificity `0.884615`。

**理由**：

- V1.1 使用 MediaPipe 478 点区域/语义差异和 blendshape 左右差异，能比 25 点静态 baseline 提供更丰富的证据。
- HB proxy grade 只能表达当前数据分布下的技术代理等级，不能替代临床 House-Brackmann 分级。
- Grade V+ 主规则未因 18 对局部差异直接调整，避免把小样本非普适差异写入规则。

## ADR-012: 20 阶段作为 MediaPipe 全流程汇总层

**决策**：新增只读汇总层 `scripts/summarize_mediapipe_end_to_end_outputs.py`，整合 09/11/12/14 阶段产物，输出最大特征差异和患者级预测结果。

**实现**：

- 特征差异汇总：`metadata/20_mediapipe_end_to_end_feature_differences.csv`
- 患者预测汇总：`metadata/20_mediapipe_end_to_end_predictions.csv`
- JSON 摘要：`metadata/20_mediapipe_end_to_end_summary.json`
- 报告：`reports/20_mediapipe_end_to_end_summary.md`

**理由**：

- 09/11/12/14 阶段报告各自完整，但不利于一次性交付“最大差异项 + 预测结果”。
- 20 阶段不改变算法和阈值，只汇总既有产物，降低重复解释和人工拷贝错误。
- 报告默认排除 pose、matrix、distance、scale 和 `*_centroid_z_asym` 等控制变量，避免把采集姿态误写成面部不对称主证据。

## ADR-013: 核心人脸对称判断使用 5 个 MediaPipe 派生特征

**决策**：当前人脸是否对称的核心关键点判断指定为 5 个 MediaPipe 派生特征：

```text
bsdiff_mouthFrown_abs
raw_all_mesh_region_point_spread_asym
bsdiff_mouth_abs
raw_lip_midline_deviation
raw_mouth_corner_vertical_asym
```

**证据**：

- 旧数据 `datasets/facesym_v1_all_images_no_gate_20260119`：患者级 `all + max` 口径下 5/5 患病均值高于不患病均值；`smile_or_teeth` 合并口径下 5/5 患病更高。
- 新数据 `datasets/stroke_warning_app_rule_test_set_20260508`：`smile_teeth` role 下 5/5 患病均值高于不患病均值；患者级 `all + max` 只有 2/5 通过，因此该规则必须保留 role-specific 解释，不应把全 role 混合口径直接写成全局结论。

**特征含义**：

- `bsdiff_mouthFrown_abs`：口角下拉/口部下垂 blendshape 左右差。
- `raw_all_mesh_region_point_spread_asym`：478 点全脸左右点云离散程度差。
- `bsdiff_mouth_abs`：口部横向/侧向 blendshape 左右差。
- `raw_lip_midline_deviation`：唇中心偏离面部中线程度。
- `raw_mouth_corner_vertical_asym`：左右口角垂直高度差。

**输入约束**：

- 只在 MediaPipe Face Landmarker `detection_status=detected` 的静态人脸图片上计算。
- 检测 JSON 必须包含 478 个 `raw_landmarks`，mouth 相关 blendshape 必须包含 `mouthFrownLeft/Right` 和 `mouthLeft/Right`。
- 必须能基于鼻梁/鼻尖/下巴拟合面部中线，并基于双眼外角距离完成尺度归一化。
- `no_face`、`failed`、缺失关键点、缺失 mouth blendshape、严重遮挡、侧脸姿态过大或无法确认主脸时，不得输出核心对称判断，只能输出不可评分/需复核。

**展示要求**：

- 报告或 UI 应优先展示 MediaPipe 关键点叠加图，至少标出面部中线、左右口角连线、唇中心到中线偏移和 478 点覆盖。
- 输出必须包含 role、样本 ID、5 个特征值、特征方向和对应数据集版本。

**限制**：

- 这 5 个特征是当前两批数据下的弱监督核心证据，不是临床面瘫真值或 House-Brackmann 真值。
- 对外只能表述为“人脸对称性辅助证据/预警参考”，不得表述为医学诊断。
