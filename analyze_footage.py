#!/usr/bin/env python3
"""
analyze_footage.py — Loguea material en bruto con IA 100% local (Ollama + Qwen2.5-VL).

Por cada vídeo de una carpeta:
  1. saca fotogramas (por cambios de plano, con relleno uniforme)
  2. cada fotograma -> modelo de visión: qué se ve, producto, encuadre, luz, nitidez
  3. junta todo -> modelo de texto: resumen, categoría, mejores momentos, nota, puntuación
Salida:
  footage_report.html   informe visual con miniaturas
  footage_log.json      datos estructurados
  resolve_markers.json  marcadores verde/rojo para build_in_resolve.py
  keepers.txt           rutas de los clips recomendados (para plan_montage.py --clips-list)

Requiere: Ollama corriendo (localhost:11434) con un modelo de visión y uno de texto,
ffmpeg/ffprobe en el PATH.

    python analyze_footage.py --clips "C:/ruta/Videos" --purpose "promo de producto de maquillaje"
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from html import escape
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm", ".mts", ".m2ts", ".wmv", ".3gp"}


def _ollama_url() -> str:
    h = os.environ.get("OLLAMA_HOST", "").strip() or "http://127.0.0.1:11434"
    if "://" not in h:
        h = "http://" + h
    return h.rstrip("/").replace("//0.0.0.0:", "//127.0.0.1:")


OLLAMA = _ollama_url()


# --------------------------------------------------------------------------- #
# ffmpeg helpers
# --------------------------------------------------------------------------- #
def tool(name: str) -> str:
    p = shutil.which(name)
    if not p:
        sys.exit(f"ERROR: falta '{name}' en el PATH.")
    return p


def probe(path: Path, ffprobe: str) -> dict:
    r = subprocess.run([ffprobe, "-v", "error", "-print_format", "json",
                        "-show_streams", "-show_format", str(path)],
                       capture_output=True, text=True)
    data = json.loads(r.stdout or "{}")
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    dur = float(v.get("duration") or data.get("format", {}).get("duration") or 0.0)
    return {
        "duration": dur,
        "width": int(v.get("width") or 0),
        "height": int(v.get("height") or 0),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
    }


def scene_times(path: Path, ffmpeg: str, dur: float, want: int) -> list[float]:
    """Timestamps de cambios de plano; si hay pocos, reparte uniformemente."""
    times: list[float] = []
    try:
        r = subprocess.run(
            [ffmpeg, "-i", str(path), "-filter:v",
             "select='gt(scene,0.25)',showinfo", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120,
        )
        times = sorted(float(m) for m in re.findall(r"pts_time:([0-9.]+)", r.stderr))
    except Exception:
        pass
    even = [dur * (i + 0.5) / want for i in range(want)]
    merged = sorted(set(round(t, 2) for t in times + even if 0 <= t < dur))
    # thin out so frames aren't clustered
    out: list[float] = []
    for t in merged:
        if not out or t - out[-1] >= max(0.6, dur / (want * 2)):
            out.append(t)
    return out[:want] or even[:want]


def grab(path: Path, t: float, dst: Path, ffmpeg: str) -> bool:
    r = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(path),
         "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "3", str(dst)],
        capture_output=True, text=True,
    )
    return r.returncode == 0 and dst.is_file()


def contact_sheet(frames: list[Path], dst: Path, ffmpeg: str) -> bool:
    if not frames:
        return False
    cols = min(4, len(frames))
    rows = (len(frames) + cols - 1) // cols
    lst = dst.with_suffix(".txt")
    lst.write_text("".join(f"file '{f.as_posix()}'\n" for f in frames), encoding="utf-8")
    r = subprocess.run(
        [ffmpeg, "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-vf", f"scale=320:-2,tile={cols}x{rows}", "-frames:v", "1", str(dst)],
        capture_output=True, text=True,
    )
    lst.unlink(missing_ok=True)
    return r.returncode == 0 and dst.is_file()


# --------------------------------------------------------------------------- #
# Ollama
# --------------------------------------------------------------------------- #
def ollama(model: str, prompt: str, images: list[Path] | None = None,
           retries: int = 2, timeout: int = 300) -> str:
    body = {"model": model, "prompt": prompt, "stream": False, "format": "json",
            "think": False, "options": {"temperature": 0.1}}
    if images:
        body["images"] = [base64.b64encode(p.read_bytes()).decode() for p in images]
    data = json.dumps(body).encode()
    last = ""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(f"{OLLAMA}/api/generate", data=data,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())["response"]
        except Exception as e:  # noqa: BLE001
            last = str(e)
            time.sleep(2 + attempt * 3)
    print(f"  ! Ollama sin respuesta ({last})")
    return "{}"


def as_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?|\n?```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return {}


FRAME_PROMPT = """Eres asistente de montaje de vídeo. Analiza este fotograma de un clip en bruto.
Proyecto: {purpose}
Responde SOLO con JSON:
{{"descripcion":"qué se ve en 1 frase","producto_visible":true/false,
"accion":"aplicar producto | mostrar envase | hablar a cámara | resultado final | nada relevante",
"encuadre":"detalle | primer plano | plano medio | plano general",
"iluminacion":"buena | regular | mala","nitidez":"nítido | algo movido | borroso",
"cara_visible":true/false}}"""

CLIP_PROMPT = """Eres editor de vídeo montando un {purpose}.
Clip: {name}  ({dur:.1f}s{audio})
Fotogramas analizados:
{frames}
{transcript}

Escala de puntuación (sé generoso, es material en bruto para B-roll):
 8-10 = plano claro y aprovechable tal cual (producto nítido y bien iluminado, aplicación, resultado)
 5-7  = utilizable con recorte o como plano de apoyo corto
 2-4  = flojo (repetitivo, encuadre pobre) pero rescatable en un apuro
 0-1  = inservible (borroso, oscuro, irrelevante)
Un primer plano limpio del envase YA vale 6-8 para un B-roll de promo.

Responde SOLO con JSON:
{{"resumen":"2 frases sobre el clip",
"categoria":"producto | aplicacion | resultado | testimonio | relleno | descarte",
"mejores_momentos":[{{"inicio_s":0.0,"fin_s":0.0,"por_que":"..."}}],
"calidad":{{"iluminacion":"...","estabilidad":"...","nitidez":"..."}},
"puntuacion_promo":0,"notas":"consejo breve para el editor"}}"""


# --------------------------------------------------------------------------- #
def analyze_clip(path: Path, tmp: Path, args, ffmpeg, ffprobe) -> dict:
    info = probe(path, ffprobe)
    dur = info["duration"]
    n = max(3, min(args.max_frames, int(dur / args.every) + 1)) if dur else args.max_frames
    times = scene_times(path, ffmpeg, dur or 1.0, n)

    frames, descs = [], []
    for i, t in enumerate(times):
        fp = tmp / f"{path.stem}_{i:02d}.jpg"
        if not grab(path, t, fp, ffmpeg):
            continue
        frames.append(fp)
        d = as_json(ollama(args.vision_model, FRAME_PROMPT.format(purpose=args.purpose), [fp]))
        d["_t"] = round(t, 2)
        descs.append(d)
        print(f"    t={t:5.1f}s  {d.get('encuadre','?'):12s} {d.get('accion','?')}")

    sheet = tmp / f"{path.stem}_sheet.jpg"
    contact_sheet(frames, sheet, ffmpeg)

    frame_lines = "\n".join(
        f"- t={d['_t']}s: {d.get('descripcion','')} "
        f"[{d.get('accion','')}, {d.get('encuadre','')}, luz {d.get('iluminacion','')}, "
        f"{d.get('nitidez','')}{', producto' if d.get('producto_visible') else ''}]"
        for d in descs
    ) or "- (sin fotogramas legibles)"

    transcript = ""
    if args.transcript and info["has_audio"]:
        transcript = "Transcripción: " + (transcribe(path, args) or "(sin voz clara)")

    verdict = as_json(ollama(
        args.text_model,
        CLIP_PROMPT.format(purpose=args.purpose, name=path.name, dur=dur,
                           audio=", con audio" if info["has_audio"] else ", sin audio",
                           frames=frame_lines, transcript=transcript),
    ))
    verdict.setdefault("resumen", "")
    verdict.setdefault("categoria", "relleno")
    verdict.setdefault("notas", "")
    try:
        score = int(round(float(verdict.get("puntuacion_promo", 0))))
    except (TypeError, ValueError):
        score = 0
    verdict["puntuacion_promo"] = max(0, min(10, score))
    verdict["mejores_momentos"] = [
        m for m in verdict.get("mejores_momentos", [])
        if isinstance(m, dict) and m.get("fin_s", 0) - m.get("inicio_s", 0) > 0.1
    ]
    verdict["usar"] = verdict["puntuacion_promo"] >= args.keep_score  # coherente con la puntuación
    return {
        "archivo": str(path),
        "nombre": path.name,
        "duracion_s": round(dur, 2),
        "resolucion": f"{info['width']}x{info['height']}",
        "audio": info["has_audio"],
        "sheet": sheet.name if sheet.is_file() else "",
        "fotogramas": descs,
        **verdict,
    }


def transcribe(path: Path, args) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return ""
    if not hasattr(transcribe, "_m"):
        for dev, ct in (("cuda", "float16"), ("cpu", "int8")):
            try:
                transcribe._m = WhisperModel(args.whisper_model, device=dev, compute_type=ct)
                break
            except Exception:
                transcribe._m = None
    if not getattr(transcribe, "_m", None):
        return ""
    segs, _ = transcribe._m.transcribe(str(path), language=args.lang if args.lang != "auto" else None)
    return " ".join(s.text.strip() for s in segs)[:1200]


# --------------------------------------------------------------------------- #
def write_html(clips: list[dict], out: Path, sheet_dir: Path, args) -> None:
    clips = sorted(clips, key=lambda c: c.get("puntuacion_promo", 0), reverse=True)
    keep = [c for c in clips if c.get("usar")]
    useful_s = sum(
        max(0.0, m.get("fin_s", 0) - m.get("inicio_s", 0))
        for c in keep for m in c.get("mejores_momentos", [])
    )
    rows = []
    for c in clips:
        score = c.get("puntuacion_promo", 0)
        col = "#16a34a" if score >= 7 else "#d97706" if score >= 4 else "#dc2626"
        moments = "".join(
            f"<li><b>{m.get('inicio_s',0):.1f}–{m.get('fin_s',0):.1f}s</b> — {escape(str(m.get('por_que','')))}</li>"
            for m in c.get("mejores_momentos", [])
        ) or "<li>—</li>"
        q = c.get("calidad", {})
        sheet = f'sheets/{c["sheet"]}' if c.get("sheet") else ""
        rows.append(f"""
<div class="card">
  <div class="thumb">{f'<img src="{sheet}">' if sheet else ''}</div>
  <div class="body">
    <div class="head"><span class="score" style="background:{col}">{score}/10</span>
      <span class="cat">{escape(str(c.get('categoria','')))}</span>
      <span class="name">{escape(c['nombre'])}</span>
      <span class="meta">{c['duracion_s']}s · {c['resolucion']} · {'audio' if c['audio'] else 'sin audio'}</span></div>
    <p>{escape(str(c.get('resumen','')))}</p>
    <div class="cols">
      <div><b>Mejores momentos</b><ul>{moments}</ul></div>
      <div><b>Calidad</b><ul>
        <li>Luz: {escape(str(q.get('iluminacion','?')))}</li>
        <li>Estabilidad: {escape(str(q.get('estabilidad','?')))}</li>
        <li>Nitidez: {escape(str(q.get('nitidez','?')))}</li></ul></div>
    </div>
    <p class="notes">📝 {escape(str(c.get('notas','')))}</p>
  </div>
</div>""")

    out.write_text(f"""<!doctype html><html lang="es"><meta charset="utf-8">
<title>Informe de material</title><style>
body{{font:14px/1.5 system-ui,sans-serif;margin:0;background:#0f1115;color:#e5e7eb}}
header{{padding:20px 28px;background:#171a21;border-bottom:1px solid #262b36}}
h1{{margin:0 0 4px;font-size:18px}} .sub{{color:#9aa4b2}}
.wrap{{padding:20px 28px;display:flex;flex-direction:column;gap:14px;max-width:1100px}}
.card{{display:flex;gap:16px;background:#171a21;border:1px solid #262b36;border-radius:10px;overflow:hidden}}
.thumb{{flex:0 0 320px;background:#0b0d11;display:flex;align-items:center}}
.thumb img{{width:100%;display:block}}
.body{{padding:14px 16px;flex:1;min-width:0}}
.head{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px}}
.score{{color:#fff;font-weight:700;padding:2px 8px;border-radius:6px}}
.cat{{background:#262b36;padding:2px 8px;border-radius:6px;text-transform:capitalize}}
.name{{font-weight:600}} .meta{{color:#9aa4b2;font-size:12px}}
.cols{{display:flex;gap:24px;flex-wrap:wrap}} .cols>div{{flex:1;min-width:220px}}
ul{{margin:4px 0;padding-left:18px}} .notes{{color:#cbd5e1;background:#1f2430;padding:8px 10px;border-radius:6px}}
</style>
<header><h1>Informe de material — {escape(args.purpose)}</h1>
<div class="sub">{len(clips)} clips · {len(keep)} recomendados · ~{useful_s:.0f}s de material útil ·
modelo visión {escape(args.vision_model)} · texto {escape(args.text_model)}</div></header>
<div class="wrap">{''.join(rows)}</div></html>""", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clips", required=True, type=Path)
    ap.add_argument("--purpose", default="montaje promocional de un producto",
                    help="para qué es el vídeo; guía a la IA")
    ap.add_argument("--out", type=Path, default=Path(__file__).with_name("footage"))
    ap.add_argument("--vision-model", default="qwen2.5vl:7b")
    ap.add_argument("--text-model", default="qwen3:8b")
    ap.add_argument("--every", type=float, default=2.0, help="1 fotograma cada N s (aprox)")
    ap.add_argument("--max-frames", type=int, default=8)
    ap.add_argument("--recursive", action="store_true")
    ap.add_argument("--transcript", action="store_true", help="transcribir audio (necesita faster-whisper)")
    ap.add_argument("--whisper-model", default="small")
    ap.add_argument("--lang", default="es")
    ap.add_argument("--keep-score", type=int, default=6, help="puntuación mínima para keepers.txt")
    args = ap.parse_args()

    if not args.clips.is_dir():
        sys.exit(f"ERROR: carpeta no encontrada: {args.clips}")
    ffmpeg, ffprobe = tool("ffmpeg"), tool("ffprobe")

    try:
        urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5).read()
    except Exception:
        sys.exit(f"ERROR: Ollama no responde en {OLLAMA}. Ábrelo y reintenta.")

    it = args.clips.rglob("*") if args.recursive else args.clips.glob("*")
    vids = sorted(p for p in it if p.is_file() and p.suffix.lower() in VIDEO_EXTS)
    if not vids:
        sys.exit("ERROR: no hay vídeos en la carpeta.")
    print(f"{len(vids)} vídeo(s). Proyecto: {args.purpose}\n")

    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    sheets = out_dir / "sheets"
    sheets.mkdir(exist_ok=True)

    # Guardado parcial + reanudación: con muchos clips, un corte no debe perder el trabajo hecho.
    partial = out_dir / "footage_log.partial.json"
    results = []
    if partial.is_file():
        try:
            results = json.loads(partial.read_text(encoding="utf-8")).get("clips", [])
            print(f"Reanudando: {len(results)} clip(s) ya analizados\n")
        except (json.JSONDecodeError, OSError):
            results = []
    done = {c["archivo"] for c in results}
    with tempfile.TemporaryDirectory(prefix="footage_") as td:
        tmp = Path(td)
        for k, v in enumerate(vids, 1):
            if str(v) in done:
                continue
            print(f"[{k}/{len(vids)}] {v.name}")
            try:
                r = analyze_clip(v, tmp, args, ffmpeg, ffprobe)
            except Exception as e:  # noqa: BLE001
                print(f"  ! error: {e}")
                continue
            if r.get("sheet"):
                src = tmp / r["sheet"]
                if src.is_file():
                    shutil.copy2(src, sheets / r["sheet"])
            results.append(r)
            partial.write_text(
                json.dumps({"purpose": args.purpose, "clips": results}, ensure_ascii=False),
                encoding="utf-8")
            print(f"  -> {r.get('puntuacion_promo',0)}/10  {r.get('categoria','')}  "
                  f"{'USAR' if r.get('usar') else 'descartar'}\n")

    (out_dir / "footage_log.json").write_text(
        json.dumps({"purpose": args.purpose, "clips": results}, indent=2, ensure_ascii=False),
        encoding="utf-8")

    markers = [{
        "archivo": c["archivo"], "usar": bool(c.get("usar")),
        "puntuacion": c.get("puntuacion_promo", 0), "nota": c.get("notas", ""),
        "marcadores": ([{"t": 0.0, "color": "Red", "nota": "descartar: " + c.get("notas", "")}]
                       if not c.get("usar") else
                       [{"t": m.get("inicio_s", 0), "color": "Green", "nota": m.get("por_que", "")}
                        for m in c.get("mejores_momentos", [])]),
    } for c in results]
    (out_dir / "resolve_markers.json").write_text(json.dumps(markers, indent=2, ensure_ascii=False),
                                                  encoding="utf-8")

    keepers = [c["archivo"] for c in sorted(results, key=lambda c: -c.get("puntuacion_promo", 0))
               if c.get("puntuacion_promo", 0) >= args.keep_score]
    (out_dir / "keepers.txt").write_text("\n".join(keepers), encoding="utf-8")

    write_html(results, out_dir / "footage_report.html", sheets, args)
    keep = sum(1 for c in results if c.get("usar"))
    print(f"Listo. {keep}/{len(results)} clips recomendados.")
    print(f"  {out_dir / 'footage_report.html'}")
    print(f"  {out_dir / 'footage_log.json'} · resolve_markers.json · keepers.txt")


if __name__ == "__main__":
    main()
