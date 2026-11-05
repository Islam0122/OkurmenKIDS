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
import re
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
# Written as a sales voiceover: a hook, short punchy phrases, benefits, a call to action.
LINES: dict[str, str] = {
    "intro": "Отчёты для родителей отнимают часы? С Окурмэн Кидс — это пара кликов!",
    "kpi": "Открываем группу, вкладку Кей Пи Ай — и статистика каждого ученика уже перед вами.",
    "generate": "Жмём «Создать отчёт». Выбираем месяц, язык и формат: картинка плюс текст для Ватсапа.",
    "analytics": "Посещаемость, домашка, оценки, тесты — система считает всё сама! "
                 "Локально, по данным школы, без внешнего искусственного интеллекта.",
    "png": "Вот он — готовый фирменный отчёт! Статистика группы, прогресс каждого ученика, "
           "статусы и понятные рекомендации для родителей.",
    "text": "А это — сообщение для родителей. Русский или кыргызский — в один клик. Поправили, скопировали, отправили!",
    "history": "Скачайте картинку — а все отчёты сохраняются в истории.",
    "final": "Окурмэн Кидс. Один клик — полный отчёт. Попробуйте уже сегодня!",
}

# Delivery styles: `sales` — brisk and expressive (default), `calm` — an even explainer.
STYLES = {
    "sales": {"speed": 1.08, "noise_scale": 0.74, "noise_scale_w": 0.9, "pause": {".": 0.26, "!": 0.32, "?": 0.38}},
    "calm": {"speed": 1.0, "noise_scale": 0.55, "noise_scale_w": 0.7, "pause": {".": 0.3, "!": 0.3, "?": 0.35}},
}
STYLE = os.environ.get("DEMO_VOICE_STYLE", "sales")

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


def _engine(voice: str, style: dict):
    import sherpa_onnx

    folder = ensure_voice(voice)
    model = folder / f"{VOICES[voice].removeprefix('vits-piper-')}.onnx"
    config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=str(model), tokens=str(folder / "tokens.txt"), data_dir=str(folder / "espeak-ng-data"),
                # Less randomness in pitch/timing = a smoother, more even narrator.
                noise_scale=style["noise_scale"], noise_scale_w=style["noise_scale_w"], length_scale=1.0,
            ),
            num_threads=max(1, (os.cpu_count() or 2) - 1),
        ),
        max_num_sentences=2,
    )
    return sherpa_onnx.OfflineTts(config)


def _sentences(text: str) -> list[tuple[str, str]]:
    """[(sentence, its final punctuation)] — each is synthesised on its own and
    followed by a deliberate pause, which gives the brisk rhythm of an ad read."""
    parts = re.findall(r"[^.!?]+[.!?]*", text)
    return [(part.strip(), (part.strip()[-1:] if part.strip()[-1:] in ".!?" else ".")) for part in parts if part.strip()]


def synthesize(out_dir: Path, *, voice: str = "irina", style: str | None = None) -> dict[str, Clip]:
    """One WAV per scene in `out_dir`; returns their durations (seconds)."""
    import numpy as np
    import soundfile as sf

    settings = STYLES[style or STYLE]
    out_dir.mkdir(parents=True, exist_ok=True)
    tts = _engine(voice, settings)
    clips = {}
    for scene, text in LINES.items():
        pieces, rate = [], 22050
        sentences = _sentences(text)
        for index, (sentence, mark) in enumerate(sentences):
            audio = tts.generate(sentence, sid=0, speed=settings["speed"])
            samples = np.asarray(audio.samples, dtype=np.float32)
            if samples.size == 0 or float(np.abs(samples).max()) < 0.01:
                raise RuntimeError(f"Голос не синтезировал фразу сцены «{scene}»: {sentence}")
            rate = audio.sample_rate
            pieces.append(_trim(samples, rate))
            if index < len(sentences) - 1:
                pieces.append(np.zeros(int(settings["pause"][mark] * rate), dtype=np.float32))
        samples = np.concatenate(pieces)
        path = out_dir / f"{scene}.wav"
        sf.write(path, samples, rate)
        clips[scene] = Clip(scene, path, samples.size / rate)
    return clips


def _trim(samples, rate: int, threshold: float = 0.012):
    """Cut the model's leading/trailing silence so the pauses are exactly ours."""
    import numpy as np

    loud = np.flatnonzero(np.abs(samples) > threshold)
    if loud.size == 0:
        return samples
    pad = int(0.03 * rate)
    return samples[max(0, loud[0] - pad): loud[-1] + pad]


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
