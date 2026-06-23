# MCD-rPPG reproduction closure pattern

Use this when PM workflow resumes old MCD-rPPG reproduction tasks from `tasks/queue/`, especially broad tasks that originally requested full preprocessing/training.

## Trigger

- Queue contains old MCD-rPPG tasks such as setup, preprocessing, training, integration.
- Later sessions already produced staged artifacts: mapping, ROI caches, feature tables, correlation reports, or task reports.
- User asks to “complete the MCD-rPPG reproduction task” or clean up orphan queue tasks.

## Workflow

1. **Do not blindly execute stale full-run tasks.** First compare queue tasks against `tasks/done/`, reports, and actual artifacts.
2. **Verify artifacts, not just reports.** Check at least:
   - `mcd_rppg.csv`: row count, unique patient count, fold distribution, patient-level leakage.
   - ROI cache stats: sample count, success/failure counts, face success rate, bad cache count, `.npz` count.
   - Feature outputs: `video_features.csv`, `subject_features.csv`, quality JSON/report.
   - HbA1c/correlation reports: sample size, candidate feature count, top correlations, FDR caveats.
3. **If a safer staged route superseded the old task, close it explicitly.** Write a final report explaining which old requirements were completed directly, which were intentionally superseded, and why.
4. **Archive stale queue task files to `tasks/done/*_legacy_task.md` only after final report and validation exist.** This prevents PM recovery from repeatedly flagging historical orphan tasks.
5. **Update `WORK_STATUS.md` and `PROJECT_CONTEXT.md` with a concise recovery point.** The next PM session should see the actual current approval point, not stale queue noise.
6. **Run a validation script/check before reporting done.** Confirm required files exist, queue is empty, data checks pass, and any lightweight tests still pass.

## Caveats to preserve

- If full 3600-video preprocessing or SCNN-8ROI 5-fold training was not actually run, state that directly; do not imply a full paper reproduction.
- For MCD-rPPG diabetes/HbA1c analysis, separate engineering reproduction from medical claims.
- Small subject-level HbA1c correlations are hypothesis-generating only, especially when FDR q-values are not significant.
- Do not claim camera-based glucose measurement or diabetes diagnosis from these artifacts.

## Recommended final artifacts

- `mcd_rppg_reference/RESULTS.md`: unified reproduction/adaptation summary.
- `tasks/done/task_M2-MCD-RPPG-REPRODUCTION_final_report.md`: PM task completion report.
- `tasks/done/*_legacy_task.md`: archived original queue task files.
- Updated `WORK_STATUS.md` and `PROJECT_CONTEXT.md`.
