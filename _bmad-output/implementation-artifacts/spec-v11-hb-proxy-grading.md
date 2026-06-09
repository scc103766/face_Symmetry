---
title: "V1.1 HB Proxy Grading"
type: "feature"
created: "2026-05-22"
status: "done"
baseline_commit: "NO_VCS"
context:
  - "datasets/facesym_v1_all_images_no_gate_20260119/reports/13_next_week_optimization_plan_hb_grading_20260522.md"
  - "datasets/facesym_v1_all_images_no_gate_20260119/reports/11_v11_role_aware_quality_weighted_fit.md"
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** V1.1 已经能用患病/不患病数据生成 role-aware 弱关联不对称分数，但患者级输出仍是二分类拟合分数，不能表达人脸不对称程度或 House-Brackmann 风格等级。

**Approach:** 新增独立 HB proxy grading 阶段，读取现有 V1.1 feature set、image scores、patient core results 和 split，生成静息、闭眼、眉额、微笑/口部、整体不对称、无运动风险、质量可靠性等组件分数，再输出 I-VI 技术代理等级、派生筛查字段、分布/单调性/二分类指标和人工复核候选。

## Boundaries & Constraints

**Always:** 复用 `facesym_v1_all_images_no_gate_20260119` 的 V1.1 产物；输出写入同一 dataset 的 `metadata/12_*` 和 `reports/14_*`；patient outcome 只能作为弱监督单调性检查；HB 输出必须标注为 proxy grade，不得写成临床诊断。

**Ask First:** 需要改动 MediaPipe 模型、原始 xlsx、现有 V1/V1.1 scoring 权重、删除旧产物或把 proxy grade 当作正式临床 HB 标签时必须先询问。

**Never:** 不覆盖 `11_v11_role_aware_*`；不使用 profile/tongue/medical/auxiliary roles 进入 HB 主评分；不把姿态、matrix、采集距离特征引入主分级；不宣称 patient outcome 指标等同医学性能。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Full HB proxy run | 11 阶段 CSV 和 09/05 metadata 存在 | 生成 `12_v11_hb_proxy_patient_grades.csv`、`12_v11_hb_proxy_component_scores.csv`、`12_v11_hb_proxy_grade_evaluation.json`、`14_v11_hb_proxy_grading_results.md` | 缺失必需文件时抛出可读错误 |
| Missing role evidence | 患者缺少 eyes_closed、forehead_wrinkle、frown 等 role | 仍输出 grade，但降低 `hb_grade_confidence`、提高 `hb_needs_manual_review`，reason codes 记录缺失 role | 不强行把缺失动态 role 解释为正常 |
| No manual HB labels | 只有 `患病/不患病` 标签 | 报告 grade 分布、患病/不患病平均等级、Grade II+/III+/IV+ 派生二分类指标 | 明确这是 proxy validation，不输出 weighted kappa |

</frozen-after-approval>

## Code Map

- `scripts/build_v11_role_aware_quality_weighted_fit.py` -- V1.1 role 配置、CSV/JSON/report helper、当前患者级分数口径。
- `datasets/facesym_v1_all_images_no_gate_20260119/metadata/11_v11_role_aware_patient_core_results.csv` -- 患者级六个核心 role 分数。
- `datasets/facesym_v1_all_images_no_gate_20260119/metadata/11_v11_role_aware_image_scores.csv` -- 图像级 role 分数和 top features，可用于组件证据。
- `datasets/facesym_v1_all_images_no_gate_20260119/metadata/11_v11_role_aware_feature_set.csv` -- role 内入选特征，用于组件/原因归因。
- `datasets/facesym_v1_all_images_no_gate_20260119/metadata/09_mediapipe_full_features.csv` -- 原始 MediaPipe 派生特征，用于闭眼、眉额、口部表达充分性代理。
- `scripts/calibrate_v11_hb_proxy_with_review_labels.py` -- 读取人工面部不对称标签或质量复核标签，生成复核模板、校准预测、summary/report，并在标签足够时输出校准阈值和组件权重配置。
- `scripts/serve_face_asymmetry_label_tool.py` -- 标注网站服务端，读取 16 阶段模板和已保存标签，提供病例 API、图片静态服务、CSV 写回、重新校准接口、局域网/外网绑定和 access token 保护。
- `tools/face_asymmetry_label_tool.html` -- 人工标注页面，展示 6 个核心 role 的 MediaPipe 特征点图、组件分数、代理原因和人工标签表单；远程访问时自动携带 token 调用 API 和图片资源。
- `scripts/summarize_mediapipe_end_to_end_outputs.py` -- 20 阶段只读汇总脚本，整合 09/11/12/14 阶段产物，输出最大差异特征、患者级预测和汇总报告。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/build_v11_hb_proxy_grading.py` -- 新增 HB proxy grading CLI，读取 11/09/05 产物并生成 12/14 输出 -- 独立落地计划中的核心阶段。
- [x] `scripts/build_v11_hb_proxy_grading.py` -- 实现组件分数、train/val 分位数等级、HB I-VI 规则、confidence/review/reason codes -- 让患者级输出表达不对称程度。
- [x] `scripts/build_v11_hb_proxy_grading.py` -- 输出 evaluation JSON 和 Markdown 报告，包含 grade 分布、单调性、Grade II+/III+/IV+ 指标、复核候选 -- 保证可复核。
- [x] `scripts/build_v11_hb_proxy_grading.py` -- 指定 Grade I-VI 的静息/动态/闭眼/眉额笑容语义，并写入患者级 CSV 和报告 -- 对应“对称/粗略对称/极度不对称/无动态”等业务指标。
- [x] `scripts/build_v11_hb_proxy_grading.py` -- 基于 `09_mediapipe_full_features.csv` 输出 `12_v11_hb_proxy_mediapipe_grade_differences.csv`，比较各等级之间的 MediaPipe 478 点与 blendshape 差异 -- 用全关键点派生特征支撑等级差异分析。
- [x] `scripts/build_v11_hb_proxy_grading.py` -- 增加 Grade V+ 人脸不对称输出规则和 `12_v11_hb_proxy_grade_v_plus_asymmetry_cases.csv` -- 达到 5 级及以上时输出 `人脸不对称` 并给出原因。
- [x] `scripts/extract_v11_grade_v_plus_nondisease_review.py` -- 单独提取 Grade V+ 不患病 18 例，生成 CSV/JSON/Markdown 复核报告并展示核心 role 特征点图片 -- 支持假阳性和标签口径差异分析。
- [x] `scripts/compare_v11_grade_v_plus_18_disease_nondisease.py` -- 固定 18 例不患病对照，并挑取 18 例患病 Grade V+ 匹配样本生成对比报告 -- 支持患病/不患病同等级高风险样本的图文对比。
- [x] `scripts/analyze_v11_grade_v_plus_generalization.py` -- 验证 18 对关键差异是否普适，并评估候选规则是否应替换当前 Grade V+ 主规则 -- 防止把小样本局部差异写入规则。
- [x] `scripts/calibrate_v11_hb_proxy_with_review_labels.py` -- 引入人工面部不对称标签或质量门控后的复核标签入口，并在标签充足时重新校准阈值和组件权重 -- 将阈值更新从 patient outcome 代理转向人工/复核标签。
- [x] `scripts/serve_face_asymmetry_label_tool.py` -- 提供 HTML 标注服务，读取模板/标签、服务 annotated 特征点图、保存单例标注并触发校准，支持局域网/外网绑定和 token 访问保护 -- 让远程复核标签可以直接落到校准输入 CSV。
- [x] `tools/face_asymmetry_label_tool.html` -- 构建人工标注页面，支持病例筛选、6 role 特征点图查看、人工对称性标签、程度等级、质量排除、备注、保存和重新校准 -- 降低人工复核成本。
- [x] `scripts/summarize_mediapipe_end_to_end_outputs.py` -- 汇总患病/不患病最大主证据差异、预测模型权重最高特征、HB proxy Grade I-VI 最大差异和患者级预测结果 -- 满足“输出最大差异项和预测结果”的交付需求。
- [x] `tests/test_v11_hb_proxy_grading.py` -- 用合成患者分数验证等级规则、缺失 role 降置信、二分类指标、等级语义、MediaPipe 差异特征筛选和 Grade V+ 不对称原因 -- 降低回归风险。
- [x] `tests/test_v11_grade_v_plus_nondisease_review.py` -- 验证不患病专项复核的特征去重和高分 role 筛选 -- 固化报告聚合逻辑。
- [x] `tests/test_v11_grade_v_plus_pair_comparison.py` -- 验证 18 对照配对优先选择核心 role 图片齐全的患病样本 -- 保证报告图片完整性。
- [x] `tests/test_v11_grade_v_plus_generalization.py` -- 验证规则调整验收门槛和 split 方向一致性判断 -- 固化“未通过测试集不改主规则”的保护。
- [x] `tests/test_v11_face_asymmetry_calibration.py` -- 验证人工标签解析、质量门控剔除、权重候选归一化、合成标签校准和缺失组件评分 -- 固化复核标签校准逻辑。
- [x] `tests/test_face_asymmetry_label_tool.py` -- 验证标注服务的 CSV 写回、标签合并、质量排除、输入校验、dataset 路径保护和 token 远程访问 URL -- 固化网站保存逻辑。

**Acceptance Criteria:**
- Given 当前 all-images/no-gate dataset, when 运行 `scripts/build_v11_hb_proxy_grading.py`, then 生成 12 阶段 CSV/JSON 和 14 报告且不修改 11 阶段产物。
- Given 患者六个核心 role 都可用, when 组件分数和总分较低, then 输出低等级 HB proxy 且不要求人工复核。
- Given 患者动态/闭眼组件高或 role 缺失, when 分级运行, then 输出更高等级或人工复核 reason code。
- Given 没有人工 HB 标签, when 报告生成, then 使用 patient outcome 仅报告代理单调性和派生二分类指标。
- Given 09 阶段 MediaPipe 完整特征存在, when 分级运行, then 输出等级差异 CSV，包含全 478 点 `raw_all_mesh_region_*`、区域/语义 landmark、`bsdiff_*` 和 `bs_*` 差异，并排除 pose/matrix/距离/scale 类字段。
- Given 患者 `hb_proxy_grade_num >= 5`, when 分级运行, then 患者级 CSV 输出 `face_asymmetry_output=人脸不对称`，Grade V+ 清单记录该患者及 `face_asymmetry_reason`，报告给出该规则的患病/不患病弱监督验证指标。
- Given Grade V+ 输出病例中存在 `label_binary=0`, when 运行不患病专项复核脚本, then 单独输出 18 例 CSV/JSON/Markdown，并在报告中展示每例 6 个核心 role 的 MediaPipe 特征点图片。
- Given 18 例不患病 Grade V+ 对照, when 运行患病/不患病对比脚本, then 按 split、grade、代理分数和核心 role 图片完整性挑取 18 例患病匹配样本，输出 36 行 CSV/JSON/Markdown，并在报告中展示 216 张核心 role 特征点图片。
- Given 18 对对比已生成, when 运行普适性验证脚本, then 输出组件分 split 效应、候选规则指标和规则调整结论；若候选规则未在 test 同时提升 balanced accuracy、precision 且不降低 recall，则不修改 Grade V+ 主规则。
- Given 没有已填充的 `16_v11_face_asymmetry_review_labels.csv`, when 运行人工/复核标签校准脚本, then 生成 505 行复核模板、校准预测占位、summary/report，并返回 `insufficient_labels`，不生成 calibration config。
- Given 人工面部不对称或质量复核标签满足最小样本数和正负类别数, when 运行校准脚本, then 基于有效标签网格搜索组件权重和二分类阈值，输出 current Grade V+ 与 calibrated rule 的分 split 指标。
- Given 本地标注网站启动, when 用户选择病例并保存人工对称性标签, then 服务端直接更新 `metadata/16_v11_face_asymmetry_review_labels.csv`，保留模板上下文列并合并已有标签。
- Given 页面触发重新校准, when 保存标签满足校准条件, then 服务端调用 `calibrate_v11_hb_proxy_with_review_labels.py` 并返回最新 calibration summary。
- Given 服务以 `--host 0.0.0.0 --access-token <token>` 启动, when 局域网或外网用户通过带 token 的 URL 打开页面, then 页面能够加载病例 API 和特征点图片，并能保存人工标签；缺少或错误 token 的 API/图片请求返回 401。
- Given 09/11/12/14 阶段产物存在, when 运行 20 阶段汇总脚本, then 输出特征差异 CSV、患者预测 CSV、summary JSON 和 Markdown 报告，且不改变前置算法产物。

## Spec Change Log

- 2026-05-22: 按用户补充要求增加 Grade I-VI 语义指定和 MediaPipe 478 点等级差异输出；生成 1008 行差异结果，其中全核心 role 144 行。
- 2026-05-22: 增加 `hb_proxy_grade_num >= 5` 人脸不对称输出验证；当前输出 105 例，患病 87、不患病 18，test precision 0.727273。
- 2026-05-22: 增加 Grade V+ 不患病 18 例专项复核；报告展示 108 张核心 role 特征点图片。
- 2026-05-22: 增加 Grade V+ 患病/不患病 18 对照报告；全部使用 same split + same grade 匹配，报告展示 216 张核心 role 特征点图片。
- 2026-05-25: 增加 Grade V+ 差异普适性与规则调整验证；结论为 18 对关键差异多数不普适，候选规则未通过测试集验收，当前主规则不调整。
- 2026-05-25: 增加人工面部不对称/质量复核标签校准入口；当前尚无填充标签，生成 505 行模板并保持 `insufficient_labels`，未调整主规则阈值和权重。
- 2026-05-25: 增加本地 HTML 人工标注网站；页面读取复核模板和 landmark overlay，保存结果直接写入 `16_v11_face_asymmetry_review_labels.csv`，用于后续校准阈值和权重。
- 2026-05-25: 标注网站增加局域网/外网访问支持；`--host 0.0.0.0` 可绑定远程入口，`--access-token` 会保护 API 和图片访问，并自动追加到页面请求。
- 2026-05-27: 增加 20 阶段 MediaPipe 全流程特征差异与预测汇总；输出 108 行特征差异汇总、504 行患者预测、summary JSON 和 Markdown 报告。
- 2026-05-28: 基于旧数据 `facesym_v1_all_images_no_gate_20260119` 和新数据 `stroke_warning_app_rule_test_set_20260508`，指定 5 个当前核心人脸对称判断特征：`bsdiff_mouthFrown_abs`、`raw_all_mesh_region_point_spread_asym`、`bsdiff_mouth_abs`、`raw_lip_midline_deviation`、`raw_mouth_corner_vertical_asym`；后续评分/报告接入前必须检查关键点输出完整性。
- 2026-05-29: 增加 `scripts/build_core_symmetry_threshold_and_attribution.py`，在旧数据 `smile/teeth` 与新数据 `smile_teeth` 上分别建立不患病/患病稳健参考分布，只保留患病中位数更高的核心特征，生成统一 `core_asymmetry_score`、高不对称阈值 `2.500922` 和归因明细；输出目录为 `datasets/core_symmetry_threshold_attribution_20260529`。

## Design Notes

HB proxy grade 的阈值先来自 train+val 患者组件总分分位数，而不是手写医学阈值。规则输出只能表达“当前数据分布下的不对称程度代理”，后续有人工 HB 标签后再用 ordinal MAE、weighted kappa 和人工等级校准阈值。

Grade I-VI 的“对称/粗略对称/极度不对称/无动态”等语义是报告层和 CSV 字段层的固定解释标签；等级阈值仍由当前数据的 train+val 分布决定。MediaPipe 等级差异分析只用于发现不同 proxy grade 之间的关键点派生特征差异，不改变主分级阈值。

Grade V+ 人脸不对称输出是代理等级上的业务输出规则：`hb_proxy_grade_num >= 5` 即输出 `人脸不对称`，原因由等级语义、严重/中度组件分数、无运动风险和主要 MediaPipe/V1.1 特征证据共同生成。该规则的 precision/recall 仍只是在 patient outcome 标签上的弱监督检查。

复核标签校准流程只接受人工面部不对称标签或质量门控后的复核标签作为校准依据。标注文件不存在、有效标签少于 10、正例少于 3 或负例少于 3 时，脚本只生成标注模板和占位预测，不输出 calibration config，也不改变主 HB proxy/Grade V+ 规则。

人工标注网站不引入账号体系。保存接口按 `patient_sample_id` 合并写回标签 CSV，图片服务限制在当前 dataset 根目录内，避免通过 URL 读取项目外文件。局域网或外网暴露时应使用 `--access-token`，并通过防火墙、VPN、SSH 隧道或反向代理控制访问范围。

20 阶段汇总脚本不重新计算 MediaPipe landmarks、不重新拟合阈值，也不改变 11/12/14 阶段输出。它只读取既有 CSV/JSON，排除 pose、matrix、distance、scale 和 `*_centroid_z_asym` 等控制变量后，生成便于汇报和复核的最大差异特征表与患者级预测表。

当前核心对称特征只在输入满足 MediaPipe 关键点输出要求时有效：`detection_status=detected`、478 个 raw landmarks、mouth 左右 blendshape 完整、可拟合面部中线并完成双眼外角距离归一化。新规则测试集显示 5 个特征在 `smile_teeth` role 下均为患病更高，但全 role all+max 只有 2/5 通过；因此后续报告必须保留 role-specific 解释，不得把 `smile_teeth` 证据泛化为所有输入 role 的全局结论。

核心对称阈值规则是独立于 HB proxy Grade V+ 的辅助输出：旧数据使用 `smile/teeth`，新数据使用 `smile_teeth`；每个数据集分别建立不患病/患病稳健参考分布，单特征分数表示患者值在不患病中位数到患病中位数之间的插值位置。只保留 `患病中位数 > 不患病中位数` 的核心特征：旧数据 5/5，新数据 4/5（`raw_mouth_corner_vertical_asym` 在新数据中位数方向不满足）。当前阈值 `core_asymmetry_score >= 2.500922` 输出 `人脸不对称性较高`，合并弱监督指标为 precision `0.717172`、recall `0.375661`、specificity `0.752212`。归因必须优先列出活跃核心特征，再补充高不对称组同步升高且 AUC `>= 0.60` 的绝对不对称/偏移类支撑特征。

患者级使用入口优先读取 `metadata/50_core_symmetry_patient_face_asymmetry_outputs.csv`，其中 `face_asymmetry_output` 直接给出 `人脸不对称` 或 `未见明显人脸不对称`，`face_asymmetry_reason` 给出分数、阈值、活跃核心特征和主要归因。`患病` 标签仅作为默认人脸不对称代理阳性来选择阈值，不代表输出疾病诊断。

## Verification

**Commands:**
- `scripts/run_in_project_env.sh python scripts/build_v11_hb_proxy_grading.py --dataset datasets/facesym_v1_all_images_no_gate_20260119` -- expected: 生成 12/14 产物并打印输出路径。
- `scripts/run_in_project_env.sh python scripts/extract_v11_grade_v_plus_nondisease_review.py --dataset datasets/facesym_v1_all_images_no_gate_20260119` -- expected: 生成 13 阶段不患病专项 CSV/JSON 和 15 报告。
- `scripts/run_in_project_env.sh python scripts/compare_v11_grade_v_plus_18_disease_nondisease.py --dataset datasets/facesym_v1_all_images_no_gate_20260119` -- expected: 生成 14 阶段 18 对照 CSV/JSON 和 16 报告。
- `scripts/run_in_project_env.sh python scripts/analyze_v11_grade_v_plus_generalization.py --dataset datasets/facesym_v1_all_images_no_gate_20260119` -- expected: 生成 15 阶段普适性验证 CSV/JSON 和 17 报告。
- `scripts/run_in_project_env.sh python scripts/calibrate_v11_hb_proxy_with_review_labels.py --dataset datasets/facesym_v1_all_images_no_gate_20260119` -- expected: 无填充标签时生成 16 阶段模板/summary/predictions 和 18 报告，状态为 `insufficient_labels`。
- `scripts/run_in_project_env.sh python scripts/serve_face_asymmetry_label_tool.py --dataset datasets/facesym_v1_all_images_no_gate_20260119` -- expected: 启动本机标注网站，保存接口写入 `metadata/16_v11_face_asymmetry_review_labels.csv`。
- `scripts/run_in_project_env.sh python scripts/serve_face_asymmetry_label_tool.py --dataset datasets/facesym_v1_all_images_no_gate_20260119 --host 0.0.0.0 --access-token <token>` -- expected: 启动局域网/外网可访问的标注网站，打印本机和局域网 URL，API 和图片访问需要 token。
- `scripts/run_in_project_env.sh python scripts/summarize_mediapipe_end_to_end_outputs.py --dataset datasets/facesym_v1_all_images_no_gate_20260119` -- expected: 生成 20 阶段特征差异、预测、summary 和报告。
- `scripts/run_in_project_env.sh python scripts/build_core_symmetry_threshold_and_attribution.py` -- expected: 生成 50 阶段核心对称阈值、患者级高不对称输出和归因报告。
- `python3 -m py_compile scripts/summarize_mediapipe_end_to_end_outputs.py` -- expected: compile succeeds。
- `python3 -m py_compile scripts/build_core_symmetry_threshold_and_attribution.py` -- expected: compile succeeds。
- `env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi scripts/run_in_project_env.sh pytest -q` -- expected: `52 passed`。

## Suggested Review Order

**Entry Point**

- CLI wires existing 11/09/05 artifacts into new 12/14 outputs.
  [`build_v11_hb_proxy_grading.py:125`](../../scripts/build_v11_hb_proxy_grading.py#L125)

**Scoring Logic**

- Component split maps V1.1 role scores to HB observation dimensions.
  [`build_v11_hb_proxy_grading.py:254`](../../scripts/build_v11_hb_proxy_grading.py#L254)

- Train+val quantiles keep proxy thresholds data-derived.
  [`build_v11_hb_proxy_grading.py:309`](../../scripts/build_v11_hb_proxy_grading.py#L309)

- Patient grade row assembles grade, confidence, review flags, and evidence.
  [`build_v11_hb_proxy_grading.py:344`](../../scripts/build_v11_hb_proxy_grading.py#L344)

- Grade descriptors pin the business terms for symmetry and motion labels.
  [`build_v11_hb_proxy_grading.py:440`](../../scripts/build_v11_hb_proxy_grading.py#L440)

- Expression strength supports the movement-absence proxy without using pose.
  [`build_v11_hb_proxy_grading.py:620`](../../scripts/build_v11_hb_proxy_grading.py#L620)

- MediaPipe grade differences compare 478-point and blendshape features across proxy grades while excluding pose/distance/matrix fields.
  [`build_v11_hb_proxy_grading.py:798`](../../scripts/build_v11_hb_proxy_grading.py#L798)

- Grade V+ output turns severe proxy grades into explicit face-asymmetry cases with human-readable reasons.
  [`build_v11_hb_proxy_grading.py:452`](../../scripts/build_v11_hb_proxy_grading.py#L452)

**Outputs**

- Nondisease review CLI extracts Grade V+ false-positive review cases and links role landmark overlays.
  [`extract_v11_grade_v_plus_nondisease_review.py:43`](../../scripts/extract_v11_grade_v_plus_nondisease_review.py#L43)

- Case enrichment summarizes component drivers, role drivers, review focus, and annotation paths.
  [`extract_v11_grade_v_plus_nondisease_review.py:144`](../../scripts/extract_v11_grade_v_plus_nondisease_review.py#L144)

- Review report embeds 6 core role MediaPipe landmark images per nondisease Grade V+ case.
  [`extract_v11_grade_v_plus_nondisease_review.py:307`](../../scripts/extract_v11_grade_v_plus_nondisease_review.py#L307)

- Pair comparison CLI selects 18 diseased matches for the 18 nondisease Grade V+ cases.
  [`compare_v11_grade_v_plus_18_disease_nondisease.py:35`](../../scripts/compare_v11_grade_v_plus_18_disease_nondisease.py#L35)

- Matching prioritizes same split, same grade, close proxy score, and complete core-role images.
  [`compare_v11_grade_v_plus_18_disease_nondisease.py:80`](../../scripts/compare_v11_grade_v_plus_18_disease_nondisease.py#L80)

- Pair comparison report embeds side-by-side landmark overlays for both groups.
  [`compare_v11_grade_v_plus_18_disease_nondisease.py:292`](../../scripts/compare_v11_grade_v_plus_18_disease_nondisease.py#L292)

- Generalization analysis checks split stability for the 18-pair differences.
  [`analyze_v11_grade_v_plus_generalization.py:120`](../../scripts/analyze_v11_grade_v_plus_generalization.py#L120)

- Rule candidate evaluation rejects changes that fail the test-set acceptance policy.
  [`analyze_v11_grade_v_plus_generalization.py:191`](../../scripts/analyze_v11_grade_v_plus_generalization.py#L191)

- Generalization report records the no-change decision and supporting metrics.
  [`analyze_v11_grade_v_plus_generalization.py:427`](../../scripts/analyze_v11_grade_v_plus_generalization.py#L427)

- Review-label calibration CLI generates templates and optional calibrated config.
  [`calibrate_v11_hb_proxy_with_review_labels.py:45`](../../scripts/calibrate_v11_hb_proxy_with_review_labels.py#L45)

- Label template prioritizes Grade V+ nondisease, diseased low-grade, and existing manual-review candidates.
  [`calibrate_v11_hb_proxy_with_review_labels.py:143`](../../scripts/calibrate_v11_hb_proxy_with_review_labels.py#L143)

- Review-label loading accepts multiple manual/review columns and excludes quality-rejected rows.
  [`calibrate_v11_hb_proxy_with_review_labels.py:215`](../../scripts/calibrate_v11_hb_proxy_with_review_labels.py#L215)

- Calibration requires minimum valid labels, then searches component weights and binary threshold.
  [`calibrate_v11_hb_proxy_with_review_labels.py:267`](../../scripts/calibrate_v11_hb_proxy_with_review_labels.py#L267)

- Calibration report records whether rules were recalibrated or blocked by insufficient labels.
  [`calibrate_v11_hb_proxy_with_review_labels.py:516`](../../scripts/calibrate_v11_hb_proxy_with_review_labels.py#L516)

- Remote access URL generation prints local/LAN/public URLs and appends token when configured.
  [`serve_face_asymmetry_label_tool.py:104`](../../scripts/serve_face_asymmetry_label_tool.py#L104)

- Label-tool server exposes the page, cases API, dataset images, save API, recalibration API, and token authorization.
  [`serve_face_asymmetry_label_tool.py:139`](../../scripts/serve_face_asymmetry_label_tool.py#L139)

- Save logic merges one reviewed patient back into the full review-label CSV.
  [`serve_face_asymmetry_label_tool.py:403`](../../scripts/serve_face_asymmetry_label_tool.py#L403)

- Recalibration endpoint delegates to the existing 16-stage calibration script.
  [`serve_face_asymmetry_label_tool.py:472`](../../scripts/serve_face_asymmetry_label_tool.py#L472)

- HTML page stores remote access token and renders the role image grid and manual label form.
  [`face_asymmetry_label_tool.html:635`](../../tools/face_asymmetry_label_tool.html#L635)

- HTML API helpers attach token to GET, POST, and image-loading URLs.
  [`face_asymmetry_label_tool.html:667`](../../tools/face_asymmetry_label_tool.html#L667)

- HTML page renders the role image grid and manual label form.
  [`face_asymmetry_label_tool.html:519`](../../tools/face_asymmetry_label_tool.html#L519)

- Frontend save and recalibration handlers call the local APIs.
  [`face_asymmetry_label_tool.html:871`](../../tools/face_asymmetry_label_tool.html#L871)

- Evaluation captures grade distribution, monotonicity, and derived binary metrics.
  [`build_v11_hb_proxy_grading.py:965`](../../scripts/build_v11_hb_proxy_grading.py#L965)

- Markdown report presents proxy limits and review candidates.
  [`build_v11_hb_proxy_grading.py:1189`](../../scripts/build_v11_hb_proxy_grading.py#L1189)

**Project Context**

- Long-term context now records command, outputs, and proxy limits.
  [`project-context.md:87`](../../docs/project-context.md#L87)

- Agent context mirrors the new HB proxy stage for future sessions.
  [`project-context.md:181`](../project-context.md#L181)

**Tests**

- Unit tests pin grade thresholds, missing-role review, and binary metrics.
  [`test_v11_hb_proxy_grading.py:10`](../../tests/test_v11_hb_proxy_grading.py#L10)

- Unit tests pin descriptor labels and MediaPipe difference feature inclusion/exclusion.
  [`test_v11_hb_proxy_grading.py:88`](../../tests/test_v11_hb_proxy_grading.py#L88)

- Unit tests pin Grade V+ face-asymmetry output and reason generation.
  [`test_v11_hb_proxy_grading.py:96`](../../tests/test_v11_hb_proxy_grading.py#L96)

- Unit tests pin nondisease review feature compaction and high-score role filtering.
  [`test_v11_grade_v_plus_nondisease_review.py:6`](../../tests/test_v11_grade_v_plus_nondisease_review.py#L6)

- Unit tests pin pair matching preference for complete landmark-image coverage.
  [`test_v11_grade_v_plus_pair_comparison.py:6`](../../tests/test_v11_grade_v_plus_pair_comparison.py#L6)

- Unit tests pin generalization rule-change guardrails.
  [`test_v11_grade_v_plus_generalization.py:6`](../../tests/test_v11_grade_v_plus_generalization.py#L6)

- Unit tests pin review-label parsing, quality exclusion, and synthetic calibration behavior.
  [`test_v11_face_asymmetry_calibration.py:14`](../../tests/test_v11_face_asymmetry_calibration.py#L14)

- Unit tests pin label-tool CSV save, case payload merge, quality exclusion, validation, path traversal protection, and token-protected remote URLs.
  [`test_face_asymmetry_label_tool.py:81`](../../tests/test_face_asymmetry_label_tool.py#L81)
