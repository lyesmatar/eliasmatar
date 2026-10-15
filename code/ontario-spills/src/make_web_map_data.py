"""
make_web_map_data.py - Write the data file for the interactive web map.

Watersheds: the Ontario Watershed Boundaries are downloaded again at full
detail, because at full detail neighbouring watersheds share exactly the same
borders (a valid "coverage"). They are then simplified with
shapely.coverage_simplify, which simplifies each shared border once, so
neighbours still meet with no slivers between them. (Simplifying each
watershed on its own, as QGIS's Simplify tool does, leaves hairline gaps.)

Towns: the municipal layer simplified in QGIS (output/web_layers.gpkg).
Shoreline: the "-00" shoreline units, clipped to municipal land.

Only the fields the map shows are kept, and coordinates are rounded to
4 decimals (about 10 m).

Output: Portfolio/work/spills-map/data.js
"""

import json
from pathlib import Path

import geopandas as gpd
import requests
import shapely

ROOT = Path(__file__).resolve().parent.parent
FULL = ROOT / "data" / "external" / "owb_main_units_full.geojson"
SHORE = ROOT / "data" / "external" / "owb_shoreline_units.geojson"  # "-00" units with 5th-level names
JOINED = ROOT / "output" / "spills_watersheds_v2.gpkg"   # spill counts per watershed (make_map.py)
WEB = ROOT / "output" / "web_layers.gpkg"                 # town layer simplified in QGIS
MUNIS = ROOT / "data" / "external" / "municipal_boundaries.gpkg"
OUT = ROOT.parent / "Portfolio" / "work" / "spills-map" / "data.js"

OWB_URL = ("https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/"
           "LIO_OPEN_DATA/LIO_Open04/MapServer/27/query")
CRS = 3161
TOLERANCE = 400   # metres
MIN_HOLE = 2e6    # m2; lakes smaller than this inside a watershed are filled in


def download_full() -> None:
    # Small pages with retries: the Great Lakes units are huge and time out in big pages.
    # geometryPrecision=1 rounds to 0.1 m, which keeps shared vertices identical.
    features, offset, page = [], 0, 50
    while True:
        for attempt in range(4):
            try:
                r = requests.get(OWB_URL, params={
                    "where": "1=1", "outFields": "QUATERNARY_WATERSHED_CODE", "outSR": CRS,
                    "geometryPrecision": 1, "orderByFields": "OBJECTID",
                    "resultOffset": offset, "resultRecordCount": page, "f": "geojson"}, timeout=600)
                r.raise_for_status()
                break
            except requests.RequestException as e:
                print(f"  retry {attempt + 1}: {e.__class__.__name__}")
        else:
            raise RuntimeError(f"download failed at offset {offset}")
        batch = r.json()["features"]
        features += batch
        print(f"  downloaded {len(features)} units")
        if len(batch) < page:
            break
        offset += page
    FULL.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def download_shoreline() -> None:
    """The shoreline strips (quaternary code ending "-00") with their fifth-level
    names, e.g. 029A-0006 "Highland Creek". No spill report carries these codes,
    but naming the strips makes clear they are real land, not holes in the map."""
    features, offset, page = [], 0, 25
    while True:
        r = requests.get(OWB_URL, params={
            "where": "QUATERNARY_WATERSHED_CODE LIKE '%-00'",
            "outFields": "QUATERNARY_WATERSHED_CODE,FIFTH_LEVEL_WATERSHED_CODE,FIFTH_LEVEL_WATERSHED_NAME",
            "outSR": CRS, "geometryPrecision": 1, "orderByFields": "OBJECTID",
            "resultOffset": offset, "resultRecordCount": page, "f": "geojson"}, timeout=600)
        r.raise_for_status()
        batch = r.json()["features"]
        features += batch
        print(f"  downloaded {len(features)} shoreline units")
        if len(batch) < page:
            break
        offset += page
    SHORE.write_text(json.dumps({"type": "FeatureCollection", "features": features}))


def fill_small_holes(geom):
    polys = getattr(geom, "geoms", [geom])
    return shapely.MultiPolygon([
        shapely.Polygon(p.exterior, [r for r in p.interiors if shapely.Polygon(r).area >= MIN_HOLE])
        for p in polys])


def rounded(geom: dict) -> dict:
    def r(c):
        return [round(c[0], 4), round(c[1], 4)] if isinstance(c[0], float) else [r(x) for x in c]
    return {"type": geom["type"], "coordinates": r(geom["coordinates"])}


def collection(gdf: gpd.GeoDataFrame, fields: dict) -> dict:
    gdf = gdf.to_crs(4326)
    geoms = json.loads(gdf.geometry.to_json())["features"]
    feats = []
    for row, g in zip(gdf.drop(columns="geometry").to_dict("records"), geoms):
        if g["geometry"] is None:
            continue
        props = {short: (None if row[col] != row[col] else row[col]) for short, col in fields.items()}
        feats.append({"type": "Feature", "properties": props, "geometry": rounded(g["geometry"])})
    return {"type": "FeatureCollection", "features": feats}


def main() -> None:
    if not FULL.exists():
        print("Downloading full-detail watershed boundaries...")
        download_full()
    units = gpd.read_file(FULL).set_crs(CRS, allow_override=True)
    sheds = units.dissolve("QUATERNARY_WATERSHED_CODE").reset_index().rename(
        columns={"QUATERNARY_WATERSHED_CODE": "code"})
    print("valid coverage:", shapely.coverage_is_valid(sheds.geometry.values))

    stats = gpd.read_file(JOINED).drop(columns="geometry")
    sheds = sheds.merge(stats, on="code", how="left")
    sheds["geometry"] = shapely.coverage_simplify(sheds.geometry.values, TOLERANCE)
    sheds = sheds[~sheds.geometry.is_empty]

    water = sheds[sheds.unit_type == "Quaternary watershed"].copy()
    water["geometry"] = water.geometry.apply(fill_small_holes)
    water["per100km2"] = water.per100km2.astype(float).round(1)

    munis = gpd.read_file(MUNIS).to_crs(CRS)
    land = munis[munis.MUNICIPAL_AREA_EXTENT_TYPE != "Water"].simplify(100).buffer(0).union_all()
    if not SHORE.exists():
        print("Downloading shoreline units with names...")
        download_shoreline()
    shore = gpd.read_file(SHORE).set_crs(CRS, allow_override=True)
    shore = shore.dissolve("FIFTH_LEVEL_WATERSHED_CODE", aggfunc={"FIFTH_LEVEL_WATERSHED_NAME": "first"}).reset_index()
    shore = shore.rename(columns={"FIFTH_LEVEL_WATERSHED_CODE": "code", "FIFTH_LEVEL_WATERSHED_NAME": "name"})
    shore["geometry"] = shore.intersection(land).simplify(TOLERANCE)
    shore = shore.explode(index_parts=False)
    shore = shore[(shore.geom_type == "Polygon") & (shore.area > 1e6)]
    shore = shore.dissolve("code", aggfunc={"name": "first"}).reset_index()

    towns = gpd.read_file(WEB, layer="Municipal Boundaries")
    towns = towns[towns.MUNICIPAL_AREA_EXTENT_TYPE != "Water"]
    towns["town"] = towns.MUNICIPAL_NAME_SHORTFORM.str.title()

    data = {
        "watersheds": collection(water, {"n": "name", "c": "code", "s": "spills", "r": "per100km2",
                                         "w": "reached_water"}),
        "towns": collection(towns, {"t": "town"}),
        "shoreline": collection(shore, {"n": "name", "c": "code"}),
    }
    OUT.write_text("var SPILLS_MAP_DATA = " + json.dumps(data, separators=(",", ":"), ensure_ascii=False) + ";",
                   encoding="utf-8")
    print({k: len(v["features"]) for k, v in data.items()}, f"{OUT.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
