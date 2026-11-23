# Computational environment and random seeds

## Purpose

Record the software stack and seeds needed to reproduce the locked aggregate
outputs (including Supplementary Table S3 inputs) to the reported precision.

## Python packages

Prefer the pinned lock file at repository root:

```text
requirements-lock.txt
```

Minimum ranges (flexible installs) are listed in `requirements.txt`.

Versions recorded for the locked re-run environment used with the shipped
`examples/aggregate_outputs/` (Python 3.12.x):

| Package | Locked version |
|---|---|
| numpy | 2.4.6 |
| pandas | 2.3.3 |
| scipy | 1.17.1 |
| scikit-learn | 1.9.0 |
| statsmodels | 0.14.6 |
| matplotlib | 3.11.0 |
| python-docx | >=1.0 (export helpers only) |
| Pillow | >=10.0 (figure export only) |

Create the environment with:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
python -m pip install -U pip
pip install -r requirements-lock.txt
```

## Random seeds (already in config)

All of the following are set in `config/config.example.json` and read by
`analysis/rerun_pipeline.py`:

| Procedure | Setting | Value | Where applied |
|---|---|---|---|
| Primary / sensitivity bootstrap | `n_boot` | 1000 | `bootstrap(..., n_boot, seed, ...)` |
| Bootstrap RNG seed | `seed` | 20261108 | `numpy.random.default_rng(seed)` |
| Interval type | `primary_interval` | `percentile` | primary reporting |
| Multiple imputation | `m = 20` (code default in `mi_table`) | 20 completed datasets | Table S11 |
| MI imputer seed | `random_state = cfg["seed"] + i` | 20261108 … 20261127 | `sklearn.impute.IterativeImputer` |
| Prediction optimism bootstrap | `n_boot=500`, `seed=cfg["seed"]` | 500 / 20261108 | `prediction_table` |

Legacy historical note (superseded for the revised primary): early Model 3
reconciliation materials used bootstrap seed `20261014`. The **revised** locked
re-run and Table S3 use **`20261108`**.

## OS / hardware

The locked numeric outputs are intended to be OS-independent given the same
Python package versions, seeds, INSPIRE v1.4.2 inputs, and cohort files.
Floating-point differences across BLAS builds are expected to be negligible at
the reported rounding (two decimal places for risk differences in percentage
points).
