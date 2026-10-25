"""Учебный прогресс — три независимых показателя (только чтение).

1. **Учебный месяц группы** (`group_progress`) — общий прогресс IT-программы
   текущей группы ученика: проведённые (`completed`) занятия предмета
   программы в этой группе, каждое занятие один раз (отменённые,
   запланированные, идущие и другие предметы не входят). Правило: 1–12 →
   месяц 1, 13–24 → месяц 2…; полные 12/12 остаются в своём месяце. Одинаков
   у всех учеников группы — не зависит от даты прихода и посещаемости.
   После перевода — прогресс новой группы (история переводов не меняется).
   Смена преподавателя прогресс не сбрасывает: это одна строка программы
   (`trainer_assignment` меняет тренера в той же строке) или строки, чьи
   проведённые занятия идут последовательно. Если программ предмета
   несколько активных или их занятия пересекаются по датам — «Нужна
   настройка: несколько IT-программ», цифры не показываются.
   Размер месяца и число месяцев — из тарифов программы курса группы
   (активные тарифы курса и предмета + тарифы договоров учеников группы);
   нет тарифа или параметры расходятся — предупреждение, 12 не подставляется.
2. **Посещаемость ученика** (`attendance`) — сколько проведённых занятий
   предмета в текущей группе он посетил («был» / «опоздал»).
3. **Финансовый пакет** (`package`) — пакет договора ученика (уроки,
   засчитанные ему по договору); по нему выставляются начисления и сроки.

Месяц группы не меняет и не обосновывает начисления, долг, аванс, платежи,
сроки или посещаемость — он только показывается рядом."""
from __future__ import annotations

import datetime as dt
from itertools import pairwise

from django.db.models import Count, Max, Min, Q
from django.utils import timezone

from apps.academy.models import Attendance, Group, GroupTeacher, Lesson

from ..models import BillingPlan, LessonPackage, StudentBillingProfile
from . import BillingError

ATTENDED = (Attendance.Status.PRESENT, Attendance.Status.LATE)
WARNINGS = {
    "no_group": "Ученик не состоит в группе — учебный месяц группы не определён.",
    "no_subject": "У тарифа не указан предмет программы — учебный месяц группы не определён.",
    "no_program": "Нужна настройка: у группы нет программы этого предмета.",
    "multiple_programs": "Нужна настройка: несколько IT-программ в группе — общий прогресс не определён.",
    "no_tariff": "Нужна настройка: у курса группы нет тарифа с учебными месяцами — размер месяца не подтверждён.",
    "tariff_conflict": "Нужна настройка: тарифы курса группы задают разный размер учебного месяца.",
}


def study_progress(counted: int, per_month: int | None, duration: int | None) -> dict:
    """Месяц и занятие месяца по числу занятий: 1–12 → 1, 13–24 → 2…"""
    counted = max(int(counted or 0), 0)
    if not per_month:
        return {"month": None, "months": duration, "in_month": counted, "per_month": per_month,
                "counted": counted, "total": None}
    month = 1 if counted == 0 else (counted - 1) // per_month + 1
    if duration:
        month = min(month, duration)
    return {"month": month, "months": duration, "in_month": counted - (month - 1) * per_month,
            "per_month": per_month, "counted": counted, "total": duration * per_month if duration else None}


# ---------------------------------------------------------------------------
# 1. Учебный месяц группы
# ---------------------------------------------------------------------------

def _program_status(group_id: int, subject_id: int) -> str | None:
    """None — программа однозначна; иначе код предупреждения."""
    programs = list(GroupTeacher.objects.filter(group_id=group_id, subject_id=subject_id)
                    .annotate(first=Min("lessons__date", filter=_held_q()), last=Max("lessons__date", filter=_held_q()),
                              held=Count("lessons", filter=_held_q())))
    if not programs:
        return "no_program"
    if sum(1 for p in programs if p.is_active) > 1:
        return "multiple_programs"
    spans = sorted((p.first, p.last) for p in programs if p.held)
    # Последовательная смена преподавателя: следующая программа начинает после
    # последнего занятия предыдущей. Пересечение дат — параллельные программы.
    if any(nxt[0] <= prev[1] for prev, nxt in pairwise(spans)):
        return "multiple_programs"
    return None


def _held_q() -> Q:
    return Q(lessons__status=Lesson.Status.COMPLETED)


def tariff_params(group: Group, subject_id: int, on: dt.date | None = None) -> tuple[dict | None, str | None]:
    """({per_month, months} | None, код предупреждения) — тарифы программы курса группы."""
    from .contracts import course_quote

    on = on or timezone.localdate()
    plans = set(BillingPlan.objects.filter(course_id=group.course_id, subject_id=subject_id, is_active=True,
                                           duration_months__isnull=False))
    plans |= {p.plan for p in StudentBillingProfile.objects.filter(
        student__group=group, plan__course_id=group.course_id, plan__subject_id=subject_id,
        plan__duration_months__isnull=False).exclude(status__in=StudentBillingProfile.CLOSED_STATUSES)
        .select_related("plan")}
    def month_params(plan):
        try:
            quote = course_quote(plan, on)
        except BillingError:  # тариф без действующей цены не подтверждает размер месяца
            return None
        return quote.lessons_per_month, quote.duration_months

    params = {p for p in map(month_params, plans) if p is not None}
    if not params:
        return None, "no_tariff"
    if len(params) > 1:
        return None, "tariff_conflict"
    per_month, months = params.pop()
    return {"per_month": per_month, "months": months}, None


def group_progress(group: Group | None, subject_id: int | None, *, cache: dict | None = None) -> dict:
    """Учебный месяц группы (см. модуль). `cache` — общий словарь на страницу
    списка: одна группа считается один раз."""
    key = (getattr(group, "pk", None), subject_id)
    if cache is not None and key in cache:
        return cache[key]
    result = {"status": "ok", "warning": None, "group": getattr(group, "pk", None),
              "group_name": getattr(group, "name", None), "held": None, "month": None, "months": None,
              "in_month": None, "per_month": None, "total": None}
    code = None
    if group is None:
        code = "no_group"
    elif subject_id is None:
        code = "no_subject"
    else:
        code = _program_status(group.pk, subject_id)
        if code is None:
            params, code = tariff_params(group, subject_id)
            held = Lesson.objects.filter(group=group, subject_id=subject_id, status=Lesson.Status.COMPLETED).count()
            result["held"] = held
            if params is not None:
                rule = study_progress(held, params["per_month"], params["months"])
                result.update({k: rule[k] for k in ("month", "months", "in_month", "per_month", "total")})
    if code is not None:
        result.update({"status": code, "warning": WARNINGS[code]})
    if cache is not None:
        cache[key] = result
    return result


# ---------------------------------------------------------------------------
# 2. Посещаемость ученика и 3. финансовый пакет договора
# ---------------------------------------------------------------------------

def attendance(profile, group: Group | None) -> dict:
    if group is None or not profile.subject_id:
        return {"attended": None, "held": None}
    lessons = Lesson.objects.filter(group=group, subject_id=profile.subject_id, status=Lesson.Status.COMPLETED)
    attended = Attendance.objects.filter(student_id=profile.student_id, lesson__in=lessons, status__in=ATTENDED).count()
    return {"attended": attended, "held": lessons.count()}


def counted_lessons(profile, packages=None) -> int:
    """Уроки, засчитанные ученику по договору (не отменённые пакеты)."""
    if packages is None:
        packages = profile.packages.all()
    return sum(p.lessons_used for p in packages if p.status != LessonPackage.Status.CANCELLED)


def financial_package(profile, packages=None) -> dict | None:
    """Текущий пакет договора: по нему начисления и сроки оплаты."""
    packages = list(profile.packages.all()) if packages is None else packages
    live = [p for p in packages if p.status != LessonPackage.Status.CANCELLED]
    current = next((p for p in live if p.status == LessonPackage.Status.ACTIVE), None) or (live[-1] if live else None)
    if current is None:
        return None
    return {"number": current.month_number or current.number, "lessons_used": current.lessons_used,
            "lessons_total": current.lessons_total, "status": current.status,
            "counted": counted_lessons(profile, packages),
            "contract_months": profile.duration_months, "contract_per_month": profile.lessons_per_month}


def profile_progress(profile, packages=None, *, cache: dict | None = None) -> dict:
    """Все три показателя для договора ученика."""
    group = profile.student.group if profile.student.group_id else None
    return {
        "group": group_progress(group, profile.subject_id, cache=cache),
        "package": financial_package(profile, packages),
    }


__all__ = ["WARNINGS", "attendance", "counted_lessons", "financial_package", "group_progress", "profile_progress",
           "study_progress", "tariff_params"]
