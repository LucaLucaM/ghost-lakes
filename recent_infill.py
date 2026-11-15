"""Recent infill scanner: lakes / ponds / lagoons that were long-term water and became land
between H1 2023 and 2026. Optical (Dynamic World) detection + Sentinel-1 radar confirmation.

Detection (per city box, 20 m):
  JRC occurrence 1984-2021 >= 50 %             (it was real, persistent water)
  DW P(water) Jan-Jun 2023 >= 0.7              (still water in 2023)
  DW P(water) Apr-Nov 2026 <= 0.2 and built+bare >= 0.5   (land now)
Radar confirmation per patch: S1 VV median H1 2023 <= -17 dB and Apr-Nov 2026 at least +3 dB brighter.

Run:  python recent_infill.py [city ...]
"""
import json
import os
import sys

import ee

import ghostlakes as gl
import radar_check as rc
import vanished as vn

OUT = os.path.join(gl.OUT, "recent_infill")
MIN_HA = 1.0
THEN = ("2023-01-01", "2023-07-01")
NOW = ("2026-04-01", "2026-11-15")

EXTRA = {  # more cities with many urban lakes / wetlands (lat, lon centres)
    "wuhan": (30.58, 114.30), "hanoi": (21.03, 105.83), "dhaka": (23.78, 90.40), "kolkata": (22.55, 88.40),
    "chennai": (13.05, 80.22), "jakarta": (-6.20, 106.82), "manila": (14.60, 120.98), "lagos": (6.50, 3.38),
    "srinagar": (34.09, 74.80), "bhopal": (23.24, 77.40), "udaipur": (24.58, 73.70), "pune": (18.52, 73.86),
    "ahmedabad": (23.03, 72.58), "lucknow": (26.85, 80.95), "patna": (25.60, 85.12), "guwahati": (26.15, 91.75),
    "kampala": (0.33, 32.58), "nairobi": (-1.29, 36.82), "dar_es_salaam": (-6.80, 39.25), "accra": (5.60, -0.19),
    "colombo": (6.92, 79.86), "yangon": (16.85, 96.15), "bangkok": (13.75, 100.55), "ho_chi_minh": (10.80, 106.68),
    "baghdad": (33.33, 44.40), "tehran": (35.70, 51.40), "bogota": (4.65, -74.10), "lima": (-12.05, -77.04),
    "mexico_city": (19.43, -99.13), "villahermosa": (17.99, -92.93), "belem": (-1.40, -48.48), "manaus": (-3.10, -60.02),
}
ROMANIA = {k: v["train"] for k, v in gl.REGIONS.items()}


def boxes():
    b = dict(vn.CITIES)
    for n, (la, lo) in EXTRA.items():
        b[n] = [lo - 0.12, la - 0.12, lo + 0.12, la + 0.12]
    for n, bb in ROMANIA.items():
        b["ro_" + n] = bb
    return b


def dw(geom, a, b):
    return (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(geom).filterDate(a, b)
            .select(["water", "built", "bare"]).mean())


def scan(bbox):
    geom = gl.box(bbox)
    t, n = dw(geom, *THEN), dw(geom, *NOW)
    occ = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0)
    m = (occ.gte(50).And(t.select("water").gte(0.7)).And(n.select("water").lte(0.2))
         .And(n.select("built").add(n.select("bare")).gte(0.5)))
    m = m.updateMask(m.connectedPixelCount(100, True).gte(int(MIN_HA * 1e4 / 400))).selfMask()
    vecs = m.reduceToVectors(geometry=geom, scale=20, geometryType="polygon", eightConnected=True,
                             labelProperty="v", maxPixels=1e10, tileScale=8)
    radar = rc.vv(geom, *THEN).rename("vv_before").addBands(rc.vv(geom, *NOW).rename("vv_after"))
    vecs = radar.reduceRegions(vecs, ee.Reducer.median(), 20, tileScale=8)

    def enrich(f):
        g = f.geometry()
        c = g.centroid(1).coordinates()
        return f.set({"area_ha": g.area(1).divide(1e4), "lon": c.get(0), "lat": c.get(1)})
    return vecs.map(enrich).filter(ee.Filter.gte("area_ha", MIN_HA)).sort("area_ha", False).limit(30).getInfo()


def rows_for(name, gj):
    rows = []
    for f in gj["features"]:
        p = f["properties"]
        b, a = p.get("vv_before"), p.get("vv_after")
        ok = rc.is_confirmed(b, a)
        rows.append([name, round(p["lat"], 5), round(p["lon"], 5), round(p["area_ha"], 2),
                     None if b is None else round(b, 1), None if a is None else round(a, 1), ok])
    return rows


def write_all_csv():
    """Rebuild all.csv from every cached city file, so partial or parallel runs never drop cities."""
    rows = []
    for fn in sorted(os.listdir(OUT)):
        if fn.endswith(".geojson"):
            with open(os.path.join(OUT, fn), encoding="utf-8") as f:
                rows += rows_for(fn[:-len(".geojson")], json.load(f))
    tmp = os.path.join(OUT, "all.csv.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("city,lat,lon,area_ha,vv_before,vv_after,radar_confirmed\n")
        for r in rows:
            f.write(",".join(map(str, r)) + "\n")
    os.replace(tmp, os.path.join(OUT, "all.csv"))
    return rows


def main(names):
    gl.init()
    os.makedirs(OUT, exist_ok=True)
    allb = boxes()
    for name in names or list(allb):
        path = os.path.join(OUT, f"{name}.geojson")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                gj = json.load(f)
        else:
            try:
                gj = scan(allb[name])
            except Exception as e:
                print(f"{name}: FAILED {str(e)[:120]}")
                continue
            with open(path, "w", encoding="utf-8") as f:
                json.dump(gj, f)
        rows = rows_for(name, gj)
        conf = [r for r in rows if r[6]]
        if rows:
            print(f"{name:16s} patches={len(rows):2d} radar-confirmed={len(conf):2d} "
                  f"{sum(r[3] for r in conf):6.1f} ha  "
                  + "  ".join(f"{r[3]:.1f}ha@{r[1]:.4f},{r[2]:.4f}" for r in conf[:3]), flush=True)
        else:
            print(f"{name:16s} -", flush=True)
    rows = write_all_csv()
    print(f"all.csv: {len({r[0] for r in rows})} cities, {len(rows)} patches, "
          f"{sum(r[6] for r in rows)} radar-confirmed")


if __name__ == "__main__":
    main(sys.argv[1:])
