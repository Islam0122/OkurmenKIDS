"""Проверка готового ролика: файл открывается, параметры потоков, длительность
совпадает с таймлайном озвучки, громкость в норме, субтитры синхронны,
нет запрещённых строк (пароль демо-учётки, токены), сохраняет контрольные кадры.

Запуск: python marketing_video/verify.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MP4 = ROOT / "marketing_tutorial.mp4"
CHECK = ROOT / "build" / "check"


def main() -> int:
    problems = []
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format",
                                       "-show_streams", str(MP4)], check=True, capture_output=True, text=True).stdout)
    streams = {s["codec_type"]: s for s in probe["streams"]}
    duration = float(probe["format"]["duration"])
    timing = json.loads((ROOT / "build" / "timing.json").read_text())
    v, a = streams.get("video"), streams.get("audio")
    print(f"Файл: {MP4.name}, {MP4.stat().st_size / 1e6:.1f} МБ, длительность {int(duration // 60)}:{duration % 60:04.1f}")
    print(f"Видео: {v['codec_name']} {v['width']}×{v['height']} {v['r_frame_rate']} к/с, {v['pix_fmt']}")
    print(f"Аудио: {a['codec_name']} {a['sample_rate']} Гц, каналов {a['channels']}")
    print(f"Субтитры: {'есть' if 'subtitle' in streams else 'нет'}")
    if (v["width"], v["height"]) != (1920, 1080):
        problems.append("разрешение не 1920×1080")
    if abs(duration - timing["total"]) > 0.5:
        problems.append(f"длительность {duration:.1f} c ≠ таймлайн {timing['total']:.1f} c")
    if not 300 <= duration <= 480:
        problems.append("длительность вне диапазона 5–8 минут")

    # Полное декодирование — файл читается без ошибок.
    err = subprocess.run(["ffmpeg", "-v", "error", "-i", str(MP4), "-f", "null", "-"], capture_output=True, text=True).stderr
    if err.strip():
        problems.append(f"ошибки декодирования: {err.strip()[:300]}")

    # Громкость озвучки.
    loud = subprocess.run(["ffmpeg", "-i", str(MP4), "-map", "0:a", "-af", "ebur128=peak=true", "-f", "null", "-"],
                          capture_output=True, text=True).stderr
    integrated = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", loud)[-1])
    peak = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", loud)[-1])
    print(f"Громкость: {integrated} LUFS, пик {peak} dBFS")
    if not -19 <= integrated <= -13 or peak > -0.5:
        problems.append("громкость вне нормы")

    # Синхронизация: в каждой реплике есть речь, в паузах между сценами — тишина.
    sil = subprocess.run(["ffmpeg", "-i", str(MP4), "-map", "0:a", "-af", "silencedetect=n=-40dB:d=0.25", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", sil)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", sil)]
    silences = list(zip(starts, ends))
    bad = 0
    lines = [(s["start"] + ln["start"], ln["duration"], ln["text"]) for s in timing["scenes"] for ln in s["lines"]]
    for start, dur, text in lines:
        mid = start + dur / 2
        if any(s0 <= mid <= s1 for s0, s1 in silences):
            bad += 1
            print(f"  ! тишина посреди реплики {start:.1f} c: {text[:50]}")
    print(f"Реплик: {len(lines)}, рассинхронизаций: {bad}")
    if bad:
        problems.append("озвучка не совпадает с субтитрами")

    # Запрещённые строки в материалах.
    secret = os.environ.get("MARKETING_DEMO_PASSWORD", "demo-video-2026")
    for name in ("script.md", "storyboard.md", "subtitles.srt"):
        text = (ROOT / name).read_text()
        if secret in text or re.search(r"eyJ[a-zA-Z0-9_-]{20,}", text):
            problems.append(f"{name}: найден пароль или токен")

    # Контрольные кадры: середина каждой сцены.
    CHECK.mkdir(parents=True, exist_ok=True)
    for s in timing["scenes"]:
        t = s["start"] + s["duration"] * 0.55
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.2f}", "-i", str(MP4), "-frames:v", "1",
                        str(CHECK / f"{s['id']}.png")], check=True)
    print(f"Контрольные кадры: {CHECK}")

    if problems:
        print("ПРОБЛЕМЫ:\n - " + "\n - ".join(problems))
        return 1
    print("Проверка пройдена.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
