---
project_name: "FaceSymAi"
user_name: "scc"
date: "2026-05-28"
sections_completed:
  - "technology_stack"
  - "current_state"
  - "mediapipe_runtime"
  - "current_data_processing_flow"
  - "all_images_no_gate_comparison_flow"
  - "v1_calculation_technical_doc"
  - "mediapipe_end_to_end_summary"
  - "core_symmetry_evidence_features"
  - "tmp_output_policy"
  - "critical_rules"
  - "next_steps"
existing_patterns_found: 11
---

# Project Context for AI Agents

本文件记录 FaceSymAi 项目中 AI 代理必须遵守的实现规则和当前进度。目标是减少环境漂移、会话串扰、过期假设和医疗场景表述风险。

## Technology Stack & Versions

- Python 运行环境：conda env `anti-spoofing_scc_175`
- Python 解释器：`/home/scc/anaconda3/envs/anti-spoofing_scc_175/bin/python`
- Python 版本：3.9.25
- MediaPipe：`mediapipe 0.10.35`
- OpenCV：`cv2 4.13.0`
- BMAD-METHOD：v6.6.0，安装目录 `_bmad`
- BMAD 输出目录：`_bmad-output`
- Codex 项目会话目录：`.codex-home`
- 轻量交接会话目录：`.codex-local`

## Current Project State

- 项目已形成 Python 包结构：`src/facesymai/`。
- 已实现关键点级人脸对称性 baseline：
  - `src/facesymai/schemas.py`
  - `src/facesymai/geometry.py`
  - `src/facesymai/features.py`
  - `src/facesymai/risk.py`
  - `src/facesymai/cli.py`
- 已实现输入管理、质量门控和数据集工具：
  - `src/facesymai/input_management.py`
  - `src/facesymai/quality.py`
  - `src/facesymai/dataset_v1.py`
- 已接入 MediaPipe Tasks `Face Landmarker` 作为 V1 检测基座：
  - `src/facesymai/landmarks/mediapipe_face_landmarker.py`
  - `models/mediapipe/face_landmarker.task`
  - `scripts/detect_mediapipe_image.py`
  - `scripts/collect_v1_keypoint_dataset.py`
- 保留旧 `MediaPipeFaceMeshDetector` 作为兼容 fallback，但当前环境不支持 `mp.solutions.face_mesh`，默认不要使用旧 FaceMesh 路径。
- 当前目录包含两个业务输入 xlsx：
  - `脑卒中数据采集-审核导出-20260119.xlsx`
  - `脑卒中预警报告老来健康app线上_2026-05-08.xlsx`
- 当前已有本地数据集和派生产物目录：
  - `datasets/stroke_media_dataset_20260119`
  - `datasets/stroke_warning_app_media_dataset_20260508`
  - `datasets/stroke_warning_app_rule_test_set_20260508`
  - `datasets/stroke_patient_outcome_quality_gated_20260119`
  - `datasets/stroke_patient_outcome_by_name_20260119`
  - `datasets/facesym_v1_by_name_20260119`
  - `datasets/facesym_v1_all_images_no_gate_20260119`
- 当前脑卒中预警 App 规则测试集已固化为脚本：
  - `scripts/build_stroke_warning_rule_test_set.py`
  - 输入：`脑卒中预警报告老来健康app线上_2026-05-08.xlsx`、`datasets/stroke_warning_app_media_dataset_20260508`
  - 输出：`datasets/stroke_warning_app_rule_test_set_20260508`
  - 规则：同一条记录同时满足 `风险等级=紧急风险`、曾经得过中风、家人得过脑卒中时纳入 `患病`；无阳性记录且至少一条 `低风险` 全指标正常记录纳入 `不患病`；同一患者阳性优先。
  - 当前结果：源记录 612、源患者 487、纳入患者 101（`患病` 42、`不患病` 59）、纳入记录 109、媒体 658（图片 549、视频 109）、排除患者 386。
  - 输出文件：`metadata/patient_samples.csv`、`metadata/rule_labeled_records.csv`、`metadata/media_index.csv`、`metadata/excluded_records.csv`、`metadata/summary.json`、`reports/01_rule_test_set.md`。
- 当前推荐数据流程已固化为脚本：
  - `scripts/build_facesym_v1_dataset_from_by_name.py`
  - 输入：`datasets/stroke_patient_outcome_by_name_20260119`
  - 输出：`datasets/facesym_v1_by_name_20260119`
- 当前全图片无筛选/无质量门控对比组已固化为脚本：
  - `scripts/build_facesym_v1_all_images_no_gate_comparison.py`
  - 输入：`datasets/stroke_patient_outcome_by_name_20260119`
  - 输出：`datasets/facesym_v1_all_images_no_gate_20260119`
- 当前 V1.1 HB proxy 分级已固化为脚本：
  - `scripts/build_v11_role_aware_quality_weighted_fit.py`
  - `scripts/build_v11_hb_proxy_grading.py`
  - 输入：`datasets/facesym_v1_all_images_no_gate_20260119`
  - 输出：`metadata/11_v11_role_aware_predictions.csv`、`metadata/12_v11_hb_proxy_patient_grades.csv`、`metadata/12_v11_hb_proxy_component_scores.csv`、`metadata/12_v11_hb_proxy_mediapipe_grade_differences.csv`、`metadata/12_v11_hb_proxy_grade_v_plus_asymmetry_cases.csv`、`metadata/12_v11_hb_proxy_grade_evaluation.json`、`reports/14_v11_hb_proxy_grading_results.md`
- 当前 Grade V+ 不患病专项复核已固化为脚本：
  - `scripts/extract_v11_grade_v_plus_nondisease_review.py`
  - 输入：`metadata/12_v11_hb_proxy_grade_v_plus_asymmetry_cases.csv`、`metadata/11_v11_role_aware_image_scores.csv`、`metadata/03_keypoints.csv`
  - 输出：`metadata/13_v11_hb_proxy_grade_v_plus_nondisease_cases.csv`、`metadata/13_v11_hb_proxy_grade_v_plus_nondisease_summary.json`、`reports/15_v11_grade_v_plus_nondisease_false_positive_review.md`
- 当前 Grade V+ 患病/不患病 18 对照已固化为脚本：
  - `scripts/compare_v11_grade_v_plus_18_disease_nondisease.py`
  - 输入：12/13 阶段 Grade V+ 结果、`metadata/11_v11_role_aware_image_scores.csv`、`metadata/03_keypoints.csv`
  - 输出：`metadata/14_v11_hb_proxy_grade_v_plus_18_pair_comparison.csv`、`metadata/14_v11_hb_proxy_grade_v_plus_18_pair_comparison_summary.json`、`reports/16_v11_grade_v_plus_18_disease_nondisease_comparison.md`
- 当前 Grade V+ 差异普适性与规则调整验证已固化为脚本：
  - `scripts/analyze_v11_grade_v_plus_generalization.py`
  - 输入：`metadata/12_v11_hb_proxy_patient_grades.csv`、`metadata/14_v11_hb_proxy_grade_v_plus_18_pair_comparison_summary.json`
  - 输出：`metadata/15_v11_grade_v_plus_generalization_component_effects.csv`、`metadata/15_v11_grade_v_plus_rule_adjustment_candidates.csv`、`metadata/15_v11_grade_v_plus_generalization_summary.json`、`reports/17_v11_grade_v_plus_generalization_and_rule_adjustment.md`
- 当前人工面部不对称/质量复核标签校准已固化为脚本：
  - `scripts/calibrate_v11_hb_proxy_with_review_labels.py`
  - 输入：`metadata/12_v11_hb_proxy_patient_grades.csv`、`metadata/03_keypoints.csv`、可选 `metadata/16_v11_face_asymmetry_review_labels.csv`
  - 输出：`metadata/16_v11_face_asymmetry_review_label_template.csv`、`metadata/16_v11_face_asymmetry_calibrated_predictions.csv`、`metadata/16_v11_face_asymmetry_calibration_summary.json`、`reports/18_v11_face_asymmetry_review_label_calibration.md`；标签足够时额外输出 `metadata/16_v11_face_asymmetry_calibration_config.json`
- 当前人工面部对称性标注网站已固化：
  - 服务入口：`scripts/serve_face_asymmetry_label_tool.py`
  - 页面：`tools/face_asymmetry_label_tool.html`
  - 输入：16 阶段复核模板、已有 `metadata/16_v11_face_asymmetry_review_labels.csv`、`annotated/.../*.jpg` 特征点图
  - 输出：直接写入 `metadata/16_v11_face_asymmetry_review_labels.csv`，并可触发 16 阶段阈值/权重校准
  - 远程访问：支持 `--host 0.0.0.0` 绑定局域网/外网入口，支持 `--access-token` 保护页面 API 和图片访问
- 当前 MediaPipe 全流程特征差异与预测汇总已固化为脚本：
  - `scripts/summarize_mediapipe_end_to_end_outputs.py`
  - 输入：`metadata/09_mediapipe_feature_differences.csv`、`metadata/11_v11_role_aware_predictions.csv`、`metadata/12_v11_hb_proxy_patient_grades.csv`、`metadata/12_v11_hb_proxy_mediapipe_grade_differences.csv`、`metadata/14_v11_hb_proxy_grade_v_plus_18_pair_comparison_summary.json`
  - 输出：`metadata/20_mediapipe_end_to_end_feature_differences.csv`、`metadata/20_mediapipe_end_to_end_predictions.csv`、`metadata/20_mediapipe_end_to_end_summary.json`、`reports/20_mediapipe_end_to_end_summary.md`
- MediaPipe 人脸关键点检测已整理为可复用模块和离线 SDK：`modules/mediapipe_face_keypoint_detector`。该模块自带 `models/face_landmarker.task`，可直接复制整个文件夹到其他机器离线使用；支持 Python SDK `FaceKeypointDetectorSDK`、命令行 `run_detect.py`、HTTP API `serve_api.py` 三种调用方式。模块只负责静态图片人脸关键点检测，输出 478 raw landmarks、语义关键点、52 blendshapes、facial transformation matrix 和可选关键点叠加图；不包含质量门控、人脸对称性判断或患病结论。离线 SDK 文档为 `modules/mediapipe_face_keypoint_detector/SDK_USAGE.md`；复制目录 smoke test 输出位于 `tmp/mediapipe_face_keypoint_detector_offline_copy_smoke/result.json`。
- 当前已基于两批数据指定人脸是否对称的 5 个 MediaPipe 核心判断特征：`bsdiff_mouthFrown_abs`、`raw_all_mesh_region_point_spread_asym`、`bsdiff_mouth_abs`、`raw_lip_midline_deviation`、`raw_mouth_corner_vertical_asym`。这些特征在旧数据 `facesym_v1_all_images_no_gate_20260119` 的患者级 all+max 口径上 5/5 表现为患病更高，在新数据 `stroke_warning_app_rule_test_set_20260508` 的 `smile_teeth` role 上 5/5 表现为患病更高；新数据患者级 all+max 只有 2/5 通过，因此后续应优先按 role-specific 口径使用，尤其是 `smile_teeth`/`smile_or_teeth`。
- 旧数据全量图片阈值外推验证已固化：`scripts/build_old_all_core_threshold_rule_test_predictions.py` 使用旧数据 train+val+test 全部 detected 图片拟合五个核心特征阈值，在 `stroke_warning_app_rule_test_set_20260508` 测试；主报告 `reports/52_old_all_core_threshold_rule_test.md`。当前图片级规则为 `triggered_core_feature_count >= 2`，患者级规则为 `max_triggered_core_feature_count >= 4`；新规则测试集患者级 TP 11、FP 6、TN 53、FN 31，precision `0.647059`、recall `0.261905`、specificity `0.898305`，不患病患者误判 6/59。`smile_teeth` 对照报告为 `reports/52_old_all_core_threshold_rule_test_smile_teeth.md`，不患病患者误判 3/58。
- 两批数据联合寻找患病/不患病判断特征已固化：`scripts/find_combined_disease_feature_candidates.py`，输出 `datasets/combined_disease_feature_candidates_20260529`，主报告 `reports/60_combined_disease_feature_candidates.md`。该口径先按患者聚合，再筛选旧数据和新数据方向一致且两边 directional AUC 均高于随机的共同 MediaPipe 特征；屏蔽姿态、位移、尺度、距离、开口宽度等采集条件字段。当前共同候选特征 121 个，推荐级特征组合 62 个，去重后推荐特征 21 个，均为患病更高；最优先特征包括 `raw_lip_midline_deviation`、`raw_eyebrow_region_height_asym`、`raw_iris_region_point_spread_asym`、`bsdiff_browDown_abs`、`bsdiff_mouth_abs`、`bsdiff_mouthFrown_abs`。
- 十个联合特征患者级患病倾向规则已固化：`scripts/build_top10_patient_disease_rule.py`，输出同目录 `datasets/combined_disease_feature_candidates_20260529`，主报告 `reports/61_top10_patient_disease_rule.md`。规则读取 60 阶段去重推荐前 10 个特征，分别确定阈值；同一患者 10 个特征中至少 5 个达到或超过阈值时输出 `患病倾向较高`，并在 `metadata/61_top10_patient_disease_rule_patient_predictions.csv` 和 `metadata/61_top10_patient_disease_rule_patient_feature_attributions.csv` 输出触发原因。当前 combined precision `0.736181`、recall `0.775132`、specificity `0.537445`；新数据 precision `0.648649`、recall `0.571429`、specificity `0.779661`。规范输入需要患者级静态人脸图片集，必需 `smile_teeth` 或旧 V1 `smile+teeth`，推荐 `front_contour/front + smile_teeth/smile,teeth + eyes_right`，且必须能输出 MediaPipe 478 landmarks、52 blendshapes 和 transformation matrix。
- 21 个去重推荐特征稳定性加权患病判断规则已固化：`scripts/build_stable_weighted_feature_disease_rule.py`，输出同目录 `datasets/combined_disease_feature_candidates_20260529`，主报告 `reports/62_stable_weighted_feature_disease_rule.md`。规则同时考虑患者更高、非患者不过阈值、旧/新跨数据 AUC、所有图片 IQR/robust CV/患者中位数差距波动性和图片数；稳定且非患者误判少的特征权重更高，波动大或非患者中也常升高的特征权重更低。当前加权得分阈值为 `weighted_disease_score >= 0.612826` 输出 `患病倾向较高`；combined precision `0.777385`、recall `0.582011`、specificity `0.722467`，新数据 precision `0.692308`、recall `0.214286`、specificity `0.932203`。当前默认推荐采用 62 作为高置信规则，因为它在 combined precision、combined specificity 和 new specificity 上优于 61/63；逐患者判断原因位于 `metadata/62_stable_weighted_feature_disease_rule_patient_predictions.csv`，逐特征归因位于 `metadata/62_stable_weighted_feature_disease_rule_patient_feature_contributions.csv`。
- 62 规则人脸不对称分析服务已封装：`modules/facial_asymmetry_service`。命令行入口为 `scripts/run_in_project_env.sh python modules/facial_asymmetry_service/run_analyze.py ...`；网页/API 入口为 `scripts/run_in_project_env.sh python modules/facial_asymmetry_service/serve_web.py --port 8790 --access-token <token>`，默认绑定 `0.0.0.0` 允许外部网络访问，页面文件为 `modules/facial_asymmetry_service/web_upload.html`，外部接口为 `POST /api/analyze` 和 `GET /api/input-spec`。调用文档为 `modules/facial_asymmetry_service/CALLING_GUIDE.md`，覆盖网页上传、curl、Python requests 和 JavaScript fetch。网页/API 输出为用户版结果：保留 `face_asymmetry_confidence` 和 `face_asymmetry_output`，原因描述使用双侧口角夹角/牵拉幅度差、唇部中线偏移、双侧眼裂高度或眼周形态差、眉部高度或动作幅度差、面部轮廓左右差等用户可读观察项，不默认展示技术特征名、阈值或权重。网页/API 只校验最少 2 张、最多 10 张，不强制限制动作；露齿微笑/微笑/示齿、正脸/面部轮廓、眼周/额眉动作每类都支持多张上传并按多图聚合规则处理。smoke test 位于 `tmp/facial_asymmetry_service_rule62_smoke`，Web API smoke 输出位于 `tmp/facial_asymmetry_service_web_api_smoke.json`。
- role-specific、阈值稳定性筛选、非患者参考分布阈值三项优化已固化：`scripts/build_optimized_threshold_feature_disease_rule.py`，输出同目录 `datasets/combined_disease_feature_candidates_20260529`，主报告 `reports/63_optimized_threshold_feature_disease_rule.md`。该规则对 21 个特征搜索旧/新方向一致且患者更高的 role_scope+aggregation，单特征阈值取 `max(Youden阈值, old/new/combined 非患者 P85)`，并用 120 次 bootstrap 阈值 IQR/患者中位数差距做稳定性降权；最终主阈值在 old/new specificity 均不低于 `0.50` 的候选中最大化 old/new Youden J 平均值。当前主阈值为 `weighted_disease_score >= 0.102162`；combined precision `0.719626`、recall `0.611111`、specificity `0.603524`，old precision `0.725424`、recall `0.636905`、specificity `0.517857`，new precision `0.653846`、recall `0.404762`、specificity `0.847458`。更宽松/严格的阈值备选位于 `metadata/63_optimized_threshold_feature_disease_rule_score_threshold_policies.csv`。
- 当前规划文档已更新到 2026-05-28 进度：
  - `_bmad-output/planning-artifacts/product-brief.md`
  - `_bmad-output/planning-artifacts/prd.md`
  - `_bmad-output/planning-artifacts/architecture-decision.md`
  - `_bmad-output/planning-artifacts/implementation-roadmap.md`
  - `_bmad-output/planning-artifacts/epics-and-backlog.md`
  - `_bmad-output/planning-artifacts/00-bmad-input-summary.md`
- 当前 V1 计算过程、特征公式、权重、阈值和 precision 来源已整理到：
  - `docs/algorithm/facesym-v1-calculation-technical-document.md`

## MediaPipe Runtime Baseline

- 技术方案已指定 MediaPipe 作为 V1 检测基座。
- 当前环境中的 `mediapipe 0.10.35` 支持 Tasks API，不支持旧 `mp.solutions.face_mesh`。
- V1 默认使用 MediaPipe Tasks `Face Landmarker`。
- 模型文件位置：`models/mediapipe/face_landmarker.task`
- 单图检测命令示例：

```bash
scripts/run_in_project_env.sh python scripts/detect_mediapipe_image.py \
  path/to/local-image.jpg \
  --output tmp/facesymai-mediapipe-result.json \
  --pretty \
  --include-analysis
```

- 已验证单图 smoke test：
  - `status = detected`
  - `detector = mediapipe_face_landmarker`
  - `raw_landmarks = 478`
  - `blendshapes = 52`
  - `facial_transformation_matrixes = 1`
- 已验证批量采集 smoke test：

```bash
scripts/run_in_project_env.sh python scripts/collect_v1_keypoint_dataset.py \
  --limit 1 \
  --roles front \
  --output tmp/facesymai-v1-keypoint-smoke
```

## Current Data Processing Flow

当前 V1 数据处理流程以“按患者组织的 by-name 数据集”为正式输入，目标是从 `front,smile,teeth` 三类静态图片生成可复核的人脸对称性分析数据集。命令：

```bash
scripts/run_in_project_env.sh python scripts/build_facesym_v1_dataset_from_by_name.py \
  --output datasets/facesym_v1_by_name_20260119 \
  --roles front,smile,teeth
```

正式输出目录：`datasets/facesym_v1_by_name_20260119`

阶段产物：

1. `01_manifest`：筛选 V1 静态图片，输出 `metadata/01_manifest.csv`、`metadata/01_manifest_summary.json`、`reports/01_manifest.md`。报告中必须列出入选图片明细。
2. `02_quality_gate`：运行当前质量门控，输出 `metadata/02_quality_gate.csv`、`metadata/02_quarantined_images.csv`、`metadata/02_quality_gate_summary.json`、`reports/02_quality_gate.md`。报告中必须列出被隔离图片明细。
3. `03_keypoints`：运行 MediaPipe Face Landmarker，输出 `metadata/03_keypoints.csv`、`metadata/03_keypoints_summary.json`、`reports/03_keypoints.md`、`keypoints/.../*.json` 和 `annotated/.../*.jpg`。报告中必须列出每张图片的检测状态和输出路径。
4. `04_features`：生成图片级与患者级对称性特征，先执行坐标标准化（鼻梁/鼻尖/下巴中线拟合、轻微 roll 校正、双眼外角距离尺度归一化），再输出 `metadata/04_image_features.csv`、`metadata/04_patient_features.csv`、`metadata/04_features_summary.json`、`reports/04_features.md`。报告中必须列出图片级和患者级特征摘要明细。
5. `05_patient_splits`：按患者维度分层切分 train/val/test，输出 `metadata/05_patient_splits.csv`、`metadata/05_patient_splits_summary.json`、`reports/05_patient_splits.md`。报告中必须列出每个患者的 split。
6. `06_baseline_evaluation`：用当前规则 baseline 做技术信号检查，输出 `metadata/06_baseline_predictions.csv`、`metadata/06_baseline_evaluation.json`、`reports/06_baseline_evaluation.md`。报告中必须列出每个患者的预测、阈值和 TP/FP/TN/FN 归类。

本轮正式结果：

- 输入规模：505 个患者样本，1546 张 V1 图片；患者标签为 `患病` 336、`不患病` 169。
- 质量门控：`pass` 938、`review` 15、`reject` 593；`accepted_for_scoring=true` 953。
- MediaPipe 检测：`detected` 1538、`no_face` 7、`failed` 1；成功样本均输出 478 个 raw landmarks 和 52 个 blendshapes；已生成 1538 张人脸特征点绘制图。
- 特征生成：1538 张图片可生成静态集合特征，505 条患者级特征，无特征计算错误；输出 `overall_symmetry_score`、`overall_asymmetry_severity`、`affected_side`，以及口部、眼部、眉部、鼻面中线、面部轮廓五类部件级 `score/symmetry_score/side/confidence`。
- 患者级切分：train 353、val 75、test 77，按 `患病/不患病` 分层，避免图片级泄漏。
- 当前规则 baseline：验证集阈值 `0.277158`；test precision `0.662338`、recall `1.000000`、specificity `0.000000`。其中 test precision 来自 `TP=51`、`FP=26`，即 `51/(51+26)=0.6623376623376623`。

解释限制：当前标签是患者 outcome 标签（`患病`/`不患病`），不是人工标注的面部不对称 ground truth。上述 precision/recall 只能作为技术信号检查，不能表述为医学诊断性能。

当前计算文档：`docs/algorithm/facesym-v1-calculation-technical-document.md`。该文档固化了 MediaPipe 语义点映射、坐标标准化、中线拟合、尺度归一化、11 个静态特征公式、五类部件级属性、总体对称性评分、预警辅助分、患者级 max-role 聚合、验证集阈值选择和 precision 计算链路。

## All-Images No-Gate Comparison Flow

对比组目标：不做 `front,smile,teeth` manifest 筛选，不运行质量门控，读取 by-name 数据集中每个患者的所有 `media_type=image` 图片，继续执行 MediaPipe Face Landmarker 检测和绘制、图片级/患者级对称性特征、患者级 train/val/test 分层切分和当前规则 baseline 技术评估。

命令：

```bash
scripts/run_in_project_env.sh python scripts/build_facesym_v1_all_images_no_gate_comparison.py \
  --output datasets/facesym_v1_all_images_no_gate_20260119
```

阶段产物：

1. `01_all_images`：输出 `metadata/01_all_images.csv`、`metadata/01_all_images_summary.json`、`reports/01_all_images.md`。
2. `02_quality_gate_skipped`：输出 `metadata/02_quality_gate_skipped.csv`、`metadata/02_quality_gate_skipped_summary.json`、`reports/02_quality_gate_skipped.md`，明确质量门控 skipped、排除数 0。
3. `03_keypoints`：输出 `metadata/03_keypoints.csv`、`metadata/03_keypoints_summary.json`、`keypoints/.../*.json`、`annotated/.../*.jpg`。
4. `04_features`：输出 `metadata/04_image_features.csv`、`metadata/04_patient_features.csv`、`metadata/04_features_summary.json`、`reports/04_features.md`。患者级分数为 `max_image_advisory_confidence_no_quality_gate`；同一患者同一 role 多图不会覆盖，role-best 按最高 `advisory_confidence` 记录。
5. `05_patient_splits`：输出患者级分层切分，seed `20260520`。
6. `06_baseline_evaluation`：输出对比组 baseline 指标和样本级预测明细。

当前对比组结果：

- 图片：5195 张，患者：505；每患者 7 到 20 张图片。
- 图片角色：`front/smile/teeth` 加 `eyes_closed/forehead_wrinkle/frown/left_profile/right_profile/tongue_bottom/tongue_surface/auxiliary_exam_image/medical_record`。
- 质量门控：skipped；排除图片 0。
- MediaPipe：`detected` 5005、`no_face` 189、`failed` 1；已写入 5005 张 landmark overlay。
- 特征：5005 张 feature-ready，505 条患者级特征，无特征计算错误。
- 切分：train 353、val 75、test 77。
- baseline：验证集阈值 `0.555802`；test precision `0.662338`、recall `1.000000`、specificity `0.000000`；test confusion matrix `TP=51, FP=26, TN=0, FN=0`。

解释限制：对比组包含侧脸、舌像、闭眼、病历等非 V1 目标输入，且不运行质量门控。它用于对照、误检归因和门控价值评估，不作为正式 V1 验收流程，也不得描述为医学诊断性能。

## V1.1 HB Proxy Grading Flow

HB proxy 分级目标：在当前 V1.1 role-aware 质量加权拟合结果上，将患者级输出从单一二分类拟合分数扩展为 House-Brackmann 风格 I-VI 技术代理分级，并输出静息、闭眼、眉额、微笑/口部、整体不对称、无运动风险和质量可靠性组件。

命令：

```bash
scripts/run_in_project_env.sh python scripts/build_v11_hb_proxy_grading.py \
  --dataset datasets/facesym_v1_all_images_no_gate_20260119
```

阶段产物：

- `metadata/12_v11_hb_proxy_patient_grades.csv`
- `metadata/12_v11_hb_proxy_component_scores.csv`
- `metadata/12_v11_hb_proxy_mediapipe_grade_differences.csv`
- `metadata/12_v11_hb_proxy_grade_v_plus_asymmetry_cases.csv`
- `metadata/12_v11_hb_proxy_manual_review_candidates.csv`
- `metadata/12_v11_hb_proxy_grade_evaluation.json`
- `reports/14_v11_hb_proxy_grading_results.md`

当前结果：

- 患者数 505，可评分 504。
- 患者级输出已指定 HB 风格等级语义字段：`hb_resting_symmetry_label`、`hb_dynamic_symmetry_label`、`hb_eye_closure_label`、`hb_mouth_brow_motion_label`、`hb_grade_descriptor`。
- grade 分布：Grade I 96、Grade II 102、Grade III 104、Grade IV 97、Grade V 68、Grade VI 37。
- Grade V+ 人脸不对称输出规则：`hb_proxy_grade_num >= 5` 时 `face_asymmetry_output=人脸不对称`，原因写入 `face_asymmetry_reason`；当前输出 105 条，其中患病 87、不患病 18。
- Grade V+ 不患病专项复核：当前 18 例，按 split 为 test 3、train 11、val 4；报告展示每例 6 个核心 role 的 MediaPipe 特征点图，共 108 张。
- Grade V+ 患病/不患病 18 对照：18 例不患病对照全部按 same split + same grade 匹配到 18 例患病样本；报告展示 216 张核心 role 特征点图。
- Grade V+ 差异普适性验证：18 对中的多数关键差异不是可直接用于调规则的普适差异；全量样本存在较稳定的患病组更高不对称信号，但在 Grade V+ 子集中只有 HB proxy 总分和无运动风险相对稳定，候选规则没有通过测试集验收，因此未调整当前 Grade V+ 主规则。
- 人工面部不对称/质量复核标签校准：当前生成 505 行复核模板和校准预测占位；`metadata/16_v11_face_asymmetry_review_labels.csv` 尚未填充，有效标签数 0，状态为 `insufficient_labels`，不会重新校准阈值/权重或生成可接入主流程的 calibration config。
- 人工标注网站：页面按病例展示 6 个核心 role 的 MediaPipe 特征点图、组件分数、HB proxy 证据和标注控件；保存接口直接合并写入 `metadata/16_v11_face_asymmetry_review_labels.csv`，支持质量排除和页面内重新校准。局域网/外网标注使用 `--host 0.0.0.0 --access-token <token>`，页面会自动携带 token 调用 API 和图片资源。
- patient outcome 代理单调性检查：患病平均 grade `3.348214`，不患病平均 grade `2.601190`。
- 派生 test 指标：
  - Grade II+：precision `0.701493`、recall `0.921569`、specificity `0.230769`。
  - Grade III+：precision `0.700000`、recall `0.686275`、specificity `0.423077`。
  - Grade IV+：precision `0.709677`、recall `0.431373`、specificity `0.653846`。
  - Grade V+ 人脸不对称：precision `0.727273`、recall `0.156863`、specificity `0.884615`。
- MediaPipe 等级差异输出 1008 行，其中全核心 role 144 行；包含 35 个 `mediapipe_478_all_landmarks` 全 478 点统计差异、252 个区域/语义 landmark 差异、378 个左右 blendshape 差异、343 个表情 blendshape 差异。
- 全核心 role 高区分示例：`raw_face_oval_region_centroid_y_asym`、`raw_iris_region_centroid_y_asym`、`raw_lip_region_centroid_y_asym`、`raw_eye_region_centroid_y_asym`、`raw_mouth_corner_vertical_asym`、`raw_all_mesh_region_centroid_y_asym`。
- 人工复核候选 195 条。

## MediaPipe End-to-End Summary Flow

当前已按 `docs/algorithm/mediapipe-pair-and-feature-difference-processing.md` 跑通并汇总 MediaPipe 全流程：

```bash
scripts/run_in_project_env.sh python scripts/build_facesym_v1_all_images_no_gate_comparison.py \
  --output datasets/facesym_v1_all_images_no_gate_20260119

scripts/run_in_project_env.sh python scripts/analyze_v1_mediapipe_full_feature_differences.py \
  --dataset datasets/facesym_v1_all_images_no_gate_20260119

scripts/run_in_project_env.sh python scripts/build_v11_role_aware_quality_weighted_fit.py \
  --dataset datasets/facesym_v1_all_images_no_gate_20260119

scripts/run_in_project_env.sh python scripts/build_v11_hb_proxy_grading.py \
  --dataset datasets/facesym_v1_all_images_no_gate_20260119

scripts/run_in_project_env.sh python scripts/compare_v11_grade_v_plus_18_disease_nondisease.py \
  --dataset datasets/facesym_v1_all_images_no_gate_20260119

scripts/run_in_project_env.sh python scripts/summarize_mediapipe_end_to_end_outputs.py \
  --dataset datasets/facesym_v1_all_images_no_gate_20260119
```

当前 20 阶段结果：

- 特征差异汇总：`metadata/20_mediapipe_end_to_end_feature_differences.csv`，108 行数据，包含患病/不患病主证据差异、预测模型权重最高特征、HB proxy Grade I-VI 最大差异。
- 患者预测汇总：`metadata/20_mediapipe_end_to_end_predictions.csv`，504 行可评分患者预测，包含 V1.1 预测标签、HB proxy grade、Grade V+ 人脸不对称输出、组件分数和 top features。
- JSON 摘要：`metadata/20_mediapipe_end_to_end_summary.json`。
- Markdown 报告：`reports/20_mediapipe_end_to_end_summary.md`。
- V1.1 患病/不患病弱监督预测 test 指标：precision `0.690476`、recall `0.568627`、specificity `0.500000`、TP `29`、FP `13`、TN `13`、FN `22`。
- Grade V+ 人脸不对称输出仍为 105 例，其中患病 87、不患病 18；test precision `0.727273`、recall `0.156863`、specificity `0.884615`。
- 患病/不患病主证据差异中，患病更高项包括 `bsdiff_mouthFrown_abs`、`raw_all_mesh_region_point_spread_asym`、`bsdiff_mouth_abs`、`raw_lip_midline_deviation`、`raw_mouth_corner_vertical_asym`；不患病更高项包括 `bsdiff_mouthSmile_abs`。
- 预测模型权重最高特征包括 `raw_lip_midline_deviation`、`raw_eyebrow_region_height_asym`、`raw_face_oval_region_centroid_y_asym`、`bsdiff_mouthFrown_abs`。
- HB proxy Grade I-VI 差异最大项包括 `raw_face_oval_region_centroid_y_asym`、`raw_iris_region_centroid_y_asym`、`raw_lip_region_centroid_y_asym`、`raw_eye_region_centroid_y_asym`、`raw_mouth_corner_vertical_asym`。

解释限制：HB proxy grade 是 patient outcome 弱关联和 train+val 分位数阈值下的技术代理等级，不是临床 House-Brackmann 诊断。当前没有人工 HB 标签，也没有已填充的人工面部不对称/质量复核标签，不能报告 weighted kappa、ordinal MAE、临床分级准确率或人工不对称标签下的最终准确率。

## Core Symmetry Evidence Features

当前人脸是否对称的核心关键点判断指定为以下 5 个 MediaPipe 派生特征：

| feature | 来源 | 对称性含义 |
| --- | --- | --- |
| `bsdiff_mouthFrown_abs` | `mouthFrownLeft/Right` blendshape 绝对差 | 口角下拉/口部下垂左右动作差 |
| `raw_all_mesh_region_point_spread_asym` | 478 raw landmarks 按面部中线分左右点云后的离散度差 | 全脸左右点云形态不一致 |
| `bsdiff_mouth_abs` | `mouthLeft/Right` blendshape 绝对差 | 口部横向/侧向控制左右差 |
| `raw_lip_midline_deviation` | 上下唇中心到鼻梁/鼻尖/下巴拟合中线的归一化偏移 | 唇中心偏离面部中线 |
| `raw_mouth_corner_vertical_asym` | 左右口角 y 坐标差，按双眼外角距离归一化 | 左右口角垂直高度不一致 |

两批数据验证口径：

- 旧数据 `datasets/facesym_v1_all_images_no_gate_20260119`：患者级 `all + max` 口径下 5/5 患病均值高于不患病均值；`smile_or_teeth` 合并口径也 5/5 患病更高。
- 新数据 `datasets/stroke_warning_app_rule_test_set_20260508`：患者级 `all + max` 口径下 2/5 通过；`smile_teeth` role 下 5/5 患病均值高于不患病均值。当前结论是这些特征对口部动作 role 具备更稳定解释力，不能脱离 role 和输入质量做全局无条件判断。

当前阈值与归因产物：

- 脚本：`scripts/build_core_symmetry_threshold_and_attribution.py`
- 输出：`datasets/core_symmetry_threshold_attribution_20260529`
- 阈值口径：旧数据使用 `smile/teeth` 合并 role，新数据使用 `smile_teeth` role；每个核心特征先做患者级 role 内 `max` 聚合，再分别建立不患病和患病患者稳健参考分布。
- 评分公式：只保留 `患病中位数 > 不患病中位数` 的核心特征；单特征插值为 `(患者特征值 - 不患病中位数) / (患病中位数 - 不患病中位数)`，贡献截断到 `[0, 6.0]`；`core_asymmetry_score` 为活跃稳健特征的插值贡献均值。
- 患病更高稳健特征：旧数据 5/5；新数据 4/5，`raw_mouth_corner_vertical_asym` 在新数据中位数方向不满足，因此不参与新数据核心插值评分。
- 当前统一阈值：`core_asymmetry_score >= 2.500922` 输出 `人脸不对称性较高`。阈值选择先要求两批数据合并 specificity `>= 0.75`，再最大化 Youden J。
- 当前合并弱监督指标：患者 `604`，高不对称 `198`；precision `0.717172`、recall `0.375661`、specificity `0.752212`、F1 `0.493056`。
- 旧数据全量图片外推测试脚本：`scripts/build_old_all_core_threshold_rule_test_predictions.py`；主输出位于 `datasets/stroke_warning_app_rule_test_set_20260508/metadata/52_old_all_core_threshold_rule_test_*`，报告 `datasets/stroke_warning_app_rule_test_set_20260508/reports/52_old_all_core_threshold_rule_test.md`。该口径用旧数据全部图片拟合单特征阈值和图片级触发数量阈值，再用旧数据患者级 `max_triggered_core_feature_count` 拟合最终患者阈值；当前患者级阈值为 `>= 4`，新规则测试集不患病误判 6/59。
- 旧数据指标：precision `0.763636`、recall `0.375000`、specificity `0.767857`；新数据指标：precision `0.484848`、recall `0.380952`、specificity `0.706897`。
- 患者级判断输出：`metadata/50_core_symmetry_patient_face_asymmetry_outputs.csv`，字段包括 `face_asymmetry_output=人脸不对称/未见明显人脸不对称`、`face_asymmetry_binary`、`face_asymmetry_reason` 和每个核心特征的插值贡献。
- 归因输出：`metadata/50_core_symmetry_high_asymmetry_attributions.csv` 固定输出活跃核心特征作为主归因；`metadata/50_core_symmetry_supporting_feature_analysis.csv` 额外输出高不对称组同步升高且 AUC `>= 0.60` 的 `bsdiff_*` 绝对差、`raw_*asym` 和 `raw_*deviation` 支撑归因特征。

输入数据必须满足关键点输出要求后才能计算这些特征：

- 输入必须是可读静态人脸图片，`media_type=image`，并带有明确 `media_role`。核心口部动作优先使用 `smile_teeth`、`smile` 或 `teeth`；`front_contour/front` 可作为面部中线和静息对照。
- MediaPipe Face Landmarker 检测状态必须为 `detected`；失败、`no_face`、多人脸未确认主脸、严重遮挡或侧脸姿态过大时不得直接输出核心对称判断。
- 检测 JSON 必须包含 `raw_landmarks` 长度 478，`blendshapes` 中必须包含 `mouthFrownLeft`、`mouthFrownRight`、`mouthLeft`、`mouthRight`，并建议保留 `facial_transformation_matrixes`/pose 供质量和姿态复核。
- 缺失 478 点、缺失 mouth blendshape、口角/唇中心关键点异常或无法完成双眼外角距离归一化时，应标记为不可评分或需要复核，不应把空值当作正常对称。
- 报告或 UI 展示时应优先给出 MediaPipe 关键点叠加图，尤其标出面部中线、左右口角连线、唇中心到中线偏移，以便人工复核这些特征为什么升高。

## Output And Temp Policy

- 项目输出和临时缓存默认不要写入系统 `/tmp`。
- 项目内临时目录统一使用：`tmp/`
- `scripts/run_in_project_env.sh` 会设置：
  - `FACE_SYM_AI_TMP_DIR=$PROJECT_ROOT/tmp`
  - `MPLCONFIGDIR=$PROJECT_ROOT/tmp/matplotlib`
- `tmp/*` 已在 `.gitignore` 中忽略，仅保留 `tmp/.gitkeep`。
- 文档、脚本示例和 smoke test 输出应优先使用 `tmp/...` 或正式项目输出目录。
- 只有系统级 IPC 或外部工具自身要求时，才保留 `/tmp` 说明；不要把 FaceSymAi 结果写到系统 `/tmp`。

## Current Verification

- 全量单元测试当前通过：

```bash
env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi scripts/run_in_project_env.sh pytest -q
```

结果：`61 passed`

注意：当前测试中若直接运行 `scripts/run_in_project_env.sh pytest -q`，`scripts.*` 测试导入会缺少项目根目录。

- 本地图片 MediaPipe 检测已验证写入项目内 `tmp/facesymai-mediapipe-result.json`。
- 正式 by-name V1 数据流程已验证写入 `datasets/facesym_v1_by_name_20260119`，smoke 输出写入 `tmp/facesym_v1_by_name_smoke`。

## Critical Implementation Rules

1. 所有 Python 命令默认使用 `anti-spoofing_scc_175`。
2. 推荐运行方式：
   - `source scripts/activate_project_env.sh`
   - `scripts/run_in_project_env.sh <command>`
3. 启动 Codex 使用 `scripts/codex_facesymai.sh`，它会同时绑定项目级 `CODEX_HOME` 和 conda 环境。
4. 不要改动现有 xlsx 文件，除非任务明确要求清洗、转换或标注。
5. 新增规划文档写入 `_bmad-output/planning-artifacts`。
6. 新增实施文档写入 `_bmad-output/implementation-artifacts`。
7. 长期项目知识写入 `docs/`；BMAD 精简上下文写入 `_bmad-output/project-context.md`。
8. 项目临时输出写入 `tmp/`，不要默认写入系统 `/tmp`。
9. MediaPipe V1 默认使用 Face Landmarker `.task` 模型；当前环境不要假设 `mp.solutions.face_mesh` 可用。
10. 核心人脸对称判断优先使用 5 个 MediaPipe 派生特征：`bsdiff_mouthFrown_abs`、`raw_all_mesh_region_point_spread_asym`、`bsdiff_mouth_abs`、`raw_lip_midline_deviation`、`raw_mouth_corner_vertical_asym`。这些特征必须在关键点输出完整且 role 适配的输入上计算。
11. 医疗相关输出必须表述为“风险提示/辅助分析/预警参考”，不得表述为“诊断结论”。
12. 在标签、冻结测试集和临床验证确认前，不得宣称模型达到医学性能指标。
13. 任何 precision、TP、FP、阈值或模型表现结论都必须绑定测试集版本、模型版本、样本级明细和阳性规则。

## Preferred Next Steps

1. 将 5 个核心对称证据特征接入下一版评分/报告时，先保证输入图片能输出 478 raw landmarks 和 mouth blendshape；对 `smile_teeth`/`smile_or_teeth` 采用 role-specific 解释，不直接用全 role 混合口径替代。
2. 使用 `scripts/serve_face_asymmetry_label_tool.py --host 0.0.0.0 --access-token <token>` 进行本机/局域网/外网标注，形成 `metadata/16_v11_face_asymmetry_review_labels.csv` 后重新运行校准脚本；patient outcome 只能作为弱监督检查，不能替代人工面部不对称标签。
3. 固化冻结测试集版本、阳性规则和阈值审批方式；当前 `05_patient_splits` 是可复跑分层切分，但尚未被业务冻结。
4. 复核 20 阶段预测 CSV 中的 FP/FN 样本，区分真实面部不对称、表情配合不足、质量问题、标签问题和规则阈值问题。
5. 盘点两个 xlsx 和 `datasets/*/metadata` 的字段、标签、样本规模、缺失率和媒体角色分布。
6. 用 MediaPipe 检测结果逐步增强质量门控中的人脸数量、姿态和关键点可信度逻辑。
