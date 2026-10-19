#!/usr/bin/env python3
"""
spa_agrupar.py — Paso 2: junta los clips que son el mismo plano (tomas repetidas).

Usa las huellas CLIP de spa_extraer.py. La similitud entre dos clips es la media simétrica de
"cada fotograma busca su mejor pareja en el otro clip". Dos clips son la misma toma si:
  - su similitud media (enlace promedio del grupo) >= --umbral, y
  - todo el grupo cabe en --ventana posiciones del orden de rodaje (las repeticiones se graban seguidas).

Para cada grupo propone un clip "por defecto" (no puede saber cuál es la mejor toma: usa la nota
del análisis y, a igualdad, la última, que en rodaje suele ser la buena). Se corrige luego en el HTML.

Salida: cache/grupos.json  y, con --carpetas, copias de los proxies en tomas/<grupo>/.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).parent


def sim_matrix(E: np.ndarray) -> np.ndarray:
    n = E.shape[0]
    M = np.zeros((n, n), dtype=np.float32)
    for i in range(n):
        for j in range(i, n):
            S = E[i] @ E[j].T
            M[i, j] = M[j, i] = 0.5 * (S.max(1).mean() + S.max(0).mean())
    return M


def cluster(M: np.ndarray, thr: float, span: int) -> list[list[int]]:
    groups = [[i] for i in range(M.shape[0])]
    while True:
        best, pair = thr, None
        for a in range(len(groups)):
            for b in range(a + 1, len(groups)):
                ids = groups[a] + groups[b]
                if max(ids) - min(ids) > span:
                    continue
                avg = float(np.mean([M[i, j] for i in groups[a] for j in groups[b]]))
                if avg >= best:
                    best, pair = avg, (a, b)
        if pair is None:
            return sorted((sorted(g) for g in groups), key=lambda g: g[0])
        a, b = pair
        groups[a] = groups[a] + groups[b]
        del groups[b]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, default=HERE / "cache")
    ap.add_argument("--umbral", type=float, default=0.91)
    ap.add_argument("--ventana", type=int, default=4, help="separación máxima entre clips de un grupo")
    ap.add_argument("--analisis", type=Path,
                    default=Path(r"C:\Claude\beat-montage\footage_spa\footage_log.json"),
                    help="footage_log.json de analyze_footage.py (notas y descripciones)")
    ap.add_argument("--carpetas", action="store_true", help="copiar proxies a tomas/<grupo>/")
    ap.add_argument("--salida-carpetas", type=Path, default=HERE / "tomas")
    args = ap.parse_args()

    meta = json.loads((args.cache / "clips.json").read_text(encoding="utf-8"))
    E = np.load(args.cache / "embeds.npz")["emb"]
    info = {}
    if args.analisis.is_file():
        for c in json.loads(args.analisis.read_text(encoding="utf-8"))["clips"]:
            info[c["nombre"]] = c

    M = sim_matrix(E)
    np.save(args.cache / "sim.npy", M)
    groups = cluster(M, args.umbral, args.ventana)

    out = []
    for gi, g in enumerate(groups, 1):
        members = []
        for i in g:
            m = meta[i]
            a = info.get(m["nombre"], {})
            members.append({
                "nombre": m["nombre"], "stem": m["stem"], "ruta": m["ruta"],
                "duracion_s": m["duracion_s"], "indice": m["indice"],
                "nota": a.get("puntuacion_promo", 0), "resumen": a.get("resumen", ""),
                "frames": m["frames"],
            })
        # clip por defecto: mejor nota; a igualdad, el último (en rodaje la buena suele ser la última)
        usable = [m for m in members if m["duracion_s"] >= 1.5] or members
        rep = max(usable, key=lambda m: (m["nota"], m["indice"]))
        sim_media = None
        if len(g) > 1:
            sim_media = round(float(np.mean([M[i, j] for a_ in g for i in [a_] for j in g if j > i])), 3)
        out.append({"id": f"T{gi:03d}", "clips": members, "defecto": rep["nombre"], "similitud": sim_media})

    (args.cache / "grupos.json").write_text(json.dumps(
        {"umbral": args.umbral, "ventana": args.ventana, "grupos": out}, indent=2, ensure_ascii=False),
        encoding="utf-8")

    multi = [g for g in out if len(g["clips"]) > 1]
    print(f"{len(meta)} clips -> {len(out)} planos distintos "
          f"({len(multi)} con tomas repetidas, {len(meta) - len(out)} clips agrupados)")
    for g in multi:
        print(f"  {g['id']}  {' + '.join(c['stem'] for c in g['clips']):44s} sim={g['similitud']}  "
              f"-> {g['defecto'][:5]}")

    if args.carpetas:
        dst = args.salida_carpetas
        if dst.exists():
            shutil.rmtree(dst)
        for g in out:
            stems = [c["stem"] for c in g["clips"]]
            label = stems[0] if len(stems) == 1 else f"{stems[0]}-{stems[-1]}"
            folder = dst / ("Tomas_repetidas" if len(stems) > 1 else "Planos_unicos") / f"{g['id']}_{label}"
            folder.mkdir(parents=True, exist_ok=True)
            for c in g["clips"]:
                shutil.copy2(c["ruta"], folder / c["nombre"])
        print(f"\nCarpetas en {dst}")


if __name__ == "__main__":
    main()
