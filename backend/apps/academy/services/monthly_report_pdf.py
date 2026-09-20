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

from .chart_geometry import nice_domain, nice_ticks, ratio_in_domain
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


def _fmt_percent(value: float) -> str:
    """`94.4` -> `"94,4%"`, `100` -> `"100%"` — Russian decimal comma,
    matching the frontend (see utils/format.ts's formatRuPercent)."""
    return f"{value:g}".replace(".", ",") + "%"


def _truncate_text(text: str, font: str, size: float, max_width: float) -> str:
    """Truncates `text` with a trailing ellipsis so it never exceeds
    `max_width` at the given font/size. A table row has no line wrapping —
    an un-clamped free-text value (a long Group/Teacher name) drawn at a
    fixed column x-position would otherwise silently run past its column
    boundary and print flush against the next column's value with no gap,
    reading as one garbled token (e.g. a group named "…— Группа 03" next
    to a students count of 10 rendering as "…Группа 0310"). Every table
    column holding a free-text name must run its value through this before
    drawing it."""
    if pdfmetrics.stringWidth(text, font, size) <= max_width:
        return text
    ellipsis = "…"
    ellipsis_width = pdfmetrics.stringWidth(ellipsis, font, size)
    truncated = text
    while truncated and pdfmetrics.stringWidth(truncated, font, size) + ellipsis_width > max_width:
        truncated = truncated[:-1]
    return (truncated.rstrip() + ellipsis) if truncated else ellipsis


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
    position = teacher.position or "Преподаватель"
    month_label = f"{MONTH_NAMES_RU[report.month]} {report.year}"

    doc.ensure_space(120)
    top = doc.y

    doc.text(MARGIN, top, "OKURMENKIDS", font=_BOLD, size=13, color=BRAND)
    doc.text(MARGIN, top - 16, "Ежемесячный отчёт преподавателя", font=_REGULAR, size=9, color=INK_MUTED)

    photo_size = 64
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


def _draw_kpi_cards(doc: _Doc, stats: dict) -> None:
    cards = [
        (str(stats["lessons_completed"]), "Занятия"),
        (str(stats["students_count"]), "Студенты"),
        (str(stats["groups_count"]), "Группы"),
        (_fmt_percent(stats["attendance"]["rate"]), "Посещаемость"),
        (_fmt_percent(stats["homework"]["submission_rate"]), "Домашние задания"),
        (_fmt_percent(stats["kpi"]["total"]), "Итоговый KPI"),
    ]
    cols = 3
    gap = 10
    card_w = (CONTENT_W - gap * (cols - 1)) / cols
    card_h = 52
    rows = (len(cards) + cols - 1) // cols
    doc.ensure_space(_TITLE_HEIGHT + rows * (card_h + gap))
    _section_title(doc, "Основная статистика")

    for index, (value, label) in enumerate(cards):
        row, col = divmod(index, cols)
        x = MARGIN + col * (card_w + gap)
        y = doc.y - row * (card_h + gap) - card_h
        _rounded_rect(doc.c, x, y, card_w, card_h, 8, fill=WHITE, stroke=BORDER, line_width=0.75)
        doc.text(x + 12, y + card_h - 22, value, font=_BOLD, size=15, color=INK)
        doc.text(x + 12, y + 12, label, font=_REGULAR, size=8.5, color=INK_SECONDARY)

    doc.y -= rows * (card_h + gap) - gap


_TITLE_HEIGHT = 28


_SUBTITLE_HEIGHT = 14


def _section_title(doc: _Doc, title: str, subtitle: str | None = None) -> None:
    """Draws the heading (+ optional muted subtitle) only — the caller must
    `ensure_space` for the heading *plus* its body beforehand (see
    `_TITLE_HEIGHT`/`_SUBTITLE_HEIGHT`), so a section's title never gets
    orphaned at the bottom of a page while its content flows onto the next
    one."""
    doc.y -= 10
    doc.text(MARGIN, doc.y, title, font=_BOLD, size=11.5, color=INK)
    doc.y -= 18
    if subtitle:
        doc.text(MARGIN, doc.y, subtitle, font=_REGULAR, size=8.5, color=INK_SECONDARY)
        doc.y -= _SUBTITLE_HEIGHT


def _draw_work_rows(doc: _Doc, stats: dict) -> None:
    rows = [
        ("Проведено занятий", str(stats["lessons_completed"])),
        ("Выдано домашних заданий", str(stats["homework"]["assigned"])),
        ("Проверено работ студентов", str(stats["homework"]["checked"])),
        ("Работа со студентами", str(stats["students_count"])),
    ]
    row_h = 22
    doc.ensure_space(_TITLE_HEIGHT + row_h * len(rows) + 10)
    _section_title(doc, "Работа преподавателя")
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
        name = _truncate_text(group["name"], _REGULAR, 9.5, col_widths[0] - 14)
        values = [name, str(group["students_count"]), str(group["lessons_count"])]
        for width, value in zip(col_widths, values):
            doc.text(x, doc.y - row_h + 7, value, font=_REGULAR, size=9.5, color=INK)
            x += width
        doc.y -= row_h
        doc.hline(doc.y, color=BORDER, width=0.5)
    doc.y -= 14


def _draw_weekly_dynamics(doc: _Doc, stats: dict) -> None:
    """A real line chart — points, connecting line, a light grid, and a
    Y-axis auto-scaled to the data's own range (see chart_geometry), so a
    strong, stable month (89.8 -> 95.9 -> 95.9 -> 95.9) still reads as
    visible movement instead of four dots flattened against a fixed
    0-100% scale. Drawn natively with reportlab's canvas — never a
    screenshot of the frontend chart."""
    weeks = stats["weekly_dynamics"]
    if len(weeks) < 2:
        doc.ensure_space(_TITLE_HEIGHT + _SUBTITLE_HEIGHT + 20)
        _section_title(doc, "Динамика посещаемости", subtitle="Посещаемость по неделям")
        doc.text(MARGIN, doc.y - 12, "Недостаточно данных для динамики.", font=_REGULAR, size=9.5, color=INK_MUTED)
        doc.y -= 26
        return

    chart_h = 140
    top_pad = 18      # headroom above the topmost point for its value label
    bottom_pad = 16   # room below the plot for week labels
    y_axis_w = 26

    doc.ensure_space(_TITLE_HEIGHT + _SUBTITLE_HEIGHT + chart_h + 20)
    _section_title(doc, "Динамика посещаемости", subtitle="Посещаемость по неделям")

    values = [w["percent"] for w in weeks]
    domain_lo, domain_hi = nice_domain(values)
    ticks = nice_ticks(domain_lo, domain_hi)

    plot_x0 = MARGIN + y_axis_w
    plot_x1 = PAGE_W - MARGIN
    plot_top = doc.y
    inner_top = plot_top - top_pad
    inner_bottom = plot_top - chart_h + bottom_pad

    def y_for(value: float) -> float:
        ratio = ratio_in_domain(value, domain_lo, domain_hi)
        return inner_bottom + ratio * (inner_top - inner_bottom)

    def x_for(index: int) -> float:
        if len(weeks) == 1:
            return (plot_x0 + plot_x1) / 2
        return plot_x0 + (index / (len(weeks) - 1)) * (plot_x1 - plot_x0)

    # Gridlines + Y-axis labels — thin and unobtrusive.
    doc.c.saveState()
    doc.c.setStrokeColor(BORDER)
    doc.c.setLineWidth(0.5)
    for tick in ticks:
        ty = y_for(tick)
        doc.c.line(plot_x0, ty, plot_x1, ty)
        doc.text(plot_x0 - 6, ty - 3, f"{tick}%", font=_REGULAR, size=7, color=INK_MUTED, align="right")
    doc.c.restoreState()

    points = [(x_for(i), y_for(w["percent"])) for i, w in enumerate(weeks)]

    # Connecting line.
    doc.c.saveState()
    doc.c.setStrokeColor(BRAND)
    doc.c.setLineWidth(1.6)
    doc.c.setLineJoin(1)
    path = doc.c.beginPath()
    path.moveTo(*points[0])
    for px, py in points[1:]:
        path.lineTo(px, py)
    doc.c.drawPath(path, stroke=1, fill=0)
    doc.c.restoreState()

    # Point markers, value labels above each point, week labels below the plot.
    plot_bottom = plot_top - chart_h
    for (px, py), week in zip(points, weeks):
        doc.c.saveState()
        doc.c.setFillColor(BRAND)
        doc.c.circle(px, py, 3.2, stroke=0, fill=1)
        doc.c.setFillColor(WHITE)
        doc.c.circle(px, py, 1.3, stroke=0, fill=1)
        doc.c.restoreState()
        doc.text(px, py + 8, _fmt_percent(week["percent"]), font=_BOLD, size=8, color=INK, align="center")
        doc.text(px, plot_bottom + 2, week["label"], font=_REGULAR, size=8, color=INK_SECONDARY, align="center")

    doc.y = plot_bottom - 14


def _draw_kpi_breakdown(doc: _Doc, stats: dict) -> None:
    """A compact 2x2 grid, not four bars stretched across the full page
    width — the same layout as the frontend and the admin screen."""
    kpi = stats["kpi"]
    metrics = [
        ("Посещаемость", kpi["attendance"]),
        ("Домашние задания", kpi["homework"]),
        ("Проведённые занятия", kpi["lessons"]),
        ("Прогресс студентов", kpi["student_progress"]),
    ]
    cols = 2
    gap_x = 24
    gap_y = 18
    cell_w = (CONTENT_W - gap_x * (cols - 1)) / cols
    cell_h = 44
    bar_h = 6
    rows = (len(metrics) + cols - 1) // cols

    doc.ensure_space(_TITLE_HEIGHT + rows * cell_h + (rows - 1) * gap_y + 50)
    _section_title(doc, "Показатели KPI")

    top = doc.y
    for index, (label, percent) in enumerate(metrics):
        row, col = divmod(index, cols)
        x = MARGIN + col * (cell_w + gap_x)
        y = top - row * (cell_h + gap_y)
        doc.text(x, y - 10, label, font=_REGULAR, size=9, color=INK_SECONDARY)
        if percent is None:
            doc.text(x, y - 27, "Нет данных", font=_BOLD, size=13, color=INK_MUTED)
        else:
            doc.text(x, y - 27, _fmt_percent(percent), font=_BOLD, size=15, color=INK)
            _progress_bar(doc.c, x, y - 36, cell_w, bar_h, percent, BRAND)

    doc.y = top - rows * cell_h - (rows - 1) * gap_y - 8
    _rounded_rect(doc.c, MARGIN, doc.y - 40, CONTENT_W, 40, 10, fill=BRAND_SOFT)
    doc.text(MARGIN + 16, doc.y - 25, "ИТОГОВЫЙ KPI", font=_BOLD, size=10, color=BRAND_DARK)
    doc.text(PAGE_W - MARGIN - 16, doc.y - 27, _fmt_percent(kpi["total"]), font=_BOLD, size=18, color=BRAND_DARK, align="right")
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
    labels = [("Преподаватель", teacher_name), ("Администратор", "_" * 22), ("Дата", today)]
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
