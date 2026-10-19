#!/usr/bin/env python3
"""
export_premiere.py — Convierte montage_plan.json en un XML de secuencia (FCP7 / xmeml v5)
que abre directo en Adobe Premiere Pro, DaVinci Resolve o Final Cut.

    python export_premiere.py                 # -> montage.xml
    python export_premiere.py --dissolve 8    # cross-dissolve de 8 frames en cada corte

Importar:
  Premiere : File > Import > montage.xml   (crea una secuencia con los cortes ya al ritmo)
  Resolve  : File > Import > Timeline > Pre-conformed / AAF EDL XML...
Los clips quedan "sin conectar" si Premiere no encuentra las rutas: click derecho > Link Media.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def pathurl(p: str) -> str:
    return "file://localhost/" + urllib.parse.quote(str(Path(p)).replace("\\", "/"))


def probe_audio_rate(path: str) -> int:
    try:
        import shutil
        ff = shutil.which("ffprobe")
        if ff:
            out = subprocess.run([ff, "-v", "error", "-select_streams", "a:0",
                                  "-show_entries", "stream=sample_rate", "-of", "csv=p=0", path],
                                 capture_output=True, text=True, timeout=15)
            return int(out.stdout.strip() or 48000)
    except Exception:
        pass
    return 48000


def rate_xml(tb: int = 30, ntsc: str = "TRUE") -> str:
    return f"<rate><timebase>{tb}</timebase><ntsc>{ntsc}</ntsc></rate>"


def file_def(fid: str, path: str, frames: int, w: int, h: int,
             audio_rate: int, has_audio: bool) -> str:
    name = escape(Path(path).name)
    audio = ""
    if has_audio:
        audio = (f"<audio><samplecharacteristics><depth>16</depth>"
                 f"<samplerate>{audio_rate}</samplerate></samplecharacteristics>"
                 f"<channelcount>2</channelcount></audio>")
    return (
        f'<file id="{fid}"><name>{name}</name>'
        f"<pathurl>{pathurl(path)}</pathurl>{rate_xml()}<duration>{frames}</duration>"
        f"<media><video><samplecharacteristics>{rate_xml()}"
        f"<width>{w}</width><height>{h}</height></samplecharacteristics></video>{audio}</media></file>"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", type=Path, default=Path(__file__).with_name("montage_plan.json"))
    ap.add_argument("--out", type=Path, default=Path(__file__).with_name("montage.xml"))
    ap.add_argument("--dissolve", type=int, default=0, metavar="F",
                    help="frames de cross-dissolve en cada corte (0 = corte seco)")
    args = ap.parse_args()

    plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
    tl = plan["timeline"]
    W, H = int(tl["width"]), int(tl["height"])
    total = int(plan["total_frames"])
    segs = plan["segments"]
    music = plan["music"]

    by_path = {c["path"]: c for c in plan["clips_scanned"]}
    used = []
    for s in segs:
        if s["clip"] not in used:
            used.append(s["clip"])
    file_ids = {p: f"file-{i+1}" for i, p in enumerate(used)}
    music_arate = probe_audio_rate(music["path"])

    defined: set[str] = set()
    dis = max(0, args.dissolve)

    # ---- video track ----
    v_items = []
    for k, s in enumerate(segs):
        p = s["clip"]
        info = by_path[p]
        fid = file_ids[p]
        src_in = int(s["in_frame"])
        dur = int(s["duration_frames"])
        rec = int(s["record_frame"])
        # extiende para solapar la transición (si cabe en el material de origen)
        head = dis // 2 if (k > 0 and dis) else 0
        tail = (dis - dis // 2) if (k < len(segs) - 1 and dis) else 0
        if src_in - head < 0:
            head = 0
        if src_in + dur + tail > info["frames"]:
            tail = max(0, info["frames"] - src_in - dur)
        s_in, s_out = src_in - head, src_in + dur + tail
        t_start, t_end = rec - head, rec + dur + tail
        fdef = file_def(fid, p, info["frames"], info["width"], info["height"],
                        music_arate, info["has_audio"]) if fid not in defined else f'<file id="{fid}"/>'
        defined.add(fid)
        v_items.append(
            f'<clipitem id="clipitem-v{k+1}"><name>{escape(Path(p).name)}</name>'
            f"<enabled>TRUE</enabled><duration>{info['frames']}</duration>{rate_xml()}"
            f"<start>{t_start}</start><end>{t_end}</end><in>{s_in}</in><out>{s_out}</out>"
            f"{fdef}<compositemode>normal</compositemode></clipitem>"
        )
        if dis and k < len(segs) - 1:
            c_at = rec + dur
            v_items.append(
                f'<transitionitem><start>{c_at - dis//2}</start><end>{c_at + (dis - dis//2)}</end>'
                f"<alignment>center</alignment>{rate_xml()}"
                f"<effect><name>Cross Dissolve</name><effectid>Cross Dissolve</effectid>"
                f"<effecttype>transition</effecttype><mediatype>video</mediatype>"
                f'<wipecode>0</wipecode><startratio>0</startratio><endratio>1</endratio><reverse>FALSE</reverse>'
                f"</effect></transitionitem>"
            )

    # ---- audio track (música) ----
    m = music
    a_item = (
        f'<clipitem id="clipitem-a1"><name>{escape(Path(m["path"]).name)}</name>'
        f"<enabled>TRUE</enabled><duration>{total}</duration>{rate_xml()}"
        f"<start>0</start><end>{total}</end><in>{int(m['in_frame'])}</in>"
        f"<out>{int(m['in_frame']) + total}</out>"
        f'<file id="file-music"><name>{escape(Path(m["path"]).name)}</name>'
        f"<pathurl>{pathurl(m['path'])}</pathurl>{rate_xml()}<duration>{int(m['in_frame']) + total + 300}</duration>"
        f"<media><audio><samplecharacteristics><depth>16</depth><samplerate>{music_arate}</samplerate>"
        f"</samplecharacteristics><channelcount>2</channelcount></audio></media></file>"
        f"<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack></clipitem>"
    )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="5">\n'
        f'<sequence id="seq-beatmontage"><name>{escape(tl["name"])}</name>'
        f"<duration>{total}</duration>{rate_xml()}"
        f"<timecode>{rate_xml()}<string>00:00:00:00</string><frame>0</frame>"
        f"<displayformat>NDF</displayformat></timecode>"
        f"<media><video><format><samplecharacteristics>{rate_xml()}"
        f"<width>{W}</width><height>{H}</height><pixelaspectratio>square</pixelaspectratio>"
        f"<fielddominance>none</fielddominance></samplecharacteristics></format>"
        f"<track>{''.join(v_items)}</track></video>"
        f"<audio><format><samplecharacteristics><depth>16</depth><samplerate>{music_arate}</samplerate>"
        f"</samplecharacteristics></format><track>{a_item}</track></audio></media>"
        f"</sequence>\n</xmeml>\n"
    )
    args.out.write_text(xml, encoding="utf-8")

    # valida que al menos es XML bien formado
    import xml.dom.minidom as md
    md.parseString(xml)
    print(f"OK -> {args.out}")
    print(f"  {len(segs)} cortes, {total} frames ({total/29.97:.1f}s), {W}x{H}, "
          f"{'dissolve ' + str(dis) + 'f' if dis else 'cortes secos'}")
    print("  Premiere: File > Import > montage.xml")


if __name__ == "__main__":
    main()
