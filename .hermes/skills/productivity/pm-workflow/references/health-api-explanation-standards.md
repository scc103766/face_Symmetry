# Health Risk API — Factor Explanation Standards

When building a health/medical risk assessment API that outputs top contributing
factors with explanations, apply these rules.

## Risk Thresholds

Use **fixed clinical thresholds**, not percentile-based ones derived from training
data:

```
低风险: probability < 0.10
中风险: 0.10 ≤ probability < 0.85
高风险: probability ≥ 0.85
```

Rationale: percentile thresholds shift with every retrain and are not meaningful to
end users. Fixed thresholds communicate clinical confidence — a prediction below 10%
means the model is quite confident the subject is not in the risk group; above 85%
means strong signal. The wide middle band (0.10-0.85) appropriately captures model
uncertainty.

## Factor Explanations

Each top contributing factor MUST cite **both** disease pathophysiology **and** the
specific paper finding. The user explicitly rejected generic medical explanations
and required that every explanation name the paper, its sample size, and its key
statistical result. Pattern:

```
【论文1·2019·J Diabetes Res】红色通道标准差...
  论文1(30人,20DM+10对照)的核心发现：糖尿病组的r_std约为对照组的2-3倍(p<0.001)
  → 这是"不可见面部红斑"最直接的量化表达。

【论文2·2020·CMPB】Lab b*均值...
  论文2在174人(Acc 92.86%,Sens 100%)上将多颜色空间统计矩作为分类特征。
  b*升高→AGEs积累→皮肤黄褐色调。

【论文3·2020·Sci Rep】EVM放大后标准差...
  论文3的核心量化指标：EVM(α=30)将不可见变化放大至可测量水平(Sens 100%)。
```

### Wrong (technical description)

```
"RGB颜色统计复现论文1和论文2中的面部红度及颜色时间变化特征。"
"Lab颜色空间特征描述面部亮度及红绿、黄蓝色调差异。"
```

### Right (medical explanation)

```
"红色通道标准差——量化面部红度的时域波动。糖尿病患者因微循环自主调节受损，
 红度波动增大。该指标直接复现论文1和论文2的核心方法论。"

"Lab b*黄蓝轴均值刻画面部黄色调。b*值升高与皮肤AGEs积累相关——糖化血红蛋白
 与皮肤胶原交联形成的荧光性AGEs使皮肤呈现黄褐色调，是糖尿病慢性高血糖的
 外在皮肤标志。"
```

### Pattern

For each feature type, map it to a pathophysiological mechanism:

| Feature class | Pathophysiology link |
|--------------|---------------------|
| R channel stats | Microvascular endothelial dysfunction → vasodilation/constriction dysregulation → facial erythema pulsation amplitude |
| G channel stats | Hemoglobin absorption at 525nm → capillary hemoglobin dynamics → altered by AGEs-collagen cross-linking |
| B channel stats | Shallow penetration (460nm) → epidermal microcirculation → AGEs fluorescence |
| Lab b* (yellowness) | Skin AGEs accumulation → Maillard reaction → yellow-brown skin tone |
| Lab a* (redness) | Microvascular perfusion → facial erythema or pallor |
| Lab L* (brightness) | AGEs in dermal collagen → skin darkening |
| EVM band features | Pulsatile microvascular blood flow → endothelial dysfunction → vasomotion instability |
| EVM magnified features | Invisible color variations amplified → Nadimi 2019 core finding |
| RMT eigenvalues | Synchronized microvascular oscillations → autonomic neuropathy → loss of vascular regulation diversity |
| RMT spectral radius | Energy concentration in dominant modes → vascular rigidity |
| RMT participation ratio | Effective vascular regulation modes → reduced with autonomic neuropathy |
| RMT signal_eigenvalues | Non-random physiological signal components above MP noise boundary |

### Checklist

- [ ] Every feature explanation ends with a disease mechanism, not a data-science note
- [ ] Abbreviations expanded (AGEs, RMT, EVM) on first use in the risk description
- [ ] Risk descriptions cite specific papers/dates when relevant (e.g. "Nadimi 2019, p<0.001")
- [ ] Disclaimer always present in API response
