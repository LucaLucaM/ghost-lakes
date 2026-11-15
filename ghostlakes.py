"""Ghost Lakes — find places where the terrain "wants" to hold water but a city sits there today.

Idea
----
1. Learn, from natural (non-urban) land only, where water occurs given terrain shape alone.
   Labels: JRC Global Surface Water (1984-2021). Features: bare-earth elevation (FABDEM),
   local depressions, slope, height above nearest drainage, upstream area, distance to rivers.
2. Apply the model inside cities. Pixels with high predicted water probability that are
   built-up today (Dynamic World) are "ghost lake" candidates.
3. Group pixels into areas, rank them, and export them for validation (old maps, flood maps).

Run:  python ghostlakes.py
"""
import json
import os

import ee
import numpy as np
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score

PROJECT = "lootlake"
SCALE = 30
SEED = 42
WATER_BUFFER_M = 250
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

# Training regions (wide, mostly rural) and city areas to scan.
REGIONS = {
    "bucuresti": {
        "train": [25.70, 44.20, 26.50, 44.70],
        "city": [25.97, 44.36, 26.24, 44.52],
    },
    "timisoara": {
        "train": [20.90, 45.55, 21.55, 45.95],
        "city": [21.15, 45.71, 21.30, 45.80],
    },
    "iasi": {
        "train": [27.20, 46.95, 27.95, 47.35],
        "city": [27.52, 47.12, 27.66, 47.20],
    },
    "cluj": {
        "train": [23.30, 46.60, 23.95, 46.95],
        "city": [23.53, 46.74, 23.66, 46.80],
    },
    "galati": {
        "train": [27.70, 45.25, 28.20, 45.65],
        "city": [27.97, 45.40, 28.08, 45.47],
    },
    "craiova": {
        "train": [23.50, 44.10, 24.10, 44.50],
        "city": [23.74, 44.28, 23.86, 44.35],
    },
    "oradea": {
        "train": [21.60, 46.85, 22.25, 47.25],
        "city": [21.88, 47.03, 21.98, 47.09],
    },
}

FEATURES = ["elev", "slope", "rel300", "rel1k", "rel3k", "above_min1k",
            "hand", "log_upa", "twi", "dist_river"]


def init():
    ee.Initialize(project=PROJECT)


def box(b):
    return ee.Geometry.Rectangle(b)


# ---------------------------------------------------------------- data layers

def dem():
    """FABDEM: Copernicus GLO-30 with buildings and forests removed (bare earth).
    Important in cities, where the plain Copernicus DSM would show rooftops."""
    img = ee.ImageCollection("projects/sat-io/open-datasets/FABDEM").mosaic().rename("elev")
    return img.setDefaultProjection("EPSG:4326", None, SCALE)


def terrain_features():
    elev = dem()
    slope = ee.Terrain.slope(elev).rename("slope")

    def coarse(scale):
        # Aggregate the DEM to a coarser grid first so big neighbourhoods stay cheap.
        return (elev.reduceResolution(ee.Reducer.mean(), maxPixels=1024)
                .reproject("EPSG:4326", None, scale))

    def rel(radius, scale, reducer=ee.Reducer.mean()):
        base = coarse(scale) if scale > SCALE else elev
        px = max(2, round(radius / scale))
        return base.reduceNeighborhood(reducer, ee.Kernel.circle(px, "pixels"))

    rel300 = elev.subtract(rel(300, SCALE)).rename("rel300")
    rel1k = elev.subtract(rel(1000, 90)).rename("rel1k")
    rel3k = elev.subtract(rel(3000, 300)).rename("rel3k")
    above_min = elev.subtract(rel(1000, 90, ee.Reducer.min())).rename("above_min1k")

    merit = ee.Image("MERIT/Hydro/v1_0_1")
    hand = merit.select("hnd").rename("hand")
    upa = merit.select("upa")  # upstream drainage area, km^2
    log_upa = upa.max(0.001).log10().rename("log_upa")
    tan_slope = slope.multiply(np.pi / 180).tan().max(0.001)
    twi = upa.multiply(1e6).divide(90).max(1).log().subtract(tan_slope.log()).rename("twi")

    rivers = upa.gt(50).selfMask()  # streams draining > 50 km^2
    dist = (rivers.unmask(0).fastDistanceTransform(512).sqrt()
            .multiply(90).reproject("EPSG:4326", None, 90).rename("dist_river"))

    return ee.Image.cat([elev, slope, rel300, rel1k, rel3k, above_min,
                         hand, log_upa, twi, dist]).float()


def jrc():
    return ee.Image("JRC/GSW1_4/GlobalSurfaceWater")


def dynamic_world(geom):
    dw = (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
          .filterBounds(geom).filterDate("2024-04-01", "2024-11-01"))
    return dw.select(["water", "built", "flooded_vegetation"]).mean()


def labels(geom):
    """1 = water seen often (>=10% of observations since 1984), 0 = never water.
    Only on land that is NOT built-up today, so the model learns natural behaviour."""
    g = jrc()
    occ = g.select("occurrence").unmask(0)
    ever = g.select("max_extent").unmask(0)
    built = dynamic_world(geom).select("built")
    natural = built.lt(0.2)
    lab = ee.Image(-1).where(occ.gte(10), 1).where(ever.eq(0), 0)
    return lab.updateMask(lab.gte(0).And(natural)).rename("label").toInt()


# ---------------------------------------------------------------- training

def sample(region_name, n_per_class=1500):
    """Stratified sample of features+label; cached locally as GeoJSON so it runs once."""
    path = os.path.join(OUT, f"samples_{region_name}.geojson")
    if not os.path.exists(path):
        geom = box(REGIONS[region_name]["train"])
        img = terrain_features().addBands(labels(geom))
        fc = img.stratifiedSample(
            numPoints=n_per_class, classBand="label", region=geom, scale=SCALE,
            seed=SEED, geometries=True, tileScale=16)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(fc.getInfo(), f)
    with open(path, encoding="utf-8") as f:
        gj = json.load(f)
    gj["features"] = [ft for ft in gj["features"]
                      if all(ft["properties"].get(k) is not None for k in FEATURES)]
    counts = np.bincount([ft["properties"]["label"] for ft in gj["features"]])
    print(f"  {region_name}: {len(gj['features'])} points (dry={counts[0]}, water={counts[1]})")
    return ee.FeatureCollection(upload_samples(region_name, gj))


ASSET_DIR = f"projects/{PROJECT}/assets/ghostlakes"


def upload_samples(region_name, gj):
    """Store samples as an Earth Engine table asset once, so later requests only reference
    them (sending ~20k points inline exceeds the 10 MB request limit)."""
    def build():
        return ee.FeatureCollection([
            ee.Feature(ee.Geometry.Point(ft["geometry"]["coordinates"]),
                       {**{k: round(ft["properties"][k], 4) for k in FEATURES}, "label": ft["properties"]["label"]})
            for ft in gj["features"]])
    return upload_table(f"samples_{region_name}", build)


def upload_table(name, build):
    import time
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
    fc = build()
    task = ee.batch.Export.table.toAsset(collection=fc, description=name, assetId=asset)
    task.start()
    print(f"    uploading {asset} ...", end="", flush=True)
    while task.status()["state"] in ("READY", "RUNNING"):
        time.sleep(10)
    st = task.status()
    if st["state"] != "COMPLETED":
        raise RuntimeError(f"Upload failed: {st}")
    print(" ok")
    return asset


def train(fc):
    return (ee.Classifier.smileRandomForest(numberOfTrees=150, minLeafPopulation=5, seed=SEED)
            .setOutputMode("PROBABILITY")
            .train(features=fc, classProperty="label", inputProperties=FEATURES))


def evaluate(clf, test_fc):
    rows = test_fc.classify(clf, "p").select(["label", "p"], retainGeometry=False).getInfo()["features"]
    y = np.array([r["properties"]["label"] for r in rows])
    p = np.array([r["properties"]["p"] for r in rows])
    yhat = (p >= 0.5).astype(int)
    return {
        "n": int(len(y)),
        "auc": round(float(roc_auc_score(y, p)), 3),
        "f1": round(float(f1_score(y, yhat)), 3),
        "precision": round(float(precision_score(y, yhat)), 3),
        "recall": round(float(recall_score(y, yhat)), 3),
    }


# ---------------------------------------------------------------- visible water (OSM)

def osm_water(city_name):
    """Rivers, canals and water polygons from OpenStreetMap for the city box.
    Satellite water masks miss narrow or concrete-lined channels (e.g. Dâmbovița, Bega),
    which made river banks show up as false 'ghost lakes'."""
    import urllib.parse
    import urllib.request

    path = os.path.join(OUT, f"osm_water_{city_name}.geojson")
    if not os.path.exists(path):
        w, s, e, n = REGIONS[city_name]["city"]
        bb = f"{s},{w},{n},{e}"
        q = f"""[out:json][timeout:120];
(way["waterway"~"^(river|canal|riverbank)$"]({bb});
 way["natural"="water"]({bb});
 way["landuse"="reservoir"]({bb});
 relation["natural"="water"]({bb}););
out geom;"""
        import time
        data, err = None, None
        for attempt in range(3):
            for url in ["https://overpass-api.de/api/interpreter",
                        "https://overpass.kumi.systems/api/interpreter",
                        "https://overpass.private.coffee/api/interpreter"]:
                try:
                    req = urllib.request.Request(
                        url, data=urllib.parse.urlencode({"data": q}).encode(),
                        headers={"User-Agent": "ghostlakes-hackathon/0.1"})
                    data = json.load(urllib.request.urlopen(req, timeout=180))
                    break
                except Exception as e:  # busy server -> try next mirror
                    err = e
            if data:
                break
            time.sleep(20)
        if data is None:
            raise RuntimeError(f"Overpass failed: {err}")
        feats = []
        for el in data["elements"]:
            if el["type"] == "way":
                rings = [el.get("geometry", [])]
            else:  # relation: use outer member ways as lines (enough for a distance mask)
                rings = [m.get("geometry", []) for m in el.get("members", []) if m.get("role") == "outer"]
            for g in rings:
                coords = [[round(p["lon"], 5), round(p["lat"], 5)] for p in g]
                if len(coords) < 2:
                    continue
                closed = len(coords) >= 4 and coords[0] == coords[-1] and "waterway" not in el["tags"]
                geom = ({"type": "Polygon", "coordinates": [coords]} if closed
                        else {"type": "LineString", "coordinates": coords})
                feats.append({"type": "Feature", "geometry": geom,
                              "properties": {"kind": el["tags"].get("waterway") or el["tags"].get("natural")
                                             or el["tags"].get("landuse"), "name": el["tags"].get("name", "")}})
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": feats}, f, ensure_ascii=False)
    with open(path, encoding="utf-8") as f:
        gj = json.load(f)

    def build():
        return ee.FeatureCollection([
            ee.Feature(ee.Geometry(ft["geometry"], None, False), {"kind": ft["properties"]["kind"] or ""})
            for ft in gj["features"]])
    return ee.FeatureCollection(upload_table(f"osm_water_{city_name}", build))


# ---------------------------------------------------------------- ghost lakes

def ghost_layers(clf, city_name):
    geom = box(REGIONS[city_name]["city"])
    feats = terrain_features()
    p = feats.classify(clf).rename("p_water")
    dw = dynamic_world(geom)
    g = jrc()
    occ = g.select("occurrence").unmask(0)
    built = dw.select("built")
    water_now = dw.select("water").gt(0.3).Or(occ.gte(50))
    # Ghost score = how strongly the terrain says "water", on land that is built-up today.
    # Skip a buffer around today's rivers/lakes: their banks are obviously wet, not a discovery.
    near_sat = water_now.focalMax(WATER_BUFFER_M, "circle", "meters")
    near_osm = osm_water(city_name).distance(WATER_BUFFER_M + 50).lte(WATER_BUFFER_M).unmask(0)
    near_water = near_sat.Or(near_osm)
    score = p.updateMask(built.gt(0.4).And(near_water.Not())).rename("ghost")
    # Direct evidence: seen as water since 1984 but built-up today.
    lost = g.select("max_extent").unmask(0).eq(1).And(built.gt(0.5)).And(water_now.Not()).rename("lost_since_1984")
    return p.clip(geom), score.clip(geom), lost.selfMask().clip(geom), built.clip(geom)


def candidates(score, feats, city_name, threshold=0.7, min_ha=2, top=15):
    geom = box(REGIONS[city_name]["city"])
    mask = score.gte(threshold)
    mask = mask.updateMask(mask.connectedPixelCount(200, True).gte(int(min_ha * 1e4 / SCALE ** 2)))
    vecs = (mask.selfMask().addBands(score)
            .reduceToVectors(geometry=geom, scale=SCALE, geometryType="polygon",
                             eightConnected=True, reducer=ee.Reducer.mean(),
                             labelProperty="zone", maxPixels=1e10, tileScale=4))
    stats_img = feats.select(["hand", "rel1k", "elev"]).addBands(
        jrc().select("max_extent").unmask(0).rename("seen_water_1984"))
    vecs = stats_img.reduceRegions(collection=vecs, reducer=ee.Reducer.mean(), scale=SCALE, tileScale=4)

    def enrich(f):
        area = f.geometry().area(1).divide(1e4)
        c = f.geometry().centroid(1).coordinates()
        return f.set({"area_ha": area, "lon": c.get(0), "lat": c.get(1),
                      "rank_score": area.sqrt().multiply(f.get("mean"))})

    vecs = vecs.map(enrich).filter(ee.Filter.gte("area_ha", min_ha))
    return vecs.sort("rank_score", False).limit(top)


# ---------------------------------------------------------------- outputs

def tile_url(img, vis):
    return img.getMapId(vis)["tile_fetcher"].url_format


def make_map(layers, cands_geojson, path):
    import folium
    m = folium.Map(location=[44.435, 26.10], zoom_start=12, tiles=None)
    folium.TileLayer("cartodbpositron", name="Hartă").add_to(m)
    folium.TileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri", name="Satelit").add_to(m)
    for name, (url, show) in layers.items():
        folium.TileLayer(url, attr="Google Earth Engine", name=name, overlay=True, show=show).add_to(m)
    for city, gj in cands_geojson.items():
        fg = folium.FeatureGroup(name=f"Candidați {city}")
        for i, f in enumerate(gj["features"], 1):
            pr = f["properties"]
            folium.GeoJson(f, style_function=lambda _: {"color": "#ff2d55", "weight": 2, "fillOpacity": 0.1}).add_to(fg)
            folium.Marker(
                [pr["lat"], pr["lon"]],
                tooltip=f"#{i} {city}",
                popup=folium.Popup(
                    f"<b>#{i} {city}</b><br>suprafață: {pr['area_ha']:.1f} ha<br>"
                    f"scor ghost: {pr['mean']:.2f}<br>HAND: {pr['hand']:.1f} m<br>"
                    f"văzut apă din 1984: {100*pr['seen_water_1984']:.0f}% din zonă", max_width=260),
                icon=folium.DivIcon(html=f"<div style='background:#ff2d55;color:#fff;border-radius:50%;"
                                         f"width:22px;height:22px;text-align:center;font:bold 12px/22px sans-serif'>{i}</div>"),
            ).add_to(fg)
        fg.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(path)


def main():
    init()
    os.makedirs(OUT, exist_ok=True)

    print("Sampling training points...")
    samples = {r: sample(r) for r in REGIONS}

    # Leave-one-region-out: train on all other regions, test on the held-out one.
    metrics = {"leave_one_region_out": {}}
    names = list(REGIONS)

    def merged(keys):
        fc = samples[keys[0]]
        for k in keys[1:]:
            fc = fc.merge(samples[k])
        return fc

    for held in names:
        m = evaluate(train(merged([n for n in names if n != held])), samples[held])
        metrics["leave_one_region_out"][held] = m
        print(f"  test on {held:10s} {m}")
    vals = metrics["leave_one_region_out"].values()
    metrics["mean_auc"] = round(float(np.mean([v["auc"] for v in vals])), 3)
    metrics["mean_f1"] = round(float(np.mean([v["f1"] for v in vals])), 3)
    print("Mean AUC", metrics["mean_auc"], "mean F1", metrics["mean_f1"])

    clf = train(merged(names))
    imp = ee.Dictionary(ee.Dictionary(clf.explain()).get("importance")).getInfo()
    tot = sum(imp.values())
    metrics["feature_importance"] = {k: round(v / tot, 3) for k, v in sorted(imp.items(), key=lambda kv: -kv[1])}
    print("Feature importance:", metrics["feature_importance"])

    feats = terrain_features()
    layers, cands_gj = {}, {}
    for city in REGIONS:
        print(f"Scanning {city}...")
        p, score, lost, built = ghost_layers(clf, city)
        layers[f"P(apă) după teren — {city}"] = (tile_url(p, {"min": 0, "max": 1, "palette": ["ffffff00", "9ecae1", "3182bd", "08306b"]}), False)
        layers[f"Scor ghost lake — {city}"] = (tile_url(score.updateMask(score.gt(0.5)), {"min": 0.5, "max": 0.95, "palette": ["fee08b", "fc8d59", "d73027"]}), True)
        layers[f"Apă 1984+ acum construit — {city}"] = (tile_url(lost, {"palette": ["00e5ff"]}), False)
        layers[f"Ape vizibile (OSM) — {city}"] = (tile_url(
            osm_water(city).style(color="0077ff", width=2, fillColor="0077ff40"), {}), False)
        gj = candidates(score, feats, city).getInfo()
        cands_gj[city] = gj
        with open(os.path.join(OUT, f"candidates_{city}.geojson"), "w", encoding="utf-8") as f:
            json.dump(gj, f)
        for i, ft in enumerate(gj["features"], 1):
            pr = ft["properties"]
            print(f"  #{i:2d} {pr['lat']:.4f},{pr['lon']:.4f}  {pr['area_ha']:6.1f} ha  "
                  f"score {pr['mean']:.2f}  hand {pr['hand']:.1f}m  seen84 {100*pr['seen_water_1984']:.0f}%")

    with open(os.path.join(OUT, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    with open(os.path.join(OUT, "candidates.csv"), "w", encoding="utf-8") as f:
        f.write("city,rank,lat,lon,area_ha,ghost_score,hand_m,seen_water_since_1984_pct\n")
        for city, gj in cands_gj.items():
            for i, ft in enumerate(gj["features"], 1):
                pr = ft["properties"]
                f.write(f"{city},{i},{pr['lat']:.5f},{pr['lon']:.5f},{pr['area_ha']:.1f},"
                        f"{pr['mean']:.3f},{pr['hand']:.2f},{100*pr['seen_water_1984']:.0f}\n")
    make_map(layers, cands_gj, os.path.join(OUT, "map.html"))
    print("Done ->", OUT)


if __name__ == "__main__":
    main()
