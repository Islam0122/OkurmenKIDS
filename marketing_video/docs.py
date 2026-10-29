"""Генерирует script.md, storyboard.md и subtitles.srt из scenes.py и
build/timing.json — тексты в документах всегда совпадают с озвучкой.

Запуск (после tts.py): python marketing_video/docs.py
"""
from __future__ import annotations

import json
from pathlib import Path

from scenes import SCENES, TITLE, line_text

ROOT = Path(__file__).resolve().parent
TIMING = json.loads((ROOT / "build" / "timing.json").read_text())
BY_ID = {s["id"]: s for s in TIMING["scenes"]}


def mmss(t: float) -> str:
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def where(scene) -> str:
    return "слайд" if scene["kind"] == "card" else f"экран LMS — «{scene['caption']}»"


def script_md() -> str:
    out = [f"# {TITLE} — сценарий озвучивания", "",
           f"Длительность: **{mmss(TIMING['total'])}**. Голос: нейросетевой Piper `ru_RU-dmitri-medium` "
           "(офлайн-синтез). Тайм-коды — начало реплики в итоговом ролике.", "",
           "Факты сверены с кодом: `backend/apps/marketing`, `frontend/src/features/marketing`, "
           "`backend/docs/marketing.md`. В ролике использованы обезличенные демонстрационные данные "
           "(`marketing_video/demo/seed_demo.py`).", ""]
    section = None
    for scene in SCENES:
        t = BY_ID[scene["id"]]
        if scene["section"] != section:
            section = scene["section"]
            out += [f"## {section}", ""]
        out += [f"### {mmss(t['start'])} — {scene.get('caption') or scene['card']['title']} ({where(scene)})", ""]
        for line in t["lines"]:
            out.append(f"- `{mmss(t['start'] + line['start'])}` {line['text']}")
        out.append("")
    return "\n".join(out)


def storyboard_md() -> str:
    out = [f"# {TITLE} — раскадровка", "",
           "Формат: 1920×1080, 30 к/с, H.264 + AAC. Экранные сцены записаны в реальном интерфейсе "
           "(Playwright, вьюпорт 1440×810, плотность 2×), слайды нарисованы Pillow. Переходы — растворение 0,5 с; "
           "приближения — плавный наезд 0,6 с; субтитры вшиты внизу кадра и дублируются отдельной дорожкой.", "",
           "| # | Время | Длит. | Тип | Сцена | Что на экране |", "|---|---|---|---|---|---|"]
    for n, scene in enumerate(SCENES, 1):
        t = BY_ID[scene["id"]]
        name = scene.get("caption") or scene["card"]["title"]
        kind = "Слайд" if scene["kind"] == "card" else "Экран"
        board = "<br>".join(f"{i}. {step}" for i, step in enumerate(scene["board"], 1))
        out.append(f"| {n} | {mmss(t['start'])} | {t['duration']:.0f} c | {kind} | {name} | {board} |")
    out += ["", "## Поясняющие подписи и приближения", "",
            "Задаются в `record.cjs` (функции `zoom()` и `note()`) и привязаны к началу реплик. "
            "Плашка с названием раздела видна первые 5 секунд каждой экранной сцены.", ""]
    return "\n".join(out)


def subtitles_srt() -> str:
    out, n = [], 0
    for scene in SCENES:
        t = BY_ID[scene["id"]]
        for line in t["lines"]:
            n += 1
            start = t["start"] + line["start"]
            out += [str(n), f"{srt_time(start)} --> {srt_time(start + line['duration'] + 0.2)}", line["text"], ""]
    return "\n".join(out)


def main():
    assert [s["id"] for s in SCENES] == [s["id"] for s in TIMING["scenes"]], "timing.json устарел — запустите tts.py"
    for scene in SCENES:
        assert [line_text(x) for x in scene["say"]] == [x["text"] for x in BY_ID[scene["id"]]["lines"]], \
            f"timing.json устарел для сцены {scene['id']} — запустите tts.py"
    (ROOT / "script.md").write_text(script_md())
    (ROOT / "storyboard.md").write_text(storyboard_md())
    (ROOT / "subtitles.srt").write_text(subtitles_srt())
    print("script.md, storyboard.md, subtitles.srt обновлены")


if __name__ == "__main__":
    main()
