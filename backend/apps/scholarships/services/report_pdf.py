"""«Отчёт по стипендиям» as an official A4 PDF document.

Built directly with reportlab's canvas, the same way the academy reports
are (apps/academy/services/monthly_report_pdf.py) — same bundled DejaVu
fonts (reportlab's built-in fonts have no Cyrillic), same palette, so all
Okurmen Kids PDFs look like one family.

It renders the very `ScholarshipReport` object the admin page renders
(services.report.build_report for the same period and filters), in the
same order: period → participating groups → groups table → summary →
students → totals. The page and the PDF cannot disagree. Every number
follows the filters (`rows_totals`), like the KPIs on the page.

Only vector primitives are used for decoration (lines, rounded rects,
dots) — no emoji, no images.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
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

from .report import NO_GROUP, PaymentStatus, ScholarshipReport

PAGE_W, PAGE_H = A4
MARGIN = 40
CONTENT_W = PAGE_W - 2 * MARGIN
FOOTER_H = 34  # room kept free at the bottom of every page for the footer

WARNING = colors.HexColor("#b4790f")
WARNING_SOFT = colors.HexColor("#fbf1df")
BRAND_LINE = colors.HexColor("#cfe3d6")

_STATUS_STYLE = {
    PaymentStatus.PAID: (BRAND, BRAND_SOFT),
    PaymentStatus.UNPAID: (WARNING, WARNING_SOFT),
    PaymentStatus.NOT_AWARDED: (INK_MUTED, SURFACE_MUTED),
}

_ROW_H = 20
_HEAD_H = 22
_LINE_H = 9.5
_CELL_PAD = 5
_BODY_SIZE = 8.3
_MAX_LINES = 2

_NBSP = " "


def som(value) -> str:
    if value is None:
        return "—"
    amount = Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{amount:,}".replace(",", _NBSP) + f"{_NBSP}сом"


# ---------------------------------------------------------------------------
# Canvas & cursor
# ---------------------------------------------------------------------------

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
            footer_left=f"Okurmen Kids · Отчёт по стипендиям · {report.range_label}",
        )
        self.c.setTitle(f"Отчёт по стипендиям {report.range_label}")
        self.c.setAuthor("Okurmen Kids")
        self.y = PAGE_H - MARGIN

    @property
    def bottom(self) -> float:
        return MARGIN + FOOTER_H

    def new_page(self) -> None:
        self.c.showPage()
        self.y = PAGE_H - MARGIN
        # Running header on continuation pages: the period is always visible.
        self.text(MARGIN, self.y - 8, "ОТЧЁТ ПО СТИПЕНДИЯМ", font=_BOLD, size=8.5, color=BRAND_DARK)
        self.text(
            PAGE_W - MARGIN, self.y - 8, f"Стипендиальный период: {self.report.range_label}",
            size=8.5, color=INK_SECONDARY, align="right",
        )
        self.y -= 16
        self.hline(self.y)
        self.y -= 14

    def ensure_space(self, needed: float) -> None:
        if self.y - needed < self.bottom:
            self.new_page()

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

    def fill_rect(self, x, y, w, h, color):
        self.c.saveState()
        self.c.setFillColor(color)
        self.c.rect(x, y, w, h, stroke=0, fill=1)
        self.c.restoreState()


def _section_title(doc: _Doc, title: str, needed: float = 0) -> None:
    doc.ensure_space(30 + needed)
    doc.text(MARGIN, doc.y, title, font=_BOLD, size=11, color=INK)
    doc.y -= 8
    doc.hline(doc.y, color=BRAND, width=1.2, x2=MARGIN + 28)
    doc.y -= 14


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _width(text: str, font, size) -> float:
    return pdfmetrics.stringWidth(text, font, size)


def _split_long(text: str, font, size, max_width) -> list[str]:
    """A single word wider than the column (a group code like
    «PRO-GROUP-2026-01») is broken after a hyphen when possible, else at
    the last character that fits."""
    parts = []
    while _width(text, font, size) > max_width and len(text) > 1:
        cut = len(text)
        while cut > 1 and _width(text[:cut], font, size) > max_width:
            cut -= 1
        hyphen = text.rfind("-", 0, cut)
        if hyphen > 0:
            cut = hyphen + 1
        parts.append(text[:cut])
        text = text[cut:]
    return parts + [text]


def _lines(value: str, font, size, max_width, max_lines=_MAX_LINES) -> list[str]:
    lines = []
    for line in _wrap_text(value, font, size, max_width) or [value]:
        lines.extend(_split_long(line, font, size, max_width))
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1] + [" ".join(lines[max_lines - 1:])]
    return [_truncate_text(line, font, size, max_width) for line in lines]


# ---------------------------------------------------------------------------
# Generic table: header repeated on every page, rows wrap to two lines
# ---------------------------------------------------------------------------

@dataclass
class _Col:
    title: str
    width: float
    align: str = "left"
    font: str = _REGULAR
    wrap: bool = False
    color: object = INK
    size: float = _BODY_SIZE


def _fit(columns: list[_Col]) -> list[_Col]:
    """Stretch the wrapping columns so the table spans CONTENT_W."""
    spare = CONTENT_W - sum(c.width for c in columns)
    flexible = [c for c in columns if c.wrap] or columns
    for col in flexible:
        col.width += spare / len(flexible)
    return columns


def _draw_head(doc: _Doc, columns: list[_Col]) -> None:
    y = doc.y - _HEAD_H
    doc.fill_rect(MARGIN, y, CONTENT_W, _HEAD_H, BRAND)
    x = MARGIN
    for col in columns:
        _single(doc, x, y, col.width, col.title, col.align, _BOLD, 7.8, WHITE, _HEAD_H)
        x += col.width
    doc.y = y


def _single(doc, x, y, width, value, align, font, size, color, height):
    value = _truncate_text(value, font, size, width - 2 * _CELL_PAD)
    baseline = y + (height - size) / 2 + 1.5
    if align == "right":
        doc.text(x + width - _CELL_PAD, baseline, value, font=font, size=size, color=color, align="right")
    elif align == "center":
        doc.text(x + width / 2, baseline, value, font=font, size=size, color=color, align="center")
    else:
        doc.text(x + _CELL_PAD, baseline, value, font=font, size=size, color=color)


def _status_pill(doc: _Doc, x, y, width, status: str, height) -> None:
    color, soft = _STATUS_STYLE[status]
    label = PaymentStatus.LABELS[status]
    size = 7.5
    pill_w = min(width - 2 * _CELL_PAD, _width(label, _BOLD, size) + 18)
    pill_h = 12
    px, py = x + _CELL_PAD, y + (height - pill_h) / 2
    _rounded_rect(doc.c, px, py, pill_w, pill_h, pill_h / 2, fill=soft)
    doc.c.saveState()
    doc.c.setFillColor(color)
    doc.c.circle(px + 6.5, py + pill_h / 2, 2, stroke=0, fill=1)
    doc.c.restoreState()
    doc.text(px + 11.5, py + 3.3, label, font=_BOLD, size=size, color=color)


def _draw_table(doc: _Doc, columns: list[_Col], rows: list[list], *, footer: list | None = None, empty: str = "") -> None:
    """`rows` hold one value per column: a string, or ("status", key)."""
    doc.ensure_space(_HEAD_H + _ROW_H * max(1, min(len(rows), 3)))
    _draw_head(doc, columns)

    if not rows:
        y = doc.y - 34
        doc.c.saveState()
        doc.c.setStrokeColor(BORDER)
        doc.c.rect(MARGIN, y, CONTENT_W, 34, stroke=1, fill=0)
        doc.c.restoreState()
        doc.text(PAGE_W / 2, y + 13, empty, size=9, color=INK_MUTED, align="center")
        doc.y = y - 22
        return

    for index, values in enumerate(rows):
        wrapped = {
            i: _lines(values[i], col.font, col.size, col.width - 2 * _CELL_PAD)
            for i, col in enumerate(columns) if col.wrap
        }
        lines = max((len(v) for v in wrapped.values()), default=1)
        height = _ROW_H + (lines - 1) * _LINE_H
        if doc.y - height < doc.bottom:
            doc.new_page()
            _draw_head(doc, columns)
        y = doc.y - height
        if index % 2:
            doc.fill_rect(MARGIN, y, CONTENT_W, height, SURFACE_MUTED)
        x = MARGIN
        for i, col in enumerate(columns):
            value = values[i]
            if isinstance(value, tuple) and value[0] == "status":
                _status_pill(doc, x, y, col.width, value[1], height)
            elif col.wrap:
                block = col.size + (len(wrapped[i]) - 1) * _LINE_H
                baseline = y + (height + block) / 2 - col.size + 1.5
                for line in wrapped[i]:
                    doc.text(x + _CELL_PAD, baseline, line, font=col.font, size=col.size, color=col.color)
                    baseline -= _LINE_H
            else:
                _single(doc, x, y, col.width, value, col.align, col.font, col.size, col.color, height)
            x += col.width
        doc.hline(y, width=0.5)
        doc.y = y

    if footer:
        if doc.y - _ROW_H < doc.bottom:
            doc.new_page()
        y = doc.y - _ROW_H
        doc.fill_rect(MARGIN, y, CONTENT_W, _ROW_H, BRAND_SOFT)
        doc.hline(doc.y, color=BRAND, width=0.8)
        x = MARGIN
        for col, value in zip(columns, footer):
            _single(doc, x, y, col.width, value, col.align, _BOLD, _BODY_SIZE, INK, _ROW_H)
            x += col.width
        doc.y = y
    doc.y -= 24


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _draw_header(doc: _Doc) -> None:
    top = doc.y
    doc.fill_rect(MARGIN, top - 4, 4, 18, BRAND)
    doc.text(MARGIN + 12, top, "Okurmen Kids", font=_BOLD, size=12, color=BRAND)
    doc.text(PAGE_W - MARGIN, top, "Стипендиальная программа", size=8.5, color=INK_MUTED, align="right")
    doc.y = top - 20
    doc.hline(doc.y)
    doc.y -= 34
    doc.text(MARGIN, doc.y, "ОТЧЁТ ПО СТИПЕНДИЯМ", font=_BOLD, size=19, color=INK)
    doc.y -= 20
    doc.text(MARGIN, doc.y, "Okurmen Kids", font=_REGULAR, size=10.5, color=INK_SECONDARY)
    doc.y -= 22


def _draw_period_box(doc: _Doc) -> None:
    """The answer to «which period, which groups» — first thing on page 1."""
    report = doc.report
    period = report.period
    label_w = 150
    value_w = CONTENT_W - 28 - label_w
    groups = ", ".join(report.group_names) or "Период ещё не рассчитан"
    if report.scope_all:
        groups += " (вся академия — группы для периода не выбраны)"
    programs = ", ".join(report.programs) or "—"
    status = "Завершён (утверждён)" if not period.is_draft else "В процессе (не утверждён)"
    rows = [
        ("Стипендиальный период", [report.range_label], _BOLD, 12),
        ("Участвующие группы", _lines(groups, _BOLD, 10, value_w, max_lines=6), _BOLD, 10),
        ("Программа", _lines(programs, _REGULAR, 9.5, value_w, max_lines=3), _REGULAR, 9.5),
        ("Название / статус", [f"{period.title} · {status}"], _REGULAR, 9),
        ("Дата начисления", [period.evaluation_date.strftime("%d.%m.%Y")], _REGULAR, 9),
    ]
    filters = report.filters
    applied = [
        text for text in (
            f"группа {filters.group}" if filters.group else "",
            f"программа {filters.program}" if filters.program else "",
            f"ученик «{filters.student}»" if filters.student else "",
            f"статус «{filters.status_label}»" if filters.status else "",
            f"способ «{filters.method_label}»" if filters.method else "",
        ) if text
    ]
    if applied:
        rows.append(("Фильтр", _lines(", ".join(applied), _REGULAR, 9, value_w, 3), _REGULAR, 9))

    heights = [max(16, 6 + len(lines) * (size + 3.5)) for _, lines, _, size in rows]
    box_h = sum(heights) + 20
    doc.ensure_space(box_h + 10)
    y = doc.y - box_h
    _rounded_rect(doc.c, MARGIN, y, CONTENT_W, box_h, 6, fill=BRAND_SOFT, stroke=BRAND, line_width=0.9)
    doc.fill_rect(MARGIN, y + 6, 4, box_h - 12, BRAND)
    cursor = doc.y - 10
    for (label, lines, font, size), height in zip(rows, heights):
        line_y = cursor - size - 2
        doc.text(MARGIN + 16, line_y + (size - 8.5) / 2, label, size=8.5, color=INK_SECONDARY)
        for line in lines:
            doc.text(MARGIN + 14 + label_w, line_y, line, font=font, size=size, color=INK)
            line_y -= size + 3.5
        cursor -= height
    doc.y = y - 24


def _draw_groups(doc: _Doc) -> None:
    report = doc.report
    if not report.groups:
        return
    columns = _fit([
        _Col("Группа", 84, font=_BOLD, wrap=True),
        _Col("Программа", 76, wrap=True),
        _Col("Начислений", 62, "right"),
        _Col("Выдано", 46, "right"),
        _Col("Не выдано", 60, "right"),
        _Col("Начислено", 72, "right", font=_BOLD),
        _Col("Выплачено", 72, "right"),
    ])
    rows = []
    for g in report.groups:
        t = g.totals
        rows.append([
            g.name, g.program_label, str(t.awards), str(t.paid), str(t.unpaid), som(t.amount), som(t.paid_amount),
        ])
    t = report.rows_totals
    footer = ["Всего", "", str(t.awards), str(t.paid), str(t.unpaid), som(t.amount), som(t.paid_amount)]
    _section_title(doc, "Группы", needed=_HEAD_H + _ROW_H)
    _draw_table(doc, columns, rows, footer=footer)


def _draw_summary(doc: _Doc) -> None:
    t = doc.report.rows_totals
    cards = (
        ("Начислений", str(t.awards), BRAND_DARK),
        ("Выдано", str(t.paid), BRAND),
        ("Не выдано", str(t.unpaid), WARNING),
        ("Всего начислено", som(t.amount), BRAND_DARK),
        ("Выплачено", som(t.paid_amount), BRAND),
        ("Остаток", som(t.remaining), WARNING if t.remaining else INK_SECONDARY),
    )
    _section_title(doc, "Краткое резюме", needed=56)
    gap = 7
    card_w = (CONTENT_W - gap * (len(cards) - 1)) / len(cards)
    card_h = 54
    y = doc.y - card_h
    for index, (label, value, accent) in enumerate(cards):
        x = MARGIN + index * (card_w + gap)
        _rounded_rect(doc.c, x, y, card_w, card_h, 6, fill=WHITE, stroke=BORDER, line_width=0.75)
        doc.fill_rect(x, y + 10, 2.5, card_h - 20, accent)
        label_y = y + card_h - 14
        for line in _lines(label, _REGULAR, 7.2, card_w - 14):
            doc.text(x + 9, label_y, line, size=7.2, color=INK_SECONDARY)
            label_y -= 8.5
        size = 13
        while size > 8 and _width(value, _BOLD, size) > card_w - 15:
            size -= 0.5
        doc.text(x + 9, y + 12, value, font=_BOLD, size=size, color=INK)
    doc.y = y - 26


def _draw_students(doc: _Doc) -> None:
    report = doc.report
    columns = _fit([
        _Col("№", 22, "center", color=INK_SECONDARY),
        _Col("Ученик", 104, font=_BOLD, wrap=True),
        _Col("Группа", 72, wrap=True),
        _Col("Сумма", 68, "right", font=_BOLD),
        _Col("Статус", 66),
        _Col("Дата", 62, "center"),
        _Col("Способ", 74, wrap=True),
    ])
    rows = [
        [
            str(row.number), row.student_name, row.group_name or NO_GROUP, som(row.amount),
            ("status", row.status),
            timezone.localtime(row.paid_at).strftime("%d.%m.%Y") if row.paid_at else "—",
            row.method_label or "—",
        ]
        for row in report.rows
    ]
    t = report.rows_totals
    footer = ["", "Итого", f"учеников: {t.students}", som(t.amount), f"выдано: {t.paid}", "", ""]
    title = "Начисления"
    if report.filters.group:
        title += f" · группа {report.filters.group}"
    _section_title(doc, title, needed=_HEAD_H + _ROW_H)
    _draw_table(doc, columns, rows, footer=footer if rows else None, empty="Нет начислений")


def _draw_totals(doc: _Doc) -> None:
    t = doc.report.rows_totals
    lines = [
        ("Количество учеников", str(t.students)),
        ("Выдано", str(t.paid)),
        ("Не выдано", str(t.unpaid)),
        ("Всего начислено", som(t.amount)),
        ("Всего выплачено", som(t.paid_amount)),
        ("Остаток к выплате", som(t.remaining)),
    ]
    box_h = 26 + len(lines) * 18 + 8
    doc.ensure_space(box_h + 110)
    y = doc.y - box_h
    _rounded_rect(doc.c, MARGIN, y, CONTENT_W, box_h, 6, fill=BRAND_SOFT, stroke=BRAND, line_width=0.8)
    doc.text(MARGIN + 14, doc.y - 18, f"ИТОГО ЗА ПЕРИОД {doc.report.range_label}", font=_BOLD, size=10.5, color=BRAND_DARK)
    line_y = doc.y - 38
    for index, (label, value) in enumerate(lines):
        is_total = index == len(lines) - 1
        doc.text(MARGIN + 14, line_y, label, font=_BOLD if is_total else _REGULAR, size=9.5, color=INK)
        doc.text(PAGE_W - MARGIN - 14, line_y, value, font=_BOLD, size=10 if is_total else 9.5, color=INK, align="right")
        if not is_total:
            doc.c.saveState()
            doc.c.setStrokeColor(BRAND_LINE)
            doc.c.setLineWidth(0.5)
            doc.c.setDash(1, 2)
            doc.c.line(MARGIN + 14, line_y - 6, PAGE_W - MARGIN - 14, line_y - 6)
            doc.c.restoreState()
        line_y -= 18
    doc.y = y - 28


def _draw_generated(doc: _Doc, generated_at) -> None:
    doc.ensure_space(80)
    for label, value in (
        ("Отчёт сформирован:", generated_at.strftime("%d.%m.%Y %H:%M")),
        ("Период отчёта:", doc.report.range_label),
    ):
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
    _draw_period_box(doc)
    _draw_groups(doc)
    _draw_summary(doc)
    _draw_students(doc)
    _draw_totals(doc)
    _draw_generated(doc, generated_at)
    doc.c.showPage()
    doc.c.save()
    return buffer.getvalue()
