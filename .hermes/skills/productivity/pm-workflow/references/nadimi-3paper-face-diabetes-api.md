# Nadimi-Majtner 三论文综合 — 扫脸糖尿病风险评估方法

> 本参考整合三篇核心论文的技术路线，用于 PM 向 Engineer 下发"面部视频→糖尿病风险预测"类 API 任务。

## 三论文核心贡献

| # | 论文 | 期刊/年 | 核心贡献 | 本项目继承 |
|---|------|---------|---------|-----------|
| 1 | Invisible Color Variations of Facial Erythema | J Diabetes Res 2019 | 面部红度周期性波动在 DM 组显著大于对照组 (p<0.001) | 生理学基础：微血管病变→颜色波动 |
| 2 | Non-invasive detection via temporal facial colour variations | CMPB 2020 | 完整自动化管线，174人 Acc 92.86%, Sens 100% | 工程框架：视频→ROI→颜色信号→ML |
| 3 | Facial erythema detects diabetic neuropathy via RMT | Sci Rep 2020 | EVM+RMT+SOC+集成，Sens 100% | 理论深化：EVM动态放大+RMT信号/噪声分离 |

## 综合五步法

```
Step 1: 视频采集 → 60s 静息面部视频, 1080p, 30fps
Step 2: ROI 提取 → FaceSym 478点 → 6 ROI（FACE/FOREHEAD/LEFT_CHEEK/RIGHT_CHEEK/NOSE/CHIN）
Step 3: EVM 动态放大 → bandpass 0.7-4.0Hz, alpha=30
Step 4: 特征提取 → 静态面色 144维 + EVM动态 288维 + RMT谱 24维 = 456维
Step 5: ML 分类 → LR+RF 概率平均集成 → GroupKFold(patient_id)
```

## 456 维特征规格

| 组 | 来源论文 | 内容 | 维度 |
|----|---------|------|------|
| A 静态面色 | 1+2 | 6 ROI × (RGB 12 + HSV 6 + Lab 6) = 24/ROI | 144 |
| B EVM 动态 | 3 | 6 ROI × 3ch × 16 统计量（band_mean/std/rms/energy/abs_mean/ptp/magnified_std/ptp/slope_abs_mean/zero_crossings/peak_freq/peak_bpm/peak_power/total_power/snr_db + 3 跨通道） | 288 |
| C RMT 谱 | 3 | 3ch × 8 统计量（λ_max/λ_2/λ_3/trace/spectral_radius/participation_ratio/mp_upper_bound/signal_eigenvalues） | 24 |

## RMT 实现要点（不可省略）

```python
# 核心：T×6 ROI-channel 矩阵 → 6×6 协方差 → 特征值谱
cov = (M.T @ M) / T                                    # 协方差矩阵
eigenvalues = np.linalg.eigvalsh(cov)[::-1]             # 降序特征值
mp_upper = sigma² × (1 + √(T/6))²                     # Marchenko-Pastur 上界
signal_count = sum(eigenvalues > mp_upper)              # 超 MP 边界的信号特征值数
```

## MCD-rPPG 数据集处理

- **金标准**：`gold_label = (glycated_hemoglobin >= 6.5)`，ADA 标准，不可简化
- **正样本**：20/600（3.3%），极度不平衡
- **量表监督**：age/bmi/upper_ap/lower_ap/cholesterol 可用于辅助任务（训练时），推理不用
- **视频**：3600 个（600人×3 camera×2 step），每人 6 段
- **分折**：GroupKFold(patient_id)，同一人的视频必须在同一 fold

## API 输出规格

```json
{
  "risk_probability": 0.2345,
  "risk_level": "低/中/高",
  "risk_level_label": "低/中/高风险",
  "risk_level_description": "模板化中文建议",
  "top_factors": [
    {"feature": "...", "display_name": "中文名", "direction": "increases/decreases_risk", "importance": 0.31, "explanation": "中文解释"}
  ],
  "video_info": {"duration_seconds": "", "frames_read": "", "face_detection_rate": "", "fps": ""},
  "model_info": {"method": "Nadimi-Majtner 3-paper combined", "label": "gold_standard_hba1c_6.5", "cv_auroc": 0.77, "cv_auprc": 0.13},
  "disclaimer": "本系统为健康风险评估工具，不作为糖尿病诊断依据..."
}
```

## 已知限制（必须写入报告和 API disclaimer）

1. MCD-rPPG 只有 20 个金标准阳性，性能受样本量限制
2. 视频仅 ~4 秒（论文要求 30-240s），EVM 频域分辨率不足
3. 中位年龄 20 岁，阳性集中在 >60 岁，年龄是强混杂
4. 面部特征在当前数据下 AUC ~0.77，不如临床 baseline（age+bmi+bp）AUC ~0.85
5. 输出是风险概率，不是糖尿病诊断

## PM 审核检查清单

- [ ] RMT 实现存在且 MP 上界公式正确
- [ ] EVM 参数锁定（0.7-4.0Hz, alpha=30）
- [ ] 456 维特征合同匹配
- [ ] GroupKFold(patient_id) 未泄漏
- [ ] API response 含 disclaimer + top_factors
- [ ] 消融报告 E0-E4 完整
- [ ] 金标准 HbA1c≥6.5% 未降级
- [ ] RMT 单元测试通过
