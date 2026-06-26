## 🎫 任务单 #M3-ACTION-03 — 待 Engineer 执行

**任务名称**：编写 API 冒烟测试脚本并验证 3 个端点
**优先级**：P2
**依赖**：M3-ACTION-01 + M3-ACTION-02（`action_detector.py` 和 `web_server.py` 修改必须先完成）

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
5. 完成后必须写入 `tasks/done/M3-ACTION-03_report.md`。

### 禁止事项
6. ❌ 不得自行 commit、push、创建分支或修改 git 历史。
7. ❌ 不得自行安装系统级包或修改 conda/pip 环境。

---

### 📝 任务描述

编写测试脚本 `scripts/test_action_api.py`，启动 8790 服务后对 3 个新端点做冒烟测试，然后验证结果。

### 📥 输入文件

- 测试图片：使用 `/supercloud/llm-code/scc/scc/FaceSymAi/datasets/facesym_v1_by_name_20260119/` 下的任意患者的正脸和侧脸图片
- 参照：`scripts/test_asymmetry_api.py` — 现有的 `/api/analyze` 测试脚本

### 📤 输出要求

- [ ] 新文件 `scripts/test_action_api.py`
- [ ] 脚本接受 `--api-base-url` 参数（默认 `http://127.0.0.1:8790`）
- [ ] 脚本检查服务是否在线（GET `/api/input-spec`），不在线则报错退出

### ✅ 验收标准

#### 测试 1：`/keypoint` 端点

1. 找一张正脸图片（建议从 V1 数据集中选一个 patient 的 front 图片）
2. POST 到 `/keypoint`，检查响应：
   - `status == "detected"`
   - `detection.raw_landmarks` 是列表，长度 478
   - `detection.blendshapes` 是 dict，包含 `eyeLookInLeft`、`jawOpen` 等 key
   - `detection.landmarks` 包含 `nose_tip`、`left_eye_outer` 等语义 key
3. 打印 "PASS" 或 "FAIL" + 实际返回的 key 数量

#### 测试 2：`/ceshi` 端点（合并：侧视 + 斜视）

1. 用正脸图片 POST 到 `/ceshi`：
   - `status == "detected"`
   - `side_view` 包含 `detected`, `direction`, `yaw_angle`, `level`
   - `side_view.yaw_angle` 是浮点数（单位：度）
   - 正脸图片的 `side_view.detected` 应为 `false`，`side_view.level` 应为 `"frontal"`
   - `strabismus` 包含 `detected`, `direction`, `confidence`, `details`
   - `strabismus.confidence` 在 [0, 1] 范围内
   - 正脸图片的斜视 `detected` 应为 `false`
2. 再用一张侧脸图片（如 `eyes_right` 动作的）POST 到 `/ceshi`：
   - `side_view.detected` 应为 `true`，`side_view.direction` 应有方向
   - 检查 `strabismus.details` 中是否包含 `head_pose_warning`（侧脸时斜视判断应有警告）
3. 打印 "PASS" 或 "FAIL" + 两组结果

#### 测试 3：`/louyachi` 端点

1. 找一张露齿图片（文件名含 `teeth` 或 `smile_teeth` 的）
2. POST 到 `/louyachi`，检查响应：
   - `teeth_exposure` 包含 `detected`, `mouth_state`, `confidence`, `details`
   - 露齿图片的 `detected` 应为 `true`，`mouth_state` 应为 `"teeth_visible"`
3. 再用一张闭嘴正脸图片验证 `detected` 为 `false`
4. 打印 "PASS" 或 "FAIL"

#### 测试 4：无脸图片

1. POST 一张纯色图或非人脸图到任意端点
2. 响应应为 `{"status": "no_face"}`（而不是 500 错误）
3. 打印 "PASS" 或 "FAIL"

#### 脚本要求

- [ ] 每个测试用 `try/except` 包裹，单个测试失败不影响其他测试
- [ ] 最后打印汇总：`X/Y tests passed`
- [ ] 失败时打印详细信息（实际返回 vs 预期）
- [ ] 使用 `requests` 库（已在 conda env `anti-spoofing_scc_175` 中）

### ⚠️ 需要关注

- 测试前需要确认 8790 服务已启动。脚本开头检查 `GET /api/input-spec` 返回 200
- 如果 M3-ACTION-02 修改了 `web_server.py`，需要重启服务才能生效
- V1 数据集的图片路径在 `01_manifest.csv` 中

### 🔗 参考资料

- `scripts/test_asymmetry_api.py` — 现有测试的模式参考
- `datasets/facesym_v1_by_name_20260119/metadata/01_manifest.csv` — 测试图片清单
