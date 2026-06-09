# FaceSymAi 项目上下文

本文件是长期项目知识入口。BMAD 面向智能体的精简上下文位于：

```text
_bmad-output/project-context.md
```

## 当前状态

- 项目目录已建立 Codex 项目隔离会话池。
- BMAD-METHOD 已安装到 `_bmad`。
- Codex BMAD 技能已安装到 `.agents/skills`。
- 基础运行环境已固定为 conda env `anti-spoofing_scc_175`。
- 项目已形成 Python 包结构：`src/facesymai/`。
- 已实现关键点级人脸对称性 baseline、质量门控和风险解释输出。
- 已按技术方案接入 MediaPipe Tasks `Face Landmarker` 作为 V1 检测基座。
- Face Landmarker 模型位于 `models/mediapipe/face_landmarker.task`。
- 本地图片检测入口为 `scripts/detect_mediapipe_image.py`。
- MediaPipe 人脸关键点检测已整理为可复用模块和离线 SDK：`modules/mediapipe_face_keypoint_detector`。该模块自带 `models/face_landmarker.task`，可直接复制整个文件夹到其他机器离线使用；支持 Python SDK `FaceKeypointDetectorSDK`、命令行 `run_detect.py`、HTTP API `serve_api.py` 三种调用方式。模块只负责静态图片人脸关键点检测，输出 478 raw landmarks、语义关键点、52 blendshapes、facial transformation matrix 和可选关键点叠加图；不包含质量门控、人脸对称性判断或患病结论。离线 SDK 文档为 `modules/mediapipe_face_keypoint_detector/SDK_USAGE.md`；复制目录 smoke test 输出位于 `tmp/mediapipe_face_keypoint_detector_offline_copy_smoke/result.json`。
- V1 关键点数据集采集入口为 `scripts/collect_v1_keypoint_dataset.py`。
- 当前推荐数据处理流程入口为 `scripts/build_facesym_v1_dataset_from_by_name.py`。
- 脑卒中预警 App 规则测试集入口为 `scripts/build_stroke_warning_rule_test_set.py`，输出位于 `datasets/stroke_warning_app_rule_test_set_20260508`；当前纳入患者 101，其中 `患病` 42、`不患病` 59。
- 旧数据全量图片核心特征阈值外推验证入口为 `scripts/build_old_all_core_threshold_rule_test_predictions.py`，主报告位于 `datasets/stroke_warning_app_rule_test_set_20260508/reports/52_old_all_core_threshold_rule_test.md`；当前规则为图片级 `triggered_core_feature_count >= 2`、患者级 `max_triggered_core_feature_count >= 4`，在规则测试集患者级不患病误判 6/59。
- 两批数据联合寻找患病/不患病判断特征入口为 `scripts/find_combined_disease_feature_candidates.py`，输出位于 `datasets/combined_disease_feature_candidates_20260529`；当前去重推荐特征 21 个，均为患病更高，优先特征包括 `raw_lip_midline_deviation`、`raw_eyebrow_region_height_asym`、`raw_iris_region_point_spread_asym`、`bsdiff_browDown_abs`、`bsdiff_mouth_abs`、`bsdiff_mouthFrown_abs`。
- 十个联合特征患者级患病倾向规则入口为 `scripts/build_top10_patient_disease_rule.py`，报告位于 `datasets/combined_disease_feature_candidates_20260529/reports/61_top10_patient_disease_rule.md`；当前规则为 10 个特征中至少 5 个达到阈值输出 `患病倾向较高`，并输出逐患者触发原因。规范输入必需 `smile_teeth` 或旧 V1 `smile+teeth`，推荐 `front_contour/front + smile_teeth/smile,teeth + eyes_right`。
- 21 个去重推荐特征稳定性加权患病判断规则入口为 `scripts/build_stable_weighted_feature_disease_rule.py`，报告位于 `datasets/combined_disease_feature_candidates_20260529/reports/62_stable_weighted_feature_disease_rule.md`；当前规则按患者更高、非患者不过阈值、跨数据 AUC、所有图片波动性和图片数分配权重，`weighted_disease_score >= 0.612826` 输出 `患病倾向较高`，并输出逐患者判断原因和逐特征贡献。当前默认推荐采用 62 作为高置信规则，因为它在 combined precision、combined specificity 和 new specificity 上优于 61/63。
- 62 规则人脸不对称分析服务已封装为 `modules/facial_asymmetry_service`，命令行入口为 `scripts/run_in_project_env.sh python modules/facial_asymmetry_service/run_analyze.py ...`，网页/API 入口为 `scripts/run_in_project_env.sh python modules/facial_asymmetry_service/serve_web.py --port 8790 --access-token <token>`，默认绑定 `0.0.0.0` 允许外部网络访问。调用文档为 `modules/facial_asymmetry_service/CALLING_GUIDE.md`，覆盖网页上传、`POST /api/analyze`、`GET /api/input-spec`、curl、Python requests 和 JavaScript fetch。网页/API 输出为用户版结果：保留 `face_asymmetry_confidence` 和 `face_asymmetry_output`，原因描述使用双侧口角夹角/牵拉幅度差、唇部中线偏移、双侧眼裂高度或眼周形态差、眉部高度或动作幅度差、面部轮廓左右差等用户可读观察项，不默认展示技术特征名、阈值或权重。网页/API 只校验最少 2 张、最多 10 张，不强制限制动作；露齿微笑/微笑/示齿、正脸/面部轮廓、眼周/额眉动作每类都支持多张上传并按多图聚合规则处理。服务 smoke test 输出位于 `tmp/facial_asymmetry_service_rule62_smoke`，Web API smoke 输出位于 `tmp/facial_asymmetry_service_web_api_smoke.json`。
- role-specific、阈值稳定性筛选、非患者参考分布阈值三项优化入口为 `scripts/build_optimized_threshold_feature_disease_rule.py`，报告位于 `datasets/combined_disease_feature_candidates_20260529/reports/63_optimized_threshold_feature_disease_rule.md`；当前规则单特征阈值取 `max(Youden阈值, old/new/combined 非患者 P85)`，用 120 次 bootstrap 稳定性降权，主加权阈值为 `weighted_disease_score >= 0.102162`。当前 new precision `0.653846`、recall `0.404762`、specificity `0.847458`。
- 正式 V1 by-name 数据处理结果位于 `datasets/facesym_v1_by_name_20260119`。
- 全图片无筛选/无质量门控对比组入口为 `scripts/build_facesym_v1_all_images_no_gate_comparison.py`。
- 全图片对比组结果位于 `datasets/facesym_v1_all_images_no_gate_20260119`。
- V1.1 HB proxy 分级入口为 `scripts/build_v11_hb_proxy_grading.py`。
- 当前 HB proxy 分级结果位于 `datasets/facesym_v1_all_images_no_gate_20260119/metadata/12_v11_hb_proxy_patient_grades.csv`，MediaPipe 等级差异位于 `datasets/facesym_v1_all_images_no_gate_20260119/metadata/12_v11_hb_proxy_mediapipe_grade_differences.csv`，Grade V+ 不对称清单位于 `datasets/facesym_v1_all_images_no_gate_20260119/metadata/12_v11_hb_proxy_grade_v_plus_asymmetry_cases.csv`，报告位于 `datasets/facesym_v1_all_images_no_gate_20260119/reports/14_v11_hb_proxy_grading_results.md`。
- Grade V+ 不患病专项复核入口为 `scripts/extract_v11_grade_v_plus_nondisease_review.py`，报告位于 `datasets/facesym_v1_all_images_no_gate_20260119/reports/15_v11_grade_v_plus_nondisease_false_positive_review.md`。
- Grade V+ 患病/不患病 18 对照入口为 `scripts/compare_v11_grade_v_plus_18_disease_nondisease.py`，报告位于 `datasets/facesym_v1_all_images_no_gate_20260119/reports/16_v11_grade_v_plus_18_disease_nondisease_comparison.md`。
- Grade V+ 差异普适性与规则调整验证入口为 `scripts/analyze_v11_grade_v_plus_generalization.py`，报告位于 `datasets/facesym_v1_all_images_no_gate_20260119/reports/17_v11_grade_v_plus_generalization_and_rule_adjustment.md`。
- 人工面部不对称/质量复核标签校准入口为 `scripts/calibrate_v11_hb_proxy_with_review_labels.py`，报告位于 `datasets/facesym_v1_all_images_no_gate_20260119/reports/18_v11_face_asymmetry_review_label_calibration.md`。
- 人工面部对称性标注网站入口为 `scripts/serve_face_asymmetry_label_tool.py`，页面文件为 `tools/face_asymmetry_label_tool.html`，保存目标为 `datasets/facesym_v1_all_images_no_gate_20260119/metadata/16_v11_face_asymmetry_review_labels.csv`，支持 `--host 0.0.0.0` 局域网/外网绑定和 `--access-token` 访问保护。
- 项目临时输出统一写入项目内 `tmp/`，不默认写入系统 `/tmp`。
- 当前测试通过：`61 passed`。
- 当前目录存在两个 xlsx 业务输入文件，文件名指向脑卒中数据采集与预警报告场景。

## 当前数据处理流程

当前流程从 `datasets/stroke_patient_outcome_by_name_20260119` 出发，仅处理 V1 静态图片角色 `front,smile,teeth`，输出到 `datasets/facesym_v1_by_name_20260119`。

运行命令：

```bash
scripts/run_in_project_env.sh python scripts/build_facesym_v1_dataset_from_by_name.py \
  --output datasets/facesym_v1_by_name_20260119 \
  --roles front,smile,teeth
```

阶段与报告：

- `01_manifest`：样本筛选，报告 `reports/01_manifest.md`，包含入选图片明细。
- `02_quality_gate`：质量门控，报告 `reports/02_quality_gate.md`，隔离图片明细 `metadata/02_quarantined_images.csv`。
- `03_keypoints`：MediaPipe Face Landmarker 检测与特征点绘制，报告 `reports/03_keypoints.md`，包含每张图片检测状态和输出路径。
- `04_features`：图片级/患者级对称性特征，先执行坐标标准化（鼻梁/鼻尖/下巴中线拟合、轻微 roll 校正、双眼外角距离尺度归一化），报告 `reports/04_features.md`，包含总体对称性判定、口部/眼部/眉部/鼻面中线/面部轮廓五类部件级属性，以及图片级和患者级特征摘要明细。
- `05_patient_splits`：患者级 train/val/test 分层切分，报告 `reports/05_patient_splits.md`，包含每个患者的 split。
- `06_baseline_evaluation`：当前规则 baseline 技术评估，报告 `reports/06_baseline_evaluation.md`，包含每个患者的预测、阈值和 TP/FP/TN/FN 归类。

当前结果摘要：

- 505 个患者样本、1546 张 V1 图片；患者标签为 `患病` 336、`不患病` 169。
- MediaPipe 检测：1538 张 detected、7 张 no_face、1 张 failed；成功样本均符合 Face Landmarker 输出形态：478 raw landmarks、52 blendshapes、1 或 2 个 transformation matrix。
- 已生成 1538 张人脸特征点绘制图：`datasets/facesym_v1_by_name_20260119/annotated/.../*.jpg`。
- 已生成 1538 个关键点 JSON：`datasets/facesym_v1_by_name_20260119/keypoints/.../*.json`。
- 已生成总体对称性与五类部件级属性：`overall_symmetry_score`、`affected_side`、`mouth/eye/brow/midline/contour` 五类 `score/symmetry_score/side/confidence`。
- 患者级切分：train 353、val 75、test 77。
- 当前 test precision 为 `0.662338`，来自 `TP=51`、`FP=26`，即 `51/(51+26)=0.6623376623376623`；该数值只针对 patient outcome 标签的技术信号检查，不是医学诊断性能。
- 当前 V1 计算过程、特征公式、权重、阈值和 precision 来源已整理到 `docs/algorithm/facesym-v1-calculation-technical-document.md`。

## 当前对比组流程

新增对比组从同一 by-name 数据集出发，读取所有 `media_type=image` 图片，不做 `front,smile,teeth` manifest 筛选，不运行质量门控。该流程用于观察非 V1 图片角色和无门控输入对 MediaPipe 检测、特征、患者级 max 分数和 baseline 指标的影响。

运行命令：

```bash
scripts/run_in_project_env.sh python scripts/build_facesym_v1_all_images_no_gate_comparison.py \
  --output datasets/facesym_v1_all_images_no_gate_20260119
```

当前对比组结果摘要：

- 输入图片：5195 张，505 个患者；每位患者 7 到 20 张图片。
- 图片角色包括 `front/smile/teeth`，以及 `eyes_closed/forehead_wrinkle/frown/left_profile/right_profile/tongue_bottom/tongue_surface/auxiliary_exam_image/medical_record`。
- 质量门控：skipped，排除图片数 0。
- MediaPipe 检测：`detected` 5005、`no_face` 189、`failed` 1；已生成 5005 张特征点绘制图。
- 特征生成：5005 张图片 feature-ready，505 条患者级特征，无特征计算错误。
- 患者级分数：`max_image_advisory_confidence_no_quality_gate`，同一患者同一 role 多图按最高 `advisory_confidence` 记录 role-best，患者总分取全图片最高分。
- 患者级切分：train 353、val 75、test 77，沿用 seed `20260520`。
- baseline：验证集阈值 `0.555802`；test precision `0.662338`、recall `1.000000`、specificity `0.000000`，对应 test `TP=51`、`FP=26`、`TN=0`、`FN=0`。

解释限制：该对比组包含侧脸、舌像、闭眼、病历等非 V1 目标输入，且不运行质量门控。它用于对照和归因，不应作为正式 V1 验收流程或医学性能结果。

## 当前 V1.1 HB Proxy 分级流程

HB proxy 分级从 `datasets/facesym_v1_all_images_no_gate_20260119` 的 11 阶段 V1.1 role-aware 结果出发，读取 `metadata/11_v11_role_aware_feature_set.csv`、`metadata/11_v11_role_aware_image_scores.csv`、`metadata/11_v11_role_aware_patient_core_results.csv`、`metadata/09_mediapipe_full_features.csv` 和 `metadata/05_patient_splits.csv`，输出 House-Brackmann 风格 I-VI 技术代理等级。

运行命令：

```bash
scripts/run_in_project_env.sh python scripts/build_v11_hb_proxy_grading.py \
  --dataset datasets/facesym_v1_all_images_no_gate_20260119
```

当前结果摘要：

- 患者数：505；可评分患者数：504。
- 输出 `hb_proxy_grade`、`hb_proxy_grade_num`、`hb_grade_confidence`、静息/闭眼/眉额/微笑口部/整体不对称/无运动风险/质量可靠性组件分数。
- 患者级 CSV 已指定 HB 风格等级语义：`hb_resting_symmetry_label`、`hb_dynamic_symmetry_label`、`hb_eye_closure_label`、`hb_mouth_brow_motion_label`、`hb_grade_descriptor`。其中 Grade I 为对称，Grade II-III/IV 为粗略对称到中度不对称，Grade V-VI 为极度不对称/无动态候选。
- grade 分布：Grade I 96、Grade II 102、Grade III 104、Grade IV 97、Grade V 68、Grade VI 37。
- Grade V+ 人脸不对称输出规则：`hb_proxy_grade_num >= 5` 时 `face_asymmetry_output=人脸不对称`，原因写入 `face_asymmetry_reason`；当前输出清单为 `metadata/12_v11_hb_proxy_grade_v_plus_asymmetry_cases.csv`，共 105 条。
- Grade V+ 弱监督验证：总体 precision `0.828571`、recall `0.258929`、specificity `0.892857`；test precision `0.727273`、recall `0.156863`、specificity `0.884615`。输出病例中患病 87、不患病 18。
- Grade V+ 不患病专项复核：输出 `metadata/13_v11_hb_proxy_grade_v_plus_nondisease_cases.csv`、`metadata/13_v11_hb_proxy_grade_v_plus_nondisease_summary.json` 和 `reports/15_v11_grade_v_plus_nondisease_false_positive_review.md`；当前 18 例，报告内展示每例 6 个核心 role 的 MediaPipe 特征点图片，共 108 张。
- Grade V+ 18 对照对比：输出 `metadata/14_v11_hb_proxy_grade_v_plus_18_pair_comparison.csv`、`metadata/14_v11_hb_proxy_grade_v_plus_18_pair_comparison_summary.json` 和 `reports/16_v11_grade_v_plus_18_disease_nondisease_comparison.md`；固定 18 例不患病对照，并按 split/grade/代理总分接近度挑取 18 例患病匹配，报告展示 216 张核心 role 特征点图片。
- Grade V+ 差异普适性验证：输出 `metadata/15_v11_grade_v_plus_generalization_component_effects.csv`、`metadata/15_v11_grade_v_plus_rule_adjustment_candidates.csv`、`metadata/15_v11_grade_v_plus_generalization_summary.json` 和 `reports/17_v11_grade_v_plus_generalization_and_rule_adjustment.md`。结论：18 对中的多数关键差异不是可直接用于调规则的普适差异；在 Grade V+ 高等级子集中只有 HB proxy 总分和无运动风险相对稳定，候选规则未通过测试集验收，因此未调整当前 Grade V+ 主规则。
- 人工面部不对称/质量复核标签校准：输出 `metadata/16_v11_face_asymmetry_review_label_template.csv`、`metadata/16_v11_face_asymmetry_calibrated_predictions.csv`、`metadata/16_v11_face_asymmetry_calibration_summary.json` 和 `reports/18_v11_face_asymmetry_review_label_calibration.md`。当前 `metadata/16_v11_face_asymmetry_review_labels.csv` 尚未填充，有效复核标签数为 0，状态为 `insufficient_labels`，因此未重新校准阈值/权重，也未生成可接入主流程的 calibration config。
- 人工标注网站：`scripts/serve_face_asymmetry_label_tool.py` 启动页面，读取 16 阶段模板和已保存标签，展示每例 6 个核心 role 的 MediaPipe 特征点图、组件分数和代理原因；保存时直接写回 `metadata/16_v11_face_asymmetry_review_labels.csv`，页面内可触发重新校准。远程标注时使用 `--host 0.0.0.0 --access-token <token>` 绑定局域网/外网地址，页面、API 和图片请求都会携带 token。
- patient outcome 代理单调性检查：患病平均 grade `3.348214`，不患病平均 grade `2.601190`，患病组更高。
- 派生二分类 test 指标：Grade II+ precision `0.701493`、recall `0.921569`、specificity `0.230769`；Grade III+ precision `0.700000`、recall `0.686275`、specificity `0.423077`；Grade IV+ precision `0.709677`、recall `0.431373`、specificity `0.653846`。
- MediaPipe 等级差异输出：`metadata/12_v11_hb_proxy_mediapipe_grade_differences.csv`，当前 1008 行，其中全核心 role 144 行；包含 35 个 `mediapipe_478_all_landmarks` 全 478 点统计差异、252 个区域/语义 landmark 差异、378 个左右 blendshape 差异、343 个表情 blendshape 差异。
- 全核心 role 的高区分差异示例：`raw_face_oval_region_centroid_y_asym`、`raw_iris_region_centroid_y_asym`、`raw_lip_region_centroid_y_asym`、`raw_eye_region_centroid_y_asym`、`raw_mouth_corner_vertical_asym`，以及全 478 点统计 `raw_all_mesh_region_centroid_y_asym`。
- 人工复核候选：`metadata/12_v11_hb_proxy_manual_review_candidates.csv`，当前 195 条。

解释限制：`hb_proxy_grade` 是基于 patient outcome 弱关联和 V1.1 组件分布生成的技术代理等级，不是临床 House-Brackmann 诊断。当前没有人工 HB 标签，也没有已填充的人工面部不对称/质量复核标签，因此不能计算 weighted kappa、ordinal MAE 或人工不对称标签下的最终准确率。

## 当前 V1 假设

- V1 聚焦静态图片人脸对称性分析。
- 优先处理 `front`、`smile`、`teeth` 等面部图片角色。
- 输出定位为脑卒中/面瘫预警辅助解释，不作为临床诊断。
- MediaPipe 输出的 landmarks、blendshapes 和 transformation matrix 是检测层基座。

## 待确认

- 标签口径：当前流程已生成复核模板和本地标注网站；重新校准阈值和权重需要通过标注网站写入人工面部不对称标签或质量门控后的复核标签。
- 冻结测试集切分规则：当前已有患者级分层切分，仍需业务冻结版本。
- precision 评估阈值、阳性规则、测试集版本和样本级预测明细格式。
- MediaPipe `.task` 模型是否需要固定 checksum、模型卡和审批记录。
- 后续是否需要 API 服务、前端审核/报告页面、部署权限和审计要求。
