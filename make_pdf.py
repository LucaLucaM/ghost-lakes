"""Render WRITEUP.md to a one-page A4 PDF (WRITEUP.pdf) using a headless Edge/Chrome.

Run:  python make_pdf.py [font_pt]
"""
import base64
import os
import re
import subprocess
import sys

import markdown
from pypdf import PdfReader

HERE = os.path.dirname(os.path.abspath(__file__))
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"]


def build_html(font_pt):
    with open(os.path.join(HERE, "WRITEUP.md"), encoding="utf-8") as f:
        md = f.read()
    body = markdown.markdown(md, extensions=["extra"])

    def inline(m):  # embed images so the HTML is self-contained
        src = m.group(1)
        with open(os.path.join(HERE, src), "rb") as fh:
            data = base64.b64encode(fh.read()).decode()
        return f'src="data:image/png;base64,{data}"'
    body = re.sub(r'src="([^"]+\.png)"', inline, body)
    css = f"""
    @page {{ size: A4; margin: 10mm 13mm; }}
    body {{ font-family: 'Segoe UI', Arial, sans-serif; font-size: {font_pt}pt; line-height: 1.28; color: #111; }}
    h1 {{ font-size: {font_pt + 7}pt; margin: 0 0 2pt; }}
    p, ul, ol {{ margin: 3pt 0; }}
    ul, ol {{ padding-left: 15pt; }}
    li {{ margin: 1pt 0; }}
    blockquote {{ margin: 5pt 0; padding: 5pt 8pt; background: #fff1f3; border-left: 3pt solid #ff2d55; }}
    blockquote p {{ margin: 0; }}
    img {{ display: block; max-width: 100%; max-height: 74mm; margin: 3pt auto; }}
    code {{ font-size: {font_pt - 0.5}pt; }}
    """
    return f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>{body}</body></html>"


def main(font_pt=9.0):
    font_pt = float(font_pt)
    html_path = os.path.join(HERE, "WRITEUP.html")
    pdf_path = os.path.join(HERE, "WRITEUP.pdf")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(font_pt))
    browser = next(b for b in BROWSERS if os.path.exists(b))
    subprocess.run([browser, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf_path}", "file:///" + html_path.replace("\\", "/")],
                   check=True, timeout=120, capture_output=True)
    pages = len(PdfReader(pdf_path).pages)
    print(f"{pdf_path}: {pages} page(s) at {font_pt} pt")
    return pages


if __name__ == "__main__":
    main(*sys.argv[1:2])
