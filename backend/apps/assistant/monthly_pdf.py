"""«Месячный отчёт» of the Assistant as an A4 portrait PDF.

Only a renderer: every number comes from `monthly.monthly_report()` — the
very data the HTML page shows for the same month — nothing is computed
here. Drawn with reportlab's canvas in the family of the existing academy
reports (DejaVu fonts, LMS palette and primitives from
academy.services.monthly_report_pdf).

Tables wrap long names instead of cutting them, continue across pages and
repeat their header; every page has a running header, the footer carries
the generation time and «Страница N из M».
"""
from __future__ import annotations

import io
from decimal import Decimal

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
)

PAGE_W, PAGE_H = A4
MARGIN = 40
CONTENT_W = PAGE_W - 2 * MARGIN
HEADER_H = 34  # running header on pages 2+
FOOTER_H = 30
BOTTOM = MARGIN + FOOTER_H - 14

GOOD = colors.HexColor("#2f8f5b")
WARN = colors.HexColor("#b4790f")
WARN_SOFT = colors.HexColor("#fbf1df")
BAD = colors.HexColor("#c7402e")
BAD_SOFT = colors.HexColor("#fbeae7")

MONTH_SLUGS = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)


def pdf_filename(year: int, month: int) -> str:
    return f"monthly_report_{MONTH_SLUGS[month - 1]}_{year}.pdf"


def _pct(value) -> str:
    return "—" if value is None else f"{value}%"


def _date(value) -> str:
    return value.strftime("%d.%m.%Y")


def _money(value) -> str:
    amount = Decimal(value).quantize(Decimal("1"))
    return f"{amount:,}".replace(",", " ") + " сом"


def _tone(value) -> colors.Color:
    if value is None:
        return INK_MUTED
    return GOOD if value >= 80 else WARN if value >= 60 else BAD


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    """Word wrap that also breaks a single word longer than the column —
    nothing ever runs past its cell or the page edge, nothing is cut."""
    lines: list[str] = []
    for paragraph in str(text).split("\n"):
        current = ""
        for word in paragraph.split():
            while pdfmetrics.stringWidth(word, font, size) > width:
                head = word
                while len(head) > 1 and pdfmetrics.stringWidth(head, font, size) > width:
                    head = head[:-1]
                if current:
                    lines.append(current)
                    current = ""
                lines.append(head)
                word = word[len(head):]
            candidate = f"{current} {word}".strip()
            if pdfmetrics.stringWidth(candidate, font, size) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return [line for line in lines if line] or [""]


class _Canvas(canvas.Canvas):
    """Defers page output so the footer can say «Страница N из M»."""

    def __init__(self, *args, title: str, generated: str, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages: list[dict] = []
        self._report_title = title
        self._generated = generated

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        self._pages.append(dict(self.__dict__))
        total = len(self._pages)
        for state in self._pages:
            self.__dict__.update(state)
            self._chrome(total)
            super().showPage()
        super().save()

    def _chrome(self, total: int) -> None:
        self.saveState()
        if self._pageNumber > 1:
            self.setFont(_BOLD, 8)
            self.setFillColor(BRAND_DARK)
            self.drawString(MARGIN, PAGE_H - 26, "OKURMENKIDS · МЕСЯЧНЫЙ ОТЧЁТ")
            self.setFont(_REGULAR, 8)
            self.setFillColor(INK_SECONDARY)
            self.drawRightString(PAGE_W - MARGIN, PAGE_H - 26, self._report_title)
            self.setStrokeColor(BORDER)
            self.setLineWidth(0.6)
            self.line(MARGIN, PAGE_H - HEADER_H, PAGE_W - MARGIN, PAGE_H - HEADER_H)
        self.setStrokeColor(BORDER)
        self.setLineWidth(0.6)
        self.line(MARGIN, FOOTER_H, PAGE_W - MARGIN, FOOTER_H)
        self.setFont(_REGULAR, 7.5)
        self.setFillColor(INK_MUTED)
        self.drawString(MARGIN, FOOTER_H - 12, f"OkurmenKIDS · Месячный отчёт · {self._report_title} · сформирован {self._generated}")
        self.drawRightString(PAGE_W - MARGIN, FOOTER_H - 12, f"Страница {self._pageNumber} из {total}")
        self.restoreState()


class _Doc:
    def __init__(self, buffer: io.BytesIO, title: str, generated: str):
        self.c = _Canvas(buffer, pagesize=A4, title=title, generated=generated)
        self.c.setTitle(f"Месячный отчёт — {title}")
        self.c.setAuthor("OkurmenKIDS")
        self.y = PAGE_H - MARGIN
        self.section_no = 0

    def new_page(self) -> None:
        self.c.showPage()
        self.y = PAGE_H - HEADER_H - 18

    def ensure(self, needed: float) -> None:
        if self.y - needed < BOTTOM:
            self.new_page()

    def text(self, x, y, text, *, font=_REGULAR, size=9, color=INK, align="left"):
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        if align == "right":
            self.c.drawRightString(x, y, text)
        elif align == "center":
            self.c.drawCentredString(x, y, text)
        else:
            self.c.drawString(x, y, text)

    def paragraph(self, text: str, *, x=MARGIN, width=CONTENT_W, font=_REGULAR, size=8.5, color=INK, leading=None):
        leading = leading or size * 1.4
        for line in _wrap(text, font, size, width):
            self.ensure(leading)
            self.text(x, self.y - size, line, font=font, size=size, color=color)
            self.y -= leading


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

def _section(doc: _Doc, title: str, hint: str | None = None) -> None:
    """Sections are numbered in the order they are drawn — never by hand."""
    doc.section_no += 1
    index = doc.section_no
    doc.ensure(70)  # a title never sits alone at the bottom of a page
    doc.y -= 6
    number = f"{index}."
    doc.text(MARGIN, doc.y - 13, number, font=_BOLD, size=13, color=BRAND)
    offset = pdfmetrics.stringWidth(number, _BOLD, 13) + 6
    doc.text(MARGIN + offset, doc.y - 13, title.upper(), font=_BOLD, size=12, color=INK)
    doc.c.saveState()
    doc.c.setStrokeColor(BRAND)
    doc.c.setLineWidth(1.2)
    doc.c.line(MARGIN, doc.y - 20, MARGIN + CONTENT_W, doc.y - 20)
    doc.c.restoreState()
    doc.y -= 28
    if hint:
        doc.paragraph(hint, size=7.8, color=INK_MUTED)
        doc.y -= 2


def _cards(doc: _Doc, cards: list[tuple[str, str, colors.Color | None]], per_row: int = 4) -> None:
    gap, height = 8, 44
    width = (CONTENT_W - gap * (per_row - 1)) / per_row
    for start in range(0, len(cards), per_row):
        doc.ensure(height + 8)
        top = doc.y
        for i, (value, label, tone) in enumerate(cards[start:start + per_row]):
            x = MARGIN + i * (width + gap)
            _rounded_rect(doc.c, x, top - height, width, height, 6, fill=SURFACE_MUTED, stroke=BORDER, line_width=0.6)
            doc.text(x + 10, top - 20, value, font=_BOLD, size=14, color=tone or INK)
            label_lines = _wrap(label, _REGULAR, 7.4, width - 18)[:2]
            for j, line in enumerate(label_lines):
                doc.text(x + 10, top - 31 - j * 8.5, line, size=7.4, color=INK_SECONDARY)
        doc.y = top - height - gap
    doc.y -= 4


def _headline(doc: _Doc, label: str, value, totals: list[tuple[str, str]]) -> None:
    height = 52
    doc.ensure(height + 8)
    top = doc.y
    _rounded_rect(doc.c, MARGIN, top - height, CONTENT_W, height, 6, fill=WHITE, stroke=BORDER, line_width=0.7)
    doc.text(MARGIN + 12, top - 18, label, font=_BOLD, size=10)
    doc.text(PAGE_W - MARGIN - 12, top - 19, _pct(value), font=_BOLD, size=16, color=_tone(value), align="right")
    _progress_bar(doc.c, MARGIN + 12, top - 30, CONTENT_W - 24, 5, value or 0, _tone(value))
    x = MARGIN + 12
    for name, number in totals:
        chunk = f"{name}: "
        doc.text(x, top - 44, chunk, size=8, color=INK_SECONDARY)
        x += pdfmetrics.stringWidth(chunk, _REGULAR, 8)
        doc.text(x, top - 44, number, font=_BOLD, size=8)
        x += pdfmetrics.stringWidth(number, _BOLD, 8) + 14
    doc.y = top - height - 10


def _table(doc: _Doc, columns: list[tuple[str, float, str]], rows: list[list], *, empty: str,
           header_fill=BRAND_SOFT, header_color=BRAND_DARK) -> None:
    """columns: (title, width fraction, align). Rows wrap; a page break
    repeats the header. A cell is a string or (string, color)."""
    widths = [w * CONTENT_W for _, w, _ in columns]
    pad, size, leading = 5, 7.8, 10
    header_size = 7.2

    # A header word never breaks mid-word: its column's header font shrinks until every word fits.
    header_sizes = []
    for (title, _, _), w in zip(columns, widths):
        size_ = header_size
        while size_ > 5.6 and any(pdfmetrics.stringWidth(word, _BOLD, size_) > w - 2 * pad for word in title.split()):
            size_ -= 0.2
        header_sizes.append(size_)

    def header_height():
        return max(len(_wrap(t, _BOLD, hs, w - 2 * pad)) for (t, _, _), w, hs in zip(columns, widths, header_sizes)) * 9 + 10

    def draw_header(continued: bool = False):
        h = header_height()
        doc.ensure(h + 22)
        top = doc.y
        _rounded_rect(doc.c, MARGIN, top - h, CONTENT_W, h, 4, fill=header_fill)
        x = MARGIN
        for (title, _, align), w, hs in zip(columns, widths, header_sizes):
            for i, line in enumerate(_wrap(title, _BOLD, hs, w - 2 * pad)):
                _cell_text(doc, x, w, top - 12 - i * 9, line, align, _BOLD, hs, header_color)
            x += w
        doc.y = top - h
        if continued:
            doc.text(PAGE_W - MARGIN, top + 4, "продолжение таблицы", size=6.5, color=INK_MUTED, align="right")

    if not rows:
        doc.ensure(24)
        _rounded_rect(doc.c, MARGIN, doc.y - 22, CONTENT_W, 22, 4, fill=SURFACE_MUTED)
        doc.text(MARGIN + 10, doc.y - 14, empty, size=8.3, color=INK_SECONDARY)
        doc.y -= 32
        return

    draw_header()
    for index, row in enumerate(rows):
        cells = [cell if isinstance(cell, tuple) else (str(cell), INK) for cell in row]
        wrapped = [_wrap(text, _REGULAR, size, w - 2 * pad) for (text, _), w in zip(cells, widths)]
        h = max(len(lines) for lines in wrapped) * leading + 8
        if doc.y - h < BOTTOM:
            doc.new_page()
            draw_header(continued=True)
        top = doc.y
        if index % 2:
            doc.c.saveState()
            doc.c.setFillColor(SURFACE_MUTED)
            doc.c.rect(MARGIN, top - h, CONTENT_W, h, stroke=0, fill=1)
            doc.c.restoreState()
        x = MARGIN
        for (_, color), lines, (_, _, align), w in zip(cells, wrapped, columns, widths):
            for i, line in enumerate(lines):
                _cell_text(doc, x, w, top - 12 - i * leading, line, align, _REGULAR, size, color)
            x += w
        doc.c.saveState()
        doc.c.setStrokeColor(BORDER)
        doc.c.setLineWidth(0.4)
        doc.c.line(MARGIN, top - h, MARGIN + CONTENT_W, top - h)
        doc.c.restoreState()
        doc.y = top - h
    doc.y -= 12


def _cell_text(doc, x, width, y, text, align, font, size, color):
    pad = 5
    if align == "right":
        doc.text(x + width - pad, y, text, font=font, size=size, color=color, align="right")
    elif align == "center":
        doc.text(x + width / 2, y, text, font=font, size=size, color=color, align="center")
    else:
        doc.text(x + pad, y, text, font=font, size=size, color=color)


def _pct_cell(value):
    return (_pct(value), _tone(value))


def _bullets(doc: _Doc, title: str, items: list[str], color, soft, empty: str) -> None:
    lines = [_wrap(item, _REGULAR, 8.5, CONTENT_W - 40) for item in items] or [[empty]]
    height = 30 + sum(len(l) for l in lines) * 12 + 6
    if height < PAGE_H / 2:
        doc.ensure(height + 6)
    top = doc.y
    if height < PAGE_H / 2:
        _rounded_rect(doc.c, MARGIN, top - height, CONTENT_W, height, 6, fill=soft)
    doc.text(MARGIN + 12, top - 18, title, font=_BOLD, size=9.5, color=color)
    doc.y = top - 30
    for item_lines in lines:
        for j, line in enumerate(item_lines):
            doc.ensure(12)
            if j == 0 and items:
                doc.text(MARGIN + 14, doc.y - 8.5, "•", font=_BOLD, size=8.5, color=color)
            doc.text(MARGIN + 26, doc.y - 8.5, line, size=8.5, color=INK if items else INK_SECONDARY)
            doc.y -= 12
    doc.y = min(doc.y, top - height) - 10


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _cover(doc: _Doc, report: dict, generated: str) -> None:
    c = doc.c
    band = 132
    c.saveState()
    c.setFillColor(BRAND_DARK)
    c.rect(0, PAGE_H - band, PAGE_W, band, stroke=0, fill=1)
    c.setFillColor(BRAND)
    c.rect(0, PAGE_H - band, PAGE_W, 4, stroke=0, fill=1)
    c.restoreState()
    top = PAGE_H - 44
    doc.text(MARGIN, top, "ОТЧЁТ ПО АКАДЕМИИ · OKURMENKIDS", font=_BOLD, size=9, color=colors.HexColor("#bfe3cd"))
    doc.text(MARGIN, top - 26, "Месячный отчёт", font=_BOLD, size=22, color=WHITE)
    doc.text(MARGIN, top - 48, report["title"], font=_BOLD, size=14, color=colors.HexColor("#d7ecdf"))
    doc.text(MARGIN, top - 72, f"Период: {_date(report['start'])} — {_date(report['end'])}", size=9.5, color=WHITE)
    doc.text(PAGE_W - MARGIN, top - 72, f"Сформирован: {generated}", size=8.5, color=colors.HexColor("#d7ecdf"), align="right")
    doc.y = PAGE_H - band - 18
    note = "Сводный отчёт по студентам и группам: посещаемость, домашние задания, активность, опросы и стипендии."
    if not report["is_complete"]:
        note += f" Месяц ещё идёт — данные по {_date(report['until'])}."
    doc.paragraph(note, size=8.3, color=INK_SECONDARY)
    doc.y -= 4


def _overview(doc: _Doc, r: dict) -> None:
    o = r["overview"]
    _section(doc, "Общая статистика")
    _cards(doc, [
        (str(o["groups_total"]), "Всего групп", None),
        (str(o["groups_active"]), "Активных групп", BRAND_DARK),
        (str(o["students_total"]), "Всего студентов", None),
        (str(o["students_active"]), "Активных студентов", BRAND_DARK),
        (str(o["students_new"]), "Новых студентов за месяц", None),
        (_pct(o["attendance_percent"]), "Средняя посещаемость", _tone(o["attendance_percent"])),
        (_pct(o["homework_percent"]), "Среднее выполнение ДЗ", _tone(o["homework_percent"])),
        (str(o["students_at_risk"]), "Студентов в зоне риска", BAD if o["students_at_risk"] else None),
    ])
    if o["groups_inactive"] or o["students_deactivated"]:
        doc.paragraph(f"Неактивных групп: {o['groups_inactive']} · деактивировано студентов за месяц: {o['students_deactivated']}.",
                      size=7.8, color=INK_SECONDARY)
        doc.y -= 4


def _attendance(doc: _Doc, r: dict) -> None:
    a = r["attendance"]
    _section(doc, "Посещаемость", "Только проведённые занятия; отменённые и будущие не учитываются.")
    _headline(doc, "Общая посещаемость", a["percent"], [
        ("Проведено занятий", str(a["lessons"])), ("Присутствовали", str(a["attended"])),
        ("Пропустили", str(a["absent"])), ("Уважительная", str(a["excused"])), ("Всего отметок", str(a["marked"])),
    ])
    _table(doc, [("Группа", 0.34, "left"), ("Студенты", 0.14, "right"), ("Занятий", 0.14, "right"),
                 ("Пропуски", 0.16, "right"), ("Посещаемость", 0.22, "right")],
           [[g["group"]["name"], g["students"], g["lessons"], g["absent"], _pct_cell(g["percent"])] for g in a["groups"]],
           empty="В этом месяце занятий не было.")


def _students_table(doc: _Doc, rows: list[dict], *, kind: str, empty: str) -> None:
    if kind == "attendance":
        columns = [("Студент", 0.34, "left"), ("Группа", 0.2, "left"), ("Посещаемость", 0.17, "right"),
                   ("Пропуски", 0.14, "right"), ("Подряд", 0.15, "right")]
        data = [[x["name"], (x["group"] or {}).get("name", "—"), (f"{_pct(x['attendance'])} ({x['attended']}/{x['marked']})", _tone(x["attendance"])),
                 x["absent"], (str(x["consecutive_absences"]), BAD if x["consecutive_absences"] >= 3 else INK)] for x in rows]
    else:
        columns = [("Студент", 0.34, "left"), ("Группа", 0.2, "left"), ("Выполнение", 0.17, "right"),
                   ("Не сдано", 0.14, "right"), ("Подряд", 0.15, "right")]
        data = [[x["name"], (x["group"] or {}).get("name", "—"), (f"{_pct(x['homework'])} ({x['homework_done']}/{x['homework_due']})", _tone(x["homework"])),
                 x["homework_missed"], (str(x["consecutive_missed_homework"]), BAD if x["consecutive_missed_homework"] >= 3 else INK)] for x in rows]
    _table(doc, columns, data, empty=empty)


def _homework(doc: _Doc, r: dict) -> None:
    h = r["homework"]
    _section(doc, "Домашние задания", "Выполнение считается по заданиям, чей дедлайн уже прошёл.")
    _headline(doc, "Среднее выполнение ДЗ", h["percent"], [
        ("Выдано заданий", str(h["given"])), ("Выполнено работ", str(h["done"])),
        ("Не выполнено", str(h["not_done"])), ("На проверке", str(h["pending"])),
    ])
    _table(doc, [("Группа", 0.3, "left"), ("ДЗ", 0.1, "right"), ("Выполнено", 0.15, "right"),
                 ("Не выполнено", 0.16, "right"), ("На проверке", 0.14, "right"), ("Выполнение", 0.15, "right")],
           [[g["group"]["name"], g["homeworks"], g["done"], g["not_done"], g["pending"], _pct_cell(g["percent"])] for g in h["groups"]],
           empty="В этом месяце ДЗ не выдавали.")


def _risk(doc: _Doc, r: dict) -> None:
    risk = r["students"]["risk"]
    _section(doc, "Студенты в зоне риска", "Низкая посещаемость и низкое выполнение ДЗ одновременно.")
    if risk:
        doc.ensure(28)
        _rounded_rect(doc.c, MARGIN, doc.y - 22, CONTENT_W, 22, 4, fill=BAD_SOFT)
        doc.text(MARGIN + 10, doc.y - 14.5, f"В зоне риска: {len(risk)}. Нужна связь со студентом и родителями.",
                 font=_BOLD, size=8.5, color=BAD)
        doc.y -= 30
    _table(doc, [("Студент", 0.27, "left"), ("Группа", 0.15, "left"), ("Посещаемость", 0.14, "right"),
                 ("ДЗ", 0.1, "right"), ("Последняя активность", 0.14, "right"), ("Причина", 0.2, "left")],
           [[x["name"], (x["group"] or {}).get("name", "—"), _pct_cell(x["attendance"]), _pct_cell(x["homework"]),
             _date(x["last_activity"]) if x["last_activity"] else "—", (x["reason"], BAD)] for x in risk],
           empty="Студентов в зоне риска нет.", header_fill=BAD_SOFT, header_color=BAD)


def _surveys(doc: _Doc, r: dict) -> None:
    s = r["surveys"]
    _section(doc, "Опросы")
    if not s["surveys"]:
        _table(doc, [("", 1, "left")], [], empty="В этом месяце опросов и ответов не было.")
        return
    _cards(doc, [
        (str(s["surveys"]), "Опросов", None),
        (str(s["participants"]), "Участников (ответов)", None),
        (_pct(s["participation"]), "Участие", None),
        (f"{s['average']} / 5" if s["average"] is not None else "—", "Средняя оценка", None),
    ])
    _table(doc, [("Опрос", 0.34, "left"), ("Группа", 0.17, "left"), ("Участников", 0.17, "right"),
                 ("Средняя оценка", 0.16, "right"), ("Низкие оценки", 0.16, "right")],
           [[f"{x['title']} ({x['audience_display']})", (x["group"] or {}).get("name", "Все"),
             f"{x['participants']}/{x['expected']} · {x['participation']}%" if x["expected"] else str(x["participants"]),
             str(x["average"]) if x["average"] is not None else "—",
             (str(x["low_ratings"]), BAD if x["low_ratings"] else INK)] for x in s["rows"]],
           empty="")
    doc.paragraph("Средняя оценка — по вопросам с числовой шкалой (1–5, 1–10), приведена к 5. Участие — для опросов группы, "
                  "к её активным студентам. Низкая оценка — 40% шкалы и ниже.", size=7.3, color=INK_MUTED)
    if s["quotes"]:
        doc.y -= 6
        doc.ensure(40)
        doc.text(MARGIN, doc.y - 10, "Что говорят студенты", font=_BOLD, size=9.5, color=BRAND_DARK)
        doc.y -= 18
        for q in s["quotes"]:
            lines = _wrap(f"«{q['text']}»" + (f"  ×{q['count']}" if q["count"] > 1 else ""), _REGULAR, 8.5, CONTENT_W - 16)
            doc.ensure(len(lines) * 11.5 + 14)
            start = doc.y
            for line in lines:
                doc.text(MARGIN + 10, doc.y - 8.5, line, size=8.5)
                doc.y -= 11.5
            doc.text(MARGIN + 10, doc.y - 7.5, f"{q['survey']} · {q['question']} · {_date(q['date'])}", size=6.8, color=INK_MUTED)
            doc.y -= 13
            doc.c.saveState()
            doc.c.setStrokeColor(BRAND_SOFT)
            doc.c.setLineWidth(2)
            doc.c.line(MARGIN + 3, start, MARGIN + 3, doc.y + 4)
            doc.c.restoreState()
        if s["texts_total"] > len(s["quotes"]):
            doc.paragraph(f"Показаны повторяющиеся и последние ответы: {len(s['quotes'])} из {s['texts_total']}.", size=7.3, color=INK_MUTED)
    doc.y -= 4


def _scholarships(doc: _Doc, r: dict) -> None:
    s = r["scholarships"]
    _section(doc, "Стипендии")
    _cards(doc, [
        (str(s["awards"]), "Стипендий", None),
        (str(s["recipients"]), "Получателей", None),
        (_money(s["total_amount"]), "Общая сумма", None),
        (f"{s['paid']} · {_money(s['paid_amount'])}" if s["paid"] else "0", "Выдано на руки", None),
    ])
    _table(doc, [("Студент", 0.22, "left"), ("Группа", 0.11, "left"), ("Стипендия", 0.12, "left"),
                 ("Сумма", 0.12, "right"), ("Причина", 0.23, "left"), ("Статус", 0.2, "left")],
           [[x["student"]["name"], x["group"] or "—", x["title"], _money(x["amount"]), x["reason"],
             f"{x['status_display']}, {x['payment_display'].lower()}"] for x in s["rows"]],
           empty="В этом месяце стипендии не начислялись.")


def _activity(doc: _Doc, r: dict) -> None:
    st = r["students"]
    a = st["activity"]
    _section(doc, "Активность студентов", f"Активные студенты начавших обучение групп: {a['analysed']}.")
    _cards(doc, [
        (str(a["normal"]), "Активные (норма)", GOOD),
        (str(a["attention"]), "Требуют внимания", WARN if a["attention"] else None),
        (str(a["low"]), "Низкая активность", BAD if a["low"] else None),
        (str(a["no_activity"]), "Без активности", BAD if a["no_activity"] else None),
        (str(a["risk"]), "В зоне риска", BAD if a["risk"] else None),
        (str(a["not_attending"]), "Не посещают", None),
        (str(a["no_homework"]), "Не сдают ДЗ", None),
        (str(a["no_data"]), "Мало данных для оценки", INK_MUTED),
    ])
    if st["no_activity"]:
        names = ", ".join(f"{x['name']} ({(x['group'] or {}).get('name', '—')})" for x in st["no_activity"])
        doc.paragraph(f"Без активности за месяц (ни одного посещения и сданного ДЗ): {names}.", size=8.3, color=INK_SECONDARY)
        doc.y -= 4


def _summary(doc: _Doc, r: dict) -> None:
    cons = r["conclusions"]
    _section(doc, "Итоги месяца")
    _bullets(doc, "Хорошие показатели", cons["good"], GOOD, BRAND_SOFT, "Нет показателей выше нормы.")
    _bullets(doc, "Требует внимания", cons["attention"], WARN, WARN_SOFT, "Проблем не найдено.")
    _bullets(doc, "Группы, требующие внимания", cons["groups"], WARN, SURFACE_MUTED, "Нет.")
    doc.ensure(40)
    doc.text(MARGIN, doc.y - 10, "Студенты, требующие внимания", font=_BOLD, size=9.5, color=WARN)
    doc.y -= 18
    _table(doc, [("Студент", 0.4, "left"), ("Группа", 0.2, "left"), ("Причина", 0.4, "left")],
           [[x["name"], x["group"] or "—", x["reason"]] for x in cons["students"]], empty="Нет.")
    doc.paragraph("Все показатели рассчитаны по данным учебной системы за выбранный месяц. KPI тренеров — в отчёте Team Lead.",
                  size=7.3, color=INK_MUTED)
    doc.y -= 6


def _bars(doc: _Doc, items: list[tuple[str, int, int | None]], *, color=BRAND) -> None:
    """Horizontal bar chart: (label, count, percent). Label wraps on the left,
    the bar is proportional to the largest count; values printed — readable
    without colour."""
    if not items:
        return
    label_w, value_w = CONTENT_W * 0.42, 64
    bar_w = CONTENT_W - label_w - value_w - 12
    top = max(count for _, count, _ in items) or 1
    for label, count, percent in items:
        lines = _wrap(label, _REGULAR, 8, label_w - 6)
        h = max(len(lines) * 10, 12) + 6
        doc.ensure(h)
        y = doc.y
        for i, line in enumerate(lines):
            doc.text(MARGIN, y - 10 - i * 10, line, size=8)
        _progress_bar(doc.c, MARGIN + label_w, y - 11, bar_w, 7, count / top * 100, color)
        doc.text(PAGE_W - MARGIN, y - 10, f"{count}" + (f" · {percent}%" if percent is not None else ""),
                 font=_BOLD, size=8, align="right")
        doc.y -= h
    doc.y -= 6


def _note(doc: _Doc, text: str, *, color=INK_SECONDARY, fill=SURFACE_MUTED) -> None:
    lines = _wrap(text, _REGULAR, 8.3, CONTENT_W - 20)
    h = len(lines) * 11 + 12
    doc.ensure(h + 6)
    _rounded_rect(doc.c, MARGIN, doc.y - h, CONTENT_W, h, 4, fill=fill)
    for i, line in enumerate(lines):
        doc.text(MARGIN + 10, doc.y - 14 - i * 11, line, size=8.3, color=color)
    doc.y -= h + 8


def _sub(doc: _Doc, title: str) -> None:
    doc.ensure(36)
    doc.text(MARGIN, doc.y - 10, title, font=_BOLD, size=9.5, color=BRAND_DARK)
    doc.y -= 18


def _days(value) -> str:
    return "—" if value is None else f"{value} дн."


def _inactive(doc: _Doc, r: dict) -> None:
    ina = r["inactive"]
    c = ina["counts"]
    short, mid, long = ina["thresholds"]
    _section(doc, "Неактивные студенты и динамика активности",
             f"Студенты, активные на конец месяца. Неактивность — дни без посещения и сданного ДЗ, когда занятия проходили. "
             f"Пороги: {short} / {mid} / {long} дней.")
    _cards(doc, [
        (str(c["active"]), "Активные", GOOD),
        (str(c["inactive"]), f"Неактивные ({mid}+ дней)", WARN if c["inactive"] else None),
        (str(c["no_attendance"]), "Без посещений за месяц", BAD if c["no_attendance"] else None),
        (str(c["no_homework"]), "Не сдают ДЗ", BAD if c["no_homework"] else None),
        (str(c["risk"]), "В зоне риска", BAD if c["risk"] else None),
        (str(c["long_inactive"]), f"Давно не активны ({long}+ дней)", BAD if c["long_inactive"] else None),
    ], per_row=3)
    prev = ina.get("previous")
    if prev:
        doc.paragraph(f"Динамика к прошлому месяцу: неактивны {mid}+ дней — {prev['inactive']} → {c['inactive']}; "
                      f"в зоне риска — {prev['risk']} → {c['risk']}.", size=8.3, color=INK_SECONDARY)
        doc.y -= 2
    _sub(doc, "Дни без активности")
    _bars(doc, [(f"{d}+ дней", c[f"idle_{d}"], None) for d in ina["thresholds"]], color=WARN)
    _table(doc, [("Студент · группа · тренер", 0.21, "left"), ("Последнее посещение / ДЗ", 0.13, "left"),
                 ("Пропуски", 0.095, "right"), ("Посещ. / ДЗ", 0.09, "right"), ("Без активности", 0.11, "right"),
                 ("Статус", 0.13, "left"), ("Рекомендуемое действие", 0.235, "left")],
           [[f"{x['name']}\n{(x['group'] or {}).get('name', '—')}" + (f" · {x['trainer']}" if x["trainer"] else ""),
             f"{_date(x['last_attended']) if x['last_attended'] else '—'}\n{_date(x['last_homework']) if x['last_homework'] else '—'}",
             x["absent"], f"{_pct(x['attendance'])}\n{_pct(x['homework'])}",
             (_days(x["days_inactive"]) + (" (ни разу)" if x["never_active"] and x["days_inactive"] else ""),
              BAD if (x["days_inactive"] or 0) >= long else WARN if (x["days_inactive"] or 0) >= mid else INK),
             f"{x['status']}\n{x['activity_label']}", x["action"]] for x in ina["students"]],
           empty="Неактивных студентов нет.")


def _departures(doc: _Doc, r: dict) -> None:
    d = r["departures"]
    _section(doc, "Деактивированные студенты",
             "Ушедшие за месяц (деактивация). Завершившие обучение и пауза — отдельно, это не уход. "
             "Неактивные, но не деактивированные студенты сюда не входят.")
    if d["filters"]:
        doc.paragraph("Фильтры: " + d["filters_label"], size=7.8, color=INK_SECONDARY)
    _cards(doc, [
        (str(d["total"]), "Ушли за месяц", BAD if d["total"] else None),
        (str(d["returned"]), "Уже вернулись", GOOD if d["returned"] else None),
        (_pct(d["returned_percent"]), "Доля вернувшихся", None),
        (str(d["unknown"]), "Причина не указана", WARN if d["unknown"] else None),
        (str(d["completed"]), "Завершили обучение", None),
        (str(d["paused"]), "Ушли на паузу", None),
    ], per_row=3)
    _table(doc, [("Студент · группа · тренер", 0.21, "left"), ("Дата", 0.115, "left"), ("Причина", 0.2, "left"),
                 ("Оформил", 0.11, "left"), ("Посл. активность", 0.115, "left"), ("Срок обучения", 0.1, "right"),
                 ("Возврат", 0.15, "left")],
           [[f"{x['name']}\n{(x['group'] or {}).get('name', '—')}" + (f" · {x['trainer']}" if x["trainer"] else ""),
             _date(x["date"]),
             (x["reason_label"] + (f"\n{x['comment']}" if x["comment"] else ""), WARN if x["reason"] == "unknown" else INK),
             x["performed_by"] or "—", _date(x["last_activity"]) if x["last_activity"] else "—",
             _days(x["study_days"]), (f"Вернулся {_date(x['returned_on'])}", GOOD) if x["returned_on"] else "—"]
            for x in d["rows"]],
           empty="За месяц никто не ушёл.")


def _reasons(doc: _Doc, r: dict) -> None:
    d = r["departures"]
    _section(doc, "Причины ухода — почему студенты уходят")
    change = d.get("change")
    prev = d.get("previous_total")
    line = f"Ушли за месяц: {d['month_total']}."
    if prev is not None:
        sign = "+" if change and change > 0 else ""
        line += f" В прошлом месяце: {prev} ({sign}{change})."
    if d["filters"]:
        line += f" По фильтрам ({d['filters_label']}): {d['total']}."
    line += f" Вернулись после ухода: {d['returned']} ({_pct(d['returned_percent'])}). Причина не указана: {d['unknown']}."
    doc.paragraph(line, size=8.5)
    doc.y -= 4
    if not d["total"]:
        _note(doc, "За месяц уходов нет — распределять нечего.")
        return
    _sub(doc, "По причинам")
    _bars(doc, [(x["label"], x["count"], x["percent"]) for x in d["by_reason"]], color=BAD)
    _sub(doc, "По группам")
    _table(doc, [("Группа", 0.6, "left"), ("Ушли", 0.2, "right"), ("Доля", 0.2, "right")],
           [[x["label"], x["count"], _pct(x["percent"])] for x in d["by_group"]], empty="—")
    _sub(doc, "По тренерам групп")
    _table(doc, [("Тренер", 0.6, "left"), ("Ушли", 0.2, "right"), ("Доля", 0.2, "right")],
           [[x["label"], x["count"], _pct(x["percent"])] for x in d["by_trainer"]], empty="—")
    doc.paragraph("Тренер — тот, кто вёл занятия группы в этот период; у группы с несколькими тренерами уход учитывается у каждого.",
                  size=7.3, color=INK_MUTED)


def _finance(doc: _Doc, r: dict) -> None:
    f = r["finance"]
    _section(doc, "Финансовая аналитика")
    if not f["allowed"]:
        _note(doc, f["note"])
        return
    _note(doc, f["note"] + " Суммы не оцениваются и не придумываются.", color=WARN, fill=WARN_SOFT)
    _table(doc, [("Показатель", 0.7, "left"), ("Значение", 0.3, "right")],
           [[m["label"], str(m["value"]) if m["value"] is not None else ("Недостаточно данных", INK_MUTED)]
            for m in f["metrics"]], empty="—")
    _sub(doc, "Каких данных не хватает")
    for item in f["missing"]:
        doc.paragraph(f"•  {item}", size=8.3)
    doc.y -= 4


def _comparison(doc: _Doc, r: dict) -> None:
    comp = r["comparison"]
    _section(doc, "Сравнение с предыдущим месяцем", f"{comp['previous_title']} → {r['title']}.")
    arrows = {"better": ("▲ лучше", GOOD), "worse": ("▼ хуже", BAD), "same": ("без изменений", INK_MUTED)}

    def fmt(v):
        return "—" if v is None else f"{v:g}" if isinstance(v, float) else str(v)

    _table(doc, [("Показатель", 0.4, "left"), (comp["previous_title"], 0.17, "right"), (r["title"], 0.17, "right"),
                 ("Изменение", 0.26, "right")],
           [[x["label"], fmt(x["previous"]), fmt(x["current"]),
             (f"{'+' if (x['delta'] or 0) > 0 else ''}{fmt(x['delta'])} · {arrows[x['trend']][0]}", arrows[x["trend"]][1])
             if x["trend"] else ("нет данных", INK_MUTED)] for x in comp["rows"]],
           empty="—")


def _recommendations(doc: _Doc, r: dict) -> None:
    _section(doc, "Рекомендации по удержанию студентов", "Только по данным этого отчёта.")
    _bullets(doc, "Что сделать", r["recommendations"], BRAND_DARK, BRAND_SOFT, "Данных для рекомендаций недостаточно.")


def _management(doc: _Doc, r: dict) -> None:
    m = r["summary"]
    _sub(doc, "Управленческое резюме")
    _bullets(doc, "Что улучшилось", m["improved"], GOOD, BRAND_SOFT, "Нет показателей, которые улучшились.")
    _bullets(doc, "Что ухудшилось", m["worsened"], BAD, BAD_SOFT, "Нет показателей, которые ухудшились.")
    _bullets(doc, "Группы, требующие внимания", m["groups"], WARN, SURFACE_MUTED, "Нет.")
    _bullets(doc, "Частые причины ухода", m["top_reasons"], WARN, SURFACE_MUTED, "Уходов за месяц не было.")
    _note(doc, f"Потенциально нуждаются в контакте: {m['contacts']} студ.", color=INK, fill=WARN_SOFT)
    _bullets(doc, "Действия на следующий месяц", m["next_month"], BRAND_DARK, BRAND_SOFT, "Нет данных для рекомендаций.")


def build_monthly_pdf(report: dict) -> bytes:
    _ensure_fonts()
    buffer = io.BytesIO()
    generated = timezone.localtime(report["generated_at"]).strftime("%d.%m.%Y %H:%M")
    doc = _Doc(buffer, report["title"], generated)
    st = report["students"]
    _cover(doc, report, generated)
    _overview(doc, report)
    _attendance(doc, report)
    _section(doc, "Студенты с плохой посещаемостью")
    _students_table(doc, st["attendance_attention"], kind="attendance", empty="Студентов с низкой посещаемостью нет.")
    _homework(doc, report)
    _section(doc, "Студенты, не выполняющие ДЗ")
    _students_table(doc, st["homework_attention"], kind="homework", empty="Студентов, которые не сдают ДЗ, нет.")
    _risk(doc, report)
    _surveys(doc, report)
    _scholarships(doc, report)
    _activity(doc, report)
    _inactive(doc, report)
    _departures(doc, report)
    _reasons(doc, report)
    _finance(doc, report)
    _comparison(doc, report)
    _recommendations(doc, report)
    _summary(doc, report)
    _management(doc, report)
    doc.c.save()
    return buffer.getvalue()
