# Manifest

## analysis/
- rerun_pipeline.py — locked unified re-run
- export_nature_figures.py — Nature-style Figure 2-4 export
- export_sci_tables_figures.py — Word three-line tables + figures

## legacy_locked/
- make_table01_anemia_ioh_icu.py — anemia-project Table01 builder (configurable --project-root / --data-dir)
- make_table01_car_ioh_phenotype.py — CAR×IOH Table01 / Dcc builder (configurable paths)
- prepare_rerun_inputs.py — builds primary_cohort_dcc_enriched.csv, duration_cohort_4023.csv, car_available_4529.csv
- make_table02_car_ioh_phenotype.py / make_actB_car_x_ioh30.py / primary_model3_locked.py
- NOTE_MICE_specification.py
- RECONCILIATION.md

See data/derived/README.md and RUN_REPRODUCE.md step 3 for the dependency chain and editorial pack naming (A1–A5, B1, C1, D1–D3).

## config/
- config.example.json
- prepare_rerun_inputs.example.json

## environment
- requirements.txt (ranges)
- requirements-lock.txt (pinned)
- docs/ENVIRONMENT.md (seeds + package versions)

## examples/aggregate_outputs/
- aggregate-only CSV/JSON summaries (no patient identifiers)

## Not included (restricted)
- INSPIRE raw tables
- one-row-per-operation analytic cohorts
- bootstrap replicate files / per-operation exposure audits
