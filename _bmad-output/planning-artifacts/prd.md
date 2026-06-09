---
title: "PRD: FaceSymAi MVP"
project: "FaceSymAi"
status: "updated"
created: "2026-05-18"
last_updated: "2026-05-28"
method: "BMAD-METHOD"
---

# PRD: FaceSymAi MVP

## 1. 产品目标

建立 FaceSymAi 的第一版可验证 MVP：对本地静态人脸图片进行 MediaPipe Face Landmarker 检测，提取标准化人脸关键点和面部属性，再通过可解释几何规则输出脑卒中/面瘫预警辅助置信度、异常贡献项和输入质量提示。系统定位为“预警参考与解释增强”，不替代临床诊断。

当前任务定义：V1 以本地图片为输入，优先支持正脸、微笑和示齿图片；检测层使用 MediaPipe Face Landmarker；特征层输出人脸对称性、口部、眼部、眉部、中线和全局镜像误差；风险解释层输出 `advisory_confidence`、`risk_level`、解释项和安全声明。V1.1 在全图片对比组上扩展到 478 点区域/语义差异、blendshape 左右差异、患者级 role-aware 预测和 HB proxy I-VI 技术代理分级。当前基于旧数据 `facesym_v1_all_images_no_gate_20260119` 和新数据 `stroke_warning_app_rule_test_set_20260508` 的复核，指定 `bsdiff_mouthFrown_abs`、`raw_all_mesh_region_point_spread_asym`、`bsdiff_mouth_abs`、`raw_lip_midline_deviation`、`raw_mouth_corner_vertical_asym` 作为人脸是否对称的核心关键点判断特征。

当前验收口径：在冻结测试集上运行检测与 scoring pipeline，输出可复核的 `precision = TP / (TP + FP)`。报告必须包含 TP、FP、阳性判定规则、阈值、测试集版本、模型版本和样本级预测明细。

## 2. 当前实现状态

### 已完成

- Python 运行入口固定为 `anti-spoofing_scc_175`。
- `src/facesymai/` 已包含 schema、几何特征、风险解释、质量门控、数据集工具和 CLI。
- 结构化关键点 JSON baseline 可运行。
- MediaPipe Tasks `Face Landmarker` 已接入：
  - 适配器：`src/facesymai/landmarks/mediapipe_face_landmarker.py`
  - 模型：`models/mediapipe/face_landmarker.task`
  - 本地图片脚本：`scripts/detect_mediapipe_image.py`
  - 批量采集脚本：`scripts/collect_v1_keypoint_dataset.py`
- 单图 smoke test 已输出 `478` 个 raw landmarks、`52` 个 blendshape、`1` 个 transformation matrix。
- 批量采集 smoke test 已通过。
- 当前推荐数据流程已落地：`scripts/build_facesym_v1_dataset_from_by_name.py`。
- 正式 by-name V1 输出已生成：`datasets/facesym_v1_by_name_20260119`，覆盖 505 个患者样本、1546 张 `front/smile/teeth` 图片。
- MediaPipe Face Landmarker 正式流程结果：1538 张 detected、7 张 no_face、1 张 failed，已生成 1538 张特征点绘制图。
- 静态几何特征正式输出总体对称性评分、疑似异常侧，以及口部、眼部、眉部、鼻面中线、面部轮廓五类部件级属性。
- 特征层已执行坐标标准化：鼻梁/鼻尖/下巴中线拟合、轻微 roll 校正、双眼外角距离尺度归一化。
- 每个数据处理阶段均有 CSV/JSON 结果和 Markdown 报告。
- 全图片无质量门控对比组已生成：`datasets/facesym_v1_all_images_no_gate_20260119`，覆盖 5195 张图片、505 个患者。
- V1.1 role-aware 预测已生成患者级预测：`metadata/11_v11_role_aware_predictions.csv`，test precision `0.690476`、recall `0.568627`、specificity `0.500000`。
- HB proxy Grade I-VI 技术代理分级已生成：`metadata/12_v11_hb_proxy_patient_grades.csv`、`reports/14_v11_hb_proxy_grading_results.md`。
- Grade V+ 人脸不对称输出已生成：105 例，其中患病 87、不患病 18；test precision `0.727273`、specificity `0.884615`。
- Grade V+ 患病/不患病 18 对照报告已生成：`reports/16_v11_grade_v_plus_18_disease_nondisease_comparison.md`。
- 人工面部不对称/质量复核标注入口已实现：`scripts/serve_face_asymmetry_label_tool.py` 与 `tools/face_asymmetry_label_tool.html`。
- MediaPipe 全流程特征差异与预测汇总已生成：`metadata/20_mediapipe_end_to_end_feature_differences.csv`、`metadata/20_mediapipe_end_to_end_predictions.csv`、`reports/20_mediapipe_end_to_end_summary.md`。
- 两批数据核心特征复核已完成：旧数据患者级 all+max 口径下 5 个核心特征均为患病更高；新数据 `smile_teeth` role 下 5 个核心特征也均为患病更高，但新数据全 role all+max 仅 2/5 通过，因此核心判断必须保留 role-specific 解释。
- 单元测试当前通过：`52 passed`。

### 未完成

- 冻结测试集和标签口径尚未业务确认。
- precision/V1.1/HB proxy 技术报告已 against patient outcome 标签生成，但尚未形成正式验收版本。
- 全量 V1 keypoint dataset 已有当前 by-name 版本，仍需人工抽样复核 landmark 质量。
- 人工面部不对称/质量复核标签尚未填充，当前校准状态仍是 `insufficient_labels`。
- 质量门控仍有 OpenCV Haar 代理逻辑，后续需要用 MediaPipe 检测结果补强人脸数量、姿态和关键点可信度。
- 尚未提供生产 API 或正式业务前端；当前只有人工复核标注工具页面。

## 3. MVP 范围

### P0

- 项目环境标准化：所有 Python 命令运行在 `anti-spoofing_scc_175`。
- MediaPipe 检测基座：本地图片通过 Face Landmarker 输出 landmarks、blendshapes 和 transformation matrix。
- 人脸对称性算法核心：输入结构化人脸关键点，输出对称性特征、辅助置信度和解释项；当前核心判断特征为 `bsdiff_mouthFrown_abs`、`raw_all_mesh_region_point_spread_asym`、`bsdiff_mouth_abs`、`raw_lip_midline_deviation`、`raw_mouth_corner_vertical_asym`。
- 细分属性：嘴角下垂、眼裂开合差异、眉部高度差异、中线偏移、全局镜像误差。
- 质量门控：基础图像质量、人脸数量/大小代理、关键点置信度、头部姿态、缺失关键点。
- 数据集采集：从本地 media manifest 生成 V1 keypoint dataset。
- 医疗安全边界：结果仅作为脑卒中/面瘫预警参考，不输出诊断结论。
- BMAD 规划：维护 Product Brief、PRD、Architecture、Epics、Roadmap。

### P1

- 数据盘点：识别现有 xlsx 和 media manifest 的字段、标签、行数、空值、枚举值和时间范围。
- 评估报告：冻结测试集 precision、TP、FP、阈值、阳性规则和样本级明细。
- 质量门控增强：用 MediaPipe 检测结果替换或补充 OpenCV Haar 代理。
- 批量报告输出：生成 Markdown/CSV/JSON 结果包。

### 暂不纳入

- 自动医学诊断结论。
- 生产级模型训练。
- 用户端应用。
- 在线推理服务。
- 视频动作时序建模。
- 侧脸、舌像等非 V1 主评分输入。

## 4. 功能需求

| ID | 功能 | 验收标准 | 当前状态 |
| --- | --- | --- | --- |
| FR-001 | 环境激活 | `source scripts/activate_project_env.sh` 后 `python` 指向 `anti-spoofing_scc_175` | 已完成 |
| FR-002 | 命令包装 | `scripts/run_in_project_env.sh python --version` 返回 Python 3.9.25 | 已完成 |
| FR-003 | 数据盘点 | 对每个 xlsx 输出 sheet、字段、行数、缺失率 | 待完成 |
| FR-004 | 数据字典 | 生成字段级说明草案，明确未知字段 | 待完成 |
| FR-005 | 质量报告 | 生成可审阅的数据质量问题列表 | 部分完成，已有质量门控产物 |
| FR-006 | 对称性评分 | 对结构化人脸关键点输出 `advisory_confidence`、`risk_level` 和解释项 | 已完成 baseline |
| FR-007 | BMAD 规划 | `_bmad-output/planning-artifacts` 下规划文档完整存在并随进展更新 | 已更新 |
| FR-008 | 医疗安全声明 | 所有结果明确标注为预警辅助，不能替代临床诊断 | 已完成 baseline |
| FR-009 | 测试集 precision 评估 | 在冻结测试集上输出 `precision = TP / (TP + FP)`，并提供 TP、FP、阈值、阳性规则、测试集版本、模型版本和样本级预测明细 | 已生成当前技术 baseline 报告，待冻结标签/测试集确认 |
| FR-010 | MediaPipe 本地图片检测 | 本地图片可输出 Face Landmarker JSON，包含 semantic landmarks、raw landmarks、blendshapes 和 transformation matrix | 已完成 |
| FR-011 | V1 关键点数据集采集 | 从本地 dataset/media manifest 批量生成 keypoint dataset | 已完成 by-name 全量版本：`datasets/facesym_v1_by_name_20260119` |
| FR-012 | 检测与评分串联 | 单张本地图片可选执行检测后直接输出对称性分析结果 | 已完成 |
| FR-013 | 阶段结果与报告 | 推荐数据流程每个阶段输出可审阅结果和报告 | 已完成当前 by-name 流程，输出位于 `metadata/*` 与 `reports/*` |
| FR-014 | 五类部件级属性 | 输出口部、眼部、眉部、鼻面中线、面部轮廓五类部件级 `score/symmetry_score/side/confidence` | 已完成 |
| FR-015 | 全图片无质量门控对比 | 读取所有 `media_type=image`，跳过质量门控并输出可对照报告 | 已完成，输出位于 `datasets/facesym_v1_all_images_no_gate_20260119` |
| FR-016 | V1.1 患病/不患病预测 | 基于 MediaPipe 478 点和 blendshape 派生特征输出患者级弱监督预测 | 已完成，输出 `metadata/11_v11_role_aware_predictions.csv` |
| FR-017 | HB proxy 分级 | 输出 I-VI 技术代理等级、组件分数、Grade V+ 人脸不对称清单和等级差异特征 | 已完成，输出 12/14 阶段产物 |
| FR-018 | 人工复核标注 | 提供页面查看 6 个核心 role 特征点图并保存人工标签，用于后续校准 | 已完成本地/远程标注入口，待填充标签 |
| FR-019 | MediaPipe 全流程汇总 | 输出最大特征差异项和患者级预测结果的单一汇总报告 | 已完成，输出 20 阶段产物 |
| FR-020 | 核心对称特征判断 | 基于两批数据复核，将 `bsdiff_mouthFrown_abs`、`raw_all_mesh_region_point_spread_asym`、`bsdiff_mouth_abs`、`raw_lip_midline_deviation`、`raw_mouth_corner_vertical_asym` 作为当前人脸是否对称的核心关键点判断特征；报告必须展示 role、特征值和关键点可视化证据 | 已指定，待接入下一版评分/报告规则 |

## 5. 非功能需求

- 可复现：所有脚本必须说明运行环境和输入输出。
- 可追踪：不得覆盖原始 xlsx；模型文件、脚本和输出版本需要记录。
- 合规：医疗或个人数据处理前必须确认脱敏策略和访问边界。
- 可维护：检测层与特征/风险层解耦，便于后续替换模型或检测器。
- 可审计：precision 报告必须包含样本级输入、输出、阈值和失败原因。
- 输入可评分性：核心对称特征只允许在 MediaPipe 输出满足 `detection_status=detected`、`raw_landmarks=478`、mouth blendshape 完整、可完成面部中线和眼距归一化的图片上计算；不满足时必须输出不可评分或需复核原因。

## 6. 风险

- 标签定义不清会导致 precision 无法解释。
- 冻结测试集如果按图片随机切分，可能出现同一患者泄漏到训练/评估两侧。
- MediaPipe latest 模型若不固定 checksum，会影响长期复现。
- 低质量图像、侧脸、遮挡和多人脸会导致关键点漂移或错误评分。
- 医疗预警场景需要严格合规、免责声明、临床验证和人工复核流程。

## 7. 开放问题

1. V1 首批评估样本已使用 `front`、`smile`、`teeth`，是否需要纳入其他角色？
2. 当前 patient outcome 标签是否可作为验收标签，还是需要人工面部不对称标注？
3. 当前患者级分层切分是否可冻结为正式测试集？
4. 当前 validation 自动阈值是否可接受，precision 阈值和阳性规则由谁最终确认？
5. 是否需要为 `models/mediapipe/face_landmarker.task` 增加 checksum、模型卡和审批记录？
6. Grade V+ 人脸不对称输出是否作为当前业务输出阈值，还是等待人工标签校准后再冻结？
