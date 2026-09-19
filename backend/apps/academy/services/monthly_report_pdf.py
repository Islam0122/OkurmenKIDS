"""Renders a `MonthlyTeacherReport` as a real, print-friendly PDF — built
directly with reportlab's canvas (never a screenshot/html2canvas — spec:
"Использовать backend PDF generation"), reusing exactly the figures
`monthly_report.compute_monthly_stats` already computes for the API/UI, so
the PDF can never show a number the on-screen report doesn't.

DejaVu Sans is bundled under `services/fonts/` and registered by file path
(not relied on being installed system-wide) purely because reportlab's
built-in fonts have no Cyrillic glyphs.
"""
from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .monthly_report import compute_monthly_stats

_FONTS_DIR = Path(__file__).resolve().parent / "fonts"
_REGULAR = "OK-DejaVuSans"
_BOLD = "OK-DejaVuSans-Bold"

_fonts_registered = False


def _ensure_fonts() -> None:
    global _fonts_registered
    if _fonts_registered:
        return
    pdfmetrics.registerFont(TTFont(_REGULAR, str(_FONTS_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont(_BOLD, str(_FONTS_DIR / "DejaVuSans-Bold.ttf")))
    _fonts_registered = True


BRAND = colors.HexColor("#2f8f5b")
BRAND_DARK = colors.HexColor("#1f5f3c")
BRAND_SOFT = colors.HexColor("#e7f3ec")
INK = colors.HexColor("#202622")
INK_SECONDARY = colors.HexColor("#68736c")
INK_MUTED = colors.HexColor("#89938d")
BORDER = colors.HexColor("#e1e7e2")
SURFACE_MUTED = colors.HexColor("#f7f9f7")
WHITE = colors.white

MONTH_NAMES_RU = [
    "", "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

PAGE_W, PAGE_H = A4
MARGIN = 42
CONTENT_W = PAGE_W - 2 * MARGIN


def _wrap_text(text: str, font: str, size: float, max_width: float) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if pdfmetrics.stringWidth(candidate, font, size) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _rounded_rect(c: canvas.Canvas, x, y, w, h, r, fill=None, stroke=None, line_width=1):
    c.saveState()
    if fill is not None:
        c.setFillColor(fill)
    if stroke is not None:
        c.setStrokeColor(stroke)
        c.setLineWidth(line_width)
    c.roundRect(x, y, w, h, r, stroke=1 if stroke is not None else 0, fill=1 if fill is not None else 0)
    c.restoreState()


def _progress_bar(c: canvas.Canvas, x, y, w, h, percent: float, color):
    percent = max(0.0, min(100.0, percent))
    _rounded_rect(c, x, y, w, h, h / 2, fill=SURFACE_MUTED)
    fill_w = w * percent / 100
    if fill_w > 0:
        _rounded_rect(c, x, y, max(fill_w, h), h, h / 2, fill=color)


class _Doc:
    """Thin cursor-based wrapper around `canvas.Canvas` — a report is a
    single linear flow of sections, so a simple "draw at cursor, move cursor
    down, start a new page if we run out of room" helper is all this needs
    (no reason to pull in platypus's full flowable/frame machinery)."""

    def __init__(self, buffer: io.BytesIO):
        self.c = canvas.Canvas(buffer, pagesize=A4)
        self.y = PAGE_H - MARGIN

    def ensure_space(self, needed: float) -> None:
        if self.y - needed < MARGIN:
            self.c.showPage()
            self.y = PAGE_H - MARGIN

    def text(self, x, y, text, font=_REGULAR, size=10, color=INK, align="left"):
        self.c.setFont(font, size)
        self.c.setFillColor(color)
        if align == "right":
            self.c.drawRightString(x, y, text)
        elif align == "center":
            self.c.drawCentredString(x, y, text)
        else:
            self.c.drawString(x, y, text)

    def hline(self, y, color=BORDER, width=0.75):
        self.c.saveState()
        self.c.setStrokeColor(color)
        self.c.setLineWidth(width)
        self.c.line(MARGIN, y, PAGE_W - MARGIN, y)
        self.c.restoreState()


def _draw_header(doc: _Doc, report) -> None:
    teacher = report.teacher
    user = teacher.user
    full_name = (user.get_full_name() or user.username).upper()
    position = teacher.position or "Тренер"
    month_label = f"{MONTH_NAMES_RU[report.month]} {report.year}"

    doc.ensure_space(112)
    top = doc.y

    doc.text(MARGIN, top, "OKURMENKIDS", font=_BOLD, size=13, color=BRAND)
    doc.text(MARGIN, top - 16, "Ежемесячный отчёт тренера", font=_REGULAR, size=9, color=INK_MUTED)

    photo_size = 56
    photo_x = MARGIN
    photo_y = top - 30 - photo_size

    image_drawn = False
    if teacher.image:
        try:
            reader = ImageReader(teacher.image.path)
            doc.c.saveState()
            path = doc.c.beginPath()
            path.circle(photo_x + photo_size / 2, photo_y + photo_size / 2, photo_size / 2)
            doc.c.clipPath(path, stroke=0, fill=0)
            doc.c.drawImage(
                reader, photo_x, photo_y, width=photo_size, height=photo_size,
                preserveAspectRatio=True, anchor="c", mask="auto",
            )
            doc.c.restoreState()
            image_drawn = True
        except Exception:
            image_drawn = False

    if not image_drawn:
        doc.c.saveState()
        doc.c.setFillColor(BRAND_SOFT)
        doc.c.circle(photo_x + photo_size / 2, photo_y + photo_size / 2, photo_size / 2, stroke=0, fill=1)
        initials = "".join(part[0].upper() for part in [user.first_name, user.last_name] if part)[:2] or "?"
        doc.c.setFillColor(BRAND_DARK)
        doc.c.setFont(_BOLD, 18)
        doc.c.drawCentredString(photo_x + photo_size / 2, photo_y + photo_size / 2 - 6, initials)
        doc.c.restoreState()

    text_x = photo_x + photo_size + 14
    doc.text(text_x, photo_y + photo_size - 14, full_name, font=_BOLD, size=15, color=INK)
    doc.text(text_x, photo_y + photo_size - 30, position, font=_REGULAR, size=10, color=INK_SECONDARY)
    doc.text(text_x, photo_y + photo_size - 46, month_label, font=_BOLD, size=10, color=BRAND)

    doc.y = photo_y - 18
    doc.hline(doc.y)
    doc.y -= 20


def _draw_top_stats(doc: _Doc, stats: dict) -> None:
    items = [
        (str(stats["lessons_completed"]), "Занятия"),
        (str(stats["students_count"]), "Студенты"),
        (str(stats["groups_count"]), "Группы"),
    ]
    doc.ensure_space(46)
    col_w = CONTENT_W / len(items)
    top = doc.y
    for index, (value, label) in enumerate(items):
        cx = MARGIN + col_w * index + col_w / 2
        doc.text(cx, top, value, font=_BOLD, size=18, color=INK, align="center")
        doc.text(cx, top - 15, label, font=_REGULAR, size=9, color=INK_SECONDARY, align="center")
    doc.y = top - 34
    doc.hline(doc.y)
    doc.y -= 20


def _draw_kpi_cards(doc: _Doc, stats: dict) -> None:
    cards = [
        (str(stats["lessons_completed"]), "Занятия"),
        (str(stats["students_count"]), "Студенты"),
        (str(stats["groups_count"]), "Группы"),
        (f"{stats['attendance']['rate']:g}%", "Attendance"),
        (f"{stats['homework']['submission_rate']:g}%", "Homework"),
        (f"{stats['kpi']['total']:g}%", "KPI"),
    ]
    cols = 3
    gap = 10
    card_w = (CONTENT_W - gap * (cols - 1)) / cols
    card_h = 52
    rows = (len(cards) + cols - 1) // cols
    doc.ensure_space(rows * (card_h + gap))

    for index, (value, label) in enumerate(cards):
        row, col = divmod(index, cols)
        x = MARGIN + col * (card_w + gap)
        y = doc.y - row * (card_h + gap) - card_h
        _rounded_rect(doc.c, x, y, card_w, card_h, 8, fill=WHITE, stroke=BORDER, line_width=0.75)
        doc.text(x + 12, y + card_h - 22, value, font=_BOLD, size=15, color=INK)
        doc.text(x + 12, y + 12, label, font=_REGULAR, size=8.5, color=INK_SECONDARY)

    doc.y -= rows * (card_h + gap) - gap


_TITLE_HEIGHT = 28


def _section_title(doc: _Doc, title: str) -> None:
    """Draws the heading only — the caller must `ensure_space` for the
    heading *plus* its body beforehand (see `_TITLE_HEIGHT`), so a section's
    title never gets orphaned at the bottom of a page while its content
    flows onto the next one."""
    doc.y -= 10
    doc.text(MARGIN, doc.y, title, font=_BOLD, size=11.5, color=INK)
    doc.y -= 18


def _draw_work_rows(doc: _Doc, stats: dict) -> None:
    rows = [
        ("Проведено занятий", str(stats["lessons_completed"])),
        ("Выдано Homework", str(stats["homework"]["assigned"])),
        ("Проверено Homework", str(stats["homework"]["checked"])),
        ("Работа со студентами", str(stats["students_count"])),
    ]
    row_h = 22
    doc.ensure_space(_TITLE_HEIGHT + row_h * len(rows) + 10)
    _section_title(doc, "Работа тренера")
    for label, value in rows:
        doc.text(MARGIN, doc.y - 15, label, font=_REGULAR, size=10, color=INK_SECONDARY)
        doc.text(PAGE_W - MARGIN, doc.y - 15, value, font=_BOLD, size=10.5, color=INK, align="right")
        doc.y -= row_h
        doc.hline(doc.y + row_h - row_h + 4, color=BORDER, width=0.5)


def _draw_groups_table(doc: _Doc, stats: dict) -> None:
    groups = stats["groups"]
    if not groups:
        doc.ensure_space(_TITLE_HEIGHT + 20)
        _section_title(doc, "Группы")
        doc.text(MARGIN, doc.y - 12, "Нет данных за этот месяц.", font=_REGULAR, size=9.5, color=INK_MUTED)
        doc.y -= 26
        return

    col_widths = [CONTENT_W * 0.5, CONTENT_W * 0.25, CONTENT_W * 0.25]
    row_h = 22
    doc.ensure_space(_TITLE_HEIGHT + row_h * (len(groups) + 1) + 6)
    _section_title(doc, "Группы")

    header_y = doc.y
    _rounded_rect(doc.c, MARGIN, header_y - row_h, CONTENT_W, row_h, 6, fill=SURFACE_MUTED)
    headers = ["Группа", "Студенты", "Занятия"]
    x = MARGIN + 12
    for width, header in zip(col_widths, headers):
        doc.text(x, header_y - row_h + 7, header, font=_BOLD, size=9, color=INK_SECONDARY)
        x += width
    doc.y = header_y - row_h

    for group in groups:
        doc.ensure_space(row_h)
        x = MARGIN + 12
        values = [group["name"], str(group["students_count"]), str(group["lessons_count"])]
        for width, value in zip(col_widths, values):
            doc.text(x, doc.y - row_h + 7, value, font=_REGULAR, size=9.5, color=INK)
            x += width
        doc.y -= row_h
        doc.hline(doc.y, color=BORDER, width=0.5)
    doc.y -= 14


def _draw_weekly_dynamics(doc: _Doc, stats: dict) -> None:
    weeks = stats["weekly_dynamics"]
    if len(weeks) < 2:
        doc.ensure_space(_TITLE_HEIGHT + 20)
        _section_title(doc, "Динамика по неделям")
        doc.text(MARGIN, doc.y - 12, "Недостаточно данных для динамики.", font=_REGULAR, size=9.5, color=INK_MUTED)
        doc.y -= 26
        return

    chart_h = 60
    doc.ensure_space(_TITLE_HEIGHT + chart_h + 24)
    _section_title(doc, "Динамика по неделям")
    base_y = doc.y - chart_h
    col_w = CONTENT_W / len(weeks)
    bar_w = min(28, col_w * 0.4)
    for index, week in enumerate(weeks):
        cx = MARGIN + col_w * index + col_w / 2
        bar_h = chart_h * week["percent"] / 100
        _rounded_rect(doc.c, cx - bar_w / 2, base_y, bar_w, max(bar_h, 2), 3, fill=BRAND)
        doc.text(cx, base_y + bar_h + 6, f"{week['percent']:g}%", font=_BOLD, size=8.5, color=INK, align="center")
        doc.text(cx, base_y - 12, week["label"], font=_REGULAR, size=8, color=INK_SECONDARY, align="center")
    doc.y = base_y - 26


def _draw_kpi_breakdown(doc: _Doc, stats: dict) -> None:
    kpi = stats["kpi"]
    bars = [
        ("Attendance", kpi["attendance"]),
        ("Homework", kpi["homework"]),
        ("Lessons", kpi["lessons"]),
        ("Student Progress", kpi["student_progress"]),
    ]
    bar_h = 8
    row_h = 26
    doc.ensure_space(_TITLE_HEIGHT + row_h * len(bars) + 46)
    _section_title(doc, "KPI")
    label_w = 120
    value_w = 44
    bar_area_w = CONTENT_W - label_w - value_w

    for label, percent in bars:
        row_top = doc.y
        doc.text(MARGIN, row_top - 6, label, font=_REGULAR, size=9.5, color=INK_SECONDARY)
        _progress_bar(doc.c, MARGIN + label_w, row_top - bar_h - 2, bar_area_w, bar_h, percent, BRAND)
        doc.text(PAGE_W - MARGIN, row_top - 6, f"{percent:g}%", font=_BOLD, size=9.5, color=INK, align="right")
        doc.y -= row_h

    doc.y -= 6
    _rounded_rect(doc.c, MARGIN, doc.y - 40, CONTENT_W, 40, 10, fill=BRAND_SOFT)
    doc.text(MARGIN + 16, doc.y - 25, "TOTAL KPI", font=_BOLD, size=10, color=BRAND_DARK)
    doc.text(PAGE_W - MARGIN - 16, doc.y - 27, f"{kpi['total']:g}%", font=_BOLD, size=18, color=BRAND_DARK, align="right")
    doc.y -= 56


def _draw_comment(doc: _Doc, report) -> None:
    text = report.comment.strip() or "Комментарий за этот месяц ещё не добавлен."
    color = INK if report.comment.strip() else INK_MUTED
    lines = _wrap_text(text, _REGULAR, 10, CONTENT_W)
    doc.ensure_space(_TITLE_HEIGHT + 16 * len(lines) + 14)
    _section_title(doc, "Итог месяца")
    for line in lines:
        doc.text(MARGIN, doc.y - 12, line, font=_REGULAR, size=10, color=color)
        doc.y -= 16
    doc.y -= 8


def _draw_signatures(doc: _Doc, report) -> None:
    teacher_name = report.teacher.user.get_full_name() or report.teacher.user.username
    today = report.updated_at.strftime("%d.%m.%Y")

    doc.ensure_space(70)
    doc.hline(doc.y)
    doc.y -= 30

    col_w = CONTENT_W / 3
    labels = [("Тренер", teacher_name), ("Администратор", "_" * 22), ("Дата", today)]
    for index, (label, value) in enumerate(labels):
        x = MARGIN + col_w * index
        doc.text(x, doc.y, label, font=_REGULAR, size=8.5, color=INK_MUTED)
        doc.text(x, doc.y - 16, value, font=_BOLD, size=10.5, color=INK)


def build_monthly_report_pdf(report) -> bytes:
    _ensure_fonts()
    stats = compute_monthly_stats(report.teacher, report.year, report.month)

    buffer = io.BytesIO()
    doc = _Doc(buffer)

    _draw_header(doc, report)
    _draw_top_stats(doc, stats)

    if not stats["has_data"]:
        doc.text(MARGIN, doc.y - 12, "Нет данных за этот месяц.", font=_REGULAR, size=10, color=INK_MUTED)
        doc.y -= 30
    else:
        _draw_kpi_cards(doc, stats)
        _draw_work_rows(doc, stats)
        _draw_groups_table(doc, stats)
        _draw_weekly_dynamics(doc, stats)
        _draw_kpi_breakdown(doc, stats)

    _draw_comment(doc, report)
    _draw_signatures(doc, report)

    doc.c.showPage()
    doc.c.save()
    return buffer.getvalue()
