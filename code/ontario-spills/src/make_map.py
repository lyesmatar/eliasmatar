"""
make_map.py - Map spills per 100 km2 by quaternary watershed (2023-2025).

Downloads the Ontario Watershed Boundaries (OWB) quaternary layer from the
Province's open-data map service (Land Information Ontario), joins it to the
table made by make_map_table.py on the watershed code, and draws the map.

Spills are divided by watershed area because a large watershed collects more
reports just by being large.

Output: output/figures/spills_watershed_map.png
        output/tables/watershed_map_join_check.csv  (codes that did not match)
"""

import json
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
import requests
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch, Rectangle
from matplotlib_scalebar.scalebar import ScaleBar
from shapely.geometry import box

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "output" / "tables" / "spills_by_quaternary_watershed_2023_2025.csv"
OWB = ROOT / "data" / "external" / "owb_main_units.geojson"
FIG = ROOT / "output" / "figures" / "spills_watershed_map.png"
CHECK = ROOT / "output" / "tables" / "watershed_map_join_check.csv"

OWB_URL = ("https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/"
           "LIO_OPEN_DATA/LIO_Open04/MapServer/27/query")
# "OWB Main - All Watershed Units". The separate quaternary layer (MapServer/1)
# leaves out the Lake Ontario shoreline strips (e.g. Highland Creek, Mimico);
# this layer covers all of Ontario, so units are dissolved to quaternary code.
CRS = 3161  # NAD83 / Ontario MNR Lambert, keeps areas true

BREAKS = [0, 0.001, 1, 5, 20, 50, 150, 100_000]
LABELS = ["No reports", "Under 1", "1 to 5", "5 to 20", "20 to 50", "50 to 150", "150 or more"]
COLORS = ["#f2f2f0", "#fee5d9", "#fcbba1", "#fc9272", "#fb6a4a", "#de2d26", "#67000d"]

LABEL_NUDGE = {"02HC-02": (-9_000, 3_000), "02HC-06": (4_000, -6_000)}  # metres
GTA_BOX = (1_318_000, 11_855_000, 1_408_000, 11_945_000)  # Hamilton to Pickering, Lake Ontario to Oak Ridges


def download_owb() -> None:
    """Page through the map service (max 2,000 features per request)."""
    features, offset = [], 0
    while True:
        r = requests.get(OWB_URL, params={
            "where": "1=1", "outFields": "QUATERNARY_WATERSHED_CODE,QUATERNARY_WATERSHED_NAME,AREA_HECTARE",
            "returnGeometry": "true", "outSR": CRS, "maxAllowableOffset": 100,
            "resultOffset": offset, "resultRecordCount": 1000, "f": "geojson"}, timeout=300)
        r.raise_for_status()
        batch = r.json()["features"]
        features += batch
        print(f"  downloaded {len(features)} watersheds")
        if len(batch) < 1000:
            break
        offset += 1000
    OWB.parent.mkdir(parents=True, exist_ok=True)
    OWB.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def main() -> None:
    if not OWB.exists():
        print("Downloading Ontario Watershed Boundaries (quaternary)...")
        download_owb()
    units = gpd.read_file(OWB).set_crs(CRS, allow_override=True)
    units["geometry"] = units.buffer(0)  # repair a few self-crossing outlines
    sheds = units.dissolve("QUATERNARY_WATERSHED_CODE", aggfunc={
        "QUATERNARY_WATERSHED_NAME": "first", "AREA_HECTARE": "sum"}).reset_index()
    sheds = sheds.rename(columns={"QUATERNARY_WATERSHED_CODE": "WATERSHED_CODE",
                                  "QUATERNARY_WATERSHED_NAME": "WATERSHED_NAME"})
    spills = pd.read_csv(TABLE)

    # Check the join before trusting the map.
    missing = spills[~spills.quat_code.isin(sheds.WATERSHED_CODE)]
    missing.to_csv(CHECK, index=False)
    print(f"{len(sheds)} watersheds in OWB; {len(spills)} with spills; "
          f"{len(missing)} spill codes not found in OWB ({missing.spills.sum()} spills)")

    m = sheds.merge(spills, left_on="WATERSHED_CODE", right_on="quat_code", how="left")
    m["spills"] = m.spills.fillna(0)
    m["per100km2"] = m.spills / (m.AREA_HECTARE / 10_000)
    print(m.per100km2.describe())
    m.sort_values("per100km2", ascending=False)[
        ["WATERSHED_CODE", "WATERSHED_NAME", "spills", "per100km2"]].head(10).pipe(print)

    cmap, norm = ListedColormap(COLORS), BoundaryNorm(BREAKS, len(COLORS))

    fig = plt.figure(figsize=(13, 8.2), dpi=300)
    ax_main = fig.add_axes([0.02, 0.10, 0.60, 0.80])
    ax_gta = fig.add_axes([0.63, 0.30, 0.35, 0.60])

    # Codes ending in "00" are not quaternary watersheds: the Great Lakes, their
    # shoreline strips and areas outside Ontario. No report uses these codes
    # (shoreline reports carry older codes such as 02HC-09), so they are shown
    # hatched rather than as "No reports".
    other = m.WATERSHED_CODE.str.endswith("00")
    quat = m[~other]
    for ax in (ax_main, ax_gta):
        m[other].plot(ax=ax, facecolor="white", edgecolor="#dedede", hatch="///", linewidth=0.15)
        quat.plot(column="per100km2", cmap=cmap, norm=norm, ax=ax,
                  edgecolor="#9a9a9a", linewidth=0.15)
        ax.set_axis_off()
    sx0, sy0, sx1, sy1 = quat.cx[:, :12_250_000].total_bounds  # southern Ontario
    ax_main.set_xlim(sx0 - 10_000, sx1 + 10_000)
    ax_main.set_ylim(sy0 - 10_000, sy1 + 10_000)

    x0, y0, x1, y1 = GTA_BOX
    ax_gta.set_xlim(x0, x1)
    ax_gta.set_ylim(y0, y1)
    ax_main.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, lw=1, ec="black"))
    for ax in (ax_main, ax_gta):
        ax.add_artist(ScaleBar(1, units="m", location="lower right", box_alpha=0.7, font_properties={"size": 7}))
    for side in ["top", "bottom", "left", "right"]:
        ax_gta.spines[side].set_visible(True)
    ax_gta.set_axis_on()
    ax_gta.set_xticks([])
    ax_gta.set_yticks([])
    ax_gta.set_xlabel("")
    ax_gta.set_ylabel("")

    # Label the busiest GTA watersheds in the close-up.
    gta = m.cx[x0:x1, y0:y1]
    for _, row in gta.nlargest(5, "spills").iterrows():
        p = row.geometry.intersection(box(x0, y0, x1, y1)).representative_point()
        dx, dy = LABEL_NUDGE.get(row.WATERSHED_CODE, (0, 0))  # keep labels apart
        p = type(p)(p.x + dx, p.y + dy)
        if x0 < p.x < x1 and y0 < p.y < y1:
            ax_gta.annotate(f"{row.WATERSHED_NAME}\n{int(row.spills)} reports", (p.x, p.y),
                            fontsize=6, ha="center", va="center",
                            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.75))
    ax_gta.set_title("Greater Toronto Area", fontsize=10, loc="left")

    ax_main.annotate("N", xy=(0.04, 0.93), xytext=(0.04, 0.85), xycoords="axes fraction",
                     ha="center", fontsize=10, fontweight="bold",
                     arrowprops=dict(arrowstyle="-|>", color="black", lw=1.2))

    fig.legend(handles=[Patch(fc=c, ec="#9a9a9a", label=l) for c, l in zip(COLORS, LABELS)]
               + [Patch(fc="white", ec="#c8c8c8", hatch="///", label="Lake, shoreline or\noutside Ontario")],
               title="Spill reports per 100 km²", loc="lower left",
               bbox_to_anchor=(0.64, 0.10), ncol=2, fontsize=8, title_fontsize=9, frameon=False)
    fig.suptitle("Spill reports per 100 km² by watershed, southern Ontario, 2023–2025",
                 x=0.02, ha="left", fontsize=14, fontweight="bold")
    fig.text(0.02, 0.03,
             "Data: Ontario Ministry of the Environment, Conservation and Parks, Environmental Occurrences and Spills "
             "(2023–2025), counted by the quaternary watershed in each report;\n"
             "Ontario Watershed Boundaries (quaternary), Ontario Ministry of Natural Resources. "
             "Contains information licensed under the Open Government Licence – Ontario. "
             "Projection: NAD83 / Ontario MNR Lambert. Map: Elias Matar, October 2026.\n"
             "About 7% of reports list an older watershed code not in the current boundary layer and are not mapped.",
             fontsize=6.5, color="#444")

    fig.savefig(FIG, dpi=300, facecolor="white")
    print(f"Saved {FIG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
