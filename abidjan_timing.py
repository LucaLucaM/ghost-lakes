"""Month in which each Abidjan infill site turned from lagoon water into land.

Uses Dynamic World P(water), 2-month window starting at each month, Jan 2023 - Oct 2026,
averaged over each site polygon. Cloud-masked pixels are ignored (not counted as anything),
and a window is only used if at least MIN_VALID of the polygon has a valid value.
'last_month_water' = last window with P(water) >= 0.5; 'first_month_land' = first later window
with P(water) < 0.3. Months are window starts, so dates are approximate (about +-1 month).
Run after lagoon_infill.py:  python abidjan_timing.py
"""
import json
import os

import ee

import ghostlakes as gl

MIN_VALID = 0.5   # fraction of the polygon that must be cloud-free in a window
N_MONTHS = 46     # Jan 2023 .. Oct 2026


def window_mean(col, start, label):
    """Mean P(water) for a 2-month window; a fully masked band if the window has no images."""
    win = col.filterDate(start, start.advance(2, "month"))
    empty = ee.Image.constant(0).toFloat().updateMask(ee.Image.constant(0))
    return ee.Image(ee.Algorithms.If(win.size().gt(0), win.mean(), empty)).rename(label)


def main():
    gl.init()
    with open(os.path.join(gl.OUT, "abidjan_infill.geojson"), encoding="utf-8") as f:
        gj = json.load(f)
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(ft["geometry"]), {"id": i + 1})
                               for i, ft in enumerate(gj["features"])])
    dw = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(fc.geometry()).select("water")
    labels, bands = [], []
    for k in range(N_MONTHS):
        y, mo = 2023 + k // 12, k % 12 + 1
        lab = f"{y}-{mo:02d}"
        labels.append(lab)
        bands.append(window_mean(dw, ee.Date.fromYMD(y, mo, 1), lab))
    stack = ee.Image.cat(bands).addBands(ee.Image.constant(1).rename("all"))
    # mean ignores masked (cloudy) pixels; count tells us how much of the polygon was valid
    reducer = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)
    rows = stack.reduceRegions(fc, reducer, 10, tileScale=4).getInfo()["features"]
    out = {}
    for r in sorted(rows, key=lambda r: r["properties"]["id"]):
        p = r["properties"]
        i = p["id"]
        total = p.get("all_count") or 0
        s = []
        for lab in labels:
            v, n = p.get(f"{lab}_mean"), p.get(f"{lab}_count") or 0
            s.append((lab, v if (v is not None and total and n / total >= MIN_VALID) else None))
        last_wet = max((l for l, v in s if v is not None and v >= 0.5), default=None)
        first_land = next((l for l, v in s if v is not None and v < 0.3 and (last_wet is None or l > last_wet)), None)
        out[i] = {"area_ha": gj["features"][i - 1]["properties"]["area_ha"], "last_month_water": last_wet,
                  "first_month_land": first_land, "series": s}
        print(f"#{i:2d} {out[i]['area_ha']:.2f} ha  last water {last_wet}  first land {first_land}")
    with open(os.path.join(gl.OUT, "abidjan_infill_timing.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
