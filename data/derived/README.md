# Derived analytic cohorts (not redistributed)

Credentialed users can run the **locked modelling re-run** once these
one-row-per-operation files are available locally:

- `primary_cohort_dcc_enriched.csv` (locked n = 3,936 before in-pipeline timing rule)
- `duration_cohort_4023.csv` (locked n = 4,023)
- `car_available_4529.csv` (locked n = 4,529; multiple imputation / Table S11)

Place them under `data/derived/` as named in `config/config.example.json`.

## Two supported routes

### A. Editorial verification files (DUA-restricted)

Copy D1–D3 from the editorial verification pack:

- `D1_primary_cohort_dcc_enriched.csv` → `primary_cohort_dcc_enriched.csv`
- `D2_duration_cohort_4023.csv` → `duration_cohort_4023.csv`
- `D3_car_available_4529.csv` → `car_available_4529.csv`

Eligible users obtain that pack under the PhysioNet / INSPIRE data-use agreement
via the editorial office. **The reproducible modelling workflow then begins at
`analysis/rerun_pipeline.py` (RUN_REPRODUCE step 4).**

### B. Rebuild from named credentialed extracts

1. Place extracts A1–A5, `inspire_os65_car_formal.csv`,
   `mc2_inspire_os65_icu_aki_fields.csv`, and
   `data/derived_verification/Dcc_MC9_annotated.csv` as documented in
   `RUN_REPRODUCE.md` step 3B0.
2. Run configurable Table 01 builders:
   - `legacy_locked/make_table01_anemia_ioh_icu.py`
   - `legacy_locked/make_table01_car_ioh_phenotype.py`
3. Run `legacy_locked/prepare_rerun_inputs.py` (config:
   `config/prepare_rerun_inputs.example.json`) to write the three files above.

**Cohort-construction workflow begins at step 3B; modelling still begins at
step 4.** Scripts that create A1–A5 from raw INSPIRE tables are not fully
public in this deposit.

## Dependency chain

```
INSPIRE v1.4.2 raw (vitals, operations, …)
        │
        ▼
Named extracts A1–A5 (+ formal / MC9 / ICU-AKI helpers)   [DUA verification files]
        │  make_table01_anemia_ioh_icu.py
        ▼
Table01_analytic_cohort.csv
        │  + A5 CAR enrich
        │  make_table01_car_ioh_phenotype.py
        ▼
Table01_analytic_cohort_Dcc.csv  (n=3936)
        │  prepare_rerun_inputs.py
        ▼
primary_cohort_dcc_enriched.csv
duration_cohort_4023.csv
car_available_4529.csv
        │  analysis/rerun_pipeline.py  ← modelling workflow begins
        ▼
Tables 2–4 / S3 / S11 aggregate outputs
```

Do **not** commit patient-level CSVs to GitHub.
