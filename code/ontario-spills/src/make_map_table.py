"""
make_map_table.py - Count spills per quaternary watershed (2023-2025) so they
can be mapped in QGIS by joining to the Ontario Watershed Boundaries (OWB)
quaternary layer.

The SAC data has no coordinates, so spills can't be placed as points. From
2023 each report lists its quaternary watershed (e.g. "02HC-03 | West Humber
River"), which is the finest location available.

A report can list more than one watershed ("02LA-07 | Jock River; 02LA-01 |
Rideau Falls"), about 8% of reports. Those are counted once in each
watershed they list.

Output: output/tables/spills_by_quaternary_watershed_2023_2025.csv
  quat_code         e.g. 02HC-03   (use this to join in QGIS)
  quat_code_nodash  e.g. 02HC03    (in case the OWB layer writes codes without the dash)
  quat_name, spills, reached_water, pct_reached_water,
  sewage_to_water, fuel_oil_to_water
"""

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "spills.db"
OUT = ROOT / "output" / "tables" / "spills_by_quaternary_watershed_2023_2025.csv"

FUEL_OIL = ["Diesel", "Gasoline", "Hydraulic oil", "Other oil",
            "Heating/furnace oil", "Transformer oil", "Other fuel"]


def main() -> None:
    with sqlite3.connect(DB) as con:
        df = pd.read_sql("""SELECT reference_number, watershed_quaternary,
                                   to_water, contaminant_group
                            FROM spills
                            WHERE year >= 2023 AND watershed_quaternary IS NOT NULL""", con)

    # One row per (spill, watershed) when a report lists several watersheds.
    df["watershed_quaternary"] = df["watershed_quaternary"].str.split(";")
    df = df.explode("watershed_quaternary")

    # "02HC-03 | West Humber River" -> code "02HC-03", name "West Humber River".
    # Codes come in two forms, "02HC-03" and "02GHA02" (also "029C-02"), so take
    # whatever is before the "|" rather than assuming one pattern.
    parts = df["watershed_quaternary"].str.extract(r"^\s*([0-9A-Z]{4}-\d{2}|[0-9A-Z]{7})\s*(?:\|\s*(.*))?")
    df["quat_code"] = parts[0]
    df["quat_name"] = parts[1].str.strip()
    print(f"Watershed entries without a readable code: {df['quat_code'].isna().sum()}")
    df = df.dropna(subset=["quat_code"])

    df["sewage_to_water"] = ((df.contaminant_group == "Sewage") & (df.to_water == 1)).astype(int)
    df["fuel_oil_to_water"] = (df.contaminant_group.isin(FUEL_OIL) & (df.to_water == 1)).astype(int)

    table = df.groupby("quat_code").agg(
        quat_name=("quat_name", lambda s: s.dropna().mode().iat[0] if s.notna().any() else None),
        spills=("reference_number", "size"),
        reached_water=("to_water", "sum"),
        sewage_to_water=("sewage_to_water", "sum"),
        fuel_oil_to_water=("fuel_oil_to_water", "sum"),
    ).reset_index()
    table["pct_reached_water"] = (100 * table.reached_water / table.spills).round(1)
    table.insert(1, "quat_code_nodash", table.quat_code.str.replace("-", ""))
    table = table.sort_values("spills", ascending=False)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT, index=False)
    print(f"{len(table)} quaternary watersheds with spills (2023-2025)")
    print(table.head(10).to_string(index=False))
    print(f"\nSaved {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
