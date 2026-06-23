# Dataset inventory and detailed analysis workflow

Use this reference when the user asks to “详细分析每个数据集”, validate local datasets, or update project docs such as `docs/dataset_analysis.md`.

## Workflow

1. **Read the existing doc first**
   - Load the current dataset analysis / audit document.
   - Preserve useful project decisions, but correct stale status based on live files.

2. **Inventory physical files, not assumptions**
   - List local project data paths and external `/raid/...` dataset roots.
   - Record file counts, shapes, sizes, and representative members.
   - For archives, inspect members without extracting full data when possible.
   - For binary tabular formats, validate with the real reader (`pd.read_sas`, `pd.read_excel`, `np.load`) instead of trusting extensions.

3. **Profile each dataset at the right grain**
   - Tabular datasets: rows, columns, dtypes, label counts, missing counts, anomalous sentinel values, numeric ranges.
   - Multi-table clinical datasets: table-by-table shapes, join key, merge bottleneck, final merged rows, label construction.
   - Video/rPPG datasets: subject count, video count, per-subject file structure, ground-truth file structure, waveform lengths, available modalities.
   - Derived datasets: generation script, output schema, label rule, split rule, leakage checks, cache tensor shapes.

4. **Separate original labels, derived labels, and model predictions**
   - Never conflate lab labels, self-report labels, pseudo-labels, and model probabilities.
   - Always state whether a label is clinical/laboratory, self-reported, proxy, or strict pseudo-label.

5. **Write documentation in reusable sections**
   - Physical location and format.
   - File/table structure and schema.
   - Label definition and distribution.
   - Missing/invalid/sentinel values.
   - Current project loader and benchmark outputs.
   - Suitable tasks and unsuitable tasks.
   - Known pitfalls and next actions.

6. **Produce a machine-readable profile artifact**
   - Prefer a script such as `scripts/profile_datasets_for_analysis.py` that writes `reports/dataset_profile_summary.json`.
   - Use that JSON as the source for the human doc to avoid hand-wavy counts.

## Durable pitfalls from this project

- **NHANES suffix case**: local NHANES files may be `.xpt` not `.XPT`. Loaders and validators should accept both.
- **NHANES fake downloads**: files can exist but be CDC HTML error pages. Validate XPORT magic and `pd.read_sas` success, not existence.
- **NHANES merge bottleneck**: `GLU_J` fasting glucose subsample can shrink the merged table substantially; document this explicitly.
- **XGBoost CUDA path**: in this environment XGBoost may accidentally use CUDA array interface. For tabular benchmarks, use `CUDA_VISIBLE_DEVICES=''` or force CPU parameters when the task does not need GPU.
- **BRFSS ZIP member names**: ZIP members can have trailing spaces such as `LLCP2015.XPT `. Match with `name.strip().lower().endswith('.xpt')`.
- **BRFSS prevalence distortion**: benchmark sampling can keep all positives and sample negatives, changing the apparent positive rate. Document raw valid prevalence separately from training-sample prevalence.
- **Pandas Series attribute collision**: when generating IDs from `DataFrame.apply`, use `row['view']` instead of `row.view`; `row.view` can resolve to a Series method and corrupt IDs.
- **rPPG ground truth heterogeneity**: UBFC uses `ground_truth.txt` with multiple numeric lines; PURE stores frame sequences inside zips; Dataset_rPPG-10 has region AVI files plus ECG `.npy` and subject metadata in Excel. Do not assume all rPPG datasets have the same video/PPG layout.

## Recommended output checks

Before finalizing the doc, verify:

- Every dataset named by the user/project is represented.
- Each section includes format, schema/fields, labels, sample counts, limitations, and project use.
- Stale status labels (e.g. “NHANES damaged”) are updated from live validation.
- The report path and profiling JSON exist.
- The final doc mentions which datasets do **not** contain diabetes/HbA1c labels.
