# Ghost Lakes

Finding lakes, ponds and lagoons that cities have buried, using AI and satellite data (Google Earth Engine).
See **[WRITEUP.md](WRITEUP.md)** for the one-page summary and **[FINDINGS.md](FINDINGS.md)** for the full research log (in Romanian).

## Setup
```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\earthengine authenticate
```
Set your Earth Engine project id in `ghostlakes.py` (`PROJECT = "..."`).

## Scripts
| Script | What it does | Main output |
|---|---|---|
| `ghostlakes.py` | Terrain model (Random Forest), leave-one-region-out evaluation, ghost-lake candidates for 7 Romanian cities | `outputs/metrics.json`, `outputs/candidates.csv`, `outputs/map.html` |
| `validate.py` | Tests the model on documented drained lakes in Bucharest | `outputs/validation_bucuresti.json` |
| `vanished.py` | Vanished-water detector for 84 cities worldwide | `outputs/vanished/*.geojson` |
| `inspect_sites.py`, `montage.py` | Old (Landsat) vs new (Sentinel-2) image chips + yearly water history for any list of points | `research/*` |
| `osm_check.py` | Is the site still mapped as water in OpenStreetMap? What is the neighbourhood called? | json |
| `lagoon_infill.py` | Abidjan Ébrié lagoon: water in 2023 → land in 2026 | `outputs/abidjan_infill.geojson` |
| `radar_check.py` | Sentinel-1 radar before/after check for any set of polygons | console |
| `recent_infill.py` | Lakes/lagoons filled 2023→2026 in ~120 cities, with radar confirmation | `outputs/recent_infill/*` |
| `recent_chips.py` | Sentinel-2 2023 vs 2026 image chips for any points | png |
| `abidjan_radar_recent.py` | Radar-only search for Abidjan infill after the June 2026 stop order + per-pass dating | `outputs/abidjan_after_pm_order.geojson` |
| `abidjan_timing.py` | Month in which each Abidjan site turned from water to land | `outputs/abidjan_infill_timing.json` |
| `abidjan_figures.py` | Presentation figure + interactive map (images embedded, no expiry) | `outputs/abidjan/` |
| `make_pdf.py` | Renders WRITEUP.md to a one-page A4 PDF (needs Edge or Chrome) | `WRITEUP.pdf` |

Abidjan order: `lagoon_infill.py` → `abidjan_timing.py` → `abidjan_figures.py`.

## Data credits
JRC Global Surface Water v1.4 (EC JRC/Google), Dynamic World V1 (Google/WRI), Copernicus Sentinel-2, Landsat 5 (USGS), FABDEM (Univ. Bristol / Fathom), MERIT Hydro, © OpenStreetMap contributors, Esri World Imagery (basemap).
