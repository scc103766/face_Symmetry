# 脑卒中预警 App 规则测试集

本文记录从 `脑卒中预警报告老来健康app线上_2026-05-08.xlsx` 构建独立测试集的规则、命令和当前产物。该测试集用于后续模型/特征验证时提供一个按业务规则筛出的患者级弱标签集合。

## 输入

- 源 Excel：`脑卒中预警报告老来健康app线上_2026-05-08.xlsx`
- 源媒体数据集：`datasets/stroke_warning_app_media_dataset_20260508`
- 构建脚本：`scripts/build_stroke_warning_rule_test_set.py`

## 标签规则

患者级标签按同一 `老来号` 聚合，阳性优先。

- 患病：同一条记录同时满足 `风险等级=紧急风险`、`曾经得过中风=是`、`家人得过脑卒中=有`。
- 不患病：该患者没有任何阳性记录，且至少一条记录为 `低风险`，同时基础病、抽烟、超重、突发无力、突发麻木、中风史、家族史均正常，经常运动为 `是`。
- 未纳入：不满足上述患病或不患病规则的患者和记录。

这里的 `患病/不患病` 是业务规则弱标签，不是人工面部不对称标签，也不是医学诊断真值。

## 生成命令

```bash
scripts/run_in_project_env.sh python scripts/build_stroke_warning_rule_test_set.py \
  --source 脑卒中预警报告老来健康app线上_2026-05-08.xlsx \
  --media-dataset datasets/stroke_warning_app_media_dataset_20260508 \
  --output datasets/stroke_warning_app_rule_test_set_20260508
```

默认使用 hardlink 组织媒体文件；跨文件系统失败时会自动 fallback 到 copy。可通过 `--link-mode copy` 或 `--link-mode symlink` 显式指定。

## 当前产物

输出目录：

```text
datasets/stroke_warning_app_rule_test_set_20260508
```

核心文件：

- `metadata/patient_samples.csv`：患者级样本、标签、记录数、媒体数和规则原因。
- `metadata/rule_labeled_records.csv`：入选记录级标签。
- `metadata/media_index.csv`：每个媒体文件的源路径、组织后路径、role、类型和校验信息。
- `metadata/excluded_records.csv`：未入选记录及排除原因。
- `metadata/summary.json`：机器可读汇总。
- `reports/01_rule_test_set.md`：规则、汇总和患者样本预览。

媒体按标签和患者组织：

```text
datasets/stroke_warning_app_rule_test_set_20260508/
  患病/<patient_sample_id>/images|videos/
  不患病/<patient_sample_id>/images|videos/
```

## 当前统计

- 源记录数：612
- 源患者数：487
- 纳入患者数：101
- 纳入记录数：109
- 排除记录数：503
- 患者标签分布：`患病` 42，`不患病` 59
- 记录标签分布：`患病` 47，`不患病` 62
- 排除患者数：386
- 阳性优先处理患者数：0
- 媒体数：658，其中图片 549、视频 109
- 媒体 role 分布：`front_contour` 109、`eyes_right` 109、`smile_teeth` 109、`tongue_surface_contour` 109、`tongue_root_contour` 109、`video` 109、`diagnostic_report` 4

## 验证

构建后已检查：

- `summary.json` 与 CSV 行数一致。
- `patient_samples.csv` 仅包含 `患病/不患病` 两类入选患者。
- `media_index.csv` 中每个 `organized_path` 都能在输出目录中找到。
- 规则判定单元测试覆盖三条件同时命中、单条件命中不纳入、低风险全正常阴性、指标异常不纳入和同患者阳性优先。

## MediaPipe 主证据特征验证

已使用该规则测试集验证 `docs/algorithm/mediapipe-largest-feature-difference-evidence-explanation.md` 中“患病更高”的 MediaPipe 主证据特征。验证脚本：

```text
scripts/validate_mediapipe_evidence_on_rule_test_set.py
```

输出：

- `metadata/40_mediapipe_evidence_keypoints.csv`
- `metadata/40_mediapipe_evidence_image_features.csv`
- `metadata/40_mediapipe_evidence_patient_features.csv`
- `metadata/40_mediapipe_evidence_feature_validation.csv`
- `metadata/40_mediapipe_evidence_validation_summary.json`
- `reports/40_mediapipe_evidence_feature_validation.md`

当前结果：

- 入选待检测图片 327，MediaPipe detected 325，no_face 2。
- 主判断为患者级 `all` role 的 `max` 聚合。
- 主证据支持数为 4/10。
- `raw_lip_midline_deviation`、`raw_eyebrow_region_height_asym` 为 supported。
- `raw_all_mesh_region_point_spread_asym`、`raw_face_oval_region_centroid_y_asym` 为 weak_supported。
- 详细解释见 `docs/algorithm/mediapipe-evidence-validation-on-rule-test-set.md`。
