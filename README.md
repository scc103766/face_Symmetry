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
