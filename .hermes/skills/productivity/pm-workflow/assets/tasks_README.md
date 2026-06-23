# 任务队列说明

> PM Agent 写入 `queue/` → Engineer (Codex) 读取执行 → 结果写入 `done/`

## Engineer Agent 操作流程

1. 在 VS Code 中打开本项目，启动 Codex 对话
2. 对 Codex 说：**"读取 tasks/queue/ 下的任务，按优先级执行"**
3. 执行完毕后，将开发日志 + 结果写入 `tasks/done/task_{编号}_report.md`
4. 完成后通知 PM Agent 审核

## 文件命名规则

- 任务单：`tasks/queue/task_{编号}.md`
- 完成报告：`tasks/done/task_{编号}_report.md`
- 退回任务：`tasks/rejected/task_{编号}_rejected.md`

## 优先级

- P0 > P1 > P2 > P3
- 同优先级按编号顺序执行

## 任务单格式 (PM → Engineer)

```markdown
# 任务单 #{编号}

**任务名称**：[描述]
**优先级**：P0/P1/P2/P3

## 任务描述
[清晰描述要做什么]

## 输出要求
- [ ] [产出1]
- [ ] [产出2]

## 验收标准
1. [标准1]
2. [标准2]
```

## 开发日志格式 (Engineer → PM)

Engineer 完成后必须输出包含以下内容的开发日志：
- 📝 开发过程（分步骤）
- 🧠 开发思路（为什么这样做）
- 📊 代码变更清单（新增/修改/删除）
- 💡 核心代码解读（关键逻辑逐段解释）
- ⚠️ 遇到的问题与解决方案
