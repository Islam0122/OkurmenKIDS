"""A Team Lead report (TeamLeadReport) as an A4 portrait PDF.

Only a renderer: it draws the very payload the report page shows —
`TeamLeadReportSerializer(..., detail=True)`: the form fields of the kind
(apps.worklog.schemas), the day's journal records (daily report), the
meeting decisions, and the LMS figures stored on the report (`metrics`, the
snapshot the page shows — nothing is recalculated here).

Drawn with reportlab in the family of the existing academy PDFs: DejaVu
fonts (Cyrillic and Kyrgyz ң ө ү), the LMS green palette and the table /
section primitives of the Assistant's monthly report (apps.assistant
.monthly_pdf): long text wraps instead of being cut, tables continue on the
next page with their header repeated, every page has «Страница N из M».
"""
from __future__ import annotations

import datetime as dt
import io

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4

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
)
from apps.assistant.monthly_pdf import (
    CONTENT_W,
    FOOTER_H,
    HEADER_H,
    MARGIN,
    PAGE_H,
    PAGE_W,
    _Canvas as _BaseCanvas,
    _Doc as _BaseDoc,
    _section,
    _table,
    _wrap,
)

from .models import ReportKind, TeamLeadReport
from .schemas import REPORT_KINDS

# --- LMS figures: the same labels and formatting as the page (ReportMetrics.tsx) ---

METRIC_LABELS = {
    "groups": "Группы", "trainers": "Тренеры", "students": "Студенты", "homework": "Домашние задания",
    "kpi": "KPI", "tests": "Тесты и экзамены", "quality": "Контроль качества", "exams": "Экзамены",
    "lessons": "Занятия", "total": "Всего", "active": "Активных", "new": "Новых", "closed": "Закрыто",
    "left": "Ушли", "with_problems": "С проблемами", "problem_names": "Требуют внимания",
    "low_attendance": "С низкой посещаемостью", "low_results": "С низкими результатами",
    "average_completion": "Средний процент выполнения", "groups_below_norm": "Групп ниже нормы",
    "attendance": "Посещаемость", "results": "Результаты", "progress": "Прогресс",
    "academy_kpi": "KPI академии", "average_trainer_kpi": "Средний KPI тренеров",
    "tests_held": "Проведено тестов", "exams_held": "Проведено экзаменов", "average_score": "Средний результат",
    "students_below_passing": "Студентов ниже минимума", "groups_with_exam": "Групп сдали экзамен",
    "groups_passed": "Групп сдали", "groups_total": "Групп всего", "students_below": "Студентов ниже нормы",
    "lessons_visited": "Посещено занятий", "trainers_checked": "Проверено тренеров",
    "problems_found": "Выявлено проблем", "problems_resolved": "Исправлено", "problems_in_progress": "В работе",
    "meetings": "Собраний", "held": "Проведено", "cancelled": "Отменено", "due": "По плану",
    "lessons_held": "Проведено занятий", "kpi_status": "Оценка KPI", "lesson_visits": "Проверок занятий",
    "lesson_visit_average": "Средняя оценка проверок", "date": "Дата", "time": "Время", "group": "Группа",
    "teacher": "Тренер", "subject": "Предмет", "room": "Кабинет", "status": "Статус", "lesson": "Занятие",
    "student": "Студент", "entries": "Записей журнала за день",
}
PERCENT_KEYS = {
    "attendance", "homework", "results", "progress", "academy_kpi", "average_trainer_kpi",
    "average_completion", "kpi", "lessons_held",
}
SKIP_KEYS = {"period", "id"}

LINK_LABELS = {"group": "Группа", "teacher": "Тренер", "student": "Студент", "lesson": "Занятие"}


def _d(value) -> str:
    if not value:
        return "—"
    if isinstance(value, str):
        value = dt.date.fromisoformat(value[:10])
    return value.strftime("%d.%m.%Y")


def pdf_filename(report: TeamLeadReport) -> str:
    """teamlead_report_monthly_2026_09.pdf, teamlead_report_weekly_2026_10_05-2026_10_11.pdf,
    teamlead_report_lesson_visit_2026_10_09.pdf — the kind and the period."""
    start, end = report.period_start, report.period_end
    if start and end:
        month_end = (start.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - dt.timedelta(days=1)
        if report.kind == ReportKind.MONTHLY and start.day == 1 and end == month_end:
            period = f"{start:%Y_%m}"
        elif start == end:
            period = f"{start:%Y_%m_%d}"
        else:
            period = f"{start:%Y_%m_%d}-{end:%Y_%m_%d}"
    else:
        period = f"{report.date:%Y_%m_%d}"
    return f"teamlead_report_{report.kind}_{period}.pdf"


def _is_ref(value) -> bool:
    return isinstance(value, dict) and "name" in value


def _is_group(value) -> bool:
    return isinstance(value, dict) and not _is_ref(value)


def metric_value(key: str, value, parent: str | None = None) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    if isinstance(value, (int, float)):
        number = f"{value:g}" if isinstance(value, float) else str(value)
        if key in PERCENT_KEYS and parent not in ("tests", "lessons"):
            return f"{number}%"
        if key == "average_score" and parent in ("tests", "exams"):
            return f"{number}%"
        return number
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "—"
    if _is_ref(value):
        return str(value["name"])
    if key == "date" and isinstance(value, str):
        return _d(value)
    return str(value)


def metric_sections(metrics: dict) -> list[tuple[str, list[tuple[str, str]]]]:
    """[(card title, [(label, value)])] — «Основное» with the plain values,
    then one card per nested group, in the order the page shows them."""
    def rows(data: dict, parent: str | None = None):
        return [
            (METRIC_LABELS.get(k, k), metric_value(k, v, parent))
            for k, v in data.items() if k not in SKIP_KEYS and not _is_group(v)
        ]

    sections = []
    plain = rows(metrics)
    if plain:
        sections.append(("Основное", plain))
    for key, value in metrics.items():
        if key not in SKIP_KEYS and _is_group(value):
            sections.append((METRIC_LABELS.get(key, key), rows(value, key)))
    return sections


def field_value(field: dict, value) -> str | list[str] | list[dict]:
    """A form field as the page shows it (ReportFieldValue)."""
    if value is None or value == "" or value == []:
        return "—"
    kind = field["type"]
    if kind == "rows":
        return value
    if isinstance(value, list):
        return [str(v) for v in value]
    if kind == "date":
        return _d(value)
    if kind == "score":
        return f"{value} из 5"
    return str(value)


# --- Document --------------------------------------------------------------------------------------

class _Canvas(_BaseCanvas):
    def _chrome(self, total: int) -> None:
        self.saveState()
        if self._pageNumber > 1:
            self.setFont(_BOLD, 8)
            self.setFillColor(BRAND_DARK)
            self.drawString(MARGIN, PAGE_H - 26, "OKURMENKIDS · ОТЧЁТ TEAM LEAD")
            self.setFont(_REGULAR, 8)
            self.setFillColor(INK_SECONDARY)
            title = _wrap(self._report_title, _REGULAR, 8, CONTENT_W * 0.6)[0]
            self.drawRightString(PAGE_W - MARGIN, PAGE_H - 26, title)
            self.setStrokeColor(BORDER)
            self.setLineWidth(0.6)
            self.line(MARGIN, PAGE_H - HEADER_H, PAGE_W - MARGIN, PAGE_H - HEADER_H)
        self.setStrokeColor(BORDER)
        self.setLineWidth(0.6)
        self.line(MARGIN, FOOTER_H, PAGE_W - MARGIN, FOOTER_H)
        self.setFont(_REGULAR, 7.5)
        self.setFillColor(INK_MUTED)
        self.drawString(MARGIN, FOOTER_H - 12, f"OkurmenKIDS · Отчёт Team Lead · сформирован {self._generated}")
        self.drawRightString(PAGE_W - MARGIN, FOOTER_H - 12, f"Страница {self._pageNumber} из {total}")
        self.restoreState()


class _Doc(_BaseDoc):
    def __init__(self, buffer: io.BytesIO, title: str, generated: str):  # noqa: super().__init__ draws a different title
        self.c = _Canvas(buffer, pagesize=A4, title=title, generated=generated)
        self.c.setTitle(f"Отчёт Team Lead — {title}")
        self.c.setAuthor("OkurmenKIDS")
        self.c.setSubject("Отчёт Team Lead")
        self.y = PAGE_H - MARGIN
        self.section_no = 0


def _cover(doc: _Doc, payload: dict, generated: str) -> None:
    c = doc.c
    # The title is «Вид · о ком · когда»; the kind is already the big heading.
    subtitle = payload["title"].removeprefix(payload["kind_label"]).lstrip(" ·") or payload["title"]
    title_lines = _wrap(subtitle, _BOLD, 13, CONTENT_W)
    band = 118 + 16 * (len(title_lines) - 1)
    c.saveState()
    c.setFillColor(BRAND_DARK)
    c.rect(0, PAGE_H - band, PAGE_W, band, stroke=0, fill=1)
    c.setFillColor(BRAND)
    c.rect(0, PAGE_H - band, PAGE_W, 4, stroke=0, fill=1)
    c.restoreState()
    top = PAGE_H - 42
    doc.text(MARGIN, top, "ОТЧЁТ TEAM LEAD · OKURMENKIDS", font=_BOLD, size=9, color=colors.HexColor("#bfe3cd"))
    doc.text(MARGIN, top - 26, payload["kind_label"], font=_BOLD, size=21, color=WHITE)
    y = top - 46
    for line in title_lines:
        doc.text(MARGIN, y, line, font=_BOLD, size=13, color=colors.HexColor("#d7ecdf"))
        y -= 16
    doc.y = PAGE_H - band - 14

    if payload.get("period_start") and payload.get("period_end"):
        period = f"{_d(payload['period_start'])} — {_d(payload['period_end'])}"
    else:
        period = _d(payload["date"])
    facts = [
        ("Отчётный период" if payload.get("period_start") else "Дата", period),
        ("Ответственный", f"{payload['author']['name']} · Team Lead"),
        ("Статус", payload["status_label"]),
        ("Дата формирования", generated),
    ]
    for link in ("group", "teacher", "student"):
        detail = payload.get(f"{link}_detail")
        if detail:
            facts.append((LINK_LABELS[link], detail["name"]))
    lesson = (payload.get("metrics") or {}).get("lesson") if payload["kind"] == ReportKind.LESSON_VISIT else None
    if lesson:
        facts.append(("Занятие", f"№{lesson.get('number')}" + (f" — {lesson['topic']}" if lesson.get("topic") else "")))
    _facts_box(doc, facts)


def _facts_box(doc: _Doc, facts: list[tuple[str, str]]) -> None:
    """Two-column key/value card; values wrap, nothing is cut."""
    col_w = CONTENT_W / 2
    label_w, pad = 92, 10
    rows = [facts[i:i + 2] for i in range(0, len(facts), 2)]
    heights = [max(len(_wrap(v, _BOLD, 8.6, col_w - label_w - 2 * pad)) for _, v in row) * 11 + 10 for row in rows]
    height = sum(heights) + 8
    doc.ensure(height + 10)
    top = doc.y
    _rounded_rect(doc.c, MARGIN, top - height, CONTENT_W, height, 6, fill=SURFACE_MUTED, stroke=BORDER, line_width=0.6)
    y = top - 6
    for row, h in zip(rows, heights):
        for i, (label, value) in enumerate(row):
            x = MARGIN + i * col_w + pad
            doc.text(x, y - 12, label, size=7.6, color=INK_SECONDARY)
            for j, line in enumerate(_wrap(value, _BOLD, 8.6, col_w - label_w - 2 * pad)):
                doc.text(x + label_w, y - 12 - j * 11, line, font=_BOLD, size=8.6, color=INK)
        y -= h
    doc.y = top - height - 12


def _content(doc: _Doc, payload: dict) -> None:
    schema = REPORT_KINDS[payload["kind"]]
    _section(doc, "Содержание отчёта", schema.get("description"))
    data = payload.get("data") or {}
    label_w = 150
    for field in schema["fields"]:
        shown = field_value(field, data.get(field["key"]))
        if field["type"] == "rows" and isinstance(shown, list):
            doc.ensure(40)
            doc.text(MARGIN, doc.y - 9, field["label"], font=_BOLD, size=8.6, color=INK_SECONDARY)
            doc.y -= 16
            columns = field["columns"]
            share = 1 / len(columns)
            _table(
                doc,
                [(c["label"], share, "left") for c in columns],
                [[(_d(row.get(c["key"])) if c["type"] == "date" else row.get(c["key"]) or "—") for c in columns] for row in shown],
                empty="Нет данных",
            )
            continue
        lines: list[tuple[str, bool]] = []  # (line, starts a bullet)
        if isinstance(shown, list):
            for item in shown:
                for j, line in enumerate(_wrap(item, _REGULAR, 8.6, CONTENT_W - label_w - 14)):
                    lines.append((line, j == 0))
        else:
            lines = [(line, False) for line in _wrap(shown, _REGULAR, 8.6, CONTENT_W - label_w)]
        label_lines = _wrap(field["label"], _BOLD, 8.2, label_w - 12)
        doc.ensure(max(len(label_lines), 1) * 11 + 6)
        top = doc.y
        for i, line in enumerate(label_lines):
            doc.text(MARGIN, top - 9 - i * 11, line, font=_BOLD, size=8.2, color=INK_SECONDARY)
        doc.y = top
        for line, bullet in lines:
            doc.ensure(12)
            x = MARGIN + label_w
            if isinstance(shown, list):
                if bullet:
                    doc.text(x, doc.y - 9, "•", font=_BOLD, size=8.6, color=BRAND)
                x += 12
            doc.text(x, doc.y - 9, line, size=8.6, color=INK if shown != "—" else INK_MUTED)
            doc.y -= 12
        doc.y = min(doc.y, top - len(label_lines) * 11) - 6
        doc.c.saveState()
        doc.c.setStrokeColor(BORDER)
        doc.c.setLineWidth(0.4)
        doc.c.line(MARGIN, doc.y + 2, MARGIN + CONTENT_W, doc.y + 2)
        doc.c.restoreState()
        doc.y -= 4
    doc.y -= 6


def _who(entry: dict) -> str:
    return ", ".join(
        p for p in (
            (entry.get("group_detail") or {}).get("name"), (entry.get("teacher_detail") or {}).get("name"),
            (entry.get("student_detail") or {}).get("name"), entry.get("with_whom"),
        ) if p
    )


def _time(entry: dict) -> str:
    if not entry.get("time_from"):
        return "—"
    text = entry["time_from"][:5]
    return f"{text}–{entry['time_to'][:5]}" if entry.get("time_to") else text


def _day_entries(doc: _Doc, entries: list[dict]) -> None:
    _section(doc, "Выполнено", "Записи рабочего журнала за этот день.")
    _table(
        doc,
        [("Время", 0.12, "left"), ("Задача", 0.36, "left"), ("Группа / тренер", 0.22, "left"), ("Результат", 0.30, "left")],
        [[_time(e), e.get("description") or e["work_type_label"], _who(e) or "—", e.get("result") or "—"] for e in entries],
        empty="За этот день записей нет.",
    )


def _decisions(doc: _Doc, tasks: list[dict]) -> None:
    _section(doc, "Решения", "Каждое решение — задача с ответственным, сроком и статусом.")

    def details(task: dict) -> str:
        parts = [task.get("title") or task["work_type_label"]]
        for label, key in (("Связано с", None), ("Цель", "goal"), ("Что сделано", "description"),
                           ("Результат", "result"), ("Проблема", "problem"), ("Решение", "decision"),
                           ("Что дальше", "next_action"), ("Комментарий", "comment")):
            value = _who(task) if key is None else task.get(key)
            if value:
                parts.append(f"{label}: {value}")
        return "\n".join(parts)

    _table(
        doc,
        [("Решение", 0.46, "left"), ("Ответственный", 0.18, "left"), ("Срок", 0.12, "left"),
         ("Приоритет", 0.11, "left"), ("Статус", 0.13, "left")],
        [[details(t), t.get("responsible") or "—", _d(t.get("deadline")), t["priority_label"],
          (t["effective_status_label"], colors.HexColor("#c7402e") if t.get("is_overdue") else INK)] for t in tasks],
        empty="Решений пока нет.",
    )


def _metrics(doc: _Doc, payload: dict) -> None:
    calculated = payload.get("metrics_calculated_at")
    hint = "Показатели посчитаны LMS"
    if calculated:
        moment = dt.datetime.fromisoformat(str(calculated).replace("Z", "+00:00"))
        hint += f" {timezone.localtime(moment):%d.%m.%Y %H:%M}"
    hint += " (снимок отчёта — те же значения, что на странице)."
    _section(doc, "Данные LMS", hint)
    sections = metric_sections(payload.get("metrics") or {})
    if not sections:
        doc.paragraph("Для этого отчёта LMS ничего не считает.", size=8.5, color=INK_SECONDARY)
        return
    for title, rows in sections:
        doc.ensure(50)
        doc.text(MARGIN, doc.y - 10, title, font=_BOLD, size=9.5, color=BRAND_DARK)
        doc.y -= 16
        _table(doc, [("Показатель", 0.62, "left"), ("Значение", 0.38, "right")], [[label, value] for label, value in rows],
               empty="Нет данных", header_fill=BRAND_SOFT)


def build_report_pdf(payload: dict) -> bytes:
    """`payload` — TeamLeadReportSerializer(report, context={"detail": True}).data."""
    _ensure_fonts()
    generated = timezone.localtime().strftime("%d.%m.%Y %H:%M")
    buffer = io.BytesIO()
    doc = _Doc(buffer, payload["title"], generated)
    _cover(doc, payload, generated)
    _content(doc, payload)
    if payload.get("day_entries") is not None:
        _day_entries(doc, payload["day_entries"])
    if payload["kind"] == ReportKind.MEETING:
        _decisions(doc, payload.get("tasks") or [])
    _metrics(doc, payload)
    doc.c.save()
    return buffer.getvalue()
