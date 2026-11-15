"""The Abidjan case study (Ébrié lagoon), step by step. Each step reads the previous step's outputs.

  detect      optical sites + radar confirmation  -> abidjan_infill.geojson (+ _optical_all)
  timing      optical fill month per site          -> abidjan_infill_timing.json
  accuracy    independent area checks, threshold sensitivity, radar dates -> abidjan_accuracy.json
  population  people within 500 m / 1 km           -> abidjan_population.json
  table       shareable site list                  -> abidjan/abidjan_sites.csv / .geojson
  figure      before/after + per-site timeline, interactive map -> abidjan/figure_before_after.png, abidjan_map.html
  timelapse   zoomed half-year timelapse, every site up close   -> abidjan/timelapse.gif, sites_zoom.png
  after_pm    radar-only search for fills after the June 2026 stop order (weak evidence) -> abidjan_after_pm_order.geojson
"""
import base64
import csv
import itertools
import os

import ee

from . import infill, radar
from .common import (box, dw_mean, fetch, font, init, load_json, occurrence, out_path, outline, reverse_geocode,
                     s2_median, s2_rgb, save_json, to_px)

BOX = [-4.12, 5.22, -3.70, 5.42]               # Ébrié lagoon, Abidjan
THEN = ("2023-01-01", "2023-07-01")            # still water
NOW = ("2026-04-01", "2026-11-15")             # land now
RADAR_AFTER = ("2026-08-15", "2026-11-15")     # recent radar window
EVENTS = [("2026-02", "Minister's warning (11 Feb 2026)", "right", -0.3),
          ("2026-06", "PM stop order (11 Jun 2026)", "left", 0.3)]
VIEW = [-4.005, 5.256, -3.928, 5.326]          # figure window (all 11 sites)
PANELS = [("Vridi / Grands Moulins", [-4.0015, 5.2640, -3.9760, 5.2880]),
          ("Koumassi / Petit Bassam", [-3.9690, 5.2610, -3.9380, 5.2905])]
HALF_YEARS = [("2023-01-01", "2023-07-01", "Jan–Jun 2023"), ("2023-07-01", "2024-01-01", "Jul–Dec 2023"),
              ("2024-01-01", "2024-07-01", "Jan–Jun 2024"), ("2024-07-01", "2025-01-01", "Jul–Dec 2024"),
              ("2025-01-01", "2025-07-01", "Jan–Jun 2025"), ("2025-07-01", "2026-01-01", "Jul–Dec 2025"),
              ("2026-01-01", "2026-07-01", "Jan–Jun 2026"), ("2026-07-01", "2026-11-15", "Jul–Nov 2026")]


def sites():
    return load_json("abidjan_infill.geojson")["features"]


def site_fc(feats):
    return ee.FeatureCollection([ee.Feature(ee.Geometry(f["geometry"]), {"id": i + 1}) for i, f in enumerate(feats)])


# ---------------------------------------------------------------- detection and dates

def detect():
    gj, area = infill.detect(BOX, THEN, NOW, RADAR_AFTER)
    save_json(gj, "abidjan_infill_optical_all.geojson")
    conf = [f for f in gj["features"] if f["properties"]["radar_confirmed"]]
    save_json({"type": "FeatureCollection", "features": conf}, "abidjan_infill.geojson")
    for f in gj["features"]:
        p = f["properties"]
        print(f"  {p['lat']:.5f},{p['lon']:.5f}  {p['area_ha']:5.2f} ha  VV {p['vv_before_db']} -> {p['vv_after_db']} dB  "
              f"{'radar OK' if p['radar_confirmed'] else 'REJECTED by radar'}")
    print(f"optical {area:.1f} ha in total; radar-confirmed {len(conf)} sites, "
          f"{sum(f['properties']['area_ha'] for f in conf):.1f} ha")


def timing():
    t = infill.timing(sites())
    save_json(t, "abidjan_infill_timing.json", indent=1)
    for i, s in t.items():
        print(f"#{i:2d} {s['area_ha']:.2f} ha  last water {s['last_month_water']}  first land {s['first_month_land']}")


# ---------------------------------------------------------------- accuracy

def _area_checks(fc, geom):
    """Independent area per site: Sentinel-2 reflectance rule (water NIR < 0.10; land NIR and SWIR > 0.15;
    MNDWI fails in this turbid, hazy lagoon) and radar per pixel. 'inside' = within our polygons
    (precision); 'grown' = +20 m (does the change extend past our edges?)."""
    s23, s26 = s2_median(geom, *THEN, bands=("B8", "B11")), s2_median(geom, *NOW, bands=("B8", "B11"))
    optical = s23.select("B8").lt(0.10).And(s26.select("B8").gt(0.15)).And(s26.select("B11").gt(0.15))
    vb, va = radar.vv(geom, *THEN), radar.vv(geom, *RADAR_AFTER)
    rad = vb.lte(radar.BEFORE_MAX_DB).And(va.subtract(vb).gte(radar.MIN_CHANGE_DB))
    area = (optical.rename("refl_ha").addBands(rad.rename("radar_ha")).addBands(optical.And(rad).rename("both_ha"))
            .multiply(ee.Image.pixelArea()).divide(1e4))
    out = {}
    for key, coll in (("inside", fc), ("grown", fc.map(lambda f: f.buffer(20)))):
        for r in area.reduceRegions(coll, ee.Reducer.sum(), 10, tileScale=4).getInfo()["features"]:
            p = r["properties"]
            out.setdefault(p["id"], {})[key] = {k: p.get(k) for k in ("refl_ha", "radar_ha", "both_ha")}
    return out


def _threshold_grid(geom):
    """Total area for 27 threshold combinations (radar rule applied per pixel, 0.5 ha patches)."""
    t, n = dw_mean(geom, *THEN), dw_mean(geom, *NOW)
    vb = radar.vv(geom, *THEN).focalMean(15, "circle", "meters")
    va = radar.vv(geom, *RADAR_AFTER).focalMean(15, "circle", "meters")
    radar_ok = vb.lte(radar.BEFORE_MAX_DB).And(va.subtract(vb).gte(radar.MIN_CHANGE_DB))
    combos = list(itertools.product([0.6, 0.7, 0.8], [0.1, 0.2, 0.3], [0.4, 0.5, 0.6]))
    bands = []
    for k, (tw, nw, land) in enumerate(combos):
        m = (t.select("water").gte(tw).And(n.select("water").lte(nw)).And(n.select("built").add(n.select("bare")).gte(land))
             .And(occurrence().gte(50)).And(radar_ok))
        m = m.updateMask(m.connectedPixelCount(200, True).gte(50)).unmask(0)
        bands.append(m.multiply(ee.Image.pixelArea()).divide(1e4).rename(f"c{k}"))
    sums = ee.Image.cat(bands).reduceRegion(ee.Reducer.sum(), geom, 10, maxPixels=1e10, tileScale=8).getInfo()
    return [{"then_water": tw, "now_water": nw, "land": land, "area_ha": round(sums[f"c{k}"], 2)}
            for k, (tw, nw, land) in enumerate(combos)]


def accuracy():
    feats = sites()
    fc, geom = site_fc(feats), box(BOX)
    ind = _area_checks(fc, geom)
    tot = {"dw": 0.0, "refl": 0.0, "radar": 0.0}
    inside = {"dw": 0.0, "refl": 0.0, "radar": 0.0, "both": 0.0}
    for i, f in enumerate(feats, 1):
        a = f["properties"]["area_ha"]
        g, s = ind.get(i, {}).get("grown", {}), ind.get(i, {}).get("inside", {})
        tot["dw"] += a
        inside["dw"] += a
        tot["refl"] += g.get("refl_ha") or 0.0
        tot["radar"] += g.get("radar_ha") or 0.0
        for k in ("refl", "radar", "both"):
            inside[k] += s.get(f"{k}_ha") or 0.0
    grid = _threshold_grid(geom)
    dates = {i: radar.change_date(s) for i, s in radar.series(feats, "2023-01-01", "2026-11-16").items()}
    print("area inside polygons:", {k: round(v, 1) for k, v in inside.items()})
    print("area with +20 m margin:", {k: round(v, 1) for k, v in tot.items()})
    print("threshold grid (0.6-0.7):", min(g["area_ha"] for g in grid if g["then_water"] < 0.8), "-",
          max(g["area_ha"] for g in grid), "ha")
    timing_ = load_json("abidjan_infill_timing.json", default={})
    for i, r in dates.items():
        t = timing_.get(str(i), {})
        print(f"  #{i:2d} optical land from {t.get('first_month_land')}  radar land from {(r or {}).get('radar_land_from')}")
    save_json({"area_independent_ha": ind, "totals_ha": {k: round(v, 2) for k, v in tot.items()},
               "inside_polygon_ha": {k: round(v, 2) for k, v in inside.items()},
               "threshold_grid": grid, "radar_dates": dates}, "abidjan_accuracy.json", indent=1)


# ---------------------------------------------------------------- people and the shareable table

def population():
    """Exposure, not damage: who lives next to the filled lagoon (GHSL 2025)."""
    feats = sites()
    union = {r: infill.people_union(feats, r) for r in (500, 1000)}
    per = infill.people_nearby(feats, 500)
    print("people within 500 m / 1 km of any site:", union)
    save_json({"dataset": infill.POP, "people_within_m": union,
               "per_site_500m": {i + 1: per[i] for i in range(len(feats))}}, "abidjan_population.json", indent=1)


def table():
    """One row per site, for journalists and authorities (CSV with BOM so Excel shows accents)."""
    gj = load_json("abidjan_infill.geojson")
    timing_ = load_json("abidjan_infill_timing.json", default={})
    dates = load_json("abidjan_accuracy.json", default={}).get("radar_dates", {})
    pop = load_json("abidjan_population.json", default={}).get("per_site_500m", {})
    cache = load_json("abidjan", "places.json", default={})
    rows = []
    for i, f in enumerate(gj["features"], 1):
        p = f["properties"]
        key = f"{p['lat']:.5f},{p['lon']:.5f}"
        if key not in cache:
            a = reverse_geocode(p["lat"], p["lon"], lang="fr").get("address", {})
            cache[key] = ", ".join(x for x in [a.get("neighbourhood") or a.get("suburb") or a.get("quarter"),
                                               a.get("city_district") or a.get("town") or a.get("city")] if x)
        t, r = timing_.get(str(i), {}), dates.get(str(i)) or {}
        row = {"site": i, "neighbourhood": cache[key], "lat": round(p["lat"], 5), "lon": round(p["lon"], 5),
               "area_ha": round(p["area_ha"], 2),
               "optical_last_water": t.get("last_month_water"), "optical_land_from": t.get("first_month_land"),
               "radar_last_water": r.get("radar_last_water"), "radar_land_from": r.get("radar_land_from"),
               "radar_vv_2023_db": p.get("vv_before_db"), "radar_vv_now_db": p.get("vv_after_db"),
               "people_within_500m": pop.get(str(i)),
               "map": f"https://www.openstreetmap.org/?mlat={p['lat']:.5f}&mlon={p['lon']:.5f}#map=17/{p['lat']:.5f}/{p['lon']:.5f}"}
        months = [m for m in (row["optical_land_from"], (row["radar_land_from"] or "")[:7]) if m]
        row["dates_agree"] = len(months) == 2 and abs(
            (int(months[0][:4]) * 12 + int(months[0][5:7])) - (int(months[1][:4]) * 12 + int(months[1][5:7]))) <= 3
        rows.append(row)
        f["properties"].update(row)
    save_json(cache, "abidjan", "places.json", indent=1)
    with open(out_path("abidjan", "abidjan_sites.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    save_json(gj, "abidjan", "abidjan_sites.geojson")
    for r in rows:
        print(f"#{r['site']:2d} {r['neighbourhood']:28s} {r['area_ha']:5.2f} ha  optical {r['optical_land_from']}  "
              f"radar {r['radar_land_from']}  agree={r['dates_agree']}  people {r['people_within_500m']}")


# ---------------------------------------------------------------- figure and interactive map

def figure():
    import folium
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    feats = sites()
    timing_ = load_json("abidjan_infill_timing.json")
    dates = load_json("abidjan_accuracy.json", default={}).get("radar_dates", {})
    pop = load_json("abidjan_population.json", default={}).get("per_site_500m", {})
    geom = ee.Geometry.Rectangle(VIEW, "EPSG:4326", False)
    tag = "_".join(f"{v:.3f}" for v in VIEW)   # cache names carry the bounds: a new VIEW never reuses old images
    imgs = {}
    for key, (a, b) in (("2023", THEN), ("2026", ("2026-04-01", "2026-11-14"))):
        p = out_path("abidjan", f"s2_{key}_{tag}.png")
        if not os.path.exists(p):
            fetch(s2_rgb(geom, a, b), VIEW, 1600).save(p)
        imgs[key] = p
    from PIL import Image
    im23, im26 = Image.open(imgs["2023"]).convert("RGB"), Image.open(imgs["2026"]).convert("RGB")

    aspect = im23.size[1] / im23.size[0]
    fig = plt.figure(figsize=(16, 8 * aspect + 4.2), dpi=150)
    gs = fig.add_gridspec(2, 2, height_ratios=[8 * aspect, 3.6], hspace=0.2, wspace=0.03)
    for k, (im, title) in enumerate([(im23, "Jan–Jun 2023 (before)"), (im26, "Apr–Nov 2026 (after)")]):
        ax = fig.add_subplot(gs[0, k])
        ax.imshow(im)
        ax.set_title(f"Sentinel-2 · {title}", fontsize=13, loc="left")
        ax.axis("off")
        for i, ft in enumerate(feats, 1):
            xs, ys = zip(*[to_px(x, y, VIEW, im.size) for x, y in ft["geometry"]["coordinates"][0]])
            ax.plot(xs, ys, color="#ff2d55", lw=1.6)
            cx, cy = to_px(ft["properties"]["lon"], ft["properties"]["lat"], VIEW, im.size)
            if 0 <= cx <= im.size[0] and 0 <= cy <= im.size[1]:
                ax.text(cx, cy - 18, str(i), color="white", fontsize=10, ha="center", weight="bold",
                        bbox=dict(boxstyle="circle,pad=0.2", fc="#ff2d55", ec="none"))
        ax.set_xlim(0, im.size[0])
        ax.set_ylim(im.size[1], 0)

    ax = fig.add_subplot(gs[1, :])
    months = [m for m, _ in timing_["1"]["series"]]
    idx = {m: i for i, m in enumerate(months)}
    for i in range(1, len(feats) + 1):
        for m, v in timing_[str(i)]["series"]:
            if v is not None:
                ax.add_patch(plt.Rectangle((idx[m], i - 0.4), 1, 0.8, lw=0,
                                           color="#2b6cb0" if v >= 0.5 else ("#9ec5e8" if v >= 0.3 else "#e0b25b")))
        rd = (dates.get(str(i)) or {}).get("radar_land_from")
        if rd and rd[:7] in idx:   # independent radar date (black diamond)
            ax.plot(idx[rd[:7]] + (int(rd[8:10]) - 1) / 31, i, marker="D", color="black", ms=4.5, zorder=5)
    for m, lab, ha, dx in EVENTS:
        ax.axvline(idx[m], color="black", ls="--", lw=1)
        ax.text(idx[m] + dx, 0.3, lab, fontsize=9, va="bottom", ha=ha)
    ax.set_xlim(0, len(months))
    ax.set_ylim(len(feats) + 0.6, 0.4)
    ax.set_yticks(range(1, len(feats) + 1))
    ax.set_yticklabels([f"#{i}  {f['properties']['area_ha']:.1f} ha" for i, f in enumerate(feats, 1)], fontsize=8)
    ax.set_xticks([idx[m] for m in months if m.endswith("-01")])
    ax.set_xticklabels([m[:4] for m in months if m.endswith("-01")])
    ax.set_title("Optical status per site (Dynamic World, 2-month windows): blue = water, sand = land, gap = clouds\n"
                 "◆ = independent check: radar (Sentinel-1) says land from here", pad=18, fontsize=11, loc="left")
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    total = sum(f["properties"]["area_ha"] for f in feats)
    after_2024 = sum(feats[int(i) - 1]["properties"]["area_ha"] for i, t in timing_.items()
                     if t["first_month_land"] and t["first_month_land"] >= "2024-01")
    fig.suptitle(f"A ban on paper, sand in the water: {total:.0f} ha of Abidjan's Ébrié lagoon became land "
                 f"at {len(feats)} sites, 2023–2026\n({after_2024:.0f} ha of it from 2024 on), "
                 f"despite a 2023 infill suspension", fontsize=14, x=0.01, ha="left", weight="bold")
    fig.savefig(out_path("abidjan", "figure_before_after.png"), bbox_inches="tight")

    # interactive map, imagery embedded (no expiring Earth Engine tiles)
    m = folium.Map(location=[(VIEW[1] + VIEW[3]) / 2, (VIEW[0] + VIEW[2]) / 2], zoom_start=14, tiles=None, control_scale=True)
    folium.TileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                     attr="Esri World Imagery", name="Esri imagery").add_to(m)
    bounds = [[VIEW[1], VIEW[0]], [VIEW[3], VIEW[2]]]
    for key, name in (("2023", "Sentinel-2 2023 (before)"), ("2026", "Sentinel-2 2026 (after)")):
        with open(imgs[key], "rb") as fh:
            uri = "data:image/png;base64," + base64.b64encode(fh.read()).decode()
        folium.raster_layers.ImageOverlay(uri, bounds=bounds, name=name).add_to(m)
    fg = folium.FeatureGroup(name="Infilled since 2023").add_to(m)
    for i, ft in enumerate(feats, 1):
        p, t, rd = ft["properties"], timing_[str(i)], dates.get(str(i)) or {}
        popup = (f"<b>Site #{i}</b><br>{p['area_ha']:.2f} ha<br>"
                 f"optical: water until {t['last_month_water']}, land from {t['first_month_land']}<br>"
                 f"radar: water until {rd.get('radar_last_water')}, land from {rd.get('radar_land_from')}<br>"
                 + (f"people within 500 m: ~{pop[str(i)]:,}<br>" if str(i) in pop else "")
                 + f"{p['lat']:.5f}, {p['lon']:.5f}")
        folium.GeoJson(ft, style_function=lambda _: {"color": "#ff2d55", "weight": 2, "fillOpacity": 0.15},
                       popup=folium.Popup(popup, max_width=240), tooltip=f"#{i} · {p['area_ha']:.1f} ha").add_to(fg)
        folium.Marker([p["lat"], p["lon"]], icon=folium.DivIcon(html=(
            f"<div style='background:#ff2d55;color:#fff;border-radius:50%;width:22px;height:22px;"
            f"text-align:center;font:bold 12px/22px sans-serif'>{i}</div>"))).add_to(fg)
    folium.LayerControl(collapsed=False).add_to(m)
    m.save(out_path("abidjan", "abidjan_map.html"))
    print("figure and map ok")


# ---------------------------------------------------------------- timelapse and close-ups

def _label_sites(im, feats, bounds):
    from PIL import ImageDraw
    d, f = ImageDraw.Draw(im), font(15)
    for i, ft in enumerate(feats, 1):
        x, y = to_px(ft["properties"]["lon"], ft["properties"]["lat"], bounds, im.size)
        if 0 <= x < im.size[0] and 0 <= y < im.size[1]:
            lx, ly = x - 34, y - 34   # up-left, so the label never hides the change
            d.ellipse([lx - 13, ly - 13, lx + 13, ly + 13], fill=(255, 45, 85))
            d.text((lx, ly), str(i), font=f, fill="white", anchor="mm")


def timelapse(panel_w=640):
    from PIL import Image, ImageDraw
    feats = sites()
    lines = outline(feats)
    frames = []
    for k, (a, b, label) in enumerate(HALF_YEARS):
        panels = []
        for name, bounds in PANELS:
            geom = ee.Geometry.Rectangle(bounds, "EPSG:4326", False)
            im = fetch(s2_rgb(geom, a, b, max_cloud=70).blend(lines), bounds, panel_w).resize((panel_w, panel_w))
            _label_sites(im, feats, bounds)
            d = ImageDraw.Draw(im)
            d.rectangle([0, im.size[1] - 26, im.size[0], im.size[1]], fill=(0, 0, 0))
            d.text((8, im.size[1] - 23), name, font=font(16), fill="white")
            panels.append(im)
        frame = Image.new("RGB", (2 * panel_w + 8, panel_w + 64), (0, 0, 0))
        frame.paste(panels[0], (0, 64))
        frame.paste(panels[1], (panel_w + 8, 64))
        d = ImageDraw.Draw(frame)
        d.text((14, 10), label, font=font(38), fill="white")
        d.text((frame.size[0] - 14, 14), "Ébrié lagoon, Abidjan · red outline = site filled 2023–2026",
               font=font(18), fill="white", anchor="ra")
        d.text((frame.size[0] - 14, 38), "Sentinel-2, cloud-masked half-year composites · Ghost Lakes",
               font=font(14), fill=(200, 200, 200), anchor="ra")
        frame.save(out_path("abidjan", "frames", f"frame_{k}.png"))
        frames.append(frame)
        print("frame", label)
    frames[0].save(out_path("abidjan", "timelapse.gif"), save_all=True, append_images=frames[1:],
                   duration=[1100] * (len(frames) - 1) + [2600], loop=0, optimize=True)
    # compact before/after for the one-page write-up (Vridi / Grands Moulins panel)
    crops = [f.crop((0, 0, panel_w, f.size[1])) for f in (frames[0], frames[-1])]
    compact = Image.new("RGB", (2 * panel_w + 8, crops[0].size[1]), (0, 0, 0))
    compact.paste(crops[0], (0, 0))
    compact.paste(crops[1], (panel_w + 8, 0))
    compact.save(out_path("abidjan", "before_after_compact.png"))
    _site_grid(feats)


def _site_grid(feats, size=230, pad=20):
    """Every site in a 700 m window at four dates: the visual proof."""
    from PIL import Image, ImageDraw
    periods = [HALF_YEARS[0], HALF_YEARS[3], HALF_YEARS[5], HALF_YEARS[7]]
    grid = Image.new("RGB", (len(periods) * (size + 4) + 4, len(feats) * (size + pad) + 34), "white")
    d = ImageDraw.Draw(grid)
    d.text((6, 6), "Every Abidjan site, 700 m window, Sentinel-2 composites (red = site outline)", font=font(16), fill="black")
    for i, ft in enumerate(feats):
        p = ft["properties"]
        dlat, dlon = 350 / 111320, 350 / (111320 * 0.9962)   # ~350 m at 5° N
        bounds = [p["lon"] - dlon, p["lat"] - dlat, p["lon"] + dlon, p["lat"] + dlat]
        geom = ee.Geometry.Rectangle(bounds, "EPSG:4326", False)
        for k, (a, b, lab) in enumerate(periods):
            im = fetch(s2_rgb(geom, a, b, max_cloud=70).blend(outline([ft])), bounds, size).resize((size, size))
            x, y = 4 + k * (size + 4), 34 + i * (size + pad) + pad
            grid.paste(im, (x, y))
            d.text((x + 2, y - pad + 3), f"#{i + 1} · {p['area_ha']:.1f} ha · {lab}", font=font(13), fill="black")
    grid.save(out_path("abidjan", "sites_zoom.png"))
    print("sites_zoom ok")


# ---------------------------------------------------------------- after the June 2026 stop order (weak evidence)

def after_pm(before=("2026-03-01", "2026-06-10"), after=("2026-08-15", "2026-11-15"), min_ha=0.2):
    """Radar-only: dark water before the stop order, >= +4 dB and >= -15 dB after. Radar alone is noisy
    (boats, floating plants): every hit needs an optical check. See docs/FINDINGS.md."""
    geom = box(BOX)
    col = radar.s1_vv(geom)
    b = col.filterDate(*before).median().focalMean(15, "circle", "meters")
    a = col.filterDate(*after).median().focalMean(15, "circle", "meters")
    m = b.lte(-17).And(a.subtract(b).gte(4)).And(a.gte(-15)).And(occurrence().gte(50))
    m = m.updateMask(m.connectedPixelCount(100, True).gte(int(min_ha * 1e4 / 100))).selfMask()

    def enrich(f):
        c = f.geometry().centroid(1).coordinates()
        return f.set({"area_ha": f.geometry().area(1).divide(1e4), "lon": c.get(0), "lat": c.get(1)})
    gj = (m.reduceToVectors(geometry=geom, scale=10, geometryType="polygon", eightConnected=True,
                            labelProperty="v", maxPixels=1e10, tileScale=8)
          .map(enrich).filter(ee.Filter.gte("area_ha", min_ha)).sort("area_ha", False).getInfo())
    ser = radar.series(gj["features"], "2026-01-01", "2026-11-16") if gj["features"] else {}
    for i, f in enumerate(gj["features"], 1):
        s = ser.get(i, [])
        change = next(((s[k - 1][0], s[k][0]) for k in range(1, len(s)) if all(v > -15 for _, v in s[k:])), (None, None))
        f["properties"].update({"last_water_obs": change[0], "first_land_obs": change[1], "series": s})
        print(f"#{i:2d} {f['properties']['lat']:.5f},{f['properties']['lon']:.5f} {f['properties']['area_ha']:.2f} ha  "
              f"water until {change[0]}  land from {change[1]}")
    save_json(gj, "abidjan_after_pm_order.geojson")


STEPS = {"detect": detect, "timing": timing, "accuracy": accuracy, "population": population,
         "table": table, "figure": figure, "timelapse": timelapse, "after_pm": after_pm}
DEFAULT = ["detect", "timing", "accuracy", "population", "table", "figure", "timelapse"]


def run(steps=None):
    init()
    for s in steps or DEFAULT:
        print(f"== {s}")
        STEPS[s]()
