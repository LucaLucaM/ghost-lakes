"""Archive detector: water seen by Landsat (JRC yearly history) that has gone and is built-up today.

Per city box, keep pixels with
  (water in >= MIN_EARLY_YEARS of 1984-2000 and no water 2015-2021, or JRC transition 'lost')
  and Dynamic World 2024 P(built) >= BUILT_MIN
  and permanent water in >= perm_min years of 1984-2009 (drops flooded rice paddies),
grouped into patches >= MIN_HA.

Reproducibility: the first wave (CITIES, reported in docs/FINDINGS.md: Lusaka, Bengaluru, Nellore...)
was run with perm_min = 0 and is cached in outputs/vanished_wave1; the second wave (CENTRES) used 3.
"""
import json
import os

import ee

from .common import OUT, box, init

MIN_EARLY_YEARS, MIN_HA, BUILT_MIN = 2, 2, 0.3

# lon_min, lat_min, lon_max, lat_max
CITIES = {
    "bengaluru": [77.45, 12.80, 77.80, 13.15], "hyderabad": [78.30, 17.25, 78.65, 17.55],
    "vijayawada": [80.55, 16.45, 80.75, 16.60], "warangal": [79.48, 17.92, 79.66, 18.05],
    "nellore": [79.92, 14.38, 80.05, 14.50], "raipur": [81.55, 21.18, 81.72, 21.32],
    "madurai": [78.05, 9.87, 78.20, 9.99], "tiruchirappalli": [78.62, 10.75, 78.76, 10.87],
    "coimbatore": [76.88, 10.93, 77.08, 11.08], "hubballi": [75.05, 15.30, 75.20, 15.42],
    "aurangabad": [75.25, 19.82, 75.42, 19.94], "jaipur": [75.70, 26.78, 75.92, 27.00],
    "chattogram": [91.75, 22.28, 91.90, 22.42], "sylhet": [91.82, 24.86, 91.93, 24.94],
    "can_tho": [105.70, 9.98, 105.82, 10.08], "phnom_penh": [104.82, 11.48, 105.00, 11.65],
    "kano": [8.42, 11.92, 8.62, 12.08], "ouagadougou": [-1.62, 12.28, -1.42, 12.45],
    "niamey": [2.03, 13.45, 2.20, 13.58], "lusaka": [28.20, -15.50, 28.40, -15.32],
    "antananarivo": [47.45, -18.98, 47.60, -18.83], "ndjamena": [14.98, 12.05, 15.15, 12.18],
    "erbil": [43.92, 36.12, 44.10, 36.25], "tashkent": [69.15, 41.22, 69.40, 41.40],
}
# Second wave: less-studied cities as centres (lat, lon); box = +-0.11 deg.
CENTRES = {
    "abuja": (9.06, 7.49), "kaduna": (10.52, 7.44), "maiduguri": (11.85, 13.16), "ibadan": (7.38, 3.93),
    "kumasi": (6.69, -1.62), "tamale": (9.40, -0.84), "bamako": (12.64, -8.00), "dakar": (14.72, -17.45),
    "conakry": (9.60, -13.62), "freetown": (8.47, -13.24), "abidjan": (5.35, -4.01), "lome": (6.15, 1.22),
    "cotonou": (6.39, 2.40), "douala": (4.05, 9.74), "yaounde": (3.87, 11.52), "bangui": (4.37, 18.56),
    "kinshasa": (-4.36, 15.30), "lubumbashi": (-11.66, 27.48), "luanda": (-8.84, 13.27), "harare": (-17.83, 31.05),
    "bulawayo": (-20.15, 28.58), "lilongwe": (-13.97, 33.79), "blantyre": (-15.79, 35.01), "maputo": (-25.94, 32.58),
    "nampula": (-15.12, 39.27), "dodoma": (-6.17, 35.75), "mwanza": (-2.52, 32.92), "kigali": (-1.95, 30.08),
    "bujumbura": (-3.38, 29.36), "juba": (4.85, 31.58), "khartoum": (15.55, 32.53), "addis_ababa": (9.01, 38.76),
    "hawassa": (7.05, 38.48), "mekelle": (13.50, 39.47), "hargeisa": (9.56, 44.06), "nouakchott": (18.08, -15.97),
    "mosul": (36.34, 43.13), "kirkuk": (35.47, 44.39), "basra": (30.51, 47.81), "sulaymaniyah": (35.56, 45.43),
    "herat": (34.35, 62.20), "kandahar": (31.61, 65.71), "quetta": (30.18, 66.99), "peshawar": (34.01, 71.55),
    "multan": (30.20, 71.47), "faisalabad": (31.42, 73.08), "samarkand": (39.65, 66.96), "bukhara": (39.77, 64.42),
    "ashgabat": (37.95, 58.38), "dushanbe": (38.56, 68.78), "bishkek": (42.87, 74.59), "ulaanbaatar": (47.92, 106.92),
    "mandalay": (21.96, 96.09), "vientiane": (17.97, 102.61), "kathmandu": (27.70, 85.32), "biratnagar": (26.46, 87.28),
    "rajshahi": (24.37, 88.60), "khulna": (22.82, 89.55), "mymensingh": (24.75, 90.41), "jessore": (23.17, 89.21),
}
ALL = {**CITIES, **{n: [lo - 0.11, la - 0.11, lo + 0.11, la + 0.11] for n, (la, lo) in CENTRES.items()}}


def vanished_layer(geom, perm_min):
    yh = ee.ImageCollection("JRC/GSW1_4/YearlyHistory")

    def years(a, b, cond):
        return yh.filter(ee.Filter.rangeContains("year", a, b)).map(lambda i: cond(i).unmask(0)).sum()
    early = years(1984, 2000, lambda i: i.gte(2)).rename("early_wet")
    late = years(2015, 2021, lambda i: i.gte(2))
    perm = years(1984, 2009, lambda i: i.eq(3))
    built = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(geom)
             .filterDate("2024-01-01", "2025-01-01").select("built").mean())
    lost = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("transition").remap([3, 6], [1, 1], 0)  # lost perm./seasonal
    had_water = early.gte(MIN_EARLY_YEARS).And(late.eq(0)).Or(lost.eq(1))
    return had_water.And(built.gte(BUILT_MIN)).And(perm.gte(perm_min)), early, built


def scan(bbox, perm_min):
    geom = box(bbox)
    mask, early, built = vanished_layer(geom, perm_min)
    mask = mask.updateMask(mask.connectedPixelCount(500, True).gte(int(MIN_HA * 1e4 / 900)))
    vecs = mask.selfMask().addBands(early).reduceToVectors(
        geometry=geom, scale=30, geometryType="polygon", eightConnected=True,
        reducer=ee.Reducer.mean(), labelProperty="zone", maxPixels=1e10, tileScale=4)
    vecs = vecs.map(lambda f: f.set("early_wet_years", f.get("mean")))
    vecs = built.rename("built").reduceRegions(vecs, ee.Reducer.mean().setOutputs(["built"]), 30, tileScale=4)

    def enrich(f):
        c = f.geometry().centroid(1).coordinates()
        return f.set({"area_ha": f.geometry().area(1).divide(1e4), "lon": c.get(0), "lat": c.get(1)})
    return vecs.map(enrich).filter(ee.Filter.gte("area_ha", MIN_HA)).sort("area_ha", False).limit(40).getInfo()


def out_dir(perm_min):
    return {3: os.path.join(OUT, "vanished"), 0: os.path.join(OUT, "vanished_wave1")}.get(
        perm_min, os.path.join(OUT, f"vanished_perm{perm_min}"))


def write_summary(out):
    """Rebuild all_patches.csv from every cached city in `out`, so partial runs never drop cities."""
    def r(v, n):
        return None if v is None else round(v, n)
    rows = []
    for fn in sorted(os.listdir(out)):
        if fn.endswith(".geojson"):
            with open(os.path.join(out, fn), encoding="utf-8") as f:
                for ft in json.load(f)["features"]:
                    p = ft["properties"]
                    rows.append([fn[:-8], r(p["lat"], 5), r(p["lon"], 5), r(p["area_ha"], 1),
                                 r(p.get("early_wet_years"), 1), r(p.get("built"), 2)])
    with open(os.path.join(out, "all_patches.csv"), "w", encoding="utf-8") as f:
        f.write("city,lat,lon,area_ha,early_wet_years,built\n")
        for row in rows:
            f.write(",".join(map(str, row)) + "\n")


def run(names=None, perm_min=3):
    init()
    out = out_dir(perm_min)
    os.makedirs(out, exist_ok=True)
    for name in names or list(ALL):
        path = os.path.join(out, f"{name}.geojson")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                gj = json.load(f)
        else:
            try:
                gj = scan(ALL[name], perm_min)
            except Exception as e:
                print(f"{name}: FAILED {e}")
                continue
            with open(path, "w", encoding="utf-8") as f:
                json.dump(gj, f)
        fs = gj["features"]
        print(f"{name:16s} patches={len(fs):3d}  total={sum(f['properties']['area_ha'] for f in fs):7.1f} ha  "
              + "  ".join(f"{f['properties']['area_ha']:.0f}ha@{f['properties']['lat']:.4f},{f['properties']['lon']:.4f}"
                          for f in fs[:3]))
    write_summary(out)
