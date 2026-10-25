"""Учебный прогресс ученика по договору — единый расчёт для «Все студенты»,
очередей, карточки, формы платежа и сверки (`progress_audit`).

Правило отображения: засчитанные ученику уроки приоритетного предмета
(IT) 1–12 → месяц 1, 13–24 → месяц 2, 25–36 → месяц 3… (12 = уроков в
месяце по договору). Полные 12/12 остаются в завершённом месяце: на 12-м
уроке ученик — «месяц 1, 12/12», а не «месяц 2, 0/12».

Засчитанные уроки — `LessonPackage.lessons_used` по не отменённым пакетам
(= действующие списания `LessonConsumption`): только предмет договора, с
даты начала, по правилу пропусков тарифа, каждый урок один раз. English и
Soft Skills не входят. Это не число проведённых занятий группы
(`group_held_lessons` — показатель академии, показывается отдельно).

Платёжный цикл не меняется: после 12-го урока пакет месяца 2 создаётся и
начисление выставляется как раньше (`billing_month` — номер этого пакета).
Расчёт только для отображения: ни пакеты, ни начисления он не трогает."""
from __future__ import annotations

from apps.academy.models import Lesson

from ..models import LessonPackage


def study_progress(counted: int, per_month: int | None, duration: int | None) -> dict:
    """Месяц и прогресс по числу засчитанных уроков (см. модуль)."""
    counted = max(int(counted or 0), 0)
    if not per_month:
        return {"month": None, "months": duration, "in_month": counted, "per_month": per_month,
                "counted": counted, "total": None}
    month = 1 if counted == 0 else (counted - 1) // per_month + 1
    if duration:
        month = min(month, duration)
    return {"month": month, "months": duration, "in_month": counted - (month - 1) * per_month,
            "per_month": per_month, "counted": counted, "total": duration * per_month if duration else None}


def counted_lessons(profile, packages=None) -> int:
    """Засчитанные ученику уроки (по не отменённым пакетам; можно передать
    уже загруженные пакеты — без запроса)."""
    if packages is None:
        packages = profile.packages.all()
    return sum(p.lessons_used for p in packages if p.status != LessonPackage.Status.CANCELLED)


def profile_progress(profile, packages=None) -> dict | None:
    """Прогресс договора по программе; None — тариф без учебных месяцев."""
    if not profile.is_course:
        return None
    packages = list(profile.packages.all()) if packages is None else packages
    progress = study_progress(counted_lessons(profile, packages), profile.lessons_per_month, profile.duration_months)
    live = [p for p in packages if p.status != LessonPackage.Status.CANCELLED]
    current = next((p for p in live if p.status == LessonPackage.Status.ACTIVE), None) or (live[-1] if live else None)
    # Номер пакета текущего платёжного цикла: на границе (12/12) — уже следующий
    # месяц, начисление по нему выставлено по правилу проекта.
    progress["billing_month"] = (current.month_number or current.number) if current else None
    progress["next_month_open"] = bool(progress["billing_month"] and progress["month"]
                                       and progress["billing_month"] > progress["month"])
    return progress


def group_held_lessons(profile) -> dict:
    """Показатель академии: проведённые занятия предмета договора в группах
    ученика (текущая и из истории переводов) — не то же, что засчитано ученику."""
    from .lessons import _student_group_ids

    held = Lesson.objects.filter(group_id__in=_student_group_ids(profile.student_id), status=Lesson.Status.COMPLETED)
    if profile.subject_id:
        held = held.filter(subject_id=profile.subject_id)
    since = held.filter(date__gte=profile.start_date)
    if profile.stopped_on:
        since = since.filter(date__lt=profile.stopped_on)
    return {"all_time": held.count(), "since_contract": since.count()}


__all__ = ["counted_lessons", "group_held_lessons", "profile_progress", "study_progress"]
