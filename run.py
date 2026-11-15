"""Ghost Lakes: one entry point for everything.

  python run.py monitor --name abidjan --box -4.12 5.22 -3.70 5.42 \\
                        --then 2023-01-01 2023-07-01 --now 2026-04-01 2026-11-15
                                   infill monitor for ANY place and period (needs Earth Engine)
  python run.py abidjan [STEP ...] the Abidjan case study; steps: detect timing accuracy population
                                   table figure timelapse (default: all) and after_pm
  python run.py terrain            terrain AI: train, leave-one-region-out test, Romanian candidates
  python run.py validate           terrain AI vs documented drained lakes (leave-Bucharest-out)
  python run.py archive [CITY ...] [--perm N]   archive detector (84 cities listed, 59 run; --perm 0 = wave 1)
  python run.py screen [CITY ...]  2023->2026 infill screen of ~120 cities with radar confirmation
  python run.py world scan|hotspots  blind world scan of every urban area (batch job ~1 h, then ranking)
  python run.py radar FILE.geojson BEFORE_START BEFORE_END AFTER_START AFTER_END
  python run.py review history|recent|montage|osm ...   image chips / OSM checks for manual review
  python run.py report             RESULTS.ipynb + one-page PDFs (no Earth Engine needed)
  python -m pytest -q              unit tests (no Earth Engine needed)
"""
import argparse
import json
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("monitor", help="infill monitor for any place")
    m.add_argument("--name", required=True)
    m.add_argument("--box", nargs=4, type=float, required=True, metavar=("LON_MIN", "LAT_MIN", "LON_MAX", "LAT_MAX"))
    m.add_argument("--then", nargs=2, required=True, metavar=("START", "END"), help="period when it was water")
    m.add_argument("--now", nargs=2, required=True, metavar=("START", "END"), help="period when it is land")
    m.add_argument("--radar-after", nargs=2, metavar=("START", "END"), help="default: last 3 months of --now")
    m.add_argument("--min-ha", type=float, default=0.5)

    a = sub.add_parser("abidjan", help="Abidjan case study")
    a.add_argument("steps", nargs="*")
    sub.add_parser("terrain", help="terrain AI")
    sub.add_parser("validate", help="terrain AI vs documented drained lakes")
    ar = sub.add_parser("archive", help="archive detector")
    ar.add_argument("cities", nargs="*")
    ar.add_argument("--perm", type=int, default=3)
    sc = sub.add_parser("screen", help="global 2023->2026 infill screen")
    sc.add_argument("cities", nargs="*")
    w = sub.add_parser("world", help="blind world scan of every urban area")
    w.add_argument("step", choices=["scan", "hotspots"])
    r = sub.add_parser("radar", help="radar check for polygons")
    r.add_argument("geojson")
    r.add_argument("dates", nargs=4)
    rv = sub.add_parser("review", help="manual review tools")
    rv.add_argument("tool", choices=["history", "recent", "montage", "osm"])
    rv.add_argument("args", nargs="+", help="history: sites.csv out_dir | recent: sites.csv out.png | "
                                            "montage: chips_dir out.png [ids] | osm: sites.csv out.json")
    sub.add_parser("report", help="RESULTS.ipynb + PDFs")
    args = ap.parse_args(argv)

    if args.cmd == "monitor":
        from ghostlakes import infill
        infill.monitor(args.name, args.box, args.then, args.now, args.radar_after, args.min_ha)
    elif args.cmd == "abidjan":
        from ghostlakes import abidjan
        abidjan.run(args.steps)
    elif args.cmd == "terrain":
        from ghostlakes import terrain
        terrain.run()
    elif args.cmd == "validate":
        from ghostlakes import terrain
        terrain.validate()
    elif args.cmd == "archive":
        from ghostlakes import archive
        archive.run(args.cities, args.perm)
    elif args.cmd == "screen":
        from ghostlakes import infill
        infill.screen(args.cities)
    elif args.cmd == "world":
        from ghostlakes import world
        if args.step == "scan":
            world.scan()
        else:
            from ghostlakes.common import init
            init()
            hs = world.hotspots()
            print(f"{len(hs)} cells with >= 3 ha, {sum(r['radar_confirmed'] for r in hs)} radar-confirmed "
                  f"(all cells: outputs/world/cells.csv)")
            for r in hs[:30]:
                print(r)
    elif args.cmd == "radar":
        from ghostlakes import radar
        from ghostlakes.common import init
        init()
        with open(args.geojson, encoding="utf-8") as f:
            feats = json.load(f)["features"]
        res = radar.confirm(feats, args.dates[:2], args.dates[2:])
        for i, x in enumerate(res, 1):
            print(f"#{i:2d}  VV {x['vv_before_db']} -> {x['vv_after_db']} dB  "
                  f"{'CONFIRMED' if x['radar_confirmed'] else 'not confirmed'}")
        print(f"{sum(x['radar_confirmed'] for x in res)}/{len(res)} confirmed "
              f"(before <= {radar.BEFORE_MAX_DB} dB and change >= +{radar.MIN_CHANGE_DB} dB)")
    elif args.cmd == "review":
        from ghostlakes import review
        if args.tool == "history":
            review.history_chips(*args.args[:2])
        elif args.tool == "recent":
            review.recent_chips(*args.args[:2])
        elif args.tool == "montage":
            review.montage(args.args[0], args.args[1], args.args[2:] or None)
        else:
            review.osm(*args.args[:2])
    elif args.cmd == "report":
        from ghostlakes import report
        report.notebook()
        report.pdf_fit("WRITEUP.md")
        report.pdf_fit("docs/BRIEF_FR.md", sizes=(9.5, 9.0))


if __name__ == "__main__":
    sys.exit(main())
