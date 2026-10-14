"""
run_all.py - Rebuild the whole project from the raw files in one command.

    python run_all.py

Steps: download the spill data -> build the database -> download Pearson
rainfall -> run the SQL analysis and charts -> run the rain vs spills comparison.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = ["get_spill_data.py", "build_database.py", "get_weather.py", "run_analysis.py", "rain_and_spills.py",
         "make_map_table.py"]

for step in STEPS:
    print(f"\n=== {step} ===")
    subprocess.run([sys.executable, str(ROOT / "src" / step)], check=True, cwd=ROOT)

print("\nAll steps finished. Results are in output/.")
