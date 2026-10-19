# Spot Spa — del rodaje al spot

Un solo programa (`spa.py`) que parte de los **originales** de un rodaje y llega a un **borrador del spot**,
un **vídeo final**, un **XML** y un **proyecto de Premiere** ordenado por etapas y tomas. Todo en local
(CLIP por ONNX + Ollama con `qwen2.5vl`), sin enviar vídeo a ningún servicio.

## Uso

```bash
python spa.py preparar --originales "F:\Video Spa" --musica cancion.mp3     # 1) hasta el visor HTML
#   -> revisas el HTML, ajustas lo que quieras y pulsas «Descargar decisiones»
python spa.py listo                                                         # 2) el «listo»
python spa.py publicar                                                      # (opcional) sube el visor a GitHub
```

Sin argumentos (`SPOT_SPA.bat`, doble clic) muestra un menú.

### 1) `preparar` — de los originales a la propuesta

| Paso | Programa | Qué hace |
|---|---|---|
| 1 | `spa_proxies.py` | **Crea los proxies** (640×360, mismo nombre, mismos fps y mismo nº de fotogramas). Los que ya existen y coinciden fotograma a fotograma se conservan |
| 2 | `spa_extraer.py` | Fotogramas por clip + huella visual (CLIP; reutiliza el modelo de AutoSync Multicam, solo lectura) |
| 3 | `analyze_footage.py` | Análisis con IA local (Ollama): qué se ve, nota 0-10 y mejores momentos de cada clip |
| 4 | `spa_beats.py` | Ritmo de la música (librosa) |
| 5 | `spa_agrupar.py` | **Junta las tomas repetidas** (mismo plano grabado varias veces); copia cada grupo a su carpeta en `tomas/` |
| 6 | `spa_atributos.py` | Preguntas de sí/no a la IA local sobre cada plano (¿hay vapor? ¿piedras? ¿mascarilla?…) |
| 7 | `spa_proponer.py` | Asigna cada plano a una etapa de la historia y elige los que entran (cada corte sobre un beat). Correcciones manuales en `overrides.json` |
| 8 | `spa_aplicar.py` | Borrador de la propuesta con los proxies |
| 9 | `spa_html.py` | **Visor HTML** (`propuesta_montaje.html`) |

Cada paso se salta si ya está hecho (`--rehacer` lo repite) y los de IA se pueden reanudar. Los resultados de la IA se guardan
**por nombre de clip**, no por número de grupo, así que siguen valiendo si cambia la agrupación.

### 2) `listo` — con tus decisiones

1. Toma el `decisiones_spot_spa.json` más reciente de Descargas (o el que indiques) y comprueba que los proxies coinciden con los originales.
2. `spa_aplicar.py`: vídeo borrador (proxies), `spot.xml`, **`spot_final.xml`** (secuencia a la resolución de los originales) y el **vídeo final** renderizado desde los originales.
3. `spa_html.py --decisiones`: el visor pasa a partir de tus decisiones.
4. `spa_premiere.py`: crea el **proyecto de Premiere** con los **originales** y los **proxies adjuntos**, con carpetas por etapa y una subcarpeta por cada plano con tomas repetidas.
5. `spa_resumen.py`: **resumen final** en pantalla, `salida/RESUMEN.md` y `salida/RESUMEN.html` (Ctrl+P para imprimir).

### Premiere

Mismo método que AutoSync Multicam: se copia la plantilla `.prproj` en blanco de Premiere 2022 y un JSX, ejecutado con el
ExtendScript Debugger de VS Code, trabaja **dentro del proyecto base ya abierto** (no usa `newProject`): importa el XML, ordena el
panel Proyecto y **adjunta los proxies** (*Toggle Proxies* alterna entre ellos y los originales). Deja un marcador `.importado.ok.txt`.

- **Nunca cierra un proyecto ajeno**: si Premiere tiene abierto otro, se detiene sin enviar ninguna tecla.
- El JSX es de solo lectura (VS Code guarda lo que haya en el editor antes de depurar: una tecla suelta lo rompería).
- Durante la ejecución no hay que tocar el teclado: se envía Esc, Esc y F5 a la ventana de VS Code (un aviso de error de un intento
  fallido se traga el F5; el Esc lo cierra) y se reintenta hasta que el script de Premiere deja su registro. No se usa Mayús+F5.
- Los proxies se adjuntan con ruta de Windows (`F:\...`): con barras `/`, `attachProxy` devuelve `false` sin avisar. Se comprueba con
  `hasProxy()` y el resumen lo vuelve a contar dentro del `.prproj` guardado.
- Si ya existe un proyecto de una ejecución anterior se conserva como `Spot Spa - FINAL (anterior AAAAMMDD_HHMM).prproj` (las 3 últimas)
  y el abierto en Premiere se descarta y se recarga en blanco: **tus cambios manuales hechos sobre un proyecto abierto no se conservan**
  salvo lo que hubieras guardado antes de volver a ejecutar `listo`.
- El XML deja los clips pegados, sin solapes (Premiere no admite clips solapados en una pista), con fundidos centrados en el
  corte solo donde ambos clips tienen material de sobra.

### GitHub

`spa_publicar.py` sigue el flujo del proyecto del Frontón: **rama + pull request, nunca directo a `main`**, y el visor publicado con
GitHub Pages desde la rama. **Pregunta antes de subir** y muestra si el repositorio es público o privado y cuántas miniaturas de
personas lleva. Busca datos personales en el texto a subir y se detiene si encuentra alguno. No sube vídeos, música, proxies ni originales.

## Agrupar tomas: cómo y hasta dónde

Similitud entre dos clips = media simétrica del mejor parecido de cada fotograma (CLIP). Son la misma toma si la similitud media del
grupo es ≥ 0.91 y caben en una ventana de 6 posiciones del orden de rodaje. Revisado a ojo en este rodaje: ≥ 0.91 fueron tomas
repetidas y ≈ 0.907 ya eran ángulos distintos. **No elige la mejor toma**: por defecto propone la de mejor nota y, a igualdad, la
última; se cambia en el HTML.

## Requisitos

Python 3.11, `ffmpeg`/`ffprobe` en el PATH, Ollama con `qwen2.5vl:7b` y `qwen3:8b`, y `pip install -r requirements.txt`.
Para Premiere: Premiere Pro 2022, VS Code con la extensión *ExtendScript Debugger* y la plantilla `Premiere2022_blank_22.4.prproj`
de AutoSync (se busca sola bajo `Documents\Codex`, o con la variable `SPA_PLANTILLA_PRPROJ`).

## Otro rodaje

La carpeta de trabajo se fija con la variable de entorno `SPA_PROYECTO` (por defecto, esta carpeta): ahí se guardan `cache/`,
`salida/`, `tomas/`, `decisiones/` y `proyecto.json`.

## Privacidad

El rodaje muestra a personas reales. Los vídeos, la música y los fotogramas completos **no** se versionan (`.gitignore`).
`docs/` es la versión estática del visor (solo miniaturas) y parte de `decisiones/`. Para retirar las imágenes: borrar `docs/img`
o pasar el repositorio a privado.
