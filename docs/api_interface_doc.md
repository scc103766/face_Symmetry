# 人脸关键点检测与动作判断 API 接口文档

> 服务地址：`http://192.168.17.175:18432`
> 更新时间：2026-06-24
> 当前版本：v3.0

---

## 1. 服务概述

基于 MediaPipe Face Landmarker，提供人脸关键点检测及三项动作判断。所有接口 HTTP POST + multipart/form-data，无需鉴权。

### 接口总览

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/action` | GET/POST | 动作检测（Web UI 页面 + API 调用） |
| `/keypoint` | POST | 人脸 478 点关键点检测 |
| `/ceshi` | POST | 眼球侧视检测 |
| `/louyachi` | POST | 露齿检测 |
| `/api/detect` | POST | 批量关键点检测 |
| `/api/detect-folder` | POST | 文件夹批量检测 |

---

## 2. 接口详情

### 2.1 健康检查

```
GET /api/health
```

```bash
curl http://192.168.17.175:18432/api/health
```

```json
{
  "status": "ok",
  "endpoints": { "health": "...", "keypoint": "...", "ceshi": "...", "louyachi": "...", "action_page": "..." }
}
```

---

### 2.2 动作检测（一键三合一）

```
GET  /action     → Web UI 上传页面
POST /action     → 上传图片，同时返回 /keypoint + /ceshi + /louyachi 结果
```

**POST 请求参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| images | file | 是 | 单张图片，jpg/jpeg/png，≤25MB |

**POST 响应关键字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | `detected` / `no_face` |
| keypoint.landmarks | object | 25 个语义关键点 |
| side_view.detected | bool | 是否侧视 |
| side_view.direction | string | `left` / `right` / `center` |
| side_view.level | string | `frontal` / `moderate` / `extreme` |
| teeth_exposure.detected | bool | 是否露齿 |
| teeth_exposure.mouth_state | string | `teeth_visible` / `mouth_open_no_teeth` / `mouth_closed` |
| teeth_exposure.confidence | float | 置信度（0~1） |

```bash
curl -X POST http://192.168.17.175:18432/action -F "images=@face.jpg"
```

```json
{
  "status": "detected",
  "keypoint": {
    "landmarks": { "nose_tip": {"x": 0.501, "y": 0.512}, "left_eye_outer": {"x": 0.398, "y": 0.401} }
  },
  "side_view": {
    "detected": true,
    "direction": "left",
    "level": "moderate",
    "confidence": 0.62
  },
  "teeth_exposure": {
    "detected": true,
    "mouth_state": "teeth_visible",
    "confidence": 0.83
  }
}
```

---

### 2.3 关键点检测

```
POST /keypoint
Content-Type: multipart/form-data
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| images | file | 是 | 单张图片，jpg/jpeg/png，≤25MB |

**响应关键字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | `detected` / `no_face` |
| detection.raw_landmarks | array | 478 个关键点 `[{x,y,z,confidence}]` |
| detection.landmarks | object | 25 个语义关键点 |
| detection.blendshapes | object | 52 维 blendshape 分数 |
| detection.pose | object | 头部姿态 `{yaw, pitch, roll}`（度） |

```bash
curl -X POST http://192.168.17.175:18432/keypoint -F "images=@face.jpg"
```

```json
{
  "status": "detected",
  "detection": {
    "landmarks": {
      "nose_tip": {"x": 0.501, "y": 0.512, "z": -0.002},
      "left_eye_outer": {"x": 0.398, "y": 0.401},
      "right_eye_outer": {"x": 0.604, "y": 0.398},
      "left_mouth_corner": {"x": 0.419, "y": 0.592},
      "right_mouth_corner": {"x": 0.583, "y": 0.589}
    },
    "blendshapes": { "jawOpen": 0.035, "eyeLookInLeft": 0.012 },
    "pose": { "yaw": -5.05, "pitch": 2.13, "roll": -0.87 }
  }
}
```

---

### 2.4 侧视检测

```
POST /ceshi
Content-Type: multipart/form-data
```

检测眼球是否看向侧方（非头部转动），基于 eyeLook blendshape。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| images | file | 是 | 单张图片，jpg/jpeg/png，≤25MB |

**响应关键字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | `detected` / `no_face` |
| side_view.detected | bool | 是否侧视 |
| side_view.direction | string | `left`（眼球看左）/ `right`（看右）/ `center`（正视） |
| side_view.level | string | `frontal` / `moderate` / `extreme` |
| side_view.confidence | float | 置信度（0~1），基于 gaze_diff 线性映射 |

**判定规则**

```
gaze_left  = eyeLookOutLeft + eyeLookInRight
gaze_right = eyeLookInLeft  + eyeLookOutRight
gaze_diff  = gaze_left - gaze_right

|gaze_diff| > 1.0  → extreme / detected
|gaze_diff| > 0.5  → moderate / detected
其他              → frontal
```

```bash
curl -X POST http://192.168.17.175:18432/ceshi -F "images=@face.jpg"
```

```json
{
  "status": "detected",
  "side_view": {
    "detected": true,
    "direction": "left",
    "level": "extreme",
    "confidence": 1.0
  }
}
```

---

### 2.5 露齿检测

```
POST /louyachi
Content-Type: multipart/form-data
```

多信号融合：口唇几何 + 色差 + 边缘特征 + 头部姿态校准。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| images | file | 是 | 单张图片，jpg/jpeg/png，≤25MB |

**响应关键字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | `detected` / `no_face` |
| teeth_exposure.detected | bool | 是否露齿 |
| teeth_exposure.mouth_state | string | `teeth_visible` / `mouth_open_no_teeth` / `mouth_closed` |
| teeth_exposure.confidence | float | 置信度（0~1） |

**判定规则**

```
基础判据：口唇几何（唇间距 / 嘴角距 / 内唇面积）

色差辅助：口腔内部 HSV 分析，区分白色牙齿 vs 红色唇/龈组织
边缘辅助：切牙连通域宽度 + 边缘梯度，区分真牙齿 vs 唇反光碎片
姿态校准：face_oval 宽高比估计头部偏转，侧脸时自动放宽阈值
```

```bash
curl -X POST http://192.168.17.175:18432/louyachi -F "images=@face.jpg"
```

```json
{
  "status": "detected",
  "teeth_exposure": {
    "detected": true,
    "mouth_state": "teeth_visible",
    "confidence": 0.92
  }
}
```

---

### 2.6 批量关键点检测

```
POST /api/detect
Content-Type: multipart/form-data
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| images | file | 是 | 可重复上传多张，jpg/jpeg/png，单张≤25MB |

```bash
curl -X POST http://192.168.17.175:18432/api/detect \
  -F "images=@front.jpg" -F "images=@smile.jpg"
```

### 2.7 文件夹批量检测

```
POST /api/detect-folder
Content-Type: application/json
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| image_dir | string | 是 | 图片目录绝对路径 |
| recursive | bool | 否 | 是否递归子目录（默认 true） |

```bash
curl -X POST http://192.168.17.175:18432/api/detect-folder \
  -H "Content-Type: application/json" \
  -d '{"image_dir": "/path/to/images", "recursive": true}'
```

---

## 3. 错误码

| HTTP 状态码 | 说明 |
|-------------|------|
| 200 | 成功（检查 `status` 区分 `detected` / `no_face`） |
| 400 | 参数错误（格式、大小、空文件） |
| 500 | 服务端异常 |

---

## 4. Python 调用示例

```python
import requests

BASE = "http://192.168.17.175:18432"

# 关键点
r = requests.post(f"{BASE}/keypoint", files={"images": open("face.jpg", "rb")}, timeout=30)
print(r.json()["status"])

# 侧视
r = requests.post(f"{BASE}/ceshi", files={"images": open("face.jpg", "rb")}, timeout=30)
s = r.json()["side_view"]
print(f"侧视: {s['detected']}, {s['direction']}, {s['level']}")

# 露齿
r = requests.post(f"{BASE}/louyachi", files={"images": open("face.jpg", "rb")}, timeout=30)
t = r.json()["teeth_exposure"]
print(f"露齿: {t['detected']}, {t['mouth_state']}, {t['confidence']}")

# 文件夹批量
r = requests.post(f"{BASE}/api/detect-folder", json={"image_dir": "/data/images"}, timeout=120)
print(r.json()["status"])
```

---

## 5. 检测指标

517 患者 / 4115 张图片全量测试：

| 检测能力 | 当前值 | 目标 | 状态 |
|---------|:---:|:---:|:--:|
| 人脸检出 | 99.6% | — | ✅ |
| 侧视检出(left) | 95.9% | ≥60% | ✅ |
| 侧视检出(right) | 86.4% | ≥60% | ✅ |
| 正脸侧视误判 | 18.7% | ≤10% | ✗ |
| 露齿检出 | 75.0% | ≥55% | ✅ |
| 闭嘴准确 | 97.9% | ≥97% | ✅ |
| 闭眼准确 | 97.7% | ≥97% | ✅ |

---

## 变更记录

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-24 | v3.0 | /ceshi 改为 eye gaze blendshape，移除 strabismus；/louyachi 改为几何+色差+边缘+Pose；新增 /action；精简响应示例为关键字段 |
| 2026-06-23 | v2.0 | 新增 /keypoint /ceshi /louyachi |
| — | v1.0 | /api/detect /api/detect-folder |
