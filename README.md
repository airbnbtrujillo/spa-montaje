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

## Privacidad

El rodaje muestra a una persona real en tratamientos de spa. Los vídeos, la música y los fotogramas
completos **no** se versionan (`.gitignore`). La versión estática (`docs/`) lleva miniaturas: no la
publiques en un repositorio público sin permiso de la persona que aparece.
