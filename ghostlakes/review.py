"""Manual review tools: old-vs-new image chips, yearly water history, and OpenStreetMap checks.

Sites CSV files have columns id,lat,lon[,radius_m].
  history_chips  Landsat 5 (1984-1996) vs Sentinel-2 (2023-24) chips + JRC water history per year
  recent_chips   Sentinel-2 H1 2023 vs Apr-Nov 2026 sheet (for 2023->2026 infill)
  montage        put <id>_old / <id>_new chips side by side
  osm            is the site already mapped as water in OSM? neighbourhood name?
"""
import csv
import json
import os
import urllib.request

import ee
from PIL import Image, ImageDraw

from .common import init, overpass, reverse_geocode, s2_rgb


def read_sites(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def landsat_old(geom, start="1984-01-01", end="1996-12-31"):
    col = (ee.ImageCollection("LANDSAT/LT05/C02/T1_L2").filterBounds(geom).filterDate(start, end)
           .filter(ee.Filter.lt("CLOUD_COVER", 20)))
    return col.median().select(["SR_B3", "SR_B2", "SR_B1"]).multiply(0.0000275).add(-0.2)


def water_history(pt, radius):
    """Fraction of the whole circle that was water each year (JRC yearly history: 2 seasonal, 3 permanent).
    Masked pixels (never water) count as dry; a year is None when nothing in the circle was observed."""
    reg = pt.buffer(radius)

    def per_year(img):
        cls = img.select(0)
        st = (cls.gte(2).unmask(0).rename("water").addBands(cls.gte(1).unmask(0).rename("valid"))
              .addBands(cls.eq(0).unmask(0).rename("nodata")).reduceRegion(ee.Reducer.mean(), reg, 30))
        return ee.Feature(None, {"year": img.get("year"), "water": st.get("water"),
                                 "valid": st.get("valid"), "nodata": st.get("nodata")})
    out = {}
    for f in ee.FeatureCollection(ee.ImageCollection("JRC/GSW1_4/YearlyHistory").map(per_year)).getInfo()["features"]:
        p = f["properties"]
        out[p["year"]] = None if (p.get("valid") or 0) == 0 and (p.get("nodata") or 0) > 0 else p.get("water")
    return out


def history_chips(csv_path, out_dir):
    init()
    os.makedirs(out_dir, exist_ok=True)
    report = {}
    for s in read_sites(csv_path):
        lat, lon, r = float(s["lat"]), float(s["lon"]), float(s.get("radius_m") or 120)
        pt = ee.Geometry.Point([lon, lat])
        region = pt.buffer(1200).bounds()
        mark = ee.Image().paint(ee.FeatureCollection([ee.Feature(pt.buffer(r))]), 1, 2).visualize(palette=["ff0000"])
        for kind, img in (("old", landsat_old(pt).visualize(min=0, max=0.25)),
                          ("new", s2_rgb(pt, "2023-04-01", "2024-10-31", max_cloud=10, vmax=0.25))):
            try:
                url = img.blend(mark).getThumbURL({"region": region, "dimensions": 384, "format": "png"})
                urllib.request.urlretrieve(url, os.path.join(out_dir, f"{s['id']}_{kind}.png"))
            except Exception as e:
                print(s["id"], kind, "failed:", e)
        hist = water_history(pt, r)
        report[s["id"]] = {"lat": lat, "lon": lon, "water_by_year": hist}
        yrs = sorted(hist)
        print(f"{s['id']:24s} {yrs[0]}..{yrs[-1]} " + "".join(
            "?" if hist[y] is None else ("#" if hist[y] > 0.3 else ("+" if hist[y] > 0.05 else ".")) for y in yrs))
    with open(os.path.join(out_dir, "history.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)


def recent_chips(csv_path, out_png, half_m=600, size=300):
    init()
    sites = read_sites(csv_path)
    sheet = Image.new("RGB", (2 * size + 10, len(sites) * (size + 18)), "white")
    d = ImageDraw.Draw(sheet)
    for r, s in enumerate(sites):
        pt = ee.Geometry.Point([float(s["lon"]), float(s["lat"])])
        reg = pt.buffer(float(half_m)).bounds()
        mark = ee.Image().paint(ee.FeatureCollection([ee.Feature(pt.buffer(60))]), 1, 2).visualize(palette=["ff0000"])
        for c, (a, b, lab) in enumerate([("2023-01-01", "2023-07-01", "2023 H1"), ("2026-04-01", "2026-11-15", "2026")]):
            url = s2_rgb(pt, a, b, vmax=0.22).blend(mark).getThumbURL({"region": reg, "dimensions": size, "format": "png"})
            im = Image.open(urllib.request.urlopen(url)).convert("RGB").resize((size, size))
            sheet.paste(im, (c * (size + 10), r * (size + 18) + 18))
            d.text((c * (size + 10) + 3, r * (size + 18) + 3), f"{s['id']}  {lab}", fill="black")
    sheet.save(out_png)


def montage(chips_dir, out_png, ids=None, size=256, pad=18, per_row=2):
    ids = ids or sorted({f.rsplit("_", 1)[0] for f in os.listdir(chips_dir) if f.endswith("_new.png")})
    rows = (len(ids) + per_row - 1) // per_row
    sheet = Image.new("RGB", (per_row * (2 * size + 10), rows * (size + pad)), "white")
    d = ImageDraw.Draw(sheet)
    for i, sid in enumerate(ids):
        r, c = divmod(i, per_row)
        x0, y0 = c * (2 * size + 10), r * (size + pad)
        d.text((x0 + 2, y0 + 2), f"{sid}  (old Landsat | new Sentinel-2)", fill="black")
        for j, kind in enumerate(["old", "new"]):
            p = os.path.join(chips_dir, f"{sid}_{kind}.png")
            if os.path.exists(p):
                sheet.paste(Image.open(p).convert("RGB").resize((size, size)), (x0 + j * size, y0 + pad))
    sheet.save(out_png)


# Whole words only (Overpass regex is POSIX ERE, no \b): otherwise 'lac' matches 'Palace', 'dam' matches 'Adam'.
WATER_WORDS = ["lake", "lakes", "tank", "pond", "lac", "lacul", "cheruvu", "kunta", "kere", "eri", "kulam", "talab",
               "sagar", "bil", "beel", "haor", "barrage", "mare", "dam", "reservoir", "lagoon", "lagune", "étang",
               "etang", "baie", "bay", "marsh", "swamp", "balta"]
NAME_RE = "(^|[^[:alpha:]])(" + "|".join(WATER_WORDS) + ")([^[:alpha:]]|$)"


def osm(csv_path, out_json, r=250):
    res = {}
    for s in read_sites(csv_path):
        lat, lon = float(s["lat"]), float(s["lon"])
        try:
            els = overpass(f"""[out:json][timeout:60];
(nwr(around:{r},{lat},{lon})["natural"~"water|wetland"]; nwr(around:{r},{lat},{lon})["water"];
 nwr(around:{r},{lat},{lon})["landuse"="reservoir"]; nwr(around:{r},{lat},{lon})["name"~"{NAME_RE}",i];
 nwr(around:{r},{lat},{lon})["historic"];);
out tags center;""")["elements"]
            feats = [{k: e["tags"][k] for k in ("name", "name:en", "natural", "water", "landuse", "historic")
                      if e["tags"].get(k)} for e in els]
            res[s["id"]] = {"osm_features": feats, "place": reverse_geocode(lat, lon).get("display_name")}
        except Exception as e:
            res[s["id"]] = {"error": str(e)}
        rr = res[s["id"]]
        print(s["id"], "|", (rr.get("place") or "")[:90], "|",
              [x.get("name") or x.get("natural") or x.get("water") for x in rr.get("osm_features", [])][:6])
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
