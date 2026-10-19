# Spot Spa — propuesta de montaje

Toma una carpeta de clips (aquí 110 proxies de un rodaje de spa) y propone un **primer montaje
ordenado según la historia**: llegada → ambiente → espejo → pasadizo → sube a la camilla →
piedras → vapor → mascarilla → cremas → cierre. Lo revisas en un **HTML** y de ahí sale un
**vídeo borrador** y un **XML para Premiere**.

Todo corre en local (CLIP por ONNX + Ollama con `qwen2.5vl`), sin enviar vídeo a ningún servicio.

## Qué hace, paso a paso

| Paso | Programa | Qué hace |
|---|---|---|
| 1 | `spa_extraer.py` | Saca 6 fotogramas por clip y calcula su huella visual con CLIP (reutiliza el modelo y el preprocesado de AutoSync Multicam, solo lectura) |
| 2 | `spa_agrupar.py` | **Junta las tomas repetidas** (mismo plano grabado varias veces). `--carpetas` copia cada grupo a su carpeta en `tomas/` |
| 3 | `spa_actos.py`, `spa_atributos.py` | El modelo de visión contesta preguntas de sí/no por plano (¿hay vapor? ¿piedras? ¿mascarilla?…) |
| 4 | `spa_proponer.py` | Asigna cada plano a una etapa de la historia y elige cuáles entran (≈ 95 s, cada corte sobre un beat). Las correcciones manuales están en `overrides.json` |
| 5 | `spa_html.py` | Genera `propuesta_montaje.html` (o `--estatico docs` sin vídeos) |
| 6 | `spa_aplicar.py` | Convierte las decisiones (las iniciales o las descargadas del HTML) en `salida/borrador.mp4` y `salida/spot.xml` |

Músicas y beats: `spa_beats.py "cancion.mp3"` (librosa) → `cache/beats.json`.

## Flujo de uso

```bash
python spa_extraer.py
python spa_agrupar.py --ventana 6 --carpetas
python spa_actos.py && python spa_atributos.py     # requiere Ollama con qwen2.5vl:7b
python spa_beats.py "cancion.mp3"
python spa_proponer.py
python spa_html.py            # abre propuesta_montaje.html
# en el HTML: revisa, cambia lo que quieras, "Descargar decisiones"
python spa_aplicar.py "decisiones_spot_spa.json"   # -> salida/borrador.mp4 + salida/spot.xml
```

En Premiere: **File ▸ Import ▸ `salida/spot.xml`**. El XML apunta a los *proxies*; para editar con
los originales, clic derecho ▸ **Link Media**.

## El HTML

Sigue el patrón del informe de verificación de AutoSync: la herramienta **propone**, tú **revisas**
y las decisiones se **exportan en JSON**. Por plano puedes: incluirlo o no, elegir qué toma usar,
cambiar de etapa, mover el orden, ajustar desde qué segundo y cuántos beats dura. Los cambios se
guardan en el navegador.

## Agrupar tomas: cómo y hasta dónde

Similitud entre dos clips = media simétrica del mejor parecido de cada fotograma (CLIP). Dos clips
son la misma toma si la similitud media del grupo es ≥ 0.91 y caben en una ventana de 6 posiciones
del orden de rodaje. Revisado a ojo sobre este rodaje: ≥ 0.91 fueron tomas repetidas y ≈ 0.907 ya
eran ángulos distintos. **No elige la mejor toma**: por defecto propone la de mejor nota y, a
igualdad, la última; se cambia en el HTML.

## Borrador con fundidos

`render_montage.py --dissolve 12` (lo que usa `spa_aplicar.py`) hace los fundidos **centrados en el corte**: cada clip se
alarga media transición hacia el corte, así la duración total y los cortes sobre los beats no cambian. Solo hay
fundido donde ambos clips tienen material de sobra (igual que en el XML). La música se normaliza (loudnorm)
y entra/sale con fundido.

## Premiere

`spa_premiere.py` crea el proyecto de Premiere con el mismo método que AutoSync Multicam: copia la
plantilla `.prproj` en blanco de Premiere 2022 y un JSX, ejecutado con el ExtendScript Debugger de
VS Code, trabaja DENTRO del proyecto base ya abierto (que es el archivo final: no usa `newProject` ni cierra nada), importa `salida/spot.xml` (la secuencia) y **ordena el panel Proyecto**:
una carpeta por etapa de la historia y, dentro, una subcarpeta por cada plano con tomas repetidas
(los clips usados se mueven; los demás se importan). Deja un marcador `.importado.ok.txt`.
`--preparar` solo genera los archivos (`ABRIR_PREMIERE_2022.bat`, el JSX y el workspace de VS Code)
y lo lanzas tú; `CREAR_PROYECTO_PREMIERE.bat` lo ejecuta todo con doble clic.

**Seguridad:** nunca cierra un proyecto ajeno. Si Premiere tiene abierto un proyecto que no es el suyo,
se detiene sin enviar ninguna tecla; el JSX comprueba lo mismo por su cuenta.

El XML (`export_premiere.py`) deja los clips pegados, sin solapes (Premiere no admite clips solapados
en una pista) y añade fundidos centrados en el corte solo donde ambos clips tienen material de sobra.

## Visor público

`docs/` es la versión estática del visor (sin vídeos, solo miniaturas) y parte de las decisiones de
`decisiones/decisiones_2026-10-19.json`. Las miniaturas muestran a una persona real durante un
tratamiento de spa; se publican por decisión del autor del proyecto. Los vídeos, la música y los
fotogramas completos **no** se versionan (`.gitignore`). Para retirar las imágenes: borrar `docs/img`
o pasar el repositorio a privado.
