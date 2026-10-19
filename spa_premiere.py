#!/usr/bin/env python3
"""
spa_premiere.py — Crea el proyecto de Premiere (.prproj) del spot con el mismo método que AutoSync.

AutoSync no escribe el .prproj desde Python: lo crea DENTRO de Premiere. Aquí se hace igual:
  1. copia la plantilla .prproj en blanco de Premiere 2022 (la de AutoSync, solo se lee) a
     salida/premiere/Spot Spa.prproj
  2. genera un JSX que importa salida/spot.xml en ese proyecto abierto, abre la secuencia, guarda
     y deja un marcador "Spot Spa.importado.ok.txt" (no importa dos veces)
  3. genera el .bat que abre Premiere 2022 con ese proyecto y el workspace de VS Code con la
     configuración del ExtendScript Debugger que ejecuta el JSX

    python spa_premiere.py              # prepara los archivos y lo lanza todo (Premiere + VS Code + F5)
    python spa_premiere.py --preparar   # solo prepara los archivos; lo lanzas tú (.bat, luego F5 en VS Code)

Con el modo automático NO toques el teclado hasta que termine: se envía F5 a la ventana de VS Code.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = Path(__file__).parent
def _buscar_plantilla() -> Path:
    """Plantilla .prproj en blanco de Premiere 2022 (la de AutoSync Multicam). Se puede fijar con
    la variable de entorno SPA_PLANTILLA_PRPROJ; si no, se busca bajo Documents\\Codex."""
    env = os.environ.get("SPA_PLANTILLA_PRPROJ")
    if env:
        return Path(env)
    hallazgos = sorted(Path.home().glob("Documents/Codex/*/*/templates/Premiere2022_blank_22.4.prproj"))
    return hallazgos[0] if hallazgos else Path("Premiere2022_blank_22.4.prproj")


TEMPLATE = _buscar_plantilla()
PREMIERE_2022 = Path(r"C:\Program Files\Adobe\Adobe Premiere Pro 2022\Adobe Premiere Pro.exe")
NOMBRE = "Spot Spa"

JSX = r"""/* Importa el XML del spot en el proyecto de Premiere abierto, guarda y deja un marcador. */
(function () {
    var C = __CONFIG__;
    function writeFile(path, text) {
        var f = new File(path);
        f.encoding = "UTF-8";
        if (f.open("w")) { f.write(text); f.close(); }
    }
    try {
        var marker = new File(C.marker);
        if (marker.exists) { $.writeln("Este paquete ya se importo: " + C.marker); return; }
        var xmlFile = new File(C.xml);
        if (!xmlFile.exists) { throw new Error("No encuentro el XML: " + C.xml); }
        if (!app.project) { throw new Error("No hay un proyecto abierto en Premiere."); }
        var before = app.project.sequences.numSequences;
        app.project.importFiles([xmlFile.fsName], true, app.project.rootItem, false);
        var seq = null, i;
        for (i = 0; i < app.project.sequences.numSequences; i++) {
            if (app.project.sequences[i].name == C.sequence) { seq = app.project.sequences[i]; }
        }
        if (!seq && app.project.sequences.numSequences > before) {
            seq = app.project.sequences[app.project.sequences.numSequences - 1];
        }
        if (!seq) { throw new Error("Premiere no dejo ninguna secuencia detectable tras importar el XML."); }
        try { app.project.openSequence(seq.sequenceID); } catch (e1) {}
        app.project.save();
        writeFile(C.marker, "OK\n" + (new Date()).toString() + "\nsecuencia: " + seq.name +
                  "\nproyecto: " + C.project + "\n");
    } catch (err) {
        writeFile(C.error, String(err));
        alert("No se pudo importar el XML en Premiere:\n" + String(err));
    }
})();
"""


def fwd(p: Path) -> str:
    return str(p).replace("\\", "/")


def preparar(out: Path, xml: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    if not TEMPLATE.is_file():
        sys.exit(f"ERROR: no encuentro la plantilla de Premiere 2022: {TEMPLATE}")
    if not xml.is_file():
        sys.exit(f"ERROR: no existe {xml}. Ejecuta antes spa_aplicar.py")
    prproj = out / f"{NOMBRE}.prproj"
    marker = out / f"{NOMBRE}.importado.ok.txt"
    error = out / f"{NOMBRE}.importado.error.txt"
    xml_dst = out / "spot.xml"
    shutil.copy2(TEMPLATE, prproj)          # la plantilla de AutoSync solo se lee
    shutil.copy2(xml, xml_dst)
    for f in (marker, error):
        f.unlink(missing_ok=True)

    cfg = {"project": fwd(prproj), "xml": fwd(xml_dst), "marker": fwd(marker), "error": fwd(error),
           "sequence": NOMBRE}
    jsx = out / "importar_xml_en_prproj_abierto.jsx"
    jsx.write_text(JSX.replace("__CONFIG__", json.dumps(cfg, indent=4)), encoding="utf-8")

    bat = out / "ABRIR_PREMIERE_2022.bat"
    bat.write_text(f"""@echo off
setlocal
set "PREMIERE={PREMIERE_2022}"
set "PRPROJ={prproj}"
if not exist "%PRPROJ%" (
  echo No encuentro el proyecto base: "%PRPROJ%"
  pause
  exit /b 1
)
start "Premiere 2022 Spot Spa" "%PREMIERE%" "%PRPROJ%"
exit /b 0
""", encoding="utf-8")

    launch = {"version": "0.2.0", "configurations": [{
        "type": "extendscript-debug", "request": "launch", "name": "Importar XML del spot en Premiere",
        "hostAppSpecifier": "premierepro-22.0", "engineName": "NewWorld",
        "script": "${workspaceFolder}/importar_xml_en_prproj_abierto.jsx", "bringToFront": True}]}
    (out / ".vscode").mkdir(exist_ok=True)
    (out / ".vscode" / "launch.json").write_text(json.dumps(launch, indent=2), encoding="utf-8")
    ws = out / "Spot_Spa_importar_xml.code-workspace"
    ws.write_text(json.dumps({"folders": [{"path": "."}], "launch": launch}, indent=2), encoding="utf-8")

    (out / "LEEME.txt").write_text(
        "Crear el proyecto de Premiere del spot (mismo método que AutoSync)\n\n"
        "Automático:   python spa_premiere.py\n\n"
        "A mano:\n"
        "  1. Doble clic en ABRIR_PREMIERE_2022.bat (abre el proyecto base 'Spot Spa.prproj').\n"
        "  2. Abre Spot_Spa_importar_xml.code-workspace con VS Code y pulsa F5.\n"
        "  3. Cuando termine aparece 'Spot Spa.importado.ok.txt' y el proyecto ya tiene la secuencia.\n\n"
        "Si prefieres no usar VS Code: en Premiere, File > Import > spot.xml.\n"
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
    if not ventana_lista("Adobe Premiere Pro", NOMBRE):
        print(f"Abriendo Premiere 2022 con {d['prproj'].name} (puede tardar varios minutos)...", flush=True)
        os.startfile(str(d["bat"]))
        if not esperar(lambda: ventana_lista("Adobe Premiere Pro", NOMBRE), 420):
            print("Premiere no terminó de abrir el proyecto en 7 minutos.")
            return False
        time.sleep(8)  # el título aparece un poco antes de que responda el host de scripting
    print("Premiere listo. Abriendo VS Code...", flush=True)
    subprocess.Popen([code, "-r", str(d["ws"]), str(d["jsx"])], shell=False)
    if not esperar(lambda: ventana_lista("Code", ws_stem), 90, 2.0):
        print("VS Code no abrió el workspace. Ábrelo tú y pulsa F5.")
        return False
    time.sleep(6)  # el ExtendScript Debugger necesita un momento
    f5 = ("$ws = New-Object -ComObject WScript.Shell; "
          f"$p = Get-Process Code | Where-Object {{ $_.MainWindowTitle -like '*{ws_stem}*' }} | Select-Object -First 1; "
          "if ($p -and $ws.AppActivate($p.Id)) { Start-Sleep -Milliseconds 900; $ws.SendKeys('{F5}'); 'ok' }")
    for intento in (1, 2):
        r = subprocess.run(["powershell", "-NoProfile", "-Command", f5], capture_output=True, text=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        print(f"F5 enviado a VS Code (intento {intento})." if r.stdout.strip() == "ok"
              else "No pude activar la ventana de VS Code.", flush=True)
        if esperar(lambda: d["marker"].exists() or d["error"].exists(), 150 if intento == 1 else 300):
            break
    if d["marker"].exists():
        print(f"OK: Premiere importó el XML y guardó {d['prproj']}")
        return True
    if d["error"].exists():
        print("Premiere devolvió un error:", d["error"].read_text(encoding="utf-8", errors="replace"))
    else:
        print("Premiere no confirmó la importación. Mira si muestra un aviso; si no, pulsa F5 en VS Code.")
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--xml", type=Path, default=HERE / "salida" / "spot.xml")
    ap.add_argument("--salida", type=Path, default=HERE / "salida" / "premiere")
    ap.add_argument("--preparar", action="store_true", help="solo prepara los archivos, no lanza nada")
    args = ap.parse_args()

    d = preparar(args.salida, args.xml)
    print(f"Paquete en {args.salida}")
    for k in ("prproj", "jsx", "bat", "ws"):
        print(f"  {k:6s} {d[k].name}")
    if not args.preparar:
        sys.exit(0 if automatico(d) else 1)


if __name__ == "__main__":
    main()
