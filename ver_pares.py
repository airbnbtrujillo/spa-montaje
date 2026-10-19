"""Compone una imagen con pares de clips (6 fotogramas cada uno) para revisar a ojo."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw
F = Path(__file__).with_name("cache") / "frames"
def strip(stem, w=150):
    ims = [Image.open(F / f"{stem}_{i}.jpg") for i in range(6)]
    h = int(ims[0].height * w / ims[0].width)
    out = Image.new("RGB", (w * 6, h), "black")
    for i, im in enumerate(ims): out.paste(im.resize((w, h)), (i * w, 0))
    return out
pairs = [p.split("~") for p in sys.argv[2:]]
rows = []
for a, b in pairs:
    sa, sb = strip(a), strip(b)
    blk = Image.new("RGB", (sa.width + 70, sa.height * 2 + 6), (30, 30, 30))
    blk.paste(sa, (70, 0)); blk.paste(sb, (70, sa.height + 6))
    d = ImageDraw.Draw(blk); d.text((4, 4), a, fill="white"); d.text((4, sa.height + 10), b, fill="white")
    rows.append(blk)
H = sum(r.height + 8 for r in rows)
img = Image.new("RGB", (rows[0].width, H), (0, 0, 0)); y = 0
for r in rows: img.paste(r, (0, y)); y += r.height + 8
img.save(sys.argv[1]); print(sys.argv[1], img.size)
