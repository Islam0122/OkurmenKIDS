"""Rule-based recommendation engine (no AI, no external services).

Every statement is produced by an explicit rule over the calculated figures
of services.analytics: a rule fires only when its metric *has data* and
meets the threshold, so a missing metric never produces a positive or a
negative statement. Three sections, each in Russian and Kyrgyz:

    strengths   — «Сильные стороны»
    attention   — «На что стоит обратить внимание»
    parents     — «Рекомендации родителям»

    recommendations.build(facts_for_student(entry), scope="student", language="ky")
"""
from __future__ import annotations

import dataclasses
from collections.abc import Callable

from . import i18n

SECTIONS = ("strengths", "attention", "parents")
MAX_ITEMS = 4

Facts = dict[str, float | int | str | None]


@dataclasses.dataclass(frozen=True)
class Rule:
    key: str
    section: str
    when: Callable[[Facts], bool]
    ru: str
    ky: str
    scopes: tuple[str, ...] = ("student", "group")


def _has(facts: Facts, name: str) -> bool:
    return facts.get(name) is not None


def _at_least(name: str, threshold: float) -> Callable[[Facts], bool]:
    return lambda f: _has(f, name) and f[name] >= threshold


def _below(name: str, threshold: float) -> Callable[[Facts], bool]:
    return lambda f: _has(f, name) and f[name] < threshold


def _between(name: str, low: float, high: float) -> Callable[[Facts], bool]:
    return lambda f: _has(f, name) and low <= f[name] < high


def _status(*statuses: str) -> Callable[[Facts], bool]:
    return lambda f: f.get("status") in statuses


RULES: tuple[Rule, ...] = (
    # ------------------------------------------------------------ strengths
    Rule("attendance_excellent", "strengths", _at_least("attendance_rate", 95),
         "Отличная посещаемость! Ученик регулярно посещает занятия.",
         "Эң сонун катышуу! Окуучу сабактарга үзгүлтүксүз катышат.", ("student",)),
    Rule("attendance_excellent", "strengths", _at_least("attendance_rate", 95),
         "Отличная посещаемость — ученики регулярно посещают занятия.",
         "Эң сонун катышуу — окуучулар сабактарга үзгүлтүксүз катышышат.", ("group",)),
    Rule("attendance_good", "strengths", _between("attendance_rate", 85, 95),
         "Хорошая посещаемость: большинство занятий посещено.",
         "Жакшы катышуу: сабактардын көпчүлүгүнө катышты."),
    Rule("homework_excellent", "strengths", _at_least("homework_rate", 90),
         "Домашние задания выполняются регулярно.",
         "Үй тапшырмалары үзгүлтүксүз аткарылат."),
    Rule("homework_good", "strengths", _between("homework_rate", 75, 90),
         "Большинство домашних заданий выполнено.",
         "Үй тапшырмаларынын көпчүлүгү аткарылды."),
    Rule("score_excellent", "strengths", _at_least("average_score", 9),
         "Отличные академические результаты.",
         "Эң сонун окуу жыйынтыктары."),
    Rule("score_good", "strengths", _between("average_score", 7.5, 9),
         "Хорошие академические результаты.",
         "Жакшы окуу жыйынтыктары."),
    Rule("tests_excellent", "strengths", _at_least("test_average", 85),
         "Высокие результаты тестирования.",
         "Тестирлөөнүн жогорку жыйынтыктары."),
    Rule("excellent_students", "strengths", _at_least("excellent_count", 1),
         "{excellent_count_ru} с отличными результатами.",
         "{excellent_count} окуучу эң жакшы жыйынтык көрсөттү.", ("group",)),
    Rule("attendance_up", "strengths", _at_least("attendance_change", 5),
         "Посещаемость выросла на {attendance_change} п.п. по сравнению с прошлым периодом.",
         "Катышуу мурунку мезгилге салыштырмалуу {attendance_change} п.п. өстү."),
    Rule("homework_up", "strengths", _at_least("homework_change", 10),
         "Выполнение домашних заданий выросло на {homework_change} п.п.",
         "Үй тапшырмаларын аткаруу {homework_change} п.п. өстү."),
    Rule("score_up", "strengths", _at_least("score_change", 0.5),
         "Средний балл вырос на {score_change}.",
         "Орточо баа {score_change} упайга өстү."),
    Rule("tests_up", "strengths", _at_least("test_change", 5),
         "Результаты тестов улучшились на {test_change} п.п.",
         "Тест жыйынтыктары {test_change} п.п. жакшырды."),
    # ------------------------------------------------------------ attention
    Rule("attendance_low", "attention", _below("attendance_rate", 70),
         "Необходимо обратить внимание на регулярность посещения занятий.",
         "Сабактарга үзгүлтүксүз катышууга көңүл буруу зарыл."),
    Rule("attendance_medium", "attention", _between("attendance_rate", 70, 85),
         "Посещаемость можно улучшить: пропуски замедляют освоение материала.",
         "Катышууну жакшыртса болот: калтырылган сабактар материалды өздөштүрүүнү жайлатат."),
    Rule("homework_low", "attention", _below("homework_rate", 60),
         "Рекомендуется уделить больше внимания выполнению домашних заданий.",
         "Үй тапшырмаларын аткарууга көбүрөөк көңүл буруу сунушталат."),
    Rule("score_low", "attention", _below("average_score", 5),
         "Рекомендуется повторить пройденные темы и закрепить материал.",
         "Өтүлгөн темаларды кайталап, материалды бекемдөө сунушталат."),
    Rule("tests_low", "attention", _below("test_average", 60),
         "Необходимо дополнительно подготовиться к тестированию.",
         "Тестирлөөгө кошумча даярдануу зарыл."),
    Rule("students_need_attention", "attention", _at_least("attention_count", 1),
         "{attention_count_ru} требуется дополнительное внимание.",
         "{attention_count} окуучуга кошумча көңүл буруу керек.", ("group",)),
    Rule("attendance_down", "attention", _below("attendance_change", -10),
         "Посещаемость снизилась на {attendance_change} п.п. по сравнению с прошлым периодом.",
         "Катышуу мурунку мезгилге салыштырмалуу {attendance_change} п.п. төмөндөдү."),
    Rule("homework_down", "attention", _below("homework_change", -15),
         "Выполнение домашних заданий снизилось на {homework_change} п.п.",
         "Үй тапшырмаларын аткаруу {homework_change} п.п. төмөндөдү."),
    Rule("score_down", "attention", _below("score_change", -1),
         "Средний балл снизился на {score_change}.",
         "Орточо баа {score_change} упайга төмөндөдү."),
    # -------------------------------------------------------------- parents
    Rule("parents_attendance", "parents", _below("attendance_rate", 85),
         "Пожалуйста, помогите ребёнку не пропускать занятия — регулярность напрямую влияет на результат.",
         "Сураныч, балаңызга сабактарды калтырбоого жардам бериңиз — үзгүлтүксүз катышуу жыйынтыкка түз таасир этет."),
    Rule("parents_homework", "parents", _below("homework_rate", 75),
         "Уточняйте у ребёнка после каждого занятия, выполнено ли домашнее задание.",
         "Ар бир сабактан кийин балаңыздан үй тапшырмасы аткарылганын сурап туруңуз."),
    Rule("parents_score", "parents", _below("average_score", 6.5),
         "Попросите ребёнка рассказать, что было на занятии, — это помогает закрепить материал.",
         "Балаңыздан сабакта эмнени үйрөнгөнүн айтып берүүсүн сураңыз — бул материалды бекемдөөгө жардам берет."),
    Rule("parents_tests", "parents", _below("test_average", 70),
         "Помогите ребёнку повторить материал перед следующим тестированием.",
         "Кийинки тестирлөөнүн алдында балаңызга материалды кайталоого жардам бериңиз."),
    Rule("parents_praise", "parents", _status("excellent"),
         "Хвалите ребёнка за успехи — это поддерживает мотивацию продолжать в том же темпе.",
         "Балаңызды ийгиликтери үчүн мактап туруңуз — бул аны ушундай темпте улантууга шыктандырат.", ("student",)),
)

FALLBACKS = {
    "no_data": {
        "ru": "Недостаточно данных за выбранный период.",
        "ky": "Тандалган мезгил боюнча маалымат жетишсиз.",
    },
    "strengths": {
        "student": {"ru": "Обучение продолжается — следим за прогрессом.",
                    "ky": "Окуу уланууда — өсүштү көзөмөлдөп жатабыз."},
        "group": {"ru": "Группа продолжает обучение по программе курса.",
                  "ky": "Топ курстун программасы боюнча окуусун улантууда."},
    },
    "attention": {"ru": "Серьёзных замечаний за период нет.", "ky": "Бул мезгилде олуттуу эскертүүлөр жок."},
    "parents": {
        "ru": "Продолжайте поддерживать интерес ребёнка к обучению и интересуйтесь его успехами.",
        "ky": "Баланын окууга болгон кызыгуусун колдоп, анын ийгиликтерине кызыгып туруңуз.",
    },
}

_METRICS = ("attendance_rate", "homework_rate", "average_score", "test_average")


def _plural_ru(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _change(comparison: dict, metric: str) -> float | None:
    return (comparison or {}).get(metric, {}).get("change")


def facts_for_student(entry: dict, *, include_comparison: bool = True) -> Facts:
    comparison = entry.get("comparison") if include_comparison else None
    return {
        **{metric: entry.get(metric) for metric in _METRICS},
        "status": entry.get("status"),
        "attendance_change": _change(comparison, "attendance_rate"),
        "homework_change": _change(comparison, "homework_rate"),
        "score_change": _change(comparison, "average_score"),
        "test_change": _change(comparison, "test_average"),
    }


def facts_for_group(snapshot: dict, *, include_comparison: bool = True) -> Facts:
    stats = snapshot["group_stats"]
    comparison = snapshot.get("group_comparison") if include_comparison else None
    return {
        **{metric: stats.get(metric) for metric in _METRICS},
        "excellent_count": stats.get("excellent_count"),
        "attention_count": stats.get("attention_count"),
        "attendance_change": _change(comparison, "attendance_rate"),
        "homework_change": _change(comparison, "homework_rate"),
        "score_change": _change(comparison, "average_score"),
        "test_change": _change(comparison, "test_average"),
    }


def _params(facts: Facts) -> dict:
    params = {}
    for name in ("attendance_change", "homework_change", "score_change", "test_change"):
        value = facts.get(name)
        params[name] = i18n.number(abs(value)) if value is not None else ""
    excellent = int(facts.get("excellent_count") or 0)
    attention = int(facts.get("attention_count") or 0)
    params["excellent_count"] = excellent
    params["attention_count"] = attention
    params["excellent_count_ru"] = f"{excellent} {_plural_ru(excellent, 'ученик', 'ученика', 'учеников')}"
    params["attention_count_ru"] = f"{attention} {_plural_ru(attention, 'ученику', 'ученикам', 'ученикам')}"
    return params


def has_data(facts: Facts) -> bool:
    return any(facts.get(metric) is not None for metric in _METRICS)


def build(facts: Facts, *, scope: str, language: str) -> dict[str, list[dict]]:
    """``{section: [{"key", "text"}]}`` — at most MAX_ITEMS per section,
    never empty (a neutral, true fallback when no rule fired)."""
    language = language if language in i18n.LANGUAGES else "ru"
    if not has_data(facts):
        text = FALLBACKS["no_data"][language]
        return {section: [{"key": "no_data", "text": text}] for section in SECTIONS}

    params = _params(facts)
    result: dict[str, list[dict]] = {section: [] for section in SECTIONS}
    for rule in RULES:
        if scope not in rule.scopes or len(result[rule.section]) >= MAX_ITEMS:
            continue
        if rule.when(facts):
            template = rule.ky if language == "ky" else rule.ru
            result[rule.section].append({"key": rule.key, "text": template.format(**params)})

    for section in SECTIONS:
        if not result[section]:
            fallback = FALLBACKS[section]
            fallback = fallback.get(scope, fallback) if section == "strengths" else fallback
            result[section].append({"key": f"{section}_default", "text": fallback[language]})
    return result


def build_all(facts: Facts, *, scope: str) -> dict[str, dict[str, list[dict]]]:
    return {language: build(facts, scope=scope, language=language) for language in i18n.LANGUAGES}
