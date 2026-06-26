# Task 06：跨动作差异特征提取与分析

## 目标

从现有数据中提取"伪视频"特征——利用同一患者前后不同动作的图片，计算从静息到动作的变化量，发现静态图片无法捕获的动态不对称信号。

## 背景

当前规则 62 只看单张图片的静态不对称特征。但脑卒中/面瘫的核心特征可能是**动态不对称**——患者在表情动作中暴露出静态姿势下不明显的不对称。

已知每个患者有多张不同动作的图片（old：front + smile + teeth；new：front_contour + smile_teeth + eyes_right），可以提取"从静息到动作"的变化量。

## 输入数据

| 数据集 | 特征文件 | 角色对齐 |
|------|------|------|
| old | `datasets/facesym_v1_all_images_no_gate_20260119/metadata/09_mediapipe_full_features.csv` | front → front_contour; smile+teeth → smile_teeth |
| new | `datasets/stroke_warning_app_rule_test_set_20260508/metadata/40_mediapipe_evidence_image_features.csv` | front_contour; smile_teeth |

## 任务步骤

### 步骤 1：建立患者-图片-动作映射

对 old 数据集：
- 将 `media_role` 为 `front` 的图片标记为"静息"（baseline）
- 将 `media_role` 为 `smile` 或 `teeth` 的图片标记为"口部动作"（action）
- 同一患者可能有多张 smile 和多张 teeth 图片，对每个 action 图分别与 baseline 配对

对 new 数据集：
- `front_contour` → 静息
- `smile_teeth` → 口部动作

### 步骤 2：计算三类跨动作特征

#### 2A：Delta 特征（结构变化）

对每个特征 f（从 60 阶段的 21 个推荐特征 + 补充的 blendshape 原始值），计算：

```python
delta_f = f(action_image) - f(baseline_image)
```

如果患者有多张 action 图片，取 `max(delta_f)`（最差情况）。

新增特征命名：`delta_<原始特征名>`

#### 2B：动作幅度比特征（功能对称性）

对成对的 blendshape 值（如 mouthSmileLeft/mouthSmileRight），在动作图片上计算：

```python
amplitude_ratio = min(left_value, right_value) / max(left_value, right_value)
# 范围 [0, 1]，1 表示完全对称，越小越不对称
```

对以下 blendshape 对计算：

| 特征名 | left blendshape | right blendshape | 含义 |
|------|------|------|------|
| `amp_ratio_mouthSmile` | `bs_mouthSmileLeft` | `bs_mouthSmileRight` | 微笑幅度比 |
| `amp_ratio_mouthFrown` | `bs_mouthFrownLeft` | `bs_mouthFrownRight` | 撇嘴幅度比 |
| `amp_ratio_eyeBlink` | `bs_eyeBlinkLeft` | `bs_eyeBlinkRight` | 眨眼幅度比 |
| `amp_ratio_browDown` | `bs_browDownLeft` | `bs_browDownRight` | 皱眉幅度比 |
| `amp_ratio_browOuterUp` | `bs_browOuterUpLeft` | `bs_browOuterUpRight` | 抬眉幅度比 |
| `amp_ratio_cheekSquint` | `bs_cheekSquintLeft` | `bs_cheekSquintRight` | 脸颊提拉幅度比 |
| `amp_ratio_eyeSquint` | `bs_eyeSquintLeft` | `bs_eyeSquintRight` | 眯眼幅度比 |
| `amp_ratio_eyeWide` | `bs_eyeWideLeft` | `bs_eyeWideRight` | 瞪眼幅度比 |
| `amp_ratio_noseSneer` | `bs_noseSneerLeft` | `bs_noseSneerRight` | 嗤鼻幅度比 |
| `amp_ratio_mouthStretch` | `bs_mouthStretchLeft` | `bs_mouthStretchRight` | 嘴角拉伸幅度比 |
| `amp_ratio_mouthDimple` | `bs_mouthDimpleLeft` | `bs_mouthDimpleRight` | 酒窝幅度比 |
| `amp_ratio_mouthPress` | `bs_mouthPressLeft` | `bs_mouthPressRight` | 抿嘴幅度比 |
| `amp_ratio_mouthUpperUp` | `bs_mouthUpperUpLeft` | `bs_mouthUpperUpRight` | 上唇上提幅度比 |
| `amp_ratio_mouthLowerDown` | `bs_mouthLowerDownLeft` | `bs_mouthLowerDownRight` | 下唇下拉幅度比 |

#### 2C：恶化指数（不对称加剧程度）

对规则 62 的 21 个特征中的每一个，计算：

```python
deterioration_index = asymmetry(action_image) / max(asymmetry(baseline_image), 1e-9)
# > 1.0 表示动作加剧了不对称
# ≈ 1.0 表示不对称程度未随动作改变
# < 1.0 表示动作反而改善了不对称（罕见）
```

取所有 21 个特征的恶化指数的中位数作为总体恶化指数：

```python
overall_deterioration = median([deterioration_index for each of 21 features])
```

### 步骤 3：患者级聚合

同一患者可能有多个 action 图片 → 对每个跨动作特征，取所有配对中的 `max` 值。

对于 old 数据中 `smile` 和 `teeth` 都是口部动作的情况：
- 如果两个角色都存在，取两个角色中 delta/max 值更大的那个（最差情况）
- 如果只有一个角色存在，使用该角色的值

### 步骤 4：患病 vs 不患病对比分析

对上一步得到的患者级跨动作特征，做以下分析：

#### 4A：单特征 AUC 对比

计算每个跨动作特征的 directional AUC（患病群体更高的方向），与同名的静态特征 AUC 对比：

| 特征 | 静态 AUC（old） | 跨动作 AUC（old） | 静态 AUC（new） | 跨动作 AUC（new） | 改善 |
|------|:-:|:-:|:-:|:-:|:-:|
| ... | | | | | |

#### 4B：恶化指数分布

绘制 `overall_deterioration` 在患病/不患病患者中的分布直方图，计算两组间的 Cohen's d 和 KS 检验 p 值。

#### 4C：FN 患者重新评估

对规则 62 的 158 个 FN（漏检患病患者），检查：
- 有多少人的 `overall_deterioration > 1.5`（动作使不对称加剧 50% 以上）？
- 有多少人的 `amp_ratio_mouthSmile < 0.5`（微笑时一侧幅度不到另一侧的一半）？
- 输出一份"可被动态特征挽救的 FN 清单"

### 步骤 5：特征聚合与评估

将表现最好的跨动作特征（AUC > 0.55 且方向一致）与规则 62 的 21 个静态特征合并：
- 先单独评估：仅用跨动作特征的 precision/recall/specificity
- 再联合评估：静态 21 个 + 新增跨动作特征
- 报告合并前后的指标变化

## 输出

在 `datasets/combined_disease_feature_candidates_20260529/` 下创建新子目录 `cross_action_analysis/`，包含：

```
cross_action_analysis/
├── metadata/
│   ├── ca_patient_cross_action_features.csv     ← 患者级跨动作特征（所有患者）
│   ├── ca_feature_auc_comparison.csv             ← 静态 vs 跨动作 AUC 对比
│   ├── ca_deterioration_distribution.csv         ← 恶化指数分布
│   ├── ca_fn_rescue_candidates.csv               ← 可被动态特征挽救的 FN 清单
│   └── ca_combined_evaluation.json               ← 联合评估指标
├── reports/
│   └── ca_cross_action_analysis.md               ← 分析报告（含图表）
```

## 环境

```bash
source $(conda info --base)/etc/profile.d/conda.sh && conda activate anti-spoofing_scc_175
```

## 验收标准

1. `ca_patient_cross_action_features.csv` 包含所有 605 名患者的跨动作特征
2. 至少发现 3 个跨动作特征的 AUC 优于同名静态特征
3. `ca_fn_rescue_candidates.csv` 列出至少 5 名可被动态特征识别的 FN 患者
4. 联合评估指标 JSON 包含 precision/recall/specificity 对比
5. 分析报告包含关键图表和结论
