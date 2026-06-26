# M4-ACTION-VIDEO：视频五动作帧提取方案

> 创建日期：2026-06-24
> 目标：输入视频 → 自动识别五个动作 → 输出每个动作置信度最高的帧

---

## 1. 需求

输入一段患者面部动作视频，自动提取五张最佳帧：

| 动作 | 检测依据 | 已有能力 |
|------|---------|:---:|
| **正脸** | 未侧视 + 未露齿 + 未张嘴 | ✅ /ceshi + /louyachi |
| **露齿** | teeth_exposure = teeth_visible | ✅ /louyachi |
| **侧视** | side_view = True | ✅ /ceshi |
| **舌面** | 张嘴无齿 + 口腔内粉色组织 | ⚠️ 需新增 |
| **舌底** | 张嘴无齿 + 口腔内粉色组织（与舌面区分） | ⚠️ 需新增 |

## 2. 技术路线

```
视频上传 → 均匀抽帧(5fps) → 逐帧 /action 检测
                                    ↓
                          时间序列: [side_view, teeth, mouth_state, color, confidence]
                                    ↓
                          滑动窗口分割 → 识别动作段
                                    ↓
                          每段取置信度最高的帧 → 输出5张图(base64或路径)
```

## 3. 新增检测：舌头状态

当前 `/louyachi` 只有三种 mouth_state：`teeth_visible` / `mouth_open_no_teeth` / `mouth_closed`。需要增加第四种：**tongue_visible**。

### 舌头检测逻辑

```
mouth_open_no_teeth (lip_gap > 0.06, teeth未检出)
  + 口腔内粉色组织占比高 (lip_ratio > 0.50, HSV色差)
  + 口腔面积足够大 (mouth_pixel_count > 50)
  → tongue_visible
```

舌面 vs 舌底通过**视频中的先后顺序**区分：

```
舌面: 第一个 tongue_visible 段 → 通常在前半段
舌底: 最后一个 tongue_visible 段 → 通常在后半段（需仰头）
```

备选：如果视频中只有一个 tongue 段，则输出同一个最佳帧同时作为舌面和舌底。

## 4. 新增端点

### `POST /api/extract-actions`

```
输入: multipart/form-data, video file (mp4/avi/mov)
输出: {
  "status": "ok",
  "frames": {
    "front":    {"frame_index": 12,  "confidence": 0.95, "image_base64": "..."},
    "teeth":    {"frame_index": 45,  "confidence": 0.92, "image_base64": "..."},
    "side_view":{"frame_index": 78,  "confidence": 0.88, "image_base64": "..."},
    "tongue_surface": {"frame_index": 110, "confidence": 0.75, "image_base64": "..."},
    "tongue_bottom":  {"frame_index": 135, "confidence": 0.72, "image_base64": "..."}
  },
  "segments": [
    {"action": "front",  "start_frame": 0,  "end_frame": 25,  "best_frame": 12},
    {"action": "teeth",  "start_frame": 26, "end_frame": 60,  "best_frame": 45},
    ...
  ]
}
```

## 5. 动作段分割算法

```python
# 逐帧检测 → 标签序列
labels = []
for frame in frames:
    sv = detect_side_view(frame)
    te = detect_teeth_exposure(frame)
    tongue = is_tongue_visible(te, color_features)

    if sv.detected:           labels.append("side_view")
    elif te == "teeth_visible": labels.append("teeth")
    elif tongue:              labels.append("tongue")
    else:                     labels.append("front")

# 平滑（合并相邻相同标签 → 段）
segments = merge_consecutive(labels, min_segment_length=3)

# 每段选最高置信度帧
for seg in segments:
    best_frame = argmax(seg.confidences)
```

## 6. 改动范围

| 文件 | 操作 | 内容 |
|------|------|------|
| `action_detector.py` | 修改 | `detect_teeth_exposure` 中增加 `tongue_visible` 状态判断 |
| `action_detector.py` | 新增 | `def _is_tongue_visible(color_features, lip_gap)` |
| `api_server.py` | 新增 | `POST /api/extract-actions` 端点 + `_handle_extract_actions()` |
| `api_server.py` | 新增 | `_extract_video_frames()` 视频抽帧函数 |

## 7. 依赖

- OpenCV (已有) 用于 `cv2.VideoCapture` 读取视频
- 现有 `detect_side_view` / `detect_teeth_exposure` / HSV 色差分析

## 8. 与 M4-VIDEO 系列的关系

| 任务 | 目的 |
|------|------|
| M4-VIDEO-01~03 | 离线：全量视频→动态特征→模型训练 |
| M4-ACTION-VIDEO | 在线：单视频→五动作帧→API 输出 |

M4-ACTION-VIDEO 是服务化产出，M4-VIDEO 是训练管线。
