# FaceSymAi 项目文档索引

当前项目按 BMAD-METHOD 组织规划与实施资料。

## 基础环境

- Conda 环境：`anti-spoofing_scc_175`
- Python：`/home/scc/anaconda3/envs/anti-spoofing_scc_175/bin/python`
- 入口：`source scripts/activate_project_env.sh`
- 命令包装：`scripts/run_in_project_env.sh <command>`

## Codex 开发环境

- Codex 会话池：`docs/development/codex/FACESYMAI_CODEX_SESSION_POOL.md`
- Codex 代理链路设置手册：`docs/development/codex/CODEX_PROXY_CHAIN_SETUP.md`

## BMAD 资料

- 项目上下文：`_bmad-output/project-context.md`
- 输入摘要：`_bmad-output/planning-artifacts/00-bmad-input-summary.md`
- 产品简报：`_bmad-output/planning-artifacts/product-brief.md`
- PRD：`_bmad-output/planning-artifacts/prd.md`
- 架构决策：`_bmad-output/planning-artifacts/architecture-decision.md`
- 史诗与待办：`_bmad-output/planning-artifacts/epics-and-backlog.md`
- 路线图：`_bmad-output/planning-artifacts/implementation-roadmap.md`

## 算法文档

- V1 当前计算过程技术文档：`docs/algorithm/facesym-v1-calculation-technical-document.md`
- MediaPipe 输出到配对差异与特征差异处理说明：`docs/algorithm/mediapipe-pair-and-feature-difference-processing.md`
- MediaPipe 最大差异主证据来源与数据集形成原因说明：`docs/algorithm/mediapipe-largest-feature-difference-evidence-explanation.md`
- MediaPipe 主证据特征在规则测试集上的有效性验证：`docs/algorithm/mediapipe-evidence-validation-on-rule-test-set.md`
- 不使用人工轻微不对称标注的特征验证集构建方案：`docs/algorithm/no-manual-label-feature-validation-dataset-design.md`
- 人脸对称性分析算法设计：`docs/algorithm/facial-symmetry-analysis.md`
- 人脸对称性判断算法技术方案：`docs/algorithm/facial-symmetry-technical-solution.md`
- 人脸对称性判断算法详细技术文档：`docs/algorithm/facial-symmetry-technical-solution-detailed.md`
- 人脸对称性判断算法研发计划：`docs/algorithm/facial-symmetry-rd-plan.md`
- 人脸对称性判断算法详细研发文档：`docs/algorithm/facial-symmetry-rd-plan-detailed.md`
- V1 静态图片输入管理规范：`docs/algorithm/input-management-spec.md`
- V1 输入质量门控规范：`docs/algorithm/quality-gate-spec.md`
- 任务定义与评估验收协议：`docs/algorithm/evaluation-protocol.md`

## 数据集与数据流程

- V1 关键点数据集采集说明：`docs/datasets/v1-keypoint-dataset.md`
- 当前 by-name 推荐数据处理流程：`docs/datasets/facesym-v1-by-name-data-flow.md`
- 脑卒中预警 App 规则测试集构建说明：`docs/datasets/stroke-warning-app-rule-test-set.md`

## 当前输入文件

- `脑卒中数据采集-审核导出-20260119.xlsx`
- `脑卒中预警报告老来健康app线上_2026-05-08.xlsx`

这些文件目前视为业务输入资料，不在没有明确任务时改动。
