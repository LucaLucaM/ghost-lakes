"""World scan: every urban area on Earth, water -> land 2023 -> 2026, in one Earth Engine batch job.

Instead of choosing cities by hand, the planet is cut into 0.1 degree cells (~11 km) and every cell
that contains urban land (GHSL settlement model 2025, class >= 21: suburban and denser) is kept.
In each cell we measure, at 30 m, long-term water (JRC >= 50% of 1984-2021) that was water in 2023
(Dynamic World mean P(water) >= 0.7) and is land in 2026 (P(water) <= 0.2, P(built) + P(bare) >= 0.5),
plus the mean Sentinel-1 VV before and after over exactly those pixels (radar check per cell).
The ranked hotspots are then reviewed by eye and against the news (ghostlakes/world.py: hotspots()).
"""
import csv
import os

import ee

from . import radar
from .common import OUT, init, occurrence

ASSET = "projects/lootlake/assets/ghostlakes/world_infill_2023_2026"
THEN, NOW = ("2023-01-01", "2024-01-01"), ("2026-01-01", "2026-11-15")
CELL = 0.1
DIR = os.path.join(OUT, "world")


def urban_cells():
    """0.1 degree cells whose centre is within ~7 km of urban land."""
    smod = ee.Image("JRC/GHSL/P2023A/GHS_SMOD/2025")
    near = smod.gte(21).focalMax(7000, "circle", "meters")
    ll = ee.Image.pixelLonLat().divide(CELL).floor()
    cell_id = ll.select("longitude").add(2000).multiply(10000).add(ll.select("latitude").add(1000)).toInt64()
    near = cell_id.updateMask(near)
    world = ee.Geometry.Rectangle([-180, -60, 180, 75], None, False)
    return near.reduceToVectors(geometry=world, crs=ee.Projection("EPSG:4326").scale(CELL, CELL),
                                geometryType="polygon", eightConnected=False, labelProperty="cell",
                                maxPixels=1e9, geometryInNativeProjection=True)


def change_image():
    dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").select(["water", "built", "bare"])
    t, n = dw.filterDate(*THEN).mean(), dw.filterDate(*NOW).mean()
    filled = (t.select("water").gte(0.7).And(n.select("water").lte(0.2))
              .And(n.select("built").add(n.select("bare")).gte(0.5)).And(occurrence().gte(50))).unmask(0)
    ha = ee.Image.pixelArea().divide(1e4)
    s1 = radar.s1_vv(ee.Geometry.Rectangle([-180, -60, 180, 75], None, False))
    vb, va = s1.filterDate(*THEN).median(), s1.filterDate(*NOW).median()
    rad = filled.And(vb.mask()).And(va.mask()).unmask(0).multiply(ha)   # filled pixels that have radar
    return ee.Image.cat(filled.multiply(ha).rename("filled_ha"), rad.rename("radar_ha"),
                        rad.multiply(vb.unmask(0)).rename("vvb_x_ha"),
                        rad.multiply(va.unmask(0)).rename("vva_x_ha")).unmask(0)


def scan():
    """Starts the batch export (about an hour); results land in ASSET."""
    init()
    res = change_image().reduceRegions(urban_cells(), ee.Reducer.sum(), 30, tileScale=16)
    res = res.filter(ee.Filter.gt("filled_ha", 0)).map(lambda f: f.setGeometry(f.geometry().centroid(100)))
    task = ee.batch.Export.table.toAsset(res, "world_infill_2023_2026", ASSET)
    task.start()
    print("started", task.id)


def hotspots(min_ha=3.0):
    """Cells with >= min_ha of change, largest first, with the cell-level radar check; saves a CSV."""
    rows = []
    for f in ee.FeatureCollection(ASSET).getInfo()["features"]:
        p = f["properties"]
        a, r = p["filled_ha"], p["radar_ha"]
        b, c = (p["vvb_x_ha"] / r, p["vva_x_ha"] / r) if r else (None, None)
        lon, lat = f["geometry"]["coordinates"]
        rows.append({"lat": round(lat, 3), "lon": round(lon, 3), "filled_ha": round(a, 1),
                     "vv_before": None if b is None else round(b, 1), "vv_after": None if c is None else round(c, 1),
                     "radar_confirmed": radar.is_confirmed(b, c)})
    rows.sort(key=lambda r: -r["filled_ha"])
    os.makedirs(DIR, exist_ok=True)
    with open(os.path.join(DIR, "cells.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return [r for r in rows if r["filled_ha"] >= min_ha]
