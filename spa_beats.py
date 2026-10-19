#!/usr/bin/env python3
"""spa_beats.py — rejilla de beats de la música (librosa) -> cache/beats.json"""
import json, sys
from pathlib import Path
import librosa
try: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception: pass
sys.path.insert(0, str(Path(__file__).parent))
from spa_lib import CACHE
musica = Path(sys.argv[1])
y, sr = librosa.load(str(musica), mono=True)
tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
try: bpm = float(tempo)
except TypeError: bpm = float(tempo[0])
out = {"ruta": str(musica.resolve()), "bpm": round(bpm, 2),
       "duracion_s": round(float(librosa.get_duration(y=y, sr=sr)), 3),
       "beats": [round(float(b), 4) for b in beats]}
CACHE.mkdir(parents=True, exist_ok=True)
dst = CACHE / "beats.json"
dst.write_text(json.dumps(out), encoding="utf-8")
print(f"{musica.name[:40]}: {out['bpm']} BPM, {len(out['beats'])} beats, {out['duracion_s']}s, primer beat {out['beats'][0]}s")
