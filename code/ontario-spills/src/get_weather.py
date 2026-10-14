"""
get_weather.py - Download daily rainfall for Toronto Pearson Airport from
Environment and Climate Change Canada's open-data API (api.weather.gc.ca).

Pearson changed station ID on 2013-06-13, so the record comes in two parts:
  6158733  TORONTO LESTER B. PEARSON INT'L A   (to 2013-06-12)
  6158731  TORONTO INTL A                       (from 2013-06-13)

Output: data/external/pearson_daily_precip.csv  (date, precip_mm)

Run from the project folder:  python src/get_weather.py
"""

from io import StringIO
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "external" / "pearson_daily_precip.csv"

API = "https://api.weather.gc.ca/collections/climate-daily/items"
PARTS = [
    ("6158733", "2003-01-01", "2013-06-12"),
    ("6158731", "2013-06-13", "2025-12-31"),
]


def download(climate_id: str, start: str, end: str) -> pd.DataFrame:
    """Fetch one station's daily records as a table."""
    params = {
        "CLIMATE_IDENTIFIER": climate_id,
        "datetime": f"{start}/{end}",
        "properties": "LOCAL_DATE,TOTAL_PRECIPITATION",
        "sortby": "LOCAL_DATE",
        "limit": 10000,          # the API's maximum per request
        "f": "csv",
    }
    r = requests.get(API, params=params, timeout=120)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    print(f"  {climate_id}: {len(df):,} days ({start} to {end})")
    return df


def main() -> None:
    print("Downloading Pearson daily precipitation...")
    df = pd.concat([download(*p) for p in PARTS], ignore_index=True)
    df = pd.DataFrame({
        "date": pd.to_datetime(df["LOCAL_DATE"]).dt.strftime("%Y-%m-%d"),
        "precip_mm": df["TOTAL_PRECIPITATION"],
    }).sort_values("date")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"  missing days: {df['precip_mm'].isna().sum()}")
    print(f"Saved {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
