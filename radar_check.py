"""Independent check with Sentinel-1 radar (sees through clouds).

Open calm water is very dark in VV backscatter; sand fill or buildings are brighter.
Rule used everywhere in this project (lagoon_infill.py, recent_infill.py and this CLI):
  confirmed  <=>  median VV before <= BEFORE_MAX_DB  and  (after - before) >= MIN_CHANGE_DB
Smooth fresh sand can stay fairly dark (around -15 dB), so we test the change, not an absolute
"land" threshold.

Usage: python radar_check.py polygons.geojson BEFORE_START BEFORE_END AFTER_START AFTER_END
"""
import json
import sys

import ee

import ghostlakes as gl

BEFORE_MAX_DB = -17.0
MIN_CHANGE_DB = 3.0


def s1_vv(geom):
    return (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(geom)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            .select("VV"))


def vv(geom, a, b):
    return s1_vv(geom).filterDate(a, b).median()


def is_confirmed(before, after):
    return (before is not None and after is not None
            and before <= BEFORE_MAX_DB and after - before >= MIN_CHANGE_DB)


def confirm(features, before, after):
    """features: list of GeoJSON features. Returns one dict per feature (same order) with
    vv_before_db, vv_after_db, radar_confirmed."""
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(f["geometry"]), {"id": i})
                               for i, f in enumerate(features)])
    img = vv(fc.geometry(), *before).rename("before").addBands(vv(fc.geometry(), *after).rename("after"))
    rows = img.reduceRegions(fc, ee.Reducer.median(), 10, tileScale=4).getInfo()["features"]
    by_id = {r["properties"]["id"]: r["properties"] for r in rows}
    out = []
    for i in range(len(features)):
        p = by_id.get(i, {})
        b, a = p.get("before"), p.get("after")
        out.append({"vv_before_db": None if b is None else round(b, 1),
                    "vv_after_db": None if a is None else round(a, 1),
                    "radar_confirmed": is_confirmed(b, a)})
    return out


def main(path, b0, b1, a0, a1):
    gl.init()
    with open(path, encoding="utf-8") as f:
        gj = json.load(f)
    res = confirm(gj["features"], (b0, b1), (a0, a1))
    for i, r in enumerate(res, 1):
        b, a = r["vv_before_db"], r["vv_after_db"]
        change = "" if b is None or a is None else f"change {a - b:+5.1f} dB"
        print(f"#{i:2d}  VV before {b} dB   after {a} dB   {change}   "
              f"{'CONFIRMED' if r['radar_confirmed'] else 'not confirmed'}")
    print(f"{sum(r['radar_confirmed'] for r in res)}/{len(res)} confirmed by radar "
          f"(rule: before <= {BEFORE_MAX_DB} dB and change >= +{MIN_CHANGE_DB} dB)")


if __name__ == "__main__":
    main(*sys.argv[1:6])
