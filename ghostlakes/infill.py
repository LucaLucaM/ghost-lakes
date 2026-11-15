"""Infill monitor: long-term water that became land between two periods, for any place.

Optical detection (Dynamic World): water then, sand/buildings now, on pixels that were water in at
least half of all observations 1984-2021 (JRC). Every site is then checked with radar, dated
month by month, and the people living nearby are counted (GHSL 2025).

Also the global screen (`screen`): the same detection over ~120 cities, with radar confirmation.
"""
import csv
import json
import os

import ee

from . import archive, radar, terrain
from .common import OUT, box, dw_mean, init, occurrence

POP = "JRC/GHSL/P2023A/GHS_POP/2025"


def detect(bbox, then, now, radar_after, min_ha=0.5, then_water=0.7, now_water=0.2, land=0.5, min_occurrence=50):
    """bbox: [lon_min, lat_min, lon_max, lat_max] or an ee.Geometry.
    Returns (GeoJSON of every optical site with radar values, total optical area in ha)."""
    geom = bbox if isinstance(bbox, ee.Geometry) else box(bbox)
    t, n = dw_mean(geom, *then), dw_mean(geom, *now)
    filled = (t.select("water").gte(then_water).And(n.select("water").lte(now_water))
              .And(n.select("built").add(n.select("bare")).gte(land)).And(occurrence().gte(min_occurrence)))
    filled = filled.updateMask(filled.connectedPixelCount(200, True).gte(5)).selfMask()
    area_ha = ee.Number(filled.multiply(ee.Image.pixelArea()).reduceRegion(
        ee.Reducer.sum(), geom, 10, maxPixels=1e10).values().get(0)).divide(1e4).getInfo() or 0.0

    def enrich(f):
        c = f.geometry().centroid(1).coordinates()
        return f.set({"area_ha": f.geometry().area(1).divide(1e4), "lon": c.get(0), "lat": c.get(1)})
    gj = (filled.reduceToVectors(geometry=geom, scale=10, geometryType="polygon", eightConnected=True,
                                 labelProperty="v", maxPixels=1e10, tileScale=4)
          .map(enrich).filter(ee.Filter.gte("area_ha", min_ha)).sort("area_ha", False).getInfo())
    if gj["features"]:
        for ft, r in zip(gj["features"], radar.confirm(gj["features"], then, radar_after)):
            ft["properties"].update(r)
    return gj, area_ha


# ---------------------------------------------------------------- dating (optical)

def change_months(series, wet=0.5, land=0.3):
    """series: [(YYYY-MM, P(water) or None)]. Returns (last month with P >= wet, first later month
    with P < land). None values (clouds / no data) are skipped."""
    last_wet = max((m for m, v in series if v is not None and v >= wet), default=None)
    first_land = next((m for m, v in series if v is not None and v < land and (last_wet is None or m > last_wet)), None)
    return last_wet, first_land


def timing(features, start_year=2023, n_months=46, min_valid=0.5):
    """Optical fill dates per site from Dynamic World P(water), 2-month window starting each month.
    Cloud-masked pixels are ignored; a window counts only if >= min_valid of the polygon is clear."""
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(f["geometry"]), {"id": i + 1}) for i, f in enumerate(features)])
    dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(fc.geometry()).select("water")
    empty = ee.Image.constant(0).toFloat().updateMask(ee.Image.constant(0))
    labels, bands = [], []
    for k in range(n_months):
        y, mo = start_year + k // 12, k % 12 + 1
        start = ee.Date.fromYMD(y, mo, 1)
        win = dw.filterDate(start, start.advance(2, "month"))
        labels.append(f"{y}-{mo:02d}")
        bands.append(ee.Image(ee.Algorithms.If(win.size().gt(0), win.mean(), empty)).rename(labels[-1]))
    stack = ee.Image.cat(bands).addBands(ee.Image.constant(1).rename("all"))
    reducer = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)
    out = {}
    for r in stack.reduceRegions(fc, reducer, 10, tileScale=4).getInfo()["features"]:
        p = r["properties"]
        total = p.get("all_count") or 0
        s = [(lab, p.get(f"{lab}_mean") if (p.get(f"{lab}_mean") is not None and total
                                            and (p.get(f"{lab}_count") or 0) / total >= min_valid) else None)
             for lab in labels]
        last_wet, first_land = change_months(s)
        out[p["id"]] = {"area_ha": features[p["id"] - 1]["properties"]["area_ha"],
                        "last_month_water": last_wet, "first_month_land": first_land, "series": s}
    return dict(sorted(out.items()))


def people_nearby(features, radius_m=500):
    """Residents within radius of each site (GHSL 2025, 100 m grid): {index: people}."""
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(f["geometry"]).buffer(radius_m), {"id": i})
                               for i, f in enumerate(features)])
    rows = ee.Image(POP).select(0).reduceRegions(fc, ee.Reducer.sum().setOutputs(["pop"]), 100).getInfo()
    return {r["properties"]["id"]: round(r["properties"].get("pop") or 0) for r in rows["features"]}


def people_union(features, radius_m):
    """Residents within radius of ANY site (no double counting)."""
    geom = ee.FeatureCollection([ee.Feature(ee.Geometry(f["geometry"]).buffer(radius_m)) for f in features]).union(1).geometry()
    return round(ee.Image(POP).select(0).reduceRegion(ee.Reducer.sum(), geom, 100, maxPixels=1e9).values().get(0).getInfo())


def monitor(name, bbox, then, now, radar_after=None, min_ha=0.5):
    """Full monitor for any place: detect -> radar -> dates -> people -> outputs/monitor/<name>/."""
    init()
    radar_after = tuple(radar_after) if radar_after else (
        ee.Date(now[1]).advance(-3, "month").format("YYYY-MM-dd").getInfo(), now[1])
    gj, area = detect(bbox, tuple(then), tuple(now), radar_after, min_ha)
    confirmed = [f for f in gj["features"] if f["properties"].get("radar_confirmed")]
    print(f"{name}: optical change {area:.1f} ha in total; {len(gj['features'])} sites >= {min_ha} ha; "
          f"{len(confirmed)} confirmed by radar ({sum(f['properties']['area_ha'] for f in confirmed):.1f} ha)")
    out = os.path.join(OUT, "monitor", name)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "sites_all.geojson"), "w", encoding="utf-8") as f:
        json.dump(gj, f)
    if confirmed:
        start_year, end_year, end_month = int(then[0][:4]), int(now[1][:4]), int(now[1][5:7])
        t = timing(confirmed, start_year, (end_year - start_year) * 12 + end_month - 1)
        pop = people_nearby(confirmed)
        for i, f in enumerate(confirmed, 1):
            f["properties"].update({"site": i, "optical_last_water": t[i]["last_month_water"],
                                    "optical_land_from": t[i]["first_month_land"], "people_500m": pop[i - 1]})
    with open(os.path.join(out, "sites.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": confirmed}, f)
    with open(os.path.join(out, "sites.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["site", "lat", "lon", "area_ha", "optical_last_water", "optical_land_from",
                    "radar_vv_before_db", "radar_vv_after_db", "people_within_500m", "map_link"])
        for ft in confirmed:
            p = ft["properties"]
            w.writerow([p["site"], round(p["lat"], 5), round(p["lon"], 5), round(p["area_ha"], 2),
                        p["optical_last_water"], p["optical_land_from"], p["vv_before_db"], p["vv_after_db"],
                        p["people_500m"], f"https://www.openstreetmap.org/?mlat={p['lat']:.5f}&mlon={p['lon']:.5f}"
                                          f"#map=17/{p['lat']:.5f}/{p['lon']:.5f}"])
            print(f"  #{p['site']:2d} {p['lat']:.5f},{p['lon']:.5f}  {p['area_ha']:5.2f} ha  "
                  f"land from {p['optical_land_from']}  ~{p['people_500m']:,} people within 500 m")
    print(f"-> {out}")


# ---------------------------------------------------------------- global screen (2023 -> 2026)

SCREEN_OUT = os.path.join(OUT, "recent_infill")
SCREEN_THEN, SCREEN_NOW = ("2023-01-01", "2023-07-01"), ("2026-04-01", "2026-11-15")
EXTRA = {  # more cities with many urban lakes / wetlands (lat, lon)
    "wuhan": (30.58, 114.30), "hanoi": (21.03, 105.83), "dhaka": (23.78, 90.40), "kolkata": (22.55, 88.40),
    "chennai": (13.05, 80.22), "jakarta": (-6.20, 106.82), "manila": (14.60, 120.98), "lagos": (6.50, 3.38),
    "srinagar": (34.09, 74.80), "bhopal": (23.24, 77.40), "udaipur": (24.58, 73.70), "pune": (18.52, 73.86),
    "ahmedabad": (23.03, 72.58), "lucknow": (26.85, 80.95), "patna": (25.60, 85.12), "guwahati": (26.15, 91.75),
    "kampala": (0.33, 32.58), "nairobi": (-1.29, 36.82), "dar_es_salaam": (-6.80, 39.25), "accra": (5.60, -0.19),
    "colombo": (6.92, 79.86), "yangon": (16.85, 96.15), "bangkok": (13.75, 100.55), "ho_chi_minh": (10.80, 106.68),
    "baghdad": (33.33, 44.40), "tehran": (35.70, 51.40), "bogota": (4.65, -74.10), "lima": (-12.05, -77.04),
    "mexico_city": (19.43, -99.13), "villahermosa": (17.99, -92.93), "belem": (-1.40, -48.48), "manaus": (-3.10, -60.02),
}


def screen_boxes():
    b = dict(archive.ALL)
    b.update({n: [lo - 0.12, la - 0.12, lo + 0.12, la + 0.12] for n, (la, lo) in EXTRA.items()})
    b.update({"ro_" + n: v["train"] for n, v in terrain.REGIONS.items()})
    return b


def screen_scan(bbox, min_ha=1.0):
    geom = box(bbox)
    t, n = dw_mean(geom, *SCREEN_THEN), dw_mean(geom, *SCREEN_NOW)
    m = (occurrence().gte(50).And(t.select("water").gte(0.7)).And(n.select("water").lte(0.2))
         .And(n.select("built").add(n.select("bare")).gte(0.5)))
    m = m.updateMask(m.connectedPixelCount(100, True).gte(int(min_ha * 1e4 / 400))).selfMask()
    vecs = m.reduceToVectors(geometry=geom, scale=20, geometryType="polygon", eightConnected=True,
                             labelProperty="v", maxPixels=1e10, tileScale=8)
    rad = radar.vv(geom, *SCREEN_THEN).rename("vv_before").addBands(radar.vv(geom, *SCREEN_NOW).rename("vv_after"))
    vecs = rad.reduceRegions(vecs, ee.Reducer.median(), 20, tileScale=8)

    def enrich(f):
        c = f.geometry().centroid(1).coordinates()
        return f.set({"area_ha": f.geometry().area(1).divide(1e4), "lon": c.get(0), "lat": c.get(1)})
    return vecs.map(enrich).filter(ee.Filter.gte("area_ha", min_ha)).sort("area_ha", False).limit(30).getInfo()


def screen_rows(name, gj):
    rows = []
    for f in gj["features"]:
        p = f["properties"]
        b, a = p.get("vv_before"), p.get("vv_after")
        rows.append([name, round(p["lat"], 5), round(p["lon"], 5), round(p["area_ha"], 2),
                     None if b is None else round(b, 1), None if a is None else round(a, 1), radar.is_confirmed(b, a)])
    return rows


def write_screen_csv(out=None):
    """Rebuild all.csv from every cached city file, so partial or parallel runs never drop cities."""
    out = out or SCREEN_OUT
    rows = []
    for fn in sorted(os.listdir(out)):
        if fn.endswith(".geojson"):
            with open(os.path.join(out, fn), encoding="utf-8") as f:
                rows += screen_rows(fn[:-len(".geojson")], json.load(f))
    tmp = os.path.join(out, "all.csv.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("city,lat,lon,area_ha,vv_before,vv_after,radar_confirmed\n")
        for r in rows:
            f.write(",".join(map(str, r)) + "\n")
    os.replace(tmp, os.path.join(out, "all.csv"))
    return rows


def screen(names=None):
    init()
    os.makedirs(SCREEN_OUT, exist_ok=True)
    boxes = screen_boxes()
    for name in names or list(boxes):
        path = os.path.join(SCREEN_OUT, f"{name}.geojson")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                gj = json.load(f)
        else:
            try:
                gj = screen_scan(boxes[name])
            except Exception as e:
                print(f"{name}: FAILED {str(e)[:120]}")
                continue
            with open(path, "w", encoding="utf-8") as f:
                json.dump(gj, f)
        rows = screen_rows(name, gj)
        conf = [r for r in rows if r[6]]
        print(f"{name:16s} patches={len(rows):2d} radar-confirmed={len(conf):2d} {sum(r[3] for r in conf):6.1f} ha"
              if rows else f"{name:16s} -", flush=True)
    rows = write_screen_csv()
    print(f"all.csv: {len({r[0] for r in rows})} cities with patches, {len(rows)} patches, {sum(r[6] for r in rows)} radar-confirmed")
