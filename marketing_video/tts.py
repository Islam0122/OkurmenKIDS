"""Озвучка: каждая реплика из scenes.py синтезируется офлайн-движком RHVoice
(голос aleksandr-hq), затем собирается таймлайн всего ролика.

Результат в build/:
  audio/<сцена>_<n>.wav — реплики;
  narration.wav         — дорожка озвучки целиком (48 кГц, моно);
  timing.json           — начало и длительность каждой сцены и реплики.

Запуск: python marketing_video/tts.py
"""
from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import numpy as np

from scenes import SCENES, line_pause, line_text, tts_text

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
AUDIO = BUILD / "audio"
VOICE = "aleksandr-hq"
SPEED = 110                         # темп речи RHVoice, %
RATE = 48000
LEAD = {"card": 0.9, "screen": 0.7}  # пауза перед первой репликой (здесь идёт переход)
GAP = 0.45                           # пауза между репликами
TAIL = 0.9                           # пауза после последней реплики


def synth(text: str, out: Path) -> np.ndarray:
    raw = out.with_suffix(".raw.wav")
    subprocess.run(["RHVoice-test", "-p", VOICE, "-r", str(SPEED), "-o", str(raw)], input=tts_text(text).encode(), check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Ресемплинг до 48 кГц и обрезка тишины по краям.
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af",
                    "silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
                    "silenceremove=start_periods=1:start_threshold=-50dB,areverse",
                    "-ar", str(RATE), "-ac", "1", str(out)], check=True)
    raw.unlink()
    with wave.open(str(out)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)


def main():
    AUDIO.mkdir(parents=True, exist_ok=True)
    timeline, chunks, t = [], [], 0.0

    def pad(seconds: float):
        nonlocal t
        chunks.append(np.zeros(int(round(seconds * RATE)), dtype=np.float32))
        t += seconds

    for scene in SCENES:
        start = t
        lines = []
        pad(LEAD[scene["kind"]])
        for n, line in enumerate(scene["say"]):
            text = line_text(line)
            if n:
                pad(GAP + line_pause(scene["say"][n - 1]))
            samples = synth(text, AUDIO / f"{scene['id']}_{n}.wav")
            dur = len(samples) / RATE
            lines.append({"text": text, "start": round(t - start, 3), "duration": round(dur, 3)})
            chunks.append(samples)
            t += dur
        pad(TAIL + scene.get("tail", 0.0))
        timeline.append({"id": scene["id"], "kind": scene["kind"], "start": round(start, 3),
                         "duration": round(t - start, 3), "lines": lines})
        print(f"{scene['id']:<15} {t - start:6.1f} c")

    audio = np.concatenate(chunks)
    audio = np.clip(audio, -32768, 32767).astype(np.int16)
    with wave.open(str(BUILD / "narration.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(audio.tobytes())
    (BUILD / "timing.json").write_text(json.dumps({"total": round(t, 3), "scenes": timeline}, ensure_ascii=False,
                                                  indent=1))
    print(f"Итого: {t:.1f} c ({int(t // 60)}:{int(t % 60):02d})")


if __name__ == "__main__":
    main()
