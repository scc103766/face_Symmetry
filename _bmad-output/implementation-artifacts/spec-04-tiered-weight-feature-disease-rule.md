---
title: 'Task 04 tiered weight feature disease rule'
type: 'feature'
created: '2026-06-08'
status: 'done'
baseline_commit: 'NO_VCS'
context:
  - '{project-root}/docs/project-context.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Rule 62 uses a mostly equalized stability weight formula, so highly consistent cross-dataset core features such as `bsdiff_mouth_abs` and `raw_lip_midline_deviation` are not separated enough from noisy or high-false-positive weak features.

**Approach:** Build a new tiered weighting script that reuses Rule 62 feature thresholds and patient-level trigger mechanics, applies configurable Tier 1/2/3/4 multipliers to the base `raw_weight_score`, optionally evaluates `raw_all_mesh_region_point_spread_asym`, searches a global score threshold on combined patients, and writes the requested analysis/report outputs under `datasets/yolo_comparison_20260608`.

## Boundaries & Constraints

**Always:** Preserve Rule 62's patient-level trigger definition: a patient contributes a feature's weight only when the patient aggregated feature value is `>=` that feature's threshold. Keep all tier thresholds and multipliers parameterized. Evaluate train/val/test using the fixed `05_patient_splits.csv` seed `20260520`, and use combined all-patient data only for the global threshold search.

**Ask First:** Do not change the source 60-stage feature files, Rule 62 artifacts, or production `facial_asymmetry_service` rule wiring in this task.

**Never:** Do not present the outcome-label metrics as clinical diagnostic performance. Do not silently drop core Rule 62 fields from patient prediction output.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path | Existing 60-stage metrics, thresholds, candidate patient rows, Rule 62 weights/predictions, and fixed split file exist | Script writes JSON analysis, tiered patient predictions, comparison CSV, and Markdown report | Fail fast with missing file path if a required input is absent |
| Optional candidate eligible | At least 3 `raw_all_mesh_region_point_spread_asym` variants have `combined_directional_auc > 0.58` | Include the best `combined_directional_auc` variant and record inclusion rationale | If patient aggregation or threshold selection fails, record exclusion reason |
| Optional candidate ineligible | Fewer than 3 variants pass `combined_directional_auc > 0.58` | Keep the 21 Rule 62 features and record non-inclusion reason | Continue script execution |

</frozen-after-approval>

## Code Map

- `scripts/build_stable_weighted_feature_disease_rule.py` -- Rule 62 implementation to reuse for base weighting, patient triggers, metrics helpers, and report conventions.
- `scripts/find_combined_disease_feature_candidates.py` -- Source of 60-stage patient aggregation, threshold selection, CSV/JSON writers, role scopes, and binary metric helpers.
- `datasets/combined_disease_feature_candidates_20260529/metadata/*60*.csv` -- Candidate metrics, thresholds, and patient-level feature source files for Task 04.
- `datasets/combined_disease_feature_candidates_20260529/metadata/62_*.csv` -- Baseline Rule 62 weights and predictions for comparison.
- `datasets/facesym_v1_by_name_20260119/metadata/05_patient_splits.csv` -- Fixed old-dataset train/val/test split mapping.

## Tasks & Acceptance

**Execution:**
- [x] `scripts/build_tiered_weight_feature_disease_rule.py` -- Create the Task 04 builder script with configurable tier thresholds/multipliers, optional candidate inclusion, 0.0001 global threshold search, split metrics, JSON summary, CSV outputs, and Markdown report.
- [x] `datasets/yolo_comparison_20260608/*` -- Generate required Task 04 outputs by running the script in the project environment.
- [x] `tasks/done/task_04_report.md` -- Record implementation log, generated files, verification command, and key metric result.

**Acceptance Criteria:**
- Given the repository input artifacts, when `scripts/run_in_project_env.sh python scripts/build_tiered_weight_feature_disease_rule.py` runs, then all required Task 04 output files are regenerated successfully.
- Given Rule 62 baseline predictions, when split-level comparison is built, then `facesymai_rule62` and `tiered_weight_v1` rows cover `test`, `val`, `train`, and `combined`.
- Given the new feature weights, when the analysis summary and report are inspected, then `bsdiff_mouth_abs` and `raw_lip_midline_deviation` have visibly increased normalized weights compared with Rule 62.
- Given combined all-patient predictions, when metrics are computed, then `tiered_weight_v1` combined `balanced_accuracy` is at least Rule 62 combined `balanced_accuracy`, or the report explicitly explains why the tiered strategy failed.

## Spec Change Log

## Design Notes

The new script should import helpers from the existing Rule 62 and 60-stage scripts rather than duplicating CSV formatting and patient aggregation. To avoid collisions with historical metadata naming, Task 04 outputs go to `datasets/yolo_comparison_20260608` exactly as requested.

## Verification

**Commands:**
- `scripts/run_in_project_env.sh python scripts/build_tiered_weight_feature_disease_rule.py` -- expected: script exits 0 and writes all required files.
- `scripts/run_in_project_env.sh python -m py_compile scripts/build_tiered_weight_feature_disease_rule.py` -- expected: exits 0.

## Suggested Review Order

**Rule Builder**

- Entry point wires candidate selection, tiering, prediction, comparison, and outputs.
  [`build_tiered_weight_feature_disease_rule.py:53`](../../scripts/build_tiered_weight_feature_disease_rule.py#L53)

- CLI defaults expose every tier threshold and multiplier for follow-up tuning.
  [`build_tiered_weight_feature_disease_rule.py:127`](../../scripts/build_tiered_weight_feature_disease_rule.py#L127)

**Feature Selection And Weights**

- Optional high-Cohen candidate gate implements the three-variant combined-AUC rule.
  [`build_tiered_weight_feature_disease_rule.py:173`](../../scripts/build_tiered_weight_feature_disease_rule.py#L173)

- Tier assignment applies weak-feature downgrade before core-feature promotion.
  [`build_tiered_weight_feature_disease_rule.py:291`](../../scripts/build_tiered_weight_feature_disease_rule.py#L291)

- Tier-adjusted scores are normalized back to total feature weight one.
  [`build_tiered_weight_feature_disease_rule.py:266`](../../scripts/build_tiered_weight_feature_disease_rule.py#L266)

**Evaluation**

- Combined threshold scan follows the requested 0.0001 grid priority.
  [`build_tiered_weight_feature_disease_rule.py:343`](../../scripts/build_tiered_weight_feature_disease_rule.py#L343)

- Split resolution keeps old seed splits and assigns new patients to external test.
  [`build_tiered_weight_feature_disease_rule.py:410`](../../scripts/build_tiered_weight_feature_disease_rule.py#L410)

- Method comparison emits the required method/split metric table.
  [`build_tiered_weight_feature_disease_rule.py:448`](../../scripts/build_tiered_weight_feature_disease_rule.py#L448)

**Reports**

- JSON summary collects tiers, weight changes, candidate inclusion, and disagreements.
  [`build_tiered_weight_feature_disease_rule.py:586`](../../scripts/build_tiered_weight_feature_disease_rule.py#L586)

- Markdown report renders method, tier, metric delta, and inconsistency analysis.
  [`build_tiered_weight_feature_disease_rule.py:675`](../../scripts/build_tiered_weight_feature_disease_rule.py#L675)

- Development log records outputs, verification, and key metric result.
  [`task_04_report.md:1`](../../tasks/done/task_04_report.md#L1)
