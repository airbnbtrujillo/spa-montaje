"""Utilidades compartidas del proyecto spa-montaje (etapas, rejilla de beats, decisiones -> plan)."""
from __future__ import annotations

import json
import os
from pathlib import Path

HERE = Path(__file__).parent                              # carpeta del código
BASE = Path(os.environ.get("SPA_PROYECTO") or HERE)       # carpeta de trabajo del proyecto (un rodaje)
CACHE = BASE / "cache"
SALIDA = BASE / "salida"
TOMAS = BASE / "tomas"
DECISIONES = BASE / "decisiones"
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
        # límites redondeados una sola vez: el final de un plano es exactamente el inicio del siguiente
        rec, fin = int(round(a_s * fps)), int(round(z_s * fps))
        dur = fin - rec
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


def probe_video(path) -> dict:
    """Ancho, alto, fps, nº de fotogramas, duración y audio de un vídeo (ffprobe)."""
    import shutil
    import subprocess
    ff = shutil.which("ffprobe")
    if not ff:
        raise RuntimeError("falta ffprobe en el PATH")
    r = subprocess.run([ff, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
                       capture_output=True, text=True)
    d = json.loads(r.stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    n, den = v["r_frame_rate"].split("/")
    fps_exacto = float(n) / float(den)
    dur = float(v.get("duration") or d["format"]["duration"])
    frames = int(v["nb_frames"]) if str(v.get("nb_frames", "")).isdigit() else int(round(dur * fps_exacto))
    return {"width": int(v["width"]), "height": int(v["height"]), "fps": round(fps_exacto, 3),
            "frames": frames, "duration": dur, "has_audio": any(s["codec_type"] == "audio" for s in d["streams"])}


def plan_final(plan: dict, orig_dir) -> dict:
    """Mismo plan pero apuntando a los ORIGINALES (mismo nombre que cada proxy). Comprueba que cada
    original tenga los mismos fps y fotogramas suficientes para el corte; la secuencia toma su resolución."""
    import copy
    from collections import Counter
    from pathlib import Path
    orig_dir = Path(orig_dir)
    p = copy.deepcopy(plan)
    fps = float(p["timeline"]["fps"])
    info: dict[str, dict] = {}
    for seg in p["segments"]:
        proxy = Path(seg["clip"])
        ruta = orig_dir / proxy.name
        if not ruta.is_file():
            raise FileNotFoundError(f"no existe el original de {proxy.name}: {ruta}")
        i = info.get(proxy.name) or info.setdefault(proxy.name, probe_video(ruta))
        if abs(i["fps"] - fps) > 0.01:
            raise ValueError(f"{proxy.name}: el original va a {i['fps']} fps y la secuencia a {fps}")
        if seg["in_frame"] + seg["duration_frames"] > i["frames"]:
            raise ValueError(f"{proxy.name}: el corte pide hasta el fotograma "
                             f"{seg['in_frame'] + seg['duration_frames']} y el original solo tiene {i['frames']}")
        seg["clip_proxy"] = str(proxy)
        seg["clip"] = str(ruta)
    p["clips_scanned"] = [{"path": str(orig_dir / n), "fps": i["fps"], "duration": i["duration"],
                           "frames": i["frames"], "width": i["width"], "height": i["height"],
                           "has_audio": i["has_audio"]} for n, i in info.items()]
    w, h = Counter((i["width"], i["height"]) for i in info.values()).most_common(1)[0][0]
    p["timeline"].update({"width": w, "height": h})
    return p


def ultima_decision():
    """Las decisiones más recientes del proyecto (la última descargada del HTML) o, si no hay, las iniciales."""
    candidatos = sorted(DECISIONES.glob("*.json"), key=lambda p: p.stat().st_mtime) if DECISIONES.is_dir() else []
    return candidatos[-1] if candidatos else SALIDA / "decisiones_iniciales.json"
