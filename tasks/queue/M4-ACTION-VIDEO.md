## 🎫 任务单 #M4-ACTION-VIDEO — 待 Engineer 执行

**任务名称**：18432 新增视频五动作帧提取端点 `/api/extract-actions`
**优先级**：P0
**依赖**：M3-P0-05（露齿检测已完成，色差/边缘/Pose就绪）

---

## 🔧 角色与约束（Engineer 身份）

你是本项目的 Engineer Agent。在本任务中你必须遵守：

### 执行边界
1. **只执行本任务单描述的内容**，不得自行扩展需求。
2. 修改 `action_detector.py` + `api_server.py`，不新增文件。

### 决策权限
3. 遇到技术阻塞时：写清原因，停止并回报 PM。
4. 多路径时选最简方案并注明理由。

### 产出规范
5. 完成后写入 `tasks/done/M4-ACTION-VIDEO_report.md`。
6. 报告末尾「💡 Engineer 建议」节。

### 禁止事项
7. ❌ 不得 commit/push/修改 git 历史。
8. ❌ 不得修改 conda/pip 环境。

---

## 📝 任务描述

在 18432 服务新增端点：输入一段视频 → 自动识别五个动作 → 输出每个动作置信度最高的帧。

五个目标动作：**正脸 / 露齿 / 侧视 / 舌面 / 舌底**。

---

## ✅ 子任务 1：舌头可见性检测

在 `action_detector.py` 中增加舌头判断，复用已有的 HSV 色差分析。

### 1A：新增 `_is_tongue_visible()` 函数

```python
def _is_tongue_visible(
    color_features: dict | None,
    lip_gap: float,
) -> bool:
    """Detect tongue visibility inside open mouth."""
    if color_features is None:
        return False
    if lip_gap < 0.06:          # 嘴不够开
        return False
    if color_features["mouth_pixel_count"] < 50:  # 口腔面积太小
        return False
    # 粉色组织主导（非牙齿白、非暗区黑）
    lip_ratio = color_features.get("lip_ratio", 0)
    return lip_ratio > 0.50
```

### 1B：修改 `detect_teeth_exposure` 增加 `tongue_visible` 状态

在现有判定逻辑之后增加：

```python
if mouth_state == "mouth_open_no_teeth" and color_features is not None:
    if _is_tongue_visible(color_features, lip_gap):
        mouth_state = "tongue_visible"
```

`TeethExposureResult` 的 `mouth_state` 新增合法值 `"tongue_visible"`。

---

## ✅ 子任务 2：视频抽帧

在 `api_server.py` 中新增 `_extract_video_frames()` 函数。

```python
def _extract_video_frames(video_path: str, max_frames: int = 300) -> list[np.ndarray]:
    """从视频均匀抽帧，返回 BGR numpy 数组列表。"""
    import cv2
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return []
    interval = max(1, total // max_frames)
    frames = []
    for i in range(0, min(total, max_frames * interval), interval):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if ret:
            frames.append(frame)
    cap.release()
    return frames
```

---

## ✅ 子任务 3：动作段分割

```python
def _segment_actions(frame_labels: list[str], min_length: int = 3) -> list[dict]:
    """合并相邻相同标签为动作段。"""
    segments = []
    start = 0
    for i in range(1, len(frame_labels) + 1):
        if i == len(frame_labels) or frame_labels[i] != frame_labels[start]:
            if i - start >= min_length:
                segments.append({"action": frame_labels[start], "start": start, "end": i - 1})
            start = i
    return segments
```

---

## ✅ 子任务 4：新增 `/api/extract-actions` 端点

### 4A：`handle_post` 增加路由

```python
if parsed.path == "/api/extract-actions":
    self._handle_extract_actions(request, parsed.query)
    return
```

### 4B：`_handle_extract_actions()` 核心实现

流程：

1. 接收视频文件（multipart/form-data，支持 mp4/avi/mov）
2. 保存到临时路径
3. 调用 `_extract_video_frames()` 抽帧
4. 对每帧：保存为临时 jpg → `sdk.detect_image()` → `detect_side_view()` + `detect_teeth_exposure(image_path=...)`
5. 逐帧标记动作标签：

```python
label = "front"            # 默认
if sv.detected:
    label = "side_view"
elif te.mouth_state == "teeth_visible":
    label = "teeth"
elif te.mouth_state == "tongue_visible":
    label = "tongue"
```

6. 对 tongue 段：第一个 tongue 段 → `tongue_surface`，最后的 tongue 段 → `tongue_bottom`。如果只有一个 tongue 段，同时作为舌面和舌底。
7. 每段选该动作置信度最高的帧：

```
正脸: 选 teeth_exposure.mouth_state!="teeth_visible" 置信度 = 1 - sv.confidence
露齿: 选 teeth_exposure.confidence 最高
侧视: 选 sv.confidence 最高
舌头: 选 color_features.teeth_color_score 最低（粉色组织多 = 牙齿白少）
```

8. 将选中帧编码为 base64，返回 JSON。

### 4C：响应格式

```json
{
  "status": "ok",
  "total_frames": 150,
  "frames": {
    "front":    {"frame_index": 12,  "confidence": 0.95, "image_base64": "/9j/4AA..."},
    "teeth":    {"frame_index": 45,  "confidence": 0.92, "image_base64": "/9j/4AA..."},
    "side_view":{"frame_index": 78,  "confidence": 0.88, "image_base64": "/9j/4AA..."},
    "tongue_surface": {"frame_index": 110, "confidence": 0.75, "image_base64": "/9j/4AA..."},
    "tongue_bottom":  {"frame_index": 135, "confidence": 0.72, "image_base64": "/9j/4AA..."}
  },
  "segments": [
    {"action": "front",     "start_frame": 0,   "end_frame": 25},
    {"action": "teeth",     "start_frame": 26,  "end_frame": 60},
    {"action": "side_view", "start_frame": 61,  "end_frame": 95},
    {"action": "tongue",    "start_frame": 96,  "end_frame": 130},
    {"action": "tongue",    "start_frame": 131, "end_frame": 149}
  ]
}
```

---

## 修改文件汇总

| 文件 | 操作 | 内容 |
|------|------|------|
| `action_detector.py` | 新增 | `_is_tongue_visible()` |
| `action_detector.py` | 修改 | `detect_teeth_exposure` 增加 `tongue_visible` 分支 |
| `api_server.py` | 新增 | `_extract_video_frames()` / `_segment_actions()` / `_handle_extract_actions()` |
| `api_server.py` | 修改 | `handle_post` 增加 `/api/extract-actions` 路由 |
| `api_server.py` | 修改 | `/api/health` endpoints 增加 `extract_actions` |

## 验证

```bash
# 语法检查
python -m py_compile modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py
python -m py_compile modules/mediapipe_face_keypoint_detector/face_keypoint_detector/api_server.py

# 冒烟测试
curl -X POST http://192.168.17.175:18432/api/extract-actions -F "video=@test.mp4"
```

## 环境

```bash
conda activate anti-spoofing_scc_175
cd /supercloud/llm-code/scc/scc/FaceSymAi
export PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi
```
