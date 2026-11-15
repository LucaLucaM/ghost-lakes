"""One-page PDFs (via headless Edge/Chrome) and the RESULTS.ipynb notebook (no Earth Engine needed)."""
import base64
import os
import re
import subprocess

from .common import ROOT

BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "/usr/bin/google-chrome", "/usr/bin/chromium"]
CSS = """
@page {{ size: A4; margin: 9mm 12mm; }}
body {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: {pt}pt; line-height: 1.28; color: #111; }}
h1 {{ font-size: {h1}pt; margin: 0 0 2pt; }}
p, ul, ol {{ margin: 3pt 0; }}  ul, ol {{ padding-left: 15pt; }}  li {{ margin: 1pt 0; }}
blockquote {{ margin: 5pt 0; padding: 5pt 8pt; background: #fff1f3; border-left: 3pt solid #ff2d55; }}
blockquote p {{ margin: 0; }}
img {{ display: block; max-width: 100%; max-height: 58mm; margin: 3pt auto; }}
code {{ font-size: {code}pt; }}
table {{ border-collapse: collapse; margin: 4pt 0; }}
th, td {{ border: 0.5pt solid #bbb; padding: 1.5pt 5pt; text-align: left; }}  th {{ background: #f3f3f3; }}
"""


def pdf(src="WRITEUP.md", pt=9.0):
    """Render a markdown file (path relative to the repo root) to a PDF next to it; returns page count."""
    import markdown
    from pypdf import PdfReader
    src_path = os.path.join(ROOT, src)
    with open(src_path, encoding="utf-8") as f:
        body = markdown.markdown(f.read(), extensions=["extra"])

    def inline(m):  # embed images so the HTML is self-contained
        with open(os.path.join(os.path.dirname(src_path), m.group(1)), "rb") as fh:
            return f'src="data:image/png;base64,{base64.b64encode(fh.read()).decode()}"'
    body = re.sub(r'src="([^"]+\.png)"', inline, body)
    css = CSS.format(pt=pt, h1=pt + 7, code=pt - 0.5)
    stem = os.path.splitext(src_path)[0]
    with open(stem + ".html", "w", encoding="utf-8") as f:
        f.write(f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>{body}</body></html>")
    browser = next(b for b in BROWSERS if os.path.exists(b))
    subprocess.run([browser, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={stem}.pdf",
                    "file:///" + (stem + ".html").replace("\\", "/")], check=True, timeout=120, capture_output=True)
    os.remove(stem + ".html")
    pages = len(PdfReader(stem + ".pdf").pages)
    print(f"{stem}.pdf: {pages} page(s) at {pt} pt")
    return pages


def pdf_fit(src="WRITEUP.md", sizes=(9.5, 9.2, 9.0, 8.8)):
    """Largest font size that keeps the document on one page."""
    for pt in sizes:
        if pdf(src, pt) == 1:
            return pt
    return None


def notebook():
    """Build and execute RESULTS.ipynb: every number in the write-up, recomputed from outputs/."""
    import nbformat
    from nbclient import NotebookClient
    md, code = nbformat.v4.new_markdown_cell, nbformat.v4.new_code_cell
    cells = [
        md("# Ghost Lakes — results and tests\n"
           "Every number in `WRITEUP.md`, recomputed from the files in `outputs/`. **No Earth Engine account needed**: "
           "this notebook only reads saved results (`python run.py --help` lists the steps that made them).\n\n"
           "1. Terrain AI: how well does it generalise?  2. Terrain AI on documented drained lakes  "
           "3. Abidjan: the sites  4. Abidjan: how good are the estimates?  5. Global screen: precision  6. Where it fails"),
        code("import json, pandas as pd\nfrom IPython.display import display\npd.set_option('display.width', 160)\n"
             "load = lambda p: json.load(open(p, encoding='utf-8'))"),
        md("## 1. Terrain AI: leave-one-region-out\nRandom Forest on 10 terrain features, trained on 6 Romanian regions, "
           "tested on the 7th. Test sets are balanced 50/50 water/dry, so these numbers are optimistic."),
        code("m = load('outputs/metrics.json')\n"
             "display(pd.DataFrame(m['leave_one_region_out']).T[['n', 'auc', 'f1', 'precision', 'recall']])\n"
             "print('mean AUC', m['mean_auc'], ' mean F1', m['mean_f1'])\n"
             "pd.Series(m['feature_importance']).plot.barh(title='Feature importance', figsize=(6, 3));"),
        md("## 2. Terrain AI on documented drained water bodies (Bucharest)\nTrained **without** any Bucharest data; "
           "sites compared with random land pixels of the city."),
        code("v = load('outputs/validation_bucuresti.json')\n"
             "display(pd.DataFrame(v['sites'])[['site', 'group', 'p_water', 'percentile']])\n"
             "print({k: v[k] for k in v if k.startswith('auc_') or k.startswith('n_')})"),
        md("**Honest reading:** on water bodies that vanished completely the terrain model is close to chance "
           "(AUC ≈ 0.57, n = 4). That is why the findings come from the satellite archive and radar, not terrain alone."),
        md("## 3. Abidjan: the sites\nLagoon water for decades (JRC ≥ 50 %), water in H1 2023, sand or buildings in 2026, "
           "and radar-confirmed."),
        code("s = pd.read_csv('outputs/abidjan/abidjan_sites.csv')\n"
             "display(s[['site', 'neighbourhood', 'area_ha', 'optical_land_from', 'radar_land_from', 'dates_agree', "
             "'people_within_500m']])\n"
             "print(f\"{len(s)} sites, {s.area_ha.sum():.1f} ha; from 2024 on: "
             "{s[s.optical_land_from >= '2024-01'].area_ha.sum():.1f} ha\")\n"
             "p = load('outputs/abidjan_population.json')['people_within_m']\n"
             "print('people within 500 m of any site:', p['500'], ' within 1 km:', p['1000'])"),
        md("![Abidjan before/after and timeline](outputs/abidjan/figure_before_after.png)\n\n"
           "![Abidjan timelapse 2023-2026](outputs/abidjan/timelapse.gif)\n\n"
           "**Visual proof, every site up close** (700 m window; 2023 H1, 2024 H2, 2025 H2, 2026): inside each red "
           "outline, dark water becomes sand.\n\n![Every site at four dates](outputs/abidjan/sites_zoom.png)"),
        md("## 4. Abidjan: how good are the estimates?"),
        code("a = load('outputs/abidjan_accuracy.json')\ninside = a['inside_polygon_ha']\n"
             "print('Area inside the polygons (ha):', inside)\n"
             "print(f\"  confirmed by reflectance rule: {inside['refl'] / inside['dw']:.0%}, by radar: "
             "{inside['radar'] / inside['dw']:.0%}, by both: {inside['both'] / inside['dw']:.0%}\")\n"
             "print('With a 20 m margin (extent):', a['totals_ha'])"),
        code("g = pd.DataFrame(a['threshold_grid'])\n"
             "display(g.pivot_table(index=['then_water', 'now_water'], columns='land', values='area_ha'))\n"
             "ok = g[g.then_water < 0.8]\n"
             "print(f'thresholds 0.6-0.7: {ok.area_ha.min():.1f} - {ok.area_ha.max():.1f} ha; 0.8 gives 0 because '\n"
             "      'Dynamic World rarely reaches P(water) >= 0.8 in this turbid lagoon')"),
        code("print('Fill dates: optical and radar agree within 3 months for', int(s.dates_agree.sum()), 'of', len(s), 'sites')\n"
             "display(s[['site', 'optical_last_water', 'optical_land_from', 'radar_last_water', 'radar_land_from', 'dates_agree']])"),
        md("Sites 8 and 10: radar still sees open water on 14 March / 7 April 2026 and land from mid-April, so they were "
           "filled **after** the minister's 11 February 2026 warning. Both sensors agree."),
        md("## 5. Global screen: precision of the 2023→2026 infill detector\n~120 cities. Every radar-confirmed patch "
           "was checked by eye (Sentinel-2 2023 vs 2026) and labelled."),
        code("lab = pd.read_csv('outputs/recent_infill/labels.csv')\n"
             "c = lab.groupby('label').agg(patches=('city', 'size'), area_ha=('area_ha', 'sum'))\n"
             "c['share_patches'] = (c.patches / c.patches.sum()).round(2)\nc['share_area'] = (c.area_ha / c.area_ha.sum()).round(2)\n"
             "display(c)\ndisplay(lab.groupby(['city', 'label', 'note']).area_ha.agg(['size', 'sum']).round(1))"),
        md("## 6. Where it fails\n| Failure | Evidence | Consequence |\n|---|---|---|\n"
           "| Terrain AI cannot see lakes that left no terrain trace | AUC 0.57 on 4 documented Bucharest sites | Only a hint; findings come from archive + radar |\n"
           "| Terrain AI top candidates in Romania were artefacts | sunken stadium pitch, excavations, quarries | No Romanian discovery claimed |\n"
           "| Moving rivers and beaches look like infill | 5 of 29 global radar-confirmed patches | Human review required; next: mask river channels and shorelines |\n"
           "| Dates uncertain for some sites | optical vs radar differ 6–20 months for 4 of 11 Abidjan sites | Reported as ranges |\n"
           "| MNDWI water index fails in this turbid, hazy lagoon | open water MNDWI ≈ -0.1…-0.2 | Replaced by a NIR/SWIR rule |\n"
           "| Cannot tell legal from illegal fill | port areas in Vridi | We never claim illegality |\n"
           "| Small fills (< 0.5 ha) not counted | design choice | 33 ha is a lower bound |"),
    ]
    nb = nbformat.v4.new_notebook(cells=cells, metadata={"kernelspec": {"name": "python3", "display_name": "Python 3"}})
    NotebookClient(nb, timeout=300, kernel_name="python3", resources={"metadata": {"path": ROOT}}).execute()
    nbformat.write(nb, os.path.join(ROOT, "RESULTS.ipynb"))
    print("RESULTS.ipynb written")
