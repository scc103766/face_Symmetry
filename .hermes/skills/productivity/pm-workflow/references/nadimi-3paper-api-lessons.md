# Nadimi-Majtner Three-Paper Combined Face-Video Diabetes Risk API

Lessons from building and deploying the `api_nadimi` service on MCD-rPPG.

## Paper Anchoring (Essential)

Every API output explanation MUST cite which paper, what finding, at what significance level. Generic medical explanations are rejected by the user. The three papers:

| Paper | Journal | Year | N | Key Metric |
|-------|---------|------|---|------------|
| 1 | J Diabetes Res | 2019 | 30 (20DM+10C) | p<0.001 for temporal redness fluctuation |
| 2 | CMPB | 2020 | 174 (114DM+60C) | Acc 92.86%, Sens 100%, Spec 80% |
| 3 | Sci Rep | 2020 | — | EVM α=30, RMT+MP, Sens 100% |

## Risk Threshold Design

User requires: `risk_probability >= 0.85` to trigger "高风险". Do NOT use percentile-based thresholds. Fixed clinical thresholds:

```python
LOW = 0.10   # < 0.10 → 低风险
HIGH = 0.85  # >= 0.85 → 高风险
# between → 中风险
```

With only 20 gold-positive subjects on MCD-rPPG, CV probabilities max out at ~0.77 — the 0.85 threshold will rarely/never trigger. This is correct behavior for a screening tool on limited data.

## In-Sample vs CV Evaluation Pitfall

When the final model is fit on all 600 subjects (for deployment), evaluating on those same 600 subjects gives inflated metrics (AUROC 0.99) due to data leakage. The honest performance is always the **cross-validated** estimate (AUROC 0.77 on GroupKFold patient-level). Always report both and clearly label which is CV.

## Gold Label vs XGBoost-Derived Label

The old XGBoost pseudo-label is circular: Glucose = 28.7×HbA1c-46.7, so XGBoost probability ≈ f(HbA1c). This cannot validate whether face video carries independent signal. Use pure lab threshold: `gold_label = HbA1c >= 6.5`.

## Feature Pipeline Summary

```
Video → 120 uniform frames → FaceSym API (478 landmarks)
  → 6 ROI (FACE/FOREHEAD/LEFT_CHEEK/RIGHT_CHEEK/NOSE/CHIN)
  → 456 features:
    A: 144 static (RGB/HSV/Lab per ROI)
    B: 288 EVM (bandpass 0.7-4Hz, α=30, per ROI×channel)
    C: 24 RMT (eigenvalue spectrum per channel, 6×6 covariance matrix)
  → SelectKBest(80) → LR+RF ensemble
```

## Multi-Task Auxiliary Heads

Train Ridge regression heads for age/BMI/BP/cholesterol from the same face features. These force the encoder to learn health-relevant representations. Use only during training; API inference is video-only.

## Engineer Dispatch Pattern

User prefers **manual dispatch**: PM writes task specs to `tasks/queue/`, user manually sends to Codex. Do NOT auto-delegate. After Engineer reports to `tasks/done/`, PM reviews and writes audit.
