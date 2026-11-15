"""Sentinel-1 radar: confirm that water became land, and date the change.

Open calm water is very dark in VV backscatter; sand fill or buildings are brighter. One rule is
used everywhere in the project:
    confirmed  <=>  median VV before <= BEFORE_MAX_DB  and  (after - before) >= MIN_CHANGE_DB
Fresh smooth sand can stay fairly dark (about -15 dB), so we test the change, not an absolute
"land" threshold.
"""
import ee
import numpy as np

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
    """Radar check for GeoJSON features: one dict per feature (same order) with
    vv_before_db, vv_after_db, radar_confirmed."""
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(f["geometry"]), {"id": i}) for i, f in enumerate(features)])
    img = vv(fc.geometry(), *before).rename("before").addBands(vv(fc.geometry(), *after).rename("after"))
    by_id = {r["properties"]["id"]: r["properties"]
             for r in img.reduceRegions(fc, ee.Reducer.median(), 10, tileScale=4).getInfo()["features"]}
    out = []
    for i in range(len(features)):
        b, a = by_id.get(i, {}).get("before"), by_id.get(i, {}).get("after")
        out.append({"vv_before_db": None if b is None else round(b, 1),
                    "vv_after_db": None if a is None else round(a, 1),
                    "radar_confirmed": is_confirmed(b, a)})
    return out


def series(features, start, end):
    """Per-acquisition median VV for each feature: {site_number: sorted [(YYYY-MM-DD, dB), ...]}.
    One row per (image, site), so a missing value can never shift onto another site."""
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(f["geometry"]), {"id": i + 1})
                               for i, f in enumerate(features)])

    def per_img(img):
        d = img.date().format("YYYY-MM-dd")
        return img.reduceRegions(fc, ee.Reducer.median().setOutputs(["vv"]), 10).map(
            lambda f: ee.Feature(None, {"id": f.get("id"), "vv": f.get("vv"), "date": d}))
    rows = ee.FeatureCollection(s1_vv(fc.geometry()).filterDate(start, end).map(per_img)).flatten().getInfo()
    out = {i: [] for i in range(1, len(features) + 1)}
    for r in rows["features"]:
        p = r["properties"]
        if p.get("vv") is not None:
            out[p["id"]].append((p["date"], p["vv"]))
    return {i: sorted(s) for i, s in out.items()}


def change_date(s, split="2023-07-01", min_change=MIN_CHANGE_DB, persist=0.8, water_margin=1.5):
    """s: sorted [(YYYY-MM-DD, VV dB)]. Baseline = median before `split`.
    Land from = first acquisition >= baseline + min_change after which at least `persist` of all
    later acquisitions (>= 3 of them) are also that bright. Last water = last earlier acquisition
    within `water_margin` dB of the baseline. None if there is no baseline."""
    before = [v for d, v in s if d < split]
    if not before:
        return None
    base = float(np.median(before))
    land_from = None
    for k in range(len(s)):
        rest = [v for _, v in s[k:]]
        if (len(rest) >= 3 and s[k][1] >= base + min_change
                and np.mean([v >= base + min_change for v in rest]) >= persist):
            land_from = s[k][0]
            break
    last_water = None
    if land_from:
        dark = [d for d, v in s if d < land_from and v <= base + water_margin]
        last_water = dark[-1] if dark else None
    return {"base_db": round(base, 1), "radar_last_water": last_water,
            "radar_land_from": land_from, "n_obs": len(s)}
