# 项目进度恢复总览 + 技术教师代码讲解模式

适用场景：用户选择“项目进度恢复总览”、对项目进度失控、或要求梳理“已经做了什么、现在处于哪里、下一步做什么”。

## 核心流程

1. 只读恢复上下文：
   - `PROJECT_CONTEXT.md`
   - `WORK_STATUS.md`
   - `tasks/done/*.md`
   - 关键 `docs/`、`reports/`、`src/`、`scripts/` 产物清单
2. 先向用户输出总览草案，不直接写项目记忆文件。
3. 总览必须区分：
   - 已完成产物
   - 已验证结论
   - 不能宣称的内容
   - 技术债
   - 下一步决策树
4. 用户明确批准后，才写入 `PROJECT_PROGRESS_SUMMARY.md`。
5. 写入后必须读回验证：文件存在、大小、行数、核心章节关键词。
6. 未经单独批准，不同步修改 `PROJECT_CONTEXT.md`、`WORK_STATUS.md`、`tasks/queue/` 或代码。

## 技术教师增强要求

项目总览不能只写“模块完成/未完成”。对关键代码资产要补充：

- 关键模块应该怎么写。
- 为什么这样写。
- 替代写法为什么当前不选。
- 常见代码坑。
- 这些代码结构如何服务后续训练、验证、部署和质量把关。

示例：

- `schema.py`：定义稳定输入字段，避免训练/推理字段漂移。
- `feature_adapter.py`：负责外部数据源到模型特征的映射，不让 predictor 直接依赖前端字段名。
- `predictor.py`：保持纯推理，便于测试、部署和换模型。
- `FaceDetector`：用 class 管理 MediaPipe 生命周期、ROI、pose、quality，而不是每帧重新初始化或硬编码像素 ROI。
- `MultiTaskModel`：backbone 与 heads 分离，输出 dict，loss 支持 mask 和动态权重，避免多任务顺序错乱与缺失标签误用。

## 医疗/健康项目特别注意

进度总览必须显式写出“不能宣称”的边界，例如：

- dummy data loss 下降不等于真实模型有效。
- self-report 标签不是 MACE/ICD 金标准。
- diabetes strict label 不能当 CVD 标签。
- Framingham/ASCVD 是公式风险，不是真实事件标签。
- `risk_score`、`risk_level`、`probability`、`prediction` 等派生字段不能默认作为训练特征。

## 推荐输出结构

1. 总体结论
2. 已完成产物清单
3. 按里程碑恢复项目状态
4. 技术教师说明：关键代码为什么这样写
5. 当前不能宣称的内容
6. 当前主要技术债
7. 下一步决策树
8. 推荐下一步任务
9. 需要用户另行批准的项目记忆同步项
