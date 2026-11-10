# -*- coding: utf-8 -*-
"""Nature-style Figure 2–4: TNR, white bg, PDF vector + 600 dpi TIFF, 3 palettes."""
from __future__ import annotations

import re
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

mpl.rcParams.update({
    "font.family": "Times New Roman",
    "font.size": 9,
    "axes.labelsize": 10,
    "axes.titlesize": 11,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 8,
    "axes.linewidth": 0.8,
    "axes.edgecolor": "#222222",
    "axes.facecolor": "white",
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
    "savefig.edgecolor": "white",
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "mathtext.fontset": "custom",
    "mathtext.rm": "Times New Roman",
    "mathtext.it": "Times New Roman:italic",
    "mathtext.bf": "Times New Roman:bold",
})

OUT = Path(__file__).resolve().parents[1] / "examples" / "figures_nature_variants"
OUT.mkdir(parents=True, exist_ok=True)
SRC = Path(__file__).resolve().parents[1] / "examples" / "aggregate_outputs"

# Three Nature-aligned, colorblind-friendly schemes
PALETTES = {
    "A_OkabeIto": {
        "label": "Scheme A — Okabe–Ito (Nature/CUD)",
        "groups": ["#0072B2", "#E69F00", "#009E73", "#D55E00"],
        "ci": "#0072B2",
        "line": "#D55E00",
        "ref": "#888888",
        "forest": "#0072B2",
        "null": "#666666",
    },
    "B_TolBright": {
        "label": "Scheme B — Paul Tol Bright",
        "groups": ["#4477AA", "#EE6677", "#228833", "#CCBB44"],
        "ci": "#4477AA",
        "line": "#EE6677",
        "ref": "#888888",
        "forest": "#4477AA",
        "null": "#666666",
    },
    "C_NatureClassic": {
        "label": "Scheme C — Nature classic navy–coral",
        "groups": ["#1B4F72", "#148F77", "#E67E22", "#C0392B"],
        "ci": "#1B4F72",
        "line": "#C0392B",
        "ref": "#7F8C8D",
        "forest": "#1B4F72",
        "null": "#5D6D7E",
    },
}

LABEL_MAP = {
    "overall": ("Overall", {}),
    "sg_age_ge75": ("Age", {0: "<75 y", 1: "≥75 y"}),
    "sg_female": ("Sex", {0: "Male", 1: "Female"}),
    "sg_asa_ge3": ("ASA", {0: "ASA <3", 1: "ASA ≥3"}),
    "sg_opdur_gt_median": ("Operative duration", {0: "≤ median", 1: "> median"}),
    "sg_general_anes": ("Anaesthesia", {0: "Non-general", 1: "General"}),
}


def parse_ci(s):
    if pd.isna(s):
        return np.nan, np.nan, np.nan
    s = str(s)
    if "reference" in s.lower():
        return 0.0, np.nan, np.nan
    m = re.search(r"([-\d.]+)\s*\(\s*([-\d.]+)\s*to\s*([-\d.]+)\s*\)", s)
    if not m:
        return np.nan, np.nan, np.nan
    return float(m.group(1)), float(m.group(2)), float(m.group(3))


def fmt_p(p):
    if pd.isna(p):
        return None
    s = str(p).strip()
    if s.startswith("<"):
        return f"P {s}"
    try:
        pv = float(s)
    except Exception:
        return f"P = {s}"
    if pv < 0.001:
        return "P < 0.001"
    return f"P = {pv:.3f}"


def style_ax(ax):
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("#222222")
        spine.set_linewidth(0.8)
    ax.tick_params(colors="#222222", width=0.7, length=3.5)
    ax.yaxis.grid(False)
    ax.xaxis.grid(False)


def save_fig(fig, stem, palette_key):
    d = OUT / palette_key
    d.mkdir(parents=True, exist_ok=True)
    pdf = d / f"{stem}.pdf"
    tiff = d / f"{stem}.tiff"
    png = d / f"{stem}.png"
    fig.savefig(pdf, format="pdf", bbox_inches="tight", dpi=600)
    fig.savefig(tiff, format="tiff", dpi=600, pil_kwargs={"compression": "tiff_lzw"})
    fig.savefig(png, format="png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    return pdf, tiff


def load_data():
    t2 = pd.read_csv(SRC / "02_primary_table2.csv")
    t2 = t2.rename(columns={t2.columns[0]: "group"})
    boot = pd.read_csv(SRC / "02_primary_boot_summary.csv")
    curve = pd.read_csv(SRC / "08_figure3_curve_on_5min_grid.csv")
    sg = pd.read_csv(SRC / "10_figure4_subgroups.csv")

    rows = []
    for _, r in t2.iterrows():
        rd, rd_lo, rd_hi = parse_ci(r["RD_vs_Neither_pp"])
        orv, or_lo, or_hi = parse_ci(r["OR_Wald"])
        risk, risk_lo, risk_hi = parse_ci(r["std_risk_pct"])
        rows.append({
            "group": r["group"],
            "n": int(r["n"]),
            "events": int(r["events"]),
            "risk": risk,
            "risk_lo": risk_lo,
            "risk_hi": risk_hi,
            "RD": rd,
            "RD_lo": rd_lo,
            "RD_hi": rd_hi,
            "OR": orv,
            "OR_lo": or_lo,
            "OR_hi": or_hi,
        })
    gdf = pd.DataFrame(rows)
    p_both = boot.loc[boot.estimand == "RD_G11_vs_G00", "p_boot_display"].iloc[0]
    p_ic = boot.loc[boot.estimand == "IC_RD", "p_boot_display"].iloc[0]
    return gdf, curve, sg, p_both, p_ic


def fig2(pal, key, gdf, p_both, p_ic):
    colors = pal["groups"]
    order = {g: i for i, g in enumerate(["Neither", "High CAR only", "IOH >=30 min only", "Both"])}
    d = gdf.copy()
    d["ord"] = d["group"].map(order)
    d = d.sort_values("ord").reset_index(drop=True)
    x = np.arange(len(d))

    fig, ax = plt.subplots(figsize=(6.5, 4.4), dpi=150)
    style_ax(ax)
    ax.bar(x, d["risk"].values, color=colors, width=0.62, edgecolor="white", linewidth=0.6, zorder=3)
    yerr = np.vstack([
        d["risk"].values - d["risk_lo"].fillna(d["risk"]).values,
        d["risk_hi"].fillna(d["risk"]).values - d["risk"].values,
    ])
    ax.errorbar(x, d["risk"].values, yerr=yerr, fmt="none", ecolor="#222222",
                elinewidth=0.9, capsize=3, zorder=4)
    ax.set_xticks(x)
    ax.set_xticklabels(["Neither", "High CAR\nonly", "IOH ≥30 min\nonly", "Both"])
    ax.set_ylabel("Standardized ICU admission risk (%)")
    ymax = max(d["risk_hi"].fillna(d["risk"]).max() * 1.42, 22)
    ax.set_ylim(0, ymax)

    for i, r in d.iterrows():
        ytop = r["risk_hi"] if not pd.isna(r["risk_hi"]) else r["risk"]
        if r["group"] == "Neither":
            ax.text(i, ytop + 0.8, "Reference", ha="center", va="bottom", fontsize=8, color="#444444")
        else:
            ax.text(i, ytop + 0.7,
                    f"RD {r['RD']:.2f} ({r['RD_lo']:.2f}–{r['RD_hi']:.2f})",
                    ha="center", va="bottom", fontsize=7.5, color="#222222")
            if r["group"] == "Both":
                ax.text(i, ytop + 2.05, fmt_p(p_both), ha="center", va="bottom",
                        fontsize=8, fontweight="bold", fontstyle="italic", color="#111111")

    t0 = ax.text(
        0.01, -0.20, "Additive interaction (IC_RD): ",
        transform=ax.transAxes, fontsize=8, color="#111111", ha="left", va="top",
    )
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    bb = t0.get_window_extent(renderer=renderer)
    inv = ax.transAxes.inverted()
    x1, _ = inv.transform((bb.x1, bb.y0))
    ax.text(
        x1, -0.20, fmt_p(p_ic),
        transform=ax.transAxes, fontsize=8, fontweight="bold", fontstyle="italic",
        color="#111111", ha="left", va="top",
    )
    ax.set_title("Figure 2. Standardized ICU risk by CAR×IOH exposure", pad=10)
    fig.tight_layout()
    return save_fig(fig, "Figure2_std_risk", key)


def fig3(pal, key, curve):
    fig, ax = plt.subplots(figsize=(6.5, 4.2), dpi=150)
    style_ax(ax)
    x = curve["minutes"].values
    y = curve["OR"].values
    lo = curve["lo"].values
    hi = curve["hi"].values
    ax.fill_between(x, lo, hi, color=pal["ci"], alpha=0.22, linewidth=0, zorder=2)
    ax.plot(x, y, color=pal["line"], lw=1.8, zorder=3)
    ax.axhline(1.0, color=pal["ref"], lw=0.9, ls="--", zorder=1)
    ax.set_xlabel("Intraoperative hypotension duration (min)")
    ax.set_ylabel("Odds ratio for ICU admission")
    ax.set_xlim(0, float(max(x)))
    ax.set_ylim(0.8, max(float(hi.max()) * 1.08, 2.2))

    if (curve["minutes"] == 30).any():
        r30 = curve.loc[curve["minutes"] == 30].iloc[0]
        ax.plot(30, r30["OR"], "o", color=pal["line"], ms=5, zorder=4)
        ax.annotate(
            f"30 min: OR {r30['OR']:.2f}\n({r30['lo']:.2f}–{r30['hi']:.2f})",
            xy=(30, r30["OR"]), xytext=(38, r30["OR"] + 0.25),
            fontsize=8, color="#222222",
            arrowprops=dict(arrowstyle="->", color="#555555", lw=0.7),
        )
    ax.set_title("Figure 3. IOH duration–response (adjusted OR)", pad=10)
    fig.tight_layout()
    return save_fig(fig, "Figure3_IOH_dose_response", key)


def fig4(pal, key, sg):
    plot_rows = []
    for subg, g in sg.groupby("subgroup", sort=False):
        name, lvmap = LABEL_MAP[subg]
        if subg == "overall":
            r = g.iloc[0]
            plot_rows.append({
                "label": "Overall", "is_header": False,
                "OR": r["OR"], "lo": r["OR_lo"], "hi": r["OR_hi"],
                "p": r["p_wald"], "pint": None,
            })
        else:
            plot_rows.append({
                "label": name, "is_header": True,
                "OR": np.nan, "lo": np.nan, "hi": np.nan,
                "p": np.nan, "pint": g["p_interaction_LRT"].iloc[0],
            })
            for _, r in g.iterrows():
                lv = lvmap.get(int(r["level"]), str(r["level"]))
                plot_rows.append({
                    "label": f"   {lv}", "is_header": False,
                    "OR": r["OR"], "lo": r["OR_lo"], "hi": r["OR_hi"],
                    "p": r["p_wald"], "pint": None,
                })

    n = len(plot_rows)
    y = np.arange(n)[::-1]
    xmax = max(r["hi"] for r in plot_rows if not r["is_header"] and not pd.isna(r["hi"]))
    fig_h = max(5.4, 0.40 * n + 1.5)

    fig = plt.figure(figsize=(9.0, fig_h), dpi=150, facecolor="white")
    # left labels | forest | OR text | P text
    gs = fig.add_gridspec(
        1, 4, width_ratios=[1.55, 3.0, 1.55, 0.95], wspace=0.08,
        left=0.02, right=0.98, top=0.90, bottom=0.10,
    )
    axlab = fig.add_subplot(gs[0, 0])
    ax = fig.add_subplot(gs[0, 1])
    axor = fig.add_subplot(gs[0, 2])
    axp = fig.add_subplot(gs[0, 3])

    for a in (axlab, axor, axp):
        a.set_facecolor("white")
        a.set_xticks([])
        a.set_yticks([])
        for spine in a.spines.values():
            spine.set_visible(False)
        a.set_ylim(-0.5, n - 0.5)
        a.set_xlim(0, 1)

    style_ax(ax)
    ax.set_ylim(-0.5, n - 0.5)
    ax.axvline(1.0, color=pal["null"], lw=0.9, ls="--", zorder=1)

    axlab.text(0.0, n - 0.15, "Subgroup", fontsize=8, fontweight="bold", va="bottom", ha="left")
    axor.text(0.0, n - 0.15, "OR (95% CI)", fontsize=8, fontweight="bold", va="bottom", ha="left")
    axp.text(1.0, n - 0.15, "P", fontsize=8, fontweight="bold", fontstyle="italic",
             va="bottom", ha="right")

    for yi, row in zip(y, plot_rows):
        if row["is_header"]:
            axlab.text(
                0.0, yi, row["label"], fontsize=9, fontweight="bold",
                va="center", ha="left", color="#111111",
            )
            if row["pint"] is not None and not pd.isna(row["pint"]):
                axp.text(
                    1.0, yi, fmt_p(row["pint"]), fontsize=8,
                    fontweight="bold", fontstyle="italic",
                    va="center", ha="right", color="#111111",
                )
            continue

        ax.errorbar(
            row["OR"], yi,
            xerr=[[row["OR"] - row["lo"]], [row["hi"] - row["OR"]]],
            fmt="s", color=pal["forest"], ecolor=pal["forest"],
            elinewidth=1.1, capsize=2.5, markersize=5.5, zorder=3,
        )
        axlab.text(0.0, yi, row["label"], fontsize=8.5, va="center", ha="left", color="#222222")
        axor.text(
            0.0, yi, f"{row['OR']:.2f} ({row['lo']:.2f}–{row['hi']:.2f})",
            fontsize=8, va="center", ha="left", color="#222222",
        )
        axp.text(
            1.0, yi, fmt_p(row["p"]), fontsize=8, va="center", ha="right",
            fontweight="bold", fontstyle="italic", color="#111111",
        )

    ax.set_yticks([])
    ax.set_xlabel("Odds ratio (Both vs Neither)")
    ax.set_xscale("log")
    ax.set_xlim(0.35, max(10.0, float(xmax) * 1.08))
    ax.set_xticks([0.5, 1, 2, 4, 8])
    ax.xaxis.set_major_formatter(mticker.ScalarFormatter())
    fig.suptitle("Figure 4. Subgroup forest plot (Both vs Neither)",
                 fontsize=11, fontname="Times New Roman", y=0.98)
    # footnote: header-row P = interaction P
    fig.text(
        0.02, 0.015,
        "Note: P values in subgroup header rows are interaction P (likelihood-ratio test).",
        fontsize=7.5, fontstyle="italic", color="#333333",
    )
    return save_fig(fig, "Figure4_subgroup_forest", key)


def main():
    gdf, curve, sg, p_both, p_ic = load_data()
    lines = [
        "Nature-style figure variants for BMC Geriatrics CAR×IOH revision",
        "Font: Times New Roman | Background: white | Formats: PDF (vector) + TIFF 600 dpi (LZW)",
        "P values in figures: bold italic",
        "",
        "Schemes:",
    ]
    manifest = []
    for key, pal in PALETTES.items():
        lines.append(f"  {key}: {pal['label']}")
        lines.append(f"    colors: {', '.join(pal['groups'])}")
        print("===", key, pal["label"])
        for name, paths in [
            ("Fig2", fig2(pal, key, gdf, p_both, p_ic)),
            ("Fig3", fig3(pal, key, curve)),
            ("Fig4", fig4(pal, key, sg)),
        ]:
            pdf, tiff = paths
            print(f"  {name}: {pdf.name} + {tiff.name}")
            manifest.extend([str(pdf), str(tiff)])

    readme = OUT / "README_color_schemes.txt"
    readme.write_text("\n".join(lines) + "\n\nFiles:\n" + "\n".join(manifest), encoding="utf-8")
    print("DONE ->", OUT)


if __name__ == "__main__":
    main()
