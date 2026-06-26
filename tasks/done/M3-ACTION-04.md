## 🎫 任务单 #M3-ACTION-04 — 待 Engineer 执行

**任务名称**：在 18432 api_server.py 中新增 3 个动作检测端点
**优先级**：P1
**依赖**：M3-ACTION-01（`action_detector.py` 必须已完成）

---

## 🔧 角色与约束（Engineer 身份）

你是本项目的 Engineer Agent。在本次任务中，你必须遵守以下约束：

### 执行边界
1. **只执行本任务单描述的内容**，不得自行扩展需求、变更架构、修改技术选型。
2. 任务单中未明确要求的文件/模块/依赖，不得新增或修改。
3. 不得自行发起新的实验、训练、数据采集或模型下载。

### 决策权限
4. 遇到技术阻塞时：写清阻塞原因和影响范围，不要自行绕过或换方案，停止执行并回报 PM。

### 产出规范
5. 完成后必须写入 `tasks/done/M3-ACTION-04_report.md`。
6. 代码必须通过任务单中指定的验证命令后再写回报。

### 禁止事项
7. ❌ 不得自行 commit、push、创建分支或修改 git 历史。
8. ❌ 不得自行安装系统级包或修改 conda/pip 环境。
9. ❌ 不得读取、打印或记录任何凭据文件。
10. ❌ 不得修改 `/api/detect` 和 `/api/detect-folder` 的现有行为。

---

### 📝 任务描述

修改 `modules/mediapipe_face_keypoint_detector/face_keypoint_detector/api_server.py`，新增 3 条 POST 路由：`/keypoint`、`/ceshi`、`/louyachi`。

### 📥 输入文件

- 主文件：`modules/mediapipe_face_keypoint_detector/face_keypoint_detector/api_server.py`
- 依赖：`modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`（M3-ACTION-01 产出）

### 📤 输出要求

- [ ] 只修改 `api_server.py` 一个文件
- [ ] 不新增其他文件

---

### ✅ 验收标准

#### 导入 action_detector

两个模块不在同一目录，需要处理 import 路径。在文件顶部现有 import 之后添加：

```python
_FACIAL_SERVICE_DIR = Path(__file__).resolve().parents[2] / "facial_asymmetry_service" / "facial_asymmetry_service"
if str(_FACIAL_SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(_FACIAL_SERVICE_DIR))

from action_detector import (  # noqa: E402
    detect_side_view,
    detect_strabismus,
    detect_teeth_exposure,
)
```

说明：`action_detector.py` 只依赖标准库（math + dataclasses），不依赖 facial_asymmetry_service 的其他模块，可以安全导入。

#### 路由调度（handle_post 方法）

当前 `handle_post` 的结构：
```python
def handle_post(self, request):
    parsed = urlparse(request.path)
    if parsed.path not in {"/api/detect", "/api/detect-folder"}:
        send_json(request, 404, {"error": "not found"})
        return
```

改为：先匹配 3 个新路径，再走原有逻辑。

新增路由：
- `POST /keypoint`  — 调用 `self._handle_keypoint(request, parsed.query)`
- `POST /ceshi`    — 调用 `self._handle_ceshi(request, parsed.query)`
- `POST /louyachi` — 调用 `self._handle_louyachi(request, parsed.query)`

匹配不到新端点且不是 `/api/detect` / `/api/detect-folder` → 404。

#### `/keypoint` 端点

1. 鉴权：`self.authorized(request, parsed.query)`，未授权返回 401
2. 从 multipart/form-data 读一张图片：复用 `self.read_uploads(request)`，取 `uploads[0]`
3. 用 SDK 检测：`result = self.sdk.detect_image(upload.path)`
4. 无人脸（`result["status"] == "no_face"`）→ 返回 `{"status": "no_face"}`
5. 有人脸 → 返回：
```python
{
    "status": "detected",
    "detection": result["detection"],
}
```
`result["detection"]` 已包含 `raw_landmarks`（478个）、`landmarks`（语义）、`blendshapes`（52个）、`pose`、`face_count`
6. 不上传图片到磁盘，不需要写 analysis.json（与 `/api/detect` 不同）

#### `/ceshi` 端点（18432 版：只返回斜视）

1. 鉴权 → 读图 → SDK detect
2. 无人脸返回 `{"status": "no_face"}`
3. 有人脸 → 取 `detection_payload = result["detection"]`
4. 调用 `detect_strabismus(detection_payload)`
5. 返回：
```python
{
    "status": "detected",
    "strabismus": {
        "detected": result_st.detected,
        "direction": result_st.direction,
        "confidence": round(result_st.confidence, 4),
        "details": result_st.details,
    }
}
```

注意：18432 的 `/ceshi` **不返回 side_view**（与 8790 不同），只做斜视判断。

#### `/louyachi` 端点

1. 同上流程
2. 调用 `detect_teeth_exposure(detection_payload)`
3. 返回：
```python
{
    "status": "detected",
    "teeth_exposure": {
        "detected": result.detected,
        "mouth_state": result.mouth_state,
        "confidence": round(result.confidence, 4),
        "details": result.details,
    }
}
```

#### 代码结构要求

- [ ] 新增 3 个 handler 方法命名为 `_handle_keypoint`、`_handle_ceshi`、`_handle_louyachi`（与 8790 命名一致）
- [ ] 提取通用方法 `_detect_single_face(self, request, query)`：鉴权 + 读图 + SDK detect + 返回 `(detection_payload, error_response)`
- [ ] 异常处理风格与现有代码一致（`ValueError` → 400，`Exception` → 500）
- [ ] 不要修改 `read_uploads`、`detect_uploads`、`detect_folder_images` 的任何行为
- [ ] 不要在 `handle_get` 中新增路由（新端点全部是 POST）

### ⚠️ 需要关注

- `read_uploads` 会把图片写入 `upload_dir` 磁盘目录——这是现有行为，保留
- `read_uploads` 支持多图上传，新端点只取 `uploads[0]`
- SDK 的 `detect_image()` 返回值结构：`{"status": "detected|no_face", "detection": {...}}`，见 `sdk.py:64-90`
- 18432 的 `/ceshi` 与 8790 的 `/ceshi` 不完全相同——18432 只返回 strabismus，不返回 side_view。这是用户明确要求的，不要自行添加
- 18432 服务已在运行（PID 3110908），重启后验证

### 🔗 参考资料

- `modules/mediapipe_face_keypoint_detector/face_keypoint_detector/api_server.py` — 当前代码
- `modules/mediapipe_face_keypoint_detector/face_keypoint_detector/sdk.py:64-90` — SDK detect_image 返回结构
- `modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py` — 三个检测函数签名
- `modules/facial_asymmetry_service/facial_asymmetry_service/web_server.py:309-410` — 8790 的 handler 实现参考

### 验证命令

修改完成后，重启 18432 服务并验证：

```bash
# 语法检查
python -m py_compile modules/mediapipe_face_keypoint_detector/face_keypoint_detector/api_server.py

# 启动服务（先停旧进程）
kill $(pgrep -f "serve_api.py.*18432")
cd /supercloud/llm-code/scc/scc/FaceSymAi
PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi python modules/mediapipe_face_keypoint_detector/serve_api.py --port 18432 &

# 冒烟测试
curl -X POST http://127.0.0.1:18432/keypoint -F "images=@一张正脸图.jpg"
curl -X POST http://127.0.0.1:18432/ceshi -F "images=@一张正脸图.jpg"
curl -X POST http://127.0.0.1:18432/louyachi -F "images=@一张露齿图.jpg"
```
