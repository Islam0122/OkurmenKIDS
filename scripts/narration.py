"""Russian voiceover for the demo video — synthesised locally, offline.

Neural Piper voices (VITS) run through `sherpa-onnx` on the CPU: no cloud
TTS, no AI API, no keys. The voice model (~80 MB) is downloaded once from
the sherpa-onnx GitHub release into DEMO_VOICES_DIR (default
~/.cache/okurmenkids-demo/voices).

    python scripts/narration.py            # synthesise every line, print durations

Brand names are written the way they are read («Окурмэн Кидс», «Ватсап»),
otherwise a Russian voice spells the Latin letters.
"""
from __future__ import annotations

import dataclasses
import os
import tarfile
import urllib.request
import wave
from pathlib import Path

VOICES = {
    "irina": "vits-piper-ru_RU-irina-medium",    # female, warm (default)
    "dmitri": "vits-piper-ru_RU-dmitri-medium",  # male, calm
    "denis": "vits-piper-ru_RU-denis-medium",
    "ruslan": "vits-piper-ru_RU-ruslan-medium",
}
RELEASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/{name}.tar.bz2"
VOICES_DIR = Path(os.environ.get("DEMO_VOICES_DIR", Path.home() / ".cache" / "okurmenkids-demo" / "voices"))

# Scene → what the narrator says while it plays (matches demo_reports.py scenes).
LINES: dict[str, str] = {
    "intro": "Окурмэн Кидс. Ежемесячный отчёт для родителей — всего за несколько кликов.",
    "kpi": "Тренер открывает свою группу и вкладку Кей Пи Ай. Здесь уже видна статистика каждого студента за прошлый месяц.",
    "generate": "В разделе «Отчёты» нажимаем «Создать отчёт». Выбираем группу, месяц, язык и формат: картинка и текст для Ватсапа.",
    "analytics": "Всё считается локально, на Пайтоне, без внешних сервисов искусственного интеллекта: "
                 "посещаемость, домашние задания, оценки, тесты и рекомендации.",
    "png": "Готово! Фирменный отчёт Окурмэн Кидс: статистика группы, таблица студентов с прогресс-барами и статусами, "
           "а внизу — сильные стороны и рекомендации для родителей.",
    "text": "Рядом — готовое сообщение для родителей. Его можно переключить на кыргызский язык, отредактировать и скопировать одной кнопкой.",
    "history": "Картинка скачивается за секунду, а каждый отчёт сохраняется в истории группы.",
    "final": "Окурмэн Кидс. Один клик — полный отчёт.",
}


# How the spoken spellings are written in the subtitles.
_DISPLAY = {"Окурмэн Кидс": "OkurmenKIDS", "Кей Пи Ай": "KPI", "Пайтоне": "Python", "Ватсапа": "WhatsApp"}


def display_text(line: str) -> str:
    text = LINES[line]
    for spoken, written in _DISPLAY.items():
        text = text.replace(spoken, written)
    return text


@dataclasses.dataclass
class Clip:
    scene: str
    path: Path
    duration: float


def ensure_voice(voice: str) -> Path:
    name = VOICES[voice]
    folder = VOICES_DIR / name
    if (folder / f"{name.removeprefix('vits-piper-')}.onnx").exists():
        return folder
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    archive = VOICES_DIR / f"{name}.tar.bz2"
    print(f"  ↓ голос {voice}: {RELEASE.format(name=name)}")
    urllib.request.urlretrieve(RELEASE.format(name=name), archive)
    with tarfile.open(archive) as tar:
        tar.extractall(VOICES_DIR, filter="data")
    archive.unlink()
    return folder


def _engine(voice: str):
    import sherpa_onnx

    folder = ensure_voice(voice)
    model = folder / f"{VOICES[voice].removeprefix('vits-piper-')}.onnx"
    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(model), tokens=str(folder / "tokens.txt"), data_dir=str(folder / "espeak-ng-data"),
                # Less randomness in pitch/timing = a smoother, more even narrator.
                noise_scale=0.55, noise_scale_w=0.7, length_scale=1.0,
            ),
            num_threads=max(1, (os.cpu_count() or 2) - 1),
        ),
        max_num_sentences=2,
    )
    return sherpa_onnx.OfflineTts(config)


def synthesize(out_dir: Path, *, voice: str = "irina", speed: float = 1.02) -> dict[str, Clip]:
    """One WAV per scene in `out_dir`; returns their durations (seconds)."""
    import numpy as np
    import soundfile as sf

    out_dir.mkdir(parents=True, exist_ok=True)
    tts = _engine(voice)
    clips = {}
    for scene, text in LINES.items():
        audio = tts.generate(text, sid=0, speed=speed)
        samples = np.asarray(audio.samples, dtype=np.float32)
        if samples.size == 0 or float(np.abs(samples).max()) < 0.01:
            raise RuntimeError(f"Голос не синтезировал фразу сцены «{scene}»")
        path = out_dir / f"{scene}.wav"
        sf.write(path, samples, audio.sample_rate)
        clips[scene] = Clip(scene, path, samples.size / audio.sample_rate)
    return clips


def wav_duration(path: Path) -> float:
    with wave.open(str(path)) as handle:
        return handle.getnframes() / handle.getframerate()


if __name__ == "__main__":
    import sys
    import tempfile

    chosen = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DEMO_VOICE", "irina")
    target = Path(tempfile.mkdtemp(prefix="okurmen-voice-"))
    total = 0.0
    for clip in synthesize(target, voice=chosen).values():
        total += clip.duration
        print(f"{clip.scene:10s} {clip.duration:5.1f}s  {clip.path}")
    print(f"total {total:.1f}s")
