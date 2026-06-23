# Approval scope and artifact hygiene notes

Use this reference when operating in PM 工作模式 for research/prototype repos.

## Approval scope

- Treat “批准执行 X” as approval for X only.
- Treat “批准只执行 X” as an explicit scope limiter: do not opportunistically run adjacent tasks, train extra models, push GitHub changes, or continue a previously pending workstream unless it is a direct prerequisite for X.
- If the user says “进入 X” after a prior plan, do not assume execution approval unless the local PM convention has already made that phrase equivalent. Confirm whether this means “设计/进入方案” or “批准执行”.
- Keep unrelated in-flight tasks paused when the user switches topics; resume only when the latest user message asks for them.

## Artifact hygiene before publishing a research repo

- Publish code, docs, PM done reports, configs, and small reproducible metrics/reports.
- Exclude raw/private/large/generated assets such as `data/`, `models/`, `features/`, `.npz`, `.xpt`, `.pkl`, cloned external baselines, and local cache repos.
- Redact API tokens in scripts and reports; prefer command-line arguments or environment variables such as `FACESYM_API_URL`.
- Run a staged-file policy check before commit so private datasets, model weights, and transient task queues are not uploaded.
