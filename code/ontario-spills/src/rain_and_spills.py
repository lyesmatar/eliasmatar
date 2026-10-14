"""
rain_and_spills.py - When a spill happens on a rainy day, is it more likely
to reach water?

Joins GTA spill reports (data/spills.db) to Pearson daily rainfall
(data/external/pearson_daily_precip.csv) by date, groups spills by how much
rain fell that day, and compares the share of spills that reached water.

Comparison: risk ratio (share reaching water on rainy days / share on dry
days) with a 95% confidence interval (standard log method):
    RR = (a / n1) / (c / n2)
    SE(log RR) = sqrt(1/a - 1/n1 + 1/c - 1/n2)
    95% CI = exp(log RR +/- 1.96 * SE)
If the interval does not include 1, the difference is unlikely to be chance.

Outputs:
  output/tables/rain_vs_spill_impact.csv
  output/tables/rain_vs_spill_impact_by_substance.csv
  output/figures/rain_vs_spill_impact.png
"""

import math
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "spills.db"
RAIN = ROOT / "data" / "external" / "pearson_daily_precip.csv"
TABLES = ROOT / "output" / "tables"
FIGURES = ROOT / "output" / "figures"

# Municipalities around Pearson / in the TRCA area.
GTA = ["TORONTO", "MISSISSAUGA", "BRAMPTON", "VAUGHAN", "MARKHAM",
       "RICHMOND HILL", "PICKERING", "AJAX", "CALEDON"]

RAIN_BINS = [-0.1, 0.2, 10, 25, 1000]
RAIN_LABELS = ["Dry (<0.2 mm)", "Light (0.2-10 mm)", "Moderate (10-25 mm)", "Heavy (25+ mm)"]

# Liquids that can be carried by runoff; compared on dry vs wet (10+ mm) days.
SUBSTANCES = ["Gasoline", "Other oil", "Diesel", "Hydraulic oil",
              "Coolant/antifreeze", "Sewage"]


def risk_ratio(hits_a, n_a, hits_b, n_b):
    """Risk ratio of group a vs group b, with a 95% confidence interval."""
    rr = (hits_a / n_a) / (hits_b / n_b)
    se = math.sqrt(1 / hits_a - 1 / n_a + 1 / hits_b - 1 / n_b)
    return rr, math.exp(math.log(rr) - 1.96 * se), math.exp(math.log(rr) + 1.96 * se)


def main() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)

    placeholders = ",".join("?" * len(GTA))
    with sqlite3.connect(DB) as con:
        spills = pd.read_sql(
            f"""SELECT date, to_water, contaminant_group
                FROM spills WHERE municipality IN ({placeholders})""",
            con, params=GTA)

    rain = pd.read_csv(RAIN).dropna(subset=["precip_mm"])
    spills = spills.merge(rain, on="date", how="inner")   # keep spills with a rain reading
    spills["rain_class"] = pd.cut(spills.precip_mm, RAIN_BINS, labels=RAIN_LABELS)

    # --- 1. All GTA spills: share reaching water, by rain class -------------
    table = spills.groupby("rain_class", observed=True).agg(
        spills=("to_water", "size"), reached_water=("to_water", "sum"))
    table["pct_reached_water"] = 100 * table.reached_water / table.spills
    dry = table.loc[RAIN_LABELS[0]]
    cis = [risk_ratio(r.reached_water, r.spills, dry.reached_water, dry.spills)
           for r in table.itertuples()]
    table["ratio_vs_dry"] = [c[0] for c in cis]
    table["ci_low"] = [c[1] for c in cis]
    table["ci_high"] = [c[2] for c in cis]
    table.round(3).to_csv(TABLES / "rain_vs_spill_impact.csv")

    print(f"GTA spills joined to Pearson rain: {len(spills):,} "
          f"({spills.date.min()} to {spills.date.max()})\n")
    print(table.round(2).to_string(), "\n")

    # --- 2. Same substance, dry vs wet day ------------------------------------
    spills["wet"] = spills.precip_mm >= 10
    rows = []
    for name in SUBSTANCES:
        sub = spills[spills.contaminant_group == name]
        d, w = sub[~sub.wet], sub[sub.wet]
        rr, lo, hi = risk_ratio(w.to_water.sum(), len(w), d.to_water.sum(), len(d))
        rows.append({"substance": name,
                     "spills_dry_day": len(d), "pct_water_dry": 100 * d.to_water.mean(),
                     "spills_wet_day": len(w), "pct_water_wet": 100 * w.to_water.mean(),
                     "ratio": rr, "ci_low": lo, "ci_high": hi})
    by_sub = pd.DataFrame(rows)
    by_sub.round(3).to_csv(TABLES / "rain_vs_spill_impact_by_substance.csv", index=False)
    print("Same substance, dry day vs wet day (10+ mm):")
    print(by_sub.round(2).to_string(index=False))

    # --- Chart ------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.8),
                                   gridspec_kw={"width_ratios": [1, 1.2]})
    ax1.bar(range(len(table)), table.pct_reached_water, color="#3a6f9a")
    for i, (pct, n) in enumerate(zip(table.pct_reached_water, table.spills)):
        ax1.text(i, pct + 1, f"{pct:.0f}%", ha="center", fontsize=10)
    ax1.set_xticks(range(len(table)),
                   [f"{l.split(' (')[0]}\n({l.split(' (')[1]}\nn={n:,}"
                    for l, n in zip(table.index, table.spills)], fontsize=8)
    ax1.set_ylim(0, 50)
    ax1.set_ylabel("% of spills that reached water")
    ax1.set_title("All GTA spills, by rain that day", loc="left", fontsize=11)

    y = range(len(by_sub))
    ax2.barh([i + 0.2 for i in y], by_sub.pct_water_dry, height=0.4,
             color="#9aa5ad", label="Dry day (<10 mm)")
    ax2.barh([i - 0.2 for i in y], by_sub.pct_water_wet, height=0.4,
             color="#3a6f9a", label="Wet day (10+ mm)")
    ax2.set_yticks(list(y), by_sub.substance)
    ax2.invert_yaxis()
    ax2.set_xlim(0, 90)
    ax2.set_xlabel("% of spills that reached water")
    ax2.set_title("Same substance, dry vs wet day", loc="left", fontsize=11)
    ax2.legend(frameon=False, loc="upper right")

    for ax in (ax1, ax2):
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Rain on the day of a spill makes it more likely to reach water "
                 "(GTA, 2003-2025)", x=0.01, ha="left", fontsize=12)
    fig.tight_layout()
    fig.savefig(FIGURES / "rain_vs_spill_impact.png", dpi=150)
    plt.close(fig)
    print("\nSaved output/figures/rain_vs_spill_impact.png")


if __name__ == "__main__":
    main()
