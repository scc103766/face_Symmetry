# CVD label taxonomy and leakage-validator workflow

Use this reference after CVD dataset inventory / NHANES-BRFSS audit tasks, before any baseline training or multimodal fusion in the Cardiovascular project or similar health-risk projects.

## Trigger

Use when:

- The project has multiple CVD-like labels from Kaggle, Mymensing, NHANES, BRFSS, Framingham/ASCVD, MCD-rPPG, model predictions, or proxy metabolic labels.
- The next proposed step is baseline training, fusion training, or Route B/Route C model integration.
- The user asks to avoid false claims, label mixing, or leakage in CVD/health-risk training.

## Core rule

Before training, convert label semantics into both:

1. Human-readable taxonomy: `docs/cvd_label_taxonomy.md`.
2. Machine-readable schema: `configs/cvd_label_schema.yaml`.
3. Enforceable validator: `scripts/validate_cvd_training_features.py`.

Do not rely on Markdown alone. The schema and validator turn PM/medical caveats into a training-time guardrail.

## Required label classes

Keep these label classes explicit and separate:

- `clinical_event`: adjudicated MACE / MI / stroke / CVD death / revascularization.
- `icd_or_ehr_diagnosis`: ICD/EHR/claims diagnosis labels.
- `self_report`: survey labels such as NHANES/BRFSS self-reported CVD.
- `formula_derived_risk`: Framingham, ASCVD, SCORE, QRISK, Mymensing risk score/level.
- `proxy_cardiometabolic_risk`: diabetes, HbA1c, hypertension, obesity, glucose-risk proxies.
- `model_prediction`: probabilities, pseudo-labels, previous-model outputs.
- `signal_quality_or_physiology`: HR, HRV, SQI, rPPG quality, physiology estimates.

Never collapse these into a generic `cvd_positive` unless the task is explicitly a carefully documented multi-task/domain adaptation setup.

## Output artifacts

For a CVD label-guard task, generate:

```text
docs/cvd_label_taxonomy.md
configs/cvd_label_schema.yaml
scripts/validate_cvd_training_features.py
reports/cvd_label_taxonomy_validation.json
tasks/done/task_CVD-LABEL-01_report.md
```

If the task was originally queued in `tasks/queue/`, move the completed task spec to:

```text
tasks/done/completed_task_specs/<task>.md
```

This keeps `tasks/queue/` reserved for active work and prevents false orphan-task recovery.

## Validator design

The validator should:

- Read CSV headers only, not full large tables:

```python
columns = pd.read_csv(csv_path, nrows=0).columns.tolist()
```

- Support CLI arguments:

```text
--csv <path>
--target <column>
--schema configs/cvd_label_schema.yaml
--output reports/<name>.json
--strict
```

- Check that the target exists in the CSV header.
- Check that the target appears in schema labels / `column_name` / aliases.
- Exclude the target itself from leakage detection:

```python
feature_columns = [c for c in columns if c != target]
```

- Match leakage patterns case-insensitively and with space/underscore/hyphen compatibility.
- Use `--strict` to return non-zero when suspected leakage or schema/target failures appear.

Suggested leakage patterns:

```text
risk_score
risk level
risk_level
probability
prediction
predicted
pseudo
framingham
ascvd
```

## Validation pattern

Run at least:

1. Schema load check with `yaml.safe_load`.
2. `python scripts/validate_cvd_training_features.py --help`.
3. Validator on NHANES reuse table with target `cvd_self_report_any`.
4. Validator on BRFSS reuse table with target `cvd_self_report_any`.
5. A strict negative probe if a known leakage column exists, e.g. Mymensing target `CVD Risk Level` should flag `CVD Risk Score` and exit non-zero.

A good final report records:

- Target label type and source dataset.
- Columns count.
- Suspected leakage columns.
- Warnings.
- `strict_pass`.
- Caveat that self-report labels are not MACE/ICD gold standards.

## Common pitfalls

1. **Only writing taxonomy in Markdown.** This is not enough; future training code cannot enforce it.
2. **Treating target as leakage.** If target is `CVD Risk Level`, that column is valid as target; only non-target features are checked for leakage.
3. **Loading full BRFSS just to inspect columns.** Use `nrows=0`.
4. **Letting Mymensing `CVD Risk Score` predict `CVD Risk Level`.** This is likely direct formula leakage unless the task is explicitly formula reproduction/calibration.
5. **Calling NHANES/BRFSS CVD labels gold standards.** They are self-report survey labels.
6. **Using MCD-rPPG diabetes/HbA1c labels as CVD labels.** They are cardiometabolic proxy/auxiliary labels only.
