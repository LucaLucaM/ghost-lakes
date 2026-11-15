"""Paths, Earth Engine setup and the satellite helpers shared by every step."""
import io
import json
import os
import time
import urllib.parse
import urllib.request

import ee

PROJECT = "lootlake"          # your Google Earth Engine project id
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "outputs")
UA = {"User-Agent": "ghostlakes-hackathon/0.1"}


def init():
    ee.Initialize(project=PROJECT)


def box(b):
    """[lon_min, lat_min, lon_max, lat_max] -> ee.Geometry.Rectangle"""
    return ee.Geometry.Rectangle(b)


def out_path(*parts):
    p = os.path.join(OUT, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def load_json(*parts, default=None):
    p = os.path.join(OUT, *parts)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save_json(obj, *parts, indent=None):
    with open(out_path(*parts), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=indent, ensure_ascii=False)


# ---------------------------------------------------------------- satellite layers

def jrc():
    """JRC Global Surface Water 1984-2021 (occurrence, max_extent, transition, ...)."""
    return ee.Image("JRC/GSW1_4/GlobalSurfaceWater")


def occurrence():
    return jrc().select("occurrence").unmask(0)


def dw_mean(geom, a, b, bands=("water", "built", "bare")):
    """Mean Dynamic World class probabilities over a period."""
    return (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(geom).filterDate(a, b)
            .select(list(bands)).mean())


def s2_median(geom, a, b, bands=("B4", "B3", "B2"), max_cloud=60):
    """Cloud-masked (SCL) Sentinel-2 surface-reflectance median, scaled to 0-1."""
    def mask(i):
        scl = i.select("SCL")
        return i.updateMask(scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)))
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(geom).filterDate(a, b)
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud)).map(mask))
    return col.median().select(list(bands)).divide(10000)


def s2_rgb(geom, a, b, max_cloud=60, vmax=0.2):
    return s2_median(geom, a, b, max_cloud=max_cloud).visualize(min=0, max=vmax)


def outline(features, color="ff2d55", width=1):
    """Red outlines of GeoJSON features, as an image to blend on top of a picture."""
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(f["geometry"])) for f in features])
    return ee.Image().paint(fc, 1, width).visualize(palette=[color])


def fetch(img, bounds, width):
    """Download a visualised image for [lon_min, lat_min, lon_max, lat_max] as a PIL image."""
    from PIL import Image
    region = ee.Geometry.Rectangle(bounds, "EPSG:4326", False)
    url = img.getThumbURL({"region": region, "dimensions": width, "format": "png", "crs": "EPSG:4326"})
    return Image.open(io.BytesIO(urllib.request.urlopen(url).read())).convert("RGB")


def to_px(lon, lat, bounds, size):
    """Map lon/lat to pixel x/y in an image covering `bounds` (EPSG:4326)."""
    w, h = size
    return ((lon - bounds[0]) / (bounds[2] - bounds[0]) * w, (bounds[3] - lat) / (bounds[3] - bounds[1]) * h)


def font(size):
    from PIL import ImageFont
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


# ---------------------------------------------------------------- OpenStreetMap

OVERPASS = ["https://overpass-api.de/api/interpreter",
            "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]


def overpass(q):
    """Run an Overpass query, trying mirrors (busy servers are common)."""
    last = None
    for _ in range(3):
        for url in OVERPASS:
            try:
                req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(), headers=UA)
                return json.load(urllib.request.urlopen(req, timeout=120))
            except Exception as e:
                last = e
        time.sleep(15)
    raise RuntimeError(last)


def reverse_geocode(lat, lon, lang="en", zoom=16):
    """Nominatim reverse geocoding (max 1 request/second by policy)."""
    url = (f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat:.5f}&lon={lon:.5f}"
           f"&zoom={zoom}&accept-language={lang}")
    res = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60))
    time.sleep(1.1)
    return res
