#!/usr/bin/env python3
"""
render_montage.py — Renderiza montage_plan.json a un .mp4 con ffmpeg. Sin DaVinci Resolve.

    python render_montage.py                 # usa montage_plan.json -> montage.mp4
    python render_montage.py --size 1080x1920 --fade 0.08

Cada corte se recorta del clip de origen, se escala/rellena al formato de la timeline
y se une; luego se añade la música (con fundido de salida). Cortes secos por defecto.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def tool(name: str) -> str:
    p = shutil.which(name)
    if not p:
        sys.exit(f"ERROR: falta '{name}' en el PATH.")
    return p


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", type=Path, default=Path(__file__).with_name("montage_plan.json"))
    ap.add_argument("--out", type=Path, default=Path(__file__).with_name("montage.mp4"))
    ap.add_argument("--size", help="forzar WxH, p.ej. 1080x1920")
    ap.add_argument("--fps", type=float, default=0.0, help="forzar fps de salida")
    ap.add_argument("--crf", type=int, default=18, help="calidad H.264 (menor = mejor, 18-23)")
    ap.add_argument("--preset", default="medium")
    ap.add_argument("--fade", type=float, default=0.0, help="crossfade entre cortes en s (0 = corte seco)")
    ap.add_argument("--music-gain", type=float, default=0.0, help="ganancia de música en dB")
    ap.add_argument("--keep-temp", action="store_true")
    args = ap.parse_args()

    ffmpeg = tool("ffmpeg")
    if not args.plan.is_file():
        sys.exit(f"ERROR: no existe {args.plan}. Ejecuta antes plan_montage.py")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))

    tl = plan["timeline"]
    fps = args.fps or float(tl["fps"])
    if args.size:
        W, H = (int(x) for x in args.size.lower().split("x"))
    else:
        W, H = int(tl["width"]), int(tl["height"])
    W -= W % 2
    H -= H % 2
    segs = plan["segments"]
    music = plan["music"]
    total_s = plan["total_frames"] / float(tl["fps"])

    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={fps},format=yuv420p")

    print(f"{len(segs)} cortes -> {W}x{H} @ {fps} fps, {total_s:.1f}s")
    tmp = Path(tempfile.mkdtemp(prefix="render_"))
    try:
        parts: list[Path] = []
        for i, s in enumerate(segs):
            src = Path(s["clip"])
            in_s = s["in_frame"] / float(tl["fps"])
            dur = s["duration_frames"] / float(tl["fps"])
            dst = tmp / f"seg_{i:04d}.mp4"
            # seek rápido antes de -i, ajuste fino después = exacto y ágil
            pre = max(0.0, in_s - 1.5)
            fine = in_s - pre
            r = run([ffmpeg, "-y", "-v", "error", "-ss", f"{pre:.3f}", "-i", str(src),
                     "-ss", f"{fine:.3f}", "-t", f"{dur:.3f}", "-an", "-vf", vf,
                     "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
                     "-video_track_timescale", "90000", str(dst)])
            if r.returncode != 0 or not dst.is_file():
                print(f"  ! corte {i} falló: {r.stderr.strip()[-300:]}")
                continue
            parts.append(dst)
            print(f"  {i + 1:>3}/{len(segs)}  {src.name[:40]:40s} {dur:4.2f}s")

        if not parts:
            sys.exit("ERROR: no se renderizó ningún corte.")

        silent = tmp / "silent.mp4"
        if args.fade > 0 and len(parts) > 1:
            # xfade encadenado
            inputs: list[str] = []
            for p in parts:
                inputs += ["-i", str(p)]
            fc, prev, offset = [], "0:v", 0.0
            durs = [s["duration_frames"] / float(tl["fps"]) for s in segs][:len(parts)]
            for idx in range(1, len(parts)):
                offset += durs[idx - 1] - args.fade
                lbl = f"x{idx}"
                fc.append(f"[{prev}][{idx}:v]xfade=transition=fade:duration={args.fade}:"
                          f"offset={max(0.0, offset):.3f}[{lbl}]")
                prev = lbl
            r = run([ffmpeg, "-y", "-v", "error", *inputs, "-filter_complex", ";".join(fc),
                     "-map", f"[{prev}]", "-c:v", "libx264", "-preset", args.preset,
                     "-crf", str(args.crf), str(silent)])
            if r.returncode != 0:
                print(f"  ! crossfade falló, usando cortes secos: {r.stderr.strip()[-200:]}")
                args.fade = 0
        if args.fade <= 0 or not silent.is_file():
            lst = tmp / "list.txt"
            lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
            run([ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                 "-c", "copy", str(silent)])

        m_in = music["in_frame"] / float(tl["fps"])
        af = (f"volume={args.music_gain}dB," if args.music_gain else "") + \
             f"afade=t=out:st={max(0.0, total_s - 1.0):.2f}:d=1.0"
        r = run([ffmpeg, "-y", "-v", "error", "-i", str(silent),
                 "-ss", f"{m_in:.3f}", "-i", music["path"], "-t", f"{total_s:.3f}",
                 "-map", "0:v:0", "-map", "1:a:0", "-af", af,
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                 "-movflags", "+faststart", str(args.out)])
        if r.returncode != 0:
            sys.exit(f"ERROR al mezclar audio: {r.stderr.strip()[-400:]}")
    finally:
        if args.keep_temp:
            print(f"temp: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)

    mb = args.out.stat().st_size / 1e6
    print(f"\nOK -> {args.out}  ({total_s:.1f}s, {W}x{H} @ {fps}, {mb:.1f} MB)")


if __name__ == "__main__":
    main()
