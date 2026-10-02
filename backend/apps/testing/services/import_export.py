"""Import / export of tests and of one test's questions (CSV / XLSX).

File reading and writing reuse the shared helpers of
apps/users/import_export/formats.py. Every question goes through
services.questions.save_question, so a file is held to exactly the same
rules as the admin question editor and the REST API.

Import is row by row: valid rows are saved, invalid rows are reported with
their row number (1 = header) and nothing of them is written. An existing
test / question (same title, same question text, or the question id from an
export) is never duplicated: it is skipped, or updated only when the admin
explicitly allows it (``update_existing``).
"""
from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, QuerySet
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font

from apps.users.import_export.formats import build_export_response, read_numbered_rows
from apps.users.import_export.results import RowError
from apps.users.models import Subject

from ..models import ProgrammingLanguage, Question, QuestionType, Test, TestLevel, TestStatus
from . import questions as question_service
from .question_rules import CHOICE_TYPES, CodeTestData, OptionData, QuestionData

FORMATS = (("xlsx", "Excel (.xlsx)"), ("csv", "CSV (.csv)"))
EXPORT_SCOPES = (("all", "Все тесты"), ("selected", "Только выбранные"), ("filtered", "Только текущий фильтр"))
LIST_SEPARATOR = ";"
MIN_OPTION_COLUMNS = 4
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass
class ImportReport:
    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: list[RowError] = field(default_factory=list)  # already exist, not changed
    errors: list[RowError] = field(default_factory=list)

    @property
    def error_rows(self) -> int:
        return len(self.errors)


# ---------------------------------------------------------------------------
# Shared parsing
# ---------------------------------------------------------------------------

def _choice(value: str, choices, *, aliases: dict[str, str] | None = None) -> str | None:
    """A TextChoices value from its code or its Russian label (any case)."""
    value = (value or "").strip().casefold()
    if not value:
        return None
    for code, label in choices:
        if value in (str(code).casefold(), str(label).casefold()):
            return code
    return (aliases or {}).get(value)


def _int(value: str, label: str, errors: list[str], *, low: int | None = None, high: int | None = None) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        number = int(float(value.replace(",", ".")))
    except ValueError:
        errors.append(f"«{label}» должно быть целым числом, получено «{value}».")
        return None
    if (low is not None and number < low) or (high is not None and number > high):
        errors.append(f"«{label}» должно быть от {low} до {high}." if high is not None else f"«{label}» должно быть не меньше {low}.")
        return None
    return number


def _split(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(LIST_SEPARATOR) if part.strip()]


def _messages(error: ValidationError, labels: dict[str, str]) -> list[str]:
    if hasattr(error, "error_dict"):
        return [
            message if key in ("__all__", "options", "correct_answers", "code_tests") else f"{labels.get(key, key)}: {message}"
            for key, messages in error.message_dict.items()
            for message in messages
        ]
    return list(error.messages)


def _read(uploaded_file) -> list[tuple[int, dict[str, str]]]:
    """(line number in the file, row keyed by lower-case header — ``Title``
    and ``title`` both work)."""
    return [
        (number, {(k or "").strip().casefold(): v for k, v in row.items()})
        for number, row in read_numbered_rows(uploaded_file)
    ]


def _xlsx_response(sheets: list[tuple[str, list[str], list[list]]], filename: str) -> HttpResponse:
    """A workbook of several sheets: [(title, header, rows)]. The first sheet
    is the one imports read."""
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, header, rows in sheets:
        sheet = workbook.create_sheet(title)
        sheet.append(header)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for row in rows:
            sheet.append(row)
        for column in sheet.columns:
            width = max(len(str(cell.value or "")) for cell in column)
            sheet.column_dimensions[column[0].column_letter].width = min(max(width + 2, 10), 60)
    buffer = io.BytesIO()
    workbook.save(buffer)
    response = HttpResponse(buffer.getvalue(), content_type=XLSX_CONTENT_TYPE)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _stamp() -> str:
    return timezone.now().strftime("%Y%m%d_%H%M%S")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

TEST_COLUMNS = [
    # (key, importable, description for the template's help sheet)
    ("title", True, "Название теста. Обязательно, уникально."),
    ("subject", True, "Название предмета (как в разделе «Предметы»). Можно оставить пустым."),
    ("level", True, "Уровень: easy / medium / hard или Начальный / Средний / Продвинутый. По умолчанию medium."),
    ("status", True, "Статус: draft / active / archived или Черновик / Активен / Архив. По умолчанию draft."),
    ("description", True, "Описание."),
    ("image_url", True, "Ссылка на изображение (http:// или https://). Файл не загружается."),
    ("time_limit_minutes", True, "Ограничение времени в минутах; пусто — без ограничения."),
    ("max_attempts", True, "Попыток на студента; пусто — без ограничения."),
    ("passing_score", True, "Проходной балл, % (0–100). По умолчанию 60."),
    ("questions_count", False, "Только экспорт: количество вопросов."),
    ("attempts_count", False, "Только экспорт: количество попыток."),
    ("created_at", False, "Только экспорт: дата создания."),
    ("updated_at", False, "Только экспорт: дата обновления."),
]
TEST_IMPORT_KEYS = [key for key, importable, _ in TEST_COLUMNS if importable]
TEST_LABELS = {
    "title": "Название", "subject": "Предмет", "level": "Уровень", "status": "Статус",
    "description": "Описание", "image_url": "Изображение", "time_limit_minutes": "Время",
    "max_attempts": "Попытки", "passing_score": "Проходной балл",
}


def export_tests(tests: QuerySet, fmt: str) -> HttpResponse:
    tests = tests.select_related("subject").annotate(
        _questions=Count("questions", distinct=True), _attempts=Count("sessions__attempts", distinct=True),
    )
    rows = [
        {
            "title": t.title,
            "subject": t.subject.name if t.subject_id else "",
            "level": t.level,
            "status": t.status,
            "description": t.description,
            "image_url": t.image_url,
            "time_limit_minutes": t.time_limit_minutes or "",
            "max_attempts": t.max_attempts or "",
            "passing_score": t.passing_score,
            "questions_count": t._questions,
            "attempts_count": t._attempts,
            "created_at": timezone.localtime(t.created_at).strftime("%Y-%m-%d %H:%M"),
            "updated_at": timezone.localtime(t.updated_at).strftime("%Y-%m-%d %H:%M"),
        }
        for t in tests
    ]
    return build_export_response(rows, [key for key, _, _ in TEST_COLUMNS], fmt, "tests")


def tests_template(fmt: str) -> HttpResponse:
    if fmt != "xlsx":
        return build_export_response([], TEST_IMPORT_KEYS, fmt, "tests_import_template")
    example = [
        ["Python Basics", "Python", "easy", "draft", "Основы синтаксиса", "https://example.com/python.png", "30", "2", "60"],
        ["HTML и CSS", "", "medium", "draft", "", "", "", "", "70"],
    ]
    help_rows = [[key, text] for key, importable, text in TEST_COLUMNS if importable]
    return _xlsx_response(
        [("Тесты", TEST_IMPORT_KEYS, []), ("Пример", TEST_IMPORT_KEYS, example), ("Справка", ["Колонка", "Описание"], help_rows)],
        f"tests_import_template_{_stamp()}.xlsx",
    )


def import_tests(uploaded_file, *, update_existing: bool = False) -> ImportReport:
    rows = _read(uploaded_file)
    report = ImportReport(total=len(rows))
    if rows and "title" not in rows[0][1]:
        report.errors.append(RowError(1, ["В файле нет колонки «title». Скачайте шаблон и заполните его."]))
        return report
    subjects = {s.name.casefold(): s for s in Subject.objects.all()}
    seen: dict[str, int] = {}
    for number, raw in rows:
        errors: list[str] = []
        title = (raw.get("title") or "").strip()
        if not title:
            report.errors.append(RowError(number, ["Не указано название теста (title)."]))
            continue
        key = title.casefold()
        if key in seen:
            report.errors.append(RowError(number, [f"Тест «{title}» уже встречается в файле (строка {seen[key]})."]))
            continue
        seen[key] = number

        existing = Test.objects.filter(title__iexact=title).first()
        if existing and not update_existing:
            report.skipped.append(RowError(number, [f"Тест «{existing.title}» уже существует — пропущен."]))
            continue
        test = existing or Test(title=title)

        if "subject" in raw:
            name = (raw.get("subject") or "").strip()
            if not name:
                test.subject = None
            elif name.casefold() in subjects:
                test.subject = subjects[name.casefold()]
            else:
                errors.append(f"Предмет «{name}» не найден.")
        for name, choices in (("level", TestLevel.choices), ("status", TestStatus.choices)):
            if (raw.get(name) or "").strip():
                value = _choice(raw[name], choices)
                if value is None:
                    errors.append(f"Неизвестное значение «{TEST_LABELS[name]}»: «{raw[name]}».")
                else:
                    setattr(test, name, value)
        for name in ("description", "image_url"):
            if name in raw:
                setattr(test, name, (raw.get(name) or "").strip())
        for name in ("time_limit_minutes", "max_attempts"):  # ranges: the model's validators (full_clean)
            if name in raw:
                setattr(test, name, _int(raw.get(name), TEST_LABELS[name], errors, low=1))
        if (raw.get("passing_score") or "").strip():
            score = _int(raw["passing_score"], TEST_LABELS["passing_score"], errors, low=0, high=100)
            if score is not None:
                test.passing_score = score
        if test.status == TestStatus.ACTIVE and not (existing and existing.questions.exists()):
            errors.append("Нельзя импортировать тест сразу активным: в нём ещё нет вопросов. Используйте draft.")

        if not errors:
            try:
                test.full_clean(validate_unique=False)
            except ValidationError as error:
                errors.extend(_messages(error, TEST_LABELS))
        if errors:
            report.errors.append(RowError(number, errors))
            continue
        test.save()
        if existing:
            report.updated += 1
        else:
            report.created += 1
    return report


# ---------------------------------------------------------------------------
# Questions of one test
# ---------------------------------------------------------------------------

QUESTION_HELP = [
    ("test", "Название теста. Можно оставить пустым; если заполнено — должно совпадать с тестом, в который импортируете."),
    ("question", "ID вопроса из экспорта. Пусто — новый вопрос; ID — обновить этот вопрос (нужна галочка «Обновлять существующие»)."),
    ("question_type", "single_choice / multiple_choice / text / code (или: Один вариант / Несколько вариантов / Текстовый ответ / Код)."),
    ("text", "Текст вопроса. Обязательно."),
    ("image_url", "Ссылка на изображение (http:// или https://). Необязательно."),
    ("option_1 … option_N", "Варианты ответа для single_choice / multiple_choice (минимум два). Можно добавить option_5, option_6 …"),
    ("correct_answer", "single_choice: номер варианта (1) или его текст. multiple_choice: номера через «;» (1;3). "
                       "text: правильный ответ, допустимые варианты через «;». code: ожидаемый вывод (необязательно)."),
    ("points", "Баллы за вопрос, 1–100. По умолчанию 1."),
    ("explanation", "Пояснение к ответу (для преподавателя, студенту во время теста не показывается)."),
    ("order", "Порядковый номер вопроса в тесте. Пусто — в конец."),
    ("language", "Только для code: python / javascript / typescript / html / css. Обязательно для code."),
    ("hint", "Подсказка, которую студент видит во время теста. Необязательно."),
]
QUESTION_TYPE_ALIASES = {
    "single": QuestionType.SINGLE_CHOICE, "radio": QuestionType.SINGLE_CHOICE,
    "multiple": QuestionType.MULTIPLE_CHOICE, "checkbox": QuestionType.MULTIPLE_CHOICE,
    "текст": QuestionType.TEXT, "код": QuestionType.CODE,
}
QUESTION_LABELS = {
    "text": "Текст вопроса", "image_url": "Изображение", "language": "Язык", "question_type": "Тип вопроса",
    "points": "Баллы", "hint": "Подсказка",
}
_OPTION_RE = re.compile(r"^option_(\d+)$")


def question_columns(option_count: int = MIN_OPTION_COLUMNS) -> list[str]:
    options = [f"option_{i}" for i in range(1, max(option_count, MIN_OPTION_COLUMNS) + 1)]
    return ["test", "question", "question_type", "text", "image_url", *options,
            "correct_answer", "points", "explanation", "order", "language", "hint"]


def _question_row(test: Test, question: Question, number: int) -> dict:
    options = list(question.options.all())
    row = {
        "test": test.title,
        "question": str(question.pk),
        "question_type": question.question_type,
        "text": question.text,
        "image_url": question.image_url,
        "points": question.points,
        "explanation": (question.metadata or {}).get("explanation", ""),
        "order": number,
        "language": question.language,
        "hint": question.hint,
    }
    for index, option in enumerate(options, start=1):
        row[f"option_{index}"] = option.text
    if question.question_type in CHOICE_TYPES:
        row["correct_answer"] = LIST_SEPARATOR.join(str(i) for i, o in enumerate(options, start=1) if o.is_correct)
    elif question.question_type == QuestionType.TEXT:
        row["correct_answer"] = LIST_SEPARATOR.join(question.correct_answers or [])
    else:
        tests = question.code_tests or []
        row["correct_answer"] = tests[0].get("expected_output", "") if tests else ""
    return row


def export_questions(test: Test, fmt: str) -> HttpResponse:
    questions = list(test.questions.prefetch_related("options").order_by("order", "created_at"))
    option_count = max([q.options.count() for q in questions] + [MIN_OPTION_COLUMNS])
    rows = [_question_row(test, q, n) for n, q in enumerate(questions, start=1)]
    return build_export_response(rows, question_columns(option_count), fmt, f"questions_{test.pk.hex[:8]}")


def questions_template(fmt: str, test: Test | None = None) -> HttpResponse:
    columns = question_columns()
    if fmt != "xlsx":
        return build_export_response([], columns, fmt, "questions_import_template")
    title = test.title if test else "Python Basics"
    example = [
        [title, "", "single_choice", "Что выведет print(2 ** 3)?", "", "6", "8", "9", "5", "2", "1", "2 ** 3 = 8", "1", "", ""],
        [title, "", "multiple_choice", "Какие типы изменяемые?", "", "list", "tuple", "dict", "str", "1;3", "2", "", "2", "", ""],
        [title, "", "text", "Как называется функция вывода?", "", "", "", "", "", "print;print()", "1", "", "3", "", ""],
        [title, "", "code", "Напишите функцию sum(a, b).", "https://example.com/task.png", "", "", "", "", "", "3", "", "4", "python", "Используйте return"],
    ]
    return _xlsx_response(
        [("Вопросы", columns, []), ("Пример", columns, example), ("Справка", ["Колонка", "Описание"], [list(r) for r in QUESTION_HELP])],
        f"questions_import_template_{_stamp()}.xlsx",
    )


def _correct_options(raw: str, options: list[str], qtype: str, errors: list[str]) -> set[int]:
    """`2`, `1;3` or option texts → 0-based indexes of the correct options."""
    tokens = _split(raw)
    if len(tokens) == 1 and "," in tokens[0] and all(p.strip().isdigit() for p in tokens[0].split(",")):
        tokens = [p.strip() for p in tokens[0].split(",")]
    if not tokens:
        errors.append("Укажите правильный ответ (correct_answer): номер варианта, например 1.")
        return set()
    texts = [o.casefold() for o in options]
    correct: set[int] = set()
    for token in tokens:
        if token.isdigit():
            index = int(token) - 1
            if not 0 <= index < len(options) or not options[index]:
                errors.append(f"correct_answer: варианта №{token} нет.")
                continue
        elif token.casefold() in texts:
            index = texts.index(token.casefold())
        else:
            errors.append(f"correct_answer: «{token}» не совпадает ни с одним вариантом.")
            continue
        correct.add(index)
    if qtype == QuestionType.SINGLE_CHOICE and len(correct) > 1:
        errors.append("Для single_choice правильным может быть только один вариант.")
    return correct


def import_questions(test: Test, uploaded_file, *, update_existing: bool = False) -> ImportReport:
    rows = _read(uploaded_file)
    report = ImportReport(total=len(rows))
    if rows and not {"text", "question_type"} <= set(rows[0][1]):
        report.errors.append(RowError(1, ["В файле нет колонок «question_type» и «text». Скачайте шаблон и заполните его."]))
        return report
    option_keys = sorted(
        (key for key in (rows[0][1] if rows else {}) if _OPTION_RE.match(key)),
        key=lambda k: int(_OPTION_RE.match(k).group(1)),
    )
    seen: dict[str, int] = {}
    ordered: list[tuple[int, Question]] = []
    for number, raw in rows:
        errors: list[str] = []
        file_test = (raw.get("test") or "").strip()
        if file_test and file_test.casefold() != test.title.casefold():
            report.errors.append(RowError(number, [f"Строка относится к тесту «{file_test}», а импорт идёт в «{test.title}»."]))
            continue
        text = (raw.get("text") or "").strip()
        qtype = _choice(raw.get("question_type"), QuestionType.choices, aliases=QUESTION_TYPE_ALIASES)
        if qtype is None:
            errors.append(
                f"Неизвестный тип вопроса «{raw.get('question_type', '')}»: используйте single_choice, multiple_choice, text или code."
                if (raw.get("question_type") or "").strip() else "Не указан тип вопроса (question_type)."
            )
        if not text:
            errors.append("Не указан текст вопроса (text).")
        elif text.casefold() in seen:
            errors.append(f"Такой вопрос уже есть в файле (строка {seen[text.casefold()]}).")
        if errors:
            report.errors.append(RowError(number, errors))
            continue
        seen[text.casefold()] = number

        existing = None
        question_id = (raw.get("question") or "").strip()
        if question_id:
            try:
                existing = test.questions.filter(pk=uuid.UUID(question_id)).first()
            except ValueError:
                existing = None
            if existing is None:
                report.errors.append(RowError(number, [f"Вопрос с ID «{question_id}» не найден в этом тесте. Оставьте колонку question пустой, чтобы создать новый."]))
                continue
        same_text = test.questions.filter(text=text).exclude(pk=getattr(existing, "pk", None)).first()
        if existing is None and same_text is not None:
            existing = same_text
        elif same_text is not None:
            report.errors.append(RowError(number, ["В тесте уже есть другой вопрос с таким текстом."]))
            continue
        if existing and not update_existing:
            report.skipped.append(RowError(number, [f"Вопрос «{existing.text[:80]}» уже есть в тесте — пропущен."]))
            continue

        options = [(raw.get(key) or "").strip() for key in option_keys]
        while options and not options[-1]:
            options.pop()
        data = QuestionData(question_type=qtype, text=text, image_url=(raw.get("image_url") or "").strip())
        answer = (raw.get("correct_answer") or "").strip()
        if qtype in CHOICE_TYPES:
            correct = _correct_options(answer, options, qtype, errors)
            old_images = {o.text.casefold(): o.image_url for o in existing.options.all()} if existing else {}
            data.options = [
                OptionData(text, i in correct, image_url=old_images.get(text.casefold(), ""))
                for i, text in enumerate(options) if text
            ]
        elif options:
            errors.append("У вопросов text и code нет вариантов ответа — очистите колонки option_N.")
        if qtype == QuestionType.TEXT:
            data.correct_answers = _split(answer)
        if qtype == QuestionType.CODE:
            data.language = _choice(raw.get("language"), [c for c in ProgrammingLanguage.choices if c[0]]) or ""
            if (raw.get("language") or "").strip() and not data.language:
                errors.append(f"Неизвестный язык «{raw['language']}»: python, javascript, typescript, html или css.")
            old_tests = (existing.code_tests or []) if existing and existing.question_type == QuestionType.CODE else []
            if old_tests and old_tests[0].get("expected_output", "") == answer:
                data.code_tests = [CodeTestData(t.get("input", ""), t.get("expected_output", "")) for t in old_tests]
            elif answer:
                data.code_tests = [CodeTestData("", answer)]
        points = _int(raw.get("points"), "Баллы", errors, low=1, high=100)
        order = _int(raw.get("order"), "Порядок", errors, low=1)
        if errors:
            report.errors.append(RowError(number, errors))
            continue

        extra = {"points": points if points is not None else (existing.points if existing else 1)}
        if "hint" in raw:
            extra["hint"] = (raw.get("hint") or "").strip()
        try:
            with transaction.atomic():
                question = question_service.save_question(test, data, question=existing, **extra)
                metadata = dict(question.metadata or {})
                explanation = (raw.get("explanation") or "").strip()
                if "explanation" in raw and metadata.get("explanation", "") != explanation:
                    if explanation:
                        metadata["explanation"] = explanation
                    else:
                        metadata.pop("explanation", None)
                    question.metadata = metadata
                    question.save(update_fields=["metadata"])
        except ValidationError as error:
            report.errors.append(RowError(number, _messages(error, QUESTION_LABELS)))
            continue
        if order is not None:
            ordered.append((order, question))
        if existing:
            report.updated += 1
        else:
            report.created += 1

    if ordered:
        _apply_file_order(test, ordered)
    if report.created or report.updated:
        Test.objects.filter(pk=test.pk).update(updated_at=timezone.now())
    return report


def _apply_file_order(test: Test, ordered: list[tuple[int, Question]]) -> None:
    """Put the questions with an ``order`` from the file at that position
    (1-based); every other question keeps its relative order."""
    placed = {q.pk: position for position, q in ordered}
    rest = [q for q in test.questions.order_by("order", "created_at") if q.pk not in placed]
    result: list[Question] = []
    for position, question in sorted(ordered, key=lambda item: item[0]):
        while len(result) < position - 1 and rest:
            result.append(rest.pop(0))
        result.append(question)
    result.extend(rest)
    for position, question in enumerate(result, start=1):
        question.order = position
    Question.objects.bulk_update(result, ["order"])
