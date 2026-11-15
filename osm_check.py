"""For each site: is there any water / wetland / named lake feature in OpenStreetMap nearby,
and what is the neighbourhood called (Nominatim reverse geocode).

Usage: python osm_check.py sites.csv out.json      (columns: id,lat,lon)
"""
import csv
import json
import sys
import time
import urllib.parse
import urllib.request

UA = {"User-Agent": "ghostlakes-hackathon/0.1"}
MIRRORS = ["https://overpass-api.de/api/interpreter",
           "https://overpass.kumi.systems/api/interpreter",
           "https://overpass.private.coffee/api/interpreter"]


def overpass(q):
    last = None
    for _ in range(3):
        for url in MIRRORS:
            try:
                req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(), headers=UA)
                return json.load(urllib.request.urlopen(req, timeout=120))
            except Exception as e:
                last = e
        time.sleep(15)
    raise RuntimeError(last)


def check(lat, lon, r=250):
    q = f"""[out:json][timeout:60];
(nwr(around:{r},{lat},{lon})["natural"~"water|wetland"];
 nwr(around:{r},{lat},{lon})["water"];
 nwr(around:{r},{lat},{lon})["landuse"="reservoir"];
 nwr(around:{r},{lat},{lon})["name"~"[Ll]ake|[Tt]ank|[Pp]ond|[Ll]ac|[Cc]heruvu|[Kk]unta|[Kk]ere|[Ee]ri|[Kk]ulam|[Tt]alab|[Ss]agar|[Bb]il|[Hh]aor|[Bb]arrage|[Mm]are|[Bb]arrage|[Dd]am",i];
 nwr(around:{r},{lat},{lon})["historic"];
);
out tags center;"""
    els = overpass(q)["elements"]
    feats = [{k: e["tags"].get(k) for k in ("name", "name:en", "natural", "water", "landuse", "historic", "amenity", "leisure")
              if e["tags"].get(k)} for e in els]
    rev = json.load(urllib.request.urlopen(urllib.request.Request(
        f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}&zoom=16&accept-language=en",
        headers=UA), timeout=60))
    time.sleep(1.1)  # Nominatim usage policy: max 1 req/s
    return {"osm_features": feats, "place": rev.get("display_name")}


def main(csv_path, out):
    res = {}
    with open(csv_path, encoding="utf-8") as f:
        for s in csv.DictReader(f):
            try:
                res[s["id"]] = check(float(s["lat"]), float(s["lon"]))
            except Exception as e:
                res[s["id"]] = {"error": str(e)}
            r = res[s["id"]]
            print(s["id"], "|", (r.get("place") or "")[:90], "|",
                  [x.get("name") or x.get("natural") or x.get("water") for x in r.get("osm_features", [])][:6])
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
