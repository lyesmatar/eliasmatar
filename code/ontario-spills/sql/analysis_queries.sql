-- analysis_queries.sql
-- Questions asked of the Spills Action Centre database (data/spills.db, table: spills).
-- Each query starts with "-- name:"; src/run_analysis.py runs them all and
-- saves each result to output/tables/<name>.csv.

-- name: spills_per_year
-- How many spills are reported each year, and how many reach water?
SELECT year,
       COUNT(*)                          AS spills,
       SUM(to_water)                     AS reached_water,
       ROUND(100.0 * AVG(to_water), 1)   AS pct_reached_water
FROM spills
GROUP BY year
ORDER BY year;

-- name: contaminants
-- Which substances are spilled most, and which ones end up in water?
SELECT contaminant_group,
       COUNT(*)                          AS spills,
       SUM(to_water)                     AS reached_water,
       ROUND(100.0 * AVG(to_water), 1)   AS pct_reached_water
FROM spills
GROUP BY contaminant_group
ORDER BY spills DESC;

-- name: causes
-- Why do spills happen? (cause recorded by SAC, grouped by keyword)
SELECT reason_group,
       COUNT(*)                          AS spills,
       ROUND(100.0 * AVG(to_water), 1)   AS pct_reached_water
FROM spills
GROUP BY reason_group
ORDER BY spills DESC;

-- name: weather_spills_by_month
-- Weather-caused spills by month: when should response teams expect them?
SELECT month,
       COUNT(*)                                        AS weather_spills,
       SUM(contaminant_group = 'Sewage')               AS sewage,
       SUM(to_water)                                   AS reached_water
FROM spills
WHERE reason_group = 'Weather'
GROUP BY month
ORDER BY month;

-- name: conservation_authorities_2023_2025
-- Where do spills happen? Conservation authority is only recorded from 2023.
SELECT COALESCE(conservation_authority, '(none recorded)') AS conservation_authority,
       COUNT(*)                          AS spills,
       SUM(to_water)                     AS reached_water,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM spills WHERE year >= 2023), 1)
                                         AS pct_of_ontario
FROM spills
WHERE year >= 2023
GROUP BY 1
ORDER BY spills DESC
LIMIT 15;

-- name: trca_top_contaminants_to_water_2023_2025
-- In the Toronto and Region (TRCA) area, what reaches water most often?
SELECT contaminant_group,
       COUNT(*) AS spills_reaching_water
FROM spills
WHERE year >= 2023
  AND conservation_authority = 'Toronto and Region'
  AND to_water = 1
GROUP BY contaminant_group
ORDER BY spills_reaching_water DESC
LIMIT 10;

-- name: top_municipalities
SELECT municipality,
       COUNT(*)        AS spills,
       SUM(to_water)   AS reached_water
FROM spills
GROUP BY municipality
ORDER BY spills DESC
LIMIT 15;
