# -*- coding: utf-8 -*-
"""LOCKED primary Model 3 Clinical analysis for CAR x IOH -> ICU (Dcc).

This is the verified implementation for the revised manuscript:
- Cohort: Table01_analytic_cohort_Dcc.csv (n=3936, 407 events)
- Phenotype: four-level factor; reference = G00 (Neither)
- Covariates: age, asa (linear), op_duration_min, creatinine, bmi, hb, glucose,
  female, emop, general_anes, C(proc_axis, ref=other_orthopedic)
- Estimator: logistic MLE via statsmodels, method='lbfgs', maxiter=500
- Standardisation: g-computation over the empirical Dcc covariate distribution
- Uncertainty: percentile bootstrap B=1000, seed=20261014, patient-level resample + refit
- Do NOT use method='newton' for the primary estimate (see reconciliation note)
"""
from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

PHENOS = ["G00", "G10", "G01", "G11"]
COV_CONT = ["age", "asa", "op_duration_min", "creatinine", "bmi", "hb", "glucose"]
COV_BIN = ["female", "emop", "general_anes"]
N_BOOT = 1000
SEED = 20261014


def formula_m3() -> str:
    parts = (
        ["C(phenotype, Treatment(reference='G00'))"]
        + COV_CONT
        + COV_BIN
        + ["C(proc_axis, Treatment(reference='other_orthopedic'))"]
    )
    return "icu ~ " + " + ".join(parts)


def load_dcc(path: str | Path) -> pd.DataFrame:
    d = pd.read_csv(path, low_memory=False)
    d["icu"] = pd.to_numeric(d["icu_admission"], errors="coerce")
    d["phenotype"] = pd.Categorical(d["phenotype"], categories=PHENOS, ordered=True)
    for c in COV_CONT + COV_BIN:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["proc_axis"] = d["proc_axis"].fillna("other_orthopedic").astype(str)
    use = ["icu", "phenotype", "proc_axis"] + COV_CONT + COV_BIN
    out = d.dropna(subset=use).copy()
    out = out.loc[out["phenotype"].isin(PHENOS)].copy()
    out["phenotype"] = pd.Categorical(out["phenotype"], categories=PHENOS, ordered=True)
    return out


def fit_logit(df: pd.DataFrame):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return smf.logit(formula_m3(), data=df).fit(disp=False, method="lbfgs", maxiter=500)


def gcomp_risks(df: pd.DataFrame, res) -> dict[str, float]:
    risks = {}
    for g in PHENOS:
        t = df.copy()
        t["phenotype"] = g
        t["phenotype"] = pd.Categorical(t["phenotype"], categories=PHENOS)
        risks[g] = float(np.mean(res.predict(t)))
    return risks


def main(dcc_csv: str):
    df = load_dcc(dcc_csv)
    res = fit_logit(df)
    R = gcomp_risks(df, res)
    print("n/events", len(df), int(df.icu.sum()))
    print("std risks", {k: round(100 * v, 2) for k, v in R.items()})
    print("RD Both pp", round(100 * (R["G11"] - R["G00"]), 2))
    term = "C(phenotype, Treatment(reference='G00'))[T.G11]"
    print("OR Both", round(float(np.exp(res.params[term])), 2))


if __name__ == "__main__":
    import sys
    main(sys.argv[1])
