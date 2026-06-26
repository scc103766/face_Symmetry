# M3-ACTION-02 开发报告

## 1. 开发过程

1. 读取 `tasks/queue/M3-ACTION-02.md`，确认本次任务只允许修改
   `modules/facial_asymmetry_service/facial_asymmetry_service/web_server.py`，
   并在完成后写入本报告。
2. 读取当前 `web_server.py` 中的导入区、`FacialAsymmetryWebApp.handle_post()`、
   `read_uploads()` 和 `analyze_uploads()`，确认现有上传读取、鉴权、异常处理和
   `detector_lock` 使用方式。
3. 在 `web_server.py` 顶部导入 M3-ACTION-01 新增的三个检测函数：
   `detect_side_view`、`detect_strabismus`、`detect_teeth_exposure`。
4. 在 `handle_post()` 中，在 `/api/analyze` 判断前新增三条路由：
   `/keypoint`、`/ceshi`、`/louyachi`。
5. 新增 `_detect_single_face()`，复用 `read_uploads()` 并只取第一张上传图片，
   在 `detector_lock` 内调用 `self.detector.detect_image_path(upload.path)`。
6. 新增 `_handle_keypoint()`、`_handle_ceshi()`、`_handle_louyachi()` 三个私有 handler。
7. 执行验证命令：
   - `scripts/run_in_project_env.sh python -m py_compile modules/facial_asymmetry_service/facial_asymmetry_service/web_server.py modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`
   - `env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi scripts/run_in_project_env.sh python -c "from modules.facial_asymmetry_service.facial_asymmetry_service.web_server import FacialAsymmetryWebApp; print(FacialAsymmetryWebApp.__name__)"`
   - `env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi scripts/run_in_project_env.sh pytest -q`

验证结果：`64 passed, 3 warnings`。warnings 为既有 Pillow deprecation warning，非本次改动导致。

## 2. 开发思路

实现选择严格按任务单指定路径：

- 新端点不复用 `/api/analyze` 的多图分析流程，避免改变现有分析接口行为。
- 三个新端点共享 `_detect_single_face()`，避免重复 multipart 读取和 MediaPipe 检测代码。
- 新端点只读取第一张上传图片；`read_uploads()` 原有多图能力不改动。
- 鉴权逻辑保持与 `/api/analyze`、`/api/input-spec` 一致，统一调用 `self.authorized()`。
- 异常处理保持当前服务风格：`ValueError` 返回 400，其他异常返回 500。
- 无人脸不是异常，按任务单返回 200 + `{"status": "no_face"}`。

## 3. 代码变更清单

修改：

- `modules/facial_asymmetry_service/facial_asymmetry_service/web_server.py`
  - 新增 `.action_detector` 三个函数导入。
  - `handle_post()` 新增 `/keypoint`、`/ceshi`、`/louyachi` 路由分支。
  - 新增 `_handle_keypoint()`。
  - 新增 `_handle_ceshi()`。
  - 新增 `_handle_louyachi()`。
  - 新增 `_detect_single_face()`。

未修改：

- 未修改 `/api/analyze` 的处理流程。
- 未修改 `/api/input-spec`。
- 未修改 `read_uploads()` 行为。
- 未修改模型、数据集、环境或依赖。
- 未执行 commit/push/分支操作。

## 4. 核心代码解读

### `handle_post()`

在原有 `/api/analyze` 判断之前增加三个精确路径匹配：

```text
/keypoint  -> self._handle_keypoint()
/ceshi     -> self._handle_ceshi()
/louyachi  -> self._handle_louyachi()
```

未匹配到新端点或 `/api/analyze` 的请求仍返回 404。

### `_detect_single_face()`

该方法复用现有上传逻辑：

1. `uploads = self.read_uploads(request)`
2. 若没有上传图片，抛出 `ValueError("请上传一张图片。")`
3. 取 `uploads[0]`
4. 在 `self.detector_lock` 内调用 `self.detector.detect_image_path(upload.path)`
5. `detection is None` 时返回 `{"status": "no_face"}`
6. 有检测结果时返回 `FaceMeshDetection` 对象

### `_handle_keypoint()`

检测成功后返回：

```json
{
  "status": "detected",
  "detection": "detection.to_dict()"
}
```

`detection.to_dict()` 保留 raw landmarks、semantic landmarks、blendshapes、pose、face_count 等字段。

### `_handle_ceshi()`

对同一个 `detection_payload = detection.to_dict()` 同时执行：

- `detect_side_view(detection_payload)`
- `detect_strabismus(detection_payload)`

返回 `side_view` 和 `strabismus` 两组结果，其中 `yaw_angle` 保留 2 位小数，`confidence` 保留 4 位小数。

### `_handle_louyachi()`

执行 `detect_teeth_exposure(detection.to_dict())`，并返回：

```json
{
  "status": "detected",
  "teeth_exposure": {
    "detected": "...",
    "mouth_state": "...",
    "confidence": "...",
    "details": "..."
  }
}
```

## 5. 遇到的问题与解决方案

1. 当前 `web_server.py` 在本任务前已经存在大量已跟踪文件改动。
   - 处理：不回滚、不重排、不归因既有改动；本次只在当前文件基础上插入任务要求的导入、路由、handler 和辅助方法。
2. 任务单要求新端点只取第一张图片，但现有 `read_uploads()` 支持多图并会落盘。
   - 处理：保持 `read_uploads()` 原行为不变，在 `_detect_single_face()` 中只使用 `uploads[0]`。
3. 新端点需要与 `/api/analyze` 保持异常处理风格。
   - 处理：三个 handler 都显式捕获 `ValueError` 和通用 `Exception`，分别返回 400 和 500。

## 6. 参考来源

- `tasks/queue/M3-ACTION-02.md`
- `modules/facial_asymmetry_service/facial_asymmetry_service/web_server.py`
- `modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`
- `tasks/done/M3-ACTION-01_report.md`
- `AGENTS.md`
