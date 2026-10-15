"""
make_map.py - Map spills per 100 km2 by quaternary watershed (2023-2025).

Downloads the Ontario Watershed Boundaries (OWB) quaternary layer from the
Province's open-data map service (Land Information Ontario), joins it to the
table made by make_map_table.py on watershed code and name, and draws the map.

Spills are divided by watershed area because a large watershed collects more
reports just by being large.

Output: output/figures/spills_watershed_map.png
        output/tables/watershed_map_join_check.csv  (how each code was matched)
        output/spills_watersheds_v2.gpkg  (joined layer for QGIS)
"""

import io
import json
import math
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import geopandas as gpd
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from PIL import Image
from pyproj import Transformer
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch, Rectangle
from matplotlib_scalebar.scalebar import ScaleBar
from shapely.geometry import box

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "output" / "tables" / "spills_by_quaternary_watershed_2023_2025.csv"
OWB = ROOT / "data" / "external" / "owb_main_units.geojson"
FIG = ROOT / "output" / "figures" / "spills_watershed_map.png"
CHECK = ROOT / "output" / "tables" / "watershed_map_join_check.csv"
GPKG = ROOT / "output" / "spills_watersheds_v2.gpkg"
PROVINCE = ROOT / "data" / "external" / "ontario_boundary.geojson"
MUNIS = ROOT / "data" / "external" / "municipal_boundaries.gpkg"  # LIO_Open03/MapServer/14
PROVINCE_URL = ("https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/"
                "LIO_OPEN_DATA/LIO_Open03/MapServer/0/query")

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

# The map is drawn in Web Mercator (EPSG:3857) so a tiled basemap fits under it.
# Rates were calculated from the official AREA_HECTARE field, so the projection
# only affects the drawing, not the numbers.
WEB = 3857
BASEMAP_URL = ("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/"
               "World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}")  # no key needed
BASEMAP_ATTR = "Basemap: Esri, HERE, Garmin, © OpenStreetMap contributors"
MAIN_CITIES = ["TORONTO", "OTTAWA", "HAMILTON", "LONDON", "WINDSOR", "KITCHENER", "BARRIE", "KINGSTON",
               "SUDBURY", "SAULT STE. MARIE", "PETERBOROUGH", "SARNIA", "NIAGARA FALLS",
               "BELLEVILLE", "NORTH BAY", "OWEN SOUND", "CORNWALL"]
# In the close-up the busiest watersheds get labelled boxes, so the cities under
# them (Toronto, Vaughan, Markham, Richmond Hill) are left out to avoid overlaps.
GTA_CITIES = ["MISSISSAUGA", "OAKVILLE", "BURLINGTON", "HAMILTON", "PICKERING", "MILTON", "NEWMARKET"]


def basemap(ax, bbox, zoom: int) -> None:
    """Draw Web Mercator basemap tiles covering bbox (x0, y0, x1, y1 in EPSG:3857)."""
    r = 6378137 * math.pi
    size = 2 * r / 2 ** zoom
    tx0, tx1 = int((bbox[0] + r) // size), int((bbox[2] + r) // size)
    ty0, ty1 = int((r - bbox[3]) // size), int((r - bbox[1]) // size)
    mosaic = Image.new("RGB", (256 * (tx1 - tx0 + 1), 256 * (ty1 - ty0 + 1)), "white")
    with requests.Session() as s:
        for tx in range(tx0, tx1 + 1):
            for ty in range(ty0, ty1 + 1):
                resp = s.get(BASEMAP_URL.format(z=zoom, x=tx, y=ty), timeout=60)
                if resp.ok:
                    mosaic.paste(Image.open(io.BytesIO(resp.content)).convert("RGB"),
                                 (256 * (tx - tx0), 256 * (ty - ty0)))
    extent = (tx0 * size - r, (tx1 + 1) * size - r, r - (ty1 + 1) * size, r - ty0 * size)
    # Blended toward white so the lakes stay light and the colours stay the focus.
    ax.imshow(np.asarray(mosaic), extent=extent, interpolation="bilinear", zorder=0, alpha=0.55)


def city_labels(ax, munis: gpd.GeoDataFrame, names, size: float) -> None:
    """Place names at the centre of each municipality's land area (from the municipal boundaries)."""
    halo = [pe.withStroke(linewidth=2, foreground="white")]
    for name in names:
        hit = munis[munis.MUNICIPAL_NAME_SHORTFORM == name]
        if hit.empty:
            continue
        p = hit.geometry.buffer(0).union_all().representative_point()
        ax.text(p.x, p.y, name.title(), fontsize=size, ha="center", va="center",
                color="#333", path_effects=halo, zorder=5, clip_on=True)
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


def ontario_land():
    """Ontario's provincial boundary (land only; the Great Lakes are outside it)."""
    if not PROVINCE.exists():
        r = requests.get(PROVINCE_URL, params={"where": "1=1", "outSR": CRS, "maxAllowableOffset": 100,
                                               "f": "geojson"}, timeout=300)
        r.raise_for_status()
        PROVINCE.write_text(r.text)
    return gpd.read_file(PROVINCE).set_crs(CRS, allow_override=True).buffer(0).union_all()


def share_in_ontario(sheds: gpd.GeoDataFrame) -> pd.Series:
    """Share of each watershed's area inside Ontario's provincial boundary."""
    return sheds.intersection(ontario_land()).area / sheds.area


def simplify(name) -> str:
    """Lower case, accents removed, letters and digits only."""
    name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", name.lower())


def match_codes(spills: pd.DataFrame, sheds: gpd.GeoDataFrame) -> pd.DataFrame:
    """Find the current watershed for each code used in the spill reports.

    The Province renumbered some watersheds between versions of the boundary
    layer, so a code alone can point to the wrong place (e.g. reports say
    "Mad River" under 02ED-09, which is now the Boyne River). A code is only
    trusted when the name in the reports agrees with the boundary layer;
    otherwise the name is looked up within the same tertiary watershed (first
    four characters). Reports with no watershed name can't be checked and are
    left off the map.
    """
    by_code = sheds.set_index("WATERSHED_CODE").WATERSHED_NAME.map(simplify)
    by_name = sheds.assign(key=sheds.WATERSHED_CODE.str[:4] + "|" + sheds.WATERSHED_NAME.map(simplify))
    by_name = by_name.drop_duplicates("key", keep=False).set_index("key").WATERSHED_CODE

    codes, how = [], []
    for code, name in zip(spills.quat_code, spills.quat_name):
        if pd.isna(name):
            codes.append(None); how.append("no name in reports")
        elif code in by_code and SequenceMatcher(None, simplify(name), by_code[code]).ratio() >= 0.8:
            codes.append(code); how.append("code and name agree")
        elif f"{code[:4]}|{simplify(name)}" in by_name:
            codes.append(by_name[f"{code[:4]}|{simplify(name)}"]); how.append("matched by name (code changed)")
        else:
            codes.append(None); how.append("name not found in boundary layer")
    spills = spills.assign(map_code=codes, match=how)
    spills.to_csv(CHECK, index=False)
    print(spills.groupby("match").spills.agg(["size", "sum"]))
    return spills


def write_geopackage(m: gpd.GeoDataFrame):
    """The joined layer, for styling in QGIS."""
    out = m.rename(columns={"WATERSHED_CODE": "code", "WATERSHED_NAME": "name"})
    out["area_km2"] = (out.AREA_HECTARE / 100).round(1)
    out["per100km2"] = out.per100km2.round(2)
    out["unit_type"] = "Quaternary watershed"
    out.loc[~out.in_ontario, "unit_type"] = "Outside Ontario"
    out.loc[out.code.str.endswith("00"), "unit_type"] = "Lake, shoreline or outside Ontario"
    out = out[["code", "name", "unit_type", "area_km2", "spills", "per100km2", "reached_water",
               "pct_reached_water", "sewage_to_water", "fuel_oil_to_water", "geometry"]]
    out.to_file(GPKG, layer="spills_by_watershed_2023_2025", driver="GPKG")

    # Shoreline strips: land drained by small creeks straight into a lake
    # (e.g. Grimsby, Highland Creek). They have no numbered watershed, so no
    # report can be placed in them. Clipped to land so the lakes aren't shaded.
    shore = out[out.code.str.endswith("-00")][["code", "geometry"]].copy()
    # The provincial boundary includes nearshore lake area, so clip to the land
    # parts of municipalities instead (mainland and islands, not "Water").
    munis = gpd.read_file(MUNIS).to_crs(CRS)
    land = munis[munis.MUNICIPAL_AREA_EXTENT_TYPE != "Water"].buffer(0).union_all()
    shore["geometry"] = shore.intersection(land)
    shore = shore.explode(index_parts=False)
    shore = shore[shore.geom_type == "Polygon"]  # drop stray lines/points from the clip
    shore = shore.dissolve("code").reset_index()
    shore = shore[shore.area > 1e6]
    shore.to_file(GPKG, layer="shoreline_not_mapped", driver="GPKG")
    print(f"Saved {GPKG.relative_to(ROOT)}")
    return shore, munis[munis.MUNICIPAL_AREA_EXTENT_TYPE != "Water"]


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
    sheds["in_ontario"] = share_in_ontario(sheds) >= 0.1
    spills = match_codes(pd.read_csv(TABLE), sheds)

    # Two old codes can point to the same current watershed, so add them up.
    counts = ["spills", "reached_water", "sewage_to_water", "fuel_oil_to_water"]
    per_shed = spills.dropna(subset=["map_code"]).groupby("map_code")[counts].sum().reset_index()
    per_shed["pct_reached_water"] = (100 * per_shed.reached_water / per_shed.spills).round(1)

    m = sheds.merge(per_shed, left_on="WATERSHED_CODE", right_on="map_code", how="left")
    m[counts] = m[counts].fillna(0).astype(int)
    m["per100km2"] = m.spills / (m.AREA_HECTARE / 10_000)
    # Border-river watersheds that are mostly water or Quebec/US (e.g. St. Marys
    # River at Sault Ste. Marie) still count when Ontario reports name them.
    m["in_ontario"] = m.in_ontario | (m.spills > 0)
    shore, munis = write_geopackage(m)
    print(m.per100km2.describe())
    m.sort_values("per100km2", ascending=False)[
        ["WATERSHED_CODE", "WATERSHED_NAME", "spills", "per100km2"]].head(10).pipe(print)

    # Draw in Web Mercator so the basemap tiles fit; see WEB above.
    m, shore, munis = m.to_crs(WEB), shore.to_crs(WEB), munis.to_crs(WEB)
    to_web = Transformer.from_crs(CRS, WEB, always_xy=True)
    gx0, gy0, gx1, gy1 = GTA_BOX
    xs, ys = to_web.transform([gx0, gx1, gx0, gx1], [gy0, gy0, gy1, gy1])
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    stretch = (x1 - x0) / (gx1 - gx0)  # Mercator inflates distances here by ~1.4
    cmap, norm = ListedColormap(COLORS), BoundaryNorm(BREAKS, len(COLORS))

    fig = plt.figure(figsize=(13, 8.2), dpi=300)
    ax_main = fig.add_axes([0.02, 0.10, 0.60, 0.80])
    ax_gta = fig.add_axes([0.63, 0.30, 0.35, 0.60])

    # Only Ontario's quaternary watersheds are coloured. Lakes and the areas
    # across the border simply show the basemap, and the shoreline strips (land
    # with no watershed code, so no report can be placed there) are hatched.
    quat = m[~m.WATERSHED_CODE.str.endswith("00") & m.in_ontario]
    south = quat[quat.geometry.centroid.y < 5_980_000]  # roughly south of 47°N
    sx0, sy0, sx1, sy1 = south.total_bounds
    main_box = (sx0 - 20_000, sy0 - 20_000, sx1 + 20_000, sy1 + 20_000)
    basemap(ax_main, main_box, zoom=8)
    basemap(ax_gta, (x0, y0, x1, y1), zoom=10)
    for ax in (ax_main, ax_gta):
        shore.plot(ax=ax, facecolor="#e4e4e2", edgecolor="#b8b8b8", hatch="///", linewidth=0.1, alpha=0.9, zorder=2)
        quat.plot(column="per100km2", cmap=cmap, norm=norm, ax=ax,
                  edgecolor="#8a8a8a", linewidth=0.15, alpha=0.9, zorder=3)
        ax.set_axis_off()
    ax_main.set_xlim(main_box[0], main_box[2])
    ax_main.set_ylim(main_box[1], main_box[3])
    ax_gta.set_xlim(x0, x1)
    ax_gta.set_ylim(y0, y1)
    city_labels(ax_main, munis, MAIN_CITIES, 6)
    city_labels(ax_gta, munis, GTA_CITIES, 6.5)
    ax_main.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, lw=1, ec="black", zorder=6))
    for ax, lat in ((ax_main, 44.5), (ax_gta, 43.8)):
        # Mercator metres are not true metres; scale the bar by cos(latitude).
        ax.add_artist(ScaleBar(math.cos(math.radians(lat)), units="m", location="lower right",
                               box_alpha=0.7, font_properties={"size": 7}))
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
        p = type(p)(p.x + dx * stretch, p.y + dy * stretch)
        if x0 < p.x < x1 and y0 < p.y < y1:
            ax_gta.annotate(f"{row.WATERSHED_NAME}\n{int(row.spills)} reports", (p.x, p.y),
                            fontsize=6, ha="center", va="center", zorder=7,
                            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.8))
    ax_gta.set_title("Greater Toronto Area", fontsize=10, loc="left")

    ax_main.annotate("N", xy=(0.04, 0.93), xytext=(0.04, 0.85), xycoords="axes fraction",
                     ha="center", fontsize=10, fontweight="bold",
                     arrowprops=dict(arrowstyle="-|>", color="black", lw=1.2))

    fig.legend(handles=[Patch(fc=c, ec="#9a9a9a", label=l) for c, l in zip(COLORS, LABELS)]
               + [Patch(fc="#e4e4e2", ec="#b8b8b8", hatch="///", label="Shoreline area (no\nwatershed code in data)")],
               title="Spill reports per 100 km²", loc="lower left",
               bbox_to_anchor=(0.64, 0.10), ncol=2, fontsize=8, title_fontsize=9, frameon=False)
    fig.suptitle("Spill reports per 100 km² by watershed, southern Ontario, 2023–2025",
                 x=0.02, ha="left", fontsize=14, fontweight="bold")
    fig.text(0.02, 0.03,
             "Data: Ontario Ministry of the Environment, Conservation and Parks, Environmental Occurrences and Spills "
             "(2023–2025), counted by the quaternary watershed in each report;\n"
             "Ontario Watershed Boundaries (quaternary), Ontario Ministry of Natural Resources. "
             "Contains information licensed under the Open Government Licence – Ontario. "
             f"{BASEMAP_ATTR}. Map: Elias Matar, October 2026.\n"
             "About 9% of reports give no watershed name, or a name not in the current boundary layer, and are not mapped.",
             fontsize=6.5, color="#444")

    fig.savefig(FIG, dpi=300, facecolor="white")
    print(f"Saved {FIG.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
