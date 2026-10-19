#!/usr/bin/env python3
"""
spa_atributos.py — Paso 3b: preguntas concretas de sí/no sobre cada plano distinto.

Un modelo de visión pequeño acierta mucho más con preguntas simples ("¿hay vapor?") que eligiendo
una etapa entre doce. Aquí se extraen atributos; la etapa de la historia se decide después con
reglas + el orden de rodaje (spa_proponer.py).
Salida: cache/atributos.json   {id_grupo: {atributo: bool, ...}}   (reanudable)
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).parent))
from spa_actos import ollama_url, sheet  # noqa: E402

HERE = Path(__file__).parent

PROMPT = """La imagen es una tira de 6 fotogramas consecutivos de un clip de un spa.
Responde SOLO con JSON; cada campo es true o false según lo que se ve en la mayoría de fotogramas:
{"hay_persona": hay una persona visible,
 "persona_de_pie": la persona está de pie (no acostada ni sentada),
 "persona_caminando": la persona avanza caminando,
 "persona_acostada": la persona está acostada o recostada en una camilla,
 "frente_a_espejo": la persona está frente a un espejo (se ve su reflejo o está de espaldas ante él),
 "piedras_negras_sobre_cuerpo": hay piedras negras redondas colocadas sobre el cuerpo,
 "vapor_o_niebla": hay vapor o niebla sobre el rostro,
 "mascarilla_en_rostro": el rostro lleva una mascarilla (LED, de tela o de crema),
 "manos_aplicando_producto": unas manos aplican crema, suero o dan masaje en la piel,
 "terapeuta_visible": se ve a una profesional con gorro o uniforme trabajando,
 "sonrisa_a_camara": una o más personas sonríen mirando a la cámara,
 "solo_objetos": solo se ven objetos o el ambiente, sin ninguna persona,
 "bata_negra": la persona viste bata o capa negra}"""

CAMPOS = ["hay_persona", "persona_de_pie", "persona_caminando", "persona_acostada", "frente_a_espejo",
          "piedras_negras_sobre_cuerpo", "vapor_o_niebla", "mascarilla_en_rostro",
          "manos_aplicando_producto", "terapeuta_visible", "sonrisa_a_camara", "solo_objetos", "bata_negra"]


def ask(model: str, img: bytes, retries: int = 2) -> dict:
    body = {"model": model, "prompt": PROMPT, "stream": False, "format": "json", "think": False,
            "options": {"temperature": 0.0}, "images": [base64.b64encode(img).decode()]}
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
    args = ap.parse_args()

    grupos = json.loads((args.cache / "grupos.json").read_text(encoding="utf-8"))["grupos"]
    out_path = args.cache / "atributos.json"
    res = json.loads(out_path.read_text(encoding="utf-8")) if out_path.is_file() else {}
    pend = [(g["id"], next(c for c in g["clips"] if c["nombre"] == g["defecto"]))
            for g in grupos if g["id"] not in res]
    print(f"{len(grupos)} planos ({len(grupos) - len(pend)} ya hechos)", flush=True)

    for n, (gid, c) in enumerate(pend, 1):
        r = ask(args.modelo, sheet(args.cache / "frames", c["frames"]))
        attrs = {k: bool(r.get(k, False)) for k in CAMPOS}
        res[gid] = attrs
        out_path.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
        on = ",".join(k for k, v in attrs.items() if v)
        print(f"[{n}/{len(pend)}] {gid} {c['stem']}  {on}", flush=True)
    print("OK", flush=True)


if __name__ == "__main__":
    main()
