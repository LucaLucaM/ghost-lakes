"""Presentation assets for the Abidjan lagoon-infill finding.

Creates:
  outputs/abidjan/s2_2023.png, s2_2026.png      Sentinel-2 composites of the study box (with bounds)
  outputs/abidjan/figure_before_after.png       numbered before/after panels + timeline
  outputs/abidjan/abidjan_map.html              interactive map (works offline from EE: images embedded as overlays)

Needs outputs/abidjan_infill.geojson and outputs/abidjan_infill_timing.json (run lagoon_infill.py first,
then the timing step in FINDINGS.md / abidjan_timing.py).
Run:  python abidjan_figures.py
"""
import base64
import json
import os
import urllib.request

import ee
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

import ghostlakes as gl

OUT = os.path.join(gl.OUT, "abidjan")
VIEW = [-4.005, 5.258, -3.928, 5.296]          # lon_min, lat_min, lon_max, lat_max (main cluster)
SUPPRESSION = "2023"                            # suspension of landfill permits
WARNING = "2026-02"                             # minister's public warning
PM_ORDER = "2026-06"                            # Prime Minister's stop order


def s2(a, b, geom):
    def mask(i):
        scl = i.select("SCL")
        return i.updateMask(scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)))
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(geom).filterDate(a, b)
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60)).map(mask))
    return col.median().select(["B4", "B3", "B2"]).divide(10000).visualize(min=0, max=0.2)


def download(img, bounds, path, width=1600):
    region = ee.Geometry.Rectangle(bounds, "EPSG:4326", False)
    url = img.getThumbURL({"region": region, "dimensions": width, "format": "png", "crs": "EPSG:4326"})
    urllib.request.urlretrieve(url, path)


def to_px(lon, lat, bounds, size):
    w, h = size
    x = (lon - bounds[0]) / (bounds[2] - bounds[0]) * w
    y = (bounds[3] - lat) / (bounds[3] - bounds[1]) * h
    return x, y


def main():
    gl.init()
    os.makedirs(OUT, exist_ok=True)
    gj = json.load(open(os.path.join(gl.OUT, "abidjan_infill.geojson")))
    timing = json.load(open(os.path.join(gl.OUT, "abidjan_infill_timing.json")))
    geom = ee.Geometry.Rectangle(VIEW, "EPSG:4326", False)

    p23, p26 = os.path.join(OUT, "s2_2023.png"), os.path.join(OUT, "s2_2026.png")
    if not os.path.exists(p23):
        download(s2("2023-01-01", "2023-07-01", geom), VIEW, p23)
    if not os.path.exists(p26):
        download(s2("2026-04-01", "2026-11-14", geom), VIEW, p26)

    # ---------------- figure: before | after | timeline
    im23, im26 = Image.open(p23).convert("RGB"), Image.open(p26).convert("RGB")
    aspect = im23.size[1] / im23.size[0]
    fig = plt.figure(figsize=(16, 8 * aspect + 4.2), dpi=150)
    gs = fig.add_gridspec(2, 2, height_ratios=[8 * aspect, 3.6], hspace=0.12, wspace=0.03)
    for k, (im, title) in enumerate([(im23, "Jan–Jun 2023 (before)"), (im26, "Apr–Nov 2026 (after)")]):
        ax = fig.add_subplot(gs[0, k])
        ax.imshow(im)
        ax.set_title(f"Sentinel-2 · {title}", fontsize=13, loc="left")
        ax.axis("off")
        for i, ft in enumerate(gj["features"], 1):
            ring = ft["geometry"]["coordinates"][0]
            xs, ys = zip(*[to_px(x, y, VIEW, im.size) for x, y in ring])
            ax.plot(xs, ys, color="#ff2d55", lw=1.6)
            cx, cy = to_px(ft["properties"]["lon"], ft["properties"]["lat"], VIEW, im.size)
            if 0 <= cx <= im.size[0] and 0 <= cy <= im.size[1]:
                ax.text(cx, cy - 18, str(i), color="white", fontsize=10, ha="center", weight="bold",
                        bbox=dict(boxstyle="circle,pad=0.2", fc="#ff2d55", ec="none"))
        ax.set_xlim(0, im.size[0])
        ax.set_ylim(im.size[1], 0)

    ax = fig.add_subplot(gs[1, :])
    months = [l for l, _ in timing["1"]["series"]]
    idx = {m: i for i, m in enumerate(months)}
    for i in range(1, len(gj["features"]) + 1):
        t = timing[str(i)]
        for m, v in t["series"]:
            if v is None:
                continue
            ax.add_patch(plt.Rectangle((idx[m], i - 0.4), 1, 0.8,
                                       color="#2b6cb0" if v >= 0.5 else ("#9ec5e8" if v >= 0.3 else "#e0b25b"), lw=0))
    for m, lab, ha, dx in [("2026-02", "Minister's warning (Feb 2026)", "right", -0.3),
                           ("2026-06", "PM stop order (Jun 2026)", "left", 0.3)]:
        ax.axvline(idx[m], color="black", ls="--", lw=1)
        ax.text(idx[m] + dx, 0.3, lab, fontsize=9, va="bottom", ha=ha)
    ax.set_xlim(0, len(months))
    ax.set_ylim(len(gj["features"]) + 0.6, 0.4)
    ax.set_yticks(range(1, len(gj["features"]) + 1))
    ax.set_yticklabels([f"#{i}  {gj['features'][i-1]['properties']['area_ha']:.1f} ha" for i in range(1, len(gj['features']) + 1)],
                       fontsize=8)
    ax.set_xticks([idx[m] for m in months if m.endswith("-01")])
    ax.set_xticklabels([m[:4] for m in months if m.endswith("-01")])
    ax.set_title("Dynamic World status of each site (2-month windows): blue = lagoon water, sand = land, gap = clouds",
                 fontsize=11, loc="left")
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    total = sum(f["properties"]["area_ha"] for f in gj["features"])
    after_2024 = sum(gj["features"][int(i) - 1]["properties"]["area_ha"] for i, t in timing.items()
                     if t["first_month_land"] and t["first_month_land"] >= "2024-01")
    fig.suptitle(f"A ban on paper, sand in the water: {total:.0f} ha of Abidjan's Ébrié lagoon became land "
                 f"at {len(gj['features'])} sites, 2023–2026\n"
                 f"({after_2024:.0f} ha of it from 2024 on), despite a 2023 infill suspension",
                 fontsize=14, x=0.01, ha="left", weight="bold")
    fig.savefig(os.path.join(OUT, "figure_before_after.png"), bbox_inches="tight")
    print("figure ok")

    # ---------------- interactive map with embedded overlays (no EE tile expiry)
    import folium
    m = folium.Map(location=[(VIEW[1] + VIEW[3]) / 2, (VIEW[0] + VIEW[2]) / 2], zoom_start=14, tiles=None,
                   control_scale=True)
    base = folium.TileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery", name="Esri imagery").add_to(m)
    bounds = [[VIEW[1], VIEW[0]], [VIEW[3], VIEW[2]]]

    def data_uri(p):
        return "data:image/png;base64," + base64.b64encode(open(p, "rb").read()).decode()
    folium.raster_layers.ImageOverlay(data_uri(p23), bounds=bounds, name="Sentinel-2 2023 (before)").add_to(m)
    folium.raster_layers.ImageOverlay(data_uri(p26), bounds=bounds, name="Sentinel-2 2026 (after)").add_to(m)
    fg = folium.FeatureGroup(name="Infilled since 2023").add_to(m)
    for i, ft in enumerate(gj["features"], 1):
        p, t = ft["properties"], timing[str(i)]
        popup = (f"<b>Site #{i}</b><br>{p['area_ha']:.2f} ha<br>last month with water: {t['last_month_water']}<br>"
                 f"first month as land: {t['first_month_land']}<br>{p['lat']:.5f}, {p['lon']:.5f}")
        folium.GeoJson(ft, style_function=lambda _: {"color": "#ff2d55", "weight": 2, "fillOpacity": 0.15},
                       popup=folium.Popup(popup, max_width=240), tooltip=f"#{i} · {p['area_ha']:.1f} ha").add_to(fg)
        folium.Marker([p["lat"], p["lon"]], icon=folium.DivIcon(html=(
            f"<div style='background:#ff2d55;color:#fff;border-radius:50%;width:22px;height:22px;"
            f"text-align:center;font:bold 12px/22px sans-serif'>{i}</div>"))).add_to(fg)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(os.path.join(OUT, "abidjan_map.html"))
    print("map ok")


if __name__ == "__main__":
    main()
