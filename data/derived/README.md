# Derived analytic cohorts (not redistributed)

Credentialed users should rebuild one-row-per-operation analytic files
with the cohort-construction scripts under `legacy_locked/` and the
exposure reconstruction in `analysis/rerun_pipeline.py`.

Expected inputs for the locked re-run (names only):
- primary_cohort_dcc_enriched.csv  (n≈3935–3936 after timing rule)
- duration_cohort_4023.csv
- car_available_4529.csv  (optional; multiple imputation)

Do **not** commit patient-level CSVs to GitHub.
