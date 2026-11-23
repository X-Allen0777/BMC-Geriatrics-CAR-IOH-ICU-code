# -*- coding: utf-8 -*-
"""ICU entry vs anaesthesia-window / MAP-epoch temporal audit.

Reproduces the Editor temporal-order check after exposure reconstruction:
- how many recorded ICU entries precede / coincide with / follow exposure-window end
- whether any in-window FINAL MAP epoch occurred at or after ICU entry

Usage (from repository root, venv activated):
  python analysis/audit_icu_map_timing.py --config config/config.json

Primary output:
  <out_dir>/timing_overlap_audit.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from rerun_pipeline import load_vitals, prepare, timing_rule  # noqa: E402


def _root_from_config(cfg_path: Path) -> Path:
    return cfg_path.resolve().parent.parent


def final_inwindow_epochs(vitals: pd.DataFrame, ops: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """FINAL epochs inside the half-open anaesthesia window (same rules as build_exposure)."""
    lo, hi = cfg["phys_range"]
    low = cfg["map_low"]
    v = vitals.drop_duplicates(["op_id", "chart_time", "item_name", "value"])
    g = v.groupby(["op_id", "chart_time", "item_name"])["value"].transform("nunique")
    v = v[g == 1]
    wide = (
        v.pivot_table(
            index=["op_id", "chart_time"],
            columns="item_name",
            values="value",
            aggfunc="first",
        )
        .reset_index()
    )
    for c in ("art_mbp", "nibp_mbp"):
        if c not in wide.columns:
            wide[c] = np.nan

    w = ops[["op_id", "anstart_time", "anend_time", "opstart_time", "opend_time", "icuin_time"]].drop_duplicates(
        "op_id"
    ).copy()
    w["anstart_time"] = w["anstart_time"].fillna(w["opstart_time"])
    w["anend_time"] = w["anend_time"].fillna(w["opend_time"])
    wide = wide.merge(
        w[["op_id", "anstart_time", "anend_time", "icuin_time"]],
        on="op_id",
        how="inner",
    )
    inwin = (wide["chart_time"] >= wide["anstart_time"]) & (wide["chart_time"] < wide["anend_time"])
    ww = wide.loc[inwin].copy()
    art = ww["art_mbp"].where((ww["art_mbp"] >= lo) & (ww["art_mbp"] <= hi))
    nibp = ww["nibp_mbp"].where((ww["nibp_mbp"] >= lo) & (ww["nibp_mbp"] <= hi))
    ww["pref"] = art.where(art.notna(), nibp)
    ww = ww[ww["pref"].notna()].copy()
    ww["low_F"] = (ww["pref"] < low).astype(int)
    return ww


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cfg_path = Path(args.config)
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    root = _root_from_config(cfg_path)
    out = Path(args.out) if args.out else Path(cfg.get("out_dir", "rerun_out"))
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)

    prim = pd.read_csv(root / cfg["primary_cohort_csv"], low_memory=False)
    expo_path = out / "01_exposure_per_operation.csv"
    if not expo_path.exists():
        raise FileNotFoundError(
            f"Missing {expo_path}. Run analysis/rerun_pipeline.py first "
            "(or place 01_exposure_per_operation.csv in the output directory)."
        )
    expo = pd.read_csv(expo_path, low_memory=False)

    d = prepare(prim, expo, cfg)
    d, bad_ids = timing_rule(d)
    d = d.merge(
        expo[["op_id", "anstart_time", "anend_time"]],
        on="op_id",
        how="left",
        validate="one_to_one",
    )

    icu = d[d["icuin_time"].notna()].copy()
    n_icu = int(len(icu))
    before = int((icu["icuin_time"] < icu["anend_time"]).sum())
    coincide = int((icu["icuin_time"] == icu["anend_time"]).sum())
    after = int((icu["icuin_time"] > icu["anend_time"]).sum())

    ops = icu[
        ["op_id", "anstart_time", "anend_time", "opstart_time", "opend_time", "icuin_time"]
    ].drop_duplicates("op_id")
    vit = load_vitals(root / cfg["inspire_vitals"], ops["op_id"].tolist())
    epochs = final_inwindow_epochs(vit, ops, cfg)
    n_epochs = int(len(epochs))
    ge = epochs["chart_time"] >= epochs["icuin_time"]
    ge_icu = int(ge.sum()) if n_epochs else 0
    low_ge = int((ge & (epochs["low_F"] == 1)).sum()) if n_epochs else 0
    ops_any = (
        epochs.loc[ge, "op_id"].drop_duplicates().astype(int).tolist() if n_epochs else []
    )

    audit = {
        "primary_n_after_timing_rule": int(len(d)),
        "timing_rule_excluded_op_ids": [int(x) for x in bad_ids],
        "n_icu_admissions": n_icu,
        "icu_before_window_end": before,
        "icu_coincide_with_window_end": coincide,
        "icu_after_window_end": after,
        "n_inwindow_final_epochs_among_icu_ops": n_epochs,
        "n_epochs_chart_time_ge_icuin": ge_icu,
        "n_low_MAP_epochs_chart_time_ge_icuin": low_ge,
        "n_operations_with_any_epoch_ge_icuin": len(ops_any),
        "operations_with_any_epoch_ge_icuin": ops_any,
        "command": "python analysis/audit_icu_map_timing.py --config config/config.json",
        "output_file": "timing_overlap_audit.json",
    }
    dest = out / "timing_overlap_audit.json"
    dest.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
