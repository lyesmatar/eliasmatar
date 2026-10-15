# Data sources and references

All data in this project is public, published by the Government of Ontario and the
Government of Canada under open licences. Nothing was entered by hand: every file is
downloaded by the scripts in `src/` from the URLs below.

## 1. Spill reports (Ontario Spills Action Centre)

**Ontario Ministry of the Environment, Conservation and Parks. (2026).** *Environmental
Occurrences and Spills* [Data set]. Ontario Data Catalogue. Open Government Licence – Ontario.
https://data.ontario.ca/dataset/environmental-occurrences-and-spills

Reports received by the Spills Action Centre, including date, municipality, substance,
receiving media (land, air, water), cause, sector and, from 2023, conservation authority
and watershed. The Ministry records every reported spill, whether or not it responded in the field.

| File | Years | Size | SHA-256 checksum (downloaded 2026-10-13) |
|---|---|---|---|
| [spill_occurrences_2003-2022.csv](https://files.ontario.ca/moe_mapping/downloads/4Other/SAC/spill_occurrences_2003-2022.csv) | 2003–2022 | 19.1 MB | `3998134ED2C026D7A1FF59A56F21B0011EEDC7CDDB80E1662E2E0A709C9CFAC9` |
| [spill_occurrences_2023.xlsx](https://files.ontario.ca/moe_mapping/downloads/4Other/SAC/spill_occurrences_2023.xlsx) | 2023 | 1.0 MB | `501C5076576854128D900E5C2233C26385C030B7CDCF31C00616F68D7296E9BF` |
| [spill_occurrences_2024.xlsx](https://files.ontario.ca/moe_mapping/downloads/4Other/SAC/spill_occurrences_2024.xlsx) | 2024 | 0.9 MB | `7ADE3E224FD186C047E74C9B6062262FA674F52F6FFD1A3E0ED877C4CB67B9CE` |
| [spill_occurrences_2025.csv](https://files.ontario.ca/moe_mapping/downloads/4Other/SAC/spill_occurrences_2025.csv) | 2025 | 2.5 MB | `E72D694A60D10A1180FD6DB5AD0DB58D5B16C140B6C80A0176979B742CA4C725` |
| [Spills_metadata_EN.pdf](https://files.ontario.ca/moe_mapping/downloads/metadata/opendata/Spills_metadata_EN.pdf) | metadata | 35 KB | `4F489752E183F99697D00AC5D2F1803FC1437968BB6EF908480D51A6B7D4D0A7` |

The raw files are not copied here because of their size; `src/get_spill_data.py` downloads
them from the links above. The checksums let anyone confirm they have the same files I used
(Windows: `Get-FileHash <file>`; Mac/Linux: `shasum -a 256 <file>`). If the Ministry updates a
file, the checksum will change.

*Contains information licensed under the Open Government Licence – Ontario.*

## 2. Rainfall (Environment and Climate Change Canada)

**Environment and Climate Change Canada. (2026).** *Daily climate observations*, Toronto
Pearson International Airport, Climate IDs 6158733 (to 2013-06-12) and 6158731 (from
2013-06-13) [Data set]. MSC GeoMet / OGC API. Open Government Licence – Canada.
https://api.weather.gc.ca/collections/climate-daily

Included here as `pearson_daily_precip.csv` (date, precipitation in mm), 2003–2025, as
downloaded by `src/get_weather.py`. 26 days have no reading and are left out of the analysis.

*Contains information licensed under the Open Government Licence – Canada.*

## 3. Results tables

The `tables/` folder holds every result shown on the project page and in the charts,
exactly as produced by `src/run_analysis.py`, `src/rain_and_spills.py` and
`src/make_map_table.py`.

## 4. Watershed boundaries (for the map)

**Ontario Ministry of Natural Resources. (2026).** *Ontario Watershed Boundaries (OWB) – Main,
All Watershed Units* [Data set]. Land Information Ontario. Open Government Licence – Ontario.
https://geohub.lio.gov.on.ca/datasets/mnrf::ontario-watershed-boundaries-owb

Map service used by `src/make_map.py` (downloaded 2026-10-13):
https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open04/MapServer/27
Outlines are simplified to 100 m for drawing; rates use the official `AREA_HECTARE` field.

The separate quaternary layer (MapServer/1) leaves out the Lake Ontario shoreline strips, so the
"All Watershed Units" layer is used and dissolved to quaternary codes.

The Province renumbered some watersheds between versions of the layer (e.g. reports say "Mad River"
under 02ED-09, which is now the Boyne River), so reports are matched on code **and** name. Where only
the code changed, the name is used (9 codes, 356 reports). About 9% of 2023–2025 reports (1,778) give
no watershed name, or a name not in the current layer, and are not mapped. Every code and how it was
matched is listed in `tables/watershed_map_join_check.csv`.

Watersheds mostly outside Ontario (e.g. Tonawanda Creek, New York) are marked using:
**Ontario Ministry of Natural Resources. (2026).** *Province* [boundary data set]. Land Information
Ontario. https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open03/MapServer/0

*Contains information licensed under the Open Government Licence – Ontario.*

## 5. Municipal boundaries (for the map)

**Ontario Ministry of Municipal Affairs and Housing / Land Information Ontario. (2026).**
*Municipal Boundary – Lower and Single Tier* [Data set]. Open Government Licence – Ontario.
https://ws.lioservices.lrc.gov.on.ca/arcgis2/rest/services/LIO_OPEN_DATA/LIO_Open03/MapServer/14
(downloaded 2026-10-14). Used for town outlines on the web map and to keep the
"shoreline" hatching on land.

Basemap: © CARTO, © OpenStreetMap contributors.

**Interactive web map** (`work/spills-map/`): styled and simplified in QGIS, published with Leaflet.
`src/make_web_map_data.py` re-downloads the watershed boundaries at full detail and simplifies
them with `shapely.coverage_simplify`, so neighbouring watersheds keep shared borders (no slivers).
Coordinates are rounded to 4 decimals (about 10 m).

## Method reference

Risk ratios and 95% confidence intervals use the standard log method, as in:
Rothman, K. J., Greenland, S., & Lash, T. L. (2008). *Modern Epidemiology* (3rd ed.).
Lippincott Williams & Wilkins.
