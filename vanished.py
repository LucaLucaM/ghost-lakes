"""Vanished water bodies: places the Landsat archive saw as water in 1984-2000 that are
built-up today and have not been water since 2015.

Unlike the terrain model (which says where water *should* be), this gives direct satellite
evidence that a lake/pond/wetland existed and was later built over.

Per city box:
  early_wet  = years 1984-2000 classified water (JRC YearlyHistory class 2 or 3)
  late_wet   = years 2015-2021 classified water
  built      = Dynamic World mean P(built), 2024
Keep pixels with early_wet >= MIN_EARLY_YEARS, late_wet == 0, built >= 0.5,
group into patches >= MIN_HA, and report them with simple descriptors.

Run:  python vanished.py [city ...]      (default: all in CITIES)
"""
import json
import os
import sys

import ee

import ghostlakes as gl

MIN_EARLY_YEARS = 2
MIN_HA = 2
OUT = os.path.join(gl.OUT, "vanished")

# Fast-growing cities with little lake-by-lake documentation online (plus 2 controls).
# lon_min, lat_min, lon_max, lat_max
CITIES = {
    # controls (lake loss well documented)
    "bengaluru": [77.45, 12.80, 77.80, 13.15],
    "hyderabad": [78.30, 17.25, 78.65, 17.55],
    # India, tier-2
    "vijayawada": [80.55, 16.45, 80.75, 16.60],
    "warangal": [79.48, 17.92, 79.66, 18.05],
    "nellore": [79.92, 14.38, 80.05, 14.50],
    "raipur": [81.55, 21.18, 81.72, 21.32],
    "madurai": [78.05, 9.87, 78.20, 9.99],
    "tiruchirappalli": [78.62, 10.75, 78.76, 10.87],
    "coimbatore": [76.88, 10.93, 77.08, 11.08],
    "hubballi": [75.05, 15.30, 75.20, 15.42],
    "aurangabad": [75.25, 19.82, 75.42, 19.94],
    "jaipur": [75.70, 26.78, 75.92, 27.00],
    # Bangladesh / SE Asia
    "chattogram": [91.75, 22.28, 91.90, 22.42],
    "sylhet": [91.82, 24.86, 91.93, 24.94],
    "can_tho": [105.70, 9.98, 105.82, 10.08],
    "phnom_penh": [104.82, 11.48, 105.00, 11.65],
    # Africa
    "kano": [8.42, 11.92, 8.62, 12.08],
    "ouagadougou": [-1.62, 12.28, -1.42, 12.45],
    "niamey": [2.03, 13.45, 2.20, 13.58],
    "lusaka": [28.20, -15.50, 28.40, -15.32],
    "antananarivo": [47.45, -18.98, 47.60, -18.83],
    "ndjamena": [14.98, 12.05, 15.15, 12.18],
    # Middle East / Central Asia
    "erbil": [43.92, 36.12, 44.10, 36.25],
    "tashkent": [69.15, 41.22, 69.40, 41.40],
}

# Second wave: less-studied cities, given as centres (lat, lon); box = +-0.11 deg.
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
for _n, (_la, _lo) in CENTRES.items():
    CITIES[_n] = [_lo - 0.11, _la - 0.11, _lo + 0.11, _la + 0.11]


def vanished_layer(geom):
    yh = ee.ImageCollection("JRC/GSW1_4/YearlyHistory")
    wet = lambda a, b: (yh.filter(ee.Filter.rangeContains("year", a, b))
                        .map(lambda i: i.gte(2).unmask(0)).sum())
    early = wet(1984, 2000).rename("early_wet")
    # years of *permanent* water (class 3) at any time before 2010: filters out flooded paddies
    perm = (yh.filter(ee.Filter.rangeContains("year", 1984, 2009))
            .map(lambda i: i.eq(3).unmask(0)).sum())
    late = wet(2015, 2021).rename("late_wet")
    dw = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(geom)
          .filterDate("2024-01-01", "2025-01-01").select(["built", "water", "crops", "trees", "grass", "bare"]).mean())
    built = dw.select("built")
    # JRC transition classes 3 = "lost permanent", 6 = "lost seasonal" (first vs last year of record)
    lost = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("transition").remap([3, 6], [1, 1], 0)
    had_water = early.gte(MIN_EARLY_YEARS).And(late.eq(0)).Or(lost.eq(1))
    mask = had_water.And(built.gte(0.3)).And(perm.gte(3))
    return mask, early, built, dw


def scan(name, bbox):
    geom = gl.box(bbox)
    mask, early, built, dw = vanished_layer(geom)
    mask = mask.updateMask(mask.connectedPixelCount(500, True).gte(int(MIN_HA * 1e4 / 900)))
    vecs = (mask.selfMask().addBands(early)
            .reduceToVectors(geometry=geom, scale=30, geometryType="polygon", eightConnected=True,
                             reducer=ee.Reducer.mean(), labelProperty="zone", maxPixels=1e10, tileScale=4))
    vecs = vecs.map(lambda f: f.set("early_wet_years", f.get("mean")))
    vecs = built.rename("built").reduceRegions(vecs, ee.Reducer.mean().setOutputs(["built"]), 30, tileScale=4)

    def enrich(f):
        g = f.geometry()
        a = g.area(1).divide(1e4)
        c = g.centroid(1).coordinates()
        return f.set({"area_ha": a, "lon": c.get(0), "lat": c.get(1)})
    vecs = vecs.map(enrich).filter(ee.Filter.gte("area_ha", MIN_HA)).sort("area_ha", False).limit(40)
    gj = vecs.getInfo()
    for ft in gj["features"]:
        ft["properties"]["city"] = name
    return gj


def main(names):
    gl.init()
    os.makedirs(OUT, exist_ok=True)
    summary = []
    for name in names:
        path = os.path.join(OUT, f"{name}.geojson")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                gj = json.load(f)
        else:
            try:
                gj = scan(name, CITIES[name])
            except Exception as e:
                print(f"{name}: FAILED {e}")
                continue
            with open(path, "w", encoding="utf-8") as f:
                json.dump(gj, f)
        fs = gj["features"]
        tot = sum(ft["properties"]["area_ha"] for ft in fs)
        print(f"{name:16s} patches={len(fs):3d}  total={tot:7.1f} ha  "
              + "  ".join(f"{ft['properties']['area_ha']:.0f}ha@{ft['properties']['lat']:.4f},{ft['properties']['lon']:.4f}"
                          for ft in fs[:3]))
        for ft in fs:
            p = ft["properties"]
            summary.append([name, round(p["lat"], 5), round(p["lon"], 5), round(p["area_ha"], 1),
                            round(p["early_wet_years"], 1), round(p["built"], 2)])
    with open(os.path.join(OUT, "all_patches.csv"), "w", encoding="utf-8") as f:
        f.write("city,lat,lon,area_ha,early_wet_years,built\n")
        for r in summary:
            f.write(",".join(map(str, r)) + "\n")


if __name__ == "__main__":
    main(sys.argv[1:] or list(CITIES))
