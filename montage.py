"""Put <id>_old.png / <id>_new.png chips side by side with labels: python montage.py chips_dir out.png [ids...]"""
import os
import sys

from PIL import Image, ImageDraw


def main(d, out, ids=None):
    if not ids:
        ids = sorted({f.rsplit("_", 1)[0] for f in os.listdir(d) if f.endswith("_new.png")})
    S, pad = 256, 18
    cols = 2
    per_row = 2  # sites per row
    rows = (len(ids) + per_row - 1) // per_row
    W = per_row * (cols * S + 10)
    H = rows * (S + pad)
    sheet = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(sheet)
    for i, sid in enumerate(ids):
        r, c = divmod(i, per_row)
        x0, y0 = c * (cols * S + 10), r * (S + pad)
        dr.text((x0 + 2, y0 + 2), f"{sid}  (old Landsat | new Sentinel-2)", fill="black")
        for j, kind in enumerate(["old", "new"]):
            p = os.path.join(d, f"{sid}_{kind}.png")
            if os.path.exists(p):
                im = Image.open(p).convert("RGB").resize((S, S))
                sheet.paste(im, (x0 + j * S, y0 + pad))
    sheet.save(out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
