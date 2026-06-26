## 🎫 任务单 #M3-ACTION-02 — 待 Engineer 执行

**任务名称**：在 web_server.py 中新增 3 个动作检测 API 端点
**优先级**：P1
**依赖**：M3-ACTION-01（`action_detector.py` 必须先完成）

---

## 🔧 角色与约束（Engineer 身份）

你是本项目的 Engineer Agent。在本次任务中，你必须遵守以下约束：

### 执行边界
1. **只执行本任务单描述的内容**，不得自行扩展需求、变更架构、修改技术选型。
2. 任务单中未明确要求的文件/模块/依赖，不得新增或修改。
3. 不得自行发起新的实验、训练、数据采集或模型下载。

### 决策权限
4. 遇到技术阻塞时：写清阻塞原因和影响范围，不要自行绕过或换方案，停止执行并回报 PM。
5. 遇到多个实现路径时，选择任务单明确指定的路径；如任务单未指定，选最简路径并注明选择理由。

### 产出规范
6. 完成后必须写入 `tasks/done/M3-ACTION-02_report.md`：开发过程 → 开发思路 → 代码变更清单 → 核心代码解读 → 遇到的问题与解决方案。
7. 代码必须通过任务单中指定的验证命令后再写回报。

### 禁止事项
8. ❌ 不得自行 commit、push、创建分支或修改 git 历史。
9. ❌ 不得自行安装系统级包或修改 conda/pip 环境。
10. ❌ 不得读取、打印或记录任何凭据文件。
11. ❌ 不要修改已有 `/api/analyze` 和 `/api/input-spec` 的行为。

---

### 📝 任务描述

修改 `modules/facial_asymmetry_service/facial_asymmetry_service/web_server.py`，在 `FacialAsymmetryWebApp.handle_post()` 中新增 3 条路由：`/keypoint`、`/ceshi`、`/louyachi`。

其中 `/ceshi` 是合并端点：同时返回侧视判断 + 斜视判断。

### 📥 输入文件

- 主文件：`modules/facial_asymmetry_service/facial_asymmetry_service/web_server.py`
- 导入：M3-ACTION-01 产出的 `action_detector.py`（同一目录下）

### 📤 输出要求

- [ ] 修改 `web_server.py`（只改这一个文件）
- [ ] 在文件顶部新增 import：
```python
from .action_detector import (
    detect_strabismus,
    detect_teeth_exposure,
    detect_side_view,
)
```

- [ ] 在 `handle_post()` 方法中新增 3 条路由处理（加在现有 `if parsed.path != "/api/analyze"` 之前）

### ✅ 验收标准

#### 路由调度（handle_post 方法）

当前代码：
```python
def handle_post(self, request: BaseHTTPRequestHandler) -> None:
    parsed = urlparse(request.path)
    if parsed.path != "/api/analyze":
        send_json(request, 404, {"error": "not found"})
        return
```

改为：在 `/api/analyze` 判断之前，先匹配 3 个新路径。每个路径都是一个独立的 `if` 分支。

新增路由：
- `POST /keypoint` — 调用 `self._handle_keypoint(request)`
- `POST /ceshi`   — 调用 `self._handle_ceshi(request)`
- `POST /louyachi` — 调用 `self._handle_louyachi(request)`

匹配不到任何已知路径 → 404。

#### `/keypoint` 端点

1. 鉴权：调用 `self.authorized(request, parsed.query)`，未授权返回 401
2. 从 multipart/form-data 读一张图片（复用现有的 `self.read_uploads(request)`，但只取第一张）
3. 用 `self.detector` + `self.detector_lock` 检测人脸，得到 `FaceMeshDetection`
4. 无人脸 → `{"status": "no_face"}`
5. 有人脸 → 返回：
```python
{
    "status": "detected",
    "detection": detection.to_dict(),
}
```
其中 `detection.to_dict()` 包含 `raw_landmarks`（478个）、`landmarks`（语义映射）、`blendshapes`（52个）、`pose`、`face_count` 等
6. 不用写文件到磁盘（不像 `/api/analyze` 那样保存 analysis.json）

#### `/ceshi` 端点（合并：侧视 + 斜视）

1. 鉴权
2. 读一张图片
3. 检测人脸 → 无人脸返回 `{"status": "no_face"}`
4. 有人脸 → **同时**调用两个检测函数：
   - `detect_side_view(detection.to_dict())`
   - `detect_strabismus(detection.to_dict())`
5. 返回：
```python
{
    "status": "detected",
    "side_view": {
        "detected": result_sv.detected,
        "direction": result_sv.direction,
        "yaw_angle": round(result_sv.yaw_angle, 2),
        "level": result_sv.level,
    },
    "strabismus": {
        "detected": result_st.detected,
        "direction": result_st.direction,
        "confidence": round(result_st.confidence, 4),
        "details": result_st.details,
    },
}
```
6. 注意：斜视检测中的 head_pose_warning 逻辑：如果侧视判断 `yaw_angle > 20°`，斜视的 confidence 已经在 `action_detector.py` 中被打了折扣——这里无需额外处理，直接透传即可。

#### `/louyachi` 端点

1. 同上流程
2. 调用 `detect_teeth_exposure(detection.to_dict())`
3. 返回结构中的 key 为 `teeth_exposure`，包含 `detected`, `mouth_state`, `confidence`, `details`

#### 代码结构要求

- [ ] 提取一个通用的人脸检测辅助方法，避免 3 个端点重复代码：
```python
def _detect_single_face(self, request: BaseHTTPRequestHandler) -> tuple[Any, dict | None]:
    """读取一张上传图片并检测人脸。返回 (detection, error_response)。
    如果 error_response 不为 None，调用者应直接发送该错误响应。
    detection 是 FaceMeshDetection 对象。"""
```
- [ ] 3 个 handler 方法命名为 `_handle_keypoint`, `_handle_ceshi`, `_handle_louyachi`（私有方法，前缀下划线）
- [ ] 所有 endpoint 的异常处理与现有 `/api/analyze` 保持一致（`ValueError` → 400，其他 `Exception` → 500）
- [ ] 不要修改 `read_uploads` 的行为（它支持多图上传，新端点只需要第一张）
- [ ] 不要修改 `detector_lock` 的使用方式（保持线程安全）

### ⚠️ 需要关注

- `read_uploads` 返回 `list[UploadedImage]`，新端点只需要 `uploads[0]`
- `read_uploads` 会把图片写入 `upload_dir` 磁盘目录——这是现有行为，保留不动
- 注意：`self.detector.detect_image_path(upload.path)` 的调用方式参考 `cli.py:182`
- 新端点不需要传 `media_role` 参数（不是不对称分析）
- `/ceshi` 同时调用两个检测函数，detection.to_dict() 只调用一次（复用检测结果）

### 🔗 参考资料

- `web_server.py:275-293` — 现有 `handle_post` 结构
- `web_server.py:348-377` — 现有 `analyze_uploads` 方法（detector 调用方式参考）
- `cli.py:153-214` — `analyze_one()` 中 detector 的使用方式
