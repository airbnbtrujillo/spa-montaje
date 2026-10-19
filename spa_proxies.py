#!/usr/bin/env python3
"""
spa_proxies.py — Crea los proxies de los originales: mismo nombre, 640x360, mismos fps y mismo nº de fotogramas.

    python spa_proxies.py --originales "F:\\Video Spa"                  # -> F:\\Video Spa\\Proxies
    python spa_proxies.py --originales "F:\\Video Spa" --verificar      # solo comprueba los existentes

Un proxy que ya existe se conserva si tiene exactamente los mismos fotogramas que su original;
si no, se vuelve a crear. Decodifica con la GPU (CUDA) si puede y, si falla, con la CPU.
Premiere los puede adjuntar a los originales (Attach Proxies) porque coinciden en nombre, fps y duración.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spa_lib import probe_video  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VIDEO_EXTS = {".mp4", ".mov", ".mxf", ".m4v"}


def canales_audio(path: Path) -> int:
    ff = shutil.which("ffprobe")
    r = subprocess.run([ff, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=channels",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return int(r.stdout.strip())
    except ValueError:
        return 0


def codificar(orig: Path, dst: Path, w: int, h: int, gpu: bool) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    ch = canales_audio(orig)
    cmd = [ffmpeg, "-y", "-v", "error"]
    if gpu:
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-i", str(orig), "-map", "0:v:0", "-vf", f"scale={w}:{h}:flags=bicubic,format=yuv420p",
            "-fps_mode", "passthrough", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24"]
    if ch:
        cmd += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "128k", "-ac", str(ch)]
    cmd += ["-movflags", "+faststart", str(dst)]
    tmp = dst.with_suffix(".tmp.mp4")
    cmd[-1] = str(tmp)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(dst)
    return True


def crear_proxies(originales: Path, proxies: Path | None = None, size: str = "640x360",
                  forzar: bool = False, solo_verificar: bool = False, log=print) -> dict:
    """Devuelve {'total','creados','conservados','con_problemas':[...], 'carpeta'}."""
    proxies = proxies or originales / "Proxies"
    w, h = (int(x) for x in size.lower().split("x"))
    origs = sorted(p for p in originales.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS)
    if not origs:
        sys.exit(f"ERROR: no hay vídeos en {originales}")
    if not solo_verificar:
        proxies.mkdir(parents=True, exist_ok=True)
    res = {"total": len(origs), "creados": 0, "conservados": 0, "con_problemas": [], "carpeta": proxies}
    for i, o in enumerate(origs, 1):
        dst = proxies / o.name
        po = probe_video(o)
        if dst.is_file() and not forzar:
            pp = probe_video(dst)
            if pp["frames"] == po["frames"] and abs(pp["fps"] - po["fps"]) < 0.01:
                res["conservados"] += 1
                continue
            log(f"  {o.name}: el proxy existente no coincide ({pp['frames']} vs {po['frames']} fotogramas)")
            if solo_verificar:
                res["con_problemas"].append(o.name)
                continue
        elif solo_verificar:
            res["con_problemas"].append(o.name)
            log(f"  {o.name}: sin proxy")
            continue
        ok = codificar(o, dst, w, h, gpu=True) or codificar(o, dst, w, h, gpu=False)
        if ok:
            pp = probe_video(dst)
            if pp["frames"] != po["frames"]:
                log(f"  ! {o.name}: {pp['frames']} fotogramas (el original tiene {po['frames']})")
                res["con_problemas"].append(o.name)
            res["creados"] += 1
        else:
            log(f"  ! {o.name}: no se pudo crear el proxy")
            res["con_problemas"].append(o.name)
        if i % 10 == 0 or i == len(origs):
            log(f"  proxies: {i}/{len(origs)}")
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--originales", type=Path, required=True)
    ap.add_argument("--proxies", type=Path)
    ap.add_argument("--size", default="640x360")
    ap.add_argument("--forzar", action="store_true", help="rehacer aunque ya existan")
    ap.add_argument("--verificar", action="store_true", help="solo comprobar, no crear nada")
    a = ap.parse_args()
    r = crear_proxies(a.originales, a.proxies, a.size, a.forzar, a.verificar)
    print(f"\n{r['total']} originales | creados {r['creados']} | conservados {r['conservados']} | "
          f"con problemas {len(r['con_problemas'])}  -> {r['carpeta']}")
    sys.exit(1 if r["con_problemas"] else 0)


if __name__ == "__main__":
    main()
