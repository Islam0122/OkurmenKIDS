"""Academy Performance Report — the Reports section as a print-ready A4 PDF.

Drawn directly with reportlab's canvas, in the same visual family as the
existing monthly reports (fonts, palette, rounded-rect/progress-bar
primitives are imported from services.monthly_report_pdf). Every number
comes from services.reports.service.build_full_report — the very same
figures the Reports screens show for the same filters.

Layout: page 1 — cover + summary + KPI; then GROUP PERFORMANCE; then
TEACHER PERFORMANCE (tables continue across pages with a repeated header);
last — KEY STATISTICS.
"""
from __future__ import annotations

import io

from django.utils import timezone
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
    _truncate_text,
    _wrap_text,
)
from .kpi import COMPONENT_LABELS, LEVEL_LABELS, kpi_level
from .service import describe_filters

PAGE_W, PAGE_H = A4
MARGIN = 40
CONTENT_W = PAGE_W - 2 * MARGIN
FOOTER_H = 30

GOOD = colors.HexColor("#2f8f5b")
GOOD_SOFT = colors.HexColor("#e7f3ec")
WARN = colors.HexColor("#b4790f")
WARN_SOFT = colors.HexColor("#fbf1df")
BAD = colors.HexColor("#c7402e")
BAD_SOFT = colors.HexColor("#fbeae7")

LEVEL_COLORS = {
    "good": (GOOD, GOOD_SOFT),
    "warning": (WARN, WARN_SOFT),
    "bad": (BAD, BAD_SOFT),
    "none": (INK_MUTED, SURFACE_MUTED),
}


def _pct(value) -> str:
    if value is None:
        return "—"
    return f"{value:g}".replace(".", ",") + "%"


def _level(value) -> str:
    return kpi_level(value)


def _date(value) -> str:
    return value.strftime("%d.%m.%Y")


class _NumberedCanvas(canvas.Canvas):
    """Defers page output so every footer can say "page N of M"."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_pages = []

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        self._saved_pages.append(dict(self.__dict__))
        total = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int) -> None:
        self.saveState()
        self.setStrokeColor(BORDER)
        self.setLineWidth(0.6)
        self.line(MARGIN, FOOTER_H, PAGE_W - MARGIN, FOOTER_H)
        self.setFont(_REGULAR, 7.5)
        self.setFillColor(INK_MUTED)
        self.drawString(MARGIN, FOOTER_H - 12, "OkurmenKIDS · Academy Performance Report")
        self.drawRightString(PAGE_W - MARGIN, FOOTER_H - 12, f"Страница {self._pageNumber} из {total}")
        self.restoreState()


class _Doc:
    def __init__(self, buffer: io.BytesIO, title: str):
        self.c = _NumberedCanvas(buffer, pagesize=A4)
        self.c.setTitle(title)
        self.c.setAuthor("OkurmenKIDS")
        self.y = PAGE_H - MARGIN

    def new_page(self) -> None:
        self.c.showPage()
        self.y = PAGE_H - MARGIN

    def ensure_space(self, needed: float) -> bool:
        if self.y - needed < MARGIN + FOOTER_H:
            self.new_page()
            return True
        return False

    def text(self, x, y, text, font=_REGULAR, size=10, color=INK, align="left"):
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        if align == "right":
            self.c.drawRightString(x, y, text)
        elif align == "center":
            self.c.drawCentredString(x, y, text)
        else:
            self.c.drawString(x, y, text)


def _page_title(doc: _Doc, eyebrow: str, title: str, subtitle: str | None = None) -> None:
    doc.text(MARGIN, doc.y, eyebrow, font=_BOLD, size=8, color=BRAND)
    doc.text(MARGIN, doc.y - 20, title, font=_BOLD, size=17, color=INK)
    doc.y -= 34
    if subtitle:
        doc.text(MARGIN, doc.y, subtitle, size=8.5, color=INK_SECONDARY)
        doc.y -= 14
    doc.y -= 8


def _section_label(doc: _Doc, label: str) -> None:
    doc.ensure_space(40)
    doc.text(MARGIN, doc.y, label.upper(), font=_BOLD, size=8.5, color=INK_SECONDARY)
    doc.y -= 12


def _badge(c, x_center, y, value) -> None:
    """KPI value plus its text status ("92,4% · Excellent") — the status is
    readable without color; color only reinforces it."""
    level = _level(value)
    fg, bg = LEVEL_COLORS[level]
    text = LEVEL_LABELS["none"] if level == "none" else f"{_pct(value)} · {LEVEL_LABELS[level]}"
    width = pdfmetrics.stringWidth(text, _BOLD, 7.2) + 14
    _rounded_rect(c, x_center - width / 2, y - 4, width, 14, 7, fill=bg)
    c.setFont(_BOLD, 7.2)
    c.setFillColor(fg)
    c.drawCentredString(x_center, y, text)


# ---------------------------------------------------------------------------
# Page 1 — cover, summary, KPI
# ---------------------------------------------------------------------------

def _draw_cover(doc: _Doc, report: dict) -> None:
    c = doc.c
    filters = report["filters"]
    band_h = 150
    c.saveState()
    c.setFillColor(BRAND_DARK)
    c.rect(0, PAGE_H - band_h, PAGE_W, band_h, stroke=0, fill=1)
    c.setFillColor(BRAND)
    c.rect(0, PAGE_H - band_h, PAGE_W, 5, stroke=0, fill=1)
    c.restoreState()

    top = PAGE_H - 48
    doc.text(MARGIN, top, "OKURMENKIDS", font=_BOLD, size=12, color=colors.HexColor("#bfe3cd"))
    doc.text(MARGIN, top - 30, "ACADEMY PERFORMANCE REPORT", font=_BOLD, size=21, color=WHITE)
    doc.text(MARGIN, top - 52, "Отчёт о результатах академии", size=10, color=colors.HexColor("#d7ecdf"))
    doc.text(MARGIN, top - 80, f"Период:  {_date(filters.start)} — {_date(filters.end)}   ({filters.period_label})",
             font=_BOLD, size=10, color=WHITE)

    doc.y = PAGE_H - band_h - 22
    doc.text(MARGIN, doc.y, "Фильтры: " + _truncate_text(describe_filters(filters), _REGULAR, 8.5, CONTENT_W - 50),
             size=8.5, color=INK_SECONDARY)
    doc.y -= 13
    generated = timezone.localtime().strftime("%d.%m.%Y %H:%M")
    doc.text(MARGIN, doc.y, f"Сформирован: {generated}. Все показатели рассчитаны по данным LMS.",
             size=8.5, color=INK_MUTED)
    doc.y -= 26


def _stat_cards(doc: _Doc, cards: list[tuple[str, str, str | None]]) -> None:
    gap = 10
    width = (CONTENT_W - gap * (len(cards) - 1)) / len(cards)
    height = 62
    doc.ensure_space(height + 10)
    top = doc.y
    for index, (value, label, hint) in enumerate(cards):
        x = MARGIN + index * (width + gap)
        _rounded_rect(doc.c, x, top - height, width, height, 8, fill=SURFACE_MUTED, stroke=BORDER, line_width=0.6)
        doc.text(x + 12, top - 28, value, font=_BOLD, size=18, color=INK)
        doc.text(x + 12, top - 44, label, size=8.2, color=INK_SECONDARY)
        if hint:
            doc.text(x + 12, top - 55, hint, size=6.8, color=INK_MUTED)
    doc.y = top - height - 18


def _kpi_block(doc: _Doc, overview: dict) -> None:
    kpi = overview["kpi"]
    weights = {w["key"]: w["weight"] for w in overview["kpi_weights"]}
    height = 150
    doc.ensure_space(height + 10)
    top = doc.y
    c = doc.c
    _rounded_rect(c, MARGIN, top - height, CONTENT_W, height, 10, fill=WHITE, stroke=BORDER, line_width=0.8)

    # Overall KPI (left)
    fg, bg = LEVEL_COLORS[kpi["level"]]
    box_w = 150
    _rounded_rect(c, MARGIN + 12, top - height + 12, box_w, height - 24, 8, fill=bg)
    doc.text(MARGIN + 12 + box_w / 2, top - 38, "OVERALL KPI", font=_BOLD, size=8, color=fg, align="center")
    doc.text(MARGIN + 12 + box_w / 2, top - 82, _pct(kpi["overall"]), font=_BOLD, size=30, color=fg, align="center")
    level_text = {"good": "Excellent (≥ 90%)", "warning": "Good (75–89%)", "bad": "Needs attention (< 75%)",
                  "none": "No data"}[kpi["level"]]
    doc.text(MARGIN + 12 + box_w / 2, top - 102, level_text, size=8, color=fg, align="center")

    # Components (right)
    x = MARGIN + box_w + 34
    bar_w = CONTENT_W - box_w - 34 - 70
    y = top - 30
    for key in ("attendance", "homework", "activity", "progress"):
        value = kpi[key]
        doc.text(x, y, f"{COMPONENT_LABELS[key]}  ·  вес {weights.get(key, 0):g}%", size=8.3, color=INK_SECONDARY)
        doc.text(PAGE_W - MARGIN - 14, y, _pct(value), font=_BOLD, size=10, color=INK, align="right")
        color, _soft = LEVEL_COLORS[_level(value)]
        _progress_bar(c, x, y - 12, bar_w + 50, 6, value or 0, color)
        y -= 30
    doc.y = top - height - 12
    doc.text(MARGIN, doc.y,
             "Overall KPI = взвешенное среднее компонентов с данными; компонент без данных («—») не учитывается.",
             size=7.3, color=INK_MUTED)
    doc.y -= 18


def _draw_summary_page(doc: _Doc, report: dict) -> None:
    ov = report["overview"]
    _draw_cover(doc, report)
    _section_label(doc, "Сводка")
    students = ov["students"]
    _stat_cards(doc, [
        (str(students["total"]), "Всего студентов", None),
        (str(students["active"]), "Активные", None),
        (str(students["left"]), "Ушли за период", None),
        (str(ov["teachers"]["total"]), "Тренеры", None),
        (str(ov["groups"]["total"]), "Группы", None),
    ])
    _stat_cards(doc, [
        (_pct(ov["attendance"]["rate"]), "Посещаемость", f"{ov['attendance']['total']} отметок"),
        (_pct(ov["homework"]["completion_rate"]), "Домашние задания", f"{ov['homework']['results']} результатов"),
        (f"{ov['lessons']['held']}/{ov['lessons']['total']}", "Проведено занятий", None),
        (_pct(students["retention_rate"]), "Удержание", None),
    ])
    _section_label(doc, "KPI академии")
    _kpi_block(doc, ov)
    if not ov["has_data"]:
        doc.text(MARGIN, doc.y, "За выбранный период нет занятий, отметок посещаемости и результатов ДЗ.",
                 font=_BOLD, size=9, color=WARN)
        doc.y -= 16


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def _table(doc: _Doc, columns: list[dict], rows: list[list], *, empty: str) -> None:
    """columns: {"title", "width" (fraction), "align", "badge"}. A row is a
    list of cell values (strings, or a float/None for badge columns)."""
    widths = [col["width"] * CONTENT_W for col in columns]
    header_h, row_h = 22, 20

    def draw_header():
        doc.ensure_space(header_h + row_h)
        top = doc.y
        _rounded_rect(doc.c, MARGIN, top - header_h, CONTENT_W, header_h, 5, fill=BRAND_SOFT)
        x = MARGIN
        for col, width in zip(columns, widths):
            _cell(doc, x, width, top - 14.5, col["title"], col, font=_BOLD, size=7.2, color=BRAND_DARK)
            x += width
        doc.y = top - header_h

    if not rows:
        draw_header()
        doc.y -= 18
        doc.text(MARGIN + CONTENT_W / 2, doc.y, empty, size=9, color=INK_MUTED, align="center")
        doc.y -= 16
        return

    draw_header()
    for index, row in enumerate(rows):
        if doc.y - row_h < MARGIN + FOOTER_H:
            doc.new_page()
            draw_header()
        top = doc.y
        if index % 2:
            doc.c.saveState()
            doc.c.setFillColor(SURFACE_MUTED)
            doc.c.rect(MARGIN, top - row_h, CONTENT_W, row_h, stroke=0, fill=1)
            doc.c.restoreState()
        x = MARGIN
        for col, width, value in zip(columns, widths, row):
            if col.get("badge"):
                _badge(doc.c, x + width / 2, top - 13.5, value)
            else:
                _cell(doc, x, width, top - 13.5, value, col)
            x += width
        doc.c.saveState()
        doc.c.setStrokeColor(BORDER)
        doc.c.setLineWidth(0.4)
        doc.c.line(MARGIN, top - row_h, MARGIN + CONTENT_W, top - row_h)
        doc.c.restoreState()
        doc.y = top - row_h
    doc.y -= 10


def _cell(doc, x, width, y, text, col, font=_REGULAR, size=7.8, color=INK):
    pad = 4
    text = _truncate_text(str(text), font, size, width - 2 * pad)
    align = col.get("align", "left")
    if align == "right":
        doc.text(x + width - pad, y, text, font=font, size=size, color=color, align="right")
    elif align == "center":
        doc.text(x + width / 2, y, text, font=font, size=size, color=color, align="center")
    else:
        doc.text(x + pad, y, text, font=font, size=size, color=color)


def _draw_groups(doc: _Doc, report: dict) -> None:
    doc.new_page()
    groups = report["groups"]
    ov = report["overview"]
    levels = ov["levels"]["groups"]
    _page_title(
        doc, "GROUP PERFORMANCE", "Результаты групп",
        f"{len(groups)} групп · KPI ≥ 90%: {levels['good']} · 75–89%: {levels['warning']} · "
        f"< 75%: {levels['bad']} · без данных: {levels['none']}",
    )
    columns = [
        {"title": "Группа", "width": 0.23},
        {"title": "Тренер", "width": 0.17},
        {"title": "Студ.", "width": 0.065, "align": "center"},
        {"title": "Актив.", "width": 0.07, "align": "center"},
        {"title": "Ушли", "width": 0.065, "align": "center"},
        {"title": "Посещ.", "width": 0.085, "align": "center"},
        {"title": "ДЗ", "width": 0.085, "align": "center"},
        {"title": "KPI / статус", "width": 0.23, "align": "center", "badge": True},
    ]
    rows = [
        [g["name"], g["teacher_names"], g["students"]["total"], g["students"]["active"], g["students"]["left"],
         _pct(g["attendance_rate"]), _pct(g["homework_rate"]), g["kpi"]]
        for g in sorted(groups, key=lambda g: (g["kpi"] is None, -(g["kpi"] or 0), g["name"]))
    ]
    _table(doc, columns, rows, empty="Нет групп для выбранных фильтров.")


def _draw_teachers(doc: _Doc, report: dict) -> None:
    doc.new_page()
    teachers = report["teachers"]
    _page_title(doc, "TEACHER PERFORMANCE", "Результаты тренеров",
                f"{len(teachers)} тренеров · показатели по занятиям, которые ведёт сам тренер")
    columns = [
        {"title": "Тренер", "width": 0.17},
        {"title": "Группы", "width": 0.19},
        {"title": "Студ.", "width": 0.065, "align": "center"},
        {"title": "Предметы", "width": 0.15},
        {"title": "Посещ.", "width": 0.085, "align": "center"},
        {"title": "ДЗ", "width": 0.085, "align": "center"},
        {"title": "KPI / статус", "width": 0.255, "align": "center", "badge": True},
    ]
    rows = [
        [t["name"], (f"{t['groups_count']}: " + ", ".join(g["name"] for g in t["groups"])) if t["groups"] else "Нет групп", t["students"]["total"],
         ", ".join(t["subjects"]) or "—", _pct(t["attendance_rate"]), _pct(t["homework_rate"]), t["kpi"]]
        for t in sorted(teachers, key=lambda t: (t["kpi"] is None, -(t["kpi"] or 0), t["name"]))
    ]
    _table(doc, columns, rows, empty="Нет тренеров для выбранных фильтров.")


# ---------------------------------------------------------------------------
# Key statistics
# ---------------------------------------------------------------------------

def _stat_panel(doc: _Doc, x, top, width, title, lines, accent) -> float:
    height = 26 + len(lines) * 15 + 8
    _rounded_rect(doc.c, x, top - height, width, height, 8, fill=WHITE, stroke=BORDER, line_width=0.7)
    doc.c.saveState()
    doc.c.setFillColor(accent)
    doc.c.rect(x, top - 20, 3, 12, stroke=0, fill=1)
    doc.c.restoreState()
    doc.text(x + 12, top - 17, title, font=_BOLD, size=9.2, color=INK)
    y = top - 36
    for label, value in lines:
        doc.text(x + 12, y, _truncate_text(label, _REGULAR, 8, width - 90), size=8, color=INK_SECONDARY)
        doc.text(x + width - 12, y, str(value), font=_BOLD, size=8.4, color=INK, align="right")
        y -= 15
    return height


def _draw_key_statistics(doc: _Doc, report: dict) -> None:
    doc.new_page()
    ov = report["overview"]
    _page_title(doc, "KEY STATISTICS", "Ключевые показатели")
    att, hw, lessons, st = ov["attendance"], ov["homework"], ov["lessons"], ov["students"]
    kpi = ov["kpi"]
    g_levels, t_levels = ov["levels"]["groups"], ov["levels"]["teachers"]
    teachers = report["teachers"]
    rated_teachers = [t["kpi"] for t in teachers if t["kpi"] is not None]
    rated_groups = [g["kpi"] for g in report["groups"] if g["kpi"] is not None]

    panels = [
        ("Посещаемость", GOOD, [
            ("Посещаемость", _pct(att["rate"])), ("Присутствовали", att["present"]), ("Опоздали", att["late"]),
            ("Отсутствовали", att["absent"]), ("Уважительная причина", att["excused"]),
        ]),
        ("Домашние задания", colors.HexColor("#2563a8"), [
            ("Выполнение ДЗ", _pct(hw["completion_rate"])), ("Выдано заданий", hw["assigned"]),
            ("Сдано", hw["submitted"]), ("Не сдано", hw["not_submitted"]), ("Проверено", hw["checked"]),
        ]),
        ("Активность студентов", WARN, [
            ("Активность (проведённые занятия)", _pct(kpi["activity"])),
            ("Проведено / наступивших занятий", f"{lessons['held']} / {lessons['due']}"),
            ("Отменено занятий", lessons["cancelled"]),
            ("Средний балл ДЗ", "—" if hw["average_score"] is None else f"{hw['average_score']:g}".replace(".", ",")),
            ("Прогресс", _pct(kpi["progress"])),
        ]),
        ("Удержание", BAD, [
            ("Удержание", _pct(st["retention_rate"])), ("Активные студенты", st["active"]),
            ("Ушли за период", st["left"]), ("Новые за период", st["new"]), ("Вернулись", st["returned"]),
        ]),
        ("Результаты тренеров", BRAND, [
            ("Тренеров в отчёте", len(teachers)),
            ("Средний KPI тренеров", _pct(round(sum(rated_teachers) / len(rated_teachers), 1)) if rated_teachers else "—"),
            ("KPI ≥ 90%", t_levels["good"]), ("KPI 75–89%", t_levels["warning"]), ("KPI < 75%", t_levels["bad"]),
        ]),
        ("Результаты групп", BRAND_DARK, [
            ("Групп в отчёте", len(report["groups"])),
            ("Средний KPI групп", _pct(round(sum(rated_groups) / len(rated_groups), 1)) if rated_groups else "—"),
            ("KPI ≥ 90%", g_levels["good"]), ("KPI 75–89%", g_levels["warning"]), ("KPI < 75%", g_levels["bad"]),
        ]),
    ]
    gap = 12
    width = (CONTENT_W - gap) / 2
    for index in range(0, len(panels), 2):
        top = doc.y
        heights = []
        for offset, (title, accent, lines) in enumerate(panels[index:index + 2]):
            heights.append(_stat_panel(doc, MARGIN + offset * (width + gap), top, width, title, lines, accent))
        doc.y = top - max(heights) - gap

    if ov["attention_groups"]:
        doc.y -= 4
        _section_label(doc, "Группы, требующие внимания (KPI < 90%)")
        for g in ov["attention_groups"]:
            doc.ensure_space(16)
            doc.text(MARGIN + 4, doc.y, _truncate_text(f"• {g['name']} — {g['teacher_names']}", _REGULAR, 8.5,
                                                       CONTENT_W - 130), size=8.5, color=INK)
            _badge(doc.c, PAGE_W - MARGIN - 55, doc.y, g["kpi"])
            doc.y -= 16

    doc.y -= 8
    for line in _wrap_text(
        "Методика: посещаемость = (присутствовал + опоздал) / все отметки; ДЗ = (сдано + проверено + с опозданием) "
        "/ все результаты; активность = проведённые / наступившие занятия периода; прогресс = средний балл ДЗ / 10. "
        "Студенты «всего/активные» — текущий состав; «ушли/вернулись/новые» — события за период.",
        _REGULAR, 7.3, CONTENT_W,
    ):
        doc.ensure_space(12)
        doc.text(MARGIN, doc.y, line, size=7.3, color=INK_MUTED)
        doc.y -= 10


def build_reports_pdf(report: dict) -> bytes:
    _ensure_fonts()
    buffer = io.BytesIO()
    filters = report["filters"]
    doc = _Doc(buffer, f"OkurmenKIDS — отчёт {_date(filters.start)}–{_date(filters.end)}")
    _draw_summary_page(doc, report)
    _draw_groups(doc, report)
    _draw_teachers(doc, report)
    _draw_key_statistics(doc, report)
    doc.c.save()
    return buffer.getvalue()


def pdf_filename(filters) -> str:
    return f"okurmenkids-report-{filters.start:%Y%m%d}-{filters.end:%Y%m%d}.pdf"
