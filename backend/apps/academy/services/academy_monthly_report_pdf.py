"""Renders an `AcademyMonthlyReport` as a real, print-friendly A4 PDF — built
directly with reportlab's canvas (never a screenshot/html2canvas), reusing
exactly the figures `academy_monthly_report.compute_academy_monthly_stats`
already computes for the API/frontend, so the PDF can never show a number
the on-screen report doesn't.

Deliberately mirrors `monthly_report_pdf.py`'s layout/helpers (same fonts,
palette, section-title/rounded-rect/progress-bar primitives, weekly line
chart) rather than a second, independent PDF implementation — the two
reports are visually one family.
"""
from __future__ import annotations

import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .chart_geometry import nice_domain, nice_ticks, ratio_in_domain
from .academy_monthly_report import compute_academy_monthly_stats
from .monthly_report_pdf import (
    BORDER,
    BRAND,
    BRAND_DARK,
    BRAND_SOFT,
    INK,
    INK_MUTED,
    INK_SECONDARY,
    MONTH_NAMES_RU,
    SURFACE_MUTED,
    WHITE,
    _BOLD,
    _REGULAR,
    _ensure_fonts,
    _fmt_percent,
    _progress_bar,
    _rounded_rect,
    _wrap_text,
)

PAGE_W, PAGE_H = A4
MARGIN = 42
CONTENT_W = PAGE_W - 2 * MARGIN

_TITLE_HEIGHT = 28
_SUBTITLE_HEIGHT = 14


def _na(value, formatter=str) -> str:
    """Renders `None` as "Нет данных" — never a fabricated 0/0%/blank."""
    return "Нет данных" if value is None else formatter(value)


class _Doc:
    """Same cursor-based canvas wrapper as `monthly_report_pdf._Doc` — kept
    as a private copy rather than an imported shared class, so this report's
    page-break logic never accidentally changes the Teacher report's."""

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


def _section_title(doc: _Doc, title: str, subtitle: str | None = None) -> None:
    doc.y -= 10
    doc.text(MARGIN, doc.y, title, font=_BOLD, size=11.5, color=INK)
    doc.y -= 18
    if subtitle:
        doc.text(MARGIN, doc.y, subtitle, font=_REGULAR, size=8.5, color=INK_SECONDARY)
        doc.y -= _SUBTITLE_HEIGHT


def _draw_header(doc: _Doc, report) -> None:
    month_label = f"{MONTH_NAMES_RU[report.month]} {report.year}"

    doc.ensure_space(90)
    top = doc.y

    doc.text(MARGIN, top, "OKURMENKIDS", font=_BOLD, size=13, color=BRAND)
    doc.text(MARGIN, top - 16, "Месячный отчёт академии", font=_REGULAR, size=9, color=INK_MUTED)
    doc.text(MARGIN, top - 40, month_label, font=_BOLD, size=18, color=INK)
    doc.text(MARGIN, top - 58, "Ежемесячный отчёт OKURMENKIDS", font=_REGULAR, size=9.5, color=INK_SECONDARY)

    doc.y = top - 74
    doc.hline(doc.y)
    doc.y -= 20


def _draw_kpi_cards(doc: _Doc, stats: dict) -> None:
    cards = [
        (str(stats["students_count"]), "Студенты"),
        (str(stats["groups_count"]), "Группы"),
        (str(stats["teachers_count"]), "Преподаватели"),
        (str(stats["lessons_completed"]), "Занятия"),
        (_fmt_percent(stats["attendance"]["rate"]), "Посещаемость"),
        (_fmt_percent(stats["kpi"]["total"]), "Средний KPI"),
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


def _draw_students(doc: _Doc, stats: dict) -> None:
    students = stats["students"]
    rows = [
        ("Всего активных студентов", str(students["active"])),
        ("Новые студенты", str(students["new"])),
        ("Завершили обучение", str(students["completed"])),
        ("Приостановили обучение", str(students["paused"])),
        ("Вышли из курса", str(students["left"])),
    ]
    row_h = 22
    doc.ensure_space(_TITLE_HEIGHT + row_h * len(rows) + 10)
    _section_title(doc, "Студенты")
    for label, value in rows:
        doc.text(MARGIN, doc.y - 15, label, font=_REGULAR, size=10, color=INK_SECONDARY)
        doc.text(PAGE_W - MARGIN, doc.y - 15, value, font=_BOLD, size=10.5, color=INK, align="right")
        doc.y -= row_h
        doc.hline(doc.y + 4, color=BORDER, width=0.5)
    doc.y -= 4


def _draw_groups_table(doc: _Doc, stats: dict) -> None:
    groups = stats["groups"]
    if not groups:
        doc.ensure_space(_TITLE_HEIGHT + 20)
        _section_title(doc, "Группы")
        doc.text(MARGIN, doc.y - 12, "Нет данных за этот месяц.", font=_REGULAR, size=9.5, color=INK_MUTED)
        doc.y -= 26
        return

    col_widths = [CONTENT_W * 0.34, CONTENT_W * 0.16, CONTENT_W * 0.16, CONTENT_W * 0.17, CONTENT_W * 0.17]
    row_h = 22
    doc.ensure_space(_TITLE_HEIGHT + row_h * (len(groups) + 1) + 6)
    _section_title(doc, "Группы")

    header_y = doc.y
    _rounded_rect(doc.c, MARGIN, header_y - row_h, CONTENT_W, row_h, 6, fill=SURFACE_MUTED)
    headers = ["Группа", "Студенты", "Занятия", "Посещ.", "Статус"]
    x = MARGIN + 10
    for width, header in zip(col_widths, headers):
        doc.text(x, header_y - row_h + 7, header, font=_BOLD, size=9, color=INK_SECONDARY)
        x += width
    doc.y = header_y - row_h

    for group in groups:
        doc.ensure_space(row_h)
        x = MARGIN + 10
        values = [
            group["name"],
            str(group["students_count"]),
            str(group["lessons_count"]),
            _fmt_percent(group["attendance_rate"]),
            group["status_display"],
        ]
        for width, value in zip(col_widths, values):
            doc.text(x, doc.y - row_h + 7, value, font=_REGULAR, size=9, color=INK)
            x += width
        doc.y -= row_h
        doc.hline(doc.y, color=BORDER, width=0.5)
    doc.y -= 14


def _draw_teachers_table(doc: _Doc, stats: dict) -> None:
    teachers = stats["teachers"]
    if not teachers:
        doc.ensure_space(_TITLE_HEIGHT + 20)
        _section_title(doc, "Преподаватели")
        doc.text(MARGIN, doc.y - 12, "Нет данных за этот месяц.", font=_REGULAR, size=9.5, color=INK_MUTED)
        doc.y -= 26
        return

    col_widths = [CONTENT_W * 0.36, CONTENT_W * 0.16, CONTENT_W * 0.16, CONTENT_W * 0.16, CONTENT_W * 0.16]
    row_h = 22
    doc.ensure_space(_TITLE_HEIGHT + row_h * (len(teachers) + 1) + 6)
    _section_title(doc, "Преподаватели")

    header_y = doc.y
    _rounded_rect(doc.c, MARGIN, header_y - row_h, CONTENT_W, row_h, 6, fill=SURFACE_MUTED)
    headers = ["Преподаватель", "Занятия", "Студенты", "Посещ.", "KPI"]
    x = MARGIN + 10
    for width, header in zip(col_widths, headers):
        doc.text(x, header_y - row_h + 7, header, font=_BOLD, size=9, color=INK_SECONDARY)
        x += width
    doc.y = header_y - row_h

    for teacher in teachers:
        doc.ensure_space(row_h)
        x = MARGIN + 10
        values = [
            teacher["name"],
            str(teacher["lessons_completed"]),
            str(teacher["students_count"]),
            _fmt_percent(teacher["attendance_rate"]),
            _na(teacher["kpi_total"], _fmt_percent),
        ]
        for width, value in zip(col_widths, values):
            doc.text(x, doc.y - row_h + 7, value, font=_REGULAR, size=9, color=INK)
            x += width
        doc.y -= row_h
        doc.hline(doc.y, color=BORDER, width=0.5)
    doc.y -= 14


def _draw_study_process(doc: _Doc, stats: dict) -> None:
    lessons = stats["lessons"]
    rows = [
        ("Запланировано занятий", str(lessons["scheduled"])),
        ("Проведено занятий", str(lessons["completed"])),
        ("Отменено занятий", str(lessons["cancelled"])),
        ("Перенесено занятий", _na(lessons["rescheduled"])),
        ("Средняя посещаемость", _fmt_percent(lessons["attendance_rate"])),
    ]
    row_h = 22
    doc.ensure_space(_TITLE_HEIGHT + row_h * len(rows) + 10)
    _section_title(doc, "Учебный процесс")
    for label, value in rows:
        doc.text(MARGIN, doc.y - 15, label, font=_REGULAR, size=10, color=INK_SECONDARY)
        doc.text(PAGE_W - MARGIN, doc.y - 15, value, font=_BOLD, size=10.5, color=INK, align="right")
        doc.y -= row_h
        doc.hline(doc.y + 4, color=BORDER, width=0.5)
    doc.y -= 4


def _draw_homework(doc: _Doc, stats: dict) -> None:
    homework = stats["homework"]
    rows = [
        ("Выдано домашних заданий", str(homework["assigned"])),
        ("Проверено домашних заданий", str(homework["checked"])),
        ("Ожидают проверки", str(homework["pending_review"])),
        ("Процент проверки", _na(homework["checked_rate"], _fmt_percent)),
    ]
    row_h = 22
    doc.ensure_space(_TITLE_HEIGHT + row_h * len(rows) + 10)
    _section_title(doc, "Домашние задания")
    for label, value in rows:
        doc.text(MARGIN, doc.y - 15, label, font=_REGULAR, size=10, color=INK_SECONDARY)
        doc.text(PAGE_W - MARGIN, doc.y - 15, value, font=_BOLD, size=10.5, color=INK, align="right")
        doc.y -= row_h
        doc.hline(doc.y + 4, color=BORDER, width=0.5)
    doc.y -= 4


def _draw_weekly_dynamics(doc: _Doc, stats: dict) -> None:
    weeks = stats["weekly_dynamics"]
    if len(weeks) < 2:
        doc.ensure_space(_TITLE_HEIGHT + _SUBTITLE_HEIGHT + 20)
        _section_title(doc, "Динамика академии", subtitle="Посещаемость по неделям")
        doc.text(MARGIN, doc.y - 12, "Недостаточно данных для отображения динамики.", font=_REGULAR, size=9.5, color=INK_MUTED)
        doc.y -= 26
        return

    chart_h = 140
    top_pad = 18
    bottom_pad = 16
    y_axis_w = 26

    doc.ensure_space(_TITLE_HEIGHT + _SUBTITLE_HEIGHT + chart_h + 20)
    _section_title(doc, "Динамика академии", subtitle="Посещаемость по неделям")

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

    doc.c.saveState()
    doc.c.setStrokeColor(BORDER)
    doc.c.setLineWidth(0.5)
    for tick in ticks:
        ty = y_for(tick)
        doc.c.line(plot_x0, ty, plot_x1, ty)
        doc.text(plot_x0 - 6, ty - 3, f"{tick}%", font=_REGULAR, size=7, color=INK_MUTED, align="right")
    doc.c.restoreState()

    points = [(x_for(i), y_for(w["percent"])) for i, w in enumerate(weeks)]

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
    _section_title(doc, "Показатели академии")

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
    doc.text(MARGIN + 16, doc.y - 25, "ИТОГОВЫЙ ПОКАЗАТЕЛЬ", font=_BOLD, size=10, color=BRAND_DARK)
    doc.text(PAGE_W - MARGIN - 16, doc.y - 27, _fmt_percent(kpi["total"]), font=_BOLD, size=18, color=BRAND_DARK, align="right")
    doc.y -= 56


def _draw_movement(doc: _Doc, stats: dict) -> None:
    movement = stats["movement"]
    rows = [
        ("Вышли из курса за месяц", str(movement["left"])),
        ("Завершили обучение", str(movement["completed"]["count"])),
        ("Приостановили обучение", str(movement["paused"]["count"])),
        ("Продолжили обучение", str(movement["continued"]["count"])),
        ("Вернулись после паузы", str(movement["returned_after_pause"]["count"])),
    ]
    row_h = 20
    doc.ensure_space(_TITLE_HEIGHT + row_h * len(rows) + 10)
    _section_title(doc, "Движение студентов")
    for label, value in rows:
        doc.text(MARGIN, doc.y - 14, label, font=_REGULAR, size=9.5, color=INK_SECONDARY)
        doc.text(PAGE_W - MARGIN, doc.y - 14, value, font=_BOLD, size=10, color=INK, align="right")
        doc.y -= row_h
    doc.y -= 6


def _draw_reason_breakdown(doc: _Doc, stats: dict) -> None:
    """Spec §8: reason, count, and percent of that month's departures —
    computed once in `academy_monthly_report._departures` and only ever
    rendered here, never recalculated."""
    reasons = stats["movement"]["reasons"]
    if not reasons:
        doc.ensure_space(_TITLE_HEIGHT + 20)
        _section_title(doc, "Разбивка по причинам ухода")
        doc.text(
            MARGIN, doc.y - 12,
            "За выбранный период уходов студентов не зарегистрировано.",
            font=_REGULAR, size=9.5, color=INK_MUTED,
        )
        doc.y -= 26
        return

    col_widths = [CONTENT_W * 0.5, CONTENT_W * 0.2, CONTENT_W * 0.3]
    row_h = 20
    doc.ensure_space(_TITLE_HEIGHT + row_h * (len(reasons) + 1) + 6)
    _section_title(doc, "Разбивка по причинам ухода")

    header_y = doc.y
    _rounded_rect(doc.c, MARGIN, header_y - row_h, CONTENT_W, row_h, 6, fill=SURFACE_MUTED)
    x = MARGIN + 10
    for width, header in zip(col_widths, ["Причина", "Студентов", "% от ушедших"]):
        doc.text(x, header_y - row_h + 6, header, font=_BOLD, size=9, color=INK_SECONDARY)
        x += width
    doc.y = header_y - row_h

    for row in reasons:
        doc.ensure_space(row_h)
        x = MARGIN + 10
        for width, value in zip(col_widths, [row["reason_display"], str(row["count"]), _fmt_percent(row["percent"])]):
            doc.text(x, doc.y - row_h + 6, value, font=_REGULAR, size=9, color=INK)
            x += width
        doc.y -= row_h
        doc.hline(doc.y, color=BORDER, width=0.5)
    doc.y -= 14


def _draw_attention(doc: _Doc, stats: dict) -> None:
    items = stats["attention"]
    if not items:
        return
    lines_needed = sum(len(_wrap_text(item["message"], _REGULAR, 9.5, CONTENT_W - 14)) for item in items)
    doc.ensure_space(_TITLE_HEIGHT + lines_needed * 14 + 10)
    _section_title(doc, "Требует внимания")
    for item in items:
        lines = _wrap_text(item["message"], _REGULAR, 9.5, CONTENT_W - 14)
        for index, line in enumerate(lines):
            prefix = "•  " if index == 0 else "   "
            doc.text(MARGIN, doc.y - 12, prefix + line, font=_REGULAR, size=9.5, color=INK_SECONDARY)
            doc.y -= 14
    doc.y -= 8


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


def _draw_footer(doc: _Doc, report) -> None:
    generated = report.updated_at.strftime("%d.%m.%Y %H:%M")
    doc.ensure_space(40)
    doc.hline(doc.y)
    doc.y -= 18
    doc.text(MARGIN, doc.y, f"Дата формирования отчёта: {generated}", font=_REGULAR, size=8.5, color=INK_MUTED)


def build_academy_monthly_report_pdf(report) -> bytes:
    _ensure_fonts()
    stats = compute_academy_monthly_stats(report.year, report.month)

    buffer = io.BytesIO()
    doc = _Doc(buffer)

    _draw_header(doc, report)

    if not stats["has_data"]:
        doc.text(MARGIN, doc.y - 12, "Нет данных за этот месяц.", font=_REGULAR, size=10, color=INK_MUTED)
        doc.y -= 30
    else:
        _draw_kpi_cards(doc, stats)
        _draw_students(doc, stats)
        _draw_groups_table(doc, stats)
        _draw_teachers_table(doc, stats)
        _draw_study_process(doc, stats)
        _draw_homework(doc, stats)
        _draw_weekly_dynamics(doc, stats)
        _draw_kpi_breakdown(doc, stats)
        _draw_movement(doc, stats)
        _draw_reason_breakdown(doc, stats)
        _draw_attention(doc, stats)

    _draw_comment(doc, report)
    _draw_footer(doc, report)

    doc.c.showPage()
    doc.c.save()
    return buffer.getvalue()
