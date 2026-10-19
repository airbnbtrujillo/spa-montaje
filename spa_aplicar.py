#!/usr/bin/env python3
"""
spa_aplicar.py — Convierte unas decisiones (las iniciales, o las que descargas del HTML) en entregables:

  borrador.mp4        vídeo borrador con los PROXIES (rápido), fundidos centrados en los cortes
  spot.xml            XML de secuencia con los proxies
  --originales DIR    además, con los ORIGINALES (mismo nombre que cada proxy):
  spot_final.xml        XML de secuencia a la resolución de los originales (para Premiere)
  spot_final_1080p.mp4  (con --final-mp4 1920x1080) vídeo final renderizado desde los originales

    python spa_aplicar.py decisiones.json --originales "F:\\Video Spa" --final-mp4 1920x1080
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spa_lib import CACHE, HERE, SALIDA, load_json, plan_final, plan_from_decisions  # noqa: E402

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


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def aplicar(decisiones: Path, salida: Path, dissolve: int = 12, sin_video: bool = False,
            originales: Path | None = None, final_mp4: str | None = None) -> dict:
    """Devuelve {'plan','xml','borrador','plan_final','xml_final','mp4_final'} con las rutas generadas."""
    dec = load_json(decisiones)
    orden = dec["orden"] if isinstance(dec, dict) else dec
    grupos = {g["id"]: g for g in load_json(CACHE / "grupos.json")["grupos"]}
    beats = load_json(CACHE / "beats.json")
    if not orden:
        sys.exit("ERROR: las decisiones no incluyen ningún plano.")
    out: dict = {}

    plan = plan_from_decisions(orden, grupos, beats)
    for c in plan["clips_scanned"]:
        c["has_audio"] = has_audio(c["path"])
    salida.mkdir(parents=True, exist_ok=True)
    plan_path = salida / "plan_borrador.json"
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    out["plan"] = plan_path
    out["duracion_s"] = plan["total_frames"] / plan["timeline"]["fps"]
    out["planos"] = plan["segment_count"]
    print(f"{plan['segment_count']} planos, {out['duracion_s']:.1f}s  ->  {plan_path.name}")

    py = sys.executable
    xml = salida / "spot.xml"
    r = _run([py, str(TOOLS / "export_premiere.py"), "--plan", str(plan_path), "--out", str(xml),
              "--dissolve", str(dissolve)])
    print(r.stdout.strip().splitlines()[0] if r.stdout.strip() else r.stderr.strip()[-400:])
    out["xml"] = xml

    if not sin_video:
        mp4 = salida / "borrador.mp4"
        r = _run([py, str(TOOLS / "render_montage.py"), "--plan", str(plan_path), "--out", str(mp4),
                  "--preset", "veryfast", "--crf", "22", "--dissolve", str(dissolve)])
        print("\n".join(r.stdout.strip().splitlines()[-2:]) if r.returncode == 0 else (r.stdout + r.stderr).strip()[-700:])
        if r.returncode == 0:
            out["borrador"] = mp4

    if originales:
        try:
            pf = plan_final(plan, originales)
        except (FileNotFoundError, ValueError) as e:
            sys.exit(f"ERROR con los originales: {e}")
        pf_path = salida / "plan_final.json"
        pf_path.write_text(json.dumps(pf, indent=2, ensure_ascii=False), encoding="utf-8")
        out["plan_final"] = pf_path
        tl = pf["timeline"]
        print(f"originales OK: {len(pf['clips_scanned'])} clips, secuencia {tl['width']}x{tl['height']} @ {tl['fps']}")
        xml_f = salida / "spot_final.xml"
        r = _run([py, str(TOOLS / "export_premiere.py"), "--plan", str(pf_path), "--out", str(xml_f),
                  "--dissolve", str(dissolve)])
        print(r.stdout.strip().splitlines()[0] if r.stdout.strip() else r.stderr.strip()[-400:])
        out["xml_final"] = xml_f
        if final_mp4 and not sin_video:
            mp4f = salida / f"spot_final_{final_mp4.split('x')[1]}p.mp4"
            print(f"renderizando el vídeo final {final_mp4} desde los originales (tarda unos minutos)...", flush=True)
            r = _run([py, str(TOOLS / "render_montage.py"), "--plan", str(pf_path), "--out", str(mp4f),
                      "--size", final_mp4, "--preset", "medium", "--crf", "18", "--dissolve", str(dissolve)])
            print("\n".join(r.stdout.strip().splitlines()[-2:]) if r.returncode == 0 else (r.stdout + r.stderr).strip()[-700:])
            if r.returncode == 0:
                out["mp4_final"] = mp4f
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("decisiones", nargs="?", type=Path, default=SALIDA / "decisiones_iniciales.json")
    ap.add_argument("--salida", type=Path, default=SALIDA)
    ap.add_argument("--dissolve", type=int, default=12, help="frames de cross-dissolve (0 = corte seco)")
    ap.add_argument("--sin-video", action="store_true", help="solo planes + XML, sin renderizar vídeos")
    ap.add_argument("--originales", type=Path, help="carpeta con los originales (mismo nombre que los proxies)")
    ap.add_argument("--final-mp4", metavar="WxH", help="renderiza también un mp4 desde los originales, p.ej. 1920x1080")
    a = ap.parse_args()
    aplicar(a.decisiones, a.salida, a.dissolve, a.sin_video, a.originales, a.final_mp4)


if __name__ == "__main__":
    main()
