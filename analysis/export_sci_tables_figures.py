# -*- coding: utf-8 -*-
"""SCI three-line tables + Figure 2–4 from patched rerun_out CSVs."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

ROOT = Path(__file__).resolve().parents[1] / "examples" / "aggregate_outputs"
OUT = Path(__file__).resolve().parents[1] / "examples" / "SCI_formatted"
FIG = OUT / "figures"
TAB = OUT / "tables"


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


def write_cell(cell, text, bold=False, align="center", size=10.5):
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = (
        WD_ALIGN_PARAGRAPH.CENTER
        if align == "center"
        else WD_ALIGN_PARAGRAPH.LEFT
        if align == "left"
        else WD_ALIGN_PARAGRAPH.RIGHT
    )
    run = p.add_run("" if text is None else str(text))
    set_run_font(run, size=size, bold=bold)
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)


def landscape(doc):
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Inches(11)
    section.page_height = Inches(8.5)
    for m in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(section, m, Inches(0.55))


def add_title(doc, text, size=12):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run_font(run, size=size, bold=True)
    p.paragraph_format.space_after = Pt(6)


def add_note(doc, text):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run_font(run, size=10.5, bold=False)
    p.paragraph_format.space_after = Pt(2)


def make_table_docx(path, title, headers, rows, notes, title_size=12, landscape_page=True):
    doc = Document()
    if landscape_page:
        landscape(doc)
    add_title(doc, title, size=title_size)
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for j, h in enumerate(headers):
        write_cell(table.rows[0].cells[j], h, bold=True)
    for row in rows:
        cells = table.add_row().cells
        for j, val in enumerate(row):
            write_cell(cells[j], val, align="left" if j == 0 else "center")
    apply_three_line(table)
    for n in notes:
        add_note(doc, n)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    print("Wrote", path, flush=True)


def fmt_or(o, lo, hi):
    if pd.isna(o):
        return "—"
    return f"{o:.2f} ({lo:.2f}, {hi:.2f})"


def fmt_rd(rd, lo, hi):
    if pd.isna(rd):
        return "—"
    return f"{rd:.2f} ({lo:.2f}, {hi:.2f})"


def fmt_p(p):
    if p is None or (isinstance(p, float) and not np.isfinite(p)) or pd.isna(p):
        return "—"
    if isinstance(p, str):
        return p
    p = float(p)
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def table1():
    df = pd.read_csv(ROOT / "07_table1.csv")
    first = df.columns[0]
    headers = ["Characteristic"] + [c.replace(" (n=", "\nn=") for c in df.columns[1:]]
    rows = [[str(r[first])] + [str(r[c]) for c in df.columns[1:]] for _, r in df.iterrows()]
    make_table_docx(
        TAB / "Table1_baseline_by_phenotype.docx",
        "Table 1 Baseline characteristics by CAR×IOH phenotype (final exposure, patched rerun).",
        headers,
        rows,
        [
            "Values are median (IQR) or n (%).",
            "Primary timing-compliant cohort n = 3,935 (406 ICU events). High CAR defined as CAR ≥ 0.0738095238 with boundary ties assigned to high CAR.",
            "Abbreviations: ASA, American Society of Anesthesiologists; BMI, body mass index; CAR, C-reactive protein-to-albumin ratio; ICU, intensive care unit; IOH, intraoperative hypotension; IQR, interquartile range; MAP, mean arterial pressure.",
        ],
        title_size=14,
    )


def table2():
    df = pd.read_csv(ROOT / "02_primary_table2.csv")
    ph = df.columns[0]
    rows = []
    for _, r in df.iterrows():
        rows.append(
            [
                r[ph],
                f"{int(r['n'])}",
                f"{int(r['events'])}",
                f"{r['crude_pct']:.1f}",
                r["std_risk_pct"],
                r["RD_vs_Neither_pp"],
                r["OR_Wald"],
            ]
        )
    # add IC_RD from boot summary if available
    sm = pd.read_csv(ROOT / "02_primary_boot_summary.csv")
    if "estimand" in sm.columns and (sm["estimand"] == "IC_RD").any():
        ic = sm.loc[sm["estimand"] == "IC_RD"].iloc[0]
        rows.append(
            [
                "IC_RD (additive interaction)",
                "—",
                "—",
                "—",
                "—",
                fmt_rd(ic["point"], ic["pct_lo"], ic["pct_hi"]),
                "—",
            ]
        )
    make_table_docx(
        TAB / "Table2_primary_phenotype_P3.docx",
        "Table 2 Standardised ICU risks and contrasts for CAR×IOH phenotypes (P3, final exposure).",
        [
            "Phenotype",
            "n",
            "Events",
            "Crude %",
            "Std. risk, % (95% CI)",
            "RD vs Neither, pp (95% CI)",
            "OR (95% CI)",
        ],
        rows,
        [
            "P3 covariates: age, ASA (linear), operation duration, creatinine, BMI, haemoglobin, glucose, sex, emergency surgery, general anaesthesia, procedure axis (reference = other orthopedic).",
            "Standardised risks and RDs: g-computation with percentile bootstrap (B = 1,000; seed = 20261108). OR columns are Wald intervals from the converged Newton–Raphson fit.",
            "Cohort: n = 3,935; 406 ICU events. High CAR = 1,276 (37 boundary ties).",
            "Abbreviations: CAR, C-reactive protein-to-albumin ratio; CI, confidence interval; ICU, intensive care unit; IOH, intraoperative hypotension; OR, odds ratio; pp, percentage points; RD, risk difference.",
        ],
        title_size=14,
    )


def table_s_exposure():
    df = pd.read_csv(ROOT / "03_primary_contrast_by_exposure_rule.csv")
    rows = []
    for _, r in df.iterrows():
        rows.append(
            [
                r["analysis"],
                f"{int(r['n'])}",
                f"{int(r['events'])}",
                f"{int(r['n_both'])}",
                fmt_rd(r["RD_pp"], r["RD_lo"], r["RD_hi"]),
                fmt_or(r["OR"], r["OR_boot_lo"], r["OR_boot_hi"]),
                fmt_p(r["p_boot"]),
            ]
        )
    make_table_docx(
        TAB / "TableS_exposure_rule_contrasts.docx",
        "Table S. Both vs Neither contrasts under alternative MAP <65 exposure rules.",
        ["Analysis", "n", "Events", "n Both", "RD, pp (95% CI)", "OR (95% CI)", "P value"],
        rows,
        [
            "First row reconciles the previous n = 3,936 cohort with published exposure using the converged Newton estimator (OR ≈ 2.40; RD ≈ 7.60 pp).",
            "FINAL is the pre-specified primary exposure. Percentile bootstrap B = 1,000.",
            "Abbreviations: CI, confidence interval; OR, odds ratio; pp, percentage points; RD, risk difference.",
        ],
    )


def table_s_monitoring():
    df = pd.read_csv(ROOT / "04_monitoring_contrasts.csv")
    rows = []
    for _, r in df.iterrows():
        rows.append(
            [
                r["analysis"],
                f"{int(r['n'])}",
                f"{int(r['events'])}",
                fmt_rd(r["RD_pp"], r["RD_lo"], r["RD_hi"]),
                fmt_or(r["OR"], r["OR_boot_lo"], r["OR_boot_hi"]),
                fmt_p(r["p_boot"]),
            ]
        )
    inter = pd.read_csv(ROOT / "04_interaction_tests.csv")
    notes = [
        "P3 + arterial monitoring is co-primary. Coverage ≥80% uses anaesthesia-window coverage.",
        "Abbreviations: CI, confidence interval; OR, odds ratio; pp, percentage points; RD, risk difference.",
    ]
    for _, r in inter.iterrows():
        notes.insert(-1, f"{r['test']}: statistic = {r['statistic']:.3g}; p = {fmt_p(r['p'])}" + (f"; {r['ci']}" if pd.notna(r.get("ci")) else ""))
    make_table_docx(
        TAB / "TableS_monitoring_and_interaction.docx",
        "Table S. Monitoring-adjusted contrasts and phenotype × arterial interaction tests.",
        ["Analysis", "n", "Events", "RD, pp (95% CI)", "OR (95% CI)", "P value"],
        rows,
        notes,
    )


def table_s_casemix_alt():
    c = pd.read_csv(ROOT / "05_casemix_sensitivity.csv")
    a = pd.read_csv(ROOT / "06_alternate_outcomes.csv")
    rows = []
    for _, r in c.iterrows():
        rows.append(
            [
                r["analysis"],
                f"{int(r['n'])}",
                f"{int(r['events'])}",
                fmt_rd(r["RD_pp"], r["RD_lo"], r["RD_hi"]),
                fmt_or(r["OR"], r["OR_boot_lo"], r["OR_boot_hi"]),
                fmt_p(r["p_boot"]),
            ]
        )
    for _, r in a.iterrows():
        rows.append(
            [
                r["analysis"],
                f"{int(r['n'])}",
                f"{int(r['events'])}",
                fmt_rd(r["RD_pp"], r["RD_lo"], r["RD_hi"]),
                fmt_or(r["OR"], r["OR_boot_lo"], r["OR_boot_hi"]),
                fmt_p(r["p_boot"]),
            ]
        )
    make_table_docx(
        TAB / "TableS_casemix_and_alternate_outcomes.docx",
        "Table S. Case-mix sensitivity and alternate outcomes (Both vs Neither).",
        ["Analysis", "n", "Events", "RD, pp (95% CI)", "OR (95% CI)", "P value"],
        rows,
        [
            "Case-mix rows add indication group and/or Charlson index, or restrict the cohort.",
            "Death rows include Firth and parsimonious specifications where listed.",
            "Abbreviations: CI, confidence interval; OR, odds ratio; pp, percentage points; RD, risk difference.",
        ],
    )


def table3_duration():
    df = pd.read_csv(ROOT / "08_table3_duration_models.csv")
    models = ["D0", "D1", "D2", "D3", "D4", "D5A"]
    terms = [
        ("dur_gt0_lt10", ">0 to <10 min"),
        ("dur_10_lt30", "10 to <30 min"),
        ("dur_ge30", "≥30 min"),
        ("dur_score", "p for trend"),
    ]
    # build wide: Characteristic | D0 OR | p | '' | D1 ... (too many cols) — use compact: model blocks as rows instead (Table 5 style) or multi-row
    # Compact SCI layout: one block per model
    headers = ["Model / category", "OR (95% CI)", "P value", "n / events (counts row)"]
    rows = []
    counts = df.loc[df["model"] == "counts"]
    if len(counts):
        rows.append(["Counts by duration category", "", "", ""])
        for _, r in counts.iterrows():
            rows.append([f"  {r['term']}", "—", "—", f"{int(r['n'])} / {int(r['events'])}"])
    for m in models:
        sub = df.loc[df["model"] == m]
        if not len(sub):
            continue
        rows.append([m, "", "", ""])
        for term, lab in terms:
            r = sub.loc[sub["term"] == term]
            if not len(r):
                continue
            r = r.iloc[0]
            if term == "dur_score":
                rows.append([f"  {lab}", "—", fmt_p(r["p_wald"]), ""])
            else:
                rows.append([f"  {lab}", fmt_or(r["OR"], r["OR_lo"], r["OR_hi"]), fmt_p(r["p_wald"]), ""])
    # linear
    lin = ROOT / "08_linear_per10min.csv"
    if lin.exists():
        L = pd.read_csv(lin).iloc[0]
        rows.append(["Linear (D5A covariates), per 10 min", fmt_or(L["OR"], L["OR_lo"], L["OR_hi"]), fmt_p(L["p_wald"]), ""])
    make_table_docx(
        TAB / "Table3_duration_models.docx",
        "Table 3 Association between cumulative MAP <65 duration and ICU admission (duration cohort).",
        headers,
        rows,
        [
            "Duration cohort: Liu Model 3 complete-case set n = 4,023 (416 events) before timing rule; revised n = 4,022 after excluding icuin_time < opend_time.",
            "D0 crude; D1 age+sex; D2 +ASA+emergency; D3 +BMI, Hb, albumin, creatinine, glucose; D4 +observation-duration proxy; D5A +operation duration, anaesthesia type, procedure axis.",
            "Reference category = 0 min. Trend uses ordinal score 0–3.",
            "Abbreviations: CI, confidence interval; ICU, intensive care unit; MAP, mean arterial pressure; OR, odds ratio.",
        ],
        title_size=14,
    )


def table_s8_spline():
    df = pd.read_csv(ROOT / "08_tableS8_spline_knots.csv")
    rows = []
    for _, r in df.iterrows():
        rows.append(
            [
                r["knots"],
                f"{r['aic']:.1f}",
                f"{r['lr_nonlinear']:.2f}",
                f"{int(r['df'])}",
                fmt_p(r["p_nonlinear"]),
                r["OR_10min"],
                r["OR_30min"],
                r["OR_60min"],
            ]
        )
    make_table_docx(
        TAB / "TableS8_spline_knots.docx",
        "Table S8 Restricted cubic spline knot sensitivity for MAP <65 duration (D5A).",
        ["Knots (min)", "AIC", "LR nonlinear", "df", "P nonlinear", "OR at 10 min", "OR at 30 min", "OR at 60 min"],
        rows,
        [
            "ORs are relative to 0 min on the same spline model. Primary display curve uses knots 0, 5, 45 on the observed 5-minute grid.",
            "Abbreviations: AIC, Akaike information criterion; CI, confidence interval; LR, likelihood ratio; OR, odds ratio.",
        ],
    )


def table4_los():
    df = pd.read_csv(ROOT / "09_table4_S10_los.csv")
    rows = []
    for _, r in df.iterrows():
        rows.append(
            [
                r["outcome"],
                r["contrast"],
                f"{int(r['n'])}",
                fmt_rd(r["median_diff_days"], r["lo"], r["hi"]),
                fmt_p(r["p"]),
            ]
        )
    make_table_docx(
        TAB / "Table4_LOS_median_regression.docx",
        "Table 4 Median length-of-stay differences by CAR×IOH phenotype (quantile regression, τ = 0.5).",
        ["Outcome", "Contrast", "n", "Median difference, days (95% CI)", "P value"],
        rows,
        [
            "Survivors analyses exclude in-hospital deaths. Rank composite assigns death the worst LOS value.",
            "Models include the P3 phenotype design matrix (Neither as reference).",
            "Abbreviations: CAR, C-reactive protein-to-albumin ratio; CI, confidence interval; IOH, intraoperative hypotension; LOS, length of stay.",
        ],
        title_size=14,
    )


def table_s14():
    df = pd.read_csv(ROOT / "11_tableS14_optimism_corrected.csv")
    rows = []
    for _, r in df.iterrows():
        rows.append(
            [
                r["metric"],
                f"{r['apparent']:.3f}",
                f"{r['mean_optimism']:.3f}",
                f"{r['optimism_corrected']:.3f}",
                f"{int(r['n_boot_ok'])}",
            ]
        )
    make_table_docx(
        TAB / "TableS14_optimism_NRI_IDI.docx",
        "Table S14 Optimism-corrected discrimination and reclassification (B = 500).",
        ["Metric", "Apparent", "Mean optimism", "Optimism-corrected", "Bootstrap n"],
        rows,
        [
            "Baseline model: age, ASA, emergency surgery, procedure axis.",
            "Extensions add the four-level phenotype or high-CAR indicator. Category-free NRI and IDI are reported.",
            "Abbreviations: AUC, area under the ROC curve; CAR, C-reactive protein-to-albumin ratio; IDI, integrated discrimination improvement; NRI, net reclassification improvement.",
        ],
    )


def table_s11():
    df = pd.read_csv(ROOT / "12_tableS11_mi.csv")
    rows = []
    for _, r in df.iterrows():
        rows.append(
            [
                r["analysis"],
                f"{int(r['n'])}",
                f"{int(r['m'])}",
                fmt_or(r["OR_Both"], r["lo"], r["hi"]),
            ]
        )
    make_table_docx(
        TAB / "TableS11_multiple_imputation.docx",
        "Table S11 Multiple imputation of covariates among CAR-available operations.",
        ["Analysis", "n", "m", "OR Both vs Neither (95% CI)"],
        rows,
        [
            "CAR itself is not imputed. Covariates imputed with iterative Bayesian ridge (m = 20); estimates pooled by Rubin's rules.",
            "Abbreviations: CAR, C-reactive protein-to-albumin ratio; CI, confidence interval; OR, odds ratio.",
        ],
    )


def table_s_bca():
    sm = pd.read_csv(ROOT / "02_primary_boot_summary.csv")
    rows = []
    keep = [
        "RD_G11_vs_G00",
        "RD_G10_vs_G00",
        "RD_G01_vs_G00",
        "IC_RD",
        "RD_CAR_within_IOHlt30",
        "RD_CAR_within_IOHge30",
        "RD_IOH_within_lowCAR",
        "RD_IOH_within_highCAR",
    ]
    lab = {
        "RD_G11_vs_G00": "Both vs Neither",
        "RD_G10_vs_G00": "High CAR only vs Neither",
        "RD_G01_vs_G00": "IOH only vs Neither",
        "IC_RD": "IC_RD",
        "RD_CAR_within_IOHlt30": "CAR effect | IOH <30",
        "RD_CAR_within_IOHge30": "CAR effect | IOH ≥30",
        "RD_IOH_within_lowCAR": "IOH effect | low CAR",
        "RD_IOH_within_highCAR": "IOH effect | high CAR",
    }
    for k in keep:
        r = sm.loc[sm["estimand"] == k]
        if not len(r):
            continue
        r = r.iloc[0]
        bca = "—"
        if "bca_lo" in r and pd.notna(r.get("bca_lo")):
            bca = fmt_rd(r["point"], r["bca_lo"], r["bca_hi"])
        rows.append(
            [
                lab.get(k, k),
                f"{r['point']:.2f}",
                fmt_rd(r["point"], r["pct_lo"], r["pct_hi"]),
                bca,
                fmt_p(r.get("p_boot_display", r.get("p_boot"))),
            ]
        )
    make_table_docx(
        TAB / "TableS13_percentile_vs_BCa.docx",
        "Table S13 Percentile versus BCa intervals for standardised risk differences (percentage points).",
        ["Contrast", "Point", "Percentile 95% CI", "BCa 95% CI", "Bootstrap P"],
        rows,
        [
            "Primary reporting uses percentile intervals (pre-specified). BCa uses full leave-one-out jackknife for the primary Both contrast where available.",
            "Abbreviations: BCa, bias-corrected and accelerated; CI, confidence interval; RD, risk difference.",
        ],
    )


def fig_style():
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "axes.labelsize": 11,
            "axes.titlesize": 12,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def save_fig(fig, stem):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f"{stem}.png", dpi=300, bbox_inches="tight")
    fig.savefig(FIG / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)
    print("Wrote", FIG / f"{stem}.png", flush=True)


def figure2():
    fig_style()
    df = pd.read_csv(ROOT / "02_primary_table2.csv")
    ph = df.columns[0]
    # parse point from std_risk_pct like '7.4 (6.2 to 8.7)'
    import re

    def parse_ci(s):
        m = re.match(r"\s*([0-9.]+)\s*\(([0-9.]+)\s*to\s*([0-9.]+)\)", str(s))
        if not m:
            return np.nan, np.nan, np.nan
        return float(m.group(1)), float(m.group(2)), float(m.group(3))

    pts, los, his = [], [], []
    for s in df["std_risk_pct"]:
        p, lo, hi = parse_ci(s)
        pts.append(p)
        los.append(lo)
        his.append(hi)
    colors = ["#4C78A8", "#F58518", "#54A24B", "#E45756"]
    fig, ax = plt.subplots(figsize=(6.4, 4.3))
    x = np.arange(len(df))
    ax.bar(x, pts, color=colors, width=0.72, edgecolor="black", linewidth=0.4, yerr=[np.array(pts) - np.array(los), np.array(his) - np.array(pts)], capsize=3, error_kw={"elinewidth": 1})
    ax.set_xticks(x)
    ax.set_xticklabels(df[ph], rotation=12, ha="right")
    ax.set_ylabel("Standardised ICU risk (%)")
    ax.set_title("Standardised ICU risk by CAR×IOH phenotype")
    for i, p in enumerate(pts):
        ax.text(i, his[i] + 0.35, f"{p:.1f}", ha="center", fontsize=9)
    ax.set_ylim(0, max(his) * 1.2)
    fig.text(0.01, -0.06, "P3 g-computation; n = 3,935; percentile bootstrap 95% CI. Patched exposure + CAR-cut ties.", fontsize=8, transform=ax.transAxes)
    save_fig(fig, "Figure2_std_risks")


def figure3():
    fig_style()
    df = pd.read_csv(ROOT / "08_figure3_curve_on_5min_grid.csv")
    fig, ax = plt.subplots(figsize=(6.4, 4.3))
    ax.plot(df["minutes"], df["OR"], color="#4C78A8", lw=2.2, label="OR vs 0 min")
    ax.fill_between(df["minutes"], df["lo"], df["hi"], color="#4C78A8", alpha=0.2)
    ax.axhline(1.0, color="grey", ls="--", lw=0.9)
    ax.set_xlabel("Cumulative MAP <65 duration (min)")
    ax.set_ylabel("Odds ratio vs 0 min")
    ax.set_title("Duration–response spline (D5A; knots 0, 5, 45)")
    ax.set_yscale("log")
    ax.set_ylim(0.7, max(3.5, float(df["hi"].max()) * 1.05))
    fig.text(0.01, -0.06, "Revised duration cohort; 5-minute grid. Shaded band = 95% CI.", fontsize=8, transform=ax.transAxes)
    save_fig(fig, "Figure3_duration_spline")


def figure4():
    fig_style()
    df = pd.read_csv(ROOT / "10_figure4_subgroups.csv")
    # map labels
    name_map = {
        "overall": "Overall",
        "sg_age_ge75": "Age ≥75",
        "sg_female": "Female",
        "sg_asa_ge3": "ASA ≥3",
        "sg_opdur_gt_median": "Op duration > median",
        "sg_general_anes": "General anaesthesia",
    }
    rows = []
    for _, r in df.iterrows():
        sg = r["subgroup"]
        if sg == "overall":
            lab = "Overall"
        else:
            base = name_map.get(sg, sg)
            lv = r["level"]
            if pd.isna(lv):
                lab = base
            else:
                yes = int(lv) == 1
                # for female/anes the covariate itself is the stratum
                if sg in ("sg_female", "sg_general_anes"):
                    lab = base if yes else ("Male" if sg == "sg_female" else "Non-general anaesthesia")
                else:
                    lab = base if yes else base.replace("≥", "<").replace(">", "≤")
                    if sg == "sg_age_ge75" and not yes:
                        lab = "Age <75"
                    if sg == "sg_asa_ge3" and not yes:
                        lab = "ASA <3"
                    if sg == "sg_opdur_gt_median" and not yes:
                        lab = "Op duration ≤ median"
        if pd.isna(r.get("OR")):
            continue
        rows.append({"label": lab, "OR": r["OR"], "lo": r["OR_lo"], "hi": r["OR_hi"], "p_int": r.get("p_interaction_LRT")})
    d = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(7.4, 5.2))
    y = np.arange(len(d))[::-1]
    ax.errorbar(
        d["OR"],
        y,
        xerr=[d["OR"] - d["lo"], d["hi"] - d["OR"]],
        fmt="s",
        color="#4C78A8",
        ecolor="#4C78A8",
        elinewidth=1.2,
        capsize=3,
        markersize=5,
    )
    ax.axvline(1.0, color="black", ls="--", lw=0.9)
    ax.set_yticks(y)
    ax.set_yticklabels(d["label"])
    ax.set_xlabel("OR Both vs Neither (95% CI)")
    ax.set_xscale("log")
    ax.set_title("Subgroup odds ratios for Both vs Neither")
    xmax = float(d["hi"].max()) * 1.35
    ax.set_xlim(0.4, xmax)
    for yi, (_, r) in zip(y, d.iterrows()):
        ax.text(r["hi"] * 1.03, yi, f"{r['OR']:.2f} ({r['lo']:.2f}, {r['hi']:.2f})", va="center", fontsize=8)
    fig.text(0.01, -0.05, "Both vs Neither within subgroups; Wald OR. Interaction LRT p values in source CSV.", fontsize=8, transform=ax.transAxes)
    save_fig(fig, "Figure4_subgroups")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    TAB.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    table1()
    table2()
    table3_duration()
    table4_los()
    table_s_exposure()
    table_s_monitoring()
    table_s_casemix_alt()
    table_s8_spline()
    table_s_bca()
    table_s14()
    table_s11()
    figure2()
    figure3()
    figure4()
    # also copy figures to root figures/
    import shutil

    fdir = Path(r"e:\桌面\BMC_Geriatrics_Rerun_patched\figures")
    fdir.mkdir(exist_ok=True)
    for p in FIG.glob("*"):
        shutil.copy2(p, fdir / p.name)
    print("DONE ->", OUT, flush=True)


if __name__ == "__main__":
    main()
