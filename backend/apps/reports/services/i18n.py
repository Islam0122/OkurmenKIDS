"""Russian / Kyrgyz wording of every fixed label in reports (images and texts).

Numbers are formatted here too: a decimal comma in both languages, and a
missing value is always the «no data» label — never «0%».
"""
from __future__ import annotations

import datetime as dt

LANGUAGES = ("ru", "ky")

LABELS: dict[str, dict[str, str]] = {
    "ru": {
        "brand": "OkurmenKIDS",
        "title_group": "Отчёт по студентам",
        "title_student": "Индивидуальный отчёт",
        "group": "Группа",
        "course": "Курс",
        "period": "Период",
        "lessons": "Занятий",
        "trainer": "Тренер",
        "no_data": "Нет данных",
        "active_students": "Активные студенты",
        "conducted_lessons": "Проведено занятий",
        "attendance": "Посещаемость",
        "homework": "Домашние задания",
        "average_score": "Средний балл",
        "tests": "Тесты",
        "of_planned": "из {planned} запланированных",
        "absences": "пропусков: {n}",
        "hw_done_of": "{done} из {due} выполнено",
        "scores_count": "оценок: {n}",
        "tests_count": "попыток: {n}",
        "excellent_results": "с отличными результатами: {n}",
        "col_no": "№",
        "col_student": "Студент",
        "col_lessons": "Занятия",
        "col_attendance": "Посещаемость",
        "col_homework": "ДЗ",
        "col_score": "Ср. балл",
        "col_tests": "Тесты",
        "col_status": "Статус",
        "attended_of": "{attended} из {held}",
        "strengths": "Наши сильные стороны",
        "attention": "На что стоит обратить внимание",
        "parents": "Рекомендации родителям",
        "strengths_student": "Сильные стороны",
        "comparison": "Сравнение с прошлым периодом",
        "previous": "Прошлый период",
        "current": "Этот период",
        "change": "Изменение",
        "test_results": "Результаты тестов",
        "passed": "сдан",
        "failed": "не сдан",
        "more_tests": "и ещё {n}",
        "page": "Страница {page} из {pages}",
        "generated": "Сформировано {date}",
        "continued": "продолжение",
        "students_word": "студентов",
        "status_excellent": "Отлично",
        "status_good": "Хорошо",
        "status_attention": "Нужно внимание",
        "status_support": "Требуется поддержка",
        "status_no_data": "Нет данных",
        "pp": "п.п.",
        "lessons_attended": "Посещено занятий",
    },
    "ky": {
        "brand": "OkurmenKIDS",
        "title_group": "Окуучулар боюнча отчёт",
        "title_student": "Жеке отчёт",
        "group": "Топ",
        "course": "Курс",
        "period": "Мезгил",
        "lessons": "Сабак",
        "trainer": "Машыктыруучу",
        "no_data": "Маалымат жок",
        "active_students": "Активдүү окуучулар",
        "conducted_lessons": "Өткөрүлгөн сабактар",
        "attendance": "Катышуу",
        "homework": "Үй тапшырмалары",
        "average_score": "Орточо баа",
        "tests": "Тесттер",
        "of_planned": "пландалганы: {planned}",
        "absences": "калтырылган: {n}",
        "hw_done_of": "{due} ичинен {done} аткарылды",
        "scores_count": "баалар: {n}",
        "tests_count": "аракеттер: {n}",
        "excellent_results": "эң жакшы жыйынтык: {n}",
        "col_no": "№",
        "col_student": "Окуучу",
        "col_lessons": "Сабактар",
        "col_attendance": "Катышуу",
        "col_homework": "Үй тапш.",
        "col_score": "Орт. баа",
        "col_tests": "Тесттер",
        "col_status": "Абалы",
        "attended_of": "{held} ичинен {attended}",
        "strengths": "Биздин күчтүү жактарыбыз",
        "attention": "Эмнеге көңүл буруу керек",
        "parents": "Ата-энелерге сунуштар",
        "strengths_student": "Күчтүү жактары",
        "comparison": "Мурунку мезгил менен салыштыруу",
        "previous": "Мурунку мезгил",
        "current": "Бул мезгил",
        "change": "Өзгөрүү",
        "test_results": "Тест жыйынтыктары",
        "passed": "өттү",
        "failed": "өткөн жок",
        "more_tests": "дагы {n}",
        "page": "{pages} барактын {page}-барагы",
        "generated": "Түзүлгөн күнү: {date}",
        "continued": "уландысы",
        "students_word": "окуучу",
        "status_excellent": "Эң жакшы",
        "status_good": "Жакшы",
        "status_attention": "Көңүл буруу керек",
        "status_support": "Колдоо керек",
        "status_no_data": "Маалымат жок",
        "pp": "п.п.",
        "lessons_attended": "Катышкан сабактар",
    },
}


def labels(language: str) -> dict[str, str]:
    return LABELS[language if language in LABELS else "ru"]


def number(value: float | None, digits: int = 1) -> str | None:
    if value is None:
        return None
    rounded = round(float(value), digits)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.{digits}f}".replace(".", ",")


def percent(value: float | None, language: str) -> str:
    text = number(value, 0 if value is not None and float(value).is_integer() else 1)
    return f"{text}%" if text is not None else labels(language)["no_data"]


def score(value: float | None, language: str) -> str:
    text = number(value)
    return text if text is not None else labels(language)["no_data"]


def signed(value: float | None, unit: str = "") -> str | None:
    if value is None:
        return None
    text = number(abs(value))
    sign = "+" if value > 0 else ("−" if value < 0 else "±")
    return f"{sign}{text}{unit}"


def date(value: str | dt.date) -> str:
    if isinstance(value, str):
        value = dt.date.fromisoformat(value)
    return value.strftime("%d.%m.%Y")


def period(start: str, end: str) -> str:
    return date(start) if start == end else f"{date(start)} — {date(end)}"
