"""Terrain AI: where water *should* be, given the shape of the land alone.

1. Learn from natural (non-urban) land where water occurs. Labels: JRC Global Surface Water
   (1984-2021). Features: bare-earth elevation (FABDEM), local depressions, slope, height above
   nearest drainage, upstream area, wetness and distance to rivers (MERIT Hydro).
2. Apply it inside cities: built-up pixels with high water probability, away from today's
   rivers and lakes, are "ghost lake" candidates.
3. Leave-one-region-out evaluation, and validation on documented drained lakes (Bucharest).
"""
import json
import os
import time

import ee
import numpy as np
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

from .common import OUT, PROJECT, box, init, jrc, out_path, overpass, save_json

SCALE = 30
SEED = 42
WATER_BUFFER_M = 250
ASSET_DIR = f"projects/{PROJECT}/assets/ghostlakes"

# Training regions (wide, mostly rural) and city areas to scan.
REGIONS = {
    "bucuresti": {"train": [25.70, 44.20, 26.50, 44.70], "city": [25.97, 44.36, 26.24, 44.52]},
    "timisoara": {"train": [20.90, 45.55, 21.55, 45.95], "city": [21.15, 45.71, 21.30, 45.80]},
    "iasi": {"train": [27.20, 46.95, 27.95, 47.35], "city": [27.52, 47.12, 27.66, 47.20]},
    "cluj": {"train": [23.30, 46.60, 23.95, 46.95], "city": [23.53, 46.74, 23.66, 46.80]},
    "galati": {"train": [27.70, 45.25, 28.20, 45.65], "city": [27.97, 45.40, 28.08, 45.47]},
    "craiova": {"train": [23.50, 44.10, 24.10, 44.50], "city": [23.74, 44.28, 23.86, 44.35]},
    "oradea": {"train": [21.60, 46.85, 22.25, 47.25], "city": [21.88, 47.03, 21.98, 47.09]},
}
FEATURES = ["elev", "slope", "rel300", "rel1k", "rel3k", "above_min1k", "hand", "log_upa", "twi", "dist_river"]


# ---------------------------------------------------------------- features and labels

def dem():
    """FABDEM: Copernicus GLO-30 with buildings and forests removed (bare earth)."""
    img = ee.ImageCollection("projects/sat-io/open-datasets/FABDEM").mosaic().rename("elev")
    return img.setDefaultProjection("EPSG:4326", None, SCALE)


def terrain_features():
    elev = dem()
    slope = ee.Terrain.slope(elev).rename("slope")

    def rel(radius, scale, reducer=ee.Reducer.mean()):
        # aggregate first, so big neighbourhoods stay cheap
        base = (elev.reduceResolution(ee.Reducer.mean(), maxPixels=1024).reproject("EPSG:4326", None, scale)
                if scale > SCALE else elev)
        return base.reduceNeighborhood(reducer, ee.Kernel.circle(max(2, round(radius / scale)), "pixels"))

    merit = ee.Image("MERIT/Hydro/v1_0_1")
    upa = merit.select("upa")  # upstream drainage area, km^2
    tan_slope = slope.multiply(np.pi / 180).tan().max(0.001)
    rivers = upa.gt(50).selfMask()  # streams draining > 50 km^2
    return ee.Image.cat([
        elev, slope,
        elev.subtract(rel(300, SCALE)).rename("rel300"),
        elev.subtract(rel(1000, 90)).rename("rel1k"),
        elev.subtract(rel(3000, 300)).rename("rel3k"),
        elev.subtract(rel(1000, 90, ee.Reducer.min())).rename("above_min1k"),
        merit.select("hnd").rename("hand"),
        upa.max(0.001).log10().rename("log_upa"),
        upa.multiply(1e6).divide(90).max(1).log().subtract(tan_slope.log()).rename("twi"),
        rivers.unmask(0).fastDistanceTransform(512).sqrt().multiply(90)
              .reproject("EPSG:4326", None, 90).rename("dist_river"),
    ]).float()


def dynamic_world(geom):
    return (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(geom)
            .filterDate("2024-04-01", "2024-11-01").select(["water", "built", "flooded_vegetation"]).mean())


def labels(geom):
    """1 = water in >= 10% of observations since 1984, 0 = never water; only on land that is
    NOT built-up today, so the model learns natural behaviour."""
    g = jrc()
    occ, ever = g.select("occurrence").unmask(0), g.select("max_extent").unmask(0)
    natural = dynamic_world(geom).select("built").lt(0.2)
    lab = ee.Image(-1).where(occ.gte(10), 1).where(ever.eq(0), 0)
    return lab.updateMask(lab.gte(0).And(natural)).rename("label").toInt()


# ---------------------------------------------------------------- training data (cached)

def upload_table(name, build):
    """Store a table as an Earth Engine asset once; later requests only reference it
    (sending ~20k points inline exceeds the 10 MB request limit)."""
    asset = f"{ASSET_DIR}/{name}"
    try:
        ee.data.getAsset(asset)
        return asset
    except ee.EEException:
        pass
    try:
        ee.data.getAsset(ASSET_DIR)
    except ee.EEException:
        ee.data.createAsset({"type": "FOLDER"}, ASSET_DIR)
    task = ee.batch.Export.table.toAsset(collection=build(), description=name, assetId=asset)
    task.start()
    print(f"    uploading {asset} ...", end="", flush=True)
    while task.status()["state"] in ("READY", "RUNNING"):
        time.sleep(10)
    if task.status()["state"] != "COMPLETED":
        raise RuntimeError(f"Upload failed: {task.status()}")
    print(" ok")
    return asset


def sample(region_name, n_per_class=1500):
    """Stratified sample of features + label, cached as GeoJSON and as an EE asset. A sidecar
    .meta.json records the settings; a cache made with other settings is refused."""
    path = os.path.join(OUT, f"samples_{region_name}.geojson")
    meta_path = path.replace(".geojson", ".meta.json")
    meta = {"n_per_class": n_per_class, "features": FEATURES, "scale": SCALE, "seed": SEED}
    if os.path.exists(path):
        if os.path.exists(meta_path):
            with open(meta_path, encoding="utf-8") as f:
                old = json.load(f)
            if old != meta:
                raise RuntimeError(f"Cached samples for {region_name} were made with {old}, now {meta}. Delete "
                                   f"{path}, {meta_path} and {ASSET_DIR}/samples_{region_name} to resample.")
        else:
            print(f"  note: {region_name} samples were cached before settings were recorded "
                  f"(Bucharest and Timisoara used 2000 points per class)")
    else:
        geom = box(REGIONS[region_name]["train"])
        fc = terrain_features().addBands(labels(geom)).stratifiedSample(
            numPoints=n_per_class, classBand="label", region=geom, scale=SCALE,
            seed=SEED, geometries=True, tileScale=16)
        with open(out_path(f"samples_{region_name}.geojson"), "w", encoding="utf-8") as f:
            json.dump(fc.getInfo(), f)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
    with open(path, encoding="utf-8") as f:
        gj = json.load(f)
    gj["features"] = [ft for ft in gj["features"] if all(ft["properties"].get(k) is not None for k in FEATURES)]
    counts = np.bincount([ft["properties"]["label"] for ft in gj["features"]])
    print(f"  {region_name}: {len(gj['features'])} points (dry={counts[0]}, water={counts[1]})")

    def build():
        return ee.FeatureCollection([
            ee.Feature(ee.Geometry.Point(ft["geometry"]["coordinates"]),
                       {**{k: round(ft["properties"][k], 4) for k in FEATURES}, "label": ft["properties"]["label"]})
            for ft in gj["features"]])
    return ee.FeatureCollection(upload_table(f"samples_{region_name}", build))


def merged(samples, names):
    fc = samples[names[0]]
    for n in names[1:]:
        fc = fc.merge(samples[n])
    return fc


def train(fc):
    return (ee.Classifier.smileRandomForest(numberOfTrees=150, minLeafPopulation=5, seed=SEED)
            .setOutputMode("PROBABILITY").train(features=fc, classProperty="label", inputProperties=FEATURES))


def evaluate(clf, test_fc):
    rows = test_fc.classify(clf, "p").select(["label", "p"], retainGeometry=False).getInfo()["features"]
    y = np.array([r["properties"]["label"] for r in rows])
    p = np.array([r["properties"]["p"] for r in rows])
    yhat = (p >= 0.5).astype(int)
    return {"n": int(len(y)), "auc": round(float(roc_auc_score(y, p)), 3), "f1": round(float(f1_score(y, yhat)), 3),
            "precision": round(float(precision_score(y, yhat)), 3), "recall": round(float(recall_score(y, yhat)), 3)}


# ---------------------------------------------------------------- ghost-lake candidates in cities

def osm_water(city_name):
    """Rivers, canals and water polygons from OpenStreetMap for the city box. Satellite water masks
    miss narrow or concrete-lined channels, which made river banks look like 'ghost lakes'."""
    path = os.path.join(OUT, f"osm_water_{city_name}.geojson")
    if not os.path.exists(path):
        w, s, e, n = REGIONS[city_name]["city"]
        bb = f"{s},{w},{n},{e}"
        data = overpass(f"""[out:json][timeout:120];
(way["waterway"~"^(river|canal|riverbank)$"]({bb}); way["natural"="water"]({bb});
 way["landuse"="reservoir"]({bb}); relation["natural"="water"]({bb}););
out geom;""")
        feats = []
        for el in data["elements"]:
            rings = ([el.get("geometry", [])] if el["type"] == "way"
                     else [m.get("geometry", []) for m in el.get("members", []) if m.get("role") == "outer"])
            for g in rings:
                coords = [[round(p["lon"], 5), round(p["lat"], 5)] for p in g]
                if len(coords) < 2:
                    continue
                closed = len(coords) >= 4 and coords[0] == coords[-1] and "waterway" not in el["tags"]
                feats.append({"type": "Feature",
                              "geometry": ({"type": "Polygon", "coordinates": [coords]} if closed
                                           else {"type": "LineString", "coordinates": coords}),
                              "properties": {"kind": el["tags"].get("waterway") or el["tags"].get("natural")
                                             or el["tags"].get("landuse"), "name": el["tags"].get("name", "")}})
        save_json({"type": "FeatureCollection", "features": feats}, f"osm_water_{city_name}.geojson")
    with open(path, encoding="utf-8") as f:
        gj = json.load(f)
    return ee.FeatureCollection(upload_table(f"osm_water_{city_name}", lambda: ee.FeatureCollection([
        ee.Feature(ee.Geometry(ft["geometry"], None, False), {"kind": ft["properties"]["kind"] or ""})
        for ft in gj["features"]])))


def ghost_layers(clf, city_name):
    geom = box(REGIONS[city_name]["city"])
    p = terrain_features().classify(clf).rename("p_water")
    dw = dynamic_world(geom)
    g = jrc()
    built = dw.select("built")
    water_now = dw.select("water").gt(0.3).Or(g.select("occurrence").unmask(0).gte(50))
    # skip a buffer around today's rivers/lakes: their banks are obviously wet, not a discovery
    near_water = water_now.focalMax(WATER_BUFFER_M, "circle", "meters").Or(
        osm_water(city_name).distance(WATER_BUFFER_M + 50).lte(WATER_BUFFER_M).unmask(0))
    score = p.updateMask(built.gt(0.4).And(near_water.Not())).rename("ghost")
    lost = (g.select("max_extent").unmask(0).eq(1).And(built.gt(0.5)).And(water_now.Not())
            .rename("lost_since_1984"))
    return p.clip(geom), score.clip(geom), lost.selfMask().clip(geom)


def candidates(score, city_name, threshold=0.7, min_ha=2, top=15):
    geom = box(REGIONS[city_name]["city"])
    mask = score.gte(threshold)
    mask = mask.updateMask(mask.connectedPixelCount(200, True).gte(int(min_ha * 1e4 / SCALE ** 2)))
    vecs = mask.selfMask().addBands(score).reduceToVectors(
        geometry=geom, scale=SCALE, geometryType="polygon", eightConnected=True, reducer=ee.Reducer.mean(),
        labelProperty="zone", maxPixels=1e10, tileScale=4)
    stats = terrain_features().select(["hand", "rel1k", "elev"]).addBands(
        jrc().select("max_extent").unmask(0).rename("seen_water_1984"))
    vecs = stats.reduceRegions(collection=vecs, reducer=ee.Reducer.mean(), scale=SCALE, tileScale=4)

    def enrich(f):
        area = f.geometry().area(1).divide(1e4)
        c = f.geometry().centroid(1).coordinates()
        return f.set({"area_ha": area, "lon": c.get(0), "lat": c.get(1), "rank_score": area.sqrt().multiply(f.get("mean"))})
    return vecs.map(enrich).filter(ee.Filter.gte("area_ha", min_ha)).sort("rank_score", False).limit(top)


def make_map(layers, cands, path):
    import folium
    m = folium.Map(location=[44.435, 26.10], zoom_start=12, tiles=None)
    folium.TileLayer("cartodbpositron", name="Map").add_to(m)
    folium.TileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                     attr="Esri", name="Satellite").add_to(m)
    for name, (url, show) in layers.items():
        folium.TileLayer(url, attr="Google Earth Engine", name=name, overlay=True, show=show).add_to(m)
    for city, gj in cands.items():
        fg = folium.FeatureGroup(name=f"Candidates {city}")
        for i, f in enumerate(gj["features"], 1):
            pr = f["properties"]
            folium.GeoJson(f, style_function=lambda _: {"color": "#ff2d55", "weight": 2, "fillOpacity": 0.1}).add_to(fg)
            folium.Marker([pr["lat"], pr["lon"]], tooltip=f"#{i} {city}", popup=folium.Popup(
                f"<b>#{i} {city}</b><br>{pr['area_ha']:.1f} ha<br>ghost score {pr['mean']:.2f}<br>"
                f"HAND {pr.get('hand') or 0:.1f} m<br>seen as water since 1984: {100 * (pr.get('seen_water_1984') or 0):.0f}%",
                max_width=260)).add_to(fg)
        fg.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(path)


def run():
    """Train, evaluate leave-one-region-out, scan the 7 cities, write metrics/candidates/map."""
    init()
    print("Sampling training points...")
    names = list(REGIONS)
    samples = {r: sample(r) for r in names}
    metrics = {"leave_one_region_out": {}}
    for held in names:
        m = evaluate(train(merged(samples, [n for n in names if n != held])), samples[held])
        metrics["leave_one_region_out"][held] = m
        print(f"  test on {held:10s} {m}")
    vals = metrics["leave_one_region_out"].values()
    metrics["mean_auc"] = round(float(np.mean([v["auc"] for v in vals])), 3)
    metrics["mean_f1"] = round(float(np.mean([v["f1"] for v in vals])), 3)
    clf = train(merged(samples, names))
    imp = ee.Dictionary(ee.Dictionary(clf.explain()).get("importance")).getInfo()
    metrics["feature_importance"] = {k: round(v / sum(imp.values()), 3) for k, v in sorted(imp.items(), key=lambda kv: -kv[1])}
    print("Mean AUC", metrics["mean_auc"], "mean F1", metrics["mean_f1"])

    tile = lambda img, vis: img.getMapId(vis)["tile_fetcher"].url_format  # noqa: E731
    layers, cands = {}, {}
    for city in REGIONS:
        print(f"Scanning {city}...")
        p, score, lost = ghost_layers(clf, city)
        layers[f"P(water) from terrain — {city}"] = (tile(p, {"min": 0, "max": 1, "palette": ["ffffff00", "9ecae1", "3182bd", "08306b"]}), False)
        layers[f"Ghost-lake score — {city}"] = (tile(score.updateMask(score.gt(0.5)), {"min": 0.5, "max": 0.95, "palette": ["fee08b", "fc8d59", "d73027"]}), True)
        layers[f"Water since 1984, built now — {city}"] = (tile(lost, {"palette": ["00e5ff"]}), False)
        cands[city] = candidates(score, city).getInfo()
        save_json(cands[city], f"candidates_{city}.geojson")
    save_json(metrics, "metrics.json", indent=2)
    with open(out_path("candidates.csv"), "w", encoding="utf-8") as f:
        f.write("city,rank,lat,lon,area_ha,ghost_score,hand_m,seen_water_since_1984_pct\n")
        for city, gj in cands.items():
            for i, ft in enumerate(gj["features"], 1):
                pr = ft["properties"]
                f.write(f"{city},{i},{pr['lat']:.5f},{pr['lon']:.5f},{pr['area_ha']:.1f},{pr['mean']:.3f},"
                        f"{pr.get('hand') or 0:.2f},{100 * (pr.get('seen_water_1984') or 0):.0f}\n")
    make_map(layers, cands, out_path("map.html"))
    print("Done ->", OUT)


# ---------------------------------------------------------------- validation on documented drained lakes

# Approximate centres of documented former water bodies in Bucharest (from today's landmark).
SITES = [
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


def auc_vs(baseline, scores):
    """Probability that a site scores higher than a random baseline pixel (ties count half)."""
    if len(scores) == 0:
        return None
    return float(np.mean([(baseline < s).mean() + 0.5 * (baseline == s).mean() for s in scores]))


def validate(test_city="bucuresti", n_random=1500):
    """Leave-the-city-out: train on the other regions, then compare documented former water bodies
    with random land pixels of the city. 'vanished' sites left nothing; 'lake_remains' still have a park lake."""
    init()
    train_regions = [n for n in REGIONS if n != test_city]
    clf = train(merged({n: sample(n) for n in train_regions}, train_regions))
    city = box(REGIONS[test_city]["city"])
    p = terrain_features().classify(clf).reduceNeighborhood(ee.Reducer.mean(), ee.Kernel.circle(150, "meters")).rename("p")
    land = jrc().select("occurrence").unmask(0).lt(50).And(dynamic_world(city).select("water").lt(0.3))
    rnd = np.array(p.updateMask(land).sample(region=city, scale=SCALE, numPixels=n_random * 3, seed=1, geometries=False)
                   .limit(n_random).aggregate_array("p").getInfo())
    pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([lon, lat]), {"i": i}) for i, (_, lat, lon, _, _) in enumerate(SITES)])
    vals = {f["properties"]["i"]: f["properties"].get("first")
            for f in p.reduceRegions(pts, ee.Reducer.first(), SCALE).getInfo()["features"]}
    rows = []
    for i, (n, lat, lon, note, group) in enumerate(SITES):
        pv = vals.get(i)
        rows.append({"site": n, "lat": lat, "lon": lon, "note": note, "group": group, "p_water": pv,
                     "percentile": None if pv is None else float((rnd < pv).mean() * 100)})
        print(f"  [{group:12s}] {n:42s} " + ("no value" if pv is None else f"p={pv:.2f} -> top {100 - rows[-1]['percentile']:.0f}%"))
    summary = {"city": test_city, "trained_on": train_regions, "random_land_median_p": float(np.median(rnd)),
               "sites": rows, "sources": SOURCES}
    for group in ("vanished", "lake_remains", "all"):
        s = np.array([r["p_water"] for r in rows if r["p_water"] is not None and group in ("all", r["group"])])
        a = auc_vs(rnd, s)
        summary[f"auc_{group}"], summary[f"n_{group}"] = (None if a is None else round(a, 3)), int(len(s))
        print(f"AUC sites vs random land [{group}] (n={len(s)}): {'-' if a is None else f'{a:.2f}'}")
    save_json(summary, f"validation_{test_city}.json", indent=2)
