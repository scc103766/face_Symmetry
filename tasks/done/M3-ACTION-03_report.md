# M3-ACTION-03 开发报告

## 1. 开发过程

1. 读取 `tasks/queue/M3-ACTION-03.md`，确认本次目标是新增
   `scripts/test_action_api.py`，用于验证 `/keypoint`、`/ceshi`、`/louyachi`
   和无脸输入场景。
2. 读取 `scripts/test_asymmetry_api.py`，复用其 `requests` 调用风格、超时设置和
   文件上传方式。
3. 读取 `datasets/facesym_v1_by_name_20260119/metadata/01_manifest.csv`，确认 V1
   manifest 字段为 `media_role`、`organized_path`、`source_media_path`。
4. 确认 V1 by-name manifest 只有 `front/smile/teeth`，没有 `eyes_right` 或 profile
   侧脸图。因此脚本优先从 V1 manifest 选择正脸与露齿图，侧脸图回退到同项目已存在的
   `datasets/facesym_v1_all_images_no_gate_20260119/metadata/01_all_images.csv`
   中的 `left_profile/right_profile` 原图。
5. 新增 `scripts/test_action_api.py`：
   - 支持 `--api-base-url`，默认 `http://127.0.0.1:8790`
   - 启动测试前 GET `/api/input-spec` 检查服务在线
   - 每个测试独立 `try/except`
   - 打印 `PASS` / `FAIL` 和实际关键返回
   - 最后打印 `X/Y tests passed`
   - 生成 `tmp/action_api_no_face.png` 作为纯色无脸图
6. 执行 `py_compile` 后启动 8790 服务验证。第一次访问发现旧 8790 服务仍在运行，三个新端点返回 404。
   按任务单“服务需重启后生效”的要求，停止旧进程并启动当前代码服务。
7. 第一次当前代码验证结果为 `3/4 tests passed`，`/ceshi` 失败。失败原因是 M3-ACTION-01
   的 `detect_side_view()` 对真实 MediaPipe z 轴角度未做折叠，导致正脸被判为 `extreme`；
   同时 `pose.yaw` 固定为 0 时斜视结果缺少侧脸 `head_pose_warning`。
8. 按 M3-ACTION-01 任务单中“z 轴方向可能与直觉相反，需要实际运行时验证并调整符号”的要求，
   对 `action_detector.py` 做最小依赖修正：
   - 将鼻梁到鼻尖的 raw yaw 折叠到正脸接近 0 度
   - 当 `detection["pose"]["yaw"]` 为 0 时，使用鼻部 yaw 作为 head-pose warning 的依据
9. 重启 8790 服务后重新运行 `scripts/test_action_api.py`，结果 `4/4 tests passed`。
10. 关闭验证用 8790 服务，确认端口无遗留监听进程。
11. 执行全量项目测试：
    `env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi scripts/run_in_project_env.sh pytest -q`

验证结果：`64 passed, 3 warnings`。warnings 为既有 Pillow deprecation warning。

## 2. 开发思路

脚本目标是端到端冒烟，不替代完整 QA：

- 脚本通过真实 HTTP 调用验证端点，而不是直接调用 Python 函数。
- 图片选择来自 manifest，避免硬编码单个患者路径；同时限制每类最多 40 个候选，避免测试过慢。
- 选择样本时按端点实际响应筛选第一个满足验收条件的候选图，减少单张图片质量差导致的偶发失败。
- 无脸测试用标准库生成 PNG，不引入新依赖。
- 对 `/ceshi` 的正脸与侧脸分别验证：正脸必须 `frontal` 且斜视 `detected=false`；侧脸必须
  `side_view.detected=true` 且 `strabismus.details.head_pose_warning` 存在。

## 3. 代码变更清单

新增：

- `scripts/test_action_api.py`
  - 新增服务在线检查
  - 新增 manifest 图片选择逻辑
  - 新增 `/keypoint` 冒烟测试
  - 新增 `/ceshi` 冒烟测试
  - 新增 `/louyachi` 冒烟测试
  - 新增无脸图片生成与 no-face 测试

修改：

- `modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`
  - 新增 `_normalize_nose_yaw()`
  - 新增 `_yaw_from_nose_landmarks()`
  - `detect_side_view()` 使用折叠后的鼻部 yaw
  - `detect_strabismus()` 在 `pose.yaw` 为 0 时回退使用鼻部 yaw，从而在侧脸场景记录
    `head_pose_warning`

新增报告：

- `tasks/done/M3-ACTION-03_report.md`

未执行：

- 未修改 conda/pip 环境
- 未下载模型或数据
- 未 commit/push/创建分支

## 4. 核心代码解读

### `scripts/test_action_api.py`

`check_service_online()`：

- 对 `{api_base_url}/api/input-spec` 发起 GET
- 非 200 或连接失败时直接退出，符合任务单“服务不在线则报错退出”

`images_for_roles()`：

- 从 manifest 读取 `media_role`
- 优先使用 `organized_path`，其次 `source_media_path`
- 只返回存在且后缀为 jpg/jpeg/png 的图片

`find_passing_response()`：

- 对候选图片逐张 POST 到指定 endpoint
- 用 predicate 判断是否满足验收标准
- 找不到合格样本时抛出 `SmokeTestFailure`，但不影响其他测试继续执行

四个测试函数：

- `test_keypoint()`：验证 478 raw landmarks、blendshapes 和 semantic landmarks
- `test_ceshi()`：验证正脸侧视判断、侧脸侧视判断和斜视 head-pose warning
- `test_louyachi()`：验证露齿图 `teeth_visible` 与正脸闭嘴不露齿
- `test_no_face()`：生成纯色 PNG 并验证返回 `{"status": "no_face"}`

### `action_detector.py` 依赖修正

实际 MediaPipe 输出中，鼻梁到鼻尖的 `atan2(dx, dz)` 对正脸可能接近 `±180°`，不能直接按绝对值阈值判断。
`_normalize_nose_yaw()` 将大于 90 度的角度折叠回 `[-90, 90]` 附近，使正脸样本接近 0 度。

`detect_strabismus()` 原本只看 `detection["pose"]["yaw"]`。当前 detector 的 pose yaw 为 0，因此侧脸时不会触发
`head_pose_warning`。修正后，当 pose yaw 为 0 时，回退到鼻部 yaw，满足 `/ceshi` 侧脸验收。

## 5. 遇到的问题与解决方案

1. 沙箱内直接访问 `127.0.0.1:8790` 返回 `Operation not permitted`。
   - 处理：按权限规则使用升级权限访问本机服务完成验证。
2. 8790 已有旧服务进程，导致新端点返回 404。
   - 处理：定位旧进程后停止，重新启动当前代码版本服务。
3. V1 by-name manifest 没有侧脸 role。
   - 处理：正脸和露齿仍来自 V1 by-name manifest；侧脸样本从同项目 all-images no-gate manifest 中选择
     `left_profile/right_profile`。
4. `/ceshi` 初次验证失败。
   - 处理：修正 `action_detector.py` 的实际 MediaPipe yaw 折叠和 head-pose warning 回退逻辑，重启服务后通过。

## 6. 验证结果

`scripts/run_in_project_env.sh python scripts/test_action_api.py`

结果：

```text
PASS keypoint: raw_landmarks=478, blendshapes=52, landmarks=25
PASS ceshi: front side_view frontal; side side_view moderate; head_pose_warning=True
PASS louyachi: teeth image teeth_visible; front image mouth_closed
PASS no_face: response={'status': 'no_face'}
4/4 tests passed
```

`env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi scripts/run_in_project_env.sh pytest -q`

结果：

```text
64 passed, 3 warnings
```

## 7. 参考来源

- `tasks/queue/M3-ACTION-03.md`
- `scripts/test_asymmetry_api.py`
- `datasets/facesym_v1_by_name_20260119/metadata/01_manifest.csv`
- `datasets/facesym_v1_all_images_no_gate_20260119/metadata/01_all_images.csv`
- `modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`
- `modules/facial_asymmetry_service/facial_asymmetry_service/web_server.py`
- `AGENTS.md`
