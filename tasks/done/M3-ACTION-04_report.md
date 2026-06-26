# M3-ACTION-04 开发报告

## 1. 开发过程

1. 读取 `tasks/queue/M3-ACTION-04.md`，确认本次任务目标是在
   `modules/mediapipe_face_keypoint_detector/face_keypoint_detector/api_server.py`
   中新增 `/keypoint`、`/ceshi`、`/louyachi` 三个 POST 端点。
2. 读取当前 `api_server.py`，确认现有 `/api/detect`、`/api/detect-folder`、
   `read_uploads()`、`detect_uploads()`、`detect_folder_images()` 的结构。
3. 读取 `modules/mediapipe_face_keypoint_detector/face_keypoint_detector/sdk.py`，
   确认 `FaceKeypointDetectorSDK.detect_image()` 返回 `status` 和 `detection`。
4. 参考 8790 服务的 handler 实现，但按任务要求保留 18432 差异：
   `/ceshi` 只返回 `strabismus`，不返回 `side_view`。
5. 修改 `api_server.py`：
   - 增加 facial service action detector 路径注入。
   - 导入 `detect_side_view`、`detect_strabismus`、`detect_teeth_exposure`。
   - 在 `handle_post()` 中先匹配 `/keypoint`、`/ceshi`、`/louyachi`。
   - 新增 `_handle_keypoint()`、`_handle_ceshi()`、`_handle_louyachi()`。
   - 新增 `_detect_single_face()`，统一处理鉴权、单图上传读取和 SDK 检测。
6. 执行语法检查：
   `scripts/run_in_project_env.sh python -m py_compile modules/mediapipe_face_keypoint_detector/face_keypoint_detector/api_server.py`
7. 执行导入检查：
   `env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi scripts/run_in_project_env.sh python -c "from modules.mediapipe_face_keypoint_detector.face_keypoint_detector.api_server import FaceKeypointDetectorApi; print(FaceKeypointDetectorApi.__name__)"`
8. 按任务单要求重启 18432 服务：
   - 停止旧进程 `serve_api.py --port 18432`
   - 启动当前代码版本：`env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi scripts/run_in_project_env.sh python modules/mediapipe_face_keypoint_detector/serve_api.py --host 127.0.0.1 --port 18432`
9. 使用 curl 验证：
   - `POST /keypoint` 正脸图，HTTP 200，返回 `status=detected`，`raw_landmarks=478`，`blendshapes=52`
   - `POST /ceshi` 正脸图，HTTP 200，返回 `status=detected`，只包含 `strabismus`，不包含 `side_view`
   - `POST /louyachi` 露齿图，HTTP 200，返回 `status=detected`，`teeth_exposure.mouth_state=teeth_visible`
10. 关闭验证用 18432 服务并确认端口无遗留监听。
11. 执行全量测试：
    `env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi scripts/run_in_project_env.sh pytest -q`

验证结果：`64 passed, 3 warnings`。warnings 为既有 Pillow deprecation warning。

## 2. 开发思路

实现保持最小范围，18432 仍然是 MediaPipe 关键点检测服务：

- 新端点复用 SDK `detect_image()`，不绕过现有检测封装。
- 新端点只取 `read_uploads()` 返回的第一张图片，不改变 `read_uploads()` 多图行为。
- `_detect_single_face()` 集中处理鉴权、上传读取、SDK 调用和 no-face 返回，避免三个 handler 重复代码。
- `/keypoint` 返回 SDK detection payload，作为纯关键点输出。
- `/ceshi` 只做斜视判断，严格不返回 `side_view`。
- `/louyachi` 只做露齿判断。
- 不修改 `/api/detect` 和 `/api/detect-folder` 的处理逻辑。

## 3. 代码变更清单

修改：

- `modules/mediapipe_face_keypoint_detector/face_keypoint_detector/api_server.py`
  - 新增 `_FACIAL_SERVICE_DIR` 路径注入。
  - 新增 `action_detector` 三个函数导入。
  - `handle_post()` 新增三条 action endpoint 路由。
  - 新增 `_handle_keypoint()`。
  - 新增 `_handle_ceshi()`。
  - 新增 `_handle_louyachi()`。
  - 新增 `_detect_single_face()`。

新增：

- `tasks/done/M3-ACTION-04_report.md`

未修改：

- 未修改 `read_uploads()`。
- 未修改 `detect_uploads()`。
- 未修改 `detect_folder_images()`。
- 未修改 SDK、模型、数据集或环境。
- 未执行 commit/push/创建分支。

说明：`api_server.py` 在本任务前已存在未提交改动，`git diff` 会混入既有差异；本报告仅记录本次 M3-ACTION-04 的 action 端点相关改动。

## 4. 核心代码解读

### action detector 导入

`api_server.py` 与 `action_detector.py` 不在同一包目录。本次按任务单要求添加：

```text
modules/facial_asymmetry_service/facial_asymmetry_service
```

到 `sys.path`，再从 `action_detector` 导入动作检测函数。

### `handle_post()`

在原有 `/api/detect` 和 `/api/detect-folder` 判断前新增：

```text
/keypoint  -> _handle_keypoint()
/ceshi     -> _handle_ceshi()
/louyachi  -> _handle_louyachi()
```

未匹配到新端点且不是原有 API 时仍返回 404。

### `_detect_single_face()`

流程：

1. `self.authorized(request, query)` 鉴权，失败返回 401。
2. `self.read_uploads(request)` 读取上传图片。
3. 使用 `uploads[0]`。
4. 调用 `self.sdk.detect_image(upload.path)`。
5. `status == "no_face"` 时返回 `{"status": "no_face"}`。
6. 有 `detection` dict 时返回 detection payload。
7. SDK 返回 failed 或缺少 detection 时透传结构化失败状态。

### `_handle_keypoint()`

检测成功返回：

```json
{
  "status": "detected",
  "detection": "SDK detection payload"
}
```

### `_handle_ceshi()`

只调用 `detect_strabismus(detection_payload)`，返回：

```json
{
  "status": "detected",
  "strabismus": {
    "detected": "...",
    "direction": "...",
    "confidence": "...",
    "details": "..."
  }
}
```

本端点不返回 `side_view`，符合任务单对 18432 的特殊要求。

### `_handle_louyachi()`

调用 `detect_teeth_exposure(detection_payload)`，返回 `teeth_exposure`。

## 5. 遇到的问题与解决方案

1. 18432 已有旧服务进程。
   - 处理：定位并停止旧 `serve_api.py --port 18432`，启动当前代码版本后验证。
2. 本地端口访问需要升级权限。
   - 处理：按执行环境权限规则使用升级权限访问 `127.0.0.1:18432`。
3. 第一张 `teeth` 样本实际返回 `mouth_open_no_teeth`。
   - 处理：端点结构验证已通过；随后使用 M3-ACTION-03 已验证露齿样本复测 `/louyachi`，返回 `teeth_visible`。
4. `api_server.py` 有既有未提交改动。
   - 处理：不回滚、不重排、不归因既有改动；只在当前文件基础上插入任务要求的 action endpoint 代码。

## 6. 验证结果

语法检查：

```text
python -m py_compile modules/mediapipe_face_keypoint_detector/face_keypoint_detector/api_server.py
```

通过。

导入检查：

```text
FaceKeypointDetectorApi
```

18432 curl 冒烟验证：

```text
/keypoint: HTTP 200, status=detected, raw_landmarks=478, blendshapes=52
/ceshi: HTTP 200, status=detected, keys=['status', 'strabismus'], side_view absent
/louyachi: HTTP 200, status=detected, teeth_exposure.mouth_state=teeth_visible
```

全量测试：

```text
64 passed, 3 warnings
```

端口清理：

```text
18432 无遗留监听进程
```

## 7. 参考来源

- `tasks/queue/M3-ACTION-04.md`
- `modules/mediapipe_face_keypoint_detector/face_keypoint_detector/api_server.py`
- `modules/mediapipe_face_keypoint_detector/face_keypoint_detector/sdk.py`
- `modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`
- `modules/facial_asymmetry_service/facial_asymmetry_service/web_server.py`
- `AGENTS.md`
