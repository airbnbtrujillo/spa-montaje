#!/usr/bin/env python3
"""
spa_publicar.py — Sube el visor de la propuesta a GitHub, al estilo del proyecto del Frontón:
rama + pull request (nunca directo a main) y el visor publicado con GitHub Pages desde la rama.

    python spa_publicar.py                    # pregunta antes de subir nada
    python spa_publicar.py --si               # confirma por ti (para usarlo desde otro programa)

Qué sube: el código, las decisiones, el visor estático docs/ (solo miniaturas, sin vídeos).
Qué NO sube: vídeos, música, fotogramas completos, proxies ni originales (ver .gitignore).
Antes de subir muestra el repositorio, si es público o privado y cuántas miniaturas de personas llevan.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spa_lib import BASE, HERE, load_json, ultima_decision  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(BASE), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def gh(*args: str, check: bool = True) -> str:
    exe = shutil.which("gh")
    if not exe:
        raise RuntimeError("falta la CLI de GitHub (gh)")
    r = subprocess.run([exe, *args], capture_output=True, text=True, cwd=BASE)
    if check and r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}: {(r.stderr or r.stdout).strip()}")
    return r.stdout.strip()


def datos_personales(archivos: list[str]) -> list[str]:
    """Busca en los archivos de texto que se van a subir el usuario de Windows, correos o rutas de otras unidades."""
    usuario = Path.home().name
    # (partidos para que este mismo archivo no se marque a sí mismo)
    patrones = [usuario, "@" + "gmail", "@" + "hotmail", "App" + "Data"]
    hallazgos = []
    for f in archivos:
        p = BASE / f
        if not p.is_file() or p.suffix.lower() in {".jpg", ".png", ".mp4", ".mp3"}:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat in patrones:
            if pat and pat in txt:
                hallazgos.append(f"{f}: contiene '{pat}'")
    return hallazgos


def publicar(decisiones: Path | None = None, si: bool = False, log=print) -> dict:
    decisiones = decisiones or ultima_decision()
    if not (BASE / ".git").exists():
        raise RuntimeError(f"{BASE} no es un repositorio git. Inicialízalo y crea el remoto antes de publicar.")
    if git("remote", check=False) == "":
        raise RuntimeError("el repositorio no tiene remoto (origin).")
    gh("auth", "status")

    log("Generando el visor estático (docs/)...")
    r = subprocess.run([sys.executable, str(HERE / "spa_html.py"), "--estatico", str(BASE / "docs"),
                        "--decisiones", str(decisiones)], capture_output=True, text=True,
                       env={**os.environ, "SPA_PROYECTO": str(BASE)})
    if r.returncode != 0:
        raise RuntimeError("spa_html.py falló: " + (r.stderr or r.stdout)[-400:])

    repo = json.loads(gh("repo", "view", "--json", "nameWithOwner,visibility,url"))
    rama = git("branch", "--show-current")
    if rama in ("main", "master", ""):
        rama = "propuesta-" + datetime.now().strftime("%Y%m%d")
        git("switch", "-c", rama) if git("branch", "--list", rama) == "" else git("switch", rama)
    candidatos = ["docs", "decisiones", "overrides.json", "README.md", "requirements.txt", ".gitignore",
                  "CREAR_PROYECTO_PREMIERE.bat", "SPOT_SPA.bat", "salida/premiere/LEEME.txt",
                  "salida/premiere/ABRIR_PREMIERE_2022.bat", "salida/premiere/crear_proyecto_organizado.jsx"]
    candidatos += [p.name for p in HERE.glob("*.py")]
    candidatos = [c for c in candidatos if (BASE / c).exists()]
    git("add", *candidatos)
    cambios = git("diff", "--cached", "--name-only").splitlines()
    n_img = sum(1 for c in cambios if c.startswith("docs/img/"))
    n_img_total = len(list((BASE / "docs" / "img").glob("*.jpg"))) if (BASE / "docs" / "img").is_dir() else 0
    alertas = datos_personales([c for c in cambios if not c.startswith("docs/img/")])

    log("\n=== Se va a subir ===")
    log(f"  repositorio : {repo['url']}  ({repo['visibility']})")
    log(f"  rama        : {rama}  (con pull request; nunca directo a main)")
    log(f"  archivos    : {len(cambios)} cambios ({n_img} miniaturas nuevas o modificadas; el visor lleva {n_img_total})")
    if n_img_total:
        aviso = "PÚBLICO: cualquiera verá las miniaturas de las personas del rodaje" if repo["visibility"].upper() == "PUBLIC" \
            else "privado: solo quienes tengan acceso verán las miniaturas"
        log(f"  miniaturas  : {aviso}")
    for a in alertas:
        log(f"  ⚠ datos personales: {a}")
    if alertas:
        git("reset", "-q", check=False)
        raise RuntimeError("se detectaron datos personales en el texto a subir; corrígelos y vuelve a ejecutar.")
    if not cambios:
        log("\nNo hay nada nuevo que subir.")
        return {"subido": False, "repo": repo["url"], "rama": rama}
    if not si:
        if not sys.stdin.isatty():
            git("reset", "-q", check=False)
            raise RuntimeError("necesito tu confirmación: ejecútalo en una terminal o pasa --si.")
        if input("\n¿Subo esto ahora? (s/N) ").strip().lower() not in ("s", "si", "sí", "y", "yes"):
            git("reset", "-q", check=False)
            log("Cancelado: no se subió nada.")
            return {"subido": False, "repo": repo["url"], "rama": rama}

    dur = ""
    try:
        d = load_json(decisiones)
        orden = d["orden"] if isinstance(d, dict) else d
        dur = f"{len(orden)} planos"
    except Exception:
        pass
    mensaje = ["-m", f"Actualiza la propuesta de montaje ({dur})"]
    if os.environ.get("SPA_COMMIT_EXTRA"):                  # texto opcional al final del mensaje (p. ej. autoría compartida)
        mensaje += ["-m", os.environ["SPA_COMMIT_EXTRA"]]
    git("commit", "-q", *mensaje)
    git("push", "-q", "-u", "origin", rama)
    pr = gh("pr", "list", "--head", rama, "--json", "url", "-q", ".[0].url", check=False)
    if not pr:
        pr = gh("pr", "create", "--base", "main", "--head", rama, "--title", f"Propuesta de montaje ({rama})",
                "--body", "Visor de la propuesta de montaje, tomas agrupadas y decisiones del autor.")
    nombre = repo["nameWithOwner"]
    pages = f"https://{nombre.split('/')[0]}.github.io/{nombre.split('/')[1]}/"
    if gh("api", f"repos/{nombre}/pages", check=False) == "":
        gh("api", "-X", "POST", f"repos/{nombre}/pages", "-f", f"source[branch]={rama}", "-f", "source[path]=/docs",
           check=False)
    log(f"\nSubido.\n  PR    : {pr}\n  Visor : {pages}  (GitHub tarda ~1 minuto en construirlo)")
    return {"subido": True, "repo": repo["url"], "rama": rama, "pr": pr, "pages": pages}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("decisiones", nargs="?", type=Path)
    ap.add_argument("--si", action="store_true", help="no preguntar (confirmas tú al usarlo desde otro programa)")
    a = ap.parse_args()
    try:
        publicar(a.decisiones, a.si)
    except RuntimeError as e:
        sys.exit(f"ERROR: {e}")


if __name__ == "__main__":
    main()
