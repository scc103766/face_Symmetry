# 会话归档说明

每次对话结束后，PM Agent 按会话目的分类归档：

```
sessions/
├── project/     ← 项目推进相关：需求讨论、架构决策、任务管理、里程碑推进
└── meta/        ← 非项目相关：工具准备、知识问答、代理配置、环境调试
```

## 分类规则

| 类型 | 示例 | 归档到 |
|------|------|--------|
| 需求讨论、技术选型 | "为什么不直接用深度学习做对称性判断" | `sessions/project/` |
| 任务审批、里程碑推进 | "批准M3-01，搭建部署框架" | `sessions/project/` |
| 架构设计 | "规则62 vs 63 的选型理由" | `sessions/project/` |
| 代码审核 | "Engineer的对称性特征计算对吗" | `sessions/project/` |
| Skill 安装/配置 | "安装 pm-workflow skill" | `sessions/meta/` |
| 代理环境调试 | "conda环境怎么激活" | `sessions/meta/` |
| 知识问答 | "blendshape 和 landmark 的区别" | `sessions/meta/` |
| 工具链搭建 | "Codex vs pi 的区别" | `sessions/meta/` |

## 文件命名

```
YYYY-MM-DD_简短描述.md
```

示例：
- `2026-06-08_规则63优化讨论.md` → `sessions/project/`
- `2026-06-08_PM环境搭建.md` → `sessions/meta/`
