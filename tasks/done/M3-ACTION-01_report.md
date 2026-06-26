# M3-ACTION-01 开发报告

## 1. 开发过程

1. 读取任务单 `tasks/queue/M3-ACTION-01.md`，确认本次只允许新增
   `modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`，
   并在完成后写入本报告。
2. 读取参考实现：
   - `modules/facial_asymmetry_service/facial_asymmetry_service/cli.py` 的
     `detection_summary()`，确认 detection dict 字段结构。
   - `src/facesymai/landmarks/mediapipe_face_mesh.py` 的语义 landmark 映射与
     `FaceMeshDetection.to_dict()`。
   - `src/facesymai/landmarks/mediapipe_face_landmarker.py` 的 MediaPipe Tasks
     detection 构造与 pose 输出。
3. 新建 `action_detector.py`，按任务单实现斜视、露齿、侧视三个检测函数。
4. 执行模块自测：
   `scripts/run_in_project_env.sh python modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`
5. 执行语法编译检查：
   `scripts/run_in_project_env.sh python -m py_compile modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`
6. 执行项目测试：
   `env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi scripts/run_in_project_env.sh pytest -q`

验证结果：`64 passed, 3 warnings`。warnings 为既有 Pillow deprecation warning，非本次新增模块导致。

## 2. 开发思路

本任务是动作检测基础模块，不接入 Web API 或 Rule62 主流程。实现选择保持最小范围：

- 只依赖标准库 `math`、`dataclasses`、`typing`。
- 所有阈值定义为模块级常量，便于后续 M3-ACTION-02 或校准任务调整。
- 三个公开函数统一接收 `FaceMeshDetection.to_dict()` 风格的 `detection: dict[str, Any]`。
- 空 `blendshapes`、缺失鼻部 landmark、非法数值等边界输入返回 `detected=False`，避免上层调用出现异常。
- 结果使用 dataclass，便于后续 API 层用 `dataclasses.asdict()` 序列化。

## 3. 代码变更清单

新增：

- `modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`
  - 新增 `StrabismusResult`
  - 新增 `TeethExposureResult`
  - 新增 `SideViewResult`
  - 新增 `detect_strabismus()`
  - 新增 `detect_teeth_exposure()`
  - 新增 `detect_side_view()`
  - 新增 `if __name__ == "__main__"` mock self-test

未修改：

- 未修改 `web_server.py`
- 未修改 `__init__.py`
- 未修改数据集、模型、环境或依赖
- 未执行 commit/push/分支操作

## 4. 核心代码解读

### `detect_strabismus(detection)`

读取 `eyeLookInLeft`、`eyeLookInRight`、`eyeLookOutLeft`、`eyeLookOutRight`。

核心计算：

```text
left_gaze = eyeLookOutLeft - eyeLookInLeft
right_gaze = eyeLookOutRight - eyeLookInRight
asymmetry = abs(left_gaze - right_gaze)
confidence = min(1.0, asymmetry / 0.3)
```

当 `asymmetry >= 0.3` 时输出 `detected=True`。如果 `pose.yaw` 绝对值大于 20 度，`confidence` 乘以 0.5，并在 `details.head_pose_warning` 记录 `True`。

### `detect_teeth_exposure(detection)`

读取 `jawOpen`、`mouthStretchLeft`、`mouthStretchRight`、`mouthSmileLeft`、`mouthSmileRight`。

核心判断：

```text
lip_stretch = (mouthStretchLeft + mouthStretchRight) / 2
mouth_open = jawOpen > 0.15
lip_stretched = lip_stretch > 0.1
```

- `mouth_open and lip_stretched`：`teeth_visible`
- `mouth_open and not lip_stretched`：`mouth_open_no_teeth`
- 其他：`mouth_closed`

### `detect_side_view(detection)`

读取语义点 `nose_bridge` 和 `nose_tip`，按任务单公式计算：

```text
dx = nose_tip.x - nose_bridge.x
dz = nose_tip.z - nose_bridge.z
yaw = degrees(atan2(dx, dz))
```

分级逻辑：

- `abs(yaw) > 40`：`extreme`，`detected=True`
- `abs(yaw) > 25`：`moderate`，`detected=True`
- `abs(yaw) > 15`：`slight`，`detected=False`
- 其他：`frontal`，`detected=False`

缺失 `nose_bridge` 或 `nose_tip` 时返回默认 frontal 结果，并在 `details.error` 记录
`missing_nose_landmarks`。

## 5. 遇到的问题与解决方案

1. 任务单要求 `SideViewResult` 标注缺失鼻部 landmark 的错误，但给出的 dataclass 草案没有
   `details` 字段。
   - 处理：为 `SideViewResult` 增加 `details: dict[str, Any]`，与另外两个结果类保持一致，且不影响任务单要求的
     `detected`、`direction`、`yaw_angle`、`level` 字段。
2. `StrabismusResult.details` 需要记录 `head_pose_warning: true`，不是纯 float。
   - 处理：`details` 使用 `dict[str, Any]`，支持数值、布尔值和错误字符串。
3. 当前仓库存在本任务前已有的脏工作树。
   - 处理：只新增本任务允许的两个文件，不回滚、不修改、不归因已有改动。

## 6. 参考来源

- `tasks/queue/M3-ACTION-01.md`
- `modules/facial_asymmetry_service/facial_asymmetry_service/cli.py`
- `src/facesymai/landmarks/mediapipe_face_mesh.py`
- `src/facesymai/landmarks/mediapipe_face_landmarker.py`
- `AGENTS.md`
