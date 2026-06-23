# Project code walkthrough recovery

Use when the user says code has accumulated and they need to review what each file does, why it exists, or how the pieces fit together.

## Trigger phrases

- “现在产生了很多代码，我需要每一个都看一下”
- “这些代码分别是干什么的”
- “为什么要这样做”
- “带我读一下代码”
- “项目代码太多，帮我梳理”

## Workflow

1. Do not start new engineering work or downstream model experiments while doing the reset. The deliverable is project control and code comprehension.
2. Gather current state from `PROJECT_CONTEXT.md`, `WORK_STATUS.md`, `tasks/done/*.md`, key reports, and the current git status.
3. Inventory code by project layer rather than raw filename order:
   - Core package (`src/`): data, models, features, evaluation, API/config.
   - Experiment scripts (`scripts/`): benchmark, dataset conversion, preprocessing, analysis.
   - Tooling (`tools/`): agent adapters, one-off infrastructure.
   - Tests (`tests/`): smoke, data, adapter tests.
4. For each important file, explain in this compact structure:
   - Purpose: what problem the file solves.
   - Inputs: files/tables/APIs it reads.
   - Outputs: artifacts it writes or objects it returns.
   - Key functions/classes with `path:line` references when available.
   - Design reason: why this step exists in the project pipeline.
   - Status: mainline / auxiliary / historical / tooling / test.
5. Preserve the project’s evidence boundaries. In health/ML projects, distinguish production baseline, benchmark evidence, exploratory hypothesis, and unsupported clinical claims.
6. Recommend a reading order that follows the pipeline, not alphabetic order.
7. If the user approves, write a durable root-level `CODE_WALKTHROUGH.md` and read it back to verify. Do not modify code, clean queues, train models, or commit unless separately approved.

## Recommended sections for `CODE_WALKTHROUGH.md`

- One-sentence codebase state.
- Suggested reading order.
- Directory map.
- Mainline pipeline files.
- Auxiliary/debug/tooling files.
- Tests and what they protect.
- Artifact/report map.
- Known risks and stale/historical code.
- Next review checkpoints.

## Quality rules

- Do not paste entire source files into the chat; summarize and cite paths/lines.
- When the user is learning, include “why” for each file, not only “what”.
- Mark exploratory ML scripts clearly so later agents do not accidentally treat them as validated product code.
- If many files are untracked, explicitly state that the walkthrough reflects the working tree, not necessarily committed repository state.
