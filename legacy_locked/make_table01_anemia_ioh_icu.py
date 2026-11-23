# -*- coding: utf-8 -*-
"""Table 01 — baseline by anemia × IOH≥30 min phenotype (SAP v1.0).

Paths are configurable via --project-root / --data-dir / --out-dir / --mirror-dir
(or environment defaults relative to the current working directory).
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import shutil
import numpy as np
import pandas as pd
from scipy import stats
from docx import Document
from docx.shared import Pt, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

ROOT = Path.cwd()
DATA = ROOT / "data"
OUT_PROJ = ROOT / "results" / "anemia_ioh_icu_os65" / "01_Table01_baseline"
DESK_ROOT: Path | None = None
DESK: Path | None = None


def configure_paths(
    project_root: Path,
    data_dir: Path | None = None,
    out_dir: Path | None = None,
    mirror_dir: Path | None = None,
) -> None:
    global ROOT, DATA, OUT_PROJ, DESK_ROOT, DESK
    ROOT = project_root.resolve()
    DATA = (data_dir or (ROOT / "data")).resolve()
    OUT_PROJ = (out_dir or (ROOT / "results" / "anemia_ioh_icu_os65" / "01_Table01_baseline")).resolve()
    if mirror_dir is not None:
        DESK = mirror_dir.resolve()
        DESK_ROOT = DESK.parent
    else:
        DESK = None
        DESK_ROOT = None


def proc_axis_a(code: object) -> str:
    s = str(code).strip().upper()
    if len(s) < 4 or not s.startswith("0"):
        return "other_orthopedic"
    sys, root, part = s[1], s[2], s[3]
    joint_0sr = set("9ABECDFGERS")
    joint_0rr = set("JK")
    spine_0rg = set("0124678A")
    spine_0sg = set("0135678")
    if sys == "S" and root == "R" and part in joint_0sr:
        return "joint_arthroplasty"
    if sys == "R" and root == "R" and part in joint_0rr:
        return "joint_arthroplasty"
    if sys == "R" and root == "G" and part in spine_0rg:
        return "spine_procedure"
    if sys == "S" and root == "G" and part in spine_0sg:
        return "spine_procedure"
    return "other_orthopedic"


def build_cohort() -> pd.DataFrame:
    base = pd.read_csv(DATA / "topic_rescreen_os65_labs.csv", low_memory=False)
    demo = pd.read_csv(DATA / "inspire_os65_demo_map.csv", low_memory=False)
    gar = pd.read_csv(DATA / "inspire_os65_gar_formal.csv", low_memory=False)
    los = pd.read_csv(DATA / "inspire_os65_landmark_times.csv", usecols=["op_id", "los_days"])

    d = base.copy()
    # prefer labs from base; fill from demo/gar
    d = d.merge(
        demo[["op_id", "icd10_pcs", "op_duration_min", "lab_hb", "lab_creatinine"]],
        on="op_id",
        how="left",
        suffixes=("", "_demo"),
    )
    keep = [
        "op_id",
        "bmi",
        "antype",
        "labs_glucose_last_preop7d",
        "lab_albumin",
        "lab_hb",
        "lab_creatinine",
        "icd10_pcs",
        "op_duration_min",
    ]
    keep = [c for c in keep if c in gar.columns]
    d = d.merge(gar[keep], on="op_id", how="left", suffixes=("", "_gar"))
    d = d.merge(los, on="op_id", how="left")

    # unify columns
    def coalesce(*cols):
        out = None
        for c in cols:
            if c is None or c not in d.columns:
                continue
            s = pd.to_numeric(d[c], errors="coerce") if c != "icd10_pcs" and "antype" not in c and "sex" not in c else d[c]
            if out is None:
                out = s
            else:
                out = out.where(out.notna(), s)
        return out

    d["hb"] = coalesce("labs_hb_last_preop7d", "lab_hb", "lab_hb_gar")
    d["albumin"] = coalesce("labs_albumin_last_preop7d", "lab_albumin")
    d["creatinine"] = coalesce("labs_creatinine_last_preop7d", "lab_creatinine", "lab_creatinine_gar")
    d["glucose"] = coalesce("labs_glucose_last_preop7d")
    d["bmi"] = coalesce("bmi")
    d["op_duration_min"] = coalesce("op_duration_min", "op_duration_min_gar")
    if "icd10_pcs" not in d.columns or d["icd10_pcs"].isna().all():
        d["icd10_pcs"] = d.get("icd10_pcs_gar")
    elif "icd10_pcs_gar" in d.columns:
        d["icd10_pcs"] = d["icd10_pcs"].where(d["icd10_pcs"].notna(), d["icd10_pcs_gar"])
    if "antype" not in d.columns:
        d["antype"] = np.nan

    d["age"] = pd.to_numeric(d["age"], errors="coerce")
    d["asa"] = pd.to_numeric(d["asa"], errors="coerce")
    d["emop"] = pd.to_numeric(d["emop"], errors="coerce").fillna(0).astype(int)
    d["icu_admission"] = pd.to_numeric(d["icu_admission"], errors="coerce")
    d["death_inhosp"] = pd.to_numeric(d.get("death_inhosp"), errors="coerce")
    d["los_days"] = pd.to_numeric(d.get("los_days"), errors="coerce")
    d["map_below65_min"] = pd.to_numeric(d["map_below65_min"], errors="coerce")
    # INSPIRE summary: treat as 5-min epochs → minutes
    d["map65_min"] = d["map_below65_min"] * 5.0

    sex = d["sex"].astype(str).str.upper()
    d["female"] = sex.isin(["F", "FEMALE"]).astype(int)
    male = sex.isin(["M", "MALE"])
    d["anemia"] = (d["hb"] < np.where(male, 13.0, 12.0)).astype(float)
    d.loc[d["hb"].isna(), "anemia"] = np.nan

    d["ioh30"] = (d["map65_min"] >= 30).astype(float)
    d.loc[d["map65_min"].isna(), "ioh30"] = np.nan

    # phenotype labels
    def pheno(row):
        if pd.isna(row["anemia"]) or pd.isna(row["ioh30"]):
            return np.nan
        a, i = int(row["anemia"]), int(row["ioh30"])
        return {(0, 0): "G00", (1, 0): "G10", (0, 1): "G01", (1, 1): "G11"}[(a, i)]

    d["phenotype"] = d.apply(pheno, axis=1)
    d["asa_ge3"] = (d["asa"] >= 3).astype(float)
    d.loc[d["asa"].isna(), "asa_ge3"] = np.nan
    d["general_anes"] = (
        d["antype"].astype(str).str.lower().str.contains("general", na=False)
    ).astype(int)
    d["proc_axis"] = d["icd10_pcs"].map(proc_axis_a)
    for lab, code in [
        ("joint_arthroplasty", "joint_arthroplasty"),
        ("spine_procedure", "spine_procedure"),
        ("other_orthopedic", "other_orthopedic"),
    ]:
        d[f"proc_{code}"] = (d["proc_axis"] == code).astype(int)

    d["ioh_dur_cat"] = pd.cut(
        d["map65_min"],
        bins=[-0.1, 0, 10, 30, 1e9],
        labels=["0", ">0-<10", "10-<30", ">=30"],
    )
    return d


def med_iqr(s):
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) == 0:
        return "—"
    return f"{s.median():.1f} ({s.quantile(0.25):.1f}–{s.quantile(0.75):.1f})"


def n_pct(x):
    x = pd.to_numeric(x, errors="coerce")
    m = x.notna()
    if m.sum() == 0:
        return "—"
    x = x[m].astype(int)
    return f"{int(x.sum())} ({100 * x.mean():.1f})"


def fmt_p(p):
    if p is None or (isinstance(p, float) and np.isnan(p)):
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


def p_chi(df, col, group_col="phenotype"):
    sub = df.dropna(subset=[group_col, col])
    tab = pd.crosstab(sub[group_col], pd.to_numeric(sub[col], errors="coerce").fillna(0).astype(int))
    if tab.shape[0] < 2 or tab.shape[1] < 2:
        return np.nan
    return float(stats.chi2_contingency(tab)[1])


def set_run_font(run, name="Times New Roman", size=10, bold=False):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")
    run.font.size = Pt(size)
    run.bold = bold


def set_cell_border(cell, **kwargs):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        element = OxmlElement(f"w:{edge}")
        if edge in kwargs:
            sz, val, color = kwargs[edge]
            element.set(qn("w:val"), val)
            element.set(qn("w:sz"), str(sz))
            element.set(qn("w:color"), color)
            element.set(qn("w:space"), "0")
        else:
            element.set(qn("w:val"), "nil")
        tcBorders.append(element)
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


def write_cell(cell, text, bold=False, align="left"):
    cell.text = ""
    p = cell.paragraphs[0]
    if align == "center":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(str(text))
    set_run_font(run, size=9, bold=bold)
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.0


def build_table_rows(df: pd.DataFrame):
    order = ["G00", "G10", "G01", "G11"]
    labels = {
        "G00": "Neither",
        "G10": "Anemia only",
        "G01": "IOH only\n(≥30 min)",
        "G11": "Both",
    }
    d = df.dropna(subset=["phenotype"]).copy()
    d["phenotype"] = pd.Categorical(d["phenotype"], categories=order, ordered=True)
    groups = [d.loc[d.phenotype == g] for g in order]
    ns = [len(g) for g in groups]

    def cont(label, col):
        cells = [label, med_iqr(d[col])] + [med_iqr(g[col]) for g in groups]
        cells.append(fmt_p(p_kw([g[col] for g in groups])))
        return cells

    def binrow(label, col):
        cells = [label, n_pct(d[col])] + [n_pct(g[col]) for g in groups]
        cells.append(fmt_p(p_chi(d, col)))
        return cells

    def section(title):
        return [title, "", "", "", "", "", ""]

    rows = []
    rows.append(section("Demographics and clinical status"))
    rows.append(cont("Age, years", "age"))
    rows.append(binrow("Female sex, n (%)", "female"))
    rows.append(cont("BMI, kg/m²", "bmi"))
    rows.append(binrow("ASA physical status ≥3, n (%)", "asa_ge3"))
    rows.append(binrow("Emergency surgery, n (%)", "emop"))

    rows.append(section("Preoperative laboratories"))
    rows.append(cont("Hemoglobin, g/dL", "hb"))
    rows.append(cont("Albumin, g/dL", "albumin"))
    rows.append(cont("Creatinine, mg/dL", "creatinine"))
    rows.append(cont("Glucose, mg/dL", "glucose"))

    rows.append(section("Intraoperative hypotension"))
    rows.append(cont("Cumulative MAP <65 mmHg, min", "map65_min"))
    rows.append(cont("Lowest intraoperative MAP, mmHg", "map_min"))

    rows.append(section("Anesthesia and surgery"))
    rows.append(binrow("General anesthesia, n (%)", "general_anes"))
    rows.append(cont("Operation duration, min", "op_duration_min"))
    rows.append(binrow("Joint arthroplasty, n (%)", "proc_joint_arthroplasty"))
    rows.append(binrow("Spine procedure, n (%)", "proc_spine_procedure"))
    rows.append(binrow("Other orthopedic, n (%)", "proc_other_orthopedic"))

    rows.append(section("Crude outcomes (descriptive)"))
    rows.append(binrow("Postoperative ICU admission, n (%)", "icu_admission"))
    rows.append(cont("Hospital length of stay, days", "los_days"))

    header = [
        "Variable",
        f"Overall\n(N={len(d)})",
        f"Neither\n(N={ns[0]})",
        f"Anemia only\n(N={ns[1]})",
        f"IOH ≥30 min only\n(N={ns[2]})",
        f"Both\n(N={ns[3]})",
        "P value",
    ]
    return d, rows, header, ns, labels


def to_csv(header, rows, path: Path):
    flat_h = [h.replace("\n", " ") for h in header]
    out = []
    for r in rows:
        out.append([("" if c is None else str(c).replace("\n", " ")) for c in r])
    pd.DataFrame(out, columns=flat_h).to_csv(path, index=False, encoding="utf-8-sig")


def to_docx(header, rows, path: Path, footnote: str):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Inches(11)
    sec.page_height = Inches(8.5)
    sec.left_margin = Cm(1.5)
    sec.right_margin = Cm(1.5)
    sec.top_margin = Cm(1.5)
    sec.bottom_margin = Cm(1.5)

    t = doc.add_paragraph()
    run = t.add_run(
        "Table 1. Baseline characteristics by preoperative anemia and sustained intraoperative hypotension "
        "(MAP <65 mmHg for ≥30 minutes) among older adults undergoing orthopedic surgery (INSPIRE)."
    )
    set_run_font(run, size=11, bold=True)

    table = doc.add_table(rows=1 + len(rows), cols=len(header))
    table.autofit = True
    for j, h in enumerate(header):
        write_cell(table.rows[0].cells[j], h.replace("\n", " "), bold=True, align="center")
    for i, r in enumerate(rows):
        for j, val in enumerate(r):
            is_sec = j == 0 and r[1] == "" and r[2] == ""
            write_cell(
                table.rows[i + 1].cells[j],
                val,
                bold=is_sec,
                align="center" if j > 0 else "left",
            )
    apply_three_line(table)

    note = doc.add_paragraph()
    run = note.add_run(footnote)
    set_run_font(run, size=8, bold=False)
    doc.save(path)


def main():
    OUT_PROJ.mkdir(parents=True, exist_ok=True)

    # freeze SAP v1.0 when the source note exists in this checkout
    sap_src = ROOT / "docs" / "SAP_v0.2_anemia_IOH_ICU_OS65.md"
    sap_v1 = ROOT / "docs" / "SAP_v1.0_anemia_IOH_ICU_OS65.md"
    if sap_src.exists():
        text = sap_src.read_text(encoding="utf-8")
        text = text.replace("v0.2", "v1.0").replace("终审稿（确认后升 v1.0 开跑）", "已冻结（执行版）")
        text = text.replace("**终审** — 您确认后改名 `SAP_v1.0_...` 并执行", "**已冻结 · 执行中**")
        sap_v1.parent.mkdir(parents=True, exist_ok=True)
        sap_v1.write_text(text, encoding="utf-8")
        if DESK_ROOT is not None:
            sap_mirror = DESK_ROOT / "00_SAP"
            sap_mirror.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sap_v1, sap_mirror / sap_v1.name)

    cohort = build_cohort()
    analytic = cohort.dropna(subset=["phenotype"]).copy()
    cohort_path = OUT_PROJ / "Table01_analytic_cohort.csv"
    keep_cols = [
        c
        for c in [
            "op_id",
            "subject_id",
            "hadm_id",
            "age",
            "sex",
            "female",
            "bmi",
            "asa",
            "asa_ge3",
            "emop",
            "hb",
            "albumin",
            "creatinine",
            "glucose",
            "map_below65_min",
            "map65_min",
            "map_min",
            "anemia",
            "ioh30",
            "phenotype",
            "ioh_dur_cat",
            "antype",
            "general_anes",
            "op_duration_min",
            "icd10_pcs",
            "proc_axis",
            "icu_admission",
            "los_days",
            "death_inhosp",
        ]
        if c in analytic.columns
    ]
    analytic[keep_cols].to_csv(cohort_path, index=False)

    d, rows, header, ns, _ = build_table_rows(analytic)
    csv_path = OUT_PROJ / "Table01_baseline_by_phenotype.csv"
    docx_path = OUT_PROJ / "Table01_baseline_by_phenotype.docx"

    footnote = (
        "Values are median (IQR) or n (%). Phenotypes: Neither = no anemia and cumulative MAP <65 mmHg <30 min; "
        "Anemia only = WHO anemia without sustained IOH; IOH ≥30 min only = sustained hypotension without anemia; "
        "Both = anemia and cumulative MAP <65 mmHg ≥30 min. Anemia defined as hemoglobin <13 g/dL in men and "
        "<12 g/dL in women (preoperative last value within 7 days). IOH duration estimated from INSPIRE "
        "map_below65_min × 5 (5-minute sampling grid). P values from Kruskal–Wallis test (continuous) or "
        "chi-square test (categorical) across the four phenotypes. Crude ICU and length of stay are shown for "
        "description only. Missing values were excluded variable-wise within each cell. "
        f"Cohort: INSPIRE orthopedic surgery, age ≥65 years, first eligible operation; N={len(d)} with both "
        f"hemoglobin and MAP burden available. SAP v1.0."
    )
    to_csv(header, rows, csv_path)
    to_docx(header, rows, docx_path, footnote)

    meta = {
        "n_exported_os65": int(len(cohort)),
        "n_table1_phenotype": int(len(d)),
        "n_by_phenotype": {k: int(v) for k, v in zip(["G00", "G10", "G01", "G11"], ns)},
        "icu_by_phenotype": {
            g: {
                "n": int((d.phenotype == g).sum()),
                "icu": int(d.loc[d.phenotype == g, "icu_admission"].sum()),
                "rate": float(d.loc[d.phenotype == g, "icu_admission"].mean()),
            }
            for g in ["G00", "G10", "G01", "G11"]
        },
        "map_definition": "map65_min = map_below65_min * 5; IOH+ for phenotype = map65_min >= 30",
        "outputs": [csv_path.name, docx_path.name, cohort_path.name],
    }
    (OUT_PROJ / "Table01_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if DESK is not None:
        DESK.mkdir(parents=True, exist_ok=True)
        for f in OUT_PROJ.iterdir():
            if f.is_file():
                shutil.copy2(f, DESK / f.name)
        if DESK_ROOT is not None:
            (DESK_ROOT / "README.md").write_text(
                "# ANEMIA_IOH_ICU_OS65 — output mirror\n\n"
                "Optional local mirror created because --mirror-dir was set.\n",
                encoding="utf-8",
            )

    print(json.dumps(meta, indent=2, ensure_ascii=False))
    print("OUT", OUT_PROJ)
    if DESK is not None:
        print("MIRROR", DESK)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-root", type=Path, default=Path.cwd())
    ap.add_argument("--data-dir", type=Path, default=None, help="Directory with topic_rescreen / demo / gar / landmark extracts")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--mirror-dir", type=Path, default=None, help="Optional extra copy destination; omit to disable")
    ns = ap.parse_args()
    configure_paths(ns.project_root, ns.data_dir, ns.out_dir, ns.mirror_dir)
    OUT_PROJ.mkdir(parents=True, exist_ok=True)
    main()
