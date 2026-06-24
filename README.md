# FaceSymAi — 人脸对称性分析

基于 MediaPipe Face Landmarker 的面部对称性分析工具，用于脑卒中/面瘫预警辅助决策支持研究。

⚠️ **研究原型** — 不作为临床诊断工具。

## 项目结构

```
FaceSymAi/
├── src/facesymai/              # 核心库（landmarks, geometry, features, risk, quality）
├── modules/
│   ├── mediapipe_face_keypoint_detector/  # 离线人脸关键点检测 SDK
│   └── facial_asymmetry_service/         # 规则62 Web/API 分析服务
├── scripts/                    # 分析、检测、标注、对比脚本
├── tests/                      # 测试（61 passed）
├── docs/                       # 技术文档
├── datasets/                   # 结果数据（CSV/JSON/报告，不含原始图片）
├── models/                     # MediaPipe Face Landmarker 模型
└── tasks/ + sessions/          # PM Agent 工作流
```

## 快速开始

### 环境安装

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 检测单张图片的人脸不对称

```bash
# 命令行
python -m facesymai --image path/to/face.jpg

# 或使用脚本
python scripts/detect_mediapipe_image.py --image path/to/face.jpg
```

### 启动 Web 分析服务

```bash
python modules/facial_asymmetry_service/serve_web.py --port 8790
# 访问 http://localhost:8790
```

### 运行 V1 数据处理流程

```bash
scripts/run_in_project_env.sh python scripts/build_facesym_v1_dataset_from_by_name.py \
  --output datasets/output \
  --roles front,smile,teeth
```

### 运行测试

```bash
pytest tests/ -v
```

## 当前基线

**规则62（稳定性加权特征患病判断规则）**

| 指标 | Test 集 (77 患者) |
|------|:---:|
| Precision | **0.78** |
| Recall | 0.58 |
| Specificity | **0.72** |
| F1 | 0.67 |

基于 21 个去重推荐面部对称性特征，使用跨数据 AUC 稳定性、非患者 specificity 和图片波动性进行加权。

详见 `datasets/combined_disease_feature_candidates_20260529/reports/62_stable_weighted_feature_disease_rule.md`

## 外部方案对比

与 YOLO Stroke Detection 的全面对比（2026-06-08）：

| 指标 | FaceSymAi 规则62 | YOLO |
|------|:---:|:---:|
| Precision | **0.78** | 0.68 |
| Specificity | **0.62** | 0.15 |
| 结论 | ✅ 适合临床辅助 | ❌ 误报率过高 |

详见 `datasets/yolo_comparison_20260608/final_comparison_report.md`

## 环境要求

- Python >= 3.9
- 64 位操作系统（MediaPipe 要求）
- 推荐 8GB+ RAM

## 引用

如果使用了本项目，请引用：

```bibtex
@misc{facesymai2026,
  author = {scc},
  title = {FaceSymAi — Facial Symmetry Analysis for Stroke Warning},
  year = {2026},
  url = {https://github.com/scc103766/face_Symmetry}
}
```

## 许可

研究项目，仅供学术和技术研究使用。

---

## 📋 PM Workflow Skill — 双代理项目管理

本仓库包含可迁移的 PM 工作流 skill（`pm-workflow` v2.5.0），支持 Hermes Agent 的 PM + Engineer 双代理协作模式。

### Skill 功能

| 功能 | 说明 |
|------|------|
| 项目初始化 | 一键创建 PROJECT_CONTEXT.md / WORK_STATUS.md / tasks/ / sessions/ 骨架 |
| 审批流 | PM 设计方案 → 用户审批 → Engineer 执行 → 报告 + 建议 → PM 审核 |
| 断点恢复 | 崩溃/断网后自动检测中断点，支持跨会话无缝恢复 |
| 跨机器迁移 | export.sh/import.sh 打包项目状态，可在机器间自由迁移 |
| Engineer 反馈 | Engineer 执行后可向 PM 提出方案改进建议和不合理反馈 |

### 安装

```bash
# 从本仓库安装为 Hermes 全局 skill
mkdir -p ~/.hermes/skills/productivity/
cp -r .hermes/skills/productivity/pm-workflow ~/.hermes/skills/productivity/

# 或放入目标项目的 .hermes/skills/（跟随项目 git 仓库）
cp -r .hermes/skills/productivity/pm-workflow /path/to/your-project/.hermes/skills/
```

### 使用

```bash
# 在 Hermes Agent 中启动
开启 PM 工作模式，继续 FaceSymAi 项目。

# 初始化新项目
~/.hermes/skills/productivity/pm-workflow/scripts/init.sh /path/to/new-project

# 导出项目状态
~/.hermes/skills/productivity/pm-workflow/scripts/export.sh

# 导入项目状态
~/.hermes/skills/productivity/pm-workflow/scripts/import.sh backup.tar.gz
```

### 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v2.5.0 | 2026-06-24 | 新增 Engineer 思考与反馈机制：执行后可提方案建议/不合理反馈/后续优化/风险提示 + PM 报告过期检测 |
| v2.4.0 | 2026-06-23 | 新增 Engineer 身份持久注入（AGENTS.md 模板） |
| v2.3.0 | 2026-06-23 | 新增 Engineer 身份定义模板（engineer_persona.md，14条约束） |
