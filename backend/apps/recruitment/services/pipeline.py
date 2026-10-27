"""Этапы найма и собеседования: все изменения состояния кандидата проходят
здесь, поэтому противоречивых состояний не возникает.

Правила:

* Вручную этап меняется только по `MANUAL_TRANSITIONS`. «Собеседование
  назначено» и «Собеседование пройдено» ставятся собеседованиями, «Принят на
  работу» — только наймом (вместе с созданием учётной записи).
* Пока у кандидата есть назначенная встреча, его этап — «Собеседование
  назначено». Отмена последней встречи возвращает кандидата на этап до неё.
* Отказ, отказ кандидата и предложение о работе отменяют оставшиеся
  назначенные встречи.
* Назначение и перенос предупреждают о встрече того же кандидата на близкое
  время и о занятости интервьюера (см. `find_conflicts`); подтверждённое
  предупреждение не мешает назначить.
* Каждое изменение пишется в журнал HRActivity: из какого этапа, в какой,
  кто и когда.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from ..models import Candidate, HRActivity, Interview
from . import activity

S = Candidate.Status

# Встречи одного кандидата ближе этого интервала считаются возможным дублем.
DUPLICATE_WINDOW = timedelta(hours=3)

TERMINAL = {S.HIRED, S.REJECTED, S.WITHDRAWN}
CLOSING = {S.REJECTED, S.WITHDRAWN}

MANUAL_TRANSITIONS: dict[str, set[str]] = {
    S.NEW: {S.CONTACTED, S.REJECTED, S.WITHDRAWN},
    S.CONTACTED: {S.REJECTED, S.WITHDRAWN},
    S.INTERVIEW_SCHEDULED: {S.REJECTED, S.WITHDRAWN},
    S.INTERVIEW_DONE: {S.AWAITING_DECISION, S.OFFER, S.REJECTED, S.WITHDRAWN},
    S.AWAITING_DECISION: {S.OFFER, S.REJECTED, S.WITHDRAWN},
    S.OFFER: {S.AWAITING_DECISION, S.REJECTED, S.WITHDRAWN},
    S.HIRED: set(),
    # Закрытого кандидата можно вернуть в работу — с начала воронки.
    S.REJECTED: {S.NEW},
    S.WITHDRAWN: {S.NEW},
}

# С каких этапов можно назначить собеседование.
SCHEDULABLE = {S.NEW, S.CONTACTED, S.INTERVIEW_SCHEDULED, S.INTERVIEW_DONE, S.AWAITING_DECISION}

NEXT_STEP_STATUS = {
    Interview.NextStep.NEXT_INTERVIEW: S.INTERVIEW_DONE,
    Interview.NextStep.AWAITING_DECISION: S.AWAITING_DECISION,
    Interview.NextStep.OFFER: S.OFFER,
    Interview.NextStep.REJECT: S.REJECTED,
}


@dataclass
class RecruitmentError(Exception):
    message: str
    code: str = "invalid"
    status: int = 400
    extra: dict = field(default_factory=dict)


def allowed_manual_statuses(candidate: Candidate) -> list[str]:
    return [value for value, _ in S.choices if value in MANUAL_TRANSITIONS.get(candidate.status, set())]


def _label(status: str) -> str:
    return S(status).label if status else ""


def _set_status(candidate: Candidate, new_status: str, actor, *, message: str = "", interview=None) -> None:
    old = candidate.status
    if old == new_status:
        return
    candidate.status = new_status
    candidate.status_changed_at = timezone.now()
    candidate.save(update_fields=["status", "status_changed_at", "updated_at"])
    activity.log(
        HRActivity.Kind.CANDIDATE_STATUS, actor, candidate=candidate, interview=interview,
        from_status=old, to_status=new_status,
        message=message or f"{_label(old)} → {_label(new_status)}",
    )


def _lock(candidate: Candidate) -> Candidate:
    return Candidate.objects.select_for_update().get(pk=candidate.pk)


def _cancel_open_interviews(candidate: Candidate, actor, reason: str, exclude: int | None = None) -> None:
    qs = candidate.interviews.select_for_update().filter(status=Interview.Status.SCHEDULED)
    if exclude:
        qs = qs.exclude(pk=exclude)
    now = timezone.now()
    for interview in qs:
        interview.status = Interview.Status.CANCELLED
        interview.cancel_reason = reason
        interview.cancelled_at = now
        interview.save(update_fields=["status", "cancel_reason", "cancelled_at", "updated_at"])
        activity.log(HRActivity.Kind.INTERVIEW_CANCELLED, actor, candidate=candidate, interview=interview,
                     message=reason)


def _status_without_meetings(candidate: Candidate) -> str:
    """Этап кандидата, у которого не осталось назначенных встреч."""
    if candidate.interviews.filter(status=Interview.Status.COMPLETED).exists():
        return S.INTERVIEW_DONE
    return S.CONTACTED


@transaction.atomic
def change_status(candidate: Candidate, new_status: str, actor, comment: str = "") -> Candidate:
    candidate = _lock(candidate)
    if new_status not in MANUAL_TRANSITIONS.get(candidate.status, set()):
        if new_status == S.HIRED:
            raise RecruitmentError("Этап «Принят на работу» ставится только при оформлении — кнопкой «Принять на работу».",
                                   "hire_required")
        if new_status in (S.INTERVIEW_SCHEDULED, S.INTERVIEW_DONE):
            raise RecruitmentError("Этот этап ставится собеседованием: назначьте его или зафиксируйте результат.",
                                   "interview_required")
        raise RecruitmentError(
            f"Из этапа «{_label(candidate.status)}» нельзя перейти в «{_label(new_status)}».", "invalid_transition",
            extra={"allowed": allowed_manual_statuses(candidate)},
        )
    if new_status in CLOSING or new_status == S.OFFER:
        _cancel_open_interviews(candidate, actor, f"Кандидат переведён в этап «{_label(new_status)}»")
    _set_status(candidate, new_status, actor, message=comment)
    return candidate


# ---------------------------------------------------------------------------
# Собеседования
# ---------------------------------------------------------------------------

def _end(start: datetime, minutes: int) -> datetime:
    return start + timedelta(minutes=minutes)


def find_conflicts(candidate: Candidate, interviewer, start: datetime, duration: int,
                   exclude: int | None = None) -> list[dict]:
    """Назначенные встречи, которые выглядят как дубль или пересекаются у интервьюера."""
    scheduled = Interview.objects.select_related("candidate", "interviewer").filter(status=Interview.Status.SCHEDULED)
    if exclude:
        scheduled = scheduled.exclude(pk=exclude)
    conflicts = []
    same_candidate = scheduled.filter(candidate=candidate, scheduled_at__gt=start - DUPLICATE_WINDOW,
                                      scheduled_at__lt=start + DUPLICATE_WINDOW)
    for other in same_candidate:
        conflicts.append({"type": "candidate", "interview_id": other.pk,
                          "scheduled_at": timezone.localtime(other.scheduled_at).isoformat(),
                          "message": "У кандидата уже есть собеседование на близкое время."})
    end = _end(start, duration)
    window = scheduled.filter(interviewer=interviewer, scheduled_at__lt=end,
                              scheduled_at__gt=start - timedelta(minutes=480)).exclude(candidate=candidate)
    for other in window:
        if _end(other.scheduled_at, other.duration_minutes) > start:
            conflicts.append({"type": "interviewer", "interview_id": other.pk,
                              "scheduled_at": timezone.localtime(other.scheduled_at).isoformat(),
                              "message": f"Интервьюер занят: собеседование с «{other.candidate.full_name}»."})
    return conflicts


def _check_time(start: datetime) -> None:
    if start <= timezone.now():
        raise RecruitmentError("Собеседование можно назначить только на будущее время.", "past_time")


def _raise_conflicts(conflicts: list[dict]) -> None:
    if conflicts:
        raise RecruitmentError(
            "Похоже на дублирование встречи. Проверьте время или подтвердите назначение.", "interview_conflict",
            status=409, extra={"conflicts": conflicts},
        )


@transaction.atomic
def schedule_interview(candidate: Candidate, actor, *, confirm: bool = False, **data) -> Interview:
    candidate = _lock(candidate)
    if candidate.status not in SCHEDULABLE:
        raise RecruitmentError(
            f"Кандидату на этапе «{_label(candidate.status)}» собеседование не назначается.", "not_schedulable",
        )
    _check_time(data["scheduled_at"])
    if not confirm:
        _raise_conflicts(find_conflicts(candidate, data["interviewer"], data["scheduled_at"],
                                        data.get("duration_minutes", 60)))
    data.setdefault("vacancy", candidate.vacancy)
    interview = Interview.objects.create(candidate=candidate, created_by=actor, **data)
    when = timezone.localtime(interview.scheduled_at).strftime("%d.%m.%Y %H:%M")
    activity.log(HRActivity.Kind.INTERVIEW_SCHEDULED, actor, candidate=candidate, interview=interview,
                 vacancy=interview.vacancy, message=f"Собеседование на {when}")
    _set_status(candidate, S.INTERVIEW_SCHEDULED, actor, interview=interview)
    return interview


def _lock_interview(interview: Interview) -> Interview:
    interview = Interview.objects.select_for_update().select_related("candidate").get(pk=interview.pk)
    if interview.status != Interview.Status.SCHEDULED:
        raise RecruitmentError("Собеседование уже проведено или отменено.", "not_scheduled")
    return interview


@transaction.atomic
def update_interview(interview: Interview, actor, *, confirm: bool = False, **data) -> Interview:
    """Изменение деталей и перенос. Новое время — перенос (с записью в журнал)."""
    interview = _lock_interview(interview)
    new_start = data.get("scheduled_at", interview.scheduled_at)
    moved = new_start != interview.scheduled_at
    if moved:
        _check_time(new_start)
    if moved or "interviewer" in data or "duration_minutes" in data:
        if not confirm:
            _raise_conflicts(find_conflicts(interview.candidate, data.get("interviewer", interview.interviewer),
                                            new_start, data.get("duration_minutes", interview.duration_minutes),
                                            exclude=interview.pk))
    old_start = interview.scheduled_at
    for key, value in data.items():
        setattr(interview, key, value)
    if moved:
        interview.reschedule_count += 1
    interview.save()
    if moved:
        fmt = "%d.%m.%Y %H:%M"
        activity.log(HRActivity.Kind.INTERVIEW_RESCHEDULED, actor, candidate=interview.candidate, interview=interview,
                     message=f"{timezone.localtime(old_start).strftime(fmt)} → "
                             f"{timezone.localtime(new_start).strftime(fmt)}")
    return interview


@transaction.atomic
def cancel_interview(interview: Interview, actor, reason: str) -> Interview:
    interview = _lock_interview(interview)
    candidate = _lock(interview.candidate)
    interview.status = Interview.Status.CANCELLED
    interview.cancel_reason = reason
    interview.cancelled_at = timezone.now()
    interview.save(update_fields=["status", "cancel_reason", "cancelled_at", "updated_at"])
    activity.log(HRActivity.Kind.INTERVIEW_CANCELLED, actor, candidate=candidate, interview=interview, message=reason)
    still_planned = candidate.interviews.filter(status=Interview.Status.SCHEDULED).exists()
    if candidate.status == S.INTERVIEW_SCHEDULED and not still_planned:
        _set_status(candidate, _status_without_meetings(candidate), actor, interview=interview,
                    message="Назначенных собеседований не осталось")
    return interview


@transaction.atomic
def complete_interview(interview: Interview, actor, *, result: str, next_step: str, result_comment: str = "",
                       next_step_date=None) -> Interview:
    interview = _lock_interview(interview)
    candidate = _lock(interview.candidate)
    if interview.scheduled_at > timezone.now():
        raise RecruitmentError("Результат фиксируется после начала собеседования.", "not_started")
    if next_step_date and next_step_date < timezone.localtime(interview.scheduled_at).date():
        raise RecruitmentError("Дата следующего этапа не может быть раньше собеседования.", "invalid_date")
    interview.status = Interview.Status.COMPLETED
    interview.result = result
    interview.result_comment = result_comment
    interview.next_step = next_step
    interview.next_step_date = next_step_date
    interview.completed_at = timezone.now()
    interview.save()
    activity.log(HRActivity.Kind.INTERVIEW_COMPLETED, actor, candidate=candidate, interview=interview,
                 message=f"{interview.get_result_display()}; следующий шаг — {interview.get_next_step_display()}")

    target = NEXT_STEP_STATUS[next_step]
    if target in CLOSING or target == S.OFFER:
        _cancel_open_interviews(candidate, actor, f"Кандидат переведён в этап «{_label(target)}»")
    elif candidate.interviews.filter(status=Interview.Status.SCHEDULED).exists():
        # Впереди ещё одна назначенная встреча — этап остаётся «назначено».
        return interview
    # История этапов: «пройдено» фиксируется всегда, затем — выбранный шаг.
    _set_status(candidate, S.INTERVIEW_DONE, actor, interview=interview, message="Собеседование проведено")
    _set_status(candidate, target, actor, interview=interview)
    return interview


# ---------------------------------------------------------------------------
# Найм
# ---------------------------------------------------------------------------

@transaction.atomic
def hire(candidate: Candidate, actor, create_account) -> Candidate:
    """Принять на работу: создать учётную запись (`create_account()` — обычное
    создание сотрудника HR) и связать её с кандидатом. Строка кандидата
    блокируется, поэтому два одновременных запроса не создадут двух сотрудников."""
    candidate = _lock(candidate)
    if candidate.hired_user_id:
        raise RecruitmentError("Кандидат уже принят: учётная запись сотрудника создана.", "already_hired", status=409)
    if candidate.status != S.OFFER:
        raise RecruitmentError("Принять на работу можно кандидата на этапе «Предложение о работе».", "offer_required")
    user = create_account()
    candidate.hired_user = user
    candidate.status = S.HIRED
    old = S.OFFER
    candidate.status_changed_at = timezone.now()
    candidate.save(update_fields=["hired_user", "status", "status_changed_at", "updated_at"])
    activity.log(HRActivity.Kind.EMPLOYEE_CREATED, actor, employee=user, candidate=candidate,
                 message=f"Учётная запись «{user.username}» ({user.get_role_display()}) создана при найме")
    activity.log(HRActivity.Kind.CANDIDATE_STATUS, actor, candidate=candidate, employee=user,
                 from_status=old, to_status=S.HIRED, message=f"{_label(old)} → {_label(S.HIRED)}")
    activity.log(HRActivity.Kind.CANDIDATE_HIRED, actor, candidate=candidate, employee=user, vacancy=candidate.vacancy,
                 message=f"Принят на работу: {user.get_role_display()}")
    return candidate
