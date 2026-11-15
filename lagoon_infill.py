"""Measure Abidjan (Ébrié lagoon) infill between early 2023 and 2026.
(Infill was officially suspended at some point in 2023; the exact date is not public.)

Optical detection (Dynamic World):
  Water then  : P(water) mean over Jan-Jun 2023 >= 0.7  (open lagoon)
  Land now    : P(water) mean over Apr-Nov 2026 <= 0.2 and (built + bare) >= 0.5
  plus JRC occurrence >= 50 (long-term lagoon water, not seasonal puddles)
Radar confirmation (Sentinel-1, see radar_check.py): each optical site must also have been dark
water in H1 2023 and be clearly brighter in the last months (RADAR_AFTER).

Outputs:
  outputs/abidjan_infill.geojson              radar-confirmed sites (used by the next steps)
  outputs/abidjan_infill_optical_all.geojson  every optical site with its radar values
Run order:  python lagoon_infill.py  ->  python abidjan_timing.py  ->  python abidjan_figures.py
"""
import json
import os

import ee

import ghostlakes as gl
import radar_check as rc

BOX = [-4.12, 5.22, -3.70, 5.42]   # Abidjan lagoon (Ébrié) area
THEN = ("2023-01-01", "2023-07-01")
NOW = ("2026-04-01", "2026-11-15")
RADAR_AFTER = ("2026-08-15", "2026-11-15")   # recent radar window, cloud-independent
MIN_HA = 0.5


def dw_mean(geom, a, b):
    return (ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1").filterBounds(geom).filterDate(a, b)
            .select(["water", "built", "bare", "trees", "flooded_vegetation", "grass"]).mean())


def main():
    gl.init()
    geom = gl.box(BOX)
    then = dw_mean(geom, *THEN)
    now = dw_mean(geom, *NOW)
    occ = ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0)
    filled = (then.select("water").gte(0.7)
              .And(now.select("water").lte(0.2))
              .And(now.select("built").add(now.select("bare")).gte(0.5))
              .And(occ.gte(50)))
    filled = filled.updateMask(filled.connectedPixelCount(200, True).gte(5)).selfMask()
    area_ha = ee.Number(filled.multiply(ee.Image.pixelArea()).reduceRegion(
        ee.Reducer.sum(), geom, 10, maxPixels=1e10).values().get(0)).divide(1e4).getInfo()
    vecs = filled.reduceToVectors(geometry=geom, scale=10, geometryType="polygon", eightConnected=True,
                                  labelProperty="v", maxPixels=1e10, tileScale=4)

    def enrich(f):
        a = f.geometry().area(1).divide(1e4)
        c = f.geometry().centroid(1).coordinates()
        return f.set({"area_ha": a, "lon": c.get(0), "lat": c.get(1)})
    vecs = vecs.map(enrich).filter(ee.Filter.gte("area_ha", MIN_HA)).sort("area_ha", False)
    gj = vecs.getInfo()

    radar = rc.confirm(gj["features"], THEN, RADAR_AFTER)
    for ft, r in zip(gj["features"], radar):
        ft["properties"].update(r)
    os.makedirs(gl.OUT, exist_ok=True)
    with open(os.path.join(gl.OUT, "abidjan_infill_optical_all.geojson"), "w", encoding="utf-8") as f:
        json.dump(gj, f)
    confirmed = {"type": "FeatureCollection",
                 "features": [ft for ft in gj["features"] if ft["properties"]["radar_confirmed"]]}
    with open(os.path.join(gl.OUT, "abidjan_infill.geojson"), "w", encoding="utf-8") as f:
        json.dump(confirmed, f)

    print(f"Optical: lagoon -> land {THEN[0]}..{THEN[1]} vs {NOW[0]}..{NOW[1]}: {area_ha:.1f} ha (all patches)")
    print(f"Optical sites >= {MIN_HA} ha: {len(gj['features'])}, "
          f"sum {sum(x['properties']['area_ha'] for x in gj['features']):.1f} ha")
    for ft in gj["features"]:
        p = ft["properties"]
        print(f"  {p['lat']:.5f},{p['lon']:.5f}  {p['area_ha']:.2f} ha  VV {p['vv_before_db']} -> {p['vv_after_db']} dB"
              f"  {'radar OK' if p['radar_confirmed'] else 'REJECTED by radar'}")
    print(f"Radar-confirmed: {len(confirmed['features'])} sites, "
          f"{sum(x['properties']['area_ha'] for x in confirmed['features']):.1f} ha")


if __name__ == "__main__":
    main()
