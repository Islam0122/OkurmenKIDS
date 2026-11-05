"""WhatsApp messages for parents, in Russian or Kyrgyz.

Templates + the calculation snapshot only — no AI. ``*bold*`` is WhatsApp
markup. The trainer edits the text in the LMS before copying; nothing is
sent from the LMS.

* ``group_message`` — the message that goes with the group report image
  into the parents' chat: what the report contains, the group's key figures
  and (optionally) the recommendations. No student is named in it.
* ``student_message`` — a personal message to one student's parents with
  that student's own figures, progress and recommendations.
"""
from __future__ import annotations

from . import i18n, recommendations

WORDS = {
    "ru": {
        "greeting": "Уважаемые родители! 🌟",
        "intro_monthly": "Подготовили ежемесячный отчёт по обучению учеников группы *{group}* за период {period}.",
        "intro": "Подготовили отчёт по обучению учеников группы *{group}* за период {period}.",
        "contents": "В отчёте представлены:",
        "items": ["Посещаемость", "Выполнение домашних заданий", "Средние оценки", "Результаты тестирования"],
        "item_progress": "Индивидуальный прогресс",
        "summary": "📊 *Коротко о группе:*",
        "conducted": "Проведено занятий: {n}",
        "attendance": "Средняя посещаемость: {value}",
        "homework": "Выполнение домашних заданий: {value}",
        "score": "Средний балл: {value}",
        "tests": "Результаты тестов: {value}",
        "parents": "💡 *Рекомендации родителям:*",
        "thanks": "Благодарим вас за сотрудничество и поддержку! 🙏",
        "signature": "С уважением, команда OkurmenKIDS",
        "student_intro": "Подготовили индивидуальный отчёт по обучению: *{name}*, группа {group}.",
        "student_period": "Период: {period}",
        "s_attendance": "📅 Посещаемость: {value}",
        "s_attendance_detail": "{attended} из {held} занятий",
        "s_homework": "📚 Домашние задания: {value}",
        "s_homework_detail": "{done} из {due}",
        "s_score": "⭐ Средний балл: {value}",
        "s_tests": "📝 Тесты: {value}",
        "s_tests_detail": "попыток: {n}",
        "progress": "📈 *По сравнению с прошлым периодом:*",
        "progress_attendance": "посещаемость {value}",
        "progress_homework": "домашние задания {value}",
        "progress_score": "средний балл {value}",
        "progress_tests": "тесты {value}",
        "strengths": "💪 *Сильные стороны:*",
        "attention": "👀 *На что обратить внимание:*",
        "student_thanks": "Спасибо за сотрудничество! Если у вас есть вопросы — пишите, будем рады ответить. 🙏",
    },
    "ky": {
        "greeting": "Саламатсыздарбы, урматтуу ата-энелер! 🌟",
        "intro_monthly": "*{group}* тобунун окуучуларынын {period} мезгилиндеги окуусу боюнча айлык отчётту даярдадык.",
        "intro": "*{group}* тобунун окуучуларынын {period} мезгилиндеги окуусу боюнча отчётту даярдадык.",
        "contents": "Отчётто төмөнкүлөр көрсөтүлгөн:",
        "items": ["Катышуу", "Үй тапшырмаларын аткаруу", "Орточо баалар", "Тестирлөөнүн жыйынтыктары"],
        "item_progress": "Ар бир окуучунун жеке өсүшү",
        "summary": "📊 *Топ боюнча кыскача:*",
        "conducted": "Өткөрүлгөн сабактар: {n}",
        "attendance": "Орточо катышуу: {value}",
        "homework": "Үй тапшырмаларын аткаруу: {value}",
        "score": "Орточо баа: {value}",
        "tests": "Тест жыйынтыктары: {value}",
        "parents": "💡 *Ата-энелерге сунуштар:*",
        "thanks": "Кызматташтыгыңыз жана колдооңуз үчүн чоң рахмат! 🙏",
        "signature": "Урматтоо менен, OkurmenKIDS командасы",
        "student_intro": "Окуу боюнча жеке отчётту даярдадык: *{name}*, {group} тобу.",
        "student_period": "Мезгил: {period}",
        "s_attendance": "📅 Катышуу: {value}",
        "s_attendance_detail": "{held} сабактын {attended}",
        "s_homework": "📚 Үй тапшырмалары: {value}",
        "s_homework_detail": "{due} ичинен {done}",
        "s_score": "⭐ Орточо баа: {value}",
        "s_tests": "📝 Тесттер: {value}",
        "s_tests_detail": "аракеттер: {n}",
        "progress": "📈 *Мурунку мезгил менен салыштырганда:*",
        "progress_attendance": "катышуу {value}",
        "progress_homework": "үй тапшырмалары {value}",
        "progress_score": "орточо баа {value}",
        "progress_tests": "тесттер {value}",
        "strengths": "💪 *Күчтүү жактары:*",
        "attention": "👀 *Эмнеге көңүл буруу керек:*",
        "student_thanks": "Кызматташтыгыңыз үчүн рахмат! Суроолоруңуз болсо, жазыңыз — жооп берүүгө кубанычтабыз. 🙏",
    },
}


def _bullets(items: list[str]) -> list[str]:
    return [f"• {item}" for item in items]


def _with_detail(value: str, detail: str | None) -> str:
    return f"{value} ({detail})" if detail else value


def group_message(snapshot: dict, *, language: str, options: dict) -> str:
    words = WORDS[language]
    stats = snapshot["group_stats"]
    period = i18n.period(snapshot["period"]["start"], snapshot["period"]["end"])
    intro = words["intro_monthly" if snapshot["period"].get("monthly") else "intro"]
    items = list(words["items"])
    if options.get("include_table", True):
        items.append(words["item_progress"])

    blocks = [
        [words["greeting"]],
        [intro.format(group=snapshot["group"]["name"], period=period)],
        [words["contents"], *_bullets(items)],
    ]
    if options.get("include_group_stats", True):
        blocks.append([words["summary"], *_bullets([
            words["conducted"].format(n=stats["conducted_lessons"]),
            words["attendance"].format(value=i18n.percent(stats["attendance_rate"], language)),
            words["homework"].format(value=i18n.percent(stats["homework_rate"], language)),
            words["score"].format(value=_score(stats["average_score"], language)),
            words["tests"].format(value=i18n.percent(stats["test_average"], language)),
        ])])
    if options.get("include_recommendations", True):
        facts = recommendations.facts_for_group(snapshot, include_comparison=options.get("include_comparison", True))
        advice = recommendations.build(facts, scope="group", language=language)["parents"]
        blocks.append([words["parents"], *_bullets([item["text"] for item in advice])])
    blocks.append([words["thanks"], words["signature"]])
    return "\n\n".join("\n".join(lines) for lines in blocks)


def _score(value: float | None, language: str) -> str:
    text = i18n.number(value)
    return f"{text} / 10" if text is not None else i18n.labels(language)["no_data"]


def _progress_lines(entry: dict, language: str) -> list[str]:
    words = WORDS[language]
    lines = []
    for metric, key, unit in (
        ("attendance_rate", "progress_attendance", " п.п."),
        ("homework_rate", "progress_homework", " п.п."),
        ("average_score", "progress_score", ""),
        ("test_average", "progress_tests", " п.п."),
    ):
        change = entry["comparison"][metric]["change"]
        if change is not None:
            lines.append(words[key].format(value=i18n.signed(change, unit)))
    return lines


def student_message(snapshot: dict, entry: dict, *, language: str, options: dict) -> str:
    words = WORDS[language]
    no_data = i18n.labels(language)["no_data"]
    period = i18n.period(snapshot["period"]["start"], snapshot["period"]["end"])

    attendance = _with_detail(
        i18n.percent(entry["attendance_rate"], language),
        words["s_attendance_detail"].format(attended=entry["attended"], held=entry["attendance_marked"])
        if entry["attendance_rate"] is not None else None,
    )
    homework = _with_detail(
        i18n.percent(entry["homework_rate"], language),
        words["s_homework_detail"].format(done=entry["homework_done"], due=entry["homework_due"])
        if entry["homework_rate"] is not None else None,
    )
    tests = _with_detail(
        i18n.percent(entry["test_average"], language),
        words["s_tests_detail"].format(n=entry["tests_count"]) if entry["test_average"] is not None else None,
    )
    blocks = [
        [words["greeting"]],
        [
            words["student_intro"].format(name=entry["name"], group=snapshot["group"]["name"]),
            words["student_period"].format(period=period),
        ],
        [
            words["s_attendance"].format(value=attendance),
            words["s_homework"].format(value=homework),
            words["s_score"].format(value=_score(entry["average_score"], language) if entry["average_score"] is not None else no_data),
            words["s_tests"].format(value=tests),
        ],
    ]
    include_comparison = options.get("include_comparison", True)
    if include_comparison:
        progress = _progress_lines(entry, language)
        if progress:
            blocks.append([words["progress"], *_bullets(progress)])
    if options.get("include_recommendations", True):
        sections = recommendations.build(
            recommendations.facts_for_student(entry, include_comparison=include_comparison),
            scope="student", language=language,
        )
        blocks.append([words["strengths"], *_bullets([item["text"] for item in sections["strengths"]])])
        blocks.append([words["attention"], *_bullets([item["text"] for item in sections["attention"]])])
        blocks.append([words["parents"], *_bullets([item["text"] for item in sections["parents"]])])
    blocks.append([words["student_thanks"], words["signature"]])
    return "\n\n".join("\n".join(lines) for lines in blocks)


def student_messages(snapshot: dict, *, language: str, options: dict) -> dict[str, str]:
    return {
        str(entry["id"]): student_message(snapshot, entry, language=language, options=options)
        for entry in snapshot["students"]
    }
