# M3-P0-05 Completion Report

## 任务概述

- 任务单：`tasks/queue/M3-P0-05.md`
- 目标：在 M3-P0-04 色差通道基础上，增加切牙边缘特征与 pose 分桶校准，增强 `/louyachi` 露齿检测。
- 主要修改文件：`modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`
- 服务链路：继续沿用 M3-P0-04 已完成的 `image_path` 传递，未继续修改 `web_server.py` / `api_server.py`。

## 开发过程

1. 读取 `AGENTS.md`、任务单和项目上下文，确认本任务边界为露齿检测增强。
2. 在 `action_detector.py` 中新增 mouth region 统一分析函数，复用 M3-P0-04 的 HSV 色差通道。
3. 增加切牙边缘特征：
   - `max_tooth_region_width`
   - `tooth_region_count`
   - `edge_gradient_max`
   - `tooth_edge_score`
4. 增加 pose 分桶：
   - `frontal`
   - `slight_turn`
   - `moderate_turn`
   - 对应 `POSE_CALIBRATION`
5. 调整融合逻辑：
   - geometry 仍是主判据。
   - color 仍是辅助 rescue/veto。
   - edge 只做 guarded rescue，不作为单独 veto。
   - combined rescue 保留，但提高阈值，避免其成为主分类器。
6. 使用离线缓存特征做阈值校准，再用 HTTP 全量评估确认结果。

## 开发思路

M3-P0-04 的主要问题是 HSV 色差能把 teeth 拉到 `75.0%`，但 forehead/frown 中唇部或牙龈反光会和牙齿颜色重叠。M3-P0-05 因此增加结构信号，但实测后发现：

- `edge_gradient_max` 在不少负样本也很高，不能直接作为强分类器。
- `max_tooth_region_width` 和 `tooth_region_count` 有一定帮助，但与真露齿仍有明显重叠。
- 当前数据集的 `_face_pose_level()` 全部落在 `frontal`，因此 pose 分桶结构已接入，但本轮全量评估中不会实际改变阈值。

最终策略是保守使用 edge：先让颜色弱证据执行 veto，再让结构较明确的 edge rescue 补回少量真牙齿样本。这样可以在不牺牲 teeth 目标的前提下，略微改善 frown/front/eyes。

## 代码变更清单

- 新增/调整常量：
  - `POSE_CALIBRATION`
  - `EDGE_RESCUE_THRESHOLD`
  - `TEETH_EDGE_RESCUE_LIP_GAP_THRESHOLD`
  - `TEETH_EDGE_RESCUE_LIP_AREA_THRESHOLD`
  - `TEETH_EDGE_RESCUE_REGION_COUNT_MAX`
  - `TEETH_COMBINED_RESCUE_THRESHOLD`
- 新增函数：
  - `_analyze_mouth_region(...)`
  - `_crop_mouth_region(...)`
  - `_teeth_edge_features(...)`
  - `_empty_teeth_edge_features()`
  - `_face_pose_level(...)`
  - `_mouth_feature_group(...)`
  - `_safe_float(...)`
- 保留兼容函数：
  - `_analyze_mouth_color(...)`
  - `_crop_mouth_interior(...)`
- 修改函数：
  - `detect_teeth_exposure(detection, image_path=None)`
    - `details` 在传入 `image_path` 时新增 `edge_features`、`pose_level`、`pose_factor`。
    - 融合逻辑新增 color + edge + pose-aware thresholds。

## 核心代码解读

- `detect_teeth_exposure(...)`
  - 先计算原有 lip geometry 和 jawOpen。
  - 如果有 `image_path`，调用 `_analyze_mouth_region(...)` 得到 color/edge/pose。
  - 使用 `pose_factor` 缩放 color rescue、color veto、edge rescue、combined rescue 阈值。
  - color/combined rescue 先参与辅助判定。
  - color veto 继续压制弱几何或低颜色证据样本。
  - edge rescue 最后补回结构上更像牙齿的候选，避免被低 HSV 分数直接压掉。

- `_teeth_edge_features(...)`
  - 使用 HSV 阈值生成 tooth-like mask。
  - 用 `cv2.connectedComponentsWithStats(...)` 统计亮区连通域宽度和数量。
  - 用 Sobel 水平梯度计算边缘强度。
  - 组合为 `tooth_edge_score`。

- `_face_pose_level(...)`
  - 读取 `face_oval` 点集。
  - 用 face width / face height 估计正脸或转头等级。
  - 当前全量 eval 样本均为 `frontal`。

## 遇到的问题与解决方案

1. 初版 edge rescue 误报增加：
   - 现象：teeth 到 `81.8%`，但 forehead/frown/front/eyes 均下降。
   - 原因：edge score 在唇部反光和强边缘负样本上也偏高。
   - 处理：提高 edge 使用门槛，并把 edge 限制为最后的 guarded rescue。

2. Sobel 人工边缘污染：
   - 现象：ROI 外部置黑会导致多边形边界产生人为强边缘。
   - 处理：梯度在原始 mouth ROI 上计算，HSV tooth mask 仍只在口腔 polygon 内生效。

3. 目标未全部达成：
   - teeth/front/eyes 达标。
   - forehead/frown 未达标。
   - 原因：当前 geometry/color/edge 三组特征在 forehead/frown 误报与真露齿样本之间仍高度重叠，继续压误报会把 teeth 召回压到 75% 以下。

## 验证结果

语法与单测：

```bash
scripts/run_in_project_env.sh python -m py_compile \
  modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py \
  modules/facial_asymmetry_service/facial_asymmetry_service/web_server.py \
  modules/mediapipe_face_keypoint_detector/face_keypoint_detector/api_server.py

scripts/run_in_project_env.sh python \
  modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py

env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi \
  scripts/run_in_project_env.sh pytest -q
```

结果：`64 passed, 3 warnings`。

HTTP 冒烟：

- 临时服务端口：`18433`
- `/api/health`：OK
- `/louyachi` 样本响应：
  - `status=detected`
  - `teeth_exposure.detected=true`
  - `details.color_features` 存在
  - `details.edge_features` 存在
  - `details.pose_level=frontal`

完整 API eval：

```bash
env PYTHONPATH=/supercloud/llm-code/scc/scc/FaceSymAi \
  scripts/run_in_project_env.sh python scripts/eval_action_api_full.py \
  --api http://127.0.0.1:18433 --delay 0
```

详细结果：`tmp/full_eval_action_api.json`

### /louyachi 指标

| Role | Expected | Correct | Total | Acc |
| --- | --- | ---: | ---: | ---: |
| eyes_closed | False | 500 | 512 | 97.7% |
| forehead_wrinkle | False | 469 | 511 | 91.8% |
| front | False | 503 | 514 | 97.9% |
| frown | False | 486 | 511 | 95.1% |
| teeth | True | 384 | 512 | 75.0% |
| TOTAL | - | 2342 | 2560 | 91.5% |

目标状态：

- teeth `75.0%`：达到 `>=75%`
- front `97.9%`：达到 `>=97%`
- eyes_closed `97.7%`：达到 `>=97%`
- forehead_wrinkle `91.8%`：未达到 `>=94%`
- frown `95.1%`：未达到 `>=96%`

对比 M3-P0-04：

| Role | M3-P0-04 | M3-P0-05 |
| --- | ---: | ---: |
| eyes_closed | 97.3% | 97.7% |
| forehead_wrinkle | 91.6% | 91.8% |
| front | 97.7% | 97.9% |
| frown | 94.3% | 95.1% |
| teeth | 75.0% | 75.0% |
| TOTAL | 91.2% | 91.5% |

## 参考来源

- `tasks/queue/M3-P0-05.md`
- `tasks/done/M3-P0-04_report.md`
- `modules/facial_asymmetry_service/facial_asymmetry_service/action_detector.py`
- `tmp/m3_p0_05_feature_items.json`
- `tmp/m3_p0_05_louyachi_smoke.json`
- `tmp/full_eval_action_api.json`

## Engineer 建议

1. 不建议继续只靠 HSV + Sobel + 连通域阈值硬调。当前 false positive 与 true teeth 的特征分布重叠明显，进一步调阈值会伤害 teeth 召回。
2. 建议下一步引入更局部的牙齿形态信号：上/下切牙水平边界、亮区纵横比、上下唇之间的连续白色带，而不是只看整块 ROI 的最大亮区。
3. 建议人工抽样复核 forehead/frown 的 42 个误报和 teeth 的 128 个漏检，确认是否存在标签或拍摄动作混入问题。
4. pose 分桶已接入，但当前 eval 全为 `frontal`。如果要验证 pose 价值，需要单独用 left/right profile 或半侧脸露齿样本集做分桶评估。

