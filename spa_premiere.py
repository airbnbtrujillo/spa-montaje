#!/usr/bin/env python3
"""
spa_premiere.py — Crea el proyecto de Premiere (.prproj) del spot, ORDENADO por etapas y por tomas.

Mismo método que AutoSync Multicam (el .prproj se crea DENTRO de Premiere, no desde Python):
  1. copia la plantilla .prproj en blanco de Premiere 2022 (la de AutoSync, solo se lee)
  2. un JSX, que se ejecuta con el ExtendScript Debugger de VS Code:
       - crea el proyecto nuevo "Spot Spa - organizado.prproj"
       - importa salida/spot.xml  (la secuencia con los cortes)
       - ordena el panel Proyecto: una carpeta por etapa de la historia y, dentro, una subcarpeta por
         cada plano con TOMAS REPETIDAS (los clips usados en la secuencia se mueven, los demás se importan)
       - guarda y deja el marcador "Spot Spa - organizado.importado.ok.txt"

    python spa_premiere.py [decisiones.json]   # prepara y lo lanza todo (Premiere + VS Code + F5)
    python spa_premiere.py --preparar          # solo prepara los archivos; lo lanzas tú

Con el modo automático NO toques el teclado hasta que termine: se envía F5 a la ventana de VS Code.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from spa_lib import ACTOS, CACHE, HERE, load_json  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PREMIERE_2022 = Path(r"C:\Program Files\Adobe\Adobe Premiere Pro 2022\Adobe Premiere Pro.exe")
NOMBRE = "Spot Spa"
PROYECTO = f"{NOMBRE} - organizado"


def _buscar_plantilla() -> Path:
    """Plantilla .prproj en blanco de Premiere 2022 (la de AutoSync Multicam). Se puede fijar con
    la variable de entorno SPA_PLANTILLA_PRPROJ; si no, se busca bajo Documents\\Codex."""
    env = os.environ.get("SPA_PLANTILLA_PRPROJ")
    if env:
        return Path(env)
    hallazgos = sorted(Path.home().glob("Documents/Codex/*/*/templates/Premiere2022_blank_22.4.prproj"))
    return hallazgos[0] if hallazgos else Path("Premiere2022_blank_22.4.prproj")


TEMPLATE = _buscar_plantilla()

JSX = r"""/* Crea el proyecto del spot: importa el XML y ordena el panel Proyecto por etapas y tomas. */
(function () {
    var C = __CONFIG__;
    function writeFile(path, text) {
        var f = new File(path);
        f.encoding = "UTF-8";
        if (f.open("w")) { f.write(text); f.close(); }
    }
    var paso = "inicio";
    function log(msg) {
        var f = new File(C.log);
        f.encoding = "UTF-8";
        if (f.open("a")) { f.writeln((new Date()).toTimeString().substr(0, 8) + "  " + msg); f.close(); }
    }
    function norm(p) { return String(p || "").replace(/\\/g, "/").toLowerCase(); }
    function ensureBin(parent, name) {
        var i, ch;
        for (i = 0; i < parent.children.numItems; i++) {
            ch = parent.children[i];
            if (ch && ch.type === ProjectItemType.BIN && ch.name === name) { return ch; }
        }
        return parent.createBin(name);
    }
    function visit(item, fn) {
        var i;
        if (!item) { return; }
        fn(item);
        try {
            if (item.children) {
                for (i = 0; i < item.children.numItems; i++) { visit(item.children[i], fn); }
            }
        } catch (e) {}
    }
    function findItem(path) {
        var wanted = norm(path), found = null;
        visit(app.project.rootItem, function (it) {
            var p = "";
            if (found) { return; }
            try { p = norm(it.getMediaPath()); } catch (e) {}
            if (p === wanted) { found = it; }
        });
        return found;
    }
    try {
        log("inicio");
        if (new File(C.marker).exists) { $.writeln("Este paquete ya se importo: " + C.marker); return; }
        var xmlFile = new File(C.xml);
        if (!xmlFile.exists) { throw new Error("No encuentro el XML: " + C.xml); }
        // conservar lo que hubiera abierto y crear el proyecto nuevo
        var actual = (app.project && app.project.path) ? norm(app.project.path) : "";
        if (actual && actual !== norm(C.project) && actual.indexOf(norm(C.carpeta)) !== 0) {
            throw new Error("Hay otro proyecto abierto en Premiere (" + app.project.path + "). No lo cierro: guardalo y cierralo tu, y vuelve a ejecutar.");
        }
        if (actual && actual !== norm(C.project)) {
            paso = "guardar y cerrar el proyecto base";
            try { app.project.save(); } catch (e0) {}
            try { app.project.closeDocument(0, 0); } catch (e1) {}
            log("proyecto anterior guardado y cerrado");
        }
        paso = "crear el proyecto nuevo";
        if (!app.project || norm(app.project.path) !== norm(C.project)) { app.newProject(new File(C.project).fsName); }
        log("proyecto nuevo creado: " + new File(C.project).fsName);
        paso = "importar el XML";

        var before = app.project.sequences.numSequences;
        app.project.importFiles([xmlFile.fsName], true, app.project.rootItem, false);
        var seq = null, i, a, g, c, k;
        for (i = 0; i < app.project.sequences.numSequences; i++) {
            if (app.project.sequences[i].name == C.sequence) { seq = app.project.sequences[i]; }
        }
        if (!seq && app.project.sequences.numSequences > before) {
            seq = app.project.sequences[app.project.sequences.numSequences - 1];
        }
        if (!seq) { throw new Error("Premiere no dejo ninguna secuencia detectable tras importar el XML."); }
        log("XML importado; secuencia: " + seq.name);
        paso = "ordenar el panel Proyecto";

        // ---- orden del panel Proyecto: etapa > (subcarpeta por plano con tomas repetidas) > clips ----
        var root = app.project.rootItem, moved = 0, imported = 0, total = 0, bins = 0;
        for (a = 0; a < C.actos.length; a++) {
            var bin = ensureBin(root, C.actos[a].nombre); bins++;
            for (g = 0; g < C.actos[a].grupos.length; g++) {
                var grupo = C.actos[a].grupos[g];
                var target = grupo.clips.length > 1 ? ensureBin(bin, grupo.nombre) : bin;
                if (grupo.clips.length > 1) { bins++; }
                var pend = [];
                for (k = 0; k < grupo.clips.length; k++) {
                    c = grupo.clips[k]; total++;
                    var it = findItem(c.ruta);
                    if (it) {
                        try { it.moveBin(target); moved++; } catch (eMove) { pend.push(c.ruta); }
                    } else { pend.push(c.ruta); }
                }
                if (pend.length) {
                    try { app.project.importFiles(pend, true, target, false); imported += pend.length; } catch (eImp) {}
                }
            }
        }
        log("carpetas: " + bins + ", clips movidos " + moved + ", importados " + imported + " de " + total);
        paso = "guardar";
        try { app.project.openSequence(seq.sequenceID); } catch (e2) {}
        app.project.save();
        log("guardado");
        writeFile(C.marker, "OK\n" + (new Date()).toString() + "\nsecuencia: " + seq.name +
                  "\ncarpetas: " + bins + "\nclips: " + total + " (movidos " + moved + ", importados " + imported + ")" +
                  "\nproyecto: " + C.project + "\n");
    } catch (err) {
        log("ERROR en el paso '" + paso + "': " + String(err));
        writeFile(C.error, "paso: " + paso + "\n" + String(err));
        // sin alert(): una ventana abierta bloquearia todos los scripts siguientes de Premiere
    }
})();
"""


def fwd(p) -> str:
    return str(p).replace("\\", "/")


def estructura(decisiones: Path) -> list[dict]:
    """Etapas -> planos (carpetas) -> clips, con las decisiones del autor aplicadas."""
    P = load_json(CACHE / "propuesta.json")
    dec = load_json(decisiones)
    dec = dec["orden"] if isinstance(dec, dict) else dec
    pos = {d["plano"]: i for i, d in enumerate(dec)}
    acto_de = {p["id"]: (dec[pos[p["id"]]]["acto"] if p["id"] in pos else p["acto"]) for p in P["planos"]}
    titulos = {a[0]: a[1] for a in ACTOS}
    out = []
    for aid, titulo, _pres, _col in ACTOS:
        ps = [p for p in P["planos"] if acto_de[p["id"]] == aid]
        if not ps:
            continue
        ps.sort(key=lambda p: (0 if p["id"] in pos else 1, pos.get(p["id"], p["orden_rodaje"])))
        nombre = re.sub(r"^(\d+) ·", lambda m: f"{int(m.group(1)):02d} ·", titulo)
        if aid == "descartar":
            nombre = "99 · Descartados"
        grupos = []
        for p in ps:
            tomas = p["tomas"]
            usada = dec[pos[p["id"]]]["toma"] if p["id"] in pos else p["toma"]
            tomas = sorted(tomas, key=lambda t: t["nombre"] != usada)   # la usada primero
            grupos.append({"nombre": f"{p['id']} · " + " + ".join(t["stem"] for t in tomas),
                           "clips": [{"nombre": t["nombre"], "ruta": fwd(t["ruta"])} for t in tomas]})
        out.append({"nombre": nombre, "grupos": grupos})
    return out


def preparar(out: Path, xml: Path, decisiones: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    if not TEMPLATE.is_file():
        sys.exit(f"ERROR: no encuentro la plantilla de Premiere 2022: {TEMPLATE}")
    if not xml.is_file():
        sys.exit(f"ERROR: no existe {xml}. Ejecuta antes spa_aplicar.py")
    base = out / f"{NOMBRE} - base.prproj"
    prproj = out / f"{PROYECTO}.prproj"
    marker = out / f"{PROYECTO}.importado.ok.txt"
    error = out / f"{PROYECTO}.importado.error.txt"
    xml_dst = out / "spot.xml"
    shutil.copy2(TEMPLATE, base)             # la plantilla de AutoSync solo se lee
    shutil.copy2(xml, xml_dst)
    for f in (marker, error, prproj, out / f"{PROYECTO}.log.txt"):
        f.unlink(missing_ok=True)

    cfg = {"project": fwd(prproj), "xml": fwd(xml_dst), "marker": fwd(marker), "error": fwd(error),
           "log": fwd(out / f"{PROYECTO}.log.txt"), "carpeta": fwd(out), "sequence": NOMBRE, "actos": estructura(decisiones)}
    jsx = out / "crear_proyecto_organizado.jsx"
    jsx.write_text(JSX.replace("__CONFIG__", json.dumps(cfg, indent=2, ensure_ascii=True)), encoding="utf-8")

    bat = out / "ABRIR_PREMIERE_2022.bat"
    bat.write_text(f"""@echo off
setlocal
set "PREMIERE={PREMIERE_2022}"
set "PRPROJ={base}"
if not exist "%PRPROJ%" (
  echo No encuentro el proyecto base: "%PRPROJ%"
  pause
  exit /b 1
)
start "Premiere 2022 Spot Spa" "%PREMIERE%" "%PRPROJ%"
exit /b 0
""", encoding="utf-8")

    launch = {"version": "0.2.0", "configurations": [{
        "type": "extendscript-debug", "request": "launch", "name": "Crear proyecto del spot en Premiere",
        "hostAppSpecifier": "premierepro-22.0", "engineName": "NewWorld",
        "script": "${workspaceFolder}/crear_proyecto_organizado.jsx", "bringToFront": True}]}
    (out / ".vscode").mkdir(exist_ok=True)
    (out / ".vscode" / "launch.json").write_text(json.dumps(launch, indent=2), encoding="utf-8")
    ws = out / "Spot_Spa_organizar.code-workspace"
    ws.write_text(json.dumps({"folders": [{"path": "."}], "launch": launch}, indent=2), encoding="utf-8")

    (out / "LEEME.txt").write_text(
        "Crear el proyecto de Premiere del spot, ordenado por etapas y tomas (método de AutoSync)\n\n"
        "Automático:   python spa_premiere.py\n\n"
        "A mano:\n"
        "  1. Doble clic en ABRIR_PREMIERE_2022.bat (abre un proyecto base).\n"
        "  2. Abre Spot_Spa_organizar.code-workspace con VS Code y pulsa F5.\n"
        "  3. Al terminar aparece 'Spot Spa - organizado.importado.ok.txt' y el proyecto 'Spot Spa - organizado.prproj'\n"
        "     tiene la secuencia 'Spot Spa' y el panel Proyecto ordenado: una carpeta por etapa y, dentro,\n"
        "     una subcarpeta por cada plano con tomas repetidas.\n\n"
        "Sin VS Code: en Premiere, File > Import > spot.xml (sin carpetas).\n"
        "El XML apunta a los PROXIES (F:\\Video Spa\\Proxies): para el final, clic derecho > Link Media.\n",
        encoding="utf-8")
    return {"prproj": prproj, "marker": marker, "error": error, "bat": bat, "ws": ws, "jsx": jsx}


def ventana_lista(proceso: str, texto: str) -> bool:
    q = (f"@(Get-Process '{proceso}' -ErrorAction SilentlyContinue | "
         f"Where-Object {{ $_.MainWindowTitle -like '*{texto}*' -and $_.Responding }}).Count")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", q], capture_output=True, text=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.stdout.strip() not in ("", "0")


def esperar(cond, segundos: int, cada: float = 3.0) -> bool:
    fin = time.time() + segundos
    while time.time() < fin:
        if cond():
            return True
        time.sleep(cada)
    return False


def automatico(d: dict) -> bool:
    code = shutil.which("code.cmd") or shutil.which("code")
    if not code:
        print("No encuentro VS Code: usa --preparar y sigue LEEME.txt.")
        return False
    ws_stem = d["ws"].stem
    titulo = subprocess.run(["powershell", "-NoProfile", "-Command",
                             "(Get-Process 'Adobe Premiere Pro' -ErrorAction SilentlyContinue | "
                             "Select-Object -First 1).MainWindowTitle"], capture_output=True, text=True).stdout.strip()
    if ".prproj" in titulo and str(d["prproj"].parent).lower() not in titulo.lower():
        print("Premiere tiene abierto OTRO proyecto, que no toco:\n  " + titulo +
              "\nGuárdalo y ciérralo (o cierra Premiere) y vuelve a ejecutar, o sigue LEEME.txt a mano.")
        return False
    if not ventana_lista("Adobe Premiere Pro", NOMBRE):
        print("Abriendo Premiere 2022 (puede tardar varios minutos)...", flush=True)
        os.startfile(str(d["bat"]))
        if not esperar(lambda: ventana_lista("Adobe Premiere Pro", NOMBRE), 420):
            print("Premiere no terminó de abrir el proyecto en 7 minutos.")
            return False
        time.sleep(8)  # el título aparece un poco antes de que responda el host de scripting
    else:
        print("Premiere ya está abierto: se reutiliza (el proyecto actual se guarda antes de cerrarlo).", flush=True)
    print("Abriendo VS Code...", flush=True)
    subprocess.Popen([code, "-r", str(d["ws"]), str(d["jsx"])], shell=False)
    if not esperar(lambda: ventana_lista("Code", ws_stem), 90, 2.0):
        print("VS Code no abrió el workspace. Ábrelo tú y pulsa F5.")
        return False
    time.sleep(6)  # el ExtendScript Debugger necesita un momento
    f5 = ("$ws = New-Object -ComObject WScript.Shell; "
          f"$p = Get-Process Code | Where-Object {{ $_.MainWindowTitle -like '*{ws_stem}*' }} | Select-Object -First 1; "
          "if ($p -and $ws.AppActivate($p.Id)) { Start-Sleep -Milliseconds 900; $ws.SendKeys('+{F5}'); Start-Sleep -Milliseconds 2500; $ws.SendKeys('{F5}'); 'ok' }")  # Mayús+F5 para una sesión previa, luego F5
    for intento in (1, 2):
        r = subprocess.run(["powershell", "-NoProfile", "-Command", f5], capture_output=True, text=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        print(f"F5 enviado a VS Code (intento {intento})." if r.stdout.strip() == "ok"
              else "No pude activar la ventana de VS Code.", flush=True)
        if esperar(lambda: d["marker"].exists() or d["error"].exists(), 180 if intento == 1 else 300):
            break
    if d["marker"].exists():
        print("OK: Premiere creó el proyecto.\n" + d["marker"].read_text(encoding="utf-8", errors="replace"))
        return True
    if d["error"].exists():
        print("Premiere devolvió un error:", d["error"].read_text(encoding="utf-8", errors="replace"))
    else:
        print("Premiere no confirmó la importación. Mira si muestra un aviso; si no, pulsa F5 en VS Code.")
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("decisiones", nargs="?", type=Path, default=HERE / "decisiones" / "decisiones_2026-10-19.json")
    ap.add_argument("--xml", type=Path, default=HERE / "salida" / "spot.xml")
    ap.add_argument("--salida", type=Path, default=HERE / "salida" / "premiere")
    ap.add_argument("--preparar", action="store_true", help="solo prepara los archivos, no lanza nada")
    args = ap.parse_args()

    d = preparar(args.salida, args.xml, args.decisiones)
    cfg = re.search(r"var C = (\{.*?\n\});", d["jsx"].read_text(encoding="utf-8"), re.S)
    actos = json.loads(cfg.group(1))["actos"] if cfg else []
    print(f"Paquete en {args.salida}")
    print(f"  carpetas por etapa: {len(actos)} | planos: {sum(len(a['grupos']) for a in actos)} | "
          f"clips: {sum(len(g['clips']) for a in actos for g in a['grupos'])}")
    if not args.preparar:
        sys.exit(0 if automatico(d) else 1)


if __name__ == "__main__":
    main()
