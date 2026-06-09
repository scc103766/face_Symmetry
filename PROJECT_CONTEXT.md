# 项目上下文主记忆文件 (PM Agent Memory)

> 本文件由 PM Agent 维护，是所有代理对话的共享上下文基础。
> PM Agent 每次对话前应读取本文件以恢复项目全貌。

## 1. 项目概览

| 属性 | 值 |
|------|-----|
| 项目名称 | FaceSymAi — 人脸对称性分析 |
| 项目代号 | facesymai |
| 项目目录 | `/supercloud/llm-code/scc/scc/FaceSymAi` |
| 项目定位 | 基于人脸关键点检测的面部对称性分析，用于脑卒中/面瘫预警辅助决策支持研究 |
| 当前阶段 | V1 基线已建立，特征工程与多规则组合验证中（规则 61/62/63） |
| 创建日期 | 2025-05-18 |

## 2. 产品目标

### 2.1 用户价值
- 通过人脸图片分析面部对称性，辅助脑卒中/面瘫预警
- 输出可解释的人脸不对称判断和风险原因描述
- 为医疗决策支持系统提供人脸对称性分析能力

### 2.2 产品边界（不可逾越）
- ❌ 不作为临床诊断工具，定位为预警辅助/技术研究
- ❌ 不处理视频流，当前聚焦静态图片
- ❌ 不在没有人工标签的前提下声称医学准确率
- ✅ 基于 MediaPipe Face Landmarker 的 478 点关键点分析
- ✅ 输出用户可读的不对称描述和风险分级

## 3. 技术架构

### 3.1 总体管线
```
输入图片 → MediaPipe Face Landmarker (478 landmarks + 52 blendshapes)
  → 坐标标准化 (鼻梁中轴拟合 + roll校正 + 尺度归一化)
  → 对称性特征提取 (口/眼/眉/中线/轮廓五类)
  → 特征工程 (pair差异 / 去重推荐特征 / 稳定性加权)
  → 规则引擎判断 (单特征阈值 / 多特征加权得分)
  → 输出 (face_asymmetry_confidence + face_asymmetry_output + reason)
```

### 3.2 技术栈

| 层级 | 技术 |
|------|------|
| 语言 | Python >=3.9 |
| 环境 | conda env `anti-spoofing_scc_175` |
| 深度学习 | PyTorch 2.2.0, CUDA 12.1 |
| 人脸检测 | MediaPipe Face Landmarker (`.task` 模型) |
| 图像处理 | OpenCV 4.9, Pillow, scikit-image |
| 数据处理 | numpy, pandas, scikit-learn |
| 包管理 | setuptools + pyproject.toml |
| Agent 平台 | Codex CLI (GPT-5.5) + pi (PM Agent) + BMAD |

### 3.3 核心模块

| 模块 | 路径 | 说明 |
|------|------|------|
| 主库 | `src/facesymai/` | 核心 Python 包：landmarks, geometry, features, risk, quality, schemas, input_management |
| 离线 SDK | `modules/mediapipe_face_keypoint_detector/` | 可独立复制的 MediaPipe 关键点检测模块 |
| 分析服务 | `modules/facial_asymmetry_service/` | 62 规则 Web/API 服务 |
| 数据集 | `datasets/` | 多个数据集：by-name V1、全图片对比组、HB proxy 分级等 |
| 脚本 | `scripts/` | 检测、采集、分析、标注等入口脚本 |
| 标注工具 | `tools/face_asymmetry_label_tool.html` | 人工面部不对称标注网页 |

### 3.4 目标性能指标

| 指标 | 当前值 (62规则) | 说明 |
|------|----------------|------|
| Test Precision | 待确认 | 规则62优先推荐 |
| Combined Precision | 优于 61/63 | 62 综合最优 |
| Test Specificity | 优于 61/63 | 62 综合最优 |

## 4. 代码资产

| 目录 | 内容 | 状态 |
|------|------|------|
| `src/facesymai/` | 核心库 (landmarks, geometry, features, risk, quality, schemas) | ✅ 已建立 |
| `modules/mediapipe_face_keypoint_detector/` | 离线关键点检测 SDK | ✅ 已完成 |
| `modules/facial_asymmetry_service/` | 62 规则分析服务 | ✅ 已完成 |
| `scripts/` | 各类分析/检测/标注脚本 | ✅ 持续增加 |
| `tests/` | 测试 (61 passed) | ✅ 已建立 |
| `docs/` | 技术文档 | ✅ 已建立 |
| `tools/` | 标注网站等工具 | ✅ 已建立 |

## 5. 文档资产

| 文件 | 内容 |
|------|------|
| `docs/project-context.md` | 项目上下文（长版，BMAD 维护） |
| `docs/index.md` | 文档索引 |
| `docs/algorithm/facesym-v1-calculation-technical-document.md` | V1 计算过程技术文档 |
| `docs/algorithm/facial-symmetry-technical-solution.md` | 人脸对称性技术方案 |
| `docs/algorithm/evaluation-protocol.md` | 评估验收协议 |
| `_bmad-output/planning-artifacts/` | BMAD 产品/架构/史诗文档 |

## 6. 角色体系

### 6.0 用户（你）— 最终决策者 & 学习者
- 角色：项目所有者、最终把关人、学习者
- 权限：**所有决策必须经你批准才能推进**
- 权利：对任何方法/工具有完整知情权、否决权、审批权

### 6.1 PM Agent — 翻译官 & 把关前置
- 三重角色：产品经理 + 技术教师 + 把关前置
- 核心约束：**未经你明确批准，不得向Engineer下发任何任务**

### 6.2 Engineer Agent (Codex) — 执行者
- 职责：代码编写、脚本开发、数据分析、模型实验、测试
- 核心约束：只执行已批准的Task，不得自行变更需求
- 通信方式：通过 `tasks/` 文件队列

## 7. 当前里程碑与任务

### M1: V1 基线建立与验证 ✅
- [x] MediaPipe Face Landmarker 集成
- [x] 关键点级对称性 baseline
- [x] 质量门控
- [x] V1 by-name 数据处理流程
- [x] 全图片对比组
- [x] 基线评估 (test precision 0.662)

### M2: 特征工程与规则优化 🔄 (进行中)
- [x] 联合特征寻找 (21 去重推荐特征)
- [x] 规则 61 (Top10 患者级)
- [x] 规则 62 (稳定性加权，当前推荐)
- [x] 规则 63 (优化阈值筛选)
- [x] V1.1 HB proxy 分级
- [x] Grade V+ 专项复核
- [ ] 人工标签校准（标注中）
- [ ] 冻结测试集切分规则

### M2.5: 外部方案对比 ✅
- [x] 克隆 Djilo31 YOLO Stroke Detection
- [x] YOLO 在 V1 测试集上运行（1546张图）
- [x] 患者级聚合 + 指标对比
- [x] 定性分析 + 不一致案例可视化
- [x] 结论：FaceSymAi 规则62 全面优于 YOLO（详见 `datasets/yolo_comparison_20260608/final_comparison_report.md`）

### M3: 服务化与部署 📋 (待规划)
- [x] 62 规则分析服务封装
- [ ] API 文档完善
- [ ] 前端审核/报告页面
- [ ] 部署审计

## 8. 关键决策记录

| 日期 | 决策 | 理由 | 决策者 |
|------|------|------|--------|
| 2025-05 | 采用 MediaPipe Face Landmarker 作为检测基座 | 离线可用、478 点稠密、52 blendshapes | 项目组 |
| 2025-05 | 聚焦静态图片 V1，暂不处理视频 | 复杂度控制 | 项目组 |
| 2026-05 | 规则 62 作为当前推荐规则 | 综合 precision/specificity 最优 | 项目组 |
| 2026-06-08 | FaceSymAi 规则62 全面优于 YOLO Stroke Detection，YOLO 不作为替代方案 | YOLO specificity=0.15，无法区分不患病患者；高F1来自数据不平衡 | PM Agent + 用户审批 |
| 2026-06-08 | 规则62 确认为当前基线版本，实验性尝试（分层权重、极低FP）作为独立实验存档，不覆盖基线 | 实验方案未超越规则62；规则62 数据完好位于 `combined_disease_feature_candidates_20260529/`，实验数据在 `yolo_comparison_20260608/` | PM Agent + 用户审批 |

## 9. 会话归档

- `sessions/project/` — 项目推进（需求、架构、任务、审核）
- `sessions/meta/` — 工具准备、知识问答、环境配置

## 10. 变更日志

| 日期 | 变更内容 | 操作者 |
|------|---------|--------|
| 2026-06-08 | 初始化 PM Agent 项目上下文 | PM Agent |
| 2026-06-08 | 完成 YOLO vs FaceSymAi 全面对比（任务 #01-#03） | Codex CLI + PM Agent |
| 2026-06-08 | 分层权重优化实验（任务 #04） | Codex CLI + PM Agent |
| 2026-06-08 | 极低误检率尾部规则实验（任务 #05） | Codex CLI + PM Agent |
