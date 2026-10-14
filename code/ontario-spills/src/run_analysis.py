"""
run_analysis.py - Run every query in sql/analysis_queries.sql against
data/spills.db, save each result as a CSV, and draw the summary charts.

Outputs:
  output/tables/<query name>.csv
  output/figures/*.png

Run from the project folder:  python src/run_analysis.py
"""

import re
import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "spills.db"
SQL_FILE = ROOT / "sql" / "analysis_queries.sql"
TABLES = ROOT / "output" / "tables"
FIGURES = ROOT / "output" / "figures"

BLUE, BROWN, GREY = "#3a6f9a", "#9a6b3a", "#9aa5ad"


def load_queries(path: Path) -> dict:
    """Split the .sql file into {name: query} using the '-- name:' markers."""
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^-- name:\s*(\w+)\s*$", text, flags=re.MULTILINE)
    # parts = [header, name1, sql1, name2, sql2, ...]
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}


def style(ax, title, ylabel=None):
    ax.set_title(title, loc="left", fontsize=12)
    if ylabel:
        ax.set_ylabel(ylabel)
    ax.spines[["top", "right"]].set_visible(False)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIGURES / name, dpi=150)
    plt.close(fig)
    print(f"  figure  output/figures/{name}")


def main() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)

    results = {}
    with sqlite3.connect(DB) as con:
        for name, sql in load_queries(SQL_FILE).items():
            results[name] = pd.read_sql(sql, con)
            results[name].to_csv(TABLES / f"{name}.csv", index=False)
            print(f"  table   output/tables/{name}.csv  ({len(results[name])} rows)")

    # 1. Spills per year
    df = results["spills_per_year"]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(df.year, df.spills, color=GREY, label="All spills")
    ax.bar(df.year, df.reached_water, color=BLUE, label="Reached water")
    style(ax, "Spills reported to Ontario's Spills Action Centre, 2003-2025", "Reports per year")
    ax.legend(frameon=False)
    save(fig, "spills_per_year.png")

    # 2. Which contaminants reach water (exclude the catch-all group)
    df = results["contaminants"]
    df = df[df.contaminant_group != "Other / not stated"].sort_values("pct_reached_water")
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(df.contaminant_group, df.pct_reached_water, color=BLUE)
    for y, (pct, n) in enumerate(zip(df.pct_reached_water, df.spills)):
        ax.text(pct + 1, y, f"{pct:.0f}%  (n={n:,})", va="center", fontsize=8)
    ax.set_xlim(0, 100)
    style(ax, "Share of spills that reached water, by substance (2003-2025)")
    ax.set_xlabel("% of reports where water was a receiving medium")
    save(fig, "contaminants_reaching_water.png")

    # 3. Weather-caused spills by month
    df = results["weather_spills_by_month"]
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(df.month, df.weather_spills, color=GREY, label="All weather-caused spills")
    ax.bar(df.month, df.sewage, color=BROWN, label="Sewage")
    ax.set_xticks(range(1, 13), months)
    style(ax, "Spills caused by weather, by month (2003-2025)", "Reports")
    ax.legend(frameon=False)
    save(fig, "weather_spills_by_month.png")

    # 4. Conservation authorities, 2023-2025
    df = results["conservation_authorities_2023_2025"].head(10).iloc[::-1]
    colors = [BLUE if "Toronto" in n else GREY for n in df.conservation_authority]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.barh(df.conservation_authority, df.spills, color=colors)
    for y, (n, pct) in enumerate(zip(df.spills, df.pct_of_ontario)):
        ax.text(n + 40, y, f"{n:,}  ({pct:.0f}%)", va="center", fontsize=8)
    style(ax, "Spills by conservation authority area, 2023-2025")
    ax.set_xlabel("Reports")
    save(fig, "conservation_authorities.png")


if __name__ == "__main__":
    main()
