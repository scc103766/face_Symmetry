# Cardiovascular risk dataset reuse across diabetes/face-health projects

Use this reference when the user asks to find cardiovascular risk datasets, reuse datasets downloaded for a diabetes-risk project, or compare local health-risk datasets across projects.

## Workflow

1. **Start from local truth before web research**
   - Read the current project docs first (`PROJECT_CONTEXT.md`, existing `docs/*dataset*`, reports, and downloaded resource manifests).
   - Search prior sessions for diabetes/health dataset audit terms such as `NHANES`, `BRFSS`, `Pima`, `MCD-rPPG`, `HbA1c`, `dataset_profile_summary`.
   - Read any existing cross-project dataset analysis documents and JSON profiles instead of relying on memory.

2. **Profile both projects with real file reads**
   - Current CVD project: inspect local open-source project datasets such as `cvd-risk-prediction-ai/ml-models/data/raw/*.csv`, `Cardiovascular-Disease-Prediction-and-Treatment-Recommendation-System/dataset/*.csv`, and structured branch outputs.
   - Diabetes project: inspect already-downloaded datasets and generated profiles, especially `docs/dataset_analysis.md` and `reports/dataset_profile_summary.json` if present.
   - Record absolute paths, shapes, label columns, value counts, and feature columns.

3. **Separate label classes explicitly**
   - Do not merge clinical events, self-report, formula-derived risk, proxy cardiometabolic risk, and model probabilities into one undifferentiated label.
   - Use categories such as:
     - true event/diagnosis: MACE, MI, stroke, CVD death, ICD/hospital record
     - self-report: BRFSS `CVDINFR*`, `CVDCRHD*`, `CVDSTRK*`; NHANES MCQ responses
     - formula-derived: Framingham/ASCVD/QRISK/SCORE thresholds
     - proxy risk: hypertension + diabetes + cholesterol + BMI + HbA1c combinations
     - model output: `p_clinical`, XGBoost probabilities, strict pseudo-labels

4. **Build a reuse matrix**
   - Recommended columns: dataset, local path, modality, rows/subjects/videos, CVD label availability, diabetes/metabolic label availability, face/rPPG availability, reusable fields, best use, limitations, priority.
   - Grade datasets by project fit:
     - A: directly reusable for CVD/cardiometabolic modeling (e.g. NHANES, BRFSS, Framingham-style tabular data, local CVD CSVs)
     - B: reusable for rPPG/physiology validation only (e.g. UBFC-rPPG, PURE, Dataset_rPPG-10)
     - C: reference/manifest/future acquisition only (e.g. SCAMPS/MMPD manifests without local raw data, application-only cohorts)

5. **Prioritize local reuse before downloads**
   - Prefer reusing already downloaded NHANES/BRFSS/MCD-rPPG/Pima files by absolute path or config reference.
   - Avoid duplicating large raw datasets across projects unless the user approves.
   - For cross-project reuse, propose symlinks/config references and keep the original project data immutable.

## Dataset-specific notes from this project family

### NHANES

High priority for CVD + diabetes/cardiometabolic modeling. Existing diabetes-project downloads may include `DEMO`, `BPX`, `BMX`, `GLU`, `GHB`, `DIQ`, `MCQ`. These support age/sex, BMI/waist, blood pressure, fasting glucose, HbA1c, diabetes questionnaire, and CVD self-report. For Framingham/ASCVD-like work, check whether smoking and lipid tables are present; if missing, propose adding SMQ, TCHOL, HDL/BPQ modules.

Caveat: NHANES is mostly cross-sectional; CVD fields are often self-reported unless linked mortality/follow-up files are available. Do not call NHANES self-report a MACE gold standard.

### BRFSS

High priority for questionnaire-based CVD/diabetes comorbidity modeling. Useful fields include diabetes status, age group, BMI, exercise, smoking, high blood pressure told, high cholesterol told, and CVD self-report fields for heart attack/CHD/stroke.

Caveat: labels and risk factors are self-reported; age is usually grouped; prevalence in balanced training samples must not be reported as population prevalence.

### MCD-rPPG

Core multimodal face-health data when available: face video, synchronized PPG, HbA1c, blood pressure, pulse, SpO2, cholesterol/BMI/age/sex. For CVD, use it as a face/rPPG + cardiometabolic proxy dataset, not as a true CVD-event dataset unless explicit MACE/ICD labels are found.

Good tasks:
- rPPG/HR/HRV pipeline validation
- cardiometabolic risk proxy exploration
- structured-risk + face/rPPG feature experiments with strict caveats

Bad claims:
- “face video predicts CVD diagnosis”
- “MCD-rPPG proves MACE/stroke/MI risk prediction”

### Pima

Useful only as a small diabetes/metabolic submodel or feature-bridging dataset. It is not a CVD dataset and should not be used as evidence for CVD-event prediction.

### UBFC-rPPG / PURE / Dataset_rPPG-10

Use for rPPG/HR/HRV validation and signal-quality benchmarking. They generally do not contain diabetes/CVD risk labels. Dataset_rPPG-10 may be useful for ECG-referenced HRV/ROI experiments but is too small for risk modeling.

## Recommended next-step task pattern

When the user asks for a serious CVD dataset search/reuse audit, propose a bounded PM task before training:

`CVD-DATA-01: reusable cardiovascular dataset inventory and cross-project profile`

Outputs:
- `docs/cvd_dataset_inventory.md`
- `docs/cross_project_dataset_reuse.md`
- `reports/cvd_reusable_dataset_profile.json`
- `scripts/profile_reusable_cvd_datasets.py`

Scope:
- Read/profile local CVD CSVs and diabetes-project reusable datasets.
- Produce a machine-readable profile plus a human reuse matrix.
- Do not train models, download large datasets, or modify the source diabetes project without approval.

Verification:
- Every named dataset has a real path or is marked unavailable/application-only.
- Every count/shape/label distribution comes from file reads or cited docs.
- The final report distinguishes CVD event labels, self-report labels, formula labels, proxy labels, and model probabilities.
