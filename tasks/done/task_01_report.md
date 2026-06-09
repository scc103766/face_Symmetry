# 任务单 #01 开发日志

## 执行摘要

- 已新增脚本：`scripts/run_yolo_on_v1_test_set.py`
- 已完成正式运行：`scripts/run_in_project_env.sh python scripts/run_yolo_on_v1_test_set.py --progress-every 100`
- 已生成任务要求产物：
  - `datasets/yolo_comparison_20260608/yolo_per_image_predictions.csv`
  - `datasets/yolo_comparison_20260608/yolo_run_summary.json`
  - `datasets/yolo_comparison_20260608/run.log`
- 已生成 one-shot 实现追踪：`_bmad-output/implementation-artifacts/spec-yolo-v1-test-set-predictions.md`

## 实现内容

- 脚本默认读取：
  - YOLO 模型：`third_party/stroke_detection_yolo/best.pt`
  - V1 manifest：`datasets/facesym_v1_by_name_20260119/metadata/01_manifest.csv`
  - 患者切分：`datasets/facesym_v1_by_name_20260119/metadata/05_patient_splits.csv`
- 图片路径从 manifest 的 `organized_path` / `image_path` / `source_media_path` 解析，未硬编码逐图片路径。
- YOLO 推理默认使用 `device="cpu"`、`conf=0.25`。
- 每张图片输出一行，字段为：
  - `patient_id`
  - `image_path`
  - `role`
  - `split`
  - `patient_label`
  - `yolo_detections`
  - `yolo_eye_max_severity`
  - `yolo_mouth_max_severity`
  - `yolo_any_stroke`
  - `yolo_error`
- `yolo_detections` 为 JSON 字符串，仅记录任务要求的 `class` 和 `conf`。
- 严重度按 `none < normal < weak < mid < severe` 汇总眼部和口部最高严重度。
- 单图推理失败不会中断全量任务；失败图片输出空检测、`none` 严重度、`False` stroke 标记，并在 `yolo_error` 记录异常。

## 正式运行结果

- 总图片数：1546
- 成功推理：1543
- 推理失败：3
- 成功推理但无检测：231
- 总检测框数：2223
- 任意 stroke 检测图片数：1183
- 患者数：505
- split 分布：
  - train：1079
  - val：233
  - test：234
- role 分布：
  - front：516
  - smile：513
  - teeth：517

## 失败图片

3 张图片由 ultralytics/YOLO 读图阶段报错 `ValueError: need at least one array to stack`，已在 CSV 的 `yolo_error` 和 summary 的 `failed_images` 中记录：

| patient_id | patient_label | split | role | image_path |
| --- | --- | --- | --- | --- |
| 725 | 不患病 | test | front | `/supercloud/llm-code/scc/scc/FaceSymAi/datasets/stroke_patient_outcome_by_name_20260119/不患病/姜新民__pid725/images/row0020_pid725_collect876__front_01.jpg` |
| 535 | 不患病 | train | front | `/supercloud/llm-code/scc/scc/FaceSymAi/datasets/stroke_patient_outcome_by_name_20260119/不患病/张秋珍__pid535/images/row0200_pid535_collect672__front_01.jpg` |
| 750 | 患病 | train | front | `/supercloud/llm-code/scc/scc/FaceSymAi/datasets/stroke_patient_outcome_by_name_20260119/患病/李桂香__pid750/images/row0008_pid750_collect901__front_01.jpg` |

## 校验记录

- `python3 -m py_compile scripts/run_yolo_on_v1_test_set.py`：通过
- smoke run：`scripts/run_in_project_env.sh python scripts/run_yolo_on_v1_test_set.py --limit 2 --output-dir tmp/yolo_v1_smoke --progress-every 1`：通过
- full run：`scripts/run_in_project_env.sh python scripts/run_yolo_on_v1_test_set.py --progress-every 100`：通过
- CSV 行数校验：`yolo_per_image_predictions.csv` 为 1547 行，扣除表头后 1546 行，与 manifest 图片数一致。
- CSV schema 校验：字段顺序与任务单一致。
- 空值校验：所有输出单元格非空；成功样本 `yolo_error` 写为 `none`。
- JSON 校验：每行 `yolo_detections` 均可解析为 list，检测项均包含 `class` 和 `conf`。
- summary 一致性校验：`total_images`、`success_count`、`failure_count`、`empty_detection_count`、`failed_images` 均与 CSV 统计一致。

## 审查与补丁

- 本地 adversarial review 发现 summary 中 `empty_detection_count` 容易混淆失败图片和成功推理空检测。
- 已补丁为只统计成功推理下的空检测，并新增 `failed_images` 明细。
- one-shot 流程要求使用 sub-agent 审查，但当前 sub-agent 工具规则要求用户显式授权代理协作；本轮用户未授权，因此未启动子代理，改为本地审查并记录该限制。

## 备注

- 当前目录不是 git worktree，`git status` / commit 步骤不可用，已跳过。
- `code -r` 无法连接当前 VS Code IPC，未自动打开 spec 文件；spec 文件已写入 `_bmad-output/implementation-artifacts/spec-yolo-v1-test-set-predictions.md`。
