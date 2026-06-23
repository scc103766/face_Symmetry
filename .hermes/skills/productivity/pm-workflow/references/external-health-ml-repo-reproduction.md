# External health-ML repository reproduction playbook

Use when the user asks to pull a GitHub/third-party project that is similar to the current health-risk product and “复现/验证一下”.

## Goal

Treat external repos as evidence to audit, not claims to trust. Reproduce the closest executable artifact, compare it with the README claims, and decide whether it is useful as product inspiration, model baseline, data source, or neither.

## Workflow

1. Clone under the project’s external/baseline area
   - Prefer an existing convention such as `baselines/<repo-name>/`.
   - Do not overwrite an existing clone; `git pull --ff-only` when already present.

2. Inventory first
   - Read `README.md` and locate manifests/notebooks/data/scripts.
   - Record dataset size, target variable, feature columns, and claimed metrics.
   - For notebooks, inspect code cells directly; do not assume the title/README matches what is trained.

3. Reproduce the exact published logic
   - Run or translate notebook cells with the same split/random seed when possible.
   - Preserve target/feature choices exactly for the first pass.
   - Report real metrics and whether they reproduce the claim.

4. Run an “intended target” sanity check when claims and code diverge
   - If README says “glucose prediction” but notebook predicts acetone, run a separate check using glucose as target.
   - Clearly label this as an audit/sanity check, not the repo’s original method.
   - Use appropriate regression/classification metrics for the intended target.

5. Small-data caution
   - If N is tiny, report split sensitivity and add leave-one-out or cross-validation if feasible.
   - Do not accept high in-sample R² as product evidence.
   - Compare train/test performance and note if test R² is negative or errors exceed the claim.

6. App/device components
   - Check Android/embedded build files, dependency age, and whether main source code exists.
   - Attempt build only within approved scope; if a command is blocked by policy, stop and report rather than bypass.
   - Separate “ML reproducibility” from “app/device build reproducibility”.

7. Final assessment format
   - Local path and repo URL.
   - What the project claims.
   - What actually ran.
   - Exact target/features used by the repo.
   - Metrics from exact reproduction.
   - Metrics from intended-target sanity check, if applicable.
   - Dataset limitations and leakage/target mismatch risks.
   - What is useful for the current project vs what must not be reused.

## Case pattern: ProjectHealthGo

A useful cautionary example:

- README claimed non-invasive glucose estimation and high regression coefficient.
- Notebook code actually used sensor variables to predict `Acetone`, because it sliced columns before `Blood Glu` and set `y = data.iloc[:,0:1]`.
- When audited for actual glucose prediction on 24 samples, test performance was poor and did not support the README’s ±10 mg/dL claim.

Lesson: always inspect notebook slicing and target construction before trusting health-ML repo claims.
