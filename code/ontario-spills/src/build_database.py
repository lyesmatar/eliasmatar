"""
build_database.py - Combine 23 years of Ontario Spills Action Centre (SAC) reports
into one clean SQLite database.

The Ministry publishes the data in 4 files with 3 different layouts:
  - 2003-2022: one CSV, 14 columns, dates like 12/31/2022
  - 2023, 2024: Excel files, 25 columns (adds amounts, watersheds,
    conservation authority), mixed date formats
  - 2025: CSV, 25 columns, Windows (cp1252) text encoding

This script:
  1. reads each file with the right settings
  2. renames columns to one standard set (snake_case)
  3. parses dates and flags the ones that fail
  4. removes duplicate reports (same reference number)
  5. writes everything to data/spills.db (table: spills)
  6. prints a data-quality summary

Run from the project folder:  python src/build_database.py
"""

import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "spills.db"

# One standard name for every column, whatever the source file calls it.
RENAME = {
    "Date Reported": "date_reported",
    "Time Reported": "time_reported",
    "Reference Number": "reference_number",
    "Site Municipality": "municipality",
    "Contaminant Name": "contaminant",
    "Contaminant Amount": "amount",
    "Contaminant Unit": "unit",
    "Contaminant Material Type": "material_type",
    "Receiving Media": "receiving_media",
    "Offsite Impacts (Y/N)": "offsite_impact",
    "Waterbody Impacted (Y/N)": "waterbody_impacted",
    "Health Impact": "health_impact",
    "Environmental Impact": "environmental_impact",
    "Health/Environmental Consequence": "consequence",   # 2003-2022 spelling
    "Health/Environment Consequence": "consequence",     # 2023+ spelling
    "Sector Type": "sector",
    "Source Type": "source_type",
    "Source/Sector Type": "source_sector_type",
    "Incident Event": "incident_event",
    "Incident Reason": "incident_reason",
    "Conservation Authority Name": "conservation_authority",
    "Public Health Unit Name": "public_health_unit",
    "Primary Watershed": "watershed_primary",
    "Secondary Watershed": "watershed_secondary",
    "Tertiary Watershed": "watershed_tertiary",
    "Quaternary Watershed": "watershed_quaternary",
}


# Keyword -> group. Checked in order, first match wins, so put specific
# keywords (e.g. "transformer") before general ones (e.g. "oil").
CONTAMINANT_GROUPS = [
    ("natural gas", "Natural gas"),
    ("methane", "Natural gas"),
    ("sewage", "Sewage"),
    ("diesel", "Diesel"),
    ("gasoline", "Gasoline"),
    ("hydraulic", "Hydraulic oil"),
    ("transformer", "Transformer oil"),
    ("furnace", "Heating/furnace oil"),
    ("fuel oil", "Heating/furnace oil"),
    ("aviation fuel", "Other fuel"),
    ("propane", "Other fuel"),
    ("fuel", "Other fuel"),
    ("glycol", "Coolant/antifreeze"),
    ("coolant", "Coolant/antifreeze"),
    ("antifreeze", "Coolant/antifreeze"),
    (r"\boil", "Other oil"),     # \b = word start, so SOIL and BOILER don't count as oil
    ("ammonia", "Ammonia"),
    ("chlorin", "Chlorine/chlorinated water"),
    ("refrigerant", "Refrigerant"),
    ("freon", "Refrigerant"),
    ("sediment", "Sediment/silt"),
    ("suspended solids", "Sediment/silt"),
    ("silt", "Sediment/silt"),
    (r"\bmud\b", "Sediment/silt"),
    ("concrete", "Concrete/cement/slurry"),
    ("cement", "Concrete/cement/slurry"),
    ("slurry", "Concrete/cement/slurry"),
    ("douse water", "Firefighting water/foam"),
    ("fire water", "Firefighting water/foam"),
    ("fire suppressant", "Firefighting water/foam"),
    ("styrofoam", "Other / not stated"),   # plastic beads, not firefighting foam
    (r"\bfoam", "Firefighting water/foam"),
    ("grey water", "Wastewater/effluent"),
    ("wastewater", "Wastewater/effluent"),
    ("washwater", "Wastewater/effluent"),
    ("process water", "Wastewater/effluent"),
    ("effluent", "Wastewater/effluent"),
    ("sludge", "Wastewater/effluent"),
    ("bio-solids", "Wastewater/effluent"),
    ("smoke", "Smoke/particulates/dust"),
    ("particulate", "Smoke/particulates/dust"),
    ("opacity", "Smoke/particulates/dust"),
    (r"\bdust", "Smoke/particulates/dust"),   # not "industrial"
    ("manure", "Manure"),
]

# Note: a bare "rain" keyword would also match "drain", "train", "strain",
# so only whole phrases are used for weather.
REASON_GROUPS = [
    ("weather", "Weather"),
    ("storm", "Weather"),
    ("heavy rain", "Weather"),
    ("precipitation", "Weather"),
    ("flood", "Weather"),
    ("human", "Human error"),
    ("operator", "Human error"),
    ("equipment", "Equipment failure"),
    ("corrosion", "Equipment failure"),
    ("vandal", "Vandalism"),
    ("unknown", "Unknown"),
]


def group_by_keywords(values: pd.Series, groups: list) -> pd.Series:
    """Return a group label for each value, using the first keyword it contains.

    Keywords are regular expressions, so r"\\boil" means "oil at the start of
    a word" (matches "ENGINE OIL", not "SOIL").
    """
    text = values.fillna("").str.lower()
    result = pd.Series("Other / not stated", index=values.index)
    assigned = pd.Series(False, index=values.index)
    for keyword, label in groups:
        hit = text.str.contains(keyword, regex=True) & ~assigned
        result[hit] = label
        assigned |= hit
    return result


def read_source_files() -> pd.DataFrame:
    """Read the four raw files and stack them into one table."""
    frames = [
        # utf-8-sig skips the invisible "byte order mark" at the start of
        # this file - without it the first column name gets corrupted.
        ("2003-2022", pd.read_csv(RAW / "spill_occurrences_2003-2022.csv",
                                  dtype=str, encoding="utf-8-sig")),
        ("2023", pd.read_excel(RAW / "spill_occurrences_2023.xlsx", dtype=str)),
        ("2024", pd.read_excel(RAW / "spill_occurrences_2024.xlsx", dtype=str)),
        ("2025", pd.read_csv(RAW / "spill_occurrences_2025.csv",
                             dtype=str, encoding="cp1252")),
    ]
    tables = []
    for label, df in frames:
        df.columns = df.columns.str.strip()
        df = df.rename(columns=RENAME)
        df["source_file"] = label
        print(f"  read {label:<10} {len(df):>8,} rows, {df.shape[1]} columns")
        tables.append(df)
    return pd.concat(tables, ignore_index=True)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize text, parse dates, add helper columns."""
    # Trim stray spaces; treat empty strings and 'Unknown / N/A' as missing.
    for col in df.columns:
        df[col] = df[col].str.strip()
    df = df.replace({"": None, "Unknown / N/A": None})

    # Dates come as 12/31/2022, 2023/01/1, or 2024-12-31 00:00:00.
    # format="mixed" lets pandas work each one out; failures become NaT.
    df["date"] = pd.to_datetime(df["date_reported"], format="mixed", errors="coerce")
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month

    # Upper-case municipalities so "Toronto" and "TORONTO" count as one.
    # A few reports list two places ("MISSISSAUGA;TORONTO"); keep the first.
    df["municipality"] = df["municipality"].str.upper().str.split(";").str[0].str.strip()

    # Simple yes/no flag: did the spill reach water?
    # The wording changed over the years ("Water", "water", "Land, Water",
    # "Surface Water", "Land; Surface Water"), so match the word anywhere.
    df["to_water"] = (
        df["receiving_media"].fillna("").str.contains("water", case=False)
    ).astype(int)

    # Contaminant names are free text: "NATURAL GAS", "Natural Gas (Methane)",
    # "DIESEL FUEL", "Diesel Fuel"... Group them by keyword so they can be counted.
    df["contaminant_group"] = group_by_keywords(df["contaminant"], CONTAMINANT_GROUPS)
    df["reason_group"] = group_by_keywords(df["incident_reason"], REASON_GROUPS)

    # Amount is only reported from 2023; make it numeric.
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    return df


def main() -> None:
    print("Reading raw files...")
    df = read_source_files()
    rows_in = len(df)

    df = clean(df)

    # Same reference number reported twice = duplicate record.
    dupes = df.duplicated(subset="reference_number", keep="first")
    df = df[~dupes]

    df["date"] = df["date"].dt.strftime("%Y-%m-%d")   # SQLite stores dates as text

    with sqlite3.connect(DB_PATH) as con:
        df.to_sql("spills", con, if_exists="replace", index=False)
        con.execute("CREATE INDEX IF NOT EXISTS idx_date ON spills(date)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_muni ON spills(municipality)")

    print("\nData-quality summary")
    print(f"  rows read:              {rows_in:>8,}")
    print(f"  duplicates removed:     {dupes.sum():>8,}")
    print(f"  rows in database:       {len(df):>8,}")
    print(f"  dates that failed:      {df['date'].isna().sum():>8,}")
    print(f"  date range:             {df['date'].min()} to {df['date'].max()}")
    print(f"  reached water:          {df['to_water'].sum():>8,}")
    print(f"  contaminant ungrouped:  {(df['contaminant_group'] == 'Other / not stated').mean():>8.0%}")
    print(f"\nSaved {DB_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
