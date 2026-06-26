# FaceSymAi 双代理协作方案

> 可复用的 PM + Engineer 双代理项目管理模式
> 版本：v2.5.0 | 日期：2026-06-24

---

## 1. 架构概览

```
┌─────────────────────────────────────────────────────┐
│                      用户（最终决策者）                 │
│                    审批 / 提需求 / 下发任务              │
└──────────┬──────────────────────────┬───────────────┘
           │                          │
    ┌──────▼──────┐           ┌──────▼──────┐
    │  PM Agent   │           │  Engineer   │
    │  (Hermes)   │──任务单──→│  (Codex)    │
    │             │←──报告───│             │
    │ 产品+教师+把关│           │ 代码执行者    │
    └─────────────┘           └─────────────┘
           │                          │
    ┌──────▼──────────────────────────▼──────┐
    │           tasks/ 文件队列               │
    │  queue/（待执行） done/（已完成）         │
    └────────────────────────────────────────┘
```

**三个角色**：

| 角色 | 运行平台 | 职责 |
|------|---------|------|
| **用户** | — | 最终决策者，审批所有推进，手动下发 Engineer 任务 |
| **PM Agent** | Hermes Agent | 需求拆解、方案设计、技术教学、任务编排、产出审核 |
| **Engineer Agent** | Codex CLI | 代码执行、测试验证、报告产出、建议反馈 |

---

## 2. 通信协议

PM ↔ Engineer 通过 `tasks/` 文件队列异步通信，不依赖实时对话。

```
PM 写入 tasks/queue/task_XXX.md     →  Engineer 读取并执行
Engineer 写入 tasks/done/task_XXX_report.md  →  PM 读取并审核
```

**task_XXX.md 结构**：
```markdown
## 🎫 任务单 #TASK-ID

**任务名称**：...
**优先级**：P0/P1
**依赖**：...

## 🔧 角色与约束（Engineer 身份）
（注入 19 条约束：执行边界/决策权限/产出规范/思考反馈/禁止事项）

## 📝 任务描述
（子任务拆解 + 代码示例 + 阈值常量）

## 验证 / 目标指标 / 环境
```

**task_XXX_report.md 结构**：
```markdown
# TASK-ID Completion Report

## 开发过程 / 开发思路 / 代码变更清单
## 核心代码解读 / 遇到的问题与解决方案 / 验证结果
## 💡 Engineer 建议（方案改进/不合理反馈/后续优化/风险提示）
```

---

## 3. 审批流

```
用户提需求
  → PM 设计方案 + 教学解释
  → 用户审批（批准/展开讲/换方案）
  → 批准后 PM 写入 tasks/queue/
  → 用户手动下发 Codex："读取并执行 tasks/queue/TASK-ID.md"
  → Engineer 执行（可思考分析）→ 写入 tasks/done/TASK-ID_report.md
  → PM 解读产出 + Engineer 建议 → 提交用户审核
  → 通过 → 更新 PROJECT_CONTEXT.md + WORK_STATUS.md
```

**铁律**：用户没有明确说"批准"/"通过"之前，PM 不推进。

---

## 4. PM Agent 配置

### 4.1 身份定义（pm-workflow skill）

PM 通过 Hermes 的 `pm-workflow` skill 获得三重身份：

| 身份 | 说明 |
|------|------|
| 🎯 产品经理 | 需求拆解、架构设计、任务编排、质量审核 |
| 📖 技术教师 | 解释原理、设计原因、替代方案、常见坑 |
| 🔍 把关前置 | 提交审批前自审任务合理性 |

### 4.2 安装

```bash
# 从 Git 仓库安装
git clone git@github.com:scc103766/face_Symmetry.git
cp -r face_Symmetry/.hermes/skills/productivity/pm-workflow ~/.hermes/skills/productivity/

# 或放入目标项目的 .hermes/skills/
cp -r face_Symmetry/.hermes/skills/productivity/pm-workflow /path/to/project/.hermes/skills/
```

### 4.3 启动

```bash
# 在 Hermes 中输入
开启 PM 工作模式，继续 <项目名>。
```

---

## 5. Engineer Agent 配置

### 5.1 持久身份（AGENTS.md）

在项目根目录放置 `AGENTS.md`，Codex 启动时自动加载：

```markdown
# Engineer Agent — <项目名>

你是本项目的 Engineer Agent。
运行平台：Codex CLI | 模型：GPT-5.5，reasoning_effort=xhigh
上级：PM Agent + 用户

## 持久约束
- 只执行 tasks/queue/ 中经 PM 批准的任务
- 不自行变更需求、架构、技术选型
- 完成后按格式写报告到 tasks/done/
- 报告末尾追加「💡 Engineer 建议」节
- 阻塞时停止并写清原因，不绕过
- 不 commit/push，不修改环境，不碰凭据

## 任务接收
读取并执行 tasks/queue/ 中用户指定的任务单。
```

### 5.2 下发命令

```
读取并执行 /path/to/project/tasks/queue/TASK-ID.md
```

---

## 6. 项目骨架

```
project/
├── AGENTS.md                  ← Engineer 持久身份
├── PROJECT_CONTEXT.md         ← 项目背景/架构/里程碑（PM 维护）
├── WORK_STATUS.md             ← 当前进度/中断点/技术债（PM 维护）
├── tasks/
│   ├── queue/                 ← PM 写入待执行任务
│   ├── done/                  ← Engineer 写入完成报告
│   └── rejected/              ← PM 退回的任务
├── sessions/
│   ├── project/               ← 项目推进会话归档
│   └── meta/                  ← 工具/知识/环境会话归档
└── .hermes/skills/            ← 项目级 skill（可选）
```

### 初始化

```bash
~/.hermes/skills/productivity/pm-workflow/scripts/init.sh /path/to/project
```

---

## 7. 状态追踪与断点恢复

### WORK_STATUS.md 结构

```markdown
## 🔄 当前进行中    ← 中断恢复检查第一优先级
## 📋 待审批队列
## 📝 最近会话记录
## 🔧 待处理异常 / 技术债
```

### 断点恢复检查

PM 每次启动自动扫描：
1. `WORK_STATUS.md` 当前进行中 → 有则汇报中断
2. `tasks/queue/` vs `done/` → 有孤儿任务则汇报
3. `sessions/` 缺少完成标记 → 可能中断
4. 待审批队列积压 → 提醒

---

## 8. Engineer 思考与反馈（v2.5.0）

Engineer 不是无脑执行器：

| 权限 | 说明 |
|------|------|
| 🧠 执行中思考 | 编码前分析可行性、推理根因 |
| 💡 执行后建议 | 报告末尾「💡 Engineer 建议」：方案改进/不合理反馈/后续优化/风险提示 |
| 🚩 诚实反馈 | 目标不可达时如实报告，不造假 |

PM 处理建议的四种路径：
- 合理紧急 → 开新任务单
- 合理非紧急 → 记入技术债
- 需澄清 → tasks/ 文件队列沟通
- 不合理 → 审核结论说明原因

---

## 9. 跨机器迁移

```bash
# 导出项目状态
~/.hermes/skills/productivity/pm-workflow/scripts/export.sh

# 生成 pm-state-YYYY-MM-DD.tar.gz（含 PROJECT_CONTEXT.md + WORK_STATUS.md + tasks/ + sessions/）

# 导入
~/.hermes/skills/productivity/pm-workflow/scripts/import.sh pm-state-YYYY-MM-DD.tar.gz
```

---

## 10. FaceSymAi 实践经验

### 已形成的迭代模式

```
M3-P0-03: 侧视检测 (478几何→blendshape)              三轮迭代
M3-P0-04: 露齿+色差 (69.7%→75.0%)                    单任务
M3-P0-05: 露齿+边缘+Pose (边际改善)                    单任务
M3-P0-06: 8790自动角色推断 (15行,直接执行)             无需Engineer
M4-VIDEO-01: 视频抽帧 (Pipeline第一步)                 待执行
M4-ACTION-VIDEO: 视频五动作帧API                       待执行
```

### 关键教训

1. **报告过期检测**：当代码在报告写完后继续演进，报告会残留旧指标。PM 审核时必须对比报告/代码/WORK_STATUS 三者一致性。
2. **小任务直接执行**：15 行以内的配置级改动（如 M3-P0-06），PM 可直接执行不需要经过 Engineer。
3. **阈值校准是关键**：HSV/Sobel 的种子阈值几乎都需要在全量数据上重新校准。
4. **特征分布重叠时停止硬调**：当多轮迭代只有边际改善时（M3-P0-05），接受当前基线，转向新信号。

---

## 11. 文件清单

| 文件 | 说明 |
|------|------|
| `AGENTS.md` | Engineer 持久身份（Codex 自动加载） |
| `PROJECT_CONTEXT.md` | 项目全貌：目标/架构/里程碑/决策记录 |
| `WORK_STATUS.md` | 当前进度/中断点/技术债 |
| `tasks/queue/` | 待执行任务单 |
| `tasks/done/` | 已完成报告 |
| `sessions/project/` | 项目推进会话归档 |
| `sessions/meta/` | 工具/知识会话归档 |
| `docs/` | 技术文档（API/指标/SDK） |
| `.hermes/skills/productivity/pm-workflow/` | PM 工作流 skill |
