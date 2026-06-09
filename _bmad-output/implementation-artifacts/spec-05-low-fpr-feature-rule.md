---
title: 'Task 05 low FPR tail feature rule'
type: 'feature'
created: '2026-06-08'
status: 'in-progress'
baseline_commit: 'NO_VCS'
context:
  - '{project-root}/docs/project-context.md'
  - '{project-root}/docs/algorithm/evaluation-protocol.md'
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** Rule 62 improves balanced outcome-label metrics, but its false-positive count is too high for an extremely low false-positive operating point. The requested scenario prioritizes keeping combined nonpatient FP count at or below 1, then maximizing recall and precision.

**Approach:** Build a low-FPR rule construction script that scans all 60-stage feature variants for nonpatient tail thresholds, records strict S1 filter results, evaluates an AND rule from top tail candidates, evaluates a Tier 1 weighted core-feature rule with high tail thresholds, compares both against Rule 62 on train/val/test/combined splits, and writes the required CSV and Markdown artifacts.

## Boundaries & Constraints

**Always:** Use patient-level aggregation from the raw old/new MediaPipe feature files before tail scanning. Compute nonpatient P99/P995/P999 on combined nonpatient patients. Keep S1 thresholds and cross-data consistency tolerance parameterized. Search scheme B global threshold only among candidates with combined FP <= 1, and prioritize recall then precision. Split old patients through `05_patient_splits.csv`; treat new-data patients as external test for split comparison. Report concrete FP counts before rates.

**Ask First:** Do not change Rule 62 artifacts, 60-stage source metrics, or production service wiring.

**Never:** Do not present patient outcome weak-label metrics as clinical diagnostic performance. Do not silently claim strict S1 success if the current data has zero features meeting the configured `patient_above_P99_rate >= 0.15` and `tail_separation_ratio >= 1.5` filters.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Happy path | 60-stage metrics, raw old/new image feature CSVs, patient split CSV, and Rule 62 predictions exist | Script writes low-FPR tail scan, selected feature list, patient predictions, comparison CSV, and Markdown report under `datasets/yolo_comparison_20260608` | Fail fast with the missing required path |
| Strict S1 empty | No feature meets the configured strict tail filters | Tail scan records zero strict-pass rows; selected-feature output marks fallback top-tail rows separately; report states the strict threshold was not met | Continue evaluating A/B so the low-FPR operating point remains reviewable |
| Low-FPR feasible | A or B has a threshold/quantile configuration with combined FP <= 1 | Comparison marks the best low-FPR result and reports recall/precision/FP deltas versus Rule 62 | If no positive rule can meet FP <= 1, fall back to all-negative threshold and report recall 0 |

</frozen-after-approval>

## Code Map

- `scripts/find_combined_disease_feature_candidates.py` -- Source of 60-stage role scopes, patient aggregation, CSV writers, percentiles, and binary metric helpers.
- `scripts/build_stable_weighted_feature_disease_rule.py` -- Rule 62 helper conventions, markdown table formatting, and baseline metric fields.
- `scripts/build_tiered_weight_feature_disease_rule.py` -- Existing split resolution and comparison pattern for Rule 62 vs a derived rule.
- `datasets/combined_disease_feature_candidates_20260529/metadata/60_combined_disease_feature_all_metrics.csv` -- Full 60-stage feature variant surface to scan.
- `datasets/combined_disease_feature_candidates_20260529/metadata/62_stable_weighted_feature_disease_rule_patient_predictions.csv` -- Baseline predictions for comparison.

## Tasks & Acceptance

**Execution:**
- [ ] `scripts/build_low_fpr_feature_rule.py` -- Create a runnable builder for S1 tail scan, S2 quantile thresholds, S3 AND/weighted rules, S4 split comparison, and report generation.
- [ ] `datasets/yolo_comparison_20260608/low_fpr_*.csv` and `low_fpr_report.md` -- Generate all requested Task 05 artifacts by running the script.
- [ ] `tasks/done/task_05_report.md` -- Record development log, commands, generated files, strict-filter outcome, and key low-FPR metrics.

**Acceptance Criteria:**
- Given the repository input artifacts, when `scripts/run_in_project_env.sh python scripts/build_low_fpr_feature_rule.py` runs, then all requested output files are regenerated successfully.
- Given 60-stage metric rows, when the tail scan runs, then `low_fpr_tail_features.csv` covers all 60-stage feature variants, not only the 21 Rule 62 features.
- Given the current data has no strict S1 pass, when selected features are written, then fallback rule rows are clearly marked and the report states that the configured `tail_separation_ratio >= 1.5` criterion was not met.
- Given scheme A and B are evaluated, when comparison rows are built, then `facesymai_rule62`, `low_fpr_and_3`, and `low_fpr_weighted` each cover `test`, `val`, `train`, and `combined`.
- Given scheme B threshold search, when a threshold satisfies combined FP <= 1, then the selected weighted rule maximizes recall first and precision second under that constraint.

## Spec Change Log

## Design Notes

The task's strict S1 thresholds are kept as defaults, but the script separates `strict_filter_pass` from fallback selection. This keeps the data finding honest while still producing the requested A/B rule artifacts for review.

## Verification

**Commands:**
- `scripts/run_in_project_env.sh python scripts/build_low_fpr_feature_rule.py` -- expected: exits 0 and writes all required Task 05 outputs.
- `scripts/run_in_project_env.sh python -m py_compile scripts/build_low_fpr_feature_rule.py` -- expected: exits 0.
