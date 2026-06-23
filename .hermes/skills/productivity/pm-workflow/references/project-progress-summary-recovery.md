# Project progress summary recovery

Use when a user says they are losing track of a long PM-mode project, asks what has been done, or wants a reset of project control.

## Trigger phrases

- “我对项目进度有点失去掌控了”
- “整理一下我们做了什么”
- “当前进度是什么”
- “在总体规划中处于什么位置”
- “给我一个项目总览/进度总览”

## Workflow

1. Load PM context first: `PROJECT_CONTEXT.md`, `WORK_STATUS.md`, recent `tasks/done/*.md`, and key reports produced since the last summary.
2. Produce a structured progress summary before proposing new execution.
3. If the user approves, write a durable root-level file named `PROJECT_PROGRESS_SUMMARY.md`.
4. The summary should be navigational, not a raw log dump.
5. Verify by reading the created file before reporting completion.

## Recommended sections

- One-sentence project state.
- Overall roadmap and current position.
- What has been completed by milestone.
- New documents.
- New code/scripts.
- Important output directories and artifacts.
- Current conclusions.
- Claims that are explicitly not supported yet.
- Technical debt and risks.
- Git/repository status if relevant.
- Next-step decision tree.
- PM recommendation.

## Quality rules

- Distinguish “completed engineering artifact” from “research hypothesis”.
- Keep clinical/medical caveats explicit.
- Do not continue downstream work while doing the reset; the deliverable is project control.
- Prefer file paths over pasted code.
- For long health/ML projects, state whether the current evidence is benchmark, exploratory, or product/clinical-grade.
