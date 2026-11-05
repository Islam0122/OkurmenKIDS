"""Snapshot → template context of the report images.

Only formatting happens here (labels, «Нет данных», progress-bar widths,
status colours, pagination) — every number comes from the snapshot.
"""
from __future__ import annotations

import base64
import dataclasses
import functools
from pathlib import Path

from django.conf import settings
from django.utils.safestring import mark_safe

from . import i18n, layout, recommendations

BACKEND_DIR = Path(settings.BASE_DIR)
LOGO_PATH = BACKEND_DIR / "static" / "images" / "logo.png"
FONT_DIR = BACKEND_DIR / "apps" / "academy" / "services" / "fonts"

_ICON_PATHS = {
    "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
             '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    "calendar_check": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>'
                      '<path d="m9 16 2 2 4-4"/>',
    "user_check": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
                  '<polyline points="16 11 18 13 22 9"/>',
    "book": '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    "star": '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
    "clipboard": '<rect x="8" y="2" width="8" height="4" rx="1"/>'
                 '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>'
                 '<path d="m9 14 2 2 4-4"/>',
    "thumbs_up": '<path d="M7 10v12"/><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4'
                 'a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2a3.13 3.13 0 0 1 3 3.88Z"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/>'
             '<path d="M12 9v4"/><path d="M12 17h.01"/>',
    "bulb": '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 '
            '1.5 2.5"/><path d="M9 18h6"/><path d="M10 22h4"/>',
    "up": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
    "down": '<polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/><polyline points="16 17 22 17 22 11"/>',
    "stable": '<path d="M5 12h14"/>',
    "cap": '<path d="M22 10 12 5 2 10l10 5 10-5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/>',
}


def icon(name: str, size: int = 24) -> str:
    return mark_safe(
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{_ICON_PATHS[name]}</svg>'
    )


@functools.lru_cache(maxsize=4)
def _data_uri(path: str, mime: str) -> str:
    data = Path(path).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def assets() -> dict:
    return {
        "logo": _data_uri(str(LOGO_PATH), "image/png"),
        "font_regular": _data_uri(str(FONT_DIR / "DejaVuSans.ttf"), "font/ttf"),
        "font_bold": _data_uri(str(FONT_DIR / "DejaVuSans-Bold.ttf"), "font/ttf"),
    }


def tone(value: float | None) -> str:
    """Colour of a 0–100 value: green / yellow / red, grey without data."""
    if value is None:
        return "muted"
    if value >= 85:
        return "good"
    if value >= 70:
        return "warn"
    return "bad"


STATUS_TONE = {"excellent": "good", "good": "good", "attention": "warn", "support": "bad", "no_data": "muted"}


def _bar(value: float | None) -> float | None:
    return None if value is None else max(0.0, min(100.0, float(value)))


def _metric(value: float | None, language: str, *, kind: str = "percent") -> dict:
    if kind == "score":
        text = i18n.score(value, language)
        scaled = value * 10 if value is not None else None
    else:
        text = i18n.percent(value, language)
        scaled = value
    return {"text": text, "has_data": value is not None, "bar": _bar(scaled), "tone": tone(scaled)}


def _change(item: dict | None, *, unit: str) -> dict | None:
    if not item or item.get("change") is None:
        return None
    direction = item["trend"]
    return {
        "text": i18n.signed(item["change"], unit),
        "trend": direction,
        "icon": icon(direction if direction in ("up", "down") else "stable", 14),
    }


def _name_class(name: str) -> str:
    return "name-xl" if len(name) > 40 else ("name-long" if len(name) > 26 else "")


def _status(key: str, L: dict) -> dict:
    return {"key": key, "label": L[f"status_{key}"], "tone": STATUS_TONE[key]}


# A section card of the image shows at most this many statements (the text message shows all).
IMAGE_SECTION_ITEMS = 3
DENSE_SECTION_CHARS = 230


def _section(key: str, title: str, icon_name: str, items: list[dict]) -> dict:
    texts = [item["text"] for item in items][:IMAGE_SECTION_ITEMS]
    return {"key": key, "title": title, "icon": icon(icon_name, 22), "items": texts,
            "dense": sum(len(text) for text in texts) > DENSE_SECTION_CHARS}


def _sections(sections: dict, L: dict, *, student: bool = False) -> list[dict]:
    return [
        _section("strengths", L["strengths_student" if student else "strengths"], "thumbs_up", sections["strengths"]),
        _section("attention", L["attention"], "alert", sections["attention"]),
        _section("parents", L["parents"], "bulb", sections["parents"]),
    ]


def _header(snapshot: dict, L: dict) -> dict:
    stats = snapshot["group_stats"]
    return {
        "group": snapshot["group"]["name"],
        "course": snapshot["group"]["course"],
        "trainers": ", ".join(snapshot["group"]["trainers"]),
        "period": i18n.period(snapshot["period"]["start"], snapshot["period"]["end"]),
        "lessons": stats["conducted_lessons"],
        "generated": L["generated"].format(date=i18n.date(snapshot["today"])),
    }


def group_context(snapshot: dict, *, language: str, options: dict) -> dict:
    L = i18n.labels(language)
    stats = snapshot["group_stats"]
    comparison = snapshot.get("group_comparison") or {}
    with_comparison = options.get("include_comparison", True)

    def chip(metric: str, unit: str = " " + L["pp"]):
        return _change(comparison.get(metric), unit=unit) if with_comparison else None

    attendance = _metric(stats["attendance_rate"], language)
    homework = _metric(stats["homework_rate"], language)
    score = _metric(stats["average_score"], language, kind="score")
    tests = _metric(stats["test_average"], language)
    kpis = [
        {"icon": icon("users"), "label": L["active_students"], "value": str(stats["active_students"]), "has_data": True,
         "sub": L["excellent_results"].format(n=stats["excellent_count"]) if stats["excellent_count"] else "",
         "bar": None, "tone": "good", "change": None},
        {"icon": icon("calendar_check"), "label": L["conducted_lessons"], "value": str(stats["conducted_lessons"]),
         "has_data": True, "sub": L["of_planned"].format(planned=stats["planned_lessons"]), "bar": None,
         "tone": "good", "change": None},
        {"icon": icon("user_check"), "label": L["attendance"], "value": attendance["text"],
         "has_data": attendance["has_data"], "bar": attendance["bar"], "tone": attendance["tone"],
         "sub": L["absences"].format(n=stats["absences"]) if attendance["has_data"] else "",
         "change": chip("attendance_rate")},
        {"icon": icon("book"), "label": L["homework"], "value": homework["text"], "has_data": homework["has_data"],
         "bar": homework["bar"], "tone": homework["tone"],
         "sub": L["hw_done_of"].format(done=stats["homework_done"], due=stats["homework_due"]) if homework["has_data"] else "",
         "change": chip("homework_rate")},
        {"icon": icon("star"), "label": L["average_score"], "value": score["text"], "suffix": "/10" if score["has_data"] else "",
         "has_data": score["has_data"], "bar": score["bar"], "tone": score["tone"],
         "sub": L["scores_count"].format(n=stats["scored_count"]) if score["has_data"] else "",
         "change": chip("average_score", "")},
        {"icon": icon("clipboard"), "label": L["tests"], "value": tests["text"], "has_data": tests["has_data"],
         "bar": tests["bar"], "tone": tests["tone"],
         "sub": L["tests_count"].format(n=stats["tests_count"]) if tests["has_data"] else "",
         "change": chip("test_average")},
    ]

    rows = []
    for index, entry in enumerate(snapshot["students"], start=1):
        att = _metric(entry["attendance_rate"], language)
        hw = _metric(entry["homework_rate"], language)
        rows.append({
            "no": index,
            "name": entry["name"],
            "name_class": _name_class(entry["name"]),
            "lessons": L["attended_of"].format(attended=entry["attended"], held=entry["lessons_held"])
            if entry["lessons_held"] else L["no_data"],
            "attendance": att,
            "homework": hw,
            "homework_detail": f"{entry['homework_done']}/{entry['homework_due']}" if entry["homework_due"] else "",
            "score": i18n.score(entry["average_score"], language),
            "score_has_data": entry["average_score"] is not None,
            "tests": i18n.percent(entry["test_average"], language),
            "tests_has_data": entry["test_average"] is not None,
            "status": _status(entry["status"], L),
        })

    sections = None
    if options.get("include_recommendations", True):
        facts = recommendations.facts_for_group(snapshot, include_comparison=with_comparison)
        sections = _sections(recommendations.build(facts, scope="group", language=language), L)

    sections_px = layout.sections_height(sections)
    pages = layout.paginate(
        rows,
        table=options.get("include_table", True),
        kpis=options.get("include_group_stats", True),
        sections=sections is not None,
        sections_px=sections_px,
    )
    page_dicts = [
        {
            **dataclasses.asdict(page),
            "label": L["page"].format(page=page.number, pages=len(pages)),
        }
        for page in pages
    ]
    return {
        "lang": language,
        "L": L,
        "assets": assets(),
        "header": _header(snapshot, L),
        "kpis": kpis,
        "sections": sections,
        "pages": page_dicts,
        "page_count": len(pages),
        "sections_px": sections_px,
        "sections_max": layout.SECTIONS_MAX,
        "show_table": options.get("include_table", True) and bool(rows),
        "icons": {"calendar": icon("calendar", 18), "cap": icon("cap", 18), "users": icon("users", 18)},
        "page_width": layout.PAGE_WIDTH,
        "page_height": layout.PAGE_HEIGHT,
    }


def student_context(snapshot: dict, entry: dict, *, language: str, options: dict) -> dict:
    L = i18n.labels(language)
    with_comparison = options.get("include_comparison", True)
    comparison = entry.get("comparison") or {}
    pp = " " + L["pp"]

    attendance = _metric(entry["attendance_rate"], language)
    homework = _metric(entry["homework_rate"], language)
    score = _metric(entry["average_score"], language, kind="score")
    tests = _metric(entry["test_average"], language)

    def chip(metric: str, unit: str = pp):
        return _change(comparison.get(metric), unit=unit) if with_comparison else None

    kpis = [
        {"icon": icon("calendar_check"), "label": L["lessons_attended"],
         "value": f"{entry['attended']}" if entry["attendance_marked"] else L["no_data"],
         "suffix": f"/{entry['attendance_marked']}" if entry["attendance_marked"] else "",
         "has_data": bool(entry["attendance_marked"]), "bar": None, "tone": "good",
         "sub": L["absences"].format(n=entry["absences"]) if entry["attendance_marked"] else "", "change": None},
        {"icon": icon("user_check"), "label": L["attendance"], "value": attendance["text"],
         "has_data": attendance["has_data"], "bar": attendance["bar"], "tone": attendance["tone"], "sub": "",
         "change": chip("attendance_rate")},
        {"icon": icon("book"), "label": L["homework"], "value": homework["text"], "has_data": homework["has_data"],
         "bar": homework["bar"], "tone": homework["tone"],
         "sub": L["hw_done_of"].format(done=entry["homework_done"], due=entry["homework_due"]) if homework["has_data"] else "",
         "change": chip("homework_rate")},
        {"icon": icon("star"), "label": L["average_score"], "value": score["text"],
         "suffix": "/10" if score["has_data"] else "", "has_data": score["has_data"], "bar": score["bar"],
         "tone": score["tone"], "sub": L["scores_count"].format(n=entry["scored_count"]) if score["has_data"] else "",
         "change": chip("average_score", "")},
        {"icon": icon("clipboard"), "label": L["tests"], "value": tests["text"], "has_data": tests["has_data"],
         "bar": tests["bar"], "tone": tests["tone"],
         "sub": L["tests_count"].format(n=entry["tests_count"]) if tests["has_data"] else "",
         "change": chip("test_average")},
    ]

    compare_rows = []
    if with_comparison:
        for metric, label, kind in (
            ("attendance_rate", L["attendance"], "percent"),
            ("homework_rate", L["homework"], "percent"),
            ("average_score", L["average_score"], "score"),
            ("test_average", L["tests"], "percent"),
        ):
            item = comparison.get(metric, {})
            fmt = i18n.score if kind == "score" else i18n.percent
            compare_rows.append({
                "label": label,
                "previous": fmt(item.get("previous"), language),
                "current": fmt(item.get("current"), language),
                "change": _change(item, unit="" if kind == "score" else pp),
            })

    tests_list = [
        {
            "title": test["title"] or "—",
            "date": i18n.date(test["date"]) if test["date"] else "",
            "score": i18n.percent(test["score"], language),
            "tone": tone(test["score"]),
            "passed": test["passed"],
        }
        for test in entry["tests"]
    ]
    max_tests = 5
    sections = None
    if options.get("include_recommendations", True):
        facts = recommendations.facts_for_student(entry, include_comparison=with_comparison)
        sections = _sections(recommendations.build(facts, scope="student", language=language), L, student=True)

    return {
        "lang": language,
        "L": L,
        "assets": assets(),
        "header": _header(snapshot, L),
        "student": {"name": entry["name"], "name_class": _name_class(entry["name"]), "status": _status(entry["status"], L)},
        "kpis": kpis,
        "compare_rows": compare_rows,
        "tests": tests_list[:max_tests],
        "more_tests": L["more_tests"].format(n=len(tests_list) - max_tests) if len(tests_list) > max_tests else "",
        "sections": sections,
        "icons": {"calendar": icon("calendar", 18), "cap": icon("cap", 18), "users": icon("users", 18),
                  "trend": icon("up", 22), "tests": icon("clipboard", 22)},
        "page_width": layout.PAGE_WIDTH,
        "page_height": layout.PAGE_HEIGHT,
    }
