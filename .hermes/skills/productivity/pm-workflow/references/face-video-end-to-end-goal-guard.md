# Face-video end-to-end goal guard for face-health projects

Use this note when working on face-health / Cardiovascular / diabetes “扫脸看健康” projects.

## Durable rule

For these projects, the final product goal is fixed: use face video end-to-end to assess health risk.

For the Cardiovascular project specifically, the immutable goal is:

> “扫脸看健康”：通过人脸视频端到端完成心血管病风险评估。

Intermediate work may include structured health records, NHANES/BRFSS/Kaggle/Mymensing baselines, Framingham/ASCVD formulas, rPPG/HRV extraction, Face ROI, label taxonomy, leakage checks, and dataset audits. These are support paths, not pivots away from the face-video product goal.

## PM behavior

When proposing tasks, reports, roadmaps, or documentation:

1. State how each task supports the face-video end-to-end goal.
2. Mark structured/tabular baselines as medical priors, teacher signals, validation references, or fusion baselines — not final product form.
3. Treat Route C face/video capabilities as mainline: Face ROI, rPPG, HR/HRV, SQI, video quality gates, and multimodal fusion.
4. Do not let dataset audits or table-model benchmarks become the project objective.
5. If a task cannot serve the face-video goal, label it auxiliary/exploratory and ask before spending effort.

## Documentation wording

Prefer wording like:

- “结构化 baseline 是人脸视频最终系统的医学先验、teacher signal、融合参照和验证基线，不是项目终点。”
- “最终目标固定为扫脸看健康：通过人脸视频端到端完成心血管病风险评估。”
- “后续所有任务单都应说明它如何服务于人脸视频端到端心血管风险评估。”

Avoid wording that implies the project goal has become:

- pure tabular CVD prediction;
- pure questionnaire risk scoring;
- pure Framingham/ASCVD calculator;
- dataset benchmark collection;
- rPPG signal extraction without connection to end-to-end risk assessment.
