# Reproduce exposure audit, Table 2, Supplementary Tables S3 and S11

## Software requirements

- Python **3.10+** (locked re-run used 3.12.10)
- Packages (see `code_archive_for_editorial_office/requirements.txt`):

```text
numpy>=1.24
pandas>=2.0
scipy>=1.10
statsmodels>=0.14
scikit-learn>=1.3
matplotlib>=3.7
python-docx>=1.0
Pillow>=10.0
```

Install:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
```

## Credentialed INSPIRE v1.4.2 data (not redistributed)

1. Complete PhysioNet credentialing / training / DUA.
2. Download **INSPIRE version 1.4.2**  
   https://physionet.org/content/inspire/1.4.2/  
   DOI: **10.13026/1eay-yc85**
3. Place raw files under `data/inspire/` (vitals, operations, labs, diagnosis, medications, ward_vitals, SHA256SUMS.txt, etc.).
4. Place derived one-row-per-operation analytic cohorts under `data/derived/` as named in `config/config.example.json`:
   - `primary_cohort_dcc_enriched.csv`
   - `duration_cohort_4023.csv`
   - `car_available_4529.csv` (needed for Supplementary Table S11 / MI)

Copy and edit the config:

```bash
copy config\config.example.json config\config.json
```

## One-command regeneration (locked pipeline)

From the code archive root:

```bash
python analysis\rerun_pipeline.py --config config\config.json
```

This single command rebuilds the reconstructed exposure, the exposure audit, the primary Table 2 estimates, Supplementary Table S3 inputs, and Supplementary Table S11 (MI), among other locked outputs, into `rerun_out/`.

## Output map requested by the Editor

| Manuscript item | Regenerated file(s) under `rerun_out/` |
|---|---|
| **Exposure audit** | `00_run_log.json` → key `exposure_audit`; also `01_exposure_by_rule.csv`, `01_phenotype_transition_published_to_final.csv`, `01_monitoring_by_phenotype.csv`, `01_phenotype_counts_final.csv` |
| **Table 2** | `02_primary_table2.csv` (+ `02_primary_boot_summary.csv`, `02_primary_coefficients.csv`) |
| **Supplementary Table S3** (exposure reconstruction / reclassification / monitoring-related contrasts) | `01_exposure_by_rule.csv`, `01_phenotype_transition_published_to_final.csv`, `01_monitoring_by_phenotype.csv`, `03_primary_contrast_by_exposure_rule.csv`, `04_monitoring_contrasts.csv`, `04_interaction_tests.csv` |
| **Supplementary Table S11** (primary-model reconciliation + covariate MI) | `12_tableS11_mi.csv` (+ primary coefficients / fit diagnostics in `00_fit_diagnostics.csv`, `02_primary_coefficients.csv`) |

## Locked analysis constants (do not change after seeing results)

- CAR cut: `0.0738095238`
- IOH cut: cumulative MAP <65 mmHg minutes ≥ `30`
- MAP physiologic range: `20–250` mmHg
- Epoch: `5` minutes
- Window: anaesthesia `[anstart_time, anend_time)`
- Bootstrap: `B=1000`, seed `20261108`, percentile intervals for the primary display

## Aggregate examples without patient-level data

See `aggregate_example_outputs/` in this folder (summaries only; no per-operation identifiers).
