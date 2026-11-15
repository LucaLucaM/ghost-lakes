"""Protected on paper: lagoon, lake and river water turned into land inside Ramsar sites, 2023 -> 2026.

Ramsar sites are wetlands that 172 countries promised, by treaty, to protect ("Wetlands of
International Importance"). Article 3.2 of the Convention asks each country to report to the
Ramsar Secretariat when a site's ecological character changes because of human activity.

1. screen():  one Earth Engine batch job over every Ramsar polygon in the WDPA (2,124 polygons).
              Same rule as the infill monitor, on whole calendar years so seasons cancel:
              water in 2023 (Dynamic World mean P(water) >= 0.7, and water in >= 50% of 1984-2021),
              land in 2026 (P(water) <= 0.2 and P(built) + P(bare) >= 0.5). 30 m.
2. refine():  for the sites with the most change, the 10 m infill detector inside the site
              polygon, the Sentinel-1 radar rule, and image chips for review by eye.
"""
import csv
import json
import os

import ee

from . import infill
from .common import OUT, init, occurrence, s2_rgb

ASSET = "projects/lootlake/assets/ghostlakes/ramsar_infill_2023_2026"
THEN, NOW, RADAR_AFTER = ("2023-01-01", "2024-01-01"), ("2026-01-01", "2026-11-15"), ("2026-08-15", "2026-11-15")
DIR = os.path.join(OUT, "ramsar")


def sites():
    return ee.FeatureCollection("WCMC/WDPA/current/polygons").filter(ee.Filter.stringContains("DESIG_ENG", "Ramsar"))


def change_image():
    dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").select(["water", "built", "bare"])
    t, n = dw.filterDate(*THEN).mean(), dw.filterDate(*NOW).mean()
    lt = occurrence().gte(50)
    filled = (t.select("water").gte(0.7).And(n.select("water").lte(0.2))
              .And(n.select("built").add(n.select("bare")).gte(0.5)).And(lt))
    built = filled.And(n.select("built").gt(n.select("bare")))
    ha = ee.Image.pixelArea().divide(1e4)
    return ee.Image.cat(filled.multiply(ha).rename("filled_ha"), built.multiply(ha).rename("filled_built_ha"),
                        t.select("water").gte(0.7).And(lt).multiply(ha).rename("water23_ha")).unmask(0)


def screen():
    """Starts the batch export (takes ~1 h); results land in ASSET."""
    init()
    res = change_image().reduceRegions(sites().select(["NAME", "ISO3", "SITE_ID", "GIS_AREA", "STATUS_YR"]),
                                       ee.Reducer.sum(), 30, tileScale=16)
    res = res.map(lambda f: f.setGeometry(f.geometry().centroid(100)))
    task = ee.batch.Export.table.toAsset(res, "ramsar_infill_2023_2026", ASSET)
    task.start()
    print("started", task.id)


def ranked(min_ha=2.0):
    """Screen results with at least min_ha of change, largest first (also saved as CSV)."""
    rows = [f["properties"] | {"lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1]}
            for f in ee.FeatureCollection(ASSET).getInfo()["features"]]
    rows.sort(key=lambda r: -r["filled_ha"])
    os.makedirs(DIR, exist_ok=True)
    cols = ["SITE_ID", "NAME", "ISO3", "STATUS_YR", "GIS_AREA", "water23_ha", "filled_ha", "filled_built_ha", "lat", "lon"]
    with open(os.path.join(DIR, "screen_all.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow([round(r[c], 3) if isinstance(r[c], float) else r[c] for c in cols])
    return [r for r in rows if r["filled_ha"] >= min_ha]


def refine(rows, min_ha=1.0):
    """10 m detection + radar inside each site polygon. Saves outputs/ramsar/<SITE_ID>.geojson."""
    os.makedirs(DIR, exist_ok=True)
    for r in rows:
        p = os.path.join(DIR, f"{r['SITE_ID']}.geojson")
        if os.path.exists(p):
            continue
        geom = (ee.Geometry(r["geometry"], None, False) if r.get("geometry")
                else sites().filter(ee.Filter.eq("SITE_ID", r["SITE_ID"])).geometry())
        try:
            gj, area = infill.detect(geom, THEN, NOW, RADAR_AFTER, min_ha=min_ha)
        except ee.EEException as e:
            print(f"  {r['NAME']}: {e}")
            continue
        gj["optical_ha"] = area
        with open(p, "w", encoding="utf-8") as f:
            json.dump(gj, f)
        conf = [x for x in gj["features"] if x["properties"].get("radar_confirmed")]
        print(f"{r['NAME'][:40]:40s} {r['ISO3']}  optical {area:6.1f} ha  {len(gj['features'])} patches, "
              f"{len(conf)} radar-confirmed ({sum(x['properties']['area_ha'] for x in conf):.1f} ha)")


def chips(features, out_png, half_m=700, size=260):
    """2023 vs 2026 Sentinel-2 for each patch, side by side, patch outlined in red."""
    import urllib.request
    from PIL import Image, ImageDraw
    sheet = Image.new("RGB", (2 * size + 10, len(features) * (size + 18)), "white")
    d = ImageDraw.Draw(sheet)
    for k, (label, ft) in enumerate(features):
        g = ee.Geometry(ft["geometry"])
        reg = g.centroid(1).buffer(half_m).bounds()
        line = ee.Image().paint(ee.FeatureCollection([ee.Feature(g)]), 1, 2).visualize(palette=["ff0000"])
        for c, (a, b) in enumerate([("2023-01-01", "2023-07-01"), ("2026-04-01", "2026-11-15")]):
            url = s2_rgb(g, a, b, vmax=0.22).blend(line).getThumbURL({"region": reg, "dimensions": size, "format": "png"})
            im = Image.open(urllib.request.urlopen(url)).convert("RGB").resize((size, size))
            sheet.paste(im, (c * (size + 10), k * (size + 18) + 18))
        d.text((3, k * (size + 18) + 3), f"{label}   2023  |  2026", fill="black")
    sheet.save(out_png)
