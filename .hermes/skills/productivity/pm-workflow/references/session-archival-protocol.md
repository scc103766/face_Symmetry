# PM Workflow Session Archival Protocol

Use this reference when operating PM 工作模式 in a project that separates durable conversation records into `sessions/project/` and `sessions/meta/`.

## Purpose

The split keeps project progress, decisions, and task execution separate from tool setup, knowledge Q&A, agent configuration, and workflow maintenance. This makes breakpoint recovery cleaner and avoids mixing project state with meta chatter.

## Classification Rules

Archive into `sessions/project/` when the conversation changes or reviews project state:

- Requirements, scope, product decisions, milestones
- Architecture or technical solution decisions
- Task approval, task dispatch, task completion review
- Code/model/data validation that affects the project roadmap
- Reports that should inform `PROJECT_CONTEXT.md` or `WORK_STATUS.md`

Archive into `sessions/meta/` when the conversation concerns how the agent or tools work:

- Skill installation, migration, or validation
- Hermes/pi/Codex/Claude configuration
- Environment/toolchain setup and troubleshooting
- Knowledge Q&A or teaching that is not itself a project milestone
- PM workflow or session-management maintenance

If a single real conversation contains both classes, create two concise session files rather than forcing everything into one bucket.

## Required Completion Marker

Every session file must end with exactly one of these markers.

Successful/normal closure:

```markdown
## ✅ 会话完成

**完成时间**：YYYY-MM-DD HH:MM 或 YYYY-MM-DD  
**结论**：[本次会话的 durable decision/result]  
**下一步**：[下一步恢复点 or “无”]
```

Known interruption:

```markdown
## ⚠️ 会话中断

**中断时间**：YYYY-MM-DD HH:MM  
**中断前状态**：[当时在做什么、做到哪里]  
**待恢复项**：[恢复时先读哪些文件/继续什么审批]
```

Do not leave archived session files without a marker. Missing markers create noisy breakpoint recovery and should be repaired before continuing project work.

## Breakpoint Recovery Check

When PM mode starts:

1. Read `WORK_STATUS.md` first.
2. Scan `sessions/project/*.md` and `sessions/meta/*.md` for missing completion/interruption markers.
3. Compare the scan with `WORK_STATUS.md` recent session records.
4. Treat “normal归档，未补标记” as a hygiene issue, not a live project blocker, but ask for approval before editing session files.
5. After repair, update `WORK_STATUS.md` so future scans stay quiet.

## Current-Session Archival Pattern

At the end of a mixed session:

1. Write a project session for project execution/results.
2. Write a meta session for tool/workflow/skill changes.
3. Update `WORK_STATUS.md` recent session records with both files.
4. Verify all session files contain markers.

## Context-Agent Handoff

Before a long PM session reaches the model context limit (this project treats 272k tokens as the hard ceiling; trigger around 250k-260k or when compression is likely), ask the user whether to enable the Hermes 上下文 Agent mechanism.

If approved:

1. Archive the current conversation into project/meta session files as appropriate.
2. Ensure every new session has a completion or interruption marker.
3. Update `WORK_STATUS.md` with the exact recovery point and pending approval.
4. Sync durable project decisions into `PROJECT_CONTEXT.md` if needed.
5. Generate a new-Hermes startup prompt that tells the next agent to load PM mode and recover from `PROJECT_CONTEXT.md`, `WORK_STATUS.md`, recent relevant sessions, and `tasks/` rather than from raw chat history.

See `references/hermes-context-agent.md` for the full protocol and prompt templates.

## Pitfalls

- Do not store task completion only in chat. Durable project progress belongs in `tasks/done/`, `WORK_STATUS.md`, and/or `sessions/project/`.
- Do not bury workflow/tool changes in project sessions; put them in `sessions/meta/`.
- Do not treat knowledge Q&A as project progress unless it produced a project decision. If it did, also sync the decision into `PROJECT_CONTEXT.md` or a project session.
- Do not run broad cleanup or rewrite historical sessions without user approval; session archival edits affect project memory.