"""Validation: does the terrain model 'rediscover' water bodies that historians say were drained?

To avoid leakage, the model is trained on the 6 OTHER Romanian regions only (leave-Bucharest-out),
so it has never seen any Bucharest pixel, labelled or not.

For each documented former water body we take the model's water probability (mean in a 150 m
radius) and compare it with random LAND pixels of the city (anything that is not water today:
JRC occurrence < 50 and Dynamic World P(water) < 0.3). Sites are reported in two groups:
  - fully vanished : nothing left today (Icoanei, Carvasara, buried streams)
  - lake remains   : a smaller park lake still exists on the spot (Cișmigiu, Tineretului),
                     so their score partly reflects today's lake and is less informative.

Run:  python validate.py
"""
import json
import os

import ee
import numpy as np

import ghostlakes as gl

# Approximate centres of documented former water bodies (from today's landmark) — see SOURCES.
SITES = [
    # name, lat, lon, note, group
    ("Balta Icoanei (Lacul Bulindroi)", 44.4452, 26.1060, "Grădina Icoanei; drained 1873", "vanished"),
    ("Balta de la Carvasara (Lacul Șuțu)", 44.4335, 26.1060, "behind Colțea Hospital", "vanished"),
    ("Pârâul Dâmbovicioara (Calea Rahovei)", 44.4262, 26.0935, "buried stream, Dealul Spirii -> Unirii", "vanished"),
    ("Pârâul Bucureștioara (Colțea -> Unirii)", 44.4300, 26.1045, "buried stream, now in pipes", "vanished"),
    ("Balta lui Dura (Cișmigiu marsh)", 44.4370, 26.0905, "swamp, garden after 1854; small lake remains", "lake_remains"),
    ("Balta Cocioc (Tineretului)", 44.4060, 26.1080, "swamp/garbage dump, park lake built later", "lake_remains"),
]

SOURCES = [
    "https://www.bucharest.ro/articles/the-bucurestioara-stream-where-does-the-vanished-tributary-of-the-dambovita-flow-today-1498",
    "https://skia.one.ro/en/blog/the-waters-that-shape-bucharest/",
    "https://en.wikipedia.org/wiki/Lake_Ci%C8%99migiu",
]

N_RANDOM = 1500
TEST_CITY = "bucuresti"


def auc_vs(baseline, scores):
    """Probability that a site scores higher than a random baseline pixel (ties count half)."""
    if len(scores) == 0:
        return None
    return float(np.mean([(baseline < s).mean() + 0.5 * (baseline == s).mean() for s in scores]))


def main():
    gl.init()
    train_regions = [n for n in gl.REGIONS if n != TEST_CITY]
    fc = gl.sample(train_regions[0])
    for n in train_regions[1:]:
        fc = fc.merge(gl.sample(n))
    clf = gl.train(fc)

    city = gl.box(gl.REGIONS[TEST_CITY]["city"])
    p = gl.terrain_features().classify(clf).rename("p")
    p_smooth = p.reduceNeighborhood(ee.Reducer.mean(), ee.Kernel.circle(150, "meters")).rename("p")
    dw = gl.dynamic_world(city)
    occ = gl.jrc().select("occurrence").unmask(0)
    land = occ.lt(50).And(dw.select("water").lt(0.3))

    rnd = np.array(p_smooth.updateMask(land)
                   .sample(region=city, scale=gl.SCALE, numPixels=N_RANDOM * 3, seed=1, geometries=False)
                   .limit(N_RANDOM).aggregate_array("p").getInfo())

    pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([lon, lat]), {"i": i})
                                for i, (_, lat, lon, _, _) in enumerate(SITES)])
    vals = {f["properties"]["i"]: f["properties"].get("first")
            for f in p_smooth.reduceRegions(pts, ee.Reducer.first(), gl.SCALE).getInfo()["features"]}

    print(f"Model trained WITHOUT {TEST_CITY} (on {', '.join(train_regions)}).")
    print(f"Random land pixels in {TEST_CITY}: n={len(rnd)}, median p={np.median(rnd):.2f}")
    rows = []
    for i, (n, lat, lon, note, group) in enumerate(SITES):
        pv = vals.get(i)
        pct = float((rnd < pv).mean() * 100) if pv is not None else None
        rows.append({"site": n, "lat": lat, "lon": lon, "note": note, "group": group,
                     "p_water": pv, "percentile": pct})
        txt = "no value" if pv is None else f"p={pv:.2f}  -> top {100 - pct:.0f}% of the city"
        print(f"  [{group:12s}] {n:42s} {txt}")

    summary = {"city": TEST_CITY, "trained_on": train_regions, "random_land_median_p": float(np.median(rnd)),
               "sites": rows, "sources": SOURCES}
    for group in ("vanished", "lake_remains", "all"):
        s = np.array([r["p_water"] for r in rows
                      if r["p_water"] is not None and (group == "all" or r["group"] == group)])
        a = auc_vs(rnd, s)
        summary[f"auc_{group}"] = None if a is None else round(a, 3)
        summary[f"n_{group}"] = int(len(s))
        print(f"AUC sites vs random land [{group}] (n={len(s)}): {'-' if a is None else f'{a:.2f}'}")
    with open(os.path.join(gl.OUT, "validation_bucuresti.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
