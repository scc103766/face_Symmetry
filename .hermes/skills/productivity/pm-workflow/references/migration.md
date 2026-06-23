# PM Workflow 迁移指南

> 如何在项目之间、机器之间迁移 PM 工作模式和项目状态。

---

## 1. 迁移场景总览

| 场景 | 操作 | 工具 |
|------|------|------|
| **新项目启动** | 从头搭建 PM 骨架 | `scripts/init.sh` |
| **换机器继续** | 导出状态 → 传输 → 导入 | `scripts/export.sh` → `scp` → `scripts/import.sh` |
| **多项目管理** | 为每个项目独立初始化 | 对每个项目目录运行 `init.sh` |
| **归档旧项目** | 导出最终状态，删除骨架 | `export.sh` → 保存归档 → 清理项目 |
| **克隆项目继续** | 在新目录恢复之前的 PM 状态 | `init.sh` + `import.sh --force` |

---

## 2. 安装 Skill

### 方式 A：全局 Skill（当前机器永久可用）

```bash
# 从 git 安装
hermes skills install git:github.com/user/pm-workflow

# 从本地目录安装
hermes skills install /path/to/pm-workflow

# 手动复制（无需 hermes skills install）
cp -r /path/to/pm-workflow ~/.pi/agent/skills/
```

### 方式 B：项目级 Skill（跟随项目 git 仓库）

```bash
mkdir -p .pi/skills/
cp -r /path/to/pm-workflow .pi/skills/
```

### 方式 C：作为 pi package 发布

将此目录发布到 npm 或 git 仓库，其他人可通过 `hermes skills install` 一键安装。

---

## 3. 初始化新项目

```bash
# 进入项目目录，运行初始化
cd /path/to/new-project
~/.hermes/skills/productivity/pm-workflow/scripts/init.sh

# 或指定目标目录
~/.hermes/skills/productivity/pm-workflow/scripts/init.sh /path/to/new-project

# 强制覆盖已有骨架
~/.hermes/skills/productivity/pm-workflow/scripts/init.sh . --force
```

初始化后生成：
```
project/
├── PROJECT_CONTEXT.md     ← 需要你填充项目信息
├── WORK_STATUS.md         ← 自动维护
├── tasks/
│   ├── README.md
│   ├── queue/
│   ├── done/
│   └── rejected/
└── sessions/
    ├── README.md
    ├── project/
    └── meta/
```

然后编辑 `PROJECT_CONTEXT.md` 填入项目名称、目录、阶段等基本信息，即可启动 PM 工作模式。

---

## 4. 跨机器迁移

### 4.1 在源机器导出

```bash
cd /path/to/source-project
~/.hermes/skills/productivity/pm-workflow/scripts/export.sh

# 指定输出路径
~/.hermes/skills/productivity/pm-workflow/scripts/export.sh ~/backups/myproject-$(date +%Y%m%d).tar.gz
```

导出内容：
- `PROJECT_CONTEXT.md` — 完整的项目上下文
- `WORK_STATUS.md` — 工作状态与中断点
- `tasks/` — 全部任务队列（含 queue/done/rejected）
- `sessions/` — 全部会话归档（含 project/meta）
- `MANIFEST.json` — 导出元数据

### 4.2 传输到目标机器

```bash
scp pm-state-2026-06-10.tar.gz user@target-machine:/path/to/
# 或 U盘、网盘、rsync 等任意方式
```

### 4.3 在目标机器导入

```bash
cd /path/to/target-project
~/.hermes/skills/productivity/pm-workflow/scripts/import.sh /path/to/pm-state-2026-06-10.tar.gz

# 导入到指定目录 + 强制覆盖
~/.hermes/skills/productivity/pm-workflow/scripts/import.sh backup.tar.gz /target/dir --force
```

### 4.4 导入后启动

对 PM Agent 说「启用 PM 工作模式」→ PM 自动检测 `WORK_STATUS.md`：
- 若有中断任务 → 汇报给你，询问是否继续
- 若无中断 → 汇报项目就绪

---

## 5. 导出/导入的边界

### ✅ 会被迁移的内容

| 内容 | 文件 | 说明 |
|------|------|------|
| 项目上下文 | `PROJECT_CONTEXT.md` | 项目名称、架构、里程碑、代码资产等 |
| 工作状态 | `WORK_STATUS.md` | 当前进行中任务、待审批队列、中断点 |
| 任务队列 | `tasks/queue/` | 待 Engineer 执行的任务单 |
| 完成报告 | `tasks/done/` | Engineer 完成后的开发日志 |
| 退回任务 | `tasks/rejected/` | 被退回的任务记录 |
| 项目会话 | `sessions/project/` | 需求讨论、架构决策等历史 |
| 元会话 | `sessions/meta/` | 工具配置、知识问答等历史 |

### ❌ 不会被迁移的内容

| 内容 | 原因 |
|------|------|
| 项目源代码 | PM 工作模式只管理流程，不管理代码 |
| 数据库/模型文件 | 属于项目资产，非 PM 状态 |
| `.git/` | 通过 git 独立管理 |
| 环境变量/密钥 | 安全考虑，需手动配置 |

---

## 6. 多项目管理

PM 工作模式支持同时管理多个项目。每个项目的 PM 状态完全隔离：

```
~/projects/
├── project-a/
│   ├── PROJECT_CONTEXT.md   ← 项目 A 的上下文
│   ├── WORK_STATUS.md
│   ├── tasks/
│   └── sessions/
├── project-b/
│   ├── PROJECT_CONTEXT.md   ← 项目 B 的上下文
│   ├── WORK_STATUS.md
│   ├── tasks/
│   └── sessions/
└── project-c/
    ├── PROJECT_CONTEXT.md   ← 项目 C 的上下文
    ├── WORK_STATUS.md
    ├── tasks/
    └── sessions/
```

在不同项目目录中启动 PM 时，PM Agent 读取对应目录的 `PROJECT_CONTEXT.md`，互不干扰。

---

## 7. 常见问题

### Q: 导入后 Engineer 任务还能继续吗？
A: 能。`tasks/queue/` 中的任务单被完整保留。工程师在新机器上读取即可继续执行。

### Q: 两台机器同时工作会冲突吗？
A: PM 状态文件是普通文本文件，建议用 git 管理以避免冲突。或者约定一台机器工作完成后 export → 另一台 import。

### Q: 如何清理旧项目的 PM 状态？
A: 删除 `PROJECT_CONTEXT.md`、`WORK_STATUS.md`、`tasks/`、`sessions/` 即可。建议先 `export.sh` 归档。

### Q: 能否只导出中断点（不导出已完成任务）？
A: 当前导出是完整导出。如需精简，手动编辑归档删除不需要的文件即可。
