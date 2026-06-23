# Dataset Verification Patterns from Health/Video Projects

Use this as a compact checklist when PM workflow resumes data tasks involving biomedical tabular files, video datasets, or downloaded archives.

## Do not trust existence alone

A dataset directory being non-empty is not enough. Verify actual format:

- XPT/SAS files: read with `pandas.read_sas(..., format='xport')`; valid XPORT headers begin with `HEADER RECORD*******...`, not HTML such as `<!DOCTYPE html>`.
- Case-sensitive extensions matter: accept both `.XPT` and `.xpt` where appropriate.
- ZIP members may contain trailing spaces; use the actual member name from `ZipFile.namelist()` or compare with `.strip().lower()`.
- CSV manifests may point to external paths that do not exist locally; verify referenced files separately.

## Biomedical dataset audit minimum

For each dataset, report:

1. physical path and raw file format
2. file count and sizes
3. tables/files and shapes
4. key join IDs (e.g., `SEQN`, `patient_id`, `subject_id`)
5. feature columns and label columns
6. label definition and counts
7. missing/invalid encodings (0-as-missing, 7/9 survey codes, NaN)
8. subject-level vs sample/video-level counts
9. leakage risks from repeated videos/visits per subject
10. what the dataset can and cannot support

## Split and pseudo-label safeguards

- Always split by subject/person, not by video/frame/sample, when multiple samples per subject exist.
- For strict pseudo-labels, preserve the lab rule and model threshold separately in outputs; do not equate strict negative with clinically confirmed negative.
- Write both machine-readable summaries (`*.json`) and human-readable reports (`tasks/done/...md`).

## XGBoost CUDA pitfall pattern

If XGBoost tabular training fails inside `array_interface.cu` / `QuantileDMatrix` while the data already loaded correctly, try a CPU-only run before blaming the data:

```bash
CUDA_VISIBLE_DEVICES='' conda run -n <env> python <script> ...
```

Capture the fix as a run command/workaround, not as a claim that GPU or XGBoost is broken generally.
