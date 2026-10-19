"""Imagen con un grupo por bloque: una fila (6 fotogramas) por clip del grupo."""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw
HERE = Path(__file__).parent; F = HERE / "cache" / "frames"
G = {g["id"]: g for g in json.loads((HERE / "cache" / "grupos.json").read_text(encoding="utf-8"))["grupos"]}
W = 130
def row(c):
    ims = [Image.open(F / f"{c['stem']}_{i}.jpg") for i in range(6)]
    h = int(ims[0].height * W / ims[0].width)
    out = Image.new("RGB", (W * 6 + 90, h), (25, 25, 25))
    for i, im in enumerate(ims): out.paste(im.resize((W, h)), (90 + i * W, 0))
    ImageDraw.Draw(out).text((4, 4), f"{c['stem']}\n{c['duracion_s']:.0f}s n{c['nota']}", fill="white")
    return out
blocks = []
for gid in sys.argv[2:]:
    rows = [row(c) for c in G[gid]["clips"]]
    blk = Image.new("RGB", (rows[0].width, sum(r.height + 2 for r in rows) + 16), (60, 0, 0))
    ImageDraw.Draw(blk).text((4, 2), f"{gid}  sim={G[gid]['similitud']}", fill="yellow")
    y = 16
    for r in rows: blk.paste(r, (0, y)); y += r.height + 2
    blocks.append(blk)
img = Image.new("RGB", (blocks[0].width, sum(b.height + 6 for b in blocks)), "black"); y = 0
for b in blocks: img.paste(b, (0, y)); y += b.height + 6
img.save(sys.argv[1]); print(sys.argv[1], img.size)
