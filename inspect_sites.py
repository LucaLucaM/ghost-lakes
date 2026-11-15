"""Make before/after image chips for a list of sites so they can be checked by eye.

For each site: Landsat 5 true-colour (old, ~1985-1995), Sentinel-2 true-colour (2023-2024),
and the JRC yearly water history (1984-2021) as a small time series.

Usage:  python inspect_sites.py sites.csv out_dir
sites.csv columns: id,lat,lon[,radius_m]
"""
import csv
import json
import os
import sys
import urllib.request

import ee

import ghostlakes as gl


def landsat_old(geom, start="1984-01-01", end="1996-12-31"):
    col = (ee.ImageCollection("LANDSAT/LT05/C02/T1_L2").filterBounds(geom)
           .filterDate(start, end).filter(ee.Filter.lt("CLOUD_COVER", 20)))
    img = col.median()
    return img.select(["SR_B3", "SR_B2", "SR_B1"]).multiply(0.0000275).add(-0.2)


def s2_new(geom):
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(geom)
           .filterDate("2023-04-01", "2024-10-31").filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 10)))
    return col.median().select(["B4", "B3", "B2"]).divide(10000)


def water_history(pt, radius):
    """Fraction of the whole site circle that was water in each year (JRC yearly history,
    classes 2 = seasonal, 3 = permanent). YearlyHistory masks pixels that were never water and
    uses 0 for 'no observation', so:
      - the fraction is water pixels / ALL pixels in the circle (masked pixels count as dry),
      - a year is None (no data) when no pixel in the circle has a valid observation (class >= 1)
        while some pixel does have class 0."""
    yh = ee.ImageCollection("JRC/GSW1_4/YearlyHistory")
    reg = pt.buffer(radius)

    def per_year(img):
        cls = img.select(0)
        water = cls.gte(2).unmask(0).rename("water")
        valid = cls.gte(1).unmask(0).rename("valid")
        nodata = cls.eq(0).unmask(0).rename("nodata")
        st = water.addBands(valid).addBands(nodata).reduceRegion(ee.Reducer.mean(), reg, 30)
        return ee.Feature(None, {"year": img.get("year"), "water": st.get("water"),
                                 "valid": st.get("valid"), "nodata": st.get("nodata")})
    out = {}
    for f in ee.FeatureCollection(yh.map(per_year)).getInfo()["features"]:
        p = f["properties"]
        no_obs = (p.get("valid") or 0) == 0 and (p.get("nodata") or 0) > 0
        out[p["year"]] = None if no_obs else p.get("water")
    return out


def chip(img, region, vis, path):
    url = img.getThumbURL({**vis, "region": region, "dimensions": 384, "format": "png"})
    urllib.request.urlretrieve(url, path)


def main(csv_path, out_dir):
    gl.init()
    os.makedirs(out_dir, exist_ok=True)
    report = {}
    with open(csv_path, encoding="utf-8") as f:
        sites = list(csv.DictReader(f))
    for s in sites:
        lat, lon = float(s["lat"]), float(s["lon"])
        r = float(s.get("radius_m") or 120)
        pt = ee.Geometry.Point([lon, lat])
        region = pt.buffer(1200).bounds()
        mark = ee.Image().paint(ee.FeatureCollection([ee.Feature(pt.buffer(r))]), 1, 2)
        markv = mark.visualize(palette=["ff0000"])
        try:
            old = landsat_old(pt).visualize(min=0, max=0.25).blend(markv)
            chip(old, region, {}, os.path.join(out_dir, f"{s['id']}_old.png"))
        except Exception as e:
            print(s["id"], "landsat failed", e)
        new = s2_new(pt).visualize(min=0, max=0.25).blend(markv)
        chip(new, region, {}, os.path.join(out_dir, f"{s['id']}_new.png"))
        hist = water_history(pt, r)
        report[s["id"]] = {"lat": lat, "lon": lon, "water_by_year": hist}
        yrs = sorted(hist)
        line = "".join("?" if hist[y] is None else ("#" if hist[y] > 0.3 else ("+" if hist[y] > 0.05 else "."))
                       for y in yrs)
        print(f"{s['id']:24s} {yrs[0]}..{yrs[-1]} {line}")
    with open(os.path.join(out_dir, "history.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
