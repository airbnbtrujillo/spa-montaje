#!/usr/bin/env python3
"""
spa_resumen.py — Resumen final para imprimir: qué se hizo, qué archivos hay y qué comprobaciones pasaron.

Escribe salida/RESUMEN.md y salida/RESUMEN.html (con estilo de impresión: Ctrl+P) y devuelve el texto
para mostrarlo en pantalla. Lo llama spa.py al dar el «listo»; también se puede ejecutar solo.
"""
from __future__ import annotations

import base64
import gzip
import io
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from html import escape
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spa_lib import ACTOS, BASE, CACHE, SALIDA, load_json  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

TICKS = 254016000000  # ticks por segundo en un .prproj


def _tam(p: Path) -> str:
    if not p.exists():
        return "—"
    b = p.stat().st_size
    return f"{b / 1e6:.1f} MB" if b >= 1e6 else f"{max(1, b // 1024)} KB"


def revisar_xml(xml: Path) -> dict:
    root = ET.parse(xml).getroot()
    seq = root.find("sequence")
    vt = root.find(".//media/video/track")
    clips = [(int(e.find("start").text), int(e.find("end").text)) for e in vt if e.tag == "clipitem"]
    return {
        "resolucion": "{}x{}".format(seq.find(".//media/video/format/samplecharacteristics/width").text,
                                     seq.find(".//media/video/format/samplecharacteristics/height").text),
        "clips": len(clips), "fundidos": sum(1 for e in vt if e.tag == "transitionitem"),
        "solapes": sum(1 for a, b in zip(clips, clips[1:]) if b[0] < a[1]),
        "huecos": sum(1 for a, b in zip(clips, clips[1:]) if b[0] > a[1]),
    }


def revisar_prproj(prproj: Path) -> dict | None:
    if not prproj.is_file() or prproj.stat().st_size < 20_000:   # 6 KB = plantilla en blanco
        return None
    raw = gzip.open(prproj).read().decode("utf-8", "replace")
    items = {}
    for m in re.finditer(r'<VideoClipTrackItem ObjectID="(\d+)"[^>]*>(.*?)</VideoClipTrackItem>', raw, re.S):
        s, e = re.search(r"<Start>(\d+)</Start>", m.group(2)), re.search(r"<End>(\d+)</End>", m.group(2))
        if s and e:
            items[m.group(1)] = (int(s.group(1)) / TICKS, int(e.group(1)) / TICKS)
    out = {"carpetas": len(re.findall(r"<BinProjectItem ", raw)), "pistas": []}
    for body in re.findall(r'<VideoClipTrack [^>]*ObjectUID="[^"]+"[^>]*>(.*?)</VideoClipTrack>', raw, re.S):
        sp = sorted(items[i] for i in re.findall(r'<TrackItem Index="\d+" ObjectRef="(\d+)"', body) if i in items)
        if sp:
            out["pistas"].append({"clips": len(sp), "fin_s": round(sp[-1][1], 1),
                                  "solapes": sum(1 for a, b in zip(sp, sp[1:]) if b[0] < a[1] - 0.02),
                                  "huecos": sum(1 for a, b in zip(sp, sp[1:]) if b[0] > a[1] + 0.02)})
    out["clips_distintos"] = len(set(re.findall(r"C\d{4}\.MP4", raw)))
    out["proxies"] = len(set(re.findall(r"Proxies[\\/]+(C\d{4}\.MP4)", raw)))   # proxies guardados en el archivo
    return out


def _gh(*args: str) -> str:
    gh = shutil.which("gh")
    if not gh:
        return ""
    r = subprocess.run([gh, *args], capture_output=True, text=True, cwd=BASE)
    return r.stdout.strip() if r.returncode == 0 else ""


def info_github() -> dict | None:
    if not (BASE / ".git").exists():
        return None
    remoto = subprocess.run(["git", "-C", str(BASE), "remote", "get-url", "origin"], capture_output=True, text=True)
    if remoto.returncode != 0:
        return None
    rama = subprocess.run(["git", "-C", str(BASE), "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
    repo = _gh("repo", "view", "--json", "url,visibility,nameWithOwner")
    d = json.loads(repo) if repo else {}
    pr = _gh("pr", "list", "--head", rama, "--json", "url,state", "--limit", "1") if rama else ""
    prs = json.loads(pr) if pr else []
    nombre = d.get("nameWithOwner", "")
    pages = f"https://{nombre.split('/')[0]}.github.io/{nombre.split('/')[1]}/" if "/" in nombre else ""
    return {"url": d.get("url", remoto.stdout.strip()), "visibilidad": d.get("visibility", "?"), "rama": rama,
            "pr": prs[0]["url"] if prs else "", "pages": pages}


def hoja_de_contacto(salida: Path) -> Path | None:
    """Un fotograma por plano del vídeo borrador, para ver la secuencia de un vistazo (y al imprimir)."""
    plan, mp4, ff = salida / "plan_borrador.json", salida / "borrador.mp4", shutil.which("ffmpeg")
    if not (plan.is_file() and mp4.is_file() and ff):
        return None
    from PIL import Image, ImageDraw
    p = json.loads(plan.read_text(encoding="utf-8"))
    fps = p["timeline"]["fps"]
    tmp = CACHE / "_hoja.jpg"
    tiles = []
    for s in p["segments"]:
        t = (s["record_frame"] + s["duration_frames"] * 0.5) / fps
        subprocess.run([ff, "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(mp4), "-frames:v", "1",
                        "-vf", "scale=240:-2", str(tmp)], capture_output=True)
        if tmp.is_file():
            im = Image.open(tmp).convert("RGB")
            im.load()
            ImageDraw.Draw(im).rectangle([0, 0, 239, 14], fill=(0, 0, 0))
            ImageDraw.Draw(im).text((3, 1), f"{s['index'] + 1:02d}  {s.get('plano', '')}  {s['record_frame'] / fps:4.0f}s", fill="white")
            tiles.append(im)
    if not tiles:
        return None
    cols = 4
    w, h = tiles[0].size
    hoja = Image.new("RGB", (cols * w, ((len(tiles) + cols - 1) // cols) * h), "black")
    for i, im in enumerate(tiles):
        hoja.paste(im, ((i % cols) * w, (i // cols) * h))
    dst = salida / "secuencia.png"
    hoja.save(dst)
    tmp.unlink(missing_ok=True)
    return dst


def generar(estado: dict, decisiones: Path, resultados: dict | None = None) -> str:
    """estado = proyecto.json; resultados = {'premiere': 'ok'|'error: ...'|None, ...}. Devuelve el texto del resumen."""
    resultados = resultados or {}
    salida = SALIDA
    L: list[str] = []
    add = L.append
    ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
    add(f"# {estado.get('titulo', 'Spot')} — resumen final")
    add(f"_{ahora}_\n")

    # --- material y análisis ---
    grupos = load_json(CACHE / "grupos.json")["grupos"] if (CACHE / "grupos.json").is_file() else []
    n_clips = sum(len(g["clips"]) for g in grupos)
    rep = [g for g in grupos if len(g["clips"]) > 1]
    add("## Material")
    add(f"- Originales: `{estado.get('originales', '?')}`")
    add(f"- Proxies: `{estado.get('proxies', '?')}`")
    add(f"- Música: `{Path(estado['musica']).name if estado.get('musica') else '?'}`")
    add(f"- {n_clips} clips → **{len(grupos)} planos distintos** ({len(rep)} planos con tomas repetidas, "
        f"{n_clips - len(grupos)} clips agrupados)\n")

    # --- el spot ---
    dec = load_json(decisiones)
    orden = dec["orden"] if isinstance(dec, dict) else dec
    plan = load_json(salida / "plan_borrador.json") if (salida / "plan_borrador.json").is_file() else None
    dur = plan["total_frames"] / plan["timeline"]["fps"] if plan else 0
    add("## El spot")
    add(f"- **{len(orden)} planos, {dur:.1f} s** (decisiones: `{decisiones.name}`)")
    por = {}
    for d in orden:
        por[d["acto"]] = por.get(d["acto"], 0) + 1
    titulos = {a[0]: a[1] for a in ACTOS}
    for a in ACTOS:
        if a[0] in por:
            add(f"  - {titulos[a[0]]}: {por[a[0]]}")
    add("")

    # --- entregables ---
    add("## Archivos generados")
    filas = [("Vídeo borrador (proxies)", salida / "borrador.mp4"),
             ("Vídeo final desde los originales", next(iter(sorted(salida.glob("spot_final_*p.mp4"))), salida / "spot_final.mp4")),
             ("XML de secuencia (proxies)", salida / "spot.xml"),
             ("XML de secuencia (originales)", salida / "spot_final.xml"),
             ("Proyecto de Premiere", next(iter(sorted((salida / "premiere").glob("*FINAL.prproj"))), salida / "premiere" / "Spot Spa - organizado.prproj")),
             ("Visor HTML de la propuesta", BASE / "propuesta_montaje.html"),
             ("Visor estático (GitHub)", BASE / "docs" / "index.html"),
             ("Decisiones", decisiones)]
    add("| Entregable | Archivo | Tamaño |\n|---|---|---|")
    for nombre, p in filas:
        if p.exists():
            add(f"| {nombre} | `{p}` | {_tam(p)} |")
    add("")

    # --- comprobaciones ---
    add("## Comprobaciones")
    for etiqueta, f in (("XML con proxies", salida / "spot.xml"), ("XML con originales", salida / "spot_final.xml")):
        if f.is_file():
            r = revisar_xml(f)
            ok = "✔" if r["solapes"] == 0 and r["huecos"] == 0 else "✘"
            add(f"- {ok} {etiqueta}: {r['clips']} clips, secuencia {r['resolucion']}, "
                f"{r['solapes']} solapes, {r['huecos']} huecos, {r['fundidos']} fundidos")
    pp = next(iter(sorted((salida / "premiere").glob("*FINAL.prproj"))), None) or (salida / "premiere" / "Spot Spa - organizado.prproj")
    rp = revisar_prproj(pp)
    if rp:
        for p in rp["pistas"]:
            ok = "✔" if p["solapes"] == 0 and p["huecos"] == 0 else "✘"
            add(f"- {ok} Premiere (`{pp.name}`): {p['clips']} clips en V1 hasta {p['fin_s']} s, "
                f"{p['solapes']} solapes, {p['huecos']} huecos; {rp['carpetas']} carpetas; {rp['clips_distintos']} clips referenciados; "
                f"{rp['proxies']} proxies adjuntos (comprobado en el archivo)")
    marcador = next(iter(sorted((salida / "premiere").glob("*importado.ok.txt"))), None)
    if marcador:
        add("- Premiere confirmó: " + " · ".join(l for l in marcador.read_text(encoding="utf-8", errors="replace").splitlines()[2:6] if l))
    if resultados.get("premiere") and resultados["premiere"] != "ok":
        add(f"- ⚠ Premiere: {resultados['premiere']}")
    add("")

    gh = info_github()
    if gh:
        add("## GitHub")
        add(f"- Repositorio: {gh['url']} ({gh['visibilidad']}) — rama `{gh['rama']}`")
        if gh["pr"]:
            add(f"- Pull request: {gh['pr']}")
        if gh["pages"]:
            add(f"- Visor: {gh['pages']}")
        add("")

    add("## Siguiente paso")
    add("- Para el vídeo final: exportar desde Premiere (los originales ya están enlazados y los proxies adjuntos; "
        "el botón *Toggle Proxies* alterna entre ambos).")
    texto = "\n".join(L)
    (salida / "RESUMEN.md").write_text(texto, encoding="utf-8")

    # --- versión para imprimir ---
    hoja = hoja_de_contacto(salida)
    img = ""
    if hoja:
        img = ('<h2>Secuencia (un fotograma por plano)</h2><img class="hoja" src="data:image/png;base64,'
               + base64.b64encode(hoja.read_bytes()).decode() + '">')
    cuerpo = []
    for linea in texto.splitlines():
        if linea.startswith("# "):
            cuerpo.append(f"<h1>{escape(linea[2:])}</h1>")
        elif linea.startswith("## "):
            cuerpo.append(f"<h2>{escape(linea[3:])}</h2>")
        elif linea.startswith("|"):
            celdas = [c.strip() for c in linea.strip("|").split("|")]
            if set("".join(celdas)) <= set("-"):
                continue
            tag = "th" if cuerpo and cuerpo[-1].startswith("<h2>") else "td"
            cuerpo.append("<tr>" + "".join(f"<{tag}>{escape(c)}</{tag}>" for c in celdas) + "</tr>")
        elif linea.lstrip().startswith("- "):
            cuerpo.append(f"<p class='li'>{escape(linea.lstrip()[2:])}</p>")
        elif linea.strip():
            cuerpo.append(f"<p>{escape(linea)}</p>")
    html = ("<!doctype html><html lang='es'><meta charset='utf-8'><title>Resumen final</title><style>"
            "body{font:13px/1.5 system-ui,Segoe UI,sans-serif;max-width:920px;margin:24px auto;color:#1b2430}"
            "h1{font-size:22px;margin:0}h2{font-size:15px;border-bottom:1px solid #ccd;padding-bottom:2px;margin:18px 0 6px}"
            "tr{border-bottom:1px solid #e3e7ec}td,th{text-align:left;padding:3px 8px;font-size:12px}table{border-collapse:collapse}"
            ".li{margin:2px 0 2px 14px}.hoja{width:100%;border:1px solid #ccd}"
            "@media print{body{margin:8mm}.hoja{page-break-inside:avoid}}</style>"
            + "".join(f"<table>{c}</table>" if c.startswith("<tr>") else c for c in cuerpo) + img
            + "<p style='color:#778;margin-top:18px'>Ctrl+P para imprimir o guardar como PDF.</p></html>")
    (salida / "RESUMEN.html").write_text(html, encoding="utf-8")
    return texto


def main() -> None:
    from spa_lib import ultima_decision
    est = load_json(BASE / "proyecto.json") if (BASE / "proyecto.json").is_file() else {}
    print(generar(est, ultima_decision()))
    print(f"\n(guardado en {SALIDA / 'RESUMEN.md'} y {SALIDA / 'RESUMEN.html'} — Ctrl+P para imprimir)")


if __name__ == "__main__":
    main()
