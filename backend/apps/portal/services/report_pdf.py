"""The parent's monthly report as an A4 PDF, in Russian or Kyrgyz.

Only a renderer: every number comes from services.reports.monthly_report —
the very data the portal page shows for the same month. Drawn with
reportlab in the family of the academy's other PDFs (DejaVu fonts, the LMS
green palette and primitives from academy.services.monthly_report_pdf).
"""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from apps.academy.services.monthly_report_pdf import (
    BORDER,
    BRAND,
    BRAND_DARK,
    BRAND_SOFT,
    INK,
    INK_MUTED,
    INK_SECONDARY,
    SURFACE_MUTED,
    WHITE,
    _BOLD,
    _REGULAR,
    _ensure_fonts,
    _progress_bar,
    _rounded_rect,
)

PAGE_W, PAGE_H = A4
MARGIN = 40
CONTENT_W = PAGE_W - 2 * MARGIN
BOTTOM = 60
WARN = colors.HexColor("#b4790f")
BAD = colors.HexColor("#c7402e")
# Second chart series — the same validated pair as the portal page (green #2f8f5b, blue #2563a8).
SERIES_2 = colors.HexColor("#2563a8")

MONTHS = {
    "ru": ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь",
           "Октябрь", "Ноябрь", "Декабрь"],
    "ky": ["", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь",
           "Октябрь", "Ноябрь", "Декабрь"],
}

LABELS = {
    "ru": {
        "title": "Ежемесячный отчёт об успеваемости",
        "preliminary": "предварительный — месяц ещё идёт",
        "student": "Ученик", "group": "Группа", "course": "Курс", "branch": "Филиал",
        "attendance": "Посещаемость", "homework": "Домашние задания", "tests": "Тесты", "xp": "Опыт (XP)",
        "total_lessons": "Проведено занятий", "attended": "Посетил", "missed": "Пропустил", "late": "Опозданий",
        "assigned": "Задано", "completed": "Выполнено", "avg_score": "Средний балл", "no_data": "Нет данных",
        "tests_count": "Тестов пройдено", "tests_avg": "Средний результат",
        "progress": "Успеваемость по предметам", "subject": "Предмет", "lessons": "Занятия",
        "trend": "Динамика за полгода", "comments": "Комментарии тренеров", "no_comments": "Комментариев за месяц нет.",
        "xp_attendance": "за посещение", "xp_homework": "за домашние задания", "xp_tests": "за тесты",
        "change": "к прошлому месяцу", "test_list": "Результаты тестов", "page": "Страница {n} из {total}",
        "footer": "OkurmenKIDS · отчёт сформирован автоматически по данным LMS",
    },
    "ky": {
        "title": "Айлык жетишкендик отчёту",
        "preliminary": "алдын ала — ай али бүтө элек",
        "student": "Окуучу", "group": "Топ", "course": "Курс", "branch": "Филиал",
        "attendance": "Катышуу", "homework": "Үй тапшырмалары", "tests": "Тесттер", "xp": "Тажрыйба (XP)",
        "total_lessons": "Өткөн сабактар", "attended": "Катышты", "missed": "Калтырды", "late": "Кечигүү",
        "assigned": "Берилди", "completed": "Аткарылды", "avg_score": "Орточо балл", "no_data": "Маалымат жок",
        "tests_count": "Тапшырылган тесттер", "tests_avg": "Орточо жыйынтык",
        "progress": "Сабактар боюнча жетишкендик", "subject": "Сабак", "lessons": "Сабактар",
        "trend": "Акыркы алты айдагы өзгөрүү", "comments": "Машыктыруучулардын пикирлери",
        "no_comments": "Бул айда пикир жок.",
        "xp_attendance": "катышуу үчүн", "xp_homework": "үй тапшырмасы үчүн", "xp_tests": "тесттер үчүн",
        "change": "өткөн айга салыштырмалуу", "test_list": "Тесттердин жыйынтыгы", "page": "{total} беттин {n}-бети",
        "footer": "OkurmenKIDS · отчёт LMS маалыматтары боюнча автоматтык түрдө түзүлдү",
    },
}

FILENAME_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september",
                   "october", "november", "december")


def pdf_filename(report: dict) -> str:
    period = report["period"]
    return f"report_{report['student']['id']}_{FILENAME_MONTHS[period['month'] - 1]}_{period['year']}.pdf"


def _num(value, suffix="") -> str:
    if value is None:
        return "—"
    text = f"{value:g}" if isinstance(value, float) else str(value)
    return text.replace(".", ",") + suffix


class _Doc:
    def __init__(self, lang: str):
        _ensure_fonts()
        self.lang = lang if lang in LABELS else "ru"
        self.t = LABELS[self.lang]
        self.buffer = io.BytesIO()
        self.c = canvas.Canvas(self.buffer, pagesize=A4)
        self.y = PAGE_H - MARGIN
        self.pages = 1

    def need(self, height: float):
        if self.y - height < BOTTOM:
            self.c.showPage()
            self.pages += 1
            self.y = PAGE_H - MARGIN

    def text(self, x, y, value, size=10, font=_REGULAR, color=INK, max_w=None, align="left"):
        c = self.c
        value = str(value)
        if max_w is not None:
            while value and pdfmetrics.stringWidth(value, font, size) > max_w:
                value = value[:-2] + "…" if len(value) > 2 else ""
        c.setFont(font, size)
        c.setFillColor(color)
        if align == "right":
            c.drawRightString(x, y, value)
        elif align == "center":
            c.drawCentredString(x, y, value)
        else:
            c.drawString(x, y, value)

    def wrap(self, value: str, font, size, width) -> list[str]:
        lines = []
        for paragraph in str(value).splitlines() or [""]:
            line = ""
            for word in paragraph.split():
                candidate = f"{line} {word}".strip()
                if pdfmetrics.stringWidth(candidate, font, size) <= width:
                    line = candidate
                else:
                    if line:
                        lines.append(line)
                    line = word
            lines.append(line)
        return lines

    def heading(self, value):
        self.need(40)
        self.y -= 22
        self.text(MARGIN, self.y, value, 13, _BOLD, BRAND_DARK)
        self.y -= 10


def _header(doc: _Doc, report: dict):
    c, t = doc.c, doc.t
    period, student = report["period"], report["student"]
    _rounded_rect(c, MARGIN, PAGE_H - MARGIN - 92, CONTENT_W, 92, 14, fill=BRAND)
    doc.text(MARGIN + 20, PAGE_H - MARGIN - 30, "OkurmenKIDS", 11, _BOLD, BRAND_SOFT)
    doc.text(MARGIN + 20, PAGE_H - MARGIN - 52, t["title"], 16, _BOLD, WHITE, max_w=CONTENT_W - 40)
    month = f"{MONTHS[doc.lang][period['month']]} {period['year']}"
    if not period["is_complete"]:
        month += f" · {t['preliminary']}"
    doc.text(MARGIN + 20, PAGE_H - MARGIN - 74, month, 10, _REGULAR, BRAND_SOFT)
    doc.y = PAGE_H - MARGIN - 112
    details = [
        (t["student"], student["full_name"]),
        (t["group"], (student["group"] or {}).get("name") or "—"),
        (t["course"], (student["course"] or {}).get("name") or "—"),
        (t["branch"], (student["branch"] or {}).get("name_ky" if doc.lang == "ky" else "name")
         or (student["branch"] or {}).get("name") or "—"),
    ]
    col = CONTENT_W / 4
    for index, (label, value) in enumerate(details):
        x = MARGIN + index * col
        doc.text(x, doc.y, label, 8, _REGULAR, INK_MUTED)
        doc.text(x, doc.y - 14, value, 10, _BOLD, INK, max_w=col - 8)
    doc.y -= 30


def _cards(doc: _Doc, report: dict):
    t = doc.t
    att, hw, tests, xp = report["attendance"], report["homework"], report["tests"], report["xp"]
    change = report["progress"]["change"]
    cards = [
        (t["attendance"], _num(att["percent"], "%"), att["percent"],
         f"{t['attended']}: {att['attended']} · {t['missed']}: {att['missed']}", change["attendance_rate"]),
        (t["homework"], _num(hw["completion_rate"], "%"), hw["completion_rate"],
         f"{t['completed']}: {hw['completed']} / {hw['assigned']}", change["homework_rate"]),
        (t["avg_score"], _num(hw["average_score"]), (hw["average_score"] or 0) * 10 if hw["average_score"] is not None else None,
         f"{t['tests_avg']}: {_num(tests['average'], '%')}", change["average_score"]),
        (t["xp"], f"+{xp['total']}", None, f"{t['total_lessons']}: {att['total_lessons']}", None),
    ]
    doc.need(100)
    gap = 10
    w = (CONTENT_W - gap * 3) / 4
    top = doc.y
    for index, (label, value, percent, sub, delta) in enumerate(cards):
        x = MARGIN + index * (w + gap)
        _rounded_rect(doc.c, x, top - 88, w, 88, 12, fill=SURFACE_MUTED, stroke=BORDER)
        doc.text(x + 12, top - 20, label, 8, _REGULAR, INK_SECONDARY, max_w=w - 24)
        doc.text(x + 12, top - 44, value if value != "—" else t["no_data"], 17 if value != "—" else 11, _BOLD, INK,
                 max_w=w - 24)
        if percent is not None:
            color = BRAND if percent >= 80 else (WARN if percent >= 50 else BAD)
            _progress_bar(doc.c, x + 12, top - 58, w - 24, 5, percent, color)
        doc.text(x + 12, top - 72, sub, 7, _REGULAR, INK_MUTED, max_w=w - 24)
        if delta is not None:
            sign = "+" if delta > 0 else ""
            doc.text(x + 12, top - 82, f"{sign}{_num(delta)} {t['change']}", 6.5, _REGULAR,
                     BRAND_DARK if delta >= 0 else BAD, max_w=w - 24)
    doc.y = top - 100


def _trend(doc: _Doc, report: dict):
    t = doc.t
    doc.heading(t["trend"])
    doc.need(150)
    c = doc.c
    chart_h, top = 110, doc.y
    base = top - chart_h
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.6)
    for pct in (0, 50, 100):
        y = base + chart_h * pct / 100
        c.line(MARGIN + 28, y, MARGIN + CONTENT_W, y)
        doc.text(MARGIN + 22, y - 3, f"{pct}%", 7, _REGULAR, INK_MUTED, align="right")
    trend = report["trend"]
    slot = (CONTENT_W - 36) / len(trend)
    bar_w = min(16, slot / 3)
    for index, item in enumerate(trend):
        cx = MARGIN + 36 + slot * index + slot / 2
        for offset, key, color in ((-bar_w / 2 - 1, "attendance_rate", BRAND), (bar_w / 2 + 1, "homework_rate", SERIES_2)):
            value = item[key]
            if value is None:
                continue
            h = chart_h * value / 100
            _rounded_rect(c, cx + offset - bar_w / 2, base, bar_w, max(h, 1.5), 2, fill=color)
        doc.text(cx, base - 12, MONTHS[doc.lang][item["month"]][:3], 7.5, _REGULAR, INK_SECONDARY, align="center")
        doc.text(cx, base - 22, f"{item['xp']} XP", 6.5, _REGULAR, INK_MUTED, align="center")
    legend_y = base - 36
    for i, (label, color) in enumerate(((t["attendance"], BRAND), (t["homework"], SERIES_2))):
        x = MARGIN + 36 + i * 130
        _rounded_rect(c, x, legend_y, 8, 8, 2, fill=color)
        doc.text(x + 12, legend_y + 1, label, 8, _REGULAR, INK_SECONDARY)
    doc.y = legend_y - 8


def _table(doc: _Doc, headers, rows, widths):
    c = doc.c
    doc.need(24 + 18 * min(len(rows), 3))
    _rounded_rect(c, MARGIN, doc.y - 20, CONTENT_W, 20, 6, fill=BRAND_SOFT)
    x = MARGIN + 8
    for header, width in zip(headers, widths):
        doc.text(x, doc.y - 14, header, 8, _BOLD, BRAND_DARK, max_w=width - 6)
        x += width
    doc.y -= 20
    for row in rows:
        doc.need(18)
        x = MARGIN + 8
        for value, width in zip(row, widths):
            doc.text(x, doc.y - 13, value, 8.5, _REGULAR, INK, max_w=width - 6)
            x += width
        c.setStrokeColor(BORDER)
        c.line(MARGIN, doc.y - 18, MARGIN + CONTENT_W, doc.y - 18)
        doc.y -= 18
    doc.y -= 6


def _sections(doc: _Doc, report: dict):
    t = doc.t
    subjects = report["progress"]["subjects"]
    if subjects:
        doc.heading(t["progress"])
        _table(doc, [t["subject"], t["lessons"], t["attendance"], t["homework"], t["avg_score"]],
               [[s["subject"], str(s["lessons"]), _num(s["attendance_rate"], "%"), _num(s["homework_rate"], "%"),
                 _num(s["average_score"])] for s in subjects],
               [CONTENT_W * 0.36, CONTENT_W * 0.13, CONTENT_W * 0.17, CONTENT_W * 0.17, CONTENT_W * 0.17])
    if report["tests"]["items"]:
        doc.heading(t["test_list"])
        _table(doc, [t["tests"], "", t["tests_avg"]],
               [[test["title"], test["date"].strftime("%d.%m.%Y") if test["date"] else "", _num(test["score"], "%")]
                for test in report["tests"]["items"]],
               [CONTENT_W * 0.6, CONTENT_W * 0.2, CONTENT_W * 0.2])
    xp = report["xp"]
    doc.heading(t["xp"])
    doc.need(20)
    doc.text(MARGIN, doc.y - 6, f"+{xp['attendance']} {t['xp_attendance']} · +{xp['homework']} {t['xp_homework']} · "
             f"+{xp['tests']} {t['xp_tests']}", 9.5, _REGULAR, INK_SECONDARY)
    doc.y -= 16

    doc.heading(t["comments"])
    if not report["comments"]:
        doc.need(16)
        doc.text(MARGIN, doc.y - 6, t["no_comments"], 9.5, _REGULAR, INK_MUTED)
        doc.y -= 16
    for item in report["comments"]:
        meta = " · ".join(filter(None, [
            item["date"].strftime("%d.%m.%Y") if item["date"] else "",
            (item["subject"] or {}).get("name"), (item["teacher"] or {}).get("name"), item["title"],
        ]))
        lines = doc.wrap(item["text"], _REGULAR, 9.5, CONTENT_W - 28)
        height = 22 + 13 * len(lines)
        doc.need(height + 6)
        _rounded_rect(doc.c, MARGIN, doc.y - height, CONTENT_W, height, 8, fill=SURFACE_MUTED)
        doc.c.setFillColor(BRAND)
        doc.c.rect(MARGIN, doc.y - height + 6, 3, height - 12, stroke=0, fill=1)
        doc.text(MARGIN + 14, doc.y - 14, meta, 7.5, _REGULAR, INK_MUTED, max_w=CONTENT_W - 28)
        for index, line in enumerate(lines):
            doc.text(MARGIN + 14, doc.y - 28 - 13 * index, line, 9.5, _REGULAR, INK)
        doc.y -= height + 6


def render(report: dict, lang: str = "ru") -> bytes:
    doc = _Doc(lang)
    _header(doc, report)
    _cards(doc, report)
    _trend(doc, report)
    _sections(doc, report)
    doc.c.showPage()
    doc.c.save()
    raw = doc.buffer.getvalue()
    # Second pass with the page total known for «Страница N из M».
    return _with_footer(report, lang, doc.pages) if doc.pages else raw


def _with_footer(report: dict, lang: str, total: int) -> bytes:
    doc = _Doc(lang)
    original_show = doc.c.showPage

    def show_page():
        doc.text(MARGIN, 30, doc.t["footer"], 7, _REGULAR, INK_MUTED)
        doc.text(PAGE_W - MARGIN, 30, doc.t["page"].format(n=doc.c.getPageNumber(), total=total), 7, _REGULAR,
                 INK_MUTED, align="right")
        original_show()

    doc.c.showPage = show_page
    _header(doc, report)
    _cards(doc, report)
    _trend(doc, report)
    _sections(doc, report)
    doc.c.showPage()
    doc.c.save()
    return doc.buffer.getvalue()
