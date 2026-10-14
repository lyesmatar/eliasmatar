"""
get_spill_data.py - Download the Spills Action Centre open data files from
the Ontario Data Catalogue (dataset: "Environmental Occurrences and Spills",
Open Government Licence - Ontario) into data/raw/.

Run from the project folder:  python src/get_spill_data.py
"""

from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
BASE = "https://files.ontario.ca/moe_mapping/downloads"

FILES = {
    "spill_occurrences_2003-2022.csv": f"{BASE}/4Other/SAC/spill_occurrences_2003-2022.csv",
    "spill_occurrences_2023.xlsx": f"{BASE}/4Other/SAC/spill_occurrences_2023.xlsx",
    "spill_occurrences_2024.xlsx": f"{BASE}/4Other/SAC/spill_occurrences_2024.xlsx",
    "spill_occurrences_2025.csv": f"{BASE}/4Other/SAC/spill_occurrences_2025.csv",
    "Spills_metadata_EN.pdf": f"{BASE}/metadata/opendata/Spills_metadata_EN.pdf",
}


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        target = RAW / name
        if target.exists():
            print(f"  already have {name}")
            continue
        r = requests.get(url, timeout=300)
        r.raise_for_status()
        target.write_bytes(r.content)
        print(f"  downloaded {name} ({len(r.content) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
