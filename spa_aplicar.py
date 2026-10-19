#!/usr/bin/env python3
"""
spa_aplicar.py — Paso 6: convierte unas decisiones (las iniciales, o las que descargas del HTML)
en un vídeo borrador y un XML de secuencia para Premiere.

    python spa_aplicar.py                          # usa salida/decisiones_iniciales.json
    python spa_aplicar.py "Descargas\\decisiones_spot_spa.json"

Salida en salida/:  borrador.mp4 · spot.xml · plan_borrador.json
Usa render_montage.py y export_premiere.py de esta misma carpeta.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spa_lib import CACHE, HERE, load_json, plan_from_decisions  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TOOLS = HERE   # render_montage.py y export_premiere.py viven en esta misma carpeta


def has_audio(path: str) -> bool:
    ff = shutil.which("ffprobe")
    if not ff:
        return True
    r = subprocess.run([ff, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    return bool(r.stdout.strip())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("decisiones", nargs="?", type=Path, default=HERE / "salida" / "decisiones_iniciales.json")
    ap.add_argument("--salida", type=Path, default=HERE / "salida")
    ap.add_argument("--dissolve", type=int, default=12, help="frames de cross-dissolve en el XML (0 = corte seco)")
    ap.add_argument("--sin-video", action="store_true", help="solo plan + XML, sin renderizar el borrador")
    args = ap.parse_args()

    dec = load_json(args.decisiones)
    orden = dec["orden"] if isinstance(dec, dict) else dec
    grupos = {g["id"]: g for g in load_json(CACHE / "grupos.json")["grupos"]}
    beats = load_json(CACHE / "beats.json")
    if not orden:
        sys.exit("ERROR: las decisiones no incluyen ningún plano.")

    plan = plan_from_decisions(orden, grupos, beats)
    for c in plan["clips_scanned"]:
        c["has_audio"] = has_audio(c["path"])
    args.salida.mkdir(exist_ok=True)
    plan_path = args.salida / "plan_borrador.json"
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    dur = plan["total_frames"] / plan["timeline"]["fps"]
    print(f"{plan['segment_count']} planos, {dur:.1f}s  ->  {plan_path}")

    py = sys.executable
    xml = args.salida / "spot.xml"
    r = subprocess.run([py, str(TOOLS / "export_premiere.py"), "--plan", str(plan_path), "--out", str(xml),
                        "--dissolve", str(args.dissolve)], capture_output=True, text=True)
    print(r.stdout.strip() or r.stderr.strip()[-400:])

    if not args.sin_video:
        out = args.salida / "borrador.mp4"
        r = subprocess.run([py, str(TOOLS / "render_montage.py"), "--plan", str(plan_path), "--out", str(out),
                            "--preset", "veryfast", "--crf", "22", "--dissolve", str(args.dissolve)],
                           capture_output=True, text=True)
        print("\n".join(r.stdout.strip().splitlines()[-3:]) if r.returncode == 0 else (r.stdout + r.stderr).strip()[-700:])


if __name__ == "__main__":
    main()
