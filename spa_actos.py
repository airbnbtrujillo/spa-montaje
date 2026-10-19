#!/usr/bin/env python3
"""
spa_actos.py — Paso 3: asigna cada plano distinto a una etapa de la historia del spot.

Para el clip "por defecto" de cada grupo arma una tira de 6 fotogramas y pregunta al modelo de
visión local (Ollama, qwen2.5vl) a qué etapa pertenece. Reanudable: guarda tras cada plano.
Salida: cache/actos.json   {id_grupo: {"acto": ..., "motivo": ...}}
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).parent

# id -> (título, pista para el modelo)
ACTOS = {
    "ambiente":    ("Ambiente del spa", "espacio del spa SIN persona protagonista: decoración, camilla vacía, velas, piedras, frascos, perfume, espejo de mesa, mascarilla puesta en un maniquí"),
    "entrada":     ("La chica llega", "la chica llega, se la ve de frente o de perfil, de pie, en la puerta, entrada o recepción"),
    "espejo":      ("La chica frente al espejo", "la chica frente a un espejo, arreglándose el pelo o mirándose; suele verse de espaldas con bata negra en un baño con azulejos"),
    "pasillo":     ("Camina por el pasadizo", "la chica caminando por un pasillo o corredor, de cuerpo entero, avanzando"),
    "sube_camilla": ("Sube a la camilla", "la chica se sube o se recuesta en la camilla; primeros momentos acostándose, toallas, bata"),
    "piedras":     ("Piedras calientes", "piedras volcánicas negras colocadas sobre la espalda o el cuerpo"),
    "vapor":       ("Vapor facial", "vapor o niebla sobre el rostro, ojos tapados con almohadillas blancas"),
    "mascarilla":  ("Mascarilla", "mascarilla facial puesta en el rostro: de luz LED, de tela o de crema"),
    "cremas":      ("Cremas y masaje facial", "las manos de la terapeuta aplicando cremas, sueros o lociones, o masaje facial"),
    "otros":       ("Otros tratamientos", "otro tratamiento: pies, masaje con aparato, cabello, secador de pelo, cuerpo"),
    "cierre":      ("Cierre", "sonrisas a cámara, despedida, resultado final feliz"),
    "descartar":   ("Descartar", "no sirve: borroso, sin relación con el spa, animales, paisajes, plano vacío o feo"),
}

PROMPT = """Eres editor de un spot publicitario de un spa. La imagen es una tira de 6 fotogramas \
consecutivos de un mismo clip.
Elige UNA etapa de la historia a la que pertenece el clip:
{lista}
Responde SOLO con JSON: {{"acto":"<id>","motivo":"<máximo 12 palabras>"}}"""


def ollama_url() -> str:
    h = os.environ.get("OLLAMA_HOST", "").strip() or "http://127.0.0.1:11434"
    if "://" not in h:
        h = "http://" + h
    return h.rstrip("/").replace("//0.0.0.0:", "//127.0.0.1:")


def sheet(frames_dir: Path, frames: list[str]) -> bytes:
    ims = [Image.open(frames_dir / f) for f in frames]
    w, h = ims[0].size
    cols = 3
    rows = (len(ims) + cols - 1) // cols
    out = Image.new("RGB", (w * cols, h * rows), "black")
    for i, im in enumerate(ims):
        out.paste(im, ((i % cols) * w, (i // cols) * h))
    buf = io.BytesIO()
    out.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def ask(model: str, img: bytes, retries: int = 2) -> dict:
    lista = "\n".join(f"- {k}: {v[1]}" for k, v in ACTOS.items())
    body = {"model": model, "prompt": PROMPT.format(lista=lista), "stream": False, "format": "json",
            "think": False, "options": {"temperature": 0.1},
            "images": [base64.b64encode(img).decode()]}
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(ollama_url() + "/api/generate", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as r:
                txt = json.loads(r.read())["response"]
            m = re.search(r"\{.*\}", txt, re.S)
            return json.loads(m.group()) if m else {}
        except Exception as e:  # noqa: BLE001
            print(f"  ! reintento ({e})", flush=True)
            time.sleep(2 + attempt * 3)
    return {}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache", type=Path, default=HERE / "cache")
    ap.add_argument("--modelo", default="qwen2.5vl:7b")
    ap.add_argument("--todos", action="store_true", help="clasificar todos los clips, no solo el de cada grupo")
    args = ap.parse_args()

    grupos = json.loads((args.cache / "grupos.json").read_text(encoding="utf-8"))["grupos"]
    out_path = args.cache / "actos.json"
    res = json.loads(out_path.read_text(encoding="utf-8")) if out_path.is_file() else {}

    jobs = []
    for g in grupos:
        for c in g["clips"]:
            if args.todos or c["nombre"] == g["defecto"]:
                jobs.append((g["id"] if not args.todos else c["stem"], c))
    pend = [(k, c) for k, c in jobs if k not in res]
    print(f"{len(jobs)} clips a clasificar ({len(jobs) - len(pend)} ya hechos)", flush=True)

    for n, (key, c) in enumerate(pend, 1):
        r = ask(args.modelo, sheet(args.cache / "frames", c["frames"]))
        acto = str(r.get("acto", "")).strip().lower()
        if acto not in ACTOS:
            acto = "otros"
        res[key] = {"acto": acto, "motivo": str(r.get("motivo", "")), "clip": c["nombre"]}
        out_path.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[{n}/{len(pend)}] {key} {c['stem']} -> {acto:12s} {res[key]['motivo'][:70]}", flush=True)
    print("OK", flush=True)


if __name__ == "__main__":
    main()
