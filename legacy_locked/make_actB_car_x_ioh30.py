# -*- coding: utf-8 -*-
"""Act B — CAR (CRP/albumin) × IOH≥30 → ICU.

CAR = CRP(mg/dL) / (albumin[g/dL] × 10)  [same as CAR_MACCE SAP v1.9]
Screen binary cuts (median / Q3 / T3), then full bootstrap for primary cut.
Outputs → Desktop 222\\05_ActB_CAR_IOH30
"""
from __future__ import annotations

from pathlib import Path
import json
import shutil
import warnings
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

ROOT = Path(r"e:\DS-智能体\222")
OUT_PROJ = ROOT / "results" / "car_ioh_icu_os65" / "05_ActB_RD_RERI"
DESK = Path(r"E:\桌面") / "222" / "05_ActB_CAR_IOH30"
IOH_THR = 30.0
PHENOS = ["G00", "G10", "G01", "G11"]
# Clinical: no CRP, no albumin (in CAR)
COV_CONT = ["age", "asa", "op_duration_min", "creatinine", "bmi", "hb", "glucose"]
COV_BIN = ["female", "emop", "general_anes"]
N_BOOT = 1000
RNG = np.random.default_rng(20261013)


def set_run_font(run, size=10, bold=False):
    run.font.name = "Times New Roman"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    run.font.size = Pt(size)
    run.bold = bold


def set_cell_border(cell, **kwargs):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{edge}")
        if edge in kwargs:
            sz, val, color = kwargs[edge]
            el.set(qn("w:val"), val)
            el.set(qn("w:sz"), str(sz))
            el.set(qn("w:color"), color)
            el.set(qn("w:space"), "0")
        else:
            el.set(qn("w:val"), "nil")
        tcBorders.append(el)
    tcPr.append(tcBorders)


def apply_three_line(table):
    nrows = len(table.rows)
    for i, row in enumerate(table.rows):
        for cell in row.cells:
            if i == 0:
                set_cell_border(
                    cell,
                    top=(18, "single", "000000"),
                    bottom=(12, "single", "000000"),
                    left=(0, "nil", "000000"),
                    right=(0, "nil", "000000"),
                )
            elif i == nrows - 1:
                set_cell_border(
                    cell,
                    top=(0, "nil", "000000"),
                    bottom=(18, "single", "000000"),
                    left=(0, "nil", "000000"),
                    right=(0, "nil", "000000"),
                )
            else:
                set_cell_border(
                    cell,
                    top=(0, "nil", "000000"),
                    bottom=(0, "nil", "000000"),
                    left=(0, "nil", "000000"),
                    right=(0, "nil", "000000"),
                )


def write_cell(cell, text, bold=False, align="center", size=9):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = (
        WD_ALIGN_PARAGRAPH.CENTER if align == "center" else WD_ALIGN_PARAGRAPH.LEFT
    )
    run = p.add_run(str(text))
    set_run_font(run, size=size, bold=bold)


def fmt_pct(x):
    return f"{100 * x:.1f}"


def fmt_ci_pp(est, lo, hi):
    return f"{100 * est:.2f} ({100 * lo:.2f} to {100 * hi:.2f})"


def fmt_p(p):
    if p is None or (isinstance(p, float) and np.isnan(p)):
        return "—"
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}"


def load_base() -> pd.DataFrame:
    base = pd.read_csv(
        ROOT
        / "results"
        / "anemia_ioh_icu_os65"
        / "01_Table01_baseline"
        / "Table01_analytic_cohort.csv"
    )
    enrich = pd.read_csv(
        ROOT / "data" / "inspire_os65_car_enrich.csv",
        usecols=["op_id", "labs_crp_last_preop7d", "labs_albumin_last_preop7d"],
    )
    d = base.merge(enrich, on="op_id", how="left")
    d["icu"] = pd.to_numeric(d["icu_admission"], errors="coerce")
    d["map65_min"] = pd.to_numeric(d["map65_min"], errors="coerce")
    d["crp"] = pd.to_numeric(d["labs_crp_last_preop7d"], errors="coerce")
    # albumin: prefer base preop albumin, fallback enrich
    d["alb"] = pd.to_numeric(d["albumin"], errors="coerce")
    alb2 = pd.to_numeric(d["labs_albumin_last_preop7d"], errors="coerce")
    d["alb"] = d["alb"].fillna(alb2)
    # CAR = CRP / (alb × 10) — SAP v1.9
    d["car"] = d["crp"] / (d["alb"] * 10.0)
    d.loc[d["crp"].isna() | d["alb"].isna() | (d["alb"] <= 0), "car"] = np.nan
    for c in COV_CONT + COV_BIN:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["proc_axis"] = d["proc_axis"].fillna("other_orthopedic").astype(str)
    d["ioh"] = (d["map65_min"] >= IOH_THR).astype(float)
    d.loc[d["map65_min"].isna(), "ioh"] = np.nan
    return d


def assign_pheno(flag: pd.Series, ioh: pd.Series) -> pd.Series:
    out = []
    for a, i in zip(flag, ioh):
        if pd.isna(a) or pd.isna(i):
            out.append(np.nan)
        else:
            out.append(
                {(0, 0): "G00", (1, 0): "G10", (0, 1): "G01", (1, 1): "G11"}[
                    (int(a), int(i))
                ]
            )
    return pd.Series(out, index=flag.index)


def analytic_frame(d: pd.DataFrame) -> pd.DataFrame:
    use = ["icu", "phenotype", "proc_axis"]
    for c in COV_CONT + COV_BIN:
        if d[c].nunique(dropna=True) >= 2:
            use.append(c)
    out = d.dropna(subset=use).copy()
    out["phenotype"] = pd.Categorical(out["phenotype"], categories=PHENOS, ordered=True)
    out = out.loc[out["phenotype"].isin(PHENOS)].copy()
    out.attrs["cov_cont"] = [c for c in COV_CONT if c in use]
    out.attrs["cov_bin"] = [c for c in COV_BIN if c in use]
    return out


def formula_m3(df: pd.DataFrame) -> str:
    parts = ["C(phenotype, Treatment(reference='G00'))"]
    parts += df.attrs.get("cov_cont", COV_CONT)
    parts += df.attrs.get("cov_bin", COV_BIN)
    if df["proc_axis"].nunique() >= 2:
        parts.append("C(proc_axis, Treatment(reference='other_orthopedic'))")
    return "icu ~ " + " + ".join(parts)


def fit_logit(df: pd.DataFrame):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            return smf.logit(formula_m3(df), data=df).fit(
                disp=False, method="lbfgs", maxiter=500
            )
        except Exception:
            return smf.logit(formula_m3(df), data=df).fit(disp=False)


def gcomp_risks(df: pd.DataFrame, res) -> dict[str, float]:
    cats = list(df["phenotype"].cat.categories)
    risks = {}
    for g in PHENOS:
        if g not in cats:
            risks[g] = np.nan
            continue
        t = df.copy()
        t["phenotype"] = g
        t["phenotype"] = pd.Categorical(t["phenotype"], categories=cats)
        try:
            risks[g] = float(np.mean(res.predict(t)))
        except Exception:
            risks[g] = np.nan
    return risks


def effects_from_risks(R):
    rd = {g: R[g] - R["G00"] for g in ("G10", "G01", "G11")}
    reri = R["G11"] - R["G10"] - R["G01"] + R["G00"]
    return {
        "R": R,
        "RD": rd,
        "RERI": reri,
        "AP": (reri / rd["G11"]) if rd["G11"] not in (0, np.nan) else np.nan,
    }


def crude_table(df, labels):
    rows = []
    for g in PHENOS:
        sub = df.loc[df["phenotype"] == g]
        n = len(sub)
        ev = int(sub["icu"].sum()) if n else 0
        rows.append(
            {
                "phenotype": g,
                "label": labels[g],
                "n": n,
                "events": ev,
                "crude_risk": ev / n if n else np.nan,
            }
        )
    return pd.DataFrame(rows)


def point_estimate(df):
    res = fit_logit(df)
    R = gcomp_risks(df, res)
    eff = effects_from_risks(R)
    ors = {}
    for g in ("G10", "G01", "G11"):
        term = f"C(phenotype, Treatment(reference='G00'))[T.{g}]"
        if term in res.params.index:
            b = float(res.params[term])
            lo, hi = res.conf_int().loc[term].astype(float).tolist()
            ors[g] = {
                "OR": float(np.exp(b)),
                "OR_lo": float(np.exp(lo)),
                "OR_hi": float(np.exp(hi)),
                "p": float(res.pvalues[term]),
            }
    eff["model_OR"] = ors
    eff["n"] = int(len(df))
    eff["events"] = int(df["icu"].sum())
    return eff


def bootstrap_ci(df, n_boot=N_BOOT):
    point = point_estimate(df)
    store = {
        "R": {g: [] for g in PHENOS},
        "RD": {g: [] for g in ("G10", "G01", "G11")},
        "RERI": [],
        "AP": [],
    }
    n = len(df)
    ok = 0
    for b in range(n_boot):
        idx = RNG.integers(0, n, size=n)
        boot = df.iloc[idx].copy()
        if boot["phenotype"].nunique() < 4 or boot["icu"].nunique() < 2:
            continue
        boot["phenotype"] = pd.Categorical(boot["phenotype"], categories=PHENOS, ordered=True)
        boot.attrs["cov_cont"] = df.attrs.get("cov_cont", COV_CONT)
        boot.attrs["cov_bin"] = df.attrs.get("cov_bin", COV_BIN)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = fit_logit(boot)
                R = gcomp_risks(boot, res)
                if any(np.isnan(R[g]) for g in PHENOS):
                    continue
                eff = effects_from_risks(R)
            for g in PHENOS:
                store["R"][g].append(eff["R"][g])
            for g in ("G10", "G01", "G11"):
                store["RD"][g].append(eff["RD"][g])
            store["RERI"].append(eff["RERI"])
            store["AP"].append(eff["AP"])
            ok += 1
        except Exception:
            continue
        if (b + 1) % 100 == 0:
            print(f"  bootstrap {b+1}/{n_boot} (ok={ok})", flush=True)

    def pct(arr):
        a = np.asarray(arr, float)
        a = a[np.isfinite(a)]
        if len(a) < 50:
            return np.nan, np.nan
        return float(np.quantile(a, 0.025)), float(np.quantile(a, 0.975))

    out = {"point": point, "n_boot_ok": ok, "n_boot": n_boot}
    out["R_CI"] = {g: pct(store["R"][g]) for g in PHENOS}
    out["RD_CI"] = {g: pct(store["RD"][g]) for g in ("G10", "G01", "G11")}
    out["RERI_CI"] = pct(store["RERI"])
    out["AP_CI"] = pct(store["AP"])
    reri0 = point["RERI"]
    arr = np.asarray(store["RERI"], float)
    arr = arr[np.isfinite(arr)]
    if len(arr):
        if reri0 >= 0:
            out["RERI_p_boot"] = float(2 * min(np.mean(arr <= 0), np.mean(arr >= 0)))
        else:
            out["RERI_p_boot"] = float(2 * min(np.mean(arr >= 0), np.mean(arr <= 0)))
        out["RERI_p_boot"] = min(out["RERI_p_boot"], 1.0)
    else:
        out["RERI_p_boot"] = np.nan
    return out


def step1_for_cut(raw: pd.DataFrame, flag: pd.Series, cut_name: str, cut_val: float, labels):
    d = raw.copy()
    d["phenotype"] = assign_pheno(flag, d["ioh"])
    full = d.dropna(subset=["phenotype", "icu"])
    crude = crude_table(full, labels)
    df = analytic_frame(d)
    if df["phenotype"].nunique() < 4:
        return None
    pt = point_estimate(df)
    Rf = {r["phenotype"]: r["crude_risk"] for _, r in crude.iterrows()}
    return {
        "cut_name": cut_name,
        "cut_value": cut_val,
        "flag_prev": float(flag.mean()),
        "flag_nonmiss": int(flag.notna().sum()),
        "crude": crude.to_dict(orient="records"),
        "G11_events": int(crude.loc[crude.phenotype == "G11", "events"].iloc[0]),
        "crude_RERI_pp": 100 * (Rf["G11"] - Rf["G10"] - Rf["G01"] + Rf["G00"]),
        "M3_n": pt["n"],
        "M3_events": pt["events"],
        "std_R": pt["R"],
        "std_RD_pp": {k: 100 * v for k, v in pt["RD"].items()},
        "std_RERI_pp": 100 * pt["RERI"],
        "model_OR": pt["model_OR"],
        "OR_G11": pt["model_OR"]["G11"]["OR"],
    }


def write_docx(res, labels, path, cut_name, cut_val):
    boot = res["boot"]
    point = boot["point"]
    crude = res["crude"]
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Inches(11)
    sec.page_height = Inches(8.5)
    sec.left_margin = Cm(1.5)
    sec.right_margin = Cm(1.5)
    t = doc.add_paragraph()
    run = t.add_run(
        f"Table. Act B — CAR ({cut_name}, cut={cut_val:.6g}) × cumulative MAP <65 ≥30 min "
        "and ICU (INSPIRE OS≥65; Model 3 Clinical without CRP/albumin)."
    )
    set_run_font(run, size=11, bold=True)
    headers = [
        "Phenotype",
        "N",
        "ICU",
        "Crude %",
        "Std risk %",
        "RD vs Neither (pp)",
        "OR (95% CI)",
    ]
    table = doc.add_table(rows=1 + 4 + 2, cols=len(headers))
    for j, h in enumerate(headers):
        write_cell(table.rows[0].cells[j], h, bold=True)
    for i, g in enumerate(PHENOS):
        cr = crude.loc[crude["phenotype"] == g].iloc[0]
        R = point["R"][g]
        Rlo, Rhi = boot["R_CI"][g]
        if g == "G00":
            rd_txt, or_txt = "0 (ref)", "1.00 (ref)"
        else:
            rd, lo, hi = point["RD"][g], *boot["RD_CI"][g]
            rd_txt = fmt_ci_pp(rd, lo, hi) if np.isfinite(lo) else f"{100*rd:.2f}"
            o = point["model_OR"][g]
            or_txt = f"{o['OR']:.2f} ({o['OR_lo']:.2f}–{o['OR_hi']:.2f})"
        std_txt = (
            f"{fmt_pct(R)} ({fmt_pct(Rlo)}–{fmt_pct(Rhi)})"
            if np.isfinite(Rlo)
            else fmt_pct(R)
        )
        vals = [
            labels[g],
            str(int(cr["n"])),
            str(int(cr["events"])),
            fmt_pct(cr["crude_risk"]),
            std_txt,
            rd_txt,
            or_txt,
        ]
        for j, v in enumerate(vals):
            write_cell(table.rows[i + 1].cells[j], v, align="left" if j == 0 else "center")
    reri, rlo, rhi = point["RERI"], *boot["RERI_CI"]
    write_cell(table.rows[5].cells[0], "RERI", bold=True, align="left")
    write_cell(
        table.rows[5].cells[1],
        fmt_ci_pp(reri, rlo, rhi) + f"; P={fmt_p(boot.get('RERI_p_boot'))}",
        align="left",
    )
    for j in range(2, len(headers)):
        write_cell(table.rows[5].cells[j], "")
    ap, aplo, aphi = point["AP"], *boot["AP_CI"]
    write_cell(table.rows[6].cells[0], "AP", bold=True, align="left")
    write_cell(
        table.rows[6].cells[1],
        f"{ap:.2f} ({aplo:.2f} to {aphi:.2f})" if np.isfinite(aplo) else f"{ap:.2f}",
        align="left",
    )
    for j in range(2, len(headers)):
        write_cell(table.rows[6].cells[j], "")
    apply_three_line(table)
    note = doc.add_paragraph()
    gate = res["gate"]
    run = note.add_run(
        "CAR = CRP (mg/dL) / (albumin [g/dL] × 10), aligned with project CAR SAP v1.9. "
        "Model 3 Clinical excludes CRP and albumin. "
        f"Bootstrap {boot['n_boot_ok']}/{N_BOOT}. "
        f"N={res['n']}, ICU={res['events']}. "
        f"Gate: G00 ICU={gate['G00_events']}, G11 ICU={gate['G11_events']}, "
        f"RD half-width={gate['RD11_halfwidth_pp']} pp."
    )
    set_run_font(run, size=8)
    doc.save(path)


def _safe(o):
    if isinstance(o, dict):
        return {k: _safe(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_safe(x) for x in o]
    if isinstance(o, pd.DataFrame):
        return o.to_dict(orient="records")
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer, int)):
        return int(o)
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    return o


def main():
    OUT_PROJ.mkdir(parents=True, exist_ok=True)
    DESK.mkdir(parents=True, exist_ok=True)
    raw = load_base()
    car = raw["car"]
    print(
        f"CAR nonmiss {car.notna().sum()}/{len(raw)} ({100*car.notna().mean():.1f}%) "
        f"median={car.median():.6g} IQR=[{car.quantile(0.25):.6g}, {car.quantile(0.75):.6g}]",
        flush=True,
    )

    # cuts on non-missing CAR
    med = float(car.median())
    q3 = float(car.quantile(0.75))
    # tertile: top tertile vs lower two
    t33 = float(car.quantile(1 / 3))
    t67 = float(car.quantile(2 / 3))

    cuts = {
        "ge_median": (med, (car >= med).astype(float).mask(car.isna())),
        "ge_Q3": (q3, (car >= q3).astype(float).mask(car.isna())),
        "T3_vs_T1T2": (t67, (car >= t67).astype(float).mask(car.isna())),
    }

    screen = []
    for name, (val, flag) in cuts.items():
        labels = {
            "G00": "Neither (ref)",
            "G10": f"High CAR only ({name})",
            "G01": "IOH ≥30 only",
            "G11": f"Both (high CAR + IOH≥30)",
        }
        print(f"\n--- screen {name} cut={val:.6g} prev={100*flag.mean():.1f}% ---", flush=True)
        s = step1_for_cut(raw, flag, name, val, labels)
        if s is None:
            continue
        screen.append(s)
        print(
            f"  G11 ICU={s['G11_events']} crudeRERI={s['crude_RERI_pp']:+.2f}pp "
            f"M3 RERI={s['std_RERI_pp']:+.2f}pp OR_G11={s['OR_G11']:.2f} "
            f"RD11={s['std_RD_pp']['G11']:.2f}pp",
            flush=True,
        )
        for g in ("G10", "G01", "G11"):
            o = s["model_OR"][g]
            print(
                f"    OR {g}: {o['OR']:.2f} ({o['OR_lo']:.2f}–{o['OR_hi']:.2f}) p={fmt_p(o['p'])}",
                flush=True,
            )

    # pick primary: prefer T3 (more selective / flashier) if G11>=50, else median
    by_name = {s["cut_name"]: s for s in screen}
    if "T3_vs_T1T2" in by_name and by_name["T3_vs_T1T2"]["G11_events"] >= 50:
        primary = "T3_vs_T1T2"
    elif "ge_Q3" in by_name and by_name["ge_Q3"]["G11_events"] >= 50:
        primary = "ge_Q3"
    else:
        primary = "ge_median"
    print(f"\n=== PRIMARY CUT for full bootstrap: {primary} ===", flush=True)

    cut_val, flag = cuts[primary]
    labels = {
        "G00": "Neither (ref)",
        "G10": "High CAR only",
        "G01": "IOH ≥30 min only",
        "G11": "Both (high CAR + IOH≥30)",
    }
    d = raw.copy()
    d["phenotype"] = assign_pheno(flag, d["ioh"])
    crude_full = crude_table(d.dropna(subset=["phenotype", "icu"]), labels)
    print(crude_full.to_string(index=False), flush=True)
    df = analytic_frame(d)
    print(f"M3 CC n={len(df)} events={int(df['icu'].sum())}", flush=True)
    print(f"Fitting M3 + bootstrap B={N_BOOT} …", flush=True)
    boot = bootstrap_ci(df, N_BOOT)
    point = boot["point"]
    g00e = int(crude_full.loc[crude_full.phenotype == "G00", "events"].iloc[0])
    g11e = int(crude_full.loc[crude_full.phenotype == "G11", "events"].iloc[0])
    half = (boot["RD_CI"]["G11"][1] - boot["RD_CI"]["G11"][0]) / 2
    gate = {
        "gate_A_G00_icu_ge50": g00e >= 50,
        "gate_A_G11_icu_ge100": g11e >= 100,
        "gate_A_RD_halfwidth_pp_lt5": bool(np.isfinite(half) and 100 * half < 5),
        "G00_events": g00e,
        "G11_events": g11e,
        "RD11_halfwidth_pp": float(100 * half) if np.isfinite(half) else None,
    }
    res = {
        "crude": crude_full,
        "boot": boot,
        "gate": gate,
        "n": point["n"],
        "events": point["events"],
        "ioh_thr": IOH_THR,
    }

    stem = f"ActB_CAR_{primary}_IOH30"
    write_docx(res, labels, OUT_PROJ / f"{stem}_RD_RERI.docx", primary, cut_val)
    # csv
    rows = []
    for g in PHENOS:
        cr = crude_full.loc[crude_full.phenotype == g].iloc[0]
        row = {
            "phenotype": g,
            "label": labels[g],
            "n": int(cr["n"]),
            "events": int(cr["events"]),
            "crude_risk": cr["crude_risk"],
            "std_risk": point["R"][g],
            "std_lo": boot["R_CI"][g][0],
            "std_hi": boot["R_CI"][g][1],
        }
        if g != "G00":
            row["RD"] = point["RD"][g]
            row["RD_lo"], row["RD_hi"] = boot["RD_CI"][g]
            o = point["model_OR"][g]
            row.update({f"OR_{k}": o[k] for k in ("OR", "OR_lo", "OR_hi", "p")})
        rows.append(row)
    rows.append(
        {
            "phenotype": "RERI",
            "std_risk": point["RERI"],
            "std_lo": boot["RERI_CI"][0],
            "std_hi": boot["RERI_CI"][1],
            "RD": point["AP"],
            "RD_lo": boot["AP_CI"][0],
            "RD_hi": boot["AP_CI"][1],
            "OR_p": boot["RERI_p_boot"],
        }
    )
    pd.DataFrame(rows).to_csv(OUT_PROJ / f"{stem}_RD_RERI.csv", index=False, encoding="utf-8-sig")

    summary = {
        "CAR_formula": "CRP(mg/dL)/(albumin[g/dL]*10)",
        "CAR_distribution": {
            "nonmiss": int(car.notna().sum()),
            "median": med,
            "Q1": float(car.quantile(0.25)),
            "Q3": q3,
            "T1_cut": t33,
            "T3_cut": t67,
        },
        "screen_step1": screen,
        "primary_cut": primary,
        "primary_cut_value": cut_val,
        "n": res["n"],
        "events": res["events"],
        "R": point["R"],
        "RD": point["RD"],
        "RD_CI": boot["RD_CI"],
        "RERI": point["RERI"],
        "RERI_CI": boot["RERI_CI"],
        "RERI_p_boot": boot["RERI_p_boot"],
        "AP": point["AP"],
        "model_OR": point["model_OR"],
        "gate": gate,
        "n_boot_ok": boot["n_boot_ok"],
        "vs_CRP_note": (
            "Compare to ActB CRP>=1: if CAR RERI still null but OR_G11 larger / flashier index, "
            "prefer joint-phenotype narrative (Both highest) citing Turan 2023 additive framing."
        ),
    }
    (OUT_PROJ / "ActB_CAR_summary.json").write_text(
        json.dumps(_safe(summary), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT_PROJ / "ActB_CAR_RESULT_BRIEF.md").write_text(
        f"# 幕 B · CAR ({primary}) × IOH≥30 → ICU\n\n"
        f"- CAR = CRP/(alb×10); primary cut `{primary}` = {cut_val:.6g}\n"
        f"- M3 N={res['n']}, ICU={res['events']}; boot ok {boot['n_boot_ok']}/{N_BOOT}\n"
        f"- Std risks: "
        + ", ".join(f"{g}={100*point['R'][g]:.1f}%" for g in PHENOS)
        + "\n"
        f"- **RD(G11−G00)** = {100*point['RD']['G11']:.2f} pp "
        f"({100*boot['RD_CI']['G11'][0]:.2f} to {100*boot['RD_CI']['G11'][1]:.2f})\n"
        f"- **RERI** = {100*point['RERI']:.2f} pp "
        f"({100*boot['RERI_CI'][0]:.2f} to {100*boot['RERI_CI'][1]:.2f}), "
        f"P={boot['RERI_p_boot']}\n"
        f"- OR G11 = {point['model_OR']['G11']['OR']:.2f} "
        f"({point['model_OR']['G11']['OR_lo']:.2f}–{point['model_OR']['G11']['OR_hi']:.2f})\n"
        f"- Gate: {gate}\n",
        encoding="utf-8",
    )

    for f in OUT_PROJ.iterdir():
        if f.is_file():
            shutil.copy2(f, DESK / f.name)

    print("\n=== PRIMARY RESULT ===", flush=True)
    print(json.dumps(_safe({k: summary[k] for k in [
        "primary_cut", "primary_cut_value", "n", "events", "R", "RD", "RD_CI",
        "RERI", "RERI_CI", "RERI_p_boot", "model_OR", "gate", "n_boot_ok"
    ]}), indent=2, ensure_ascii=False), flush=True)
    print("DESK", DESK, flush=True)


if __name__ == "__main__":
    main()
