"""«Отчёт по стипендиям» as an official A4 PDF document.

Built directly with reportlab's canvas, the same way the academy reports
are (apps/academy/services/monthly_report_pdf.py) — same bundled DejaVu
fonts (reportlab's built-in fonts have no Cyrillic), same palette, so all
Okurmen Kids PDFs look like one family. The figures come from
services.report.build_report, exactly what the admin page shows.

Only vector primitives are used for decoration (lines, rounded rects,
dots) — no emoji, no images.
"""
from __future__ import annotations

import io
from decimal import ROUND_HALF_UP, Decimal

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
    _rounded_rect,
    _truncate_text,
    _wrap_text,
)

from .report import PaymentStatus, ScholarshipReport, format_range

PAGE_W, PAGE_H = A4
MARGIN = 40
CONTENT_W = PAGE_W - 2 * MARGIN
FOOTER_H = 34  # room kept free at the bottom of every page for the footer

WARNING = colors.HexColor("#b4790f")
WARNING_SOFT = colors.HexColor("#fbf1df")
DANGER = colors.HexColor("#c7402e")
DANGER_SOFT = colors.HexColor("#fbeae7")

_STATUS_STYLE = {
    PaymentStatus.RECEIVED: (BRAND, BRAND_SOFT),
    PaymentStatus.PENDING: (WARNING, WARNING_SOFT),
    PaymentStatus.NOT_RECEIVED: (DANGER, DANGER_SOFT),
}

# (title, width, align) — widths add up to CONTENT_W. «Период» and
# «Статус» are wide enough to never cut a date or a status; the free-text
# columns wrap to two lines instead.
_COLUMNS = (
    ("№", 26, "center"),
    ("Ученик", 98, "left"),
    ("Группа", 68, "left"),
    ("Программа", 68, "left"),
    ("Сумма", 60, "right"),
    ("Период", 116, "left"),
    ("Статус", 79, "left"),
)
_WRAPPED = {"Ученик", "Группа", "Программа"}
_MAX_LINES = 2
_ROW_H = 20
_LINE_H = 9.5
_PERIOD_SIZE = 7.8
_HEAD_H = 22
_CELL_PAD = 5
_BODY_SIZE = 8.3

_NBSP = " "


def som(value) -> str:
    if value is None:
        return "—"
    amount = Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{amount:,}".replace(",", _NBSP) + f"{_NBSP}сом"


class _NumberedCanvas(canvas.Canvas):
    """Defers every page until save() so each footer can say «из N»."""

    def __init__(self, *args, footer_left: str = "", **kwargs):
        super().__init__(*args, **kwargs)
        self._footer_left = footer_left
        self._pages = []

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int) -> None:
        y = MARGIN - 14
        self.saveState()
        self.setStrokeColor(BORDER)
        self.setLineWidth(0.75)
        self.line(MARGIN, y + 12, PAGE_W - MARGIN, y + 12)
        self.setFont(_REGULAR, 7.5)
        self.setFillColor(INK_MUTED)
        self.drawString(MARGIN, y, self._footer_left)
        self.drawRightString(PAGE_W - MARGIN, y, f"Страница {self._pageNumber} из {total}")
        self.restoreState()


class _Doc:
    def __init__(self, buffer: io.BytesIO, report: ScholarshipReport):
        self.report = report
        self.c = _NumberedCanvas(
            buffer, pagesize=A4,
            footer_left=f"Okurmen Kids · Отчёт по стипендиям · {report.filters.range_label}",
        )
        self.c.setTitle(f"Отчёт по стипендиям {report.filters.range_label}")
        self.c.setAuthor("Okurmen Kids")
        self.y = PAGE_H - MARGIN

    @property
    def bottom(self) -> float:
        return MARGIN + FOOTER_H

    def new_page(self) -> None:
        self.c.showPage()
        self.y = PAGE_H - MARGIN
        # Running header on continuation pages.
        self.text(MARGIN, self.y - 8, "ОТЧЁТ ПО СТИПЕНДИЯМ", font=_BOLD, size=8.5, color=BRAND_DARK)
        self.text(
            PAGE_W - MARGIN, self.y - 8, f"Период: {self.report.filters.range_label}",
            size=8.5, color=INK_SECONDARY, align="right",
        )
        self.y -= 16
        self.hline(self.y)
        self.y -= 14

    def ensure_space(self, needed: float) -> bool:
        """Start a new page when `needed` does not fit; True if it did."""
        if self.y - needed < self.bottom:
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

    def hline(self, y, color=BORDER, width=0.75, x1=MARGIN, x2=PAGE_W - MARGIN):
        self.c.saveState()
        self.c.setStrokeColor(color)
        self.c.setLineWidth(width)
        self.c.line(x1, y, x2, y)
        self.c.restoreState()


def _section_title(doc: _Doc, title: str) -> None:
    doc.text(MARGIN, doc.y, title, font=_BOLD, size=11, color=INK)
    doc.y -= 8
    doc.hline(doc.y, color=BRAND, width=1.2, x2=MARGIN + 28)
    doc.y -= 14


# -- header ------------------------------------------------------------------

def _draw_header(doc: _Doc) -> None:
    filters = doc.report.filters
    top = doc.y

    # Brand line: a green bar and the academy name.
    doc.c.saveState()
    doc.c.setFillColor(BRAND)
    doc.c.rect(MARGIN, top - 4, 4, 18, stroke=0, fill=1)
    doc.c.restoreState()
    doc.text(MARGIN + 12, top, "Okurmen Kids", font=_BOLD, size=12, color=BRAND)
    doc.text(PAGE_W - MARGIN, top, "Стипендиальная программа", size=8.5, color=INK_MUTED, align="right")

    doc.y = top - 20
    doc.hline(doc.y)

    doc.y -= 34
    doc.text(MARGIN, doc.y, "ОТЧЁТ ПО СТИПЕНДИЯМ", font=_BOLD, size=19, color=INK)
    doc.y -= 20
    doc.text(MARGIN, doc.y, "Okurmen Kids", font=_REGULAR, size=10.5, color=INK_SECONDARY)
    doc.y -= 20
    doc.text(MARGIN, doc.y, "Период:", font=_REGULAR, size=11, color=INK_SECONDARY)
    doc.text(MARGIN + 50, doc.y, filters.range_label, font=_BOLD, size=11, color=INK)

    extra = []
    if filters.group:
        extra.append(("Группа", filters.group))
    if filters.program:
        extra.append(("Программа", filters.program))
    if filters.student:
        extra.append(("Ученик", filters.student))
    if filters.status:
        extra.append(("Статус выплаты", PaymentStatus.LABELS[filters.status]))
    for label, value in extra:
        doc.y -= 15
        doc.text(MARGIN, doc.y, f"{label}:", size=9.5, color=INK_SECONDARY)
        doc.text(MARGIN + 100, doc.y, _truncate_text(value, _BOLD, 9.5, CONTENT_W - 100), font=_BOLD, size=9.5)

    periods = doc.report.periods
    if periods:
        doc.y -= 15
        label = "Стипендиальные периоды:" if len(periods) > 1 else "Стипендиальный период:"
        names = "; ".join(f"{p.title} {format_range(p.period_start, p.period_end)}" for p in periods)
        doc.text(MARGIN, doc.y, label, size=8.5, color=INK_MUTED)
        doc.text(
            MARGIN + 130, doc.y, _truncate_text(names, _REGULAR, 8.5, CONTENT_W - 130), size=8.5, color=INK_MUTED,
        )
    doc.y -= 26


# -- summary -----------------------------------------------------------------

def _draw_summary(doc: _Doc) -> None:
    stats = doc.report.stats
    cards = (
        ("Всего учеников", str(stats.total_students), INK_MUTED),
        ("Получили стипендию", str(stats.received_students), BRAND),
        ("Ожидают выплату", str(stats.pending_students), WARNING),
        ("Общая сумма", som(stats.total_amount), BRAND_DARK),
        ("Средняя стипендия", som(stats.average_amount), INK_SECONDARY),
    )
    _section_title(doc, "Краткое резюме")
    gap = 8
    card_w = (CONTENT_W - gap * (len(cards) - 1)) / len(cards)
    card_h = 50
    y = doc.y - card_h
    for index, (label, value, accent) in enumerate(cards):
        x = MARGIN + index * (card_w + gap)
        _rounded_rect(doc.c, x, y, card_w, card_h, 6, fill=WHITE, stroke=BORDER, line_width=0.75)
        doc.c.saveState()
        doc.c.setFillColor(accent)
        doc.c.rect(x, y + 10, 2.5, card_h - 20, stroke=0, fill=1)
        doc.c.restoreState()
        doc.text(x + 10, y + card_h - 17, label, size=7.5, color=INK_SECONDARY)
        size = 14
        while size > 9 and doc.c.stringWidth(value, _BOLD, size) > card_w - 18:
            size -= 0.5
        doc.text(x + 10, y + 12, value, font=_BOLD, size=size, color=INK)
    doc.y = y - 26


# -- table -------------------------------------------------------------------

def _draw_table_head(doc: _Doc) -> None:
    y = doc.y - _HEAD_H
    doc.c.saveState()
    doc.c.setFillColor(BRAND)
    doc.c.rect(MARGIN, y, CONTENT_W, _HEAD_H, stroke=0, fill=1)
    doc.c.restoreState()
    x = MARGIN
    for title, width, align in _COLUMNS:
        _cell(doc, x, y, width, title, align, font=_BOLD, size=7.8, color=WHITE, height=_HEAD_H)
        x += width
    doc.y = y


def _cell(doc: _Doc, x, y, width, value, align, *, font=_REGULAR, size=_BODY_SIZE, color=INK, height=_ROW_H):
    value = _truncate_text(value, font, size, width - 2 * _CELL_PAD)
    baseline = y + (height - size) / 2 + 1.5
    if align == "right":
        doc.text(x + width - _CELL_PAD, baseline, value, font=font, size=size, color=color, align="right")
    elif align == "center":
        doc.text(x + width / 2, baseline, value, font=font, size=size, color=color, align="center")
    else:
        doc.text(x + _CELL_PAD, baseline, value, font=font, size=size, color=color)


def _cell_lines(value: str, font, size, width) -> list[str]:
    """`value` wrapped to at most two lines; the last one gets an ellipsis
    when the text is longer still."""
    max_width = width - 2 * _CELL_PAD
    lines = []
    for line in _wrap_text(value, font, size, max_width) or [value]:
        lines.extend(_split_long(line, font, size, max_width))
    if len(lines) > _MAX_LINES:
        lines = lines[:_MAX_LINES - 1] + [" ".join(lines[_MAX_LINES - 1:])]
    return [_truncate_text(line, font, size, max_width) for line in lines]


def _split_long(text: str, font, size, max_width) -> list[str]:
    """A single word wider than the column (a group code like
    «PRO-GROUP-2026-01») is broken after a hyphen when possible, else at
    the last character that fits."""
    parts = []
    while _text_width(text, font, size) > max_width and len(text) > 1:
        cut = len(text)
        while cut > 1 and _text_width(text[:cut], font, size) > max_width:
            cut -= 1
        hyphen = text.rfind("-", 0, cut)
        if hyphen > 0:
            cut = hyphen + 1
        parts.append(text[:cut])
        text = text[cut:]
    return parts + [text]


def _text_width(text: str, font, size) -> float:
    return pdfmetrics.stringWidth(text, font, size)


def _multiline_cell(doc: _Doc, x, y, width, lines, *, font, size=_BODY_SIZE, color=INK, height=_ROW_H):
    block_h = size + (len(lines) - 1) * _LINE_H
    baseline = y + (height + block_h) / 2 - size + 1.5
    for line in lines:
        doc.text(x + _CELL_PAD, baseline, line, font=font, size=size, color=color)
        baseline -= _LINE_H


def _status_pill(doc: _Doc, x, y, width, status: str, label: str, height=_ROW_H) -> None:
    color, soft = _STATUS_STYLE[status]
    size = 7.5
    pill_w = min(width - 2 * _CELL_PAD, doc.c.stringWidth(label, _BOLD, size) + 18)
    pill_h = 12
    px, py = x + _CELL_PAD, y + (height - pill_h) / 2
    _rounded_rect(doc.c, px, py, pill_w, pill_h, pill_h / 2, fill=soft)
    doc.c.saveState()
    doc.c.setFillColor(color)
    doc.c.circle(px + 6.5, py + pill_h / 2, 2, stroke=0, fill=1)
    doc.c.restoreState()
    doc.text(px + 11.5, py + 3.3, label, font=_BOLD, size=size, color=color)


def _draw_table(doc: _Doc) -> None:
    rows = doc.report.rows
    doc.ensure_space(30 + _HEAD_H + _ROW_H * max(1, min(len(rows), 3)))
    _section_title(doc, "Список учеников")
    _draw_table_head(doc)

    if not rows:
        y = doc.y - 34
        doc.c.saveState()
        doc.c.setStrokeColor(BORDER)
        doc.c.rect(MARGIN, y, CONTENT_W, 34, stroke=1, fill=0)
        doc.c.restoreState()
        doc.text(PAGE_W / 2, y + 13, "Нет данных за выбранный период", size=9, color=INK_MUTED, align="center")
        doc.y = y - 24
        return

    for index, row in enumerate(rows):
        values = {
            "№": str(row.number),
            "Ученик": row.student_name,
            "Группа": row.group_name or "—",
            "Программа": row.program or "—",
            "Сумма": som(row.amount),
            "Период": row.period_label,
        }
        wrapped = {
            title: _cell_lines(values[title], _BOLD if title == "Ученик" else _REGULAR, _BODY_SIZE, width)
            for title, width, _ in _COLUMNS if title in _WRAPPED
        }
        lines = max(len(cell) for cell in wrapped.values())
        height = _ROW_H + (lines - 1) * _LINE_H

        if doc.y - height < doc.bottom:
            doc.new_page()
            _draw_table_head(doc)
        y = doc.y - height
        if index % 2:
            doc.c.saveState()
            doc.c.setFillColor(SURFACE_MUTED)
            doc.c.rect(MARGIN, y, CONTENT_W, height, stroke=0, fill=1)
            doc.c.restoreState()

        x = MARGIN
        for title, width, align in _COLUMNS:
            if title in _WRAPPED:
                font = _BOLD if title == "Ученик" else _REGULAR
                _multiline_cell(doc, x, y, width, wrapped[title], font=font, height=height)
            elif title == "Статус":
                _status_pill(doc, x, y, width, row.status, row.status_label, height=height)
            elif title == "Период":
                _cell(doc, x, y, width, values[title], align, size=_PERIOD_SIZE, color=INK, height=height)
            else:
                font = _BOLD if title == "Сумма" else _REGULAR
                color = INK_SECONDARY if title == "№" else INK
                _cell(doc, x, y, width, values[title], align, font=font, color=color, height=height)
            x += width
        doc.hline(y, width=0.5)
        doc.y = y
    doc.y -= 26


# -- totals & signature ------------------------------------------------------

def _draw_totals(doc: _Doc) -> None:
    stats = doc.report.stats
    lines = (
        ("Количество учеников", str(stats.total_students)),
        ("Получили выплаты", str(stats.received_students)),
        ("Ожидают выплаты", str(stats.pending_students)),
        ("Общая сумма", som(stats.total_amount)),
    )
    box_h = 26 + len(lines) * 18 + 8
    doc.ensure_space(box_h + 110)
    y = doc.y - box_h
    _rounded_rect(doc.c, MARGIN, y, CONTENT_W, box_h, 6, fill=BRAND_SOFT, stroke=BRAND, line_width=0.8)
    doc.text(MARGIN + 14, doc.y - 18, "ИТОГО", font=_BOLD, size=11, color=BRAND_DARK)
    line_y = doc.y - 38
    for index, (label, value) in enumerate(lines):
        is_total = index == len(lines) - 1
        font = _BOLD if is_total else _REGULAR
        doc.text(MARGIN + 14, line_y, label, font=font, size=9.5, color=INK)
        doc.text(PAGE_W - MARGIN - 14, line_y, value, font=_BOLD, size=10 if is_total else 9.5, color=INK, align="right")
        if not is_total:
            doc.c.saveState()
            doc.c.setStrokeColor(colors.HexColor("#cfe3d6"))
            doc.c.setLineWidth(0.5)
            doc.c.setDash(1, 2)
            doc.c.line(MARGIN + 14, line_y - 6, PAGE_W - MARGIN - 14, line_y - 6)
            doc.c.restoreState()
        line_y -= 18
    doc.y = y - 28


def _draw_generated(doc: _Doc, generated_at) -> None:
    doc.ensure_space(80)
    left = (
        ("Отчёт сформирован:", generated_at.strftime("%d.%m.%Y %H:%M")),
        ("Период отчёта:", doc.report.filters.range_label),
    )
    for label, value in left:
        doc.text(MARGIN, doc.y, label, font=_BOLD, size=9, color=INK)
        doc.text(MARGIN + 122, doc.y, value, size=9, color=INK)
        doc.y -= 15

    doc.y -= 24
    sig_x = PAGE_W - MARGIN - 200
    doc.hline(doc.y, color=INK_MUTED, width=0.6, x1=sig_x, x2=PAGE_W - MARGIN)
    doc.text(sig_x, doc.y - 11, "Подпись ответственного лица", size=7.5, color=INK_MUTED)
    doc.hline(doc.y, color=INK_MUTED, width=0.6, x1=MARGIN, x2=MARGIN + 150)
    doc.text(MARGIN, doc.y - 11, "Ф. И. О.", size=7.5, color=INK_MUTED)


def render_report_pdf(report: ScholarshipReport, generated_at=None) -> bytes:
    _ensure_fonts()
    generated_at = timezone.localtime(generated_at or timezone.now())
    buffer = io.BytesIO()
    doc = _Doc(buffer, report)
    _draw_header(doc)
    _draw_summary(doc)
    _draw_table(doc)
    _draw_totals(doc)
    _draw_generated(doc, generated_at)
    doc.c.showPage()
    doc.c.save()
    return buffer.getvalue()
