# -*- coding: utf-8 -*-
"""
Unified re-run pipeline for the BMC Geriatrics revision
(CAR x cumulative IOH -> early postoperative ICU admission, INSPIRE).

ONE exposure definition, ONE primary cohort, ONE convergent estimator.
Every table that depends on hypotension exposure or on the phenotype model
is regenerated here, through the same helpers, so that primary and
sensitivity estimates are numerically comparable.

Dependencies: numpy, pandas, scipy (required); statsmodels (only for the
median-regression LOS tables); scikit-learn (only for the multiple-imputation
table); matplotlib (only for figures).

Usage
-----
    python rerun_pipeline.py --config config.json

See CONFIG_TEMPLATE below for every input path and column name.
Outputs are written to config["out_dir"]; file names match the checklist.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import math
import sys
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from scipy.special import expit

# ---------------------------------------------------------------------------
# 0. Configuration
# ---------------------------------------------------------------------------
CONFIG_TEMPLATE = {
    "out_dir": "rerun_out",
    # analytic files you already have (one row per operation)
    "primary_cohort_csv": "Table01_analytic_cohort_Dcc.csv",      # the 3,936
    "duration_cohort_csv": "duration_cohort_4023.csv",            # the 4,023 (albumin rule)
    "car_available_csv": "car_available_4529.csv",                # for MICE only; optional
    # INSPIRE raw files (the release you used)
    "inspire_vitals": "INSPIRE/vitals.csv.gz",
    "inspire_raw_dir": "INSPIRE",
    # SHA256SUMS.txt downloaded from each PhysioNet version page (optional)
    "physionet_sha256sums": {"1.3": "SHA256SUMS_v1.3.txt", "1.4.2": "SHA256SUMS_v1.4.2.txt"},
    # locked analysis constants (do NOT change after seeing results)
    "car_cut": 0.0738095238,
    "ioh_cut_min": 30,
    "map_low": 65,
    "phys_range": [20, 250],
    "epoch_min": 5,
    "window": "anaesthesia",          # anaesthesia = [anstart_time, anend_time)
    "n_boot": 1000,
    "seed": 20261108,
    "primary_interval": "percentile",  # fixed before seeing results; BCa reported as sensitivity
    "jackknife_for_bca": "leave_one_out",
}

PHENOS = ["G00", "G10", "G01", "G11"]          # Neither, High CAR only, IOH only, Both
PHENO_LABEL = {"G00": "Neither", "G10": "High CAR only", "G01": "IOH >=30 min only", "G11": "Both"}

P3_CONT = ["age", "asa", "op_duration_min", "creatinine", "bmi", "hb", "glucose"]
P3_BIN = ["female", "emop", "general_anes"]
P3_CAT = {"proc_axis": "other_orthopedic"}       # name -> reference level


class FitFailure(Exception):
    """Raised when a fit cannot be accepted (reason in args[0])."""


# ---------------------------------------------------------------------------
# 1. Logistic regression with verified convergence (Newton-Raphson / IRLS)
# ---------------------------------------------------------------------------
@dataclass
class LogitResult:
    beta: np.ndarray
    cov: np.ndarray
    llf: float
    n_iter: int
    max_abs_score: float
    converged: bool
    names: list
    firth: bool = False

    def or_ci(self, name, level=0.95):
        j = self.names.index(name)
        z = stats.norm.ppf(0.5 + level / 2)
        b, se = self.beta[j], math.sqrt(self.cov[j, j])
        return math.exp(b), math.exp(b - z * se), math.exp(b + z * se), 2 * stats.norm.sf(abs(b / se))


def _loglik(X, y, beta):
    eta = X @ beta
    return float(np.sum(y * eta - np.logaddexp(0.0, eta)))


def fit_logit(X, y, names, firth=False, max_iter=100, tol=1e-10, score_tol=1e-6,
              sep_eta=30.0):
    """Newton-Raphson with step-halving. Accept only a converged fit.

    Convergence = relative change in log-likelihood < tol AND max |score| < score_tol
    (score evaluated on the design actually used; continuous covariates are
    standardised upstream so the tolerance is meaningful).
    Quasi-separation is flagged when any |linear predictor| exceeds sep_eta.
    """
    n, p = X.shape
    if np.linalg.matrix_rank(X) < p:
        raise FitFailure("singular_design")
    if y.min() == y.max():
        raise FitFailure("no_outcome_variation")
    beta = np.zeros(p)
    beta[0] = math.log(y.mean() / (1 - y.mean()))

    def objective(b):
        ll = _loglik(X, y, b)
        if firth:
            mu = expit(X @ b)
            w = mu * (1 - mu)
            sign, logdet = np.linalg.slogdet((X * w[:, None]).T @ X)
            ll += 0.5 * logdet
        return ll

    obj = objective(beta)
    converged = False
    for it in range(1, max_iter + 1):
        mu = expit(X @ beta)
        w = mu * (1 - mu)
        info = (X * w[:, None]).T @ X
        try:
            info_inv = np.linalg.inv(info)
        except np.linalg.LinAlgError:
            raise FitFailure("singular_information")
        if firth:
            # hat diagonal of W^1/2 X (X'WX)^-1 X' W^1/2
            h = np.einsum("ij,jk,ik->i", X * np.sqrt(w)[:, None], info_inv, X * np.sqrt(w)[:, None])
            score = X.T @ (y - mu + h * (0.5 - mu))
        else:
            score = X.T @ (y - mu)
        step = info_inv @ score
        t = 1.0
        while True:
            cand = beta + t * step
            cobj = objective(cand)
            if np.isfinite(cobj) and cobj >= obj - 1e-12:
                break
            t /= 2
            if t < 1e-8:
                raise FitFailure("line_search_failed")
        rel = abs(cobj - obj) / (abs(obj) + 1e-12)
        beta, obj = cand, cobj
        mu = expit(X @ beta)
        if firth:
            w = mu * (1 - mu)
            info = (X * w[:, None]).T @ X
            info_inv = np.linalg.inv(info)
            h = np.einsum("ij,jk,ik->i", X * np.sqrt(w)[:, None], info_inv, X * np.sqrt(w)[:, None])
            score = X.T @ (y - mu + h * (0.5 - mu))
        else:
            score = X.T @ (y - mu)
        if rel < tol and np.max(np.abs(score)) < score_tol:
            converged = True
            break
    if not converged:
        raise FitFailure("not_converged")
    eta = X @ beta
    if np.max(np.abs(eta)) > sep_eta:
        raise FitFailure("quasi_separation")
    mu = expit(eta)
    w = mu * (1 - mu)
    cov = np.linalg.inv((X * w[:, None]).T @ X)
    return LogitResult(beta, cov, _loglik(X, y, beta), it, float(np.max(np.abs(score))),
                       True, list(names), firth)


# ---------------------------------------------------------------------------
# 2. Design matrices with fixed coding
# ---------------------------------------------------------------------------
@dataclass
class Spec:
    outcome: str = "icu"
    exposure: str = "pheno4"            # pheno4 | both_vs_neither | dur_cat | dur_trend | dur_linear | dur_rcs | none | highcar
    cont: list = field(default_factory=lambda: list(P3_CONT))
    binary: list = field(default_factory=lambda: list(P3_BIN))
    cat: dict = field(default_factory=lambda: dict(P3_CAT))
    extra: list = field(default_factory=list)      # extra numeric columns (e.g. art_any, charlson_index)
    extra_cat: dict = field(default_factory=dict)  # extra categorical columns name -> reference
    interact_pheno_with: str | None = None         # e.g. "art_any"
    knots: tuple = (0, 5, 45)
    firth: bool = False
    label: str = ""


def rcs_basis(x, knots):
    """Harrell restricted cubic spline: returns k-2 non-linear columns."""
    k = np.asarray(knots, float)
    kk = len(k)
    norm = (k[-1] - k[0]) ** 2
    out = []
    for j in range(kk - 2):
        term = (np.clip(x - k[j], 0, None) ** 3
                - np.clip(x - k[-2], 0, None) ** 3 * (k[-1] - k[j]) / (k[-1] - k[-2])
                + np.clip(x - k[-1], 0, None) ** 3 * (k[-2] - k[j]) / (k[-1] - k[-2]))
        out.append(term / norm)
    return np.column_stack(out) if out else np.empty((len(x), 0))


class Design:
    """Freezes coding (levels, standardisation constants) on the analysis sample,
    so bootstrap refits and counterfactual predictions use identical columns."""

    def __init__(self, df: pd.DataFrame, spec: Spec):
        self.spec = spec
        self.mu, self.sd = {}, {}
        for c in spec.cont:
            v = df[c].astype(float)
            self.mu[c], self.sd[c] = float(v.mean()), float(v.std(ddof=0)) or 1.0
        self.levels = {}
        for c, ref in {**spec.cat, **spec.extra_cat}.items():
            lv = sorted(df[c].astype(str).unique())
            if ref not in lv:
                ref = lv[0]
            self.levels[c] = [ref] + [l for l in lv if l != ref]
        # drop binary / extra columns that are constant in the analysis sample
        self.binary = [c for c in spec.binary if df[c].nunique() > 1]
        self.extra = [c for c in spec.extra if df[c].nunique() > 1]
        self.dropped_constant = [c for c in spec.binary + spec.extra if c not in self.binary + self.extra]

    def exposure_cols(self, df, override=None):
        e = self.spec.exposure
        if e == "none":
            return [], np.empty((len(df), 0))
        if e in ("pheno4",):
            ph = df["phenotype"].astype(str).values if override is None else np.repeat(override, len(df))
            names = ["ph_G10", "ph_G01", "ph_G11"]
            cols = np.column_stack([(ph == g).astype(float) for g in ("G10", "G01", "G11")])
            if self.spec.interact_pheno_with:
                m = df[self.spec.interact_pheno_with].astype(float).values
                names += [f"ph_G10:{self.spec.interact_pheno_with}", f"ph_G01:{self.spec.interact_pheno_with}",
                          f"ph_G11:{self.spec.interact_pheno_with}"]
                cols = np.column_stack([cols, cols * m[:, None]])
            return names, cols
        if e == "both_vs_neither":
            ph = df["phenotype"].astype(str).values if override is None else np.repeat(override, len(df))
            return ["ph_G11"], (ph == "G11").astype(float)[:, None]
        if e == "highcar":
            return ["high_car"], df["high_car"].astype(float).values[:, None]
        d = df["map65_final"].astype(float).values if override is None else np.repeat(float(override), len(df))
        if e == "dur_cat":
            cat = np.select([d == 0, d < 10, d < 30], [0, 1, 2], 3)
            return ["dur_gt0_lt10", "dur_10_lt30", "dur_ge30"], np.column_stack([(cat == k).astype(float) for k in (1, 2, 3)])
        if e == "dur_trend":
            cat = np.select([d == 0, d < 10, d < 30], [0, 1, 2], 3)
            return ["dur_score"], cat.astype(float)[:, None]
        if e == "dur_linear":
            return ["dur_per10"], (d / 10.0)[:, None]
        if e == "dur_rcs":
            nl = rcs_basis(d, self.spec.knots)
            return ["dur_lin"] + [f"dur_rcs{j+1}" for j in range(nl.shape[1])], np.column_stack([d, nl])
        raise ValueError(e)

    def matrix(self, df, override=None):
        names = ["Intercept"]
        blocks = [np.ones((len(df), 1))]
        en, ec = self.exposure_cols(df, override)
        names += en
        blocks.append(ec)
        for c in self.spec.cont:
            names.append(c)
            blocks.append(((df[c].astype(float).values - self.mu[c]) / self.sd[c])[:, None])
        for c in self.binary + self.extra:
            names.append(c)
            blocks.append(df[c].astype(float).values[:, None])
        for c, lv in self.levels.items():
            v = df[c].astype(str).values
            for l in lv[1:]:
                names.append(f"{c}[{l}]")
                blocks.append((v == l).astype(float)[:, None])
        return np.column_stack(blocks), names


def fit_spec(df, spec, design=None):
    design = design or Design(df, spec)
    X, names = design.matrix(df)
    y = df[spec.outcome].astype(float).values
    return fit_logit(X, y, names, firth=spec.firth), design


def gcomp(df, res, design, levels=PHENOS):
    out = {}
    for g in levels:
        X, _ = design.matrix(df, override=g)
        out[g] = float(np.mean(expit(X @ res.beta)))
    return out


# ---------------------------------------------------------------------------
# 3. Bootstrap engine with full status logging
# ---------------------------------------------------------------------------
def bootstrap(df, stat_fn, n_boot, seed, label, out_dir, jackknife=None):
    """stat_fn(df) -> dict of floats, may raise FitFailure(reason).
    Saves every replicate with its status; never silently drops a replicate."""
    point = stat_fn(df)
    keys = list(point)
    rng = np.random.default_rng(seed)
    n = len(df)
    rows = []
    for b in range(n_boot):
        idx = rng.integers(0, n, n)
        rec = {"replicate": b + 1, "status": "ok", "reason": ""}
        try:
            s = stat_fn(df.iloc[idx].reset_index(drop=True))
            if not all(np.isfinite(list(s.values()))):
                raise FitFailure("nonfinite_estimate")
            rec.update(s)
        except FitFailure as e:
            rec["status"], rec["reason"] = "failed", e.args[0]
        rows.append(rec)
    reps = pd.DataFrame(rows)
    reps.to_csv(out_dir / f"{label}_boot_replicates.csv", index=False)
    status = reps.groupby(["status", "reason"]).size().rename("n").reset_index()
    status.to_csv(out_dir / f"{label}_boot_status.csv", index=False)
    ok = reps[reps.status == "ok"]
    jk = None
    if jackknife is not None:
        jk = jackknife(df, stat_fn, keys)
    summ = []
    for k in keys:
        v = ok[k].astype(float).values
        r = {"estimand": k, "point": point[k], "n_boot_planned": n_boot, "n_boot_ok": len(v),
             "n_boot_failed": n_boot - len(v),
             "boot_mean": v.mean() if len(v) else np.nan,
             "boot_median": np.median(v) if len(v) else np.nan,
             "pct_lo": np.percentile(v, 2.5) if len(v) else np.nan,
             "pct_hi": np.percentile(v, 97.5) if len(v) else np.nan,
             "frac_below_point": float(np.mean(v < point[k])) if len(v) else np.nan,
             "n_abs_lt_1e-5": int(np.sum(np.abs(v) < 1e-5)) if len(v) else 0}
        # two-sided bootstrap p for H0: estimand = 0 (only meaningful for differences)
        if len(v):
            p = 2 * min(np.mean(v <= 0), np.mean(v >= 0))
            r["p_boot"] = max(p, 1.0 / (len(v) + 1))
            r["p_boot_display"] = f"<{1/(len(v)+1):.3f}" if p == 0 else f"{min(p,1):.3f}"
        if jk is not None and len(v):
            r.update(bca(v, point[k], jk[k]))
        summ.append(r)
    summ = pd.DataFrame(summ)
    summ.to_csv(out_dir / f"{label}_boot_summary.csv", index=False)
    return point, summ, reps


def jackknife_loo(df, stat_fn, keys):
    vals = {k: [] for k in keys}
    for i in range(len(df)):
        s = stat_fn(df.drop(index=df.index[i]).reset_index(drop=True))
        for k in keys:
            vals[k].append(s[k])
    return {k: np.asarray(v) for k, v in vals.items()}


def bca(boot, point, jack, level=0.95):
    z0 = stats.norm.ppf(np.clip(np.mean(boot < point), 1e-6, 1 - 1e-6))
    jm = jack.mean()
    num = np.sum((jm - jack) ** 3)
    den = 6 * (np.sum((jm - jack) ** 2) ** 1.5)
    a = num / den if den > 0 else 0.0
    zl, zh = stats.norm.ppf([(1 - level) / 2, (1 + level) / 2])
    a1 = stats.norm.cdf(z0 + (z0 + zl) / (1 - a * (z0 + zl)))
    a2 = stats.norm.cdf(z0 + (z0 + zh) / (1 - a * (z0 + zh)))
    return {"bca_lo": np.percentile(boot, 100 * a1), "bca_hi": np.percentile(boot, 100 * a2),
            "bca_z0": z0, "bca_a": a}


# ---------------------------------------------------------------------------
# 4. Exposure reconstruction from INSPIRE vitals
# ---------------------------------------------------------------------------
def load_vitals(path, op_ids, chunksize=5_000_000):
    keep = set(int(x) for x in op_ids)
    parts = []
    for ch in pd.read_csv(path, usecols=["op_id", "chart_time", "item_name", "value"],
                          chunksize=chunksize):
        ch = ch[ch.item_name.isin(["art_mbp", "nibp_mbp"]) & ch.op_id.isin(keep)]
        if len(ch):
            parts.append(ch)
    v = pd.concat(parts, ignore_index=True)
    v["value"] = pd.to_numeric(v["value"], errors="coerce")
    return v


def build_exposure(vitals, ops, cfg):
    """Returns (per-operation exposure table, audit dict).

    Rules (all within [anstart_time, anend_time) unless stated):
      A_legacy  : OpAnyArt source rule, no range filter, no window  (reproduces published map65_min)
      FINAL     : dedup -> drop conflicting item-time groups -> per-source 20-250 filter ->
                  EpochWise (valid arterial, else valid NIBP at the same chart_time)
      C         : FINAL, then a low epoch flanked by two adjacent (+-5 min) epochs >=65 is not counted
      D         : FINAL, but an arterial low with a concurrent valid NIBP >=65 takes the NIBP value
      E         : D then C
    """
    lo, hi = cfg["phys_range"]
    low = cfg["map_low"]
    step = cfg["epoch_min"]
    audit = {}
    v = vitals.copy()
    n0 = len(v)
    v = v.drop_duplicates(["op_id", "chart_time", "item_name", "value"])
    audit["exact_duplicate_rows_removed"] = n0 - len(v)
    g = v.groupby(["op_id", "chart_time", "item_name"])["value"].transform("nunique")
    audit["conflicting_item_time_groups_removed"] = int(
        v[g > 1].groupby(["op_id", "chart_time", "item_name"]).ngroups)
    v = v[g == 1]
    wide = v.pivot_table(index=["op_id", "chart_time"], columns="item_name", values="value",
                         aggfunc="first").reset_index()
    for c in ("art_mbp", "nibp_mbp"):
        if c not in wide:
            wide[c] = np.nan
    w = ops[["op_id", "anstart_time", "anend_time", "opstart_time", "opend_time"]].drop_duplicates("op_id").copy()
    # pre-specified fallback when anaesthesia times are missing: use surgery times
    audit["anstart_missing_used_opstart"] = int(w.anstart_time.isna().sum())
    audit["anend_missing_used_opend"] = int(w.anend_time.isna().sum())
    audit["ops_window_fallback"] = w.loc[w.anstart_time.isna() | w.anend_time.isna(), "op_id"].tolist()
    w["anstart_time"] = w.anstart_time.fillna(w.opstart_time)
    w["anend_time"] = w.anend_time.fillna(w.opend_time)
    w = w[["op_id", "anstart_time", "anend_time"]]
    wide = wide.merge(w, on="op_id", how="inner")

    # ---- A_legacy (no window, no filter, OpAnyArt)
    any_art_all = wide.groupby("op_id")["art_mbp"].transform(lambda s: s.notna().any())
    pref_a = np.where(any_art_all, wide["art_mbp"], wide["nibp_mbp"])
    wide["low_A"] = (pref_a < low).astype(int)

    # ---- window
    inwin = (wide.chart_time >= wide.anstart_time) & (wide.chart_time < wide.anend_time)
    audit["points_total"] = int(len(wide))
    audit["points_outside_window"] = int((~inwin).sum())
    ww = wide[inwin].copy()
    art_raw = ww["art_mbp"]
    audit["art_values_lt20_in_window"] = int((art_raw < lo).sum())
    audit["art_values_eq6_in_window"] = int((art_raw == 6).sum())
    audit["nibp_values_lt20_in_window"] = int((ww["nibp_mbp"] < lo).sum())
    art = art_raw.where((art_raw >= lo) & (art_raw <= hi))
    nibp = ww["nibp_mbp"].where((ww["nibp_mbp"] >= lo) & (ww["nibp_mbp"] <= hi))
    ww["pref"] = art.where(art.notna(), nibp)
    ww["src"] = np.where(art.notna(), "art", np.where(nibp.notna(), "nibp", ""))
    ww = ww[ww["src"] != ""].copy()
    ww["low_F"] = (ww["pref"] < low).astype(int)
    # D: arterial low with concurrent NIBP >= 65 -> use NIBP
    nibp_c = nibp.reindex(ww.index)
    d_val = np.where((ww.src == "art") & (ww.pref < low) & (nibp_c >= low), nibp_c, ww.pref)
    ww["pref_D"] = d_val
    ww["low_D"] = (ww["pref_D"] < low).astype(int)

    def isolated(df_, col_val):
        df_ = df_.sort_values(["op_id", "chart_time"])
        prev_t = df_.groupby("op_id")["chart_time"].shift(1)
        next_t = df_.groupby("op_id")["chart_time"].shift(-1)
        prev_v = df_.groupby("op_id")[col_val].shift(1)
        next_v = df_.groupby("op_id")[col_val].shift(-1)
        iso = ((df_[col_val] < low) & (df_.chart_time - prev_t == step) & (next_t - df_.chart_time == step)
               & (prev_v >= low) & (next_v >= low))
        return iso.reindex(df_.index)

    ww["iso_F"] = isolated(ww, "pref")
    ww["iso_D"] = isolated(ww, "pref_D")
    ww["low_C"] = (ww.low_F.astype(bool) & ~ww.iso_F).astype(int)
    ww["low_E"] = (ww.low_D.astype(bool) & ~ww.iso_D).astype(int)

    per = ww.groupby("op_id").agg(
        n_epochs=("pref", "size"),
        n_art_epochs=("src", lambda s: int((s == "art").sum())),
        n_nibp_epochs=("src", lambda s: int((s == "nibp").sum())),
        low_F=("low_F", "sum"), low_C=("low_C", "sum"), low_D=("low_D", "sum"), low_E=("low_E", "sum"),
        map_min_valid=("pref", "min")).reset_index()
    legacy = wide.groupby("op_id")["low_A"].sum().rename("low_A").reset_index()
    out = w.merge(per, on="op_id", how="left").merge(legacy, on="op_id", how="left")
    for c in ("n_epochs", "n_art_epochs", "n_nibp_epochs", "low_F", "low_C", "low_D", "low_E", "low_A"):
        out[c] = out[c].fillna(0).astype(int)
    out["map65_A_legacy"] = step * out.low_A
    out["map65_final"] = step * out.low_F
    out["map65_C"] = step * out.low_C
    out["map65_D"] = step * out.low_D
    out["map65_E"] = step * out.low_E
    dur = (out.anend_time - out.anstart_time).astype(float)
    out["coverage_anes"] = np.where(dur > 0, step * out.n_epochs / dur, np.nan)
    out["art_any"] = (out.n_art_epochs > 0).astype(int)
    out["monitoring_mode"] = np.select(
        [(out.n_art_epochs > 0) & (out.n_nibp_epochs > 0), out.n_art_epochs > 0, out.n_nibp_epochs > 0],
        ["arterial+NIBP", "arterial only", "NIBP only"], "no valid MAP epoch")
    return out, audit


# ---------------------------------------------------------------------------
# 5. Cohort assembly
# ---------------------------------------------------------------------------
def prepare(df, expo, cfg, exposure_col="map65_final"):
    e = expo.drop(columns=["anstart_time", "anend_time"])
    df = df.drop(columns=[c for c in e.columns if c in df.columns and c != "op_id"])
    d = df.merge(e, on="op_id", how="left",
                 validate="one_to_one")
    d["icu"] = pd.to_numeric(d["icu_admission"], errors="coerce")
    # ties at the boundary are HIGH (44 in the 4,529 screening sample, 37 in the primary cohort).
    # Computed CAR values that equal the cut can sit 1e-17 below it in floating point, so compare
    # with a tolerance; a strict float comparison silently moves the ties to low CAR.
    d["high_car"] = (d["car"] >= cfg["car_cut"] - 1e-9).astype(int)
    d["ioh30"] = (d[exposure_col] >= cfg["ioh_cut_min"]).astype(int)
    d["phenotype"] = np.select(
        [(d.high_car == 0) & (d.ioh30 == 0), (d.high_car == 1) & (d.ioh30 == 0),
         (d.high_car == 0) & (d.ioh30 == 1)], ["G00", "G10", "G01"], "G11")
    return d


def timing_rule(d):
    """ICU admission requires icuin_time >= opend_time when icuin_time is recorded.
    Records violating this are excluded from every cohort (applied consistently)."""
    bad = d["icuin_time"].notna() & (d["icuin_time"] < d["opend_time"])
    return d[~bad].copy(), d.loc[bad, "op_id"].tolist()


# ---------------------------------------------------------------------------
# 6. Statistic functions
# ---------------------------------------------------------------------------
class _Frozen:
    """Freeze the design (levels, standardisation, columns) on the first call
    (the full analysis sample). Bootstrap/jackknife samples reuse it, so a
    replicate missing a level gives a zero column -> singular -> logged failure."""
    def __init__(self, spec):
        self.spec, self.des = spec, None

    def fit(self, df):
        if self.des is None:
            self.des = Design(df, self.spec)
        return fit_spec(df, self.spec, self.des)


def stat_pheno4(spec):
    fz = _Frozen(spec)
    def f(df):
        res, des = fz.fit(df)
        R = gcomp(df, res, des)
        out = {f"risk_{g}": R[g] * 100 for g in PHENOS}
        out.update({
            "RD_G10_vs_G00": (R["G10"] - R["G00"]) * 100,
            "RD_G01_vs_G00": (R["G01"] - R["G00"]) * 100,
            "RD_G11_vs_G00": (R["G11"] - R["G00"]) * 100,
            "IC_RD": (R["G11"] - R["G10"] - R["G01"] + R["G00"]) * 100,
            "RD_CAR_within_IOHlt30": (R["G10"] - R["G00"]) * 100,
            "RD_CAR_within_IOHge30": (R["G11"] - R["G01"]) * 100,
            "RD_IOH_within_lowCAR": (R["G01"] - R["G00"]) * 100,
            "RD_IOH_within_highCAR": (R["G11"] - R["G10"]) * 100,
            "sum_separate_RDs": (R["G10"] - R["G00"] + R["G01"] - R["G00"]) * 100,
        })
        for g in ("G10", "G01", "G11"):
            out[f"logOR_{g}"] = res.beta[res.names.index(f"ph_{g}")]
        return out
    return f


def stat_main_rd(spec):
    """Smaller statistic set for sensitivity analyses: Both-vs-Neither RD and logOR."""
    fz = _Frozen(spec)
    def f(df):
        res, des = fz.fit(df)
        R = gcomp(df, res, des, levels=["G00", "G11"])
        return {"RD_G11_vs_G00": (R["G11"] - R["G00"]) * 100,
                "logOR_G11": res.beta[res.names.index("ph_G11")],
                "risk_G00": R["G00"] * 100, "risk_G11": R["G11"] * 100}
    return f


def stat_strata_diff(spec, col):
    fz = {"art": _Frozen(spec), "noart": _Frozen(spec)}
    def f(df):
        out = {}
        for lab, val in (("art", 1), ("noart", 0)):
            sub = df[df[col] == val].reset_index(drop=True)
            res, des = fz[lab].fit(sub)
            R = gcomp(sub, res, des, levels=["G00", "G11"])
            out[f"RD_{lab}"] = (R["G11"] - R["G00"]) * 100
        out["RD_art_minus_noart"] = out["RD_art"] - out["RD_noart"]
        return out
    return f


def wald_row(res, name):
    o, l, h, p = res.or_ci(name)
    return {"term": name, "OR": o, "OR_lo": l, "OR_hi": h, "p_wald": p}


# ---------------------------------------------------------------------------
# 7. Analyses
# ---------------------------------------------------------------------------
def counts_by_pheno(d, outcome="icu"):
    t = d.groupby("phenotype")[outcome].agg(n="size", events="sum").reindex(PHENOS).fillna(0)
    t["crude_pct"] = 100 * t.events / t.n.replace(0, np.nan)
    t.index = [PHENO_LABEL[g] for g in t.index]
    return t


def fmt_ci(p, lo, hi, nd=2):
    return f"{p:.{nd}f} ({lo:.{nd}f} to {hi:.{nd}f})"


def run_all(cfg):
    out = Path(cfg["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    log = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "config": cfg,
           "python": sys.version, "numpy": np.__version__, "pandas": pd.__version__}
    B, seed = cfg["n_boot"], cfg["seed"]

    # ---- 7.0 INSPIRE version check
    log["inspire_version_check"] = verify_inspire_version(cfg)

    # ---- 7.1 exposure
    prim0 = pd.read_csv(cfg["primary_cohort_csv"], low_memory=False)
    durc0 = pd.read_csv(cfg["duration_cohort_csv"], low_memory=False)
    ids = set(prim0.op_id) | set(durc0.op_id)
    carav = None
    if cfg.get("car_available_csv") and Path(cfg["car_available_csv"]).exists():
        carav = pd.read_csv(cfg["car_available_csv"], low_memory=False)
        ids |= set(carav.op_id)
    ops = pd.concat([x[["op_id", "anstart_time", "anend_time", "opstart_time", "opend_time"]] for x in (prim0, durc0)
                     + ((carav,) if carav is not None else ())]).drop_duplicates("op_id")
    vit = load_vitals(cfg["inspire_vitals"], ids)
    expo, audit = build_exposure(vit, ops, cfg)
    expo.to_csv(out / "01_exposure_per_operation.csv", index=False)
    log["exposure_audit"] = audit

    # ---- 7.2 cohorts
    prim_all = prepare(prim0, expo, cfg)
    prim, bad_ids = timing_rule(prim_all)
    durc, bad_d = timing_rule(prepare(durc0, expo, cfg))
    log["timing_rule_excluded_primary"] = bad_ids
    log["timing_rule_excluded_duration"] = bad_d
    if "proc_axis" in prim and prim["proc_axis"].isna().any():
        raise SystemExit("proc_axis has missing values: do not fill them silently (old code used fillna).")
    needed = ["icu", "car"] + P3_CONT + P3_BIN + list(P3_CAT)
    miss = prim[needed].isna().sum()
    if miss.any():
        raise SystemExit(f"Missing primary covariates in primary cohort:\n{miss[miss>0]}")

    flow = [
        {"step": "Primary complete-case cohort (as previously defined)", "n": len(prim_all), "events": int(prim_all.icu.sum())},
        {"step": "Excluded: ICU entry before end of surgery", "n": len(bad_ids), "events": int(prim_all[prim_all.op_id.isin(bad_ids)].icu.sum())},
        {"step": "Revised primary cohort", "n": len(prim), "events": int(prim.icu.sum())},
        {"step": "Duration cohort (as previously defined)", "n": len(durc0), "events": int(pd.to_numeric(durc0.icu_admission).sum())},
        {"step": "Revised duration cohort", "n": len(durc), "events": int(durc.icu.sum())},
    ]
    log["high_car_primary"] = int(prim.high_car.sum())
    log["car_boundary_ties_primary"] = int(np.isclose(prim.car, cfg["car_cut"], rtol=0, atol=1e-9).sum())
    pd.DataFrame(flow).to_csv(out / "01_cohort_flow.csv", index=False)
    counts_by_pheno(prim).to_csv(out / "01_phenotype_counts_final.csv")

    # exposure by rule + reclassification versus published map65_min
    rules = {"published": "map65_min", "A_legacy": "map65_A_legacy", "FINAL": "map65_final",
             "C_isolated": "map65_C", "D_art_vs_nibp": "map65_D", "E_combined": "map65_E"}
    rows = []
    base_ph = prepare(prim0, expo, cfg, "map65_min")
    base_ph, _ = timing_rule(base_ph)
    for r, col in rules.items():
        x = prim[col].astype(float)
        cat = np.select([x == 0, x < 10, x < 30], [0, 1, 2], 3)
        cat0 = np.select([prim.map65_min == 0, prim.map65_min < 10, prim.map65_min < 30], [0, 1, 2], 3)
        ph = prepare(prim0, expo, cfg, col)
        ph, _ = timing_rule(ph)
        rows.append({"rule": r, "mean_min": x.mean(), "median_min": x.median(), "p25": x.quantile(.25),
                     "p75": x.quantile(.75), "n_0": int((cat == 0).sum()), "n_gt0_lt10": int((cat == 1).sum()),
                     "n_10_lt30": int((cat == 2).sum()), "n_ge30": int((cat == 3).sum()),
                     "category_changed_vs_published": int((cat != cat0).sum()),
                     "phenotype_changed_vs_published": int((ph.phenotype.values != base_ph.phenotype.values).sum())})
    pd.DataFrame(rows).to_csv(out / "01_exposure_by_rule.csv", index=False)
    match = (prim.map65_A_legacy == prim.map65_min)
    log["legacy_reproduction_exact_match_pct"] = float(100 * match.mean())
    pd.crosstab(base_ph.phenotype, prim.phenotype.values, rownames=["published"], colnames=["final"]) \
        .to_csv(out / "01_phenotype_transition_published_to_final.csv")
    mon = prim.groupby("phenotype").agg(
        n=("op_id", "size"), coverage_median=("coverage_anes", "median"),
        coverage_p25=("coverage_anes", lambda s: s.quantile(.25)),
        coverage_p75=("coverage_anes", lambda s: s.quantile(.75)),
        coverage_ge80=("coverage_anes", lambda s: int((s >= .8).sum())),
        art_nibp=("monitoring_mode", lambda s: int((s == "arterial+NIBP").sum())),
        art_only=("monitoring_mode", lambda s: int((s == "arterial only").sum())),
        nibp_only=("monitoring_mode", lambda s: int((s == "NIBP only").sum())),
        none=("monitoring_mode", lambda s: int((s == "no valid MAP epoch").sum())))
    mon = mon.reindex(PHENOS)
    mon.index = [PHENO_LABEL[g] for g in mon.index]
    mon.to_csv(out / "01_monitoring_by_phenotype.csv")

    # ---- 7.3 primary model: diagnostics, Table 2, within-stratum RDs, BCa
    spec = Spec(label="P3")
    res, des = fit_spec(prim, spec)
    diag = fit_diagnostics(prim, spec, res)
    diag.to_csv(out / "00_fit_diagnostics.csv", index=False)
    coefs = pd.DataFrame({"term": res.names, "beta_standardised_scale": res.beta,
                          "se": np.sqrt(np.diag(res.cov))})
    coefs.to_csv(out / "02_primary_coefficients.csv", index=False)
    jk = jackknife_loo if cfg.get("jackknife_for_bca") == "leave_one_out" else None
    point, summ, _ = bootstrap(prim, stat_pheno4(spec), B, seed, "02_primary", out, jackknife=jk)
    s = summ.set_index("estimand")
    t2 = counts_by_pheno(prim)
    t2["std_risk_pct"] = [fmt_ci(s.loc[f"risk_{g}", "point"], s.loc[f"risk_{g}", "pct_lo"], s.loc[f"risk_{g}", "pct_hi"], 1) for g in PHENOS]
    t2["RD_vs_Neither_pp"] = ["0 (reference)"] + [fmt_ci(s.loc[f"RD_{g}_vs_G00", "point"], s.loc[f"RD_{g}_vs_G00", "pct_lo"], s.loc[f"RD_{g}_vs_G00", "pct_hi"]) for g in ("G10", "G01", "G11")]
    t2["OR_Wald"] = ["1.00 (reference)"] + [fmt_ci(*res.or_ci(f"ph_{g}")[:3]) for g in ("G10", "G01", "G11")]
    t2.to_csv(out / "02_primary_table2.csv")

    # ---- 7.4 Comment 1: primary contrast under each exposure rule (same estimator)
    rule_rows = []
    # reconciliation row: previous cohort (n before timing rule) + published exposure + converged MLE
    d_prev = prepare(prim0, expo, cfg, "map65_min")
    _, sm, _ = bootstrap(d_prev, stat_main_rd(spec), B, seed, "03_previous_cohort_published_exposure", out)
    rule_rows.append(summary_row("previous cohort, published exposure, converged MLE (reconciliation)", d_prev, sm))
    for r, col in rules.items():
        if r == "A_legacy":
            continue
        d_r = prepare(prim0, expo, cfg, col)
        d_r, _ = timing_rule(d_r)
        p_, sm, _ = bootstrap(d_r, stat_main_rd(spec), B, seed, f"03_rule_{r}", out)
        rule_rows.append(summary_row(f"exposure rule {r}", d_r, sm))
    pd.DataFrame(rule_rows).to_csv(out / "03_primary_contrast_by_exposure_rule.csv", index=False)

    # ---- 7.5 Comment 4: monitoring
    mrows = [summary_row("P3 (primary)", prim, summ)]
    sp_m = Spec(extra=["art_any"], label="P3+art")
    _, sm, _ = bootstrap(prim, stat_main_rd(sp_m), B, seed, "04_P3_plus_art", out)
    mrows.append(summary_row("P3 + arterial monitoring", prim, sm))
    for lab, sub in (("arterial stratum", prim[prim.art_any == 1]),
                     ("no arterial (NIBP only or none)", prim[prim.art_any == 0]),
                     ("coverage >= 80% (window-based)", prim[prim.coverage_anes >= .8])):
        sub = sub.reset_index(drop=True)
        try:
            _, sm, _ = bootstrap(sub, stat_main_rd(spec), B, seed, "04_" + slug(lab), out)
            mrows.append(summary_row(lab, sub, sm))
        except FitFailure as e:
            mrows.append({"analysis": lab, "n": len(sub), "events": int(sub.icu.sum()), "note": e.args[0]})
    pd.DataFrame(mrows).to_csv(out / "04_monitoring_contrasts.csv", index=False)
    cnt = []
    for lab, sub in (("all", prim), ("arterial", prim[prim.art_any == 1]), ("no arterial", prim[prim.art_any == 0])):
        c = counts_by_pheno(sub)
        c.insert(0, "stratum", lab)
        cnt.append(c)
    pd.concat(cnt).to_csv(out / "04_phenotype_counts_by_monitoring.csv")
    # multiplicative interaction (LRT, 3 df) and additive (bootstrap difference of stratum RDs)
    r0, _ = fit_spec(prim, Spec(extra=["art_any"]))
    r1, _ = fit_spec(prim, Spec(extra=["art_any"], interact_pheno_with="art_any"))
    lr = 2 * (r1.llf - r0.llf)
    _, sm_d, _ = bootstrap(prim, stat_strata_diff(spec, "art_any"), B, seed, "04_additive_interaction", out)
    inter = [{"test": "phenotype x arterial monitoring, LRT (multiplicative)", "statistic": lr, "df": 3,
              "p": stats.chi2.sf(lr, 3)}]
    w = wald_row(r1, "ph_G11:art_any")
    inter.append({"test": "Both x arterial, Wald (log-OR scale)", "statistic": math.log(w["OR"]), "df": 1, "p": w["p_wald"]})
    d_ = sm_d.set_index("estimand").loc["RD_art_minus_noart"]
    inter.append({"test": "difference in Both-vs-Neither RD, arterial minus no arterial (additive), pp",
                  "statistic": d_.point, "df": np.nan, "p": d_.p_boot,
                  "ci": fmt_ci(d_.point, d_.pct_lo, d_.pct_hi)})
    pd.DataFrame(inter).to_csv(out / "04_interaction_tests.csv", index=False)

    # ---- 7.6 Comment 5: case mix
    crows = [summary_row("P3 (primary)", prim, summ)]
    if "indication_group" in prim:
        for lab, sp in (("+ indication group", Spec(extra_cat={"indication_group": "other_elective_or_unclassified"})),
                        ("+ Charlson index", Spec(extra=["charlson_index"])),
                        ("+ indication group + Charlson", Spec(extra=["charlson_index"], extra_cat={"indication_group": "other_elective_or_unclassified"}))):
            _, sm, _ = bootstrap(prim, stat_main_rd(sp), B, seed, "05_" + slug(lab), out)
            crows.append(summary_row(lab, prim, sm))
    restr = {}
    if {"infection_related", "tumour_related"} <= set(prim.columns):
        restr["exclude infection- or tumour-related"] = ~((prim.infection_related == 1) | (prim.tumour_related == 1))
    restr.update({"exclude spine procedures": prim.proc_axis != "spine_procedure",
             "exclude emergency surgery": prim.emop != 1})
    excl = []
    for lab, keep in restr.items():
        sub = prim[keep].reset_index(drop=True)
        excl.append({"analysis": lab, "start_n": len(prim), "excluded": int((~keep).sum()), "final_n": len(sub),
                     "events": int(sub.icu.sum())})
        _, sm, _ = bootstrap(sub, stat_main_rd(spec), B, seed, "05_" + slug(lab), out)
        crows.append(summary_row(lab, sub, sm))
    pd.DataFrame(crows).to_csv(out / "05_casemix_sensitivity.csv", index=False)
    pd.DataFrame(excl).to_csv(out / "05_restricted_exclusion_arithmetic.csv", index=False)

    # ---- 7.7 Comment 6: alternate outcomes, sparse-data checks
    arows = []
    for oc in ("icu_stay_gt24h", "icu_stay_gt48h", "death_inhosp", "kidney_event"):
        if oc not in prim:
            continue
        sub = prim[prim[oc].notna()].reset_index(drop=True)
        cont = [c for c in P3_CONT if not (oc == "kidney_event" and c == "creatinine")]
        sp = Spec(outcome=oc, cont=cont)
        try:
            _, sm, _ = bootstrap(sub, stat_main_rd(sp), B, seed, f"06_{oc}", out)
            arows.append(summary_row(oc, sub, sm, outcome=oc))
        except FitFailure as e:
            arows.append({"analysis": oc, "n": len(sub), "events": int(sub[oc].sum()), "note": "point fit failed: " + e.args[0]})
    if "death_inhosp" in prim:
        for lab, sp in (("death: full P3, Firth", Spec(outcome="death_inhosp", firth=True)),
                        ("death: parsimonious (age, ASA, sex, emergency, procedure), ML",
                         Spec(outcome="death_inhosp", cont=["age", "asa"], binary=["female", "emop"])),
                        ("death: parsimonious, Firth",
                         Spec(outcome="death_inhosp", cont=["age", "asa"], binary=["female", "emop"], firth=True))):
            _, sm, _ = bootstrap(prim, stat_main_rd(sp), B, seed, "06_" + slug(lab), out)
            arows.append(summary_row(lab, prim, sm, outcome="death_inhosp"))
    pd.DataFrame(arows).to_csv(out / "06_alternate_outcomes.csv", index=False)

    # ---- 7.8 Duration analyses (Table 3, Figure 3, Table S8) on the revised duration cohort
    duration_tables(durc, out)

    # ---- 7.9 LOS (Table 4, Table S10) and subgroups (Figure 4)
    los_tables(prim, out)
    subgroup_table(prim, out)

    # ---- 7.10 Comment 9: prediction, optimism-corrected
    prediction_table(prim, out, n_boot=500, seed=seed)

    # ---- 7.11 Table 1
    table1(prim).to_csv(out / "07_table1.csv")

    # ---- 7.12 multiple imputation (Table S11B)
    if carav is not None:
        mi_table(carav, expo, cfg, out)

    log["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    (out / "00_run_log.json").write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")
    print("done ->", out)


def slug(x):
    return re.sub(r"[^A-Za-z0-9]+", "_", x).strip("_")[:40]


def summary_row(label, d, summ, outcome="icu"):
    s = summ.set_index("estimand")
    rd = s.loc["RD_G11_vs_G00"]
    lo = s.loc["logOR_G11"]
    row = {"analysis": label, "n": len(d), "events": int(d[outcome].sum()),
           "n_both": int((d.phenotype == "G11").sum()),
           "events_neither": int(d.loc[d.phenotype == "G00", outcome].sum()),
           "RD_pp": rd.point, "RD_lo": rd.pct_lo, "RD_hi": rd.pct_hi, "p_boot": rd.p_boot_display,
           "OR": math.exp(lo.point), "OR_boot_lo": math.exp(lo.pct_lo), "OR_boot_hi": math.exp(lo.pct_hi),
           "n_boot_ok": int(rd.n_boot_ok), "n_boot_failed": int(rd.n_boot_failed),
           "n_reps_abs_RD_lt_1e-5pp": int(rd["n_abs_lt_1e-5"])}
    if "bca_lo" in s:
        row.update({"RD_bca_lo": rd.bca_lo, "RD_bca_hi": rd.bca_hi})
    return row


def fit_diagnostics(df, spec, res):
    """Convergence evidence for the primary fit, plus a cross-check against an
    independent optimiser (scipy BFGS on the same objective)."""
    from scipy.optimize import minimize
    des = Design(df, spec)
    X, names = des.matrix(df)
    y = df[spec.outcome].astype(float).values
    r2 = minimize(lambda b: -_loglik(X, y, b), np.zeros(X.shape[1]),
                  jac=lambda b: -(X.T @ (y - expit(X @ b))), method="BFGS",
                  options={"gtol": 1e-6, "maxiter": 10000})
    return pd.DataFrame([{
        "fit": "Newton-Raphson (primary)", "converged": res.converged, "iterations": res.n_iter,
        "llf": res.llf, "max_abs_score": res.max_abs_score},
        {"fit": "scipy BFGS cross-check", "converged": bool(r2.success), "message": r2.message, "iterations": r2.nit,
         "llf": -r2.fun, "max_abs_score": float(np.max(np.abs(X.T @ (y - expit(X @ r2.x))))),
         "max_abs_beta_diff_vs_newton": float(np.max(np.abs(r2.x - res.beta)))}])


# ---------------------------------------------------------------------------
# 8. Secondary tables
# ---------------------------------------------------------------------------
D_SETS = {
    "D0": dict(cont=[], binary=[], cat={}),
    "D1": dict(cont=["age"], binary=["female"], cat={}),
    "D2": dict(cont=["age", "asa"], binary=["female", "emop"], cat={}),
    "D3": dict(cont=["age", "asa", "bmi", "hb", "albumin", "creatinine", "glucose"], binary=["female", "emop"], cat={}),
    "D4": dict(cont=["age", "asa", "bmi", "hb", "albumin", "creatinine", "glucose", "obs_duration_proxy"], binary=["female", "emop"], cat={}),
    "D5A": dict(cont=["age", "asa", "bmi", "hb", "albumin", "creatinine", "glucose", "op_duration_min"], binary=["female", "emop", "general_anes"], cat={"proc_axis": "other_orthopedic"}),
}


def duration_tables(d, out):
    rows = []
    cnt = np.select([d.map65_final == 0, d.map65_final < 10, d.map65_final < 30], [0, 1, 2], 3)
    for k, lab in enumerate(["0", ">0 to <10", "10 to <30", ">=30"]):
        rows.append({"model": "counts", "term": lab, "n": int((cnt == k).sum()), "events": int(d.icu[cnt == k].sum())})
    for m, cov in D_SETS.items():
        if m == "D4" and "obs_duration_proxy" not in d:
            continue
        r, _ = fit_spec(d, Spec(exposure="dur_cat", **cov))
        rt, _ = fit_spec(d, Spec(exposure="dur_trend", **cov))
        for t in ("dur_gt0_lt10", "dur_10_lt30", "dur_ge30"):
            rows.append({"model": m, **wald_row(r, t)})
        rows.append({"model": m, **wald_row(rt, "dur_score"), "note": "trend (ordinal score 0-3)"})
    pd.DataFrame(rows).to_csv(out / "08_table3_duration_models.csv", index=False)
    # spline (D5A) with knot sensitivity
    cov = D_SETS["D5A"]
    rlin, _ = fit_spec(d, Spec(exposure="dur_linear", **cov))
    srows, curve = [], []
    for knots in ((0, 5, 45), (0, 10, 30), (0, 5, 30, 60)):
        sp = Spec(exposure="dur_rcs", knots=knots, **cov)
        r, des = fit_spec(d, sp)
        lr = 2 * (r.llf - rlin.llf)
        dfree = len(knots) - 2
        idx = [r.names.index(n) for n in r.names if n.startswith("dur_")]
        row = {"knots": ",".join(map(str, knots)), "aic": -2 * r.llf + 2 * len(r.beta), "lr_nonlinear": lr,
               "df": dfree, "p_nonlinear": stats.chi2.sf(lr, dfree)}
        for x in (10, 30, 60):
            v = np.concatenate([[x], rcs_basis(np.array([float(x)]), knots)[0]]) - np.concatenate([[0], rcs_basis(np.array([0.0]), knots)[0]])
            b = float(v @ r.beta[idx]); se = float(np.sqrt(v @ r.cov[np.ix_(idx, idx)] @ v))
            row[f"OR_{x}min"] = fmt_ci(math.exp(b), math.exp(b - 1.96 * se), math.exp(b + 1.96 * se))
        srows.append(row)
        if knots == (0, 5, 45):
            for x in range(0, 125, 5):     # observed 5-minute grid only (Minor comment 6)
                v = np.concatenate([[x], rcs_basis(np.array([float(x)]), knots)[0]]) - np.concatenate([[0], rcs_basis(np.array([0.0]), knots)[0]])
                b = float(v @ r.beta[idx]); se = float(np.sqrt(v @ r.cov[np.ix_(idx, idx)] @ v))
                curve.append({"minutes": x, "OR": math.exp(b), "lo": math.exp(b - 1.96 * se), "hi": math.exp(b + 1.96 * se)})
    pd.DataFrame(srows).to_csv(out / "08_tableS8_spline_knots.csv", index=False)
    pd.DataFrame(curve).to_csv(out / "08_figure3_curve_on_5min_grid.csv", index=False)
    pd.DataFrame([wald_row(rlin, "dur_per10")]).to_csv(out / "08_linear_per10min.csv", index=False)


def los_tables(prim, out):
    try:
        import statsmodels.api as sm
    except ImportError:
        warnings.warn("statsmodels not installed: LOS median-regression tables skipped")
        return
    rows = []
    surv = prim[prim.death_inhosp == 0].reset_index(drop=True) if "death_inhosp" in prim else prim
    jobs = [("total LOS, survivors", surv, "los_total_days"), ("postoperative LOS, survivors", surv, "los_postop_days")]
    if "los_total_days" in prim and "death_inhosp" in prim:
        comp = prim.copy()
        worst = surv.los_total_days.max() + 1
        comp["los_rank_composite"] = np.where(comp.death_inhosp == 1, worst, comp.los_total_days)
        jobs.append(("rank composite (death = worst), full cohort", comp, "los_rank_composite"))
    for lab, d, ycol in jobs:
        if ycol not in d:
            continue
        des = Design(d, Spec())
        X, names = des.matrix(d)
        r = sm.QuantReg(d[ycol].astype(float).values, X).fit(q=0.5)
        ci = np.asarray(r.conf_int())
        for g in ("G10", "G01", "G11"):
            j = names.index(f"ph_{g}")
            rows.append({"outcome": lab, "n": len(d), "contrast": f"{PHENO_LABEL[g]} vs Neither",
                         "median_diff_days": r.params[j], "lo": ci[j, 0], "hi": ci[j, 1], "p": r.pvalues[j]})
    pd.DataFrame(rows).to_csv(out / "09_table4_S10_los.csv", index=False)


def subgroup_table(prim, out):
    d = prim[prim.phenotype.isin(["G00", "G11"])].reset_index(drop=True)
    med = prim.op_duration_min.median()
    d["sg_age_ge75"] = (d.age >= 75).astype(int)
    d["sg_female"] = d.female
    d["sg_asa_ge3"] = (d.asa >= 3).astype(int)
    d["sg_opdur_gt_median"] = (d.op_duration_min > med).astype(int)
    d["sg_general_anes"] = d.general_anes
    rows = []
    sp = Spec(exposure="both_vs_neither")
    r_all, _ = fit_spec(d, sp)
    rows.append({"subgroup": "overall", "level": "", "n": len(d), "events": int(d.icu.sum()), **wald_row(r_all, "ph_G11")})
    for sg in ("sg_age_ge75", "sg_female", "sg_asa_ge3", "sg_opdur_gt_median", "sg_general_anes"):
        main = [] if sg in ("sg_female", "sg_general_anes") else [sg]   # already P3 covariates
        base, _ = fit_spec(d, Spec(exposure="both_vs_neither", extra=main))
        d["_int"] = d[sg] * (d.phenotype == "G11").astype(int)
        full, _ = fit_spec(d, Spec(exposure="both_vs_neither", extra=main + ["_int"]))
        p_int = stats.chi2.sf(2 * (full.llf - base.llf), 1)
        for lv in (0, 1):
            sub = d[d[sg] == lv].reset_index(drop=True)
            try:
                r, _ = fit_spec(sub, sp)
                rows.append({"subgroup": sg, "level": lv, "n": len(sub), "events": int(sub.icu.sum()),
                             **wald_row(r, "ph_G11"), "p_interaction_LRT": p_int})
            except FitFailure as e:
                rows.append({"subgroup": sg, "level": lv, "n": len(sub), "events": int(sub.icu.sum()), "note": e.args[0]})
    pd.DataFrame(rows).to_csv(out / "10_figure4_subgroups.csv", index=False)


def auc(y, p):
    r = stats.rankdata(p)
    n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)


def nri_idi(y, p0, p1):
    up, dn = p1 > p0, p1 < p0
    e, ne = y == 1, y == 0
    nri = (up[e].mean() - dn[e].mean()) + (dn[ne].mean() - up[ne].mean())
    idi = (p1[e].mean() - p0[e].mean()) - (p1[ne].mean() - p0[ne].mean())
    return nri, idi


def prediction_table(prim, out, n_boot=500, seed=1):
    base = dict(cont=["age", "asa"], binary=["emop"], cat={"proc_axis": "other_orthopedic"})
    specs = {"baseline": Spec(exposure="none", **base), "baseline+phenotype": Spec(exposure="pheno4", **base),
             "baseline+high CAR": Spec(exposure="highcar", **base)}

    def metrics(train, test):
        y = test.icu.values.astype(float)
        p = {}
        for k, sp in specs.items():
            r, des = fit_spec(train, sp)
            X, _ = des.matrix(test)
            p[k] = expit(X @ r.beta)
        m = {f"AUC_{k}": auc(y, v) for k, v in p.items()}
        m["dAUC_phenotype"] = m["AUC_baseline+phenotype"] - m["AUC_baseline"]
        m["dAUC_highCAR"] = m["AUC_baseline+high CAR"] - m["AUC_baseline"]
        m["NRI_cf_phenotype"], m["IDI_phenotype"] = nri_idi(y, p["baseline"], p["baseline+phenotype"])
        m["NRI_cf_highCAR"], m["IDI_highCAR"] = nri_idi(y, p["baseline"], p["baseline+high CAR"])
        return m

    app = metrics(prim, prim)
    rng = np.random.default_rng(seed)
    opt, fails = {k: [] for k in app}, 0
    for _ in range(n_boot):
        bs = prim.iloc[rng.integers(0, len(prim), len(prim))].reset_index(drop=True)
        try:
            mb, mo = metrics(bs, bs), metrics(bs, prim)
        except FitFailure:
            fails += 1
            continue
        for k in app:
            opt[k].append(mb[k] - mo[k])
    rows = [{"metric": k, "apparent": app[k], "mean_optimism": np.mean(opt[k]), "optimism_corrected": app[k] - np.mean(opt[k]),
             "n_boot_ok": len(opt[k]), "n_boot_failed": fails} for k in app]
    pd.DataFrame(rows).to_csv(out / "11_tableS14_optimism_corrected.csv", index=False)


def table1(d):
    cont = ["age", "bmi", "hb", "albumin", "crp", "car", "creatinine", "glucose", "map65_final", "op_duration_min", "charlson_index"]
    binv = ["female", "emop", "general_anes", "icu"]
    rows = {}
    groups = [("Overall", d)] + [(PHENO_LABEL[g], d[d.phenotype == g]) for g in PHENOS]
    for c in cont:
        if c in d:
            rows[c + ", median (IQR)"] = [f"{x[c].median():.3g} ({x[c].quantile(.25):.3g}-{x[c].quantile(.75):.3g})" for _, x in groups]
    for c in binv:
        if c in d:
            rows[c + ", n (%)"] = [f"{int(x[c].sum())} ({100*x[c].mean():.1f})" for _, x in groups]
    rows["ASA >=3, n (%)"] = [f"{int((x.asa>=3).sum())} ({100*(x.asa>=3).mean():.1f})" for _, x in groups]
    for lv in sorted(d.proc_axis.unique()):
        rows[f"{lv}, n (%)"] = [f"{int((x.proc_axis==lv).sum())} ({100*(x.proc_axis==lv).mean():.1f})" for _, x in groups]
    t = pd.DataFrame(rows, index=[f"{n} (n={len(x)})" for n, x in groups]).T
    return t


def mi_table(carav, expo, cfg, out, m=20):
    try:
        from sklearn.experimental import enable_iterative_imputer  # noqa: F401
        from sklearn.impute import IterativeImputer
        from sklearn.linear_model import BayesianRidge
    except ImportError:
        warnings.warn("scikit-learn not installed: MI table skipped")
        return
    d = prepare(carav, expo, cfg)
    d, _ = timing_rule(d)
    d = d[d.icu.notna()].reset_index(drop=True)
    num = P3_CONT + P3_BIN
    pa = pd.get_dummies(d.proc_axis, prefix="pa", dtype=float)
    pa.loc[d.proc_axis.isna().values, :] = np.nan
    base = pd.concat([d[num + ["icu", "high_car", "ioh30"]].astype(float), pa], axis=1)
    betas, vars_ = [], []
    for i in range(m):
        imp = IterativeImputer(estimator=BayesianRidge(), sample_posterior=True, max_iter=20, random_state=cfg["seed"] + i)
        arr = pd.DataFrame(imp.fit_transform(base), columns=base.columns)
        di = d.copy()
        for c in P3_CONT:
            di[c] = arr[c]
        di["asa"] = arr["asa"].round().clip(1, 5)
        for c in P3_BIN:
            di[c] = (arr[c] >= 0.5).astype(int)
        pacols = [c for c in arr if c.startswith("pa_")]
        di["proc_axis"] = [pacols[j][3:] for j in np.argmax(arr[pacols].values, axis=1)]
        r, _ = fit_spec(di, Spec())
        j = r.names.index("ph_G11")
        betas.append(r.beta[j]); vars_.append(r.cov[j, j])
    qbar, ubar, bvar = np.mean(betas), np.mean(vars_), np.var(betas, ddof=1)
    tvar = ubar + (1 + 1 / m) * bvar
    dfree = (m - 1) * (1 + ubar / ((1 + 1 / m) * bvar)) ** 2 if bvar > 0 else np.inf
    tq = stats.t.ppf(.975, dfree)
    pd.DataFrame([{"analysis": "pooled covariate MI (CAR not imputed)", "n": len(d), "m": m,
                   "OR_Both": math.exp(qbar), "lo": math.exp(qbar - tq * math.sqrt(tvar)),
                   "hi": math.exp(qbar + tq * math.sqrt(tvar))}]).to_csv(out / "12_tableS11_mi.csv", index=False)


# ---------------------------------------------------------------------------
# 9. INSPIRE version verification
# ---------------------------------------------------------------------------
def sha256_file(path, block=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(block), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_inspire_version(cfg):
    raw = Path(cfg.get("inspire_raw_dir", ""))
    sums = cfg.get("physionet_sha256sums", {})
    if not raw.exists():
        return {"status": "raw dir not found"}
    local = {p.name: sha256_file(p) for p in raw.iterdir() if p.suffix in (".gz", ".csv")}
    res = {"local_sha256": local}
    for ver, f in sums.items():
        if not Path(f).exists():
            res[ver] = "SHA256SUMS file not provided"
            continue
        ref = {}
        for line in Path(f).read_text().splitlines():
            parts = line.split()
            if len(parts) == 2:
                ref[parts[1].lstrip("*").split("/")[-1]] = parts[0]
        res[ver] = {k: ("match" if ref.get(k) == v else ("absent" if k not in ref else "DIFFERENT")) for k, v in local.items()}
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="JSON config (see CONFIG_TEMPLATE)")
    ap.add_argument("--write-template", action="store_true")
    a = ap.parse_args()
    if a.write_template:
        Path("config.json").write_text(json.dumps(CONFIG_TEMPLATE, indent=2), encoding="utf-8")
        print("wrote config.json")
        sys.exit(0)
    cfg = {**CONFIG_TEMPLATE, **json.loads(Path(a.config).read_text(encoding="utf-8"))}
    run_all(cfg)
