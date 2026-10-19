#!/usr/bin/env python3
"""
spa_proponer.py — Paso 4: arma la propuesta de montaje (qué planos, en qué orden, con qué duración).

  1. Etapa de cada plano distinto: reglas sobre los atributos de spa_atributos.py + orden de rodaje.
  2. Por etapa elige los planos mejor puntuados hasta llenar su presupuesto de duración.
  3. Cada plano dura 4 beats (o 8 si es el plano estrella de la etapa), para que cada corte caiga
     en la rejilla de la música.
Salida:
  cache/propuesta.json            todo lo que necesita el HTML
  salida/decisiones_iniciales.json   la propuesta en el mismo formato que exporta el HTML
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spa_lib import ACTOS, ACTO_IDS, CACHE, HERE, carpeta_de, load_json  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

NARRATIVOS = {"entrada", "espejo", "pasillo", "sube_camilla", "cierre"}   # la nota "de promo" no aplica
ESTRELLA = {"piedras", "vapor", "mascarilla", "cremas", "ambiente"}
TRATAMIENTO = ("piedras_negras_sobre_cuerpo", "vapor_o_niebla", "mascarilla_en_rostro", "manos_aplicando_producto")


def acto_de(a: dict, idx: int, n: int) -> str:
    if a.get("solo_objetos") or not a.get("hay_persona"):
        return "ambiente"
    if a.get("sonrisa_a_camara") and idx >= int(n * 0.85):
        return "cierre"
    de_pie, acostada = a.get("persona_de_pie"), a.get("persona_acostada")
    if de_pie and not acostada:
        if a.get("persona_caminando"):
            return "pasillo"
        if a.get("frente_a_espejo"):
            return "espejo"
        if a.get("terapeuta_visible"):
            return "otros"
        return "entrada"
    if a.get("frente_a_espejo") and not acostada:
        return "espejo"
    if a.get("piedras_negras_sobre_cuerpo"):
        return "piedras"
    if a.get("vapor_o_niebla"):
        return "vapor"
    if a.get("mascarilla_en_rostro"):
        return "mascarilla"
    if a.get("manos_aplicando_producto"):
        return "cremas"
    if acostada:
        return "sube_camilla" if a.get("bata_negra") else "otros"
    return "otros"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--analisis", type=Path, default=Path(r"C:\Claude\beat-montage\footage_spa\footage_log.json"))
    ap.add_argument("--max-seg", type=float, default=110.0, help="duración máxima del spot (s)")
    args = ap.parse_args()

    grupos = load_json(CACHE / "grupos.json")["grupos"]
    attrs_clip = load_json(CACHE / "atributos_clip.json")
    vlm_clip = load_json(CACHE / "actos_clip.json") if (CACHE / "actos_clip.json").is_file() else {}
    ov = load_json(HERE / "overrides.json") if (HERE / "overrides.json").is_file() else {}
    ov_acto, ov_inicio, ov_prio = ov.get("acto", {}), ov.get("inicio_s", {}), ov.get("prioridad", {})
    beats = load_json(CACHE / "beats.json")
    bl = beats["beats"]
    spb = (bl[-1] - bl[0]) / (len(bl) - 1)   # espaciado real de los beats (no el BPM nominal)
    ana = {c["nombre"]: c for c in load_json(args.analisis)["clips"]}
    n = len(grupos)

    planos = {}
    for gi, g in enumerate(grupos):
        rep = next(c for c in g["clips"] if c["nombre"] == g["defecto"])
        miembros = [rep["nombre"]] + [c["nombre"] for c in g["clips"] if c["nombre"] != rep["nombre"]]
        a = next((attrs_clip[m] for m in miembros if m in attrs_clip), {})
        v = next((vlm_clip[m] for m in miembros if m in vlm_clip), {})
        acto = acto_de(a, gi, n) if a else v.get("acto", "otros")
        stems = [c["stem"] for c in g["clips"]]
        manual = next((ov_acto[s_] for s_ in stems if s_ in ov_acto), None)
        if manual:
            acto = manual
        info = ana.get(rep["nombre"], {})
        # una IA que dice "descartar" y una nota de promo muy baja => fuera (salvo etapas narrativas)
        if not manual and acto not in NARRATIVOS and (v.get("acto") == "descartar" or info.get("puntuacion_promo", 5) <= 1):
            acto = "descartar"
        mm = [m for m in info.get("mejores_momentos", []) if isinstance(m, dict)]
        inicio = float(mm[0]["inicio_s"]) if mm and mm[0].get("inicio_s") is not None else 0.4
        for s_ in stems:
            if s_ in ov_inicio:
                inicio = float(ov_inicio[s_])
        planos[g["id"]] = {
            "id": g["id"], "orden_rodaje": gi, "acto": acto, "acto_ia": v.get("acto", ""), "ajuste_manual": bool(manual), "stems": stems,
            "toma": g["defecto"], "inicio_s": round(max(0.0, inicio), 2), "beats": 4, "incluir": False,
            "nota": rep["nota"], "resumen": rep["resumen"], "atributos": [k for k, v in a.items() if v],
            "similitud": g["similitud"], "carpeta": carpeta_de(g),
            "tomas": [{"nombre": c["nombre"], "stem": c["stem"], "duracion_s": c["duracion_s"],
                       "nota": c["nota"], "ruta": c["ruta"],
                       "rel": f"{carpeta_de(g)}/{c['nombre']}",
                       "frames": [f"cache/frames/{f}" for f in c["frames"]]} for c in g["clips"]],
        }

    # ---- selección por etapa ----
    spb_beats = lambda s: max(2, int(round(s / spb)))
    for acto_id, _t, presupuesto, _c in ACTOS:
        if presupuesto <= 0:
            continue
        cands = [p for p in planos.values() if p["acto"] == acto_id]
        rep_dur = lambda p: next(t["duracion_s"] for t in p["tomas"] if t["nombre"] == p["toma"])
        prio = ov_prio.get(acto_id, [])
        rank = lambda p: min((prio.index(s_) for s_ in p["stems"] if s_ in prio), default=len(prio))
        if acto_id in NARRATIVOS:
            cands.sort(key=lambda p: (-rank(p) if prio else 0, min(rep_dur(p), 12.0), p["nota"]), reverse=True)
        else:
            cands.sort(key=lambda p: (p["nota"], min(rep_dur(p), 12.0)), reverse=True)
        cands = [p for p in cands if rep_dur(p) >= 2.2] or cands
        budget, used, chosen = spb_beats(presupuesto), 0, []
        for p in cands:
            if used >= budget:
                break
            b = 8 if (not chosen and acto_id in ESTRELLA and rep_dur(p) >= 7.0) else 4
            p["beats"] = b
            chosen.append(p)
            used += b
        for p in chosen:
            p["incluir"] = True

    # recorte de seguridad al máximo de duración
    incl = sorted((p for p in planos.values() if p["incluir"]),
                  key=lambda p: (ACTO_IDS.index(p["acto"]), p["orden_rodaje"]))
    total = 0.0
    for p in incl:
        if total + p["beats"] * spb > args.max_seg:
            p["incluir"] = False
        else:
            total += p["beats"] * spb

    orden = [p for p in sorted(planos.values(), key=lambda p: (ACTO_IDS.index(p["acto"]), p["orden_rodaje"]))]
    decisiones = [{"plano": p["id"], "toma": p["toma"], "inicio_s": p["inicio_s"], "beats": p["beats"],
                   "acto": p["acto"]} for p in orden if p["incluir"]]

    total_clips = sum(len(g["clips"]) for g in grupos)
    payload = {
        "proyecto": "Spot Spa — propuesta de montaje",
        "musica": {"ruta": beats["ruta"], "bpm": beats["bpm"], "spb": round(spb, 4), "duracion_s": beats["duracion_s"]},
        "actos": [{"id": a, "titulo": t, "presupuesto_s": p, "color": c} for a, t, p, c in ACTOS],
        "resumen": {"clips": total_clips, "planos": len(grupos),
                    "agrupados": total_clips - len(grupos),
                    "grupos_repetidos": sum(1 for g in grupos if len(g["clips"]) > 1)},
        "planos": orden,
    }
    (CACHE / "propuesta.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (HERE / "salida").mkdir(exist_ok=True)
    (HERE / "salida" / "decisiones_iniciales.json").write_text(
        json.dumps({"version": 1, "origen": "propuesta inicial", "orden": decisiones}, indent=2, ensure_ascii=False),
        encoding="utf-8")

    print(f"{len(decisiones)} planos propuestos, {total:.0f}s ({total / spb:.0f} beats @ {beats['bpm']} BPM)\n")
    for a, t, _p, _c in ACTOS:
        ps = [p for p in orden if p["acto"] == a]
        inc = [p for p in ps if p["incluir"]]
        print(f"{t:34s} {len(inc):2d} de {len(ps):2d} planos   "
              + " ".join(f"{p['toma'][:5]}{'*' if p['beats'] == 8 else ''}" for p in inc))


if __name__ == "__main__":
    main()
