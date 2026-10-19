#!/usr/bin/env python3
"""
render_montage.py — Renderiza un plan (montage_plan.json) a un .mp4 con ffmpeg. Sin Premiere ni Resolve.

    python render_montage.py                       # cortes secos
    python render_montage.py --dissolve 12         # fundido de 12 fotogramas centrado en cada corte

Cada plano se recorta del clip de origen, se escala/rellena al formato de la timeline y se une;
luego se añade la música (volumen normalizado y fundidos de entrada/salida).

Con --dissolve el fundido queda CENTRADO en el corte (como el XML para Premiere): los dos clips se
alargan media transición hacia el corte, así la duración total y los cortes sobre los beats no cambian.
Solo hay fundido donde ambos clips tienen material de sobra; en el resto el corte es seco.
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
    ap.add_argument("--dissolve", type=int, default=0, metavar="F",
                    help="fotogramas de fundido centrado en cada corte (0 = corte seco)")
    ap.add_argument("--music-gain", type=float, default=0.0, help="ganancia extra de la música en dB")
    ap.add_argument("--keep-temp", action="store_true")
    args = ap.parse_args()

    ffmpeg = tool("ffmpeg")
    if not args.plan.is_file():
        sys.exit(f"ERROR: no existe {args.plan}.")
    plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))

    tl = plan["timeline"]
    tfps = float(tl["fps"])                      # fps con los que se calcularon los fotogramas del plan
    fps = args.fps or tfps
    W, H = (int(x) for x in args.size.lower().split("x")) if args.size else (int(tl["width"]), int(tl["height"]))
    W -= W % 2
    H -= H % 2
    segs = plan["segments"]
    n = len(segs)
    music = plan["music"]
    total_s = plan["total_frames"] / tfps
    frames_of = {c["path"]: c["frames"] for c in plan.get("clips_scanned", [])}

    # ---- fundidos: solo donde ambos clips tienen material de sobra a cada lado del corte ----
    D = max(0, args.dissolve)
    mitad_a, mitad_b = D // 2, D - D // 2
    trans = [False] * max(0, n - 1)
    if D:
        for k in range(n - 1):
            a, b = segs[k], segs[k + 1]
            trans[k] = (a["in_frame"] + a["duration_frames"] + mitad_a <= frames_of.get(a["clip"], 10 ** 9)
                        and b["in_frame"] - mitad_b >= 0)

    vf = (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
          f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps={fps},format=yuv420p")
    print(f"{n} cortes -> {W}x{H} @ {fps} fps, {total_s:.1f}s, fundidos: {sum(trans)} de {max(0, n - 1)} cortes")

    tmp = Path(tempfile.mkdtemp(prefix="render_"))
    try:
        parts: list[Path] = []
        lens: list[int] = []
        for i, s in enumerate(segs):
            head = mitad_b if (i > 0 and trans[i - 1]) else 0
            tail = mitad_a if (i < n - 1 and trans[i]) else 0
            ini = s["in_frame"] - head
            nfr = head + s["duration_frames"] + tail
            in_s = ini / tfps
            dst = tmp / f"seg_{i:04d}.mp4"
            pre = max(0.0, in_s - 1.5)               # seek rápido antes de -i, ajuste fino después
            r = run([ffmpeg, "-y", "-v", "error", "-ss", f"{pre:.3f}", "-i", str(s["clip"]),
                     "-ss", f"{in_s - pre:.3f}", "-frames:v", str(nfr), "-an", "-vf", vf,
                     "-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
                     "-video_track_timescale", "90000", str(dst)])
            if r.returncode != 0 or not dst.is_file():
                sys.exit(f"ERROR: el plano {i + 1} falló: {r.stderr.strip()[-300:]}")
            parts.append(dst)
            lens.append(nfr)
            print(f"  {i + 1:>3}/{n}  {Path(s['clip']).name[:30]:30s} {nfr / tfps:5.2f}s"
                  + (f"  (+{head}/{tail} f de fundido)" if head or tail else ""))

        silent = tmp / "silent.mp4"
        if any(trans):
            inputs: list[str] = []
            for p in parts:
                inputs += ["-i", str(p)]
            # xfade y concat exigen la misma base de tiempo: se normaliza cada entrada y cada resultado
            fc = [f"[{k}:v]settb=AVTB,setpts=PTS-STARTPTS[s{k}]" for k in range(n)]
            prev, acc = "s0", lens[0]
            for k in range(1, n):
                lbl = f"v{k}"
                if trans[k - 1]:
                    fc.append(f"[{prev}][s{k}]xfade=transition=fade:duration={D / tfps:.5f}:"
                              f"offset={(acc - D) / tfps:.5f},settb=AVTB[{lbl}]")
                    acc += lens[k] - D
                else:
                    fc.append(f"[{prev}][s{k}]concat=n=2:v=1:a=0,settb=AVTB,setpts=PTS-STARTPTS[{lbl}]")
                    acc += lens[k]
                prev = lbl
            r = run([ffmpeg, "-y", "-v", "error", *inputs, "-filter_complex", ";".join(fc),
                     "-map", f"[{prev}]", "-c:v", "libx264", "-preset", args.preset,
                     "-crf", str(args.crf), "-pix_fmt", "yuv420p", str(silent)])
            if r.returncode != 0:
                print("filtergraph:", ";".join(fc)[:600])
                sys.exit("ERROR al encadenar los fundidos: " + r.stderr.strip()[:900])
            print(f"  duración tras los fundidos: {acc / tfps:.2f}s (esperada {total_s:.2f}s)")
        else:
            lst = tmp / "list.txt"
            lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
            run([ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                 "-c", "copy", str(silent)])

        m_in = music["in_frame"] / tfps
        af = ((f"volume={args.music_gain}dB," if args.music_gain else "") +
              f"loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=in:st=0:d=0.4,"
              f"afade=t=out:st={max(0.0, total_s - 1.5):.2f}:d=1.5")
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
