#!/usr/bin/env python3
"""
spa.py — Programa único: del rodaje al spot, con proxies, análisis, visor HTML, Premiere, GitHub y resumen.

  python spa.py preparar --originales "F:\\Video Spa" --musica cancion.mp3
      crea los PROXIES (si faltan) → fotogramas y huellas → análisis con IA local → ritmo de la música →
      junta las TOMAS REPETIDAS → qué se ve en cada plano → PROPUESTA de montaje → borrador → VISOR HTML
  (revisas el HTML, ajustas, «Descargar decisiones»)
  python spa.py listo
      con tus decisiones: vídeo borrador, XML, vídeo final desde los ORIGINALES, proyecto de PREMIERE
      (originales + proxies adjuntos, carpetas por etapa y toma) y RESUMEN para imprimir
  python spa.py publicar     sube el visor a GitHub (rama + pull request; pregunta antes)
  python spa.py proxies      solo crea/verifica los proxies
  python spa.py resumen      vuelve a mostrar el resumen
  python spa.py estado       qué pasos están hechos
  python spa.py              menú
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spa_lib import BASE, CACHE, DECISIONES, HERE, SALIDA, load_json, ultima_decision  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

ESTADO = BASE / "proyecto.json"
ENV = {**os.environ, "SPA_PROYECTO": str(BASE), "PYTHONIOENCODING": "utf-8"}
MODELO_VISION, MODELO_TEXTO = "qwen2.5vl:7b", "qwen3:8b"


# --------------------------------------------------------------------------- estado
def cargar() -> dict:
    return json.loads(ESTADO.read_text(encoding="utf-8")) if ESTADO.is_file() else {}


def guardar(est: dict) -> None:
    ESTADO.write_text(json.dumps(est, indent=2, ensure_ascii=False), encoding="utf-8")


def marcar(est: dict, paso: str) -> None:
    est.setdefault("pasos", {})[paso] = datetime.now().isoformat(timespec="seconds")
    guardar(est)


def titulo_paso(n: int, total: int, texto: str) -> None:
    print(f"\n[{n}/{total}] {texto}\n" + "-" * 70, flush=True)


def ejecutar(script: str, *args: str, ok: tuple[int, ...] = (0,)) -> int:
    cmd = [sys.executable, str(HERE / script), *args]
    r = subprocess.run(cmd, env=ENV)
    if r.returncode not in ok:
        sys.exit(f"\nERROR: {script} terminó con código {r.returncode}. Corrige y vuelve a ejecutar: continúa donde se quedó.")
    return r.returncode


def ollama_listo(modelos: tuple[str, ...]) -> None:
    host = os.environ.get("OLLAMA_HOST", "").strip() or "http://127.0.0.1:11434"
    host = (host if "://" in host else "http://" + host).replace("//0.0.0.0:", "//127.0.0.1:").rstrip("/")
    try:
        tags = json.loads(urllib.request.urlopen(host + "/api/tags", timeout=5).read())
    except Exception:
        sys.exit("ERROR: Ollama no responde. Ábrelo (es la IA local que describe los clips) y vuelve a ejecutar.")
    tengo = {m["name"] for m in tags["models"]}
    faltan = [m for m in modelos if m not in tengo]
    if faltan:
        sys.exit("ERROR: faltan modelos en Ollama: " + ", ".join(faltan) + "\n  instálalos con: ollama pull " + faltan[0])


# --------------------------------------------------------------------------- preparar
def preparar(a: argparse.Namespace) -> None:
    est = cargar()
    orig = Path(a.originales or est.get("originales") or "")
    if not orig.is_dir():
        sys.exit("ERROR: indica la carpeta de los originales con --originales")
    musica = Path(a.musica or est.get("musica") or "")
    if not musica.is_file():
        sys.exit("ERROR: indica la música con --musica")
    prox = Path(a.proxies or est.get("proxies") or orig / "Proxies")
    est.update(originales=str(orig), proxies=str(prox), musica=str(musica.resolve()),
               titulo=a.titulo or est.get("titulo") or "Spot",
               proposito=a.proposito or est.get("proposito") or "spot publicitario de un spa (tratamientos, instalaciones y ambiente relajante)")
    guardar(est)
    BASE.mkdir(parents=True, exist_ok=True)
    TOTAL = 9
    t0 = time.time()

    titulo_paso(1, TOTAL, "Proxies (640x360, mismo nombre, mismos fotogramas que los originales)")
    from spa_proxies import crear_proxies
    r = crear_proxies(orig, prox, log=print)
    print(f"  {r['total']} originales: {r['creados']} creados, {r['conservados']} ya estaban bien, {len(r['con_problemas'])} con problemas")
    if r["con_problemas"]:
        sys.exit("ERROR: hay proxies con problemas: " + ", ".join(r["con_problemas"][:8]))
    marcar(est, "proxies")

    titulo_paso(2, TOTAL, "Fotogramas y huella visual de cada clip (CLIP)")
    n_prox = len([p for p in prox.iterdir() if p.suffix.lower() in (".mp4", ".mov", ".m4v")])
    clips_json = CACHE / "clips.json"
    hecho = clips_json.is_file() and len(json.loads(clips_json.read_text(encoding="utf-8"))) == n_prox and (CACHE / "embeds.npz").is_file()
    if hecho and not a.rehacer:
        print("  ya estaba hecho (usa --rehacer para repetirlo)")
    else:
        ejecutar("spa_extraer.py", "--clips", str(prox))
    marcar(est, "extraer")

    titulo_paso(3, TOTAL, "Análisis de cada clip con IA local (qué se ve, nota, mejores momentos)")
    log_a = CACHE / "analisis" / "footage_log.json"
    completo = log_a.is_file() and len(json.loads(log_a.read_text(encoding="utf-8")).get("clips", [])) >= n_prox
    if a.sin_analisis:
        print("  omitido (--sin-analisis): la propuesta no usará notas de la IA")
    elif completo and not a.rehacer:
        print("  ya estaba hecho")
    else:
        ollama_listo((MODELO_VISION, MODELO_TEXTO))
        print("  Tarda unos 20 s por clip; se guarda tras cada uno y se puede reanudar.")
        ejecutar("analyze_footage.py", "--clips", str(prox), "--purpose", est["proposito"],
                 "--out", str(CACHE / "analisis"), "--max-frames", "4", "--keep-score", "6")
    marcar(est, "analisis")

    titulo_paso(4, TOTAL, "Ritmo de la música (beats)")
    beats = CACHE / "beats.json"
    if beats.is_file() and json.loads(beats.read_text(encoding="utf-8")).get("ruta") == str(musica.resolve()) and not a.rehacer:
        print("  ya estaba hecho")
    else:
        ejecutar("spa_beats.py", str(musica))
    marcar(est, "beats")

    titulo_paso(5, TOTAL, "Junta las tomas repetidas (mismo plano grabado varias veces)")
    ejecutar("spa_agrupar.py", "--ventana", "6", "--carpetas")
    marcar(est, "agrupar")

    titulo_paso(6, TOTAL, "Qué se ve en cada plano (preguntas de sí/no a la IA local)")
    ollama_listo((MODELO_VISION,))
    ejecutar("spa_atributos.py")
    if a.con_actos:
        ejecutar("spa_actos.py")
    marcar(est, "atributos")

    titulo_paso(7, TOTAL, "Propuesta de montaje (etapas de la historia, cortes sobre los beats)")
    ejecutar("spa_proponer.py")
    marcar(est, "proponer")

    titulo_paso(8, TOTAL, "Borrador de la propuesta (con los proxies)")
    if a.sin_borrador:
        print("  omitido (--sin-borrador)")
    else:
        ejecutar("spa_aplicar.py", str(SALIDA / "decisiones_iniciales.json"))
    marcar(est, "borrador")

    titulo_paso(9, TOTAL, "Visor HTML de la propuesta")
    ejecutar("spa_html.py")
    marcar(est, "html")
    html = BASE / "propuesta_montaje.html"
    if not a.no_abrir:
        webbrowser.open(html.as_uri())
    print(f"\nListo en {int((time.time() - t0) // 60)} min {int((time.time() - t0) % 60)} s.")
    print(f"\n  Visor: {html}\n"
          "  Revisa los planos, ajusta lo que quieras y pulsa «Descargar decisiones».\n"
          "  Después ejecuta:  python spa.py listo")
    if a.publicar:
        publicar_cmd(argparse.Namespace(decisiones=None, si=a.si))


# --------------------------------------------------------------------------- listo
def buscar_descargas() -> Path | None:
    d = Path.home() / "Downloads"
    c = sorted(d.glob("decisiones_spot_spa*.json"), key=lambda p: p.stat().st_mtime) if d.is_dir() else []
    return c[-1] if c else None


def listo(a: argparse.Namespace) -> None:
    est = cargar()
    if not est.get("originales"):
        sys.exit("ERROR: no hay proyecto preparado. Ejecuta antes:  python spa.py preparar")
    orig = Path(est["originales"])
    dec = Path(a.decisiones) if a.decisiones else buscar_descargas()
    if not dec or not dec.is_file():
        sys.exit("ERROR: no encuentro las decisiones. Pulsa «Descargar decisiones» en el visor o indica la ruta del JSON.")
    DECISIONES.mkdir(parents=True, exist_ok=True)
    destino = DECISIONES / f"decisiones_{datetime.now():%Y-%m-%d_%H%M}.json"
    if dec.parent.resolve() != DECISIONES.resolve():
        # si ya hay una copia idéntica (mismas decisiones de una ejecución anterior) se reutiliza: no se duplica
        igual = next((p for p in sorted(DECISIONES.glob("decisiones_*.json")) if p.read_bytes() == dec.read_bytes()), None)
        if igual:
            dec = igual
        else:
            shutil.copy2(dec, destino)
            dec = destino
    print(f"Decisiones: {dec.name}  ({len(load_json(dec)['orden'])} planos)")
    TOTAL = 5
    resultados: dict = {}

    titulo_paso(1, TOTAL, "Proxies verificados contra los originales")
    from spa_proxies import crear_proxies
    r = crear_proxies(orig, Path(est["proxies"]), solo_verificar=True, log=print)
    print(f"  {r['conservados']} de {r['total']} proxies coinciden fotograma a fotograma")
    if r["con_problemas"]:
        sys.exit("ERROR: proxies que no coinciden: " + ", ".join(r["con_problemas"][:8]) + "\n  ejecuta:  python spa.py proxies")

    titulo_paso(2, TOTAL, "Vídeo borrador, XML y vídeo final desde los ORIGINALES")
    from spa_aplicar import aplicar
    out = aplicar(dec, SALIDA, a.dissolve, sin_video=False, originales=orig,
                  final_mp4=None if a.sin_final else a.final_mp4)
    resultados["aplicar"] = {k: str(v) for k, v in out.items()}

    titulo_paso(3, TOTAL, "Visor HTML con tus decisiones")
    ejecutar("spa_html.py", "--decisiones", str(dec))

    titulo_paso(4, TOTAL, "Proyecto de Premiere (originales + proxies adjuntos, carpetas por etapa y toma)")
    if a.sin_premiere:
        print("  omitido (--sin-premiere)")
        resultados["premiere"] = "omitido"
    else:
        print("  Se abrirán Premiere 2022 y VS Code y se enviará F5: NO toques el teclado hasta que termine.\n"
              "  Si Premiere tiene abierto otro proyecto tuyo, no lo toca: se detiene y te lo dice.")
        rc = ejecutar("spa_premiere.py", str(dec), "--originales", str(orig), ok=(0, 1))
        resultados["premiere"] = "ok" if rc == 0 else "no se pudo crear (ver arriba); relanza con:  python spa_premiere.py --originales \"" + str(orig) + "\""

    if a.publicar:
        publicar_cmd(argparse.Namespace(decisiones=str(dec), si=a.si))

    titulo_paso(5, TOTAL, "Resumen final")
    from spa_resumen import generar
    texto = generar(est, dec, resultados)
    marcar(est, "listo")
    print("\n" + "=" * 70 + "\n" + texto + "\n" + "=" * 70)
    print(f"\nPara imprimir: {SALIDA / 'RESUMEN.html'}  (se abre ahora; Ctrl+P)")
    if not a.no_abrir:
        webbrowser.open((SALIDA / "RESUMEN.html").as_uri())


# --------------------------------------------------------------------------- otros comandos
def proxies_cmd(a: argparse.Namespace) -> None:
    est = cargar()
    orig = Path(a.originales or est.get("originales") or "")
    if not orig.is_dir():
        sys.exit("ERROR: indica --originales")
    from spa_proxies import crear_proxies
    prox = Path(a.proxies or est.get("proxies") or orig / "Proxies")
    r = crear_proxies(orig, prox, forzar=a.forzar, solo_verificar=a.verificar)
    print(f"{r['total']} originales | creados {r['creados']} | conservados {r['conservados']} | problemas {len(r['con_problemas'])}")
    est.update(originales=str(orig), proxies=str(prox))
    guardar(est)


def publicar_cmd(a: argparse.Namespace) -> None:
    from spa_publicar import publicar
    try:
        publicar(Path(a.decisiones) if a.decisiones else None, si=a.si)
    except RuntimeError as e:
        print(f"\nNo se publicó: {e}")


def resumen_cmd(_a: argparse.Namespace) -> None:
    from spa_resumen import generar
    print(generar(cargar(), ultima_decision()))
    webbrowser.open((SALIDA / "RESUMEN.html").as_uri())


def estado_cmd(_a: argparse.Namespace) -> None:
    est = cargar()
    if not est:
        print("Sin proyecto todavía. Empieza con:  python spa.py preparar --originales ... --musica ...")
        return
    print(f"Proyecto: {est.get('titulo')}\n  originales: {est.get('originales')}\n  proxies   : {est.get('proxies')}\n  música    : {est.get('musica')}")
    for k in ("proxies", "extraer", "analisis", "beats", "agrupar", "atributos", "proponer", "borrador", "html", "listo"):
        print(f"  {'✔' if k in est.get('pasos', {}) else '·'} {k:10s} {est.get('pasos', {}).get(k, '')}")


def menu() -> None:
    est = cargar()
    print("=" * 60 + "\n  SPOT SPA — del rodaje al spot\n" + "=" * 60)
    print("  1) Preparar: proxies → análisis → tomas repetidas → propuesta → visor HTML")
    print("  2) Dar el «listo»: vídeo, XML, Premiere y resumen para imprimir")
    print("  3) Publicar el visor en GitHub")
    print("  4) Crear o verificar los proxies")
    print("  5) Ver el resumen / el estado")
    print("  0) Salir")
    op = input("\nElige: ").strip()
    if op == "1":
        o = input(f"Carpeta de los originales [{est.get('originales', '')}]: ").strip().strip('"') or est.get("originales", "")
        m = input(f"Música (mp3) [{est.get('musica', '')}]: ").strip().strip('"') or est.get("musica", "")
        preparar(argparse.Namespace(originales=o, musica=m, proxies=None, titulo=None, proposito=None, rehacer=False,
                                    sin_analisis=False, con_actos=False, sin_borrador=False, no_abrir=False,
                                    publicar=False, si=False))
    elif op == "2":
        listo(argparse.Namespace(decisiones=None, dissolve=12, final_mp4="1920x1080", sin_final=False,
                                 sin_premiere=False, publicar=False, si=False, no_abrir=False))
    elif op == "3":
        publicar_cmd(argparse.Namespace(decisiones=None, si=False))
    elif op == "4":
        proxies_cmd(argparse.Namespace(originales=None, proxies=None, forzar=False, verificar=False))
    elif op == "5":
        estado_cmd(None)
        if (SALIDA / "plan_borrador.json").is_file():
            resumen_cmd(None)


def main() -> None:
    if len(sys.argv) == 1:
        return menu()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preparar", help="de los originales a la propuesta y el visor HTML")
    p.add_argument("--originales", type=Path)
    p.add_argument("--musica", type=Path)
    p.add_argument("--proxies", type=Path, help="por defecto <originales>\\Proxies")
    p.add_argument("--titulo")
    p.add_argument("--proposito", help="para qué es el vídeo; guía a la IA")
    p.add_argument("--rehacer", action="store_true", help="repetir pasos aunque ya estén hechos")
    p.add_argument("--sin-analisis", action="store_true", help="saltar el análisis de notas (más rápido, menos criterio)")
    p.add_argument("--con-actos", action="store_true", help="añadir la clasificación por etapas de la IA (pista débil, +8 min)")
    p.add_argument("--sin-borrador", action="store_true")
    p.add_argument("--no-abrir", action="store_true")
    p.add_argument("--publicar", action="store_true", help="al terminar, subir el visor a GitHub (pregunta antes)")
    p.add_argument("--si", action="store_true", help="con --publicar: no preguntar")
    p.set_defaults(fn=preparar)
    p = sub.add_parser("listo", help="aplica tus decisiones: vídeo, XML, Premiere y resumen")
    p.add_argument("decisiones", nargs="?", help="por defecto, el más reciente de Descargas")
    p.add_argument("--dissolve", type=int, default=12)
    p.add_argument("--final-mp4", default="1920x1080", metavar="WxH")
    p.add_argument("--sin-final", action="store_true", help="no renderizar el vídeo final desde los originales")
    p.add_argument("--sin-premiere", action="store_true")
    p.add_argument("--publicar", action="store_true")
    p.add_argument("--si", action="store_true")
    p.add_argument("--no-abrir", action="store_true")
    p.set_defaults(fn=listo)
    p = sub.add_parser("proxies", help="crea o verifica los proxies")
    p.add_argument("--originales", type=Path)
    p.add_argument("--proxies", type=Path)
    p.add_argument("--forzar", action="store_true")
    p.add_argument("--verificar", action="store_true")
    p.set_defaults(fn=proxies_cmd)
    p = sub.add_parser("publicar", help="sube el visor a GitHub (rama + PR)")
    p.add_argument("decisiones", nargs="?")
    p.add_argument("--si", action="store_true")
    p.set_defaults(fn=publicar_cmd)
    sub.add_parser("resumen").set_defaults(fn=resumen_cmd)
    sub.add_parser("estado").set_defaults(fn=estado_cmd)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
