"""Озвучка: каждая реплика из scenes.py синтезируется офлайн, затем
собирается таймлайн всего ролика.

Движок по умолчанию — нейросетевой Piper (VITS), голос ru_RU-dmitri-medium:
звучит заметно естественнее. Модель (~80 МБ) скачивается из GitHub-релиза
sherpa-onnx в build/voices при первом запуске. Переменные окружения:
  TTS_VOICE=dmitri|ruslan|denis|irina — голос Piper;
  TTS_ENGINE=rhvoice                  — старый синтезатор RHVoice (aleksandr-hq);
  TTS_LENGTH_SCALE=1.12               — темп Piper (>1 — медленнее).

Результат в build/:
  audio/<сцена>_<n>.wav — реплики;
  narration.wav         — дорожка озвучки целиком (48 кГц, моно);
  timing.json           — начало и длительность каждой сцены и реплики.

Запуск: python marketing_video/tts.py
"""
from __future__ import annotations

import json
import os
import subprocess
import tarfile
import urllib.request
import wave
from pathlib import Path

import numpy as np

from scenes import SCENES, line_pause, line_text, tts_text

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
AUDIO = BUILD / "audio"
ENGINE = os.environ.get("TTS_ENGINE", "piper")
PIPER_VOICE = os.environ.get("TTS_VOICE", "dmitri")
PIPER_URL = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/vits-piper-ru_RU-{v}-medium.tar.bz2"
LENGTH_SCALE = float(os.environ.get("TTS_LENGTH_SCALE", "1.12"))
RHVOICE = "aleksandr-hq"
SPEED = 110                         # темп речи RHVoice, %
RATE = 48000
LEAD = {"card": 0.9, "screen": 0.7}  # пауза перед первой репликой (здесь идёт переход)
GAP = 0.55                           # пауза между репликами
TAIL = 0.9                           # пауза после последней реплики


_piper = None


def piper_voice():
    global _piper
    if _piper is None:
        from piper import PiperVoice

        folder = BUILD / "voices" / f"vits-piper-ru_RU-{PIPER_VOICE}-medium"
        model = folder / f"ru_RU-{PIPER_VOICE}-medium.onnx"
        if not model.exists():
            archive = BUILD / "voices" / "voice.tar.bz2"
            archive.parent.mkdir(parents=True, exist_ok=True)
            print("Скачиваю голос", PIPER_VOICE)
            urllib.request.urlretrieve(PIPER_URL.format(v=PIPER_VOICE), archive)
            with tarfile.open(archive) as tar:
                tar.extractall(archive.parent, filter="data")
            archive.unlink()
        _piper = PiperVoice.load(model, config_path=model.with_suffix(".onnx.json"))
    return _piper


def synth(text: str, out: Path) -> np.ndarray:
    raw = out.with_suffix(".raw.wav")
    if ENGINE == "rhvoice":
        subprocess.run(["RHVoice-test", "-p", RHVOICE, "-r", str(SPEED), "-o", str(raw)], input=tts_text(text).encode(),
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        from piper import SynthesisConfig

        with wave.open(str(raw), "wb") as w:
            piper_voice().synthesize_wav(tts_text(text), w, syn_config=SynthesisConfig(length_scale=LENGTH_SCALE))
    # Ресемплинг до 48 кГц, лёгкая обработка голоса (срез гула, мягкая
    # компрессия) и обрезка тишины по краям.
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af",
                    "highpass=f=70,acompressor=threshold=-20dB:ratio=2.5:attack=8:release=120,"
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
