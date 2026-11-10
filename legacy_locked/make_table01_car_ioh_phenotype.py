# -*- coding: utf-8 -*-
"""Table 1 — baseline by CAR×IOH≥30 phenotype (SAP v3.0 FROZEN).

Columns: Overall, G00, G10, G01, G11 on primary complete-case set (Dcc).
CAR = CRP(mg/dL)/albumin(g/dL) [Lin]; High = T3 with locked cut ≥0.0738.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt
from scipy import stats

ROOT = Path(r"e:\DS-智能体\222")
OUT_PROJ = ROOT / "results" / "car_ioh_icu_os65" / "01_Table01_baseline"
DESK = Path(r"E:\桌面") / "222" / "01_Table01_baseline"

IOH_THR = 30.0
# Locked historical T3 cut (Lin formula); do not recompute on Dcc
CAR_CUT = 0.07380952380952381
PHENOS = ["G00", "G10", "G01", "G11"]
PHENO_LABELS = {
    "G00": "Neither",
    "G10": "High CAR only",
    "G01": "IOH ≥30 only",
    "G11": "Both",
}
COV_CONT = ["age", "asa", "op_duration_min", "creatinine", "bmi", "hb", "glucose"]
COV_BIN = ["female", "emop", "general_anes"]


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


def write_cell(cell, text, bold=False, align="left", size=10.5):
    cell.text = ""
    p = cell.paragraphs[0]
    if align == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif align == "left":
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run(str(text))
    set_run_font(run, size=size, bold=bold)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.0


def med_iqr(s, digits=1):
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) == 0:
        return "—"
    fmt = f"{{:.{digits}f}}"
    return (
        f"{fmt.format(s.median())} "
        f"({fmt.format(s.quantile(0.25))}–{fmt.format(s.quantile(0.75))})"
    )


def n_pct(series):
    x = pd.to_numeric(series, errors="coerce")
    m = x.notna()
    if m.sum() == 0:
        return "—"
    x = x[m].astype(int)
    return f"{int(x.sum())} ({100 * x.mean():.1f})"


def fmt_p(p):
    if p is None or (isinstance(p, float) and (np.isnan(p) or not np.isfinite(p))):
        return "—"
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}"


def p_kw(groups):
    gs = [pd.to_numeric(g, errors="coerce").dropna() for g in groups]
    gs = [g for g in gs if len(g)]
    if len(gs) < 2:
        return np.nan
    return float(stats.kruskal(*gs).pvalue)


def p_chi(df, col):
    sub = df.dropna(subset=["phenotype", col])
    tab = pd.crosstab(
        sub["phenotype"],
        pd.to_numeric(sub[col], errors="coerce").fillna(0).astype(int),
    )
    if tab.shape[0] < 2 or tab.shape[1] < 2:
        return np.nan
    return float(stats.chi2_contingency(tab)[1])


def load_cohort():
    base = pd.read_csv(
        ROOT
        / "results"
        / "anemia_ioh_icu_os65"
        / "01_Table01_baseline"
        / "Table01_analytic_cohort.csv",
        low_memory=False,
    )
    enrich = pd.read_csv(
        ROOT / "data" / "inspire_os65_car_enrich.csv",
        usecols=["op_id", "labs_crp_last_preop7d", "labs_albumin_last_preop7d"],
    )
    d = base.merge(enrich, on="op_id", how="left")

    crp = pd.to_numeric(d["labs_crp_last_preop7d"], errors="coerce")
    alb = pd.to_numeric(d["albumin"], errors="coerce").fillna(
        pd.to_numeric(d["labs_albumin_last_preop7d"], errors="coerce")
    )
    car = crp / alb
    car = car.mask(crp.isna() | alb.isna() | (alb <= 0))
    high = (car >= CAR_CUT).astype(float)
    high = high.mask(car.isna())

    map65 = pd.to_numeric(d["map65_min"], errors="coerce")
    ioh = (map65 >= IOH_THR).astype(float).mask(map65.isna())
    icu = pd.to_numeric(d["icu_admission"], errors="coerce")

    ph = np.select(
        [
            (high == 0) & (ioh == 0),
            (high == 1) & (ioh == 0),
            (high == 0) & (ioh == 1),
            (high == 1) & (ioh == 1),
        ],
        PHENOS,
        default="",
    )
    d["crp"] = crp
    d["alb_use"] = alb
    d["car"] = car
    d["car_high"] = high
    d["ioh_ge30"] = ioh
    d["map65_min"] = map65
    d["icu_admission"] = icu
    d["phenotype"] = pd.Series(ph, index=d.index).mask(
        high.isna() | ioh.isna() | (pd.Series(ph, index=d.index) == "")
    )

    for c in COV_CONT + COV_BIN + ["asa_ge3", "los_days", "death_inhosp", "map_min", "anemia"]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    if "asa_ge3" not in d.columns or d["asa_ge3"].isna().all():
        d["asa_ge3"] = (pd.to_numeric(d["asa"], errors="coerce") >= 3).astype(float)
        d.loc[pd.to_numeric(d["asa"], errors="coerce").isna(), "asa_ge3"] = np.nan

    d["proc_axis"] = d["proc_axis"].fillna("other_orthopedic").astype(str)
    joint_vals = {"joint_arthroplasty", "joint_replacement"}
    spine_vals = {"spine_procedure", "spine"}
    d["proc_joint"] = d["proc_axis"].isin(joint_vals).astype(int)
    d["proc_spine"] = d["proc_axis"].isin(spine_vals).astype(int)
    d["proc_other"] = (~d["proc_axis"].isin(joint_vals | spine_vals)).astype(int)

    # Dexp: exposure + outcome available
    dexp = d.dropna(subset=["phenotype", "icu_admission"]).copy()
    # Dcc: Model 3 complete cases (matches Figure 1 primary N)
    use = ["phenotype", "icu_admission", "proc_axis"] + COV_CONT + COV_BIN
    dcc = dexp.dropna(subset=use).copy()
    dcc["phenotype"] = pd.Categorical(
        dcc["phenotype"], categories=PHENOS, ordered=True
    )
    return d, dexp, dcc


def build_rows(dcc: pd.DataFrame):
    """SCI baseline Table 1: no P column; no outcome rows; no definitional IOH≥30 row."""
    groups = [dcc.loc[dcc["phenotype"] == g] for g in PHENOS]
    ns = [len(g) for g in groups]
    ncol = 6  # Characteristic + Overall + 4 phenotypes

    def section(title):
        return [title] + [""] * (ncol - 1)

    def cont(label, col, digits=1):
        return [label, med_iqr(dcc[col], digits)] + [
            med_iqr(g[col], digits) for g in groups
        ]

    def binrow(label, col):
        return [label, n_pct(dcc[col])] + [n_pct(g[col]) for g in groups]

    rows = []
    rows.append(section("Demographics"))
    rows.append(cont("Age, years", "age", digits=0))
    rows.append(binrow("Female sex, n (%)", "female"))
    rows.append(cont("Body mass index, kg/m²", "bmi"))
    rows.append(binrow("ASA physical status ≥3, n (%)", "asa_ge3"))
    rows.append(binrow("Emergency surgery, n (%)", "emop"))

    rows.append(section("Preoperative laboratories"))
    rows.append(cont("Hemoglobin, g/dL", "hb"))
    rows.append(cont("Albumin, g/dL", "alb_use"))
    rows.append(cont("C-reactive protein, mg/dL", "crp", digits=2))
    rows.append(cont("CAR", "car", digits=3))
    rows.append(cont("Creatinine, mg/dL", "creatinine"))
    rows.append(cont("Glucose, mg/dL", "glucose", digits=0))

    rows.append(section("Intraoperative blood pressure"))
    rows.append(cont("Cumulative duration of MAP <65 mmHg, min", "map65_min", digits=0))
    if "map_min" in dcc.columns:
        rows.append(cont("Lowest intraoperative MAP, mmHg", "map_min", digits=0))

    rows.append(section("Anesthesia and surgery"))
    rows.append(binrow("General anesthesia, n (%)", "general_anes"))
    rows.append(cont("Operation duration, min", "op_duration_min", digits=0))
    rows.append(section("Type of surgery, n (%)"))
    rows.append(binrow("    Joint arthroplasty", "proc_joint"))
    rows.append(binrow("    Spine procedure", "proc_spine"))
    rows.append(binrow("    Other orthopedic", "proc_other"))

    header = [
        "Characteristic",
        f"Overall\n(n={len(dcc)})",
        f"Neither\n(n={ns[0]})",
        f"High CAR only\n(n={ns[1]})",
        f"IOH ≥30 min only\n(n={ns[2]})",
        f"Both\n(n={ns[3]})",
    ]
    return rows, header, ns


def to_csv(header, rows, path: Path):
    flat_h = [h.replace("\n", " ") for h in header]
    out = [[("" if c is None else str(c).replace("\n", " ")) for c in r] for r in rows]
    pd.DataFrame(out, columns=flat_h).to_csv(path, index=False, encoding="utf-8-sig")


def to_docx(header, rows, path: Path, footnote: str):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Inches(11)
    sec.page_height = Inches(8.5)
    # ~0.55 in margins (SCI sample Table 03)
    for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, side, Inches(0.55))

    t = doc.add_paragraph()
    run = t.add_run(
        "Table 1. Baseline characteristics according to the CAR×IOH phenotype "
        "among older adults undergoing orthopedic surgery."
    )
    set_run_font(run, size=12, bold=True)
    t.paragraph_format.space_after = Pt(6)

    table = doc.add_table(rows=1 + len(rows), cols=len(header))
    table.autofit = True
    for j, h in enumerate(header):
        write_cell(
            table.rows[0].cells[j],
            h.replace("\n", " "),
            bold=True,
            align="center" if j > 0 else "left",
            size=10.5,
        )
    for i, r in enumerate(rows):
        is_sec = bool(r[0]) and all(c == "" for c in r[1:])
        for j, val in enumerate(r):
            write_cell(
                table.rows[i + 1].cells[j],
                val,
                bold=is_sec,
                align="center" if j > 0 else "left",
                size=10.5,
            )
    apply_three_line(table)

    # Column widths: characteristic wider
    try:
        widths = [Inches(3.2), Inches(1.35), Inches(1.35), Inches(1.45), Inches(1.55), Inches(1.25)]
        for row in table.rows:
            for cell, w in zip(row.cells, widths):
                cell.width = w
    except Exception:
        pass

    note = doc.add_paragraph()
    note.paragraph_format.space_before = Pt(6)
    run = note.add_run(footnote)
    set_run_font(run, size=10.5, bold=False)
    doc.save(path)


def main():
    OUT_PROJ.mkdir(parents=True, exist_ok=True)
    DESK.mkdir(parents=True, exist_ok=True)

    raw, dexp, dcc = load_cohort()
    rows, header, ns = build_rows(dcc)

    n_by = {g: int(n) for g, n in zip(PHENOS, ns)}
    icu_by = {}
    for g in PHENOS:
        sub = dcc.loc[dcc["phenotype"] == g]
        icu_by[g] = {
            "n": int(len(sub)),
            "icu": int(pd.to_numeric(sub["icu_admission"], errors="coerce").fillna(0).sum()),
            "rate": float(pd.to_numeric(sub["icu_admission"], errors="coerce").mean()),
        }

    footnote = (
        "Values are median (IQR) or n (%). "
        "Neither = low CAR (lower two tertiles) and cumulative MAP <65 mmHg duration <30 min; "
        f"High CAR only = CAR ≥ {CAR_CUT:.4f} (uppermost tertile) with cumulative MAP <65 mmHg <30 min; "
        "IOH ≥30 min only = cumulative MAP <65 mmHg ≥30 min with low CAR; "
        "Both = high CAR and cumulative MAP <65 mmHg ≥30 min. "
        "CAR = C-reactive protein (mg/dL) / albumin (g/dL). "
        "The CAR tertile cut-off was fixed from the CAR-nonmissing screening sample and was not "
        "recalculated in the complete-case set. "
        "MAP duration was derived from the INSPIRE 5-minute summary grid (map_below65_min × 5). "
        f"Analytic sample: complete-case primary cohort (n={len(dcc)}). "
        "Abbreviations: ASA, American Society of Anesthesiologists; CAR, C-reactive protein-to-albumin "
        "ratio; IOH, intraoperative hypotension; IQR, interquartile range; MAP, mean arterial pressure."
    )

    csv_name = "Table01_baseline_by_CAR_IOH_phenotype.csv"
    docx_name = "Table01_baseline_by_CAR_IOH_phenotype.docx"
    cohort_name = "Table01_analytic_cohort_Dcc.csv"
    meta_name = "Table01_meta.json"
    brief_name = "Table01_BRIEF.md"

    to_csv(header, rows, OUT_PROJ / csv_name)
    to_docx(header, rows, OUT_PROJ / docx_name, footnote)

    keep = [
        c
        for c in [
            "op_id",
            "age",
            "female",
            "bmi",
            "asa",
            "asa_ge3",
            "emop",
            "hb",
            "alb_use",
            "crp",
            "car",
            "car_high",
            "creatinine",
            "glucose",
            "map65_min",
            "map_min",
            "ioh_ge30",
            "phenotype",
            "general_anes",
            "op_duration_min",
            "proc_axis",
            "proc_joint",
            "proc_spine",
            "proc_other",
            "icu_admission",
            "los_days",
            "death_inhosp",
        ]
        if c in dcc.columns
    ]
    dcc[keep].to_csv(OUT_PROJ / cohort_name, index=False)

    meta = {
        "car_formula": "CRP(mg/dL)/albumin(g/dL) [Lin]",
        "car_cut_locked": CAR_CUT,
        "ioh_threshold_min": IOH_THR,
        "n_raw_os65": int(len(raw)),
        "n_dexp": int(len(dexp)),
        "n_dcc_table1": int(len(dcc)),
        "n_by_phenotype": n_by,
        "icu_by_phenotype": icu_by,
        "high_car_pct_dcc": float(dcc["car_high"].mean() * 100),
        "outputs": [csv_name, docx_name, cohort_name, meta_name, brief_name],
    }
    (OUT_PROJ / meta_name).write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    brief = f"""# Table 1 — CAR×IOH 四表型基线（SCI 版）

- 口径：Dcc n={len(dcc)}；切点 CAR ≥ {CAR_CUT:.4f}（锁定）
- 版式：三线表；**无基线 P 值**；**无结局行**（ICU/LOS/死亡留给 Table 2–3）
- 表型 n：G00 {n_by['G00']} / G10 {n_by['G10']} / G01 {n_by['G01']} / G11 {n_by['G11']}
- 内部核对（不入 Table 1）：ICU 粗事件 G00–G11 = {icu_by['G00']['icu']}/{icu_by['G10']['icu']}/{icu_by['G01']['icu']}/{icu_by['G11']['icu']}（合计 {int(dcc['icu_admission'].sum())}）

产物：`{csv_name}` / `{docx_name}`
"""
    (OUT_PROJ / brief_name).write_text(brief, encoding="utf-8")

    for f in OUT_PROJ.iterdir():
        if f.is_file():
            shutil.copy2(f, DESK / f.name)

    # Keep prior High vs Low artifacts if present on Desktop under same folder name
    print(json.dumps(meta, indent=2, ensure_ascii=False))
    print("OUT", OUT_PROJ)
    print("DESK", DESK)


if __name__ == "__main__":
    main()
