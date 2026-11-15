"""Sentinel-2 chips H1 2023 vs Apr-Nov 2026 around points, side by side with labels.
Usage: python recent_chips.py sites.csv out.png [half_size_m]     (sites.csv: id,lat,lon)
"""
import csv
import io
import sys
import urllib.request

import ee
from PIL import Image, ImageDraw

import ghostlakes as gl


def s2(pt, a, b):
    def mask(i):
        scl = i.select("SCL")
        return i.updateMask(scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)))
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(pt).filterDate(a, b)
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60)).map(mask))
    return col.median().select(["B4", "B3", "B2"]).divide(10000).visualize(min=0, max=0.22)


def main(path, out, half=600):
    gl.init()
    half = float(half)
    sites = list(csv.DictReader(open(path, encoding="utf-8")))
    S = 300
    sheet = Image.new("RGB", (2 * S + 10, len(sites) * (S + 18)), "white")
    d = ImageDraw.Draw(sheet)
    for r, s in enumerate(sites):
        pt = ee.Geometry.Point([float(s["lon"]), float(s["lat"])])
        reg = pt.buffer(half).bounds()
        mark = ee.Image().paint(ee.FeatureCollection([ee.Feature(pt.buffer(60))]), 1, 2).visualize(palette=["ff0000"])
        for c, (a, b, lab) in enumerate([("2023-01-01", "2023-07-01", "2023 H1"), ("2026-04-01", "2026-11-15", "2026")]):
            url = s2(pt, a, b).blend(mark).getThumbURL({"region": reg, "dimensions": S, "format": "png"})
            im = Image.open(io.BytesIO(urllib.request.urlopen(url).read())).convert("RGB").resize((S, S))
            sheet.paste(im, (c * (S + 10), r * (S + 18) + 18))
            d.text((c * (S + 10) + 3, r * (S + 18) + 3), f"{s['id']}  {lab}", fill="black")
    sheet.save(out)


if __name__ == "__main__":
    main(*sys.argv[1:])
