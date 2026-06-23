# Clinical dataset validation playbook

Use this reference when PM workflow tasks involve validating local clinical/tabular datasets before training, benchmarking, or using them as label sources.

## Core lesson

File presence is not dataset validity. Validate format, schema, label construction, loader compatibility, and benchmark execution before declaring a dataset ready.

## Validation sequence

1. Inventory files
   - List expected filenames, sizes, suffixes, and modification state.
   - Treat identical tiny files as suspicious when the expected dataset files should vary in size.

2. Validate file magic/format before loading
   - SAS XPORT/NHANES files should start with a header like:
     `HEADER RECORD*******LIBRARY HEADER RECORD!!!!!!!`
   - HTML placeholders or failed downloads may be saved with data suffixes. Detect prefixes like `<!DOCTYPE html>` / `<html>` and report them as invalid data, not loader bugs.

3. Accept harmless filename variance
   - NHANES downloads may use lowercase `.xpt` while older scripts expect uppercase `.XPT`.
   - Loaders and validators should resolve both `.XPT` and `.xpt` before reporting missing files.

4. Verify with the project loader
   - Run the existing dataset loader/benchmark after low-level format checks.
   - Capture merge counts table-by-table, final row count, feature count, label positive count/rate, and missing counts for key fields.

5. Benchmark in the right execution mode
   - If XGBoost triggers CUDA array-interface or GPU initialization errors in a mixed CUDA environment, rerun the benchmark CPU-only:
     `CUDA_VISIBLE_DEVICES='' conda run -n <env> python scripts/benchmark_datasets.py nhanes --model xgboost`
   - Record this as the execution recipe, not as a durable claim that GPU/XGBoost is broken.

6. Persist proof
   - Write a machine-readable validation JSON under `reports/`.
   - Write a human report under `tasks/done/` only after all checks actually ran.
   - Update `WORK_STATUS.md` with the current verified state and any follow-up caveats.

## NHANES-specific checklist

Expected 2017-2018 files for the current diabetes benchmark:

- `DEMO_J.xpt` / `DEMO_J.XPT`
- `BMX_J.xpt` / `BMX_J.XPT`
- `BPX_J.xpt` / `BPX_J.XPT`
- `GLU_J.xpt` / `GLU_J.XPT`
- `GHB_J.xpt` / `GHB_J.XPT`
- `DIQ_J.xpt` / `DIQ_J.XPT`
- `MCQ_J.xpt` / `MCQ_J.XPT`

Useful expected post-merge signal for NHANES 2017-2018 in this project:

- Table merge should end around 3036 rows because `GLU_J` is fasting subsample-sized.
- Distinguish two NHANES label modes explicitly:
  - **mixed-label benchmark** (legacy `benchmark_datasets.py nhanes`): `FBG >= 126 mg/dL OR HbA1c >= 6.5% OR DIQ010 == 1`. This mixes lab criteria with self-reported doctor diagnosis.
  - **lab-only benchmark** (preferred when user asks for “实验室金标准”): `FBG >= 126 mg/dL OR HbA1c >= 6.5%` only. Do not use `DIQ010` in the label or features.
- For lab-only training, treat `LBXGLU`, `LBXGH`, `DIQ010`, diabetes medication, and insulin-use fields as leakage/exclusion fields. Use non-leakage structured features such as age, sex, race/ethnicity, BMI, waist, blood pressure, and non-diabetes comorbidity fields.
- Save both model and preprocessor for any trainable benchmark intended for later inference; the older benchmark saved the model but not the NHANES-specific preprocessor.
- Always add a threshold scan for clinical/risk-label models, not just the default 0.5 threshold: report Youden’s J plus high-specificity thresholds (e.g. specificity >= 0.85/0.90/0.95) and high-precision thresholds when available. This supports the user’s strict-label preference and avoids overclaiming default-threshold predictions.
- A successful CPU-only XGBoost smoke benchmark produced AUC around 0.81 on the current setup; use this as a sanity check, not a hard invariant.

## Pandas row-access pitfall

When generating IDs from DataFrame rows, avoid attribute access for column names that may collide with `Series` methods/properties. Example: `r.view` resolves to the `Series.view` method, not necessarily the `view` column.

Use bracket access instead:

```python
row["view"]
row["patient_id"]
```

After fixing identifier generation, regenerate all downstream manifests/splits/caches that include the bad IDs and verify the bad substring is gone.
