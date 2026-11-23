# -*- coding: utf-8 -*-
"""Build the three enriched cohort CSVs required by analysis/rerun_pipeline.py.

Outputs (canonical names under --out-dir / config out_dir):
  - primary_cohort_dcc_enriched.csv
  - duration_cohort_4023.csv
  - car_available_4529.csv

All paths are configurable via --config (JSON) and/or command-line arguments.
No author machine absolute paths are hard-coded.

Dependencies that are not redistributed publicly (PhysioNet DUA):
  see RUN_REPRODUCE.md step 3 and data/derived/README.md.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

CAR_CUT_DEFAULT = 0.07380952380952381


def load_config(path: Path | None) -> dict:
    if path is None:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve(project_root: Path, value: str | Path | None, default: str | None = None) -> Path:
    raw = value if value is not None else default
    if raw is None:
        raise SystemExit("Missing required path setting")
    p = Path(raw)
    if not p.is_absolute():
        p = project_root / p
    return p.resolve()


def build_primary(
    dcc: pd.DataFrame,
    ops: pd.DataFrame,
    ext: pd.DataFrame,
    mc9: pd.DataFrame,
    car_cut: float,
) -> pd.DataFrame:
    dcc = dcc.copy()
    dcc["op_id"] = dcc["op_id"].astype(np.int64)
    ops = ops.copy()
    ops["op_id"] = ops["op_id"].astype(np.int64)
    ext = ext.copy()
    ext["op_id"] = ext["op_id"].astype(np.int64)
    mc9 = mc9.copy()
    mc9["op_id"] = mc9["op_id"].astype(np.int64)

    ops_keep = [
        "op_id",
        "subject_id",
        "hadm_id",
        "opstart_time",
        "opend_time",
        "anstart_time",
        "anend_time",
        "admission_time",
        "discharge_time",
        "icuin_time",
        "icuout_time",
        "inhosp_death_time",
        "department",
        "antype",
    ]
    ops = ops[[c for c in ops_keep if c in ops.columns]].copy()
    for c in ops.columns:
        if c not in ("op_id", "subject_id", "hadm_id", "department", "antype"):
            ops[c] = pd.to_numeric(ops[c], errors="coerce")

    m = dcc.merge(ops, on="op_id", how="left", suffixes=("", "_ops"))
    ext_cols = [
        c
        for c in (
            "op_id",
            "icu_stay_hr",
            "labs_creatinine_last_preop7d",
            "labs_creatinine_max",
        )
        if c in ext.columns
    ]
    m = m.merge(ext[ext_cols], on="op_id", how="left", suffixes=("", "_ext"))

    m["albumin"] = pd.to_numeric(m.get("alb_use", m.get("albumin")), errors="coerce")
    m["los_total_days"] = pd.to_numeric(m.get("los_days"), errors="coerce")
    if "discharge_time" in m.columns and "opend_time" in m.columns:
        m["los_postop_days"] = (m["discharge_time"] - m["opend_time"]) / (60.0 * 24.0)
    else:
        m["los_postop_days"] = np.nan

    if "icu_stay_hr" not in m.columns or m["icu_stay_hr"].isna().all():
        if {"icuout_time", "icuin_time"}.issubset(m.columns):
            m["icu_stay_hr"] = (m["icuout_time"] - m["icuin_time"]) / 60.0
        else:
            m["icu_stay_hr"] = np.nan

    stay = pd.to_numeric(m["icu_stay_hr"], errors="coerce")
    icu = m["icu_admission"].astype(float)
    m["icu_stay_gt24h"] = ((stay > 24) & (icu == 1)).astype(float)
    m.loc[stay.isna() & (icu == 0), "icu_stay_gt24h"] = 0.0
    m["icu_stay_gt48h"] = ((stay > 48) & (icu == 1)).astype(float)
    m.loc[stay.isna() & (icu == 0), "icu_stay_gt48h"] = 0.0

    pre = pd.to_numeric(m.get("labs_creatinine_last_preop7d"), errors="coerce")
    post = pd.to_numeric(m.get("labs_creatinine_max"), errors="coerce")
    pre = pre.fillna(pd.to_numeric(m.get("creatinine"), errors="coerce"))
    rise = (post - pre) >= 0.3
    ratio = post >= (1.5 * pre)
    m["kidney_event"] = np.where(pre.notna() & post.notna(), (rise | ratio).astype(float), np.nan)

    ann_cols = [
        c
        for c in (
            "indication_group",
            "fracture_related",
            "infection_related",
            "tumour_related",
            "charlson_index",
        )
        if c in mc9.columns
    ]
    if ann_cols:
        m = m.merge(mc9[["op_id"] + ann_cols].drop_duplicates("op_id"), on="op_id", how="left")

    m["car"] = pd.to_numeric(m["car"], errors="coerce")
    m["car_high"] = (m["car"] >= car_cut).astype(float)
    if {"icuin_time", "opend_time"}.issubset(m.columns):
        m["icu_before_opend"] = m["icuin_time"].notna() & (m["icuin_time"] < m["opend_time"])
    else:
        m["icu_before_opend"] = False
    m["obs_duration_proxy"] = pd.to_numeric(m.get("op_duration_min"), errors="coerce")

    need_out = [
        "op_id",
        "icu_admission",
        "car",
        "crp",
        "albumin",
        "map65_min",
        "age",
        "asa",
        "op_duration_min",
        "creatinine",
        "bmi",
        "hb",
        "glucose",
        "female",
        "emop",
        "general_anes",
        "proc_axis",
        "anstart_time",
        "anend_time",
        "opstart_time",
        "opend_time",
        "icuin_time",
        "icuout_time",
        "icu_stay_gt24h",
        "icu_stay_gt48h",
        "death_inhosp",
        "kidney_event",
        "los_total_days",
        "los_postop_days",
        "indication_group",
        "charlson_index",
        "infection_related",
        "tumour_related",
        "fracture_related",
        "car_high",
        "phenotype",
        "alb_use",
        "icu_stay_hr",
        "icu_before_opend",
        "subject_id",
        "discharge_time",
        "obs_duration_proxy",
    ]
    for c in need_out:
        if c not in m.columns:
            m[c] = np.nan
    return m[need_out].copy()


def build_duration(ops_full: pd.DataFrame, formal: pd.DataFrame, primary: pd.DataFrame) -> pd.DataFrame:
    ops_full = ops_full.copy()
    ops_full["op_id"] = ops_full["op_id"].astype(np.int64)
    os65 = ops_full.loc[
        (ops_full["department"].astype(str) == "OS")
        & (pd.to_numeric(ops_full["age"], errors="coerce") >= 65)
    ].copy()
    os65["opstart_time"] = pd.to_numeric(os65["opstart_time"], errors="coerce")
    os65 = os65.sort_values(["subject_id", "opstart_time"]).drop_duplicates("subject_id", keep="first")

    formal = formal.copy()
    formal["op_id"] = formal["op_id"].astype(np.int64)
    fcols = [
        c
        for c in (
            "op_id",
            "bmi",
            "asa",
            "emop",
            "op_duration_min",
            "death_inhosp",
            "icu_admission",
            "lab_hb",
            "lab_creatinine",
            "lab_albumin",
            "labs_glucose_last_preop7d",
            "sex",
            "antype",
            "charlson_index",
        )
        if c in formal.columns
    ]
    dur = os65.merge(formal[fcols], on="op_id", how="inner", suffixes=("", "_f"))
    dur["female"] = (dur["sex"].astype(str).str.upper().isin(["F", "FEMALE", "1"])).astype(float)
    dur["hb"] = pd.to_numeric(dur.get("lab_hb", np.nan), errors="coerce")
    dur["creatinine"] = pd.to_numeric(dur.get("lab_creatinine", np.nan), errors="coerce")
    dur["albumin"] = pd.to_numeric(dur.get("lab_albumin", np.nan), errors="coerce")
    dur["glucose"] = pd.to_numeric(dur.get("labs_glucose_last_preop7d", np.nan), errors="coerce")
    for c in ("age", "asa", "emop", "bmi", "op_duration_min"):
        dur[c] = pd.to_numeric(dur[c], errors="coerce")
    dur["general_anes"] = (
        dur["antype"].astype(str).str.contains("General", case=False, na=False)
    ).astype(float)
    dur["proc_axis"] = "other_orthopedic"
    dur["obs_duration_proxy"] = dur["op_duration_min"]
    dur["car"] = np.nan
    liu = [
        "age",
        "female",
        "asa",
        "emop",
        "bmi",
        "hb",
        "albumin",
        "creatinine",
        "glucose",
        "op_duration_min",
    ]
    dur_cc = dur.dropna(subset=liu + ["icu_admission", "anstart_time", "anend_time"]).copy()
    dur_cc = dur_cc.merge(
        primary[["op_id", "map65_min"]].rename(columns={"map65_min": "map65_pub"}),
        on="op_id",
        how="left",
    )
    dur_cc["map65_min"] = dur_cc["map65_pub"]
    keep_d = [
        "op_id",
        "icu_admission",
        "car",
        "albumin",
        "map65_min",
        "age",
        "asa",
        "op_duration_min",
        "creatinine",
        "bmi",
        "hb",
        "glucose",
        "female",
        "emop",
        "general_anes",
        "proc_axis",
        "anstart_time",
        "anend_time",
        "opstart_time",
        "opend_time",
        "icuin_time",
        "death_inhosp",
        "obs_duration_proxy",
        "charlson_index",
    ]
    for c in keep_d:
        if c not in dur_cc.columns:
            dur_cc[c] = np.nan
    return dur_cc[keep_d].copy()


def build_car_available(formal: pd.DataFrame, ops: pd.DataFrame) -> pd.DataFrame:
    car_av = formal.copy()
    car_av["op_id"] = car_av["op_id"].astype(np.int64)
    car_av["car"] = np.nan
    if {"labs_crp_last_preop7d", "labs_albumin_last_preop7d"}.issubset(car_av.columns):
        crp = pd.to_numeric(car_av["labs_crp_last_preop7d"], errors="coerce")
        alb = pd.to_numeric(car_av["labs_albumin_last_preop7d"], errors="coerce")
        car_av["car"] = np.where(alb > 0, crp / alb, np.nan)
    car_av = car_av.loc[car_av["car"].notna()].copy()
    ops = ops.copy()
    ops["op_id"] = ops["op_id"].astype(np.int64)
    time_cols = [
        c
        for c in ("op_id", "anstart_time", "anend_time", "opstart_time", "opend_time", "icuin_time")
        if c in ops.columns
    ]
    car_av = car_av.merge(ops[time_cols], on="op_id", how="left")
    car_av["female"] = (car_av["sex"].astype(str).str.upper() == "F").astype(float)
    car_av["hb"] = pd.to_numeric(car_av.get("lab_hb", np.nan), errors="coerce")
    car_av["creatinine"] = pd.to_numeric(car_av.get("lab_creatinine", np.nan), errors="coerce")
    car_av["albumin"] = pd.to_numeric(car_av.get("lab_albumin", np.nan), errors="coerce")
    car_av["glucose"] = pd.to_numeric(car_av.get("labs_glucose_last_preop7d", np.nan), errors="coerce")
    car_av["general_anes"] = (
        car_av["antype"].astype(str).str.contains("General", case=False, na=False)
    ).astype(float)
    car_av["proc_axis"] = "other_orthopedic"
    car_av["map65_min"] = np.nan
    keep_c = [
        "op_id",
        "icu_admission",
        "car",
        "albumin",
        "map65_min",
        "age",
        "asa",
        "op_duration_min",
        "creatinine",
        "bmi",
        "hb",
        "glucose",
        "female",
        "emop",
        "general_anes",
        "proc_axis",
        "anstart_time",
        "anend_time",
        "opstart_time",
        "opend_time",
        "icuin_time",
        "death_inhosp",
    ]
    for c in keep_c:
        if c not in car_av.columns:
            car_av[c] = np.nan
    return car_av[keep_c].copy()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=None, help="JSON config (see config/prepare_rerun_inputs.example.json)")
    p.add_argument("--project-root", type=Path, default=None)
    p.add_argument("--inspire-raw-dir", type=Path, default=None)
    p.add_argument("--dcc-csv", type=Path, default=None)
    p.add_argument("--mc9-annotated-csv", type=Path, default=None)
    p.add_argument("--icu-aki-fields-csv", type=Path, default=None)
    p.add_argument("--car-formal-csv", type=Path, default=None)
    p.add_argument("--out-dir", type=Path, default=None)
    p.add_argument("--car-cut", type=float, default=None)
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    project_root = Path(
        args.project_root or cfg.get("project_root") or Path.cwd()
    ).resolve()

    inspire_raw = resolve(project_root, args.inspire_raw_dir, cfg.get("inspire_raw_dir", "data/inspire"))
    dcc_csv = resolve(
        project_root,
        args.dcc_csv,
        cfg.get("dcc_csv", "results/car_ioh_icu_os65/01_Table01_baseline/Table01_analytic_cohort_Dcc.csv"),
    )
    mc9_csv = resolve(
        project_root,
        args.mc9_annotated_csv,
        cfg.get("mc9_annotated_csv", "data/derived_verification/Dcc_MC9_annotated.csv"),
    )
    ext_csv = resolve(
        project_root,
        args.icu_aki_fields_csv,
        cfg.get("icu_aki_fields_csv", "data/mc2_inspire_os65_icu_aki_fields.csv"),
    )
    formal_csv = resolve(
        project_root,
        args.car_formal_csv,
        cfg.get("car_formal_csv", "data/inspire_os65_car_formal.csv"),
    )
    out_dir = resolve(project_root, args.out_dir, cfg.get("out_dir", "data/derived"))
    car_cut = float(args.car_cut if args.car_cut is not None else cfg.get("car_cut", CAR_CUT_DEFAULT))
    expected = {
        "primary": int(cfg.get("expected_n_primary", 3936)),
        "duration": int(cfg.get("expected_n_duration", 4023)),
        "car_available": int(cfg.get("expected_n_car_available", 4529)),
    }

    ops_path = inspire_raw / "operations.csv.gz"
    for path in (dcc_csv, mc9_csv, ext_csv, formal_csv, ops_path):
        if not path.exists():
            raise SystemExit(f"Required input not found: {path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    dcc = pd.read_csv(dcc_csv, low_memory=False)
    mc9 = pd.read_csv(mc9_csv, low_memory=False)
    ext = pd.read_csv(ext_csv, low_memory=False)
    ops = pd.read_csv(ops_path, low_memory=False)
    formal = pd.read_csv(formal_csv, low_memory=False)

    primary = build_primary(dcc, ops, ext, mc9, car_cut)
    duration = build_duration(ops, formal, primary)
    car_av = build_car_available(formal, ops)

    paths = {
        "primary_cohort_dcc_enriched.csv": primary,
        "duration_cohort_4023.csv": duration,
        "car_available_4529.csv": car_av,
    }
    for name, df in paths.items():
        out_path = out_dir / name
        df.to_csv(out_path, index=False)
        print(f"Wrote {out_path} n={len(df)}")

    meta = {
        "n_primary": int(len(primary)),
        "n_duration": int(len(duration)),
        "n_car_available": int(len(car_av)),
        "expected_n": expected,
        "car_cut": car_cut,
        "inputs": {
            "dcc_csv": str(dcc_csv),
            "mc9_annotated_csv": str(mc9_csv),
            "icu_aki_fields_csv": str(ext_csv),
            "car_formal_csv": str(formal_csv),
            "operations": str(ops_path),
        },
        "outputs": {k: str(out_dir / k) for k in paths},
        "notes": [
            "analysis/rerun_pipeline.py rebuilds MAP duration from vitals and applies the locked timing rule.",
            "Row counts should match expected_n when using the locked verification extracts; mismatches indicate a different extract version.",
        ],
    }
    (out_dir / "prepare_rerun_inputs_meta.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for key, n_key in (("primary", "n_primary"), ("duration", "n_duration"), ("car_available", "n_car_available")):
        got = meta[n_key]
        exp = expected[key]
        if got != exp:
            print(
                f"WARNING: {key} n={got} differs from locked expected n={exp}",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
