# -*- coding: utf-8 -*-
"""Table 2 — CAR×IOH phenotype → ICU (SAP v3.0 FROZEN).

Lin CAR (CRP/albumin), locked T3 cut ≥0.0738.
All n/events/estimates on Dcc only (same cohort as Table 1).
SCI three-line Word style aligned with Table 1.
"""
from __future__ import annotations

import json
import shutil
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

ROOT = Path(r"e:\DS-智能体\222")
OUT_PROJ = ROOT / "results" / "car_ioh_icu_os65" / "02_Table02_CAR_IOH_phenotype"
DESK = Path(r"E:\桌面") / "222" / "02_Table02_CAR_IOH_phenotype"

CAR_CUT = 0.07380952380952381
IOH_THR = 30.0
PHENOS = ["G00", "G10", "G01", "G11"]
LABELS = {
    "G00": "Neither",
    "G10": "High CAR only",
    "G01": "IOH ≥30 min only",
    "G11": "Both",
}
COV_CONT = ["age", "asa", "op_duration_min", "creatinine", "bmi", "hb", "glucose"]
COV_BIN = ["female", "emop", "general_anes"]
N_BOOT = 1000
RNG = np.random.default_rng(20261014)


def set_run_font(run, size=10.5, bold=False):
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


def write_cell(cell, text, bold=False, align="left", size=10.5):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = (
        WD_ALIGN_PARAGRAPH.CENTER if align == "center" else WD_ALIGN_PARAGRAPH.LEFT
    )
    run = p.add_run(str(text))
    set_run_font(run, size=size, bold=bold)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.0


def fmt_pct(x, digits=1):
    return f"{100 * x:.{digits}f}"


def fmt_pp(est, lo, hi, digits=2):
    return f"{100 * est:.{digits}f} ({100 * lo:.{digits}f} to {100 * hi:.{digits}f})"


def fmt_or(o):
    return f"{o['OR']:.2f} ({o['OR_lo']:.2f} to {o['OR_hi']:.2f})"


def fmt_p(p):
    if p is None or (isinstance(p, float) and (np.isnan(p) or not np.isfinite(p))):
        return "—"
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}"


def load_dcc() -> pd.DataFrame:
    """Prefer Table 1 Dcc analytic file for exact alignment."""
    path = (
        ROOT
        / "results"
        / "car_ioh_icu_os65"
        / "01_Table01_baseline"
        / "Table01_analytic_cohort_Dcc.csv"
    )
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
    # Phenotypes taken from Table 1 Dcc (locked cut applied there); do not re-threshold
    # from CSV-rounded CAR floats.
    return out


def formula_m3() -> str:
    parts = (
        ["C(phenotype, Treatment(reference='G00'))"]
        + COV_CONT
        + COV_BIN
        + ["C(proc_axis, Treatment(reference='other_orthopedic'))"]
    )
    return "icu ~ " + " + ".join(parts)


def fit_logit(df: pd.DataFrame):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            return smf.logit(formula_m3(), data=df).fit(
                disp=False, method="lbfgs", maxiter=500
            )
        except Exception:
            return smf.logit(formula_m3(), data=df).fit(disp=False)


def gcomp_risks(df: pd.DataFrame, res) -> dict[str, float]:
    cats = list(PHENOS)
    risks = {}
    for g in PHENOS:
        t = df.copy()
        t["phenotype"] = g
        t["phenotype"] = pd.Categorical(t["phenotype"], categories=cats)
        risks[g] = float(np.mean(res.predict(t)))
    return risks


def effects_from_risks(R):
    rd = {g: R[g] - R["G00"] for g in ("G10", "G01", "G11")}
    # IC_RD (= additive interaction on risk scale; reported as RERI in prior ActB code)
    ic_rd = R["G11"] - R["G10"] - R["G01"] + R["G00"]
    return {"R": R, "RD": rd, "IC_RD": ic_rd}


def crude_rows(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for g in PHENOS:
        sub = df.loc[df["phenotype"] == g]
        n = len(sub)
        ev = int(sub["icu"].sum())
        rows.append(
            {
                "phenotype": g,
                "label": LABELS[g],
                "n": n,
                "events": ev,
                "crude_risk": ev / n if n else np.nan,
            }
        )
    return pd.DataFrame(rows)


def point_estimate(df: pd.DataFrame):
    res = fit_logit(df)
    R = gcomp_risks(df, res)
    eff = effects_from_risks(R)
    ors = {}
    for g in ("G10", "G01", "G11"):
        term = f"C(phenotype, Treatment(reference='G00'))[T.{g}]"
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


def boot_p_two_sided(arr, point):
    a = np.asarray(arr, float)
    a = a[np.isfinite(a)]
    if len(a) == 0:
        return np.nan
    if point >= 0:
        p = float(2 * min(np.mean(a <= 0), np.mean(a >= 0)))
    else:
        p = float(2 * min(np.mean(a >= 0), np.mean(a <= 0)))
    return min(max(p, 0.0), 1.0)


def bootstrap_ci(df: pd.DataFrame, n_boot=N_BOOT):
    point = point_estimate(df)
    store = {
        "R": {g: [] for g in PHENOS},
        "RD": {g: [] for g in ("G10", "G01", "G11")},
        "IC_RD": [],
    }
    fail_log = []
    n = len(df)
    ok = 0
    for b in range(n_boot):
        idx = RNG.integers(0, n, size=n)
        boot = df.iloc[idx].copy()
        if boot["phenotype"].nunique() < 4 or boot["icu"].nunique() < 2:
            fail_log.append({"b": b + 1, "reason": "degenerate_strata"})
            continue
        boot["phenotype"] = pd.Categorical(
            boot["phenotype"], categories=PHENOS, ordered=True
        )
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = fit_logit(boot)
                R = gcomp_risks(boot, res)
                if any(not np.isfinite(R[g]) for g in PHENOS):
                    fail_log.append({"b": b + 1, "reason": "nonfinite_risk"})
                    continue
                eff = effects_from_risks(R)
            for g in PHENOS:
                store["R"][g].append(eff["R"][g])
            for g in ("G10", "G01", "G11"):
                store["RD"][g].append(eff["RD"][g])
            store["IC_RD"].append(eff["IC_RD"])
            ok += 1
        except Exception as e:
            fail_log.append({"b": b + 1, "reason": type(e).__name__})
            continue
        if (b + 1) % 100 == 0:
            print(f"  bootstrap {b + 1}/{n_boot} ok={ok} fail={len(fail_log)}", flush=True)

    def pct(arr):
        a = np.asarray(arr, float)
        a = a[np.isfinite(a)]
        if len(a) < 50:
            return np.nan, np.nan
        return float(np.quantile(a, 0.025)), float(np.quantile(a, 0.975))

    out = {
        "point": point,
        "n_boot_ok": ok,
        "n_boot": n_boot,
        "n_boot_fail": len(fail_log),
        "fail_log": fail_log[:50],  # cap stored failures
        "fail_reason_counts": (
            pd.Series([f["reason"] for f in fail_log]).value_counts().to_dict()
            if fail_log
            else {}
        ),
    }
    out["R_CI"] = {g: pct(store["R"][g]) for g in PHENOS}
    out["RD_CI"] = {g: pct(store["RD"][g]) for g in ("G10", "G01", "G11")}
    out["IC_RD_CI"] = pct(store["IC_RD"])
    out["RD_p"] = {
        g: boot_p_two_sided(store["RD"][g], point["RD"][g]) for g in ("G10", "G01", "G11")
    }
    out["IC_RD_p"] = boot_p_two_sided(store["IC_RD"], point["IC_RD"])
    return out


def build_display(crude: pd.DataFrame, boot: dict) -> pd.DataFrame:
    point = boot["point"]
    rows = []
    for g in PHENOS:
        cr = crude.loc[crude["phenotype"] == g].iloc[0]
        R = point["R"][g]
        Rlo, Rhi = boot["R_CI"][g]
        if g == "G00":
            rd_txt, or_txt, p_txt, role = "0 (reference)", "1.00 (reference)", "—", "Reference"
        else:
            rd = point["RD"][g]
            lo, hi = boot["RD_CI"][g]
            rd_txt = fmt_pp(rd, lo, hi)
            or_txt = fmt_or(point["model_OR"][g])
            p_txt = fmt_p(point["model_OR"][g]["p"])
            role = "Primary contrast" if g == "G11" else "Secondary contrast"
        rows.append(
            {
                "Phenotype": LABELS[g],
                "Role": role,
                "n": int(cr["n"]),
                "Events": int(cr["events"]),
                "Crude risk, %": fmt_pct(cr["crude_risk"]),
                "Standardized risk, % (95% CI)": (
                    f"{fmt_pct(R)} ({fmt_pct(Rlo)} to {fmt_pct(Rhi)})"
                    if np.isfinite(Rlo)
                    else fmt_pct(R)
                ),
                "RD vs Neither, pp (95% CI)": rd_txt,
                "Adjusted OR (95% CI)": or_txt,
                "P value": p_txt,
                "RD_boot_P": (
                    "—" if g == "G00" else fmt_p(boot["RD_p"][g])
                ),
            }
        )
    return pd.DataFrame(rows)


def write_docx(show: pd.DataFrame, boot: dict, crude: pd.DataFrame, path: Path):
    point = boot["point"]
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Inches(11)
    sec.page_height = Inches(8.5)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Inches(0.55))

    t = doc.add_paragraph()
    run = t.add_run(
        "Table 2. Association of the CAR×IOH phenotype with postoperative ICU admission."
    )
    set_run_font(run, size=12, bold=True)
    t.paragraph_format.space_after = Pt(6)

    # Display columns (omit Role / RD_boot_P from main grid; put in footnote)
    cols = [
        "Phenotype",
        "n",
        "Events",
        "Crude risk, %",
        "Standardized risk, % (95% CI)",
        "RD vs Neither, pp (95% CI)",
        "Adjusted OR (95% CI)",
        "P value",
    ]
    table = doc.add_table(rows=1 + len(show), cols=len(cols))
    for j, h in enumerate(cols):
        write_cell(
            table.rows[0].cells[j],
            h,
            bold=True,
            align="center" if j > 0 else "left",
        )
    for i, r in show.iterrows():
        bold_row = r["Phenotype"] == "Both"
        for j, h in enumerate(cols):
            write_cell(
                table.rows[i + 1].cells[j],
                r[h],
                bold=bold_row and j == 0,
                align="center" if j > 0 else "left",
            )
    apply_three_line(table)

    ic = point["IC_RD"]
    ic_lo, ic_hi = boot["IC_RD_CI"]
    note = doc.add_paragraph()
    note.paragraph_format.space_before = Pt(6)
    footnote = (
        "Values are n, events, and percentages. "
        "Standardized risks and risk differences (RD) were obtained by Model 3 Clinical "
        "g-computation with bootstrap percentile 95% confidence intervals "
        f"(B={boot['n_boot']}; successful resamples {boot['n_boot_ok']}/{boot['n_boot']}). "
        "Adjusted odds ratios (OR) are from the same Model 3 logistic regression "
        "(age, sex, ASA, emergency surgery, operation duration, procedure axis, anesthesia type, "
        "creatinine, body mass index, hemoglobin, and glucose); C-reactive protein, albumin, and "
        "CAR were not included. "
        f"The primary contrast is the standardized RD for Both versus Neither "
        f"[{fmt_pp(point['RD']['G11'], *boot['RD_CI']['G11'])}; bootstrap P={fmt_p(boot['RD_p']['G11'])}]. "
        "RDs for High CAR only and IOH ≥30 min only versus Neither are secondary contrasts. "
        f"Additive interaction on the risk-difference scale (IC_RD) = "
        f"{fmt_pp(ic, ic_lo, ic_hi)}; bootstrap P={fmt_p(boot['IC_RD_p'])} "
        "(reported but not used as the primary abstract conclusion). "
        f"CAR = C-reactive protein (mg/dL) / albumin (g/dL); high CAR = uppermost tertile "
        f"(CAR ≥ {CAR_CUT:.4f}, cut-off locked). "
        f"IOH = cumulative MAP <65 mmHg ≥{IOH_THR:.0f} min. "
        f"Complete-case primary cohort n={point['n']}, ICU events={point['events']} "
        f"(phenotype n: Neither {int(crude.loc[crude.phenotype=='G00','n'].iloc[0])}, "
        f"High CAR only {int(crude.loc[crude.phenotype=='G10','n'].iloc[0])}, "
        f"IOH ≥30 only {int(crude.loc[crude.phenotype=='G01','n'].iloc[0])}, "
        f"Both {int(crude.loc[crude.phenotype=='G11','n'].iloc[0])}). "
        "Abbreviations: ASA, American Society of Anesthesiologists; CAR, C-reactive "
        "protein-to-albumin ratio; CI, confidence interval; IC_RD, interaction contrast on the "
        "risk-difference scale; ICU, intensive care unit; IOH, intraoperative hypotension; "
        "MAP, mean arterial pressure; OR, odds ratio; pp, percentage points; RD, risk difference."
    )
    run = note.add_run(footnote)
    set_run_font(run, size=10.5, bold=False)
    doc.save(path)


def _safe(o):
    if isinstance(o, dict):
        return {k: _safe(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_safe(x) for x in o]
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

    df = load_dcc()
    crude = crude_rows(df)
    print("Dcc crude (must sum n=3936, events=407):", flush=True)
    print(crude.to_string(index=False), flush=True)
    assert int(crude["n"].sum()) == len(df)
    assert int(crude["events"].sum()) == int(df["icu"].sum())

    print(f"\nFitting Model 3 + bootstrap B={N_BOOT} …", flush=True)
    boot = bootstrap_ci(df, N_BOOT)
    point = boot["point"]
    show = build_display(crude, boot)

    g00e = int(crude.loc[crude.phenotype == "G00", "events"].iloc[0])
    g11e = int(crude.loc[crude.phenotype == "G11", "events"].iloc[0])
    half = (boot["RD_CI"]["G11"][1] - boot["RD_CI"]["G11"][0]) / 2
    gate = {
        "P1_G00_icu_ge50": g00e >= 50,
        "P1_G11_icu_ge100": g11e >= 100,
        "P2_RD11_CI_excludes_0": bool(
            np.isfinite(boot["RD_CI"]["G11"][0]) and boot["RD_CI"]["G11"][0] > 0
        ),
        "G00_events_Dcc": g00e,
        "G11_events_Dcc": g11e,
        "RD11_halfwidth_pp": float(100 * half) if np.isfinite(half) else None,
    }

    csv_name = "Table02_CAR_IOH_ICU_phenotype.csv"
    docx_name = "Table02_CAR_IOH_ICU_phenotype.docx"
    meta_name = "Table02_meta.json"
    brief_name = "Table02_BRIEF.md"
    boot_log_name = "Table02_bootstrap_fail_log.json"

    show_out = show[
        [
            "Phenotype",
            "Role",
            "n",
            "Events",
            "Crude risk, %",
            "Standardized risk, % (95% CI)",
            "RD vs Neither, pp (95% CI)",
            "Adjusted OR (95% CI)",
            "P value",
            "RD_boot_P",
        ]
    ]
    show_out.to_csv(OUT_PROJ / csv_name, index=False, encoding="utf-8-sig")
    write_docx(show, boot, crude, OUT_PROJ / docx_name)

    meta = {
        "car_formula": "CRP(mg/dL)/albumin(g/dL) [Lin]",
        "car_cut_locked": CAR_CUT,
        "ioh_threshold_min": IOH_THR,
        "n_dcc": point["n"],
        "icu_events": point["events"],
        "crude": crude.to_dict(orient="records"),
        "std_risk": point["R"],
        "RD": point["RD"],
        "RD_CI": boot["RD_CI"],
        "RD_boot_P": boot["RD_p"],
        "IC_RD": point["IC_RD"],
        "IC_RD_CI": boot["IC_RD_CI"],
        "IC_RD_p": boot["IC_RD_p"],
        "model_OR": point["model_OR"],
        "bootstrap": {
            "B": boot["n_boot"],
            "ok": boot["n_boot_ok"],
            "fail": boot["n_boot_fail"],
            "fail_reason_counts": boot["fail_reason_counts"],
        },
        "gate_Dcc": gate,
        "primary_contrast": "standardized RD (G11 − G00)",
        "outputs": [csv_name, docx_name, meta_name, brief_name, boot_log_name],
    }
    (OUT_PROJ / meta_name).write_text(
        json.dumps(_safe(meta), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT_PROJ / boot_log_name).write_text(
        json.dumps(
            {
                "n_fail": boot["n_boot_fail"],
                "reason_counts": boot["fail_reason_counts"],
                "first_failures": boot["fail_log"],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    brief = f"""# Table 2 — CAR×IOH → ICU（Dcc · Lin）

- 分析集：**Dcc n={point['n']}，ICU={point['events']}**（与 Table 1 / Figure 1 一致）
- CAR ≥ **{CAR_CUT:.4f}**（Lin；锁定）；IOH ≥30 min
- Bootstrap：{boot['n_boot_ok']}/{boot['n_boot']} 成功（失败 {boot['n_boot_fail']}）

## 主结果

| 表型 | n | ICU | 粗率% | 标准化风险% | RD vs Neither (pp) | OR |
|---|---:|---:|---:|---|---|---|
| Neither | {int(crude.loc[crude.phenotype=='G00','n'].iloc[0])} | {g00e} | {fmt_pct(crude.loc[crude.phenotype=='G00','crude_risk'].iloc[0])} | {fmt_pct(point['R']['G00'])} | Ref | Ref |
| High CAR only | {int(crude.loc[crude.phenotype=='G10','n'].iloc[0])} | {int(crude.loc[crude.phenotype=='G10','events'].iloc[0])} | {fmt_pct(crude.loc[crude.phenotype=='G10','crude_risk'].iloc[0])} | {fmt_pct(point['R']['G10'])} | {fmt_pp(point['RD']['G10'], *boot['RD_CI']['G10'])} | {fmt_or(point['model_OR']['G10'])} |
| IOH ≥30 only | {int(crude.loc[crude.phenotype=='G01','n'].iloc[0])} | {int(crude.loc[crude.phenotype=='G01','events'].iloc[0])} | {fmt_pct(crude.loc[crude.phenotype=='G01','crude_risk'].iloc[0])} | {fmt_pct(point['R']['G01'])} | {fmt_pp(point['RD']['G01'], *boot['RD_CI']['G01'])} | {fmt_or(point['model_OR']['G01'])} |
| **Both（主对比）** | {int(crude.loc[crude.phenotype=='G11','n'].iloc[0])} | {g11e} | {fmt_pct(crude.loc[crude.phenotype=='G11','crude_risk'].iloc[0])} | {fmt_pct(point['R']['G11'])} | **{fmt_pp(point['RD']['G11'], *boot['RD_CI']['G11'])}** | {fmt_or(point['model_OR']['G11'])} |

- IC_RD = {fmt_pp(point['IC_RD'], *boot['IC_RD_CI'])}；P={fmt_p(boot['IC_RD_p'])}
- Gate（Dcc）：G00 ICU≥50 → {gate['P1_G00_icu_ge50']}；G11 ICU≥100 → {gate['P1_G11_icu_ge100']}（G11 事件={g11e}）；RD CI 不跨 0 → {gate['P2_RD11_CI_excludes_0']}
"""
    (OUT_PROJ / brief_name).write_text(brief, encoding="utf-8")

    for f in OUT_PROJ.iterdir():
        if f.is_file():
            shutil.copy2(f, DESK / f.name)

    print(json.dumps(_safe(gate), indent=2))
    print("OUT", OUT_PROJ)
    print("DESK", DESK)


if __name__ == "__main__":
    main()
