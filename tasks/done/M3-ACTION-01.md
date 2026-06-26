## 🎫 任务单 #M3-ACTION-01 — 待 Engineer 执行

**任务名称**：创建人脸动作检测模块 `action_detector.py`
**优先级**：P1
**依赖**：无（可独立开发，依赖现有 MediaPipe 基础设施）

---

## 🔧 角色与约束（Engineer 身份）

你是本项目的 Engineer Agent。在本次任务中，你必须遵守以下约束：

### 执行边界
1. **只执行本任务单描述的内容**，不得自行扩展需求、变更架构、修改技术选型。
2. 任务单中未明确要求的文件/模块/依赖，不得新增或修改。
3. 不得自行发起新的实验、训练、数据采集或模型下载。

### 决策权限
4. 遇到技术阻塞（依赖缺失、API 不可用、数据格式不匹配等）时：写清阻塞原因和影响范围，不要自行绕过或换方案，停止执行并回报 PM。
5. 遇到多个实现路径时，选择任务单明确指定的路径；如任务单未指定，选最简路径并注明选择理由。

### 产出规范
6. 完成后必须按以下顺序写入 `tasks/done/M3-ACTION-01_report.md`：开发过程（分步骤）→ 开发思路 → 代码变更清单 → 核心代码解读 → 遇到的问题与解决方案 → 参考来源。
7. 所有产出文件路径必须使用任务单中规定的路径。
8. 代码必须通过任务单中指定的验证命令后再写回报。

### 禁止事项
9. ❌ 不得自行 commit、push、创建分支或修改 git 历史。
10. ❌ 不得自行安装系统级包或修改 conda/pip 环境（除非任务单明确要求）。
11. ❌ 不得读取、打印或记录任何凭据文件（.env、token、key 等）。

---

### 📖 技术教学：blendshape 阈值方案原理

MediaPipe Face Landmarker 输出 52 个 blendshapes，每个是 0~1 的浮点数，表示对应面部动作的强度。这些值来自 MediaPipe 在百万级人脸数据上训练的模型输出，可以直接用作阈值判断，**不需要额外训练**。

三个检测任务的技术原理：

**斜视**：左右眼球的 `eyeLookIn/Out` 值在正常人注视同一目标时应一致。斜视患者的偏斜眼会表现出不对称的内/外转值。检测公式：`asymmetry = |(outL - inL) - (outR - inR)|`。

**露齿**：需要"嘴张开 + 嘴唇拉伸"两个条件同时满足。单纯 `jawOpen` 高可能只是张嘴（打哈欠），需要 `mouthStretch` 确认嘴唇被横向拉开露出牙齿。

**侧视**：鼻梁(168)→鼻尖(1) 的 3D 向量中，x 偏移反映左右转头角度（yaw）。MediaPipe 的 z 是相对于鼻梁参考点的深度值，用作归一化基准。

---

### 📝 任务描述

在 `modules/facial_asymmetry_service/facial_asymmetry_service/` 下新建 `action_detector.py`，实现三个检测函数。

### 📥 输入文件

- 参照：`modules/facial_asymmetry_service/facial_asymmetry_service/cli.py` 中的 `detection_summary()`（了解 detection dict 结构）
- 参照：`src/facesymai/landmarks/mediapipe_face_mesh.py` 中的 `MEDIAPIPE_FACE_MESH_LANDMARKS` 和 `FaceMeshDetection` dataclass
- 参照：`src/facesymai/landmarks/mediapipe_face_landmarker.py` 中的 `_estimate_pose()`（了解 pose 计算方式）

### 📤 输出要求

- [ ] 新文件 `modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`
- [ ] 包含以下三个公开函数和类型定义：

```python
from dataclasses import dataclass
from typing import Any

@dataclass
class StrabismusResult:
    detected: bool
    direction: str  # "esotropia_left" | "esotropia_right" | "exotropia_left" | "exotropia_right" | "none"
    confidence: float  # 0~1
    details: dict[str, float]

@dataclass
class TeethExposureResult:
    detected: bool
    mouth_state: str  # "teeth_visible" | "mouth_open_no_teeth" | "mouth_closed"
    confidence: float
    details: dict[str, float]

@dataclass
class SideViewResult:
    detected: bool
    direction: str  # "left" | "right" | "center"
    yaw_angle: float  # 度数
    level: str  # "frontal" | "slight" | "moderate" | "extreme"

def detect_strabismus(detection: dict[str, Any]) -> StrabismusResult:
    """从 MediaPipe detection dict 检测斜视"""

def detect_teeth_exposure(detection: dict[str, Any]) -> TeethExposureResult:
    """从 MediaPipe detection dict 检测露齿"""

def detect_side_view(detection: dict[str, Any]) -> SideViewResult:
    """从 MediaPipe detection dict 检测侧视"""
```

- [ ] 所有三个函数接受同一个 `detection: dict[str, Any]` 参数（即 `FaceMeshDetection.to_dict()` 的返回值，包含 `raw_landmarks`、`landmarks`、`blendshapes`、`pose` 四个字段）

### ✅ 验收标准

#### detect_strabismus
1. 从 `detection["blendshapes"]` 读取 `eyeLookInLeft`, `eyeLookInRight`, `eyeLookOutLeft`, `eyeLookOutRight`
2. 计算 `left_gaze = eyeLookOutLeft - eyeLookInLeft`，`right_gaze = eyeLookOutRight - eyeLookInRight`
3. `asymmetry = abs(left_gaze - right_gaze)`，阈值暂定 0.3
4. 不对称且 `left_gaze < right_gaze` → esotropia_left（左眼内斜）；不对称且 `left_gaze > right_gaze` → esotropia_right；`eyeLookIn` 主导时判断为内斜（esotropia），`eyeLookOut` 主导时判断为外斜（exotropia）
5. 如果人脸 yaw 角 > 20°（从 `detection["pose"]["yaw"]` 读取），confidence 打折扣（乘以 0.5），并在 details 里记录 `head_pose_warning: true`
6. confidence = min(1.0, asymmetry / 0.3)，clamp 到 [0, 1]

#### detect_teeth_exposure
1. 从 `detection["blendshapes"]` 读取 `jawOpen`, `mouthStretchLeft`, `mouthStretchRight`, `mouthSmileLeft`, `mouthSmileRight`
2. `lip_stretch = (mouthStretchLeft + mouthStretchRight) / 2`
3. `mouth_open = jawOpen > 0.15`，`lip_stretched = lip_stretch > 0.1`
4. `mouth_open AND lip_stretched` → teeth_visible
5. `mouth_open AND NOT lip_stretched` → mouth_open_no_teeth
6. 否则 → mouth_closed
7. confidence = min(1.0, (jawOpen / 0.15 + lip_stretch / 0.1) / 2)

#### detect_side_view
1. 从 `detection["landmarks"]` 读取 `nose_bridge` 和 `nose_tip`（使用 MediaPipe 索引 168 和 1 对应的语义名）
2. 计算 `dx = nose_tip["x"] - nose_bridge["x"]`，`dz = nose_tip["z"] - nose_bridge["z"]`
3. `yaw = math.degrees(math.atan2(dx, dz))`（注意：MediaPipe 的 z 轴方向，结果可能需要取负号，以实际测试为准）
4. |yaw| > 25° → detected=true, level="moderate"；|yaw| > 40° → level="extreme"；|yaw| > 15° → detected=false, level="slight"；否则 → frontal
5. direction = "left" if yaw < 0 else "right"
6. 细节：如果 `nose_bridge` 或 `nose_tip` 不在 landmarks 中（key 不存在）→ 返回 detected=False 且注明 `error: "missing_nose_landmarks"`

#### 通用要求
- [ ] 每个函数必须处理 boundary case：`blendshapes` 为空 dict 时返回默认值（detected=false）
- [ ] 使用 `math` 标准库（不要引入 numpy）
- [ ] 所有阈值定义为模块级常量（如 `STRABISMUS_THRESHOLD = 0.3`），方便后续调整
- [ ] 文件包含 `if __name__ == "__main__":` 块，用 mock detection dict 做 self-test
- [ ] 类型注解完整（使用 `from __future__ import annotations` + dataclass）

### ⚠️ 需要关注

- MediaPipe blendshape 的 key 名称是 camelCase（如 `eyeLookInLeft`），不是 snake_case
- 阈值 0.3 / 0.15 / 25° 是初始值，可能在后续校准中调整
- 侧视的 z 轴方向可能与直觉相反，需要你实际运行时验证并调整符号

### 🔗 参考资料

- `src/facesymai/landmarks/mediapipe_face_landmarker.py` — MediaPipe detection 的结构
- `src/facesymai/landmarks/mediapipe_face_mesh.py` — `FaceMeshDetection.to_dict()` 的输出格式
- 当前文件 `modules/facial_asymmetry_service/facial_asymmetry_service/cli.py:217-227` — `detection_summary()` 展示了 detection dict 的字段
