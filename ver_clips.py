"""Una fila de 6 fotogramas por clip (por nombre/stem), para revisar a ojo."""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw
HERE = Path(__file__).parent; F = HERE / "cache" / "frames"
meta = {m["stem"]: m for m in json.loads((HERE / "cache" / "clips.json").read_text(encoding="utf-8"))}
W = 150
def row(stem):
    ims = [Image.open(F / f"{stem}_{i}.jpg") for i in range(6)]
    h = int(ims[0].height * W / ims[0].width)
    out = Image.new("RGB", (W * 6 + 64, h), (25, 25, 25))
    for i, im in enumerate(ims): out.paste(im.resize((W, h)), (64 + i * W, 0))
    ImageDraw.Draw(out).text((3, 3), f"{stem}\n{meta[stem]['duracion_s']:.0f}s", fill="white")
    return out
rows = [row(s) for s in sys.argv[2:]]
img = Image.new("RGB", (rows[0].width, sum(r.height + 2 for r in rows)), "black"); y = 0
for r in rows: img.paste(r, (0, y)); y += r.height + 2
img.save(sys.argv[1]); print(sys.argv[1], img.size)
