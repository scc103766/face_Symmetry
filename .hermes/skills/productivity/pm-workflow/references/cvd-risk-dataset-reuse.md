# CVD risk dataset reuse and label-audit workflow

Use this reference when working on the Cardiovascular project or any health-risk project that asks to reuse diabetes/health datasets for cardiovascular risk assessment.

## Trigger

User asks for any of:

- Find cardiovascular-risk datasets already available locally.
- Reuse datasets downloaded for a diabetes-risk project.
- Compare overlap between diabetes and CVD risk datasets.
- Build NHANES/BRFSS loaders for CVD risk.
- Audit CVD labels before training.

## Core rule: separate label classes

Never collapse heterogeneous labels into one generic `cvd_positive` without an explicit taxonomy. Keep these classes separate:

1. `clinical_event` — adjudicated MACE, MI, stroke, CVD death, revascularization.
2. `icd_or_ehr_diagnosis` — ICD/EHR disease labels.
3. `self_report` — survey answers such as NHANES MCQ or BRFSS CVDINFR/CVDCRHD/CVDSTRK.
4. `formula_derived_risk` — Framingham/ASCVD/SCORE/QRISK risk categories.
5. `proxy_cardiometabolic_risk` — hypertension/diabetes/cholesterol/BMI/HbA1c composites.
6. `model_prediction` — probabilities or pseudo-labels produced by a model.

Do not mix Kaggle `cardio`, Mymensing `CVD Risk Level`, NHANES/BRFSS self-report CVD, Framingham-derived high risk, and MCD-rPPG proxy labels as if they were the same endpoint.

## Cross-project reuse pattern

1. Locate current-project CVD datasets and sibling health/diabetes project datasets.
2. Read source files in-place; do not copy or mutate sibling project raw data.
3. Generate a machine-readable profile artifact in the current project, e.g. `reports/cvd_reusable_dataset_profile.json`.
4. Generate human docs:
   - `docs/cvd_dataset_inventory.md`
   - `docs/cross_project_dataset_reuse.md`
5. For NHANES/BRFSS, create normalized audit tables in the current project only:
   - `data/processed/reusable_cvd/nhanes_2017_2018_cvd_reuse.csv`
   - `data/processed/reusable_cvd/brfss_2015_cvd_reuse.csv`
   - `reports/cvd_nhanes_brfss_label_audit.json`
6. Write a completion report under `tasks/done/` with actual shapes and label counts.

## Dataset-specific guidance

### NHANES

Useful tables seen in this project:

- `DEMO_J.xpt` demographics
- `BMX_J.xpt` body measures
- `BPX_J.xpt` measured blood pressure
- `GLU_J.xpt` fasting glucose; bottleneck table that can shrink the merge
- `GHB_J.xpt` HbA1c
- `DIQ_J.xpt` diabetes questionnaire
- `MCQ_J.xpt` medical conditions / self-reported CVD

Common derived labels:

- Diabetes lab/self-report: `LBXGLU >= 126 OR LBXGH >= 6.5 OR DIQ010 == 1`.
- CVD self-report: any available MCQ CVD fields equal yes. Treat as self-report, not MACE/ICD.

For exact Framingham/ASCVD-like scoring, check whether the cycle has total cholesterol, HDL, smoking, and BP medication tables. If missing, document the gap; do not silently compute an incomplete score.

### BRFSS

BRFSS ZIP members can have trailing spaces, e.g. `LLCP2015.XPT `. Match with `name.strip().lower().endswith('.xpt')`.

Useful columns:

- `DIABETE3` diabetes self-report
- `SEX`
- `_AGEG5YR` age group, not continuous age
- `_BMI5` BMI x 100
- `EXERANY2` exercise
- `SMOKE100` smoking history
- `BPHIGH4` told high blood pressure
- `TOLDHI2` told high cholesterol
- `CVDINFR4` heart attack
- `CVDCRHD4` angina / coronary heart disease
- `CVDSTRK3` stroke

Derived CVD self-report label:

`CVDINFR4 == 1 OR CVDCRHD4 == 1 OR CVDSTRK3 == 1`; set negative only when all available source fields are valid no; otherwise missing.

### MCD-rPPG / face-health derived data

MCD-rPPG can be valuable for face video/rPPG + cardiometabolic proxy-risk exploration, but it is not a CVD event dataset unless a true CVD label is present.

Do not use `diabetes_strict_label`, `hba1c_lab_diabetes`, or `hba1c_elevated_risk` as CVD labels. They can be auxiliary/proxy labels only.

## Leakage checks before modeling

Exclude or explicitly quarantine:

- `CVD Risk Score`
- already-derived `risk_level`
- model probabilities such as `xgb_*_probability`
- pseudo-label columns when training on the same signal that produced them
- any formula-derived label inputs when the task is to predict that formula output

## Verification checklist

Before reporting done:

- Script runs and writes outputs in the current project.
- Source sibling project files are read-only and not modified.
- Output CSV shapes are printed and checked.
- Label distributions are recorded, including missing counts.
- Docs state whether labels are self-report, clinical, formula-derived, proxy, or model predictions.
- Completion report includes exact file paths, commands, shapes, counts, and caveats.
