#!/usr/bin/env python3
"""
spa_extraer.py — Paso 1: saca fotogramas de cada clip y calcula su huella visual (CLIP).

Reutiliza el modelo CLIP local de AutoSync (F:\\AutoSyncAI\\models\\clip-vit-base-patch32) con el
mismo preprocesado que `autosync_clip_vision.py` (fotograma completo en lienzo negro 224x224),
para que sus umbrales de similitud (>=0.82 mismo plano, 0.70-0.82 revisar) sigan siendo válidos.

Salida en ./cache:
  frames/<clip>_<n>.jpg    miniaturas (también las usa el HTML)
  clips.json               duración y rutas por clip
  embeds.npz               huellas CLIP (clips x fotogramas x 512)
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from spa_lib import CACHE  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

CLIP_ONNX = Path(r"F:\AutoSyncAI\models\clip-vit-base-patch32\onnx\vision_model_quantized.onnx")
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".avi"}


def tool(name: str) -> str:
    p = shutil.which(name)
    if not p:
        sys.exit(f"ERROR: falta '{name}' en el PATH.")
    return p


def duration(path: Path, ffprobe: str) -> float:
    r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def extract_frames(path: Path, dur: float, k: int, out_dir: Path, ffmpeg: str) -> list[Path]:
    """k fotogramas repartidos por igual (320 px de ancho)."""
    frames = [out_dir / f"{path.stem}_{i}.jpg" for i in range(k)]
    if all(f.is_file() for f in frames):
        return frames
    rate = max(0.5, k / max(dur, 0.2))
    pattern = out_dir / f"{path.stem}_%d.jpg"
    for f in frames:
        f.unlink(missing_ok=True)
    subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(path),
                    "-vf", f"fps={rate:.4f},scale=320:-2", "-frames:v", str(k),
                    "-q:v", "3", "-start_number", "0", str(pattern)],
                   capture_output=True, text=True)
    got = [f for f in frames if f.is_file()]
    # clips muy cortos: repite el último fotograma hasta completar k
    for i in range(len(got), k):
        if got:
            shutil.copy2(got[-1], frames[i])
    return [f for f in frames if f.is_file()]


def preprocess(path: Path) -> np.ndarray:
    """Igual que autosync_clip_vision.py: miniatura 224 centrada en lienzo negro."""
    image = Image.open(path).convert("RGB")
    image.thumbnail((224, 224), Image.Resampling.BICUBIC)
    canvas = Image.new("RGB", (224, 224), (0, 0, 0))
    canvas.paste(image, ((224 - image.width) // 2, (224 - image.height) // 2))
    arr = np.asarray(canvas).astype(np.float32) / 255.0
    mean = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
    std = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
    return np.transpose((arr - mean) / std, (2, 0, 1)).astype(np.float32)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clips", type=Path, default=Path(r"F:\Video Spa\Proxies"))
    ap.add_argument("--cache", type=Path, default=CACHE)
    ap.add_argument("--frames", type=int, default=6, help="fotogramas por clip")
    args = ap.parse_args()

    if not CLIP_ONNX.is_file():
        sys.exit(f"ERROR: no encuentro el modelo CLIP: {CLIP_ONNX}")
    ffmpeg, ffprobe = tool("ffmpeg"), tool("ffprobe")
    fdir = args.cache / "frames"
    fdir.mkdir(parents=True, exist_ok=True)

    vids = sorted(p for p in args.clips.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS)
    print(f"{len(vids)} clips en {args.clips}")

    meta, frame_files = [], []
    for n, v in enumerate(vids, 1):
        d = duration(v, ffprobe)
        fr = extract_frames(v, d, args.frames, fdir, ffmpeg)
        meta.append({"nombre": v.name, "stem": v.stem, "ruta": str(v), "duracion_s": round(d, 3),
                     "indice": n - 1, "frames": [f.name for f in fr]})
        frame_files.append(fr)
        if n % 20 == 0 or n == len(vids):
            print(f"  fotogramas: {n}/{len(vids)}")

    import onnxruntime as ort
    sess = ort.InferenceSession(str(CLIP_ONNX), providers=["CPUExecutionProvider"])
    iname = sess.get_inputs()[0].name

    k = args.frames
    emb = np.zeros((len(vids), k, 512), dtype=np.float32)
    batch, slots = [], []

    def flush():
        if not batch:
            return
        out = sess.run(None, {iname: np.stack(batch)})[0]
        out = out / np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-8)
        for (ci, fi), vec in zip(slots, out):
            emb[ci, fi] = vec
        batch.clear()
        slots.clear()

    for ci, fr in enumerate(frame_files):
        for fi in range(k):
            f = fr[min(fi, len(fr) - 1)] if fr else None
            if f is None:
                continue
            batch.append(preprocess(f))
            slots.append((ci, fi))
            if len(batch) == 32:
                flush()
        if (ci + 1) % 20 == 0:
            print(f"  huellas CLIP: {ci + 1}/{len(vids)}")
    flush()

    (args.cache / "clips.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    np.savez_compressed(args.cache / "embeds.npz", emb=emb, names=np.array([m["nombre"] for m in meta]))
    print(f"\nOK -> {args.cache}  ({len(vids)} clips x {k} fotogramas)")


if __name__ == "__main__":
    main()
