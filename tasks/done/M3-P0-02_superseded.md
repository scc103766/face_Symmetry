## 🎫 任务单 #M3-P0-02 — 待 Engineer 执行

**任务名称**：动作检测三轮优化——侧脸多信号融合 + 斜视动态阈值 + 露齿宽松策略
**优先级**：P0
**依赖**：无（只修改 `action_detector.py`）

---

## 🔧 角色与约束（Engineer 身份）

你是本项目的 Engineer Agent。在本次任务中，你必须遵守以下约束：

### 执行边界
1. **只执行本任务单描述的内容**，不得自行扩展需求。
2. 只修改 `modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py` 一个文件。
3. 不新增文件，不修改其他模块。

### 决策权限
4. 遇到技术阻塞时：写清原因，停止并回报 PM。
5. 阈值按任务单指定值，不要自行调整。

### 产出规范
6. 完成后必须写入 `tasks/done/M3-P0-02_report.md`。
7. 代码必须通过语法检查。

### 禁止事项
8. ❌ 不得 commit/push/修改 git 历史。
9. ❌ 不得修改 conda/pip 环境。

---

### 📝 任务描述

在 `action_detector.py` 中做三个优化，目标：侧脸检出 ≥55%、斜视 FP ≤20%、露齿检出 ≥50%。

---

### ✅ 子任务 1：侧脸多信号融合

**当前**：只有鼻部 yaw + 眼距比两个信号。

**改为**：四个信号 OR 融合，任一触发即判侧视。

新增两个信号：

**信号 3：脸宽比**

```python
SIDE_VIEW_FACE_RATIO_THRESHOLD = 0.55

# 在 detect_side_view() 中：
left_cheek = landmarks.get("left_cheek")
right_cheek = landmarks.get("right_cheek")
if isinstance(left_cheek, Mapping) and isinstance(right_cheek, Mapping):
    try:
        face_w = abs(float(left_cheek["x"]) - float(right_cheek["x"]))
        face_h = abs(float(chin_pt["y"]) - float(nose_bridge["y"]))
        if face_h > 1e-9:
            face_ratio = face_w / face_h
            face_detected = face_ratio < SIDE_VIEW_FACE_RATIO_THRESHOLD
    except (KeyError, TypeError, ValueError):
        face_ratio = 1.0
        face_detected = False
```

原理：正脸时 face_width / face_height ≈ 0.7~0.9，侧脸 60°+ 时骤降到 0.5 以下。

**信号 4：单眼可见度**

```python
SIDE_VIEW_EYE_ASYMMETRY_THRESHOLD = 0.4

# 在 detect_side_view() 中：
left_eye_inner = landmarks.get("left_eye_inner")
right_eye_inner = landmarks.get("right_eye_inner")
if isinstance(left_eye_inner, Mapping) and isinstance(right_eye_inner, Mapping) \
   and isinstance(eye_outer_left, Mapping) and isinstance(eye_outer_right, Mapping):
    try:
        left_eye_w = abs(float(eye_outer_left["x"]) - float(left_eye_inner["x"]))
        right_eye_w = abs(float(eye_outer_right["x"]) - float(right_eye_inner["x"]))
        if max(left_eye_w, right_eye_w) > 1e-9:
            eye_asymmetry = min(left_eye_w, right_eye_w) / max(left_eye_w, right_eye_w)
            eye_detected = eye_asymmetry < SIDE_VIEW_EYE_ASYMMETRY_THRESHOLD
    except (KeyError, TypeError, ValueError):
        eye_asymmetry = 1.0
        eye_detected = False
```

原理：正脸时双眼宽度相近（ratio ≈ 0.8~1.0），侧脸 45°+ 时远侧眼被压缩（ratio < 0.4）。

**融合逻辑**：

```python
detected = yaw_detected or eye_ratio_detected or face_detected or eye_asymmetry_detected
```

注意：`eye_ratio_detected` 是之前的眼距比信号（改名为避免和新增的 `eye_detected` 混淆）。

**details 更新**：添加 `face_width_ratio`、`eye_width_asymmetry` 字段。

**阈值保持不变**：
- yaw: 15°/22°/35°
- 眼距比: 0.22（改名为 `SIDE_VIEW_EYE_RATIO_THRESHOLD`）
- 新增脸宽比: 0.55
- 新增单眼可见度: 0.4

---

### ✅ 子任务 2：斜视动态阈值

**当前**：固定阈值 0.5，yaw>20° 时 confidence ×0.5。

**改为**：yaw 角自适应阈值。

```python
# 替换 STRABISMUS_THRESHOLD = 0.5，改为函数：
def _strabismus_threshold(yaw_deg: float) -> float:
    abs_yaw = abs(yaw_deg)
    if abs_yaw <= 10.0:
        return 0.5
    elif abs_yaw <= 20.0:
        return 0.65
    else:
        return 0.8
```

在 `detect_strabismus()` 中：

```python
# 原来：
# detected = asymmetry >= STRABISMUS_THRESHOLD

# 改为：
pose = detection.get("pose") or {}
yaw = _float_value(pose, "yaw") if isinstance(pose, Mapping) else 0.0
threshold = _strabismus_threshold(yaw)
detected = asymmetry >= threshold

# confidence 也基于动态阈值：
confidence = _clamp01(asymmetry / threshold)  # 原来除以 STRABISMUS_THRESHOLD
```

**head_pose_warning 折扣**：从 ×0.5 → ×0.3。

```python
if abs(yaw) > STRABISMUS_HEAD_POSE_WARNING_YAW_DEGREES:
    confidence *= 0.3  # 原来 0.5
    details["head_pose_warning"] = True
```

**details 更新**：添加 `threshold` 字段（现在是动态值），添加 `yaw` 字段。

---

### ✅ 子任务 3：露齿宽松策略

**当前**：`jawOpen > 0.04 AND lip_stretch > 0.1 → teeth_visible`

**改为**：三级宽松策略。

保留模块级常量：
```python
TEETH_JAW_OPEN_THRESHOLD = 0.04
TEETH_LIP_STRETCH_THRESHOLD = 0.1
TEETH_JAW_OPEN_LOOSE = 0.08       # 新增
TEETH_LIP_STRETCH_LOOSE = 0.08    # 新增  
TEETH_LIP_STRETCH_DOMINANT = 0.25 # 新增
```

判定逻辑：
```python
if lip_stretch > TEETH_LIP_STRETCH_DOMINANT and jawOpen > 0.02:
    # 唇拉伸主导：嘴唇明显横向拉开，即使张嘴不大也判露齿
    mouth_state = "teeth_visible"
    detected = True
elif jawOpen > TEETH_JAW_OPEN_LOOSE and lip_stretch > TEETH_LIP_STRETCH_LOOSE:
    # 张嘴主导：嘴张得较大，嘴唇有一定拉伸
    mouth_state = "teeth_visible"
    detected = True
elif jawOpen > TEETH_JAW_OPEN_THRESHOLD and lip_stretch > TEETH_LIP_STRETCH_THRESHOLD:
    # 原始条件
    mouth_state = "teeth_visible"
    detected = True
elif jawOpen > TEETH_JAW_OPEN_THRESHOLD:
    mouth_state = "mouth_open_no_teeth"
    detected = False
else:
    mouth_state = "mouth_closed"
    detected = False
```

**confidence** 计算保持不变。

---

### 验证命令

```bash
# 语法检查
python -m py_compile modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py

# 自测
python modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py

# 重启 18432 服务后运行全量测试
python scripts/eval_action_api_full.py
```

### 目标指标

| 能力 | 当前 | 目标 |
|------|------|------|
| 侧脸检出(profile) | 32% | ≥55% |
| 正脸侧视误判 | 12% | ≤15% |
| 斜视判否正确率 | 63% | ≥80% |
| 露齿检出(teeth) | 32% | ≥50% |

### 🔗 参考资料

- `action_detector.py` — 当前完整代码
- `tmp/full_eval_action_api.json` — 第3轮全量测试详细结果
