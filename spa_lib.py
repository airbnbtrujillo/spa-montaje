"""Utilidades compartidas del proyecto spa-montaje (etapas, rejilla de beats, decisiones -> plan)."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
CACHE = HERE / "cache"
FPS = 29.97  # proxies a 30000/1001

# id, título, presupuesto de duración en segundos, color
ACTOS = [
    ("entrada",      "1 · La chica llega",             8,  "#4f86f7"),
    ("ambiente",     "2 · El ambiente",               10,  "#8e6bd8"),
    ("espejo",       "3 · Frente al espejo",           8,  "#d86bb8"),
    ("pasillo",      "4 · Camina por el pasadizo",     6,  "#e0707a"),
    ("sube_camilla", "5 · Sube a la camilla",          8,  "#e39a4a"),
    ("piedras",      "6 · Piedras calientes",         10,  "#c9b038"),
    ("vapor",        "7 · Vapor",                      8,  "#5bbfa0"),
    ("mascarilla",   "8 · Mascarilla",                 8,  "#3fb0c8"),
    ("cremas",       "9 · Cremas y masaje facial",    14,  "#6fa8dc"),
    ("otros",        "10 · Otros tratamientos",        6,  "#93a0ad"),
    ("cierre",       "11 · Cierre",                    4,  "#7bc96f"),
    ("descartar",    "Descartados (no entran)",        0,  "#777777"),
]
ACTO_IDS = [a[0] for a in ACTOS]


def load_json(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8-sig"))


def carpeta_de(g: dict) -> str:
    stems = [c["stem"] for c in g["clips"]]
    label = stems[0] if len(stems) == 1 else f"{stems[0]}-{stems[-1]}"
    kind = "Tomas_repetidas" if len(stems) > 1 else "Planos_unicos"
    return f"tomas/{kind}/{g['id']}_{label}"


def plan_from_decisions(dec: list[dict], grupos: dict, beats: dict, fps: float = FPS) -> dict:
    """dec: [{plano, toma, inicio_s, beats}] en orden final -> plan compatible con render_montage.py /
    export_premiere.py (formato montage_plan.json). Los cortes caen en la rejilla de beats."""
    b = beats["beats"]
    spb = 60.0 / beats["bpm"]
    idx = 0                       # índice de beat de inicio
    t0 = b[0]
    segs, used = [], {}
    for k, d in enumerate(dec):
        g = grupos[d["plano"]]
        clip = next(c for c in g["clips"] if c["nombre"] == d["toma"])
        nb = int(d["beats"])
        end_idx = idx + nb
        if end_idx >= len(b):
            break
        a_s, z_s = b[idx] - t0, b[end_idx] - t0
        rec, dur = int(round(a_s * fps)), int(round((z_s - a_s) * fps))
        dur_s = dur / fps
        inicio = max(0.0, min(float(d["inicio_s"]), max(0.0, clip["duracion_s"] - dur_s - 0.05)))
        segs.append({"index": k, "clip": clip["ruta"], "in_frame": int(round(inicio * fps)),
                     "duration_frames": dur, "record_frame": rec, "plano": d["plano"]})
        used[clip["ruta"]] = clip
        idx = end_idx
    total = segs[-1]["record_frame"] + segs[-1]["duration_frames"] if segs else 0
    scanned = [{"path": p, "fps": fps, "duration": c["duracion_s"], "frames": int(c["duracion_s"] * fps),
                "width": 640, "height": 360, "has_audio": True} for p, c in used.items()]
    return {
        "version": 1,
        "timeline": {"name": "Spot Spa", "fps": fps, "width": 640, "height": 360},
        "music": {"path": beats["ruta"], "in_frame": int(round(t0 * fps)), "record_frame": 0,
                  "duration_frames": total},
        "bpm": beats["bpm"], "segment_count": len(segs), "total_frames": total,
        "segments": segs, "clips_scanned": scanned, "warnings": [],
    }
