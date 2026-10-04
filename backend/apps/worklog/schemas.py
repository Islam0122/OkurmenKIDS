"""The form of every Team Lead report kind — one description used twice:
the API validates TeamLeadReport.data against it, and the LMS renders the
form from it (GET /api/v1/worklog/report-kinds/).

Field types: text, textarea, list (one item per line), date, number,
percent, score (1–5), select (one of `options`), multiselect, rows (a table
of `columns`). `links` say which of group / teacher / student / lesson the
report is about (with `required_links` that must be set); `period` says
whether the report covers one date ("date") or a range ("range").
Everything the LMS can compute goes to `metrics` instead (apps.worklog.metrics).
"""
from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError

from .models import ReportKind

SCORE_HELP = "1 — плохо, 5 — отлично"

LESSON_CRITERIA = [
    ("preparation", "Подготовка тренера"),
    ("structure", "Структура урока"),
    ("explanation", "Объяснение материала"),
    ("engagement", "Работа со студентами"),
    ("discipline", "Дисциплина"),
    ("practice", "Практическая часть"),
    ("homework", "Домашнее задание"),
    ("lms", "Использование LMS"),
]

STUDENT_PROBLEMS = [
    "Низкая посещаемость",
    "Низкие результаты",
    "Не выполняет ДЗ",
    "Проблемы с дисциплиной",
    "Не понимает материал",
    "Другая проблема",
]


def _f(key, label, type_="textarea", **extra):
    return {"key": key, "label": label, "type": type_, **extra}


DRAFT_SUBMITTED = [("draft", "Черновик"), ("submitted", "Сдан")]

REPORT_KINDS: dict[str, dict] = {
    ReportKind.DAILY: {
        "period": "date",
        "links": [],
        "description": "Конец рабочего дня: что сделано (записи журнала за день), проблемы, решения, план.",
        "statuses": DRAFT_SUBMITTED,
        "fields": [
            _f("working_hours", "Рабочее время", "text", placeholder="10:00–18:00"),
            _f("problems", "Проблемы", "list", required=True),
            _f("decisions", "Решения", "list", required=True),
            _f("plan_next_day", "План на следующий рабочий день", "list", required=True),
        ],
    },
    ReportKind.WEEKLY: {
        "period": "range",
        "links": [],
        "description": "Сводка недели. Группы, студенты, ДЗ, тесты и экзамены считаются LMS автоматически.",
        "statuses": DRAFT_SUBMITTED,
        "fields": [
            _f("trainers_internship", "Тренеров на стажировке", "number"),
            _f("trainers_probation", "Тренеров на испытательном сроке", "number"),
            _f("students_to_mentor", "Студентов передано ментору", "number"),
            _f("problem_groups", "Группы с проблемами", "list"),
            _f("summary", "Выводы недели", "textarea"),
            _f("next_week_plan", "План на следующую неделю", "list"),
        ],
    },
    ReportKind.MEETING: {
        "period": "date",
        "links": [],
        "description": "Еженедельная встреча с командой. Решения — задачи с ответственным, сроком и статусом.",
        "statuses": DRAFT_SUBMITTED,
        "fields": [
            _f("participants", "Участники", "list", required=True),
            _f("discussed", "Обсуждалось", "list", required=True),
            _f("notes", "Заметки", "textarea"),
        ],
    },
    ReportKind.LESSON_VISIT: {
        "period": "date",
        "links": ["lesson", "group", "teacher"],
        "required_links": ["teacher"],
        "description": "Проверка занятия: дата, время, группа, тренер, предмет и кабинет берутся из занятия.",
        "statuses": DRAFT_SUBMITTED,
        "fields": [
            *[_f(key, label, "score", required=True, help=SCORE_HELP) for key, label in LESSON_CRITERIA],
            _f("overall", "Оценка", "score", required=True, help=SCORE_HELP),
            _f("comments", "Комментарии"),
            _f("good", "Что хорошо", required=True),
            _f("improve", "Что необходимо улучшить", required=True),
            _f("recommendations", "Рекомендации", required=True),
            _f("next_check", "Повторная проверка", "date"),
        ],
    },
    ReportKind.TRAINER_REVIEW: {
        "period": "range",
        "links": ["teacher"],
        "required_links": ["teacher"],
        "description": "Динамика тренера за период. Посещаемость, ДЗ, результаты и KPI считаются LMS.",
        "statuses": DRAFT_SUBMITTED,
        "fields": [
            _f("lesson_quality", "Качество занятий", "score", help=SCORE_HELP),
            _f("journal_filling", "Заполнение журнала", "score", help=SCORE_HELP),
            _f("punctuality", "Пунктуальность", "score", help=SCORE_HELP),
            _f("student_feedback", "Обратная связь студентов", "score", help=SCORE_HELP),
            _f("problem_students_work", "Работа с проблемными студентами", "score", help=SCORE_HELP),
            _f("strengths", "Сильные стороны", required=True),
            _f("growth", "Зоны развития", required=True),
            _f("recommendations", "Рекомендации", required=True),
            _f("development_plan", "План развития", "list"),
            _f("next_check", "Следующая проверка", "date", required=True),
        ],
    },
    ReportKind.PROBLEM_STUDENT: {
        "period": "date",
        "links": ["student", "group", "teacher"],
        "required_links": ["student"],
        "description": "Отстающий студент: проблема, план действий, было / стало. Группа и тренер — из студента.",
        "statuses": [
            ("new", "Новая"), ("in_progress", "В работе"), ("improving", "Улучшение"),
            ("resolved", "Решено"), ("escalated", "Эскалировано"),
        ],
        "fields": [
            _f("problems", "Проблема", "multiselect", options=STUDENT_PROBLEMS, required=True),
            _f("problem_details", "Подробности"),
            _f("action", "Что необходимо сделать", required=True),
            _f("action_responsible", "Кто отвечает", "text", required=True),
            _f("action_deadline", "Срок", "date", required=True),
            _f("before", "Было", "text", placeholder="Посещаемость 55%"),
            _f("after", "Стало", "text", placeholder="Посещаемость 82%"),
        ],
    },
    ReportKind.INTERNSHIP: {
        "period": "range",
        "links": ["teacher"],
        "required_links": ["teacher"],
        "description": "Стажировка нового тренера: прогресс по дням и итог после 3 дней.",
        "statuses": DRAFT_SUBMITTED,
        "fields": [
            _f("days", "Дни стажировки", "rows", required=True, columns=[
                {"key": "date", "label": "Дата", "type": "date"},
                {"key": "learned", "label": "Что изучил", "type": "text"},
                {"key": "showed", "label": "Что показал", "type": "text"},
                {"key": "improve", "label": "Что необходимо улучшить", "type": "text"},
            ]),
            _f("it_knowledge", "Знание IT", "score", help=SCORE_HELP),
            _f("methodology", "Методика преподавания", "score", help=SCORE_HELP),
            _f("communication", "Коммуникация", "score", help=SCORE_HELP),
            _f("discipline", "Дисциплина", "score", help=SCORE_HELP),
            _f("independence", "Самостоятельность", "score", help=SCORE_HELP),
            _f("decision", "Решение", "select", options=["Рекомендуется к испытательному сроку", "Не рекомендуется"]),
            _f("decision_comment", "Комментарий к решению"),
        ],
    },
    ReportKind.PROBATION: {
        "period": "range",
        "links": ["teacher"],
        "required_links": ["teacher"],
        "description": "Итог испытательного срока (месяц). Посещаемость, ДЗ и результаты студентов считаются LMS.",
        "statuses": [("draft", "Черновик"), ("submitted", "Передан руководству")],
        "fields": [
            _f("lesson_quality", "Качество занятий", "score", required=True, help=SCORE_HELP),
            _f("discipline", "Дисциплина", "score", required=True, help=SCORE_HELP),
            _f("communication", "Коммуникация", "score", required=True, help=SCORE_HELP),
            _f("lms_work", "Работа с LMS", "score", required=True, help=SCORE_HELP),
            _f("strengths", "Сильные стороны", required=True),
            _f("problems", "Проблемы", required=True),
            _f("dynamics", "Динамика", required=True),
            _f("recommendations", "Рекомендации", required=True),
            _f("decision", "Решение Team Lead", "select", required=True,
               options=["Пройти испытательный срок", "Продлить испытательный срок", "Не рекомендовать"]),
        ],
    },
    ReportKind.MONTHLY: {
        "period": "range",
        "links": [],
        "description": "Итог месяца. Академия, качество, KPI и экзамены считаются LMS; мероприятия и выводы — вручную.",
        "statuses": DRAFT_SUBMITTED,
        "fields": [
            _f("hackathons", "Хакатоны", "number"),
            _f("trainer_events", "Мероприятия для тренеров", "number"),
            _f("main_problems", "Основные проблемы месяца", "list", required=True),
            _f("done", "Что было сделано", "list", required=True),
            _f("next_month_plan", "План на следующий месяц", "list", required=True),
        ],
    },
}


def kinds_payload() -> list[dict]:
    return [
        {
            "kind": kind.value,
            "label": kind.label,
            **{k: v for k, v in REPORT_KINDS[kind].items() if k != "statuses"},
            "statuses": [{"value": v, "label": label} for v, label in REPORT_KINDS[kind]["statuses"]],
            "required_links": REPORT_KINDS[kind].get("required_links", []),
        }
        for kind in ReportKind
    ]


def status_label(kind: str, status: str) -> str:
    return dict(REPORT_KINDS[kind]["statuses"]).get(status, status)


def _empty(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _clean_value(field: dict, value):
    """Normalized value or raises ValueError(message)."""
    kind = field["type"]
    if kind in ("text", "textarea"):
        if not isinstance(value, str):
            raise ValueError("Ожидается текст.")
        return value.strip()
    if kind == "list":
        if isinstance(value, str):
            value = value.splitlines()
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError("Ожидается список.")
        return [v.strip() for v in value if v.strip()]
    if kind == "date":
        try:
            return dt.date.fromisoformat(str(value)).isoformat()
        except ValueError:
            raise ValueError("Неверная дата.")
    if kind in ("number", "percent"):
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError("Ожидается число.")
        if number < 0 or (kind == "percent" and number > 100):
            raise ValueError("Недопустимое значение.")
        return int(number) if number.is_integer() else number
    if kind == "score":
        if value not in (1, 2, 3, 4, 5, "1", "2", "3", "4", "5"):
            raise ValueError("Оценка от 1 до 5.")
        return int(value)
    if kind == "select":
        if value not in field["options"]:
            raise ValueError("Выберите вариант из списка.")
        return value
    if kind == "multiselect":
        if not isinstance(value, list) or any(v not in field["options"] for v in value):
            raise ValueError("Выберите варианты из списка.")
        return list(dict.fromkeys(value))
    if kind == "rows":
        if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
            raise ValueError("Ожидается таблица.")
        rows = []
        for row in value:
            clean = {}
            for column in field["columns"]:
                cell = row.get(column["key"])
                if _empty(cell):
                    continue
                clean[column["key"]] = _clean_value(column, cell)
            if clean:
                rows.append(clean)
        return rows
    raise ValueError("Неизвестный тип поля.")


def clean_report_data(kind: str, data, *, require_complete: bool) -> dict:
    """Keep only the kind's fields, normalize them; required fields are
    enforced once the report is submitted (a draft may be incomplete)."""
    if not isinstance(data, dict):
        raise ValidationError({"data": ["Некорректные данные отчёта."]})
    errors, cleaned = {}, {}
    for field in REPORT_KINDS[kind]["fields"]:
        value = data.get(field["key"])
        if _empty(value):
            if require_complete and field.get("required"):
                errors[field["key"]] = ["Обязательное поле."]
            continue
        try:
            cleaned[field["key"]] = _clean_value(field, value)
        except ValueError as exc:
            errors[field["key"]] = [str(exc)]
            continue
        if require_complete and field.get("required") and _empty(cleaned[field["key"]]):
            errors[field["key"]] = ["Обязательное поле."]
    if errors:
        raise ValidationError(errors)  # field key → messages
    return cleaned
