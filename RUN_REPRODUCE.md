> Round-5 note: cohort-assembly instructions are complete (three enriched files named explicitly); Table 01 builders and `prepare_rerun_inputs.py` use configurable paths; environment / seed documentation is in `docs/ENVIRONMENT.md` and `requirements-lock.txt`.

# Reproduce locked analyses (Windows and Linux/macOS)

Release: **v1.0.3** (extends v1.0.2)  
Git tag: v1.0.3
Commit: `c7b5f292f4a22d386624c6e36d131e72d3c75fef`  
Release URL: https://github.com/X-Allen0777/BMC-Geriatrics-CAR-IOH-ICU-code/releases/tag/v1.0.3  
Zenodo DOI: version-specific DOI for the v1.0.3 deposit (replace after minting)

## 0. Get the code

```bash
git clone https://github.com/X-Allen0777/BMC-Geriatrics-CAR-IOH-ICU-code.git
cd BMC-Geriatrics-CAR-IOH-ICU-code
git checkout v1.0.3
```

Or download the release zip from the release URL above.

## 1. Create and activate a virtual environment

Install from the **lock file** if the goal is to match Table S3 to the reported precision:

### Windows (cmd)

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements-lock.txt
```

### Linux / macOS

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -r requirements-lock.txt
```

`requirements.txt` lists minimum compatible ranges; `requirements-lock.txt` and `docs/ENVIRONMENT.md` record the versions used for the locked aggregate outputs shipped under `examples/aggregate_outputs/`.

## 2. Credentialed INSPIRE v1.4.2

1. Complete PhysioNet credentialing / training / DUA.
2. Download INSPIRE **1.4.2** (doi 10.13026/1eay-yc85).
3. Place raw files under `data/inspire/` (see `data/inspire/README.md`), including at least `vitals.csv.gz` and `operations.csv.gz`.

## 3. Assemble the three analysis cohorts required by the main pipeline

`analysis/rerun_pipeline.py` expects these **exact** one-row-per-operation files (paths in `config/config.example.json`):

| Pipeline input key | File name | Locked row count (before in-pipeline timing rule) | Role |
|---|---|---|---|
| `primary_cohort_csv` | `data/derived/primary_cohort_dcc_enriched.csv` | 3,936 | Primary complete-case / Table S3 pathway |
| `duration_cohort_csv` | `data/derived/duration_cohort_4023.csv` | 4,023 | Duration / dose–response models |
| `car_available_csv` | `data/derived/car_available_4529.csv` | 4,529 | Covariate MI / Table S11 (CAR not imputed) |

Two routes are supported.

### Where the reproducible modelling workflow begins

- **Option A (recommended for editorial verification of Tables 2–4 / S3 / S11):** place the three locked cohort files (editorial names D1–D3) under `data/derived/`, then continue at **step 4**. The modelling workflow begins at step 4.
- **Option B (rebuild cohorts from named credentialed extracts):** after the verification extracts listed below are available locally, run the Table 01 builders and `prepare_rerun_inputs.py`, then continue at **step 4**. The cohort-construction workflow begins at step 3B; the modelling workflow still begins at step 4.

Scripts that build the upstream named extracts (A1–A5) **from raw INSPIRE tables** are not fully deposited in this public package. Those extracts are supplied to credentialed editors under the PhysioNet DUA as the editorial verification pack (or rebuilt privately by eligible users who already hold equivalent extracts). Do not claim end-to-end raw→A1–A5 reproduction from this repository alone.

### Option A — locked cohorts supplied under the PhysioNet DUA (fastest)

1. Obtain the editorial verification pack (patient-level; DUA-restricted). Eligible users: credentialed PhysioNet / INSPIRE users designated by the editorial office.
2. Copy:
   - `D1_primary_cohort_dcc_enriched.csv` → `data/derived/primary_cohort_dcc_enriched.csv`
   - `D2_duration_cohort_4023.csv` → `data/derived/duration_cohort_4023.csv`
   - `D3_car_available_4529.csv` → `data/derived/car_available_4529.csv`
3. Continue at step 4.

### Option B — rebuild the three files from named credentialed extracts

#### B0. Place named extracts (verification files)

| Editorial / working name | Typical local path | Used by |
|---|---|---|
| A1 `topic_rescreen_os65_labs.csv` | `data/topic_rescreen_os65_labs.csv` | `make_table01_anemia_ioh_icu.py` |
| A2 `inspire_os65_demo_map.csv` | `data/inspire_os65_demo_map.csv` | anemia Table 01 |
| A3 `inspire_os65_gar_formal.csv` | `data/inspire_os65_gar_formal.csv` | anemia Table 01 |
| A4 `inspire_os65_landmark_times.csv` | `data/inspire_os65_landmark_times.csv` | anemia Table 01 |
| A5 `inspire_os65_car_enrich.csv` | `data/inspire_os65_car_enrich.csv` | CAR Table 01 |
| Formal CAR extract | `data/inspire_os65_car_formal.csv` | `prepare_rerun_inputs.py` (duration + CAR-available) |
| ICU/AKI helper fields | `data/mc2_inspire_os65_icu_aki_fields.csv` | `prepare_rerun_inputs.py` (primary enrichment) |
| Casemix annotation on Dcc | `data/derived_verification/Dcc_MC9_annotated.csv` | `prepare_rerun_inputs.py` (indication / Charlson columns) |
| INSPIRE `operations.csv.gz` | `data/inspire/operations.csv.gz` | `prepare_rerun_inputs.py` |

How eligible users obtain these files: complete PhysioNet credentialing and the INSPIRE data-use agreement; request the editorial verification pack from the corresponding author / editorial office for the named extracts that are not redistributed on GitHub; place raw INSPIRE files under `data/inspire/` for steps that read operations/vitals.

#### B1. Build Table 01 analytic cohorts (configurable paths; no author Desktop paths)

```bat
REM Windows (cmd) — run from repository root
python legacy_locked\make_table01_anemia_ioh_icu.py --project-root . --data-dir data
python legacy_locked\make_table01_car_ioh_phenotype.py --project-root . --car-enrich data\inspire_os65_car_enrich.csv
```

```bash
# Linux / macOS
python legacy_locked/make_table01_anemia_ioh_icu.py --project-root . --data-dir data
python legacy_locked/make_table01_car_ioh_phenotype.py --project-root . --car-enrich data/inspire_os65_car_enrich.csv
```

These write:

- `results/anemia_ioh_icu_os65/01_Table01_baseline/Table01_analytic_cohort.csv`
- `results/car_ioh_icu_os65/01_Table01_baseline/Table01_analytic_cohort_Dcc.csv` (complete-case Dcc; n = 3,936)

Optional `--mirror-dir` copies outputs to an extra folder; omit it to avoid any Desktop dependency.

#### B2. Transform Dcc + verification extracts → the three pipeline inputs

```bat
copy config\prepare_rerun_inputs.example.json config\prepare_rerun_inputs.json
notepad config\prepare_rerun_inputs.json
python legacy_locked\prepare_rerun_inputs.py --config config\prepare_rerun_inputs.json --project-root .
```

```bash
cp config/prepare_rerun_inputs.example.json config/prepare_rerun_inputs.json
nano config/prepare_rerun_inputs.json
python legacy_locked/prepare_rerun_inputs.py --config config/prepare_rerun_inputs.json --project-root .
```

Transformations implemented by `legacy_locked/prepare_rerun_inputs.py`:

1. **`primary_cohort_dcc_enriched.csv`**  
   Start from `Table01_analytic_cohort_Dcc.csv`. Left-join INSPIRE `operations.csv.gz` (anaesthesia / ICU timestamps), `mc2_inspire_os65_icu_aki_fields.csv` (creatinine / ICU-stay helpers), and `Dcc_MC9_annotated.csv` (indication / Charlson annotations). Derive albumin, LOS, kidney-event and ICU-stay indicators; lock High-CAR with cut `0.0738095238`.

2. **`duration_cohort_4023.csv`**  
   From `operations.csv.gz`, take first OS operation per subject with age ≥65; inner-join `inspire_os65_car_formal.csv`; keep Liu-style complete cases on the duration covariate set; seed `map65_min` from the primary cohort where available (MAP duration is rebuilt later from vitals inside `rerun_pipeline.py`).

3. **`car_available_4529.csv`**  
   From `inspire_os65_car_formal.csv`, keep operations with non-missing CAR (CRP/albumin); attach operation timestamps from `operations.csv.gz`. Used only for covariate multiple imputation (CAR itself is not imputed).

The script writes the three files under `data/derived/` (or `out_dir` in the config) and records counts in `prepare_rerun_inputs_meta.json`. Warnings are emitted if counts differ from the locked 3,936 / 4,023 / 4,529.

Then continue at step 4.

## 4. Configure and run the locked pipeline

### Windows (cmd)

```bat
copy config\config.example.json config\config.json
notepad config\config.json
python analysis\rerun_pipeline.py --config config\config.json
```

### Linux / macOS

```bash
cp config/config.example.json config/config.json
nano config/config.json
python analysis/rerun_pipeline.py --config config/config.json
```

Main outputs are written under `rerun_out/` (see output map below).

**Random seeds (also in `config/config.example.json` and `docs/ENVIRONMENT.md`):**

- Bootstrap (primary and Table S3 contrasts): `n_boot = 1000`, `seed = 20261108`
- Multiple imputation (Table S11): `m = 20` imputations; `IterativeImputer(..., random_state = seed + i)` for `i = 0..19`
- Optimism / prediction bootstrap: `n_boot = 500`, seed = `20261108`

## 5. ICU–MAP timing audit (Editor temporal-order check)

After step 4 (so that `rerun_out/01_exposure_per_operation.csv` exists), run:

### Windows (cmd)

```bat
python analysis\audit_icu_map_timing.py --config config\config.json --out rerun_out
```

### Linux / macOS

```bash
python analysis/audit_icu_map_timing.py --config config/config.json --out rerun_out
```

**Primary output file:** `rerun_out/timing_overlap_audit.json`

## Output map

| Item | File(s) under `rerun_out/` |
|---|---|
| Exposure reconstruction audit | `00_run_log.json` (`exposure_audit`) |
| ICU–MAP timing audit | `timing_overlap_audit.json` |
| Per-operation exposure | `01_exposure_per_operation.csv` |
| Table 2 | `02_primary_table2.csv`, `02_primary_boot_summary.csv` |
| Supplementary Table S3 inputs | `01_exposure_by_rule.csv`, `01_phenotype_transition_published_to_final.csv`, `01_monitoring_by_phenotype.csv`, `03_primary_contrast_by_exposure_rule.csv`, `04_monitoring_contrasts.csv`, `04_interaction_tests.csv` |
| Supplementary Table S11 | `12_tableS11_mi.csv` |

## Locked constants

- CAR cut: `0.0738095238`
- IOH: cumulative MAP <65 mmHg minutes ≥ 30
- MAP physiologic range: 20–250 mmHg
- Epoch: 5 minutes
- Window: anaesthesia `[anstart_time, anend_time)`
- Bootstrap: B = 1000, seed `20261108`
