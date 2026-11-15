"""Radar-only detection of Ébrié lagoon infill AFTER the Prime Minister's stop order (11 June 2026).

Sentinel-1 sees through clouds, so we can compare narrow windows:
  before: 2026-03-01 .. 2026-06-10   VV median <= -17 dB  (open water)
  after : 2026-08-15 .. 2026-11-15   VV median at least +4 dB brighter and >= -15 dB
plus JRC occurrence >= 50 (long-term lagoon water), patches >= 0.2 ha.
Then a per-acquisition VV time series for every patch to date the change (~12-day revisit).
Run:  python abidjan_radar_recent.py
"""
import json
import os

import ee

import ghostlakes as gl

BOX = [-4.12, 5.22, -3.70, 5.42]
BEFORE = ("2026-03-01", "2026-06-10")
AFTER = ("2026-08-15", "2026-11-15")
MIN_HA = 0.2


def s1(geom):
    return (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(geom)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")).select("VV"))


def main():
    gl.init()
    geom = gl.box(BOX)
    col = s1(geom)
    # light speckle smoothing
    b = col.filterDate(*BEFORE).median().focalMean(15, "circle", "meters")
    a = col.filterDate(*AFTER).median().focalMean(15, "circle", "meters")
    occ = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0)
    m = b.lte(-17).And(a.subtract(b).gte(4)).And(a.gte(-15)).And(occ.gte(50))
    m = m.updateMask(m.connectedPixelCount(100, True).gte(int(MIN_HA * 1e4 / 100))).selfMask()
    vecs = m.reduceToVectors(geometry=geom, scale=10, geometryType="polygon", eightConnected=True,
                             labelProperty="v", maxPixels=1e10, tileScale=8)

    def enrich(f):
        g = f.geometry()
        c = g.centroid(1).coordinates()
        return f.set({"area_ha": g.area(1).divide(1e4), "lon": c.get(0), "lat": c.get(1)})
    vecs = vecs.map(enrich).filter(ee.Filter.gte("area_ha", MIN_HA)).sort("area_ha", False)
    gj = vecs.getInfo()
    print(f"patches: {len(gj['features'])}, total {sum(f['properties']['area_ha'] for f in gj['features']):.2f} ha")
    if not gj["features"]:
        return

    # per-acquisition time series (Jan 2026 - now) for each patch
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(f["geometry"]), {"id": i + 1})
                               for i, f in enumerate(gj["features"])])
    ts_col = col.filterBounds(fc.geometry()).filterDate("2026-01-01", "2026-11-16").sort("system:time_start")
    def per_img(img):
        d = img.date().format("YYYY-MM-dd")
        vals = img.reduceRegions(fc, ee.Reducer.median().setOutputs(["vv"]), 10)
        return ee.Feature(None, {"date": d, "orbit": img.get("relativeOrbitNumber_start"),
                                 "vv": vals.sort("id").aggregate_array("vv")})
    ts = ee.FeatureCollection(ts_col.map(per_img)).getInfo()["features"]
    series = {i + 1: [] for i in range(len(gj["features"]))}
    for t in ts:
        for i, v in enumerate(t["properties"]["vv"]):
            series[i + 1].append((t["properties"]["date"], t["properties"]["orbit"], v))
    for i, f in enumerate(gj["features"], 1):
        p = f["properties"]
        s = series[i]
        # change date = first acquisition after which all values are > -15 dB
        change = None
        for k in range(len(s)):
            if all(v is not None and v > -15 for _, _, v in s[k:]) and k > 0:
                change = (s[k - 1][0], s[k][0])
                break
        p["last_water_obs"], p["first_land_obs"] = change if change else (None, None)
        p["series"] = s
        print(f"#{i:2d} {p['lat']:.5f},{p['lon']:.5f} {p['area_ha']:.2f} ha  water until {p['last_water_obs']}  "
              f"land from {p['first_land_obs']}  | "
              + "".join("#" if (v or 0) <= -17 else ("+" if (v or 0) <= -15 else ".") for _, _, v in s))
    json.dump(gj, open(os.path.join(gl.OUT, "abidjan_after_pm_order.geojson"), "w"))


if __name__ == "__main__":
    main()
