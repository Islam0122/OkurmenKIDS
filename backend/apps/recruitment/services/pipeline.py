"""Этапы найма и собеседования: все изменения состояния отклика проходят
здесь, поэтому противоречивых состояний не возникает.

Правила:

* Вручную этап меняется только по `MANUAL_TRANSITIONS`. «Собеседование
  назначено» и «Собеседование проведено» ставятся собеседованиями, «Принят на
  работу» — только наймом (вместе с созданием учётной записи).
* Пока у отклика есть запланированная встреча, его этап — «Собеседование
  назначено». Отмена или неявка на последнюю встречу возвращает отклик на этап
  до неё.
* Отказ, отказ кандидата и предложение о работе отменяют оставшиеся
  запланированные встречи.
* Перенос закрывает встречу статусом «Перенесено» и создаёт новую — время
  каждой встречи остаётся в истории.
* Назначение и перенос предупреждают о встрече того же кандидата на близкое
  время и о занятости интервьюера (см. `find_conflicts`); подтверждённое
  предупреждение не мешает назначить.
* Каждое изменение пишется в журнал HRActivity: из какого этапа, в какой,
  кто и когда.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from ..models import Application, HRActivity, Interview
from . import activity
from .common import RecruitmentError

S = Application.Status
I = Interview.Status  # noqa: E741 — короткое имя статусов встречи

# Встречи одного кандидата ближе этого интервала считаются возможным дублем.
DUPLICATE_WINDOW = timedelta(hours=3)

TERMINAL = {S.HIRED, S.REJECTED, S.WITHDRAWN}
CLOSING = {S.REJECTED, S.WITHDRAWN}

MANUAL_TRANSITIONS: dict[str, set[str]] = {
    S.NEW: {S.SCREENING, S.SHORTLISTED, S.REJECTED, S.WITHDRAWN},
    S.SCREENING: {S.SHORTLISTED, S.REJECTED, S.WITHDRAWN},
    S.SHORTLISTED: {S.SCREENING, S.REJECTED, S.WITHDRAWN},
    S.INTERVIEW_SCHEDULED: {S.REJECTED, S.WITHDRAWN},
    S.INTERVIEW_DONE: {S.AWAITING_DECISION, S.NEXT_STAGE, S.OFFER, S.REJECTED, S.WITHDRAWN},
    S.AWAITING_DECISION: {S.NEXT_STAGE, S.OFFER, S.REJECTED, S.WITHDRAWN},
    S.NEXT_STAGE: {S.AWAITING_DECISION, S.OFFER, S.REJECTED, S.WITHDRAWN},
    S.OFFER: {S.AWAITING_DECISION, S.REJECTED, S.WITHDRAWN},
    S.HIRED: set(),
    # Закрытый отклик можно вернуть в работу — на первичный просмотр.
    S.REJECTED: {S.SCREENING},
    S.WITHDRAWN: {S.SCREENING},
}

# С каких этапов можно назначить собеседование.
SCHEDULABLE = {S.NEW, S.SCREENING, S.SHORTLISTED, S.INTERVIEW_SCHEDULED, S.INTERVIEW_DONE, S.AWAITING_DECISION,
               S.NEXT_STAGE}

NEXT_STEP_STATUS = {
    Interview.NextStep.NEXT_INTERVIEW: S.NEXT_STAGE,
    Interview.NextStep.AWAITING_DECISION: S.AWAITING_DECISION,
    Interview.NextStep.OFFER: S.OFFER,
    Interview.NextStep.REJECT: S.REJECTED,
}


def allowed_manual_statuses(application: Application) -> list[str]:
    return [value for value, _ in S.choices if value in MANUAL_TRANSITIONS.get(application.status, set())]


def _label(status: str) -> str:
    return S(status).label if status else ""


def set_status(application: Application, new_status: str, actor, *, message: str = "", interview=None) -> None:
    """Сменить этап без проверки перехода (вызывающий уже проверил) и записать в журнал."""
    old = application.status
    if old == new_status:
        return
    application.status = new_status
    application.status_changed_at = timezone.now()
    application.save(update_fields=["status", "status_changed_at", "updated_at"])
    activity.log(
        HRActivity.Kind.CANDIDATE_STATUS, actor, application=application, interview=interview,
        vacancy=application.vacancy, from_status=old, to_status=new_status,
        message=message or f"{_label(old)} → {_label(new_status)}",
    )


def _lock(application: Application) -> Application:
    """Строка отклика под блокировкой до конца транзакции. Блокируется только
    сам отклик (`of=("self",)`): вакансия — nullable FK, т. е. LEFT OUTER JOIN,
    а PostgreSQL не умеет FOR UPDATE для nullable-стороны внешнего соединения.
    Кандидат и вакансия всё равно читаются тем же запросом."""
    return Application.objects.select_for_update(of=("self",)).select_related("candidate", "vacancy") \
        .get(pk=application.pk)


def _cancel_open_interviews(application: Application, actor, reason: str) -> None:
    now = timezone.now()
    for interview in application.interviews.select_for_update().filter(status=I.SCHEDULED):
        interview.status = I.CANCELLED
        interview.cancel_reason = reason
        interview.cancelled_at = now
        interview.save(update_fields=["status", "cancel_reason", "cancelled_at", "updated_at"])
        activity.log(HRActivity.Kind.INTERVIEW_CANCELLED, actor, application=application, interview=interview,
                     message=reason)


def _status_without_meetings(application: Application) -> str:
    """Этап отклика, у которого не осталось запланированных встреч."""
    if application.interviews.filter(status=I.COMPLETED).exists():
        return S.INTERVIEW_DONE
    return S.SHORTLISTED


@transaction.atomic
def change_status(application: Application, new_status: str, actor, comment: str = "") -> Application:
    application = _lock(application)
    if new_status not in MANUAL_TRANSITIONS.get(application.status, set()):
        if new_status == S.HIRED:
            raise RecruitmentError("Этап «Принят на работу» ставится только при оформлении — кнопкой «Принять на работу».",
                                   "hire_required")
        if new_status in (S.INTERVIEW_SCHEDULED, S.INTERVIEW_DONE):
            raise RecruitmentError("Этот этап ставится собеседованием: назначьте его или зафиксируйте результат.",
                                   "interview_required")
        raise RecruitmentError(
            f"Из этапа «{_label(application.status)}» нельзя перейти в «{_label(new_status)}».", "invalid_transition",
            extra={"allowed": allowed_manual_statuses(application)},
        )
    if application.status in CLOSING and application.vacancy_id:
        # Вернуть в работу нельзя, если у кандидата уже есть другой действующий отклик на эту вакансию.
        if Application.objects.filter(candidate=application.candidate, vacancy=application.vacancy) \
                .exclude(pk=application.pk).exclude(status__in=TERMINAL).exists():
            raise RecruitmentError("У кандидата уже есть действующий отклик на эту вакансию.", "duplicate_application",
                                   status=409)
    if new_status in CLOSING or new_status == S.OFFER:
        _cancel_open_interviews(application, actor, f"Отклик переведён в этап «{_label(new_status)}»")
    set_status(application, new_status, actor, message=comment)
    return application


# ---------------------------------------------------------------------------
# Собеседования
# ---------------------------------------------------------------------------

def _end(start: datetime, minutes: int) -> datetime:
    return start + timedelta(minutes=minutes)


def find_conflicts(application: Application, interviewer, start: datetime, duration: int,
                   exclude: int | None = None) -> list[dict]:
    """Запланированные встречи, которые выглядят как дубль или пересекаются у интервьюера."""
    scheduled = Interview.objects.select_related("application__candidate", "interviewer").filter(status=I.SCHEDULED)
    if exclude:
        scheduled = scheduled.exclude(pk=exclude)
    conflicts = []
    same_candidate = scheduled.filter(application__candidate_id=application.candidate_id,
                                      scheduled_at__gt=start - DUPLICATE_WINDOW,
                                      scheduled_at__lt=start + DUPLICATE_WINDOW)
    for other in same_candidate:
        conflicts.append({"type": "candidate", "interview_id": other.pk,
                          "scheduled_at": timezone.localtime(other.scheduled_at).isoformat(),
                          "message": "У кандидата уже есть собеседование на близкое время."})
    end = _end(start, duration)
    window = scheduled.filter(interviewer=interviewer, scheduled_at__lt=end,
                              scheduled_at__gt=start - timedelta(minutes=480)) \
        .exclude(application__candidate_id=application.candidate_id)
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


def _when(value: datetime) -> str:
    return timezone.localtime(value).strftime("%d.%m.%Y %H:%M")


@transaction.atomic
def schedule_interview(application: Application, actor, *, confirm: bool = False, **data) -> Interview:
    application = _lock(application)
    if application.status not in SCHEDULABLE:
        raise RecruitmentError(
            f"На этапе «{_label(application.status)}» собеседование не назначается.", "not_schedulable",
        )
    _check_time(data["scheduled_at"])
    if not confirm:
        _raise_conflicts(find_conflicts(application, data["interviewer"], data["scheduled_at"],
                                        data.get("duration_minutes", 60)))
    data.setdefault("vacancy", application.vacancy)
    interview = Interview.objects.create(application=application, created_by=actor, **data)
    activity.log(HRActivity.Kind.INTERVIEW_SCHEDULED, actor, application=application, interview=interview,
                 vacancy=interview.vacancy, message=f"Собеседование на {_when(interview.scheduled_at)}")
    set_status(application, S.INTERVIEW_SCHEDULED, actor, interview=interview)
    return interview


def _lock_interview(interview: Interview) -> Interview:
    # Блокируется только встреча; отклик вызывающий блокирует отдельно (`_lock`).
    interview = Interview.objects.select_for_update(of=("self",)).select_related("application__candidate") \
        .get(pk=interview.pk)
    if interview.status != I.SCHEDULED:
        raise RecruitmentError("Собеседование уже проведено, перенесено или отменено.", "not_scheduled")
    return interview


RESCHEDULE_COPY = ("vacancy", "duration_minutes", "format", "location", "meeting_url", "interviewer", "notes")


@transaction.atomic
def update_interview(interview: Interview, actor, *, confirm: bool = False, **data) -> Interview:
    """Изменение деталей встречи. Новое время — перенос: прежняя встреча
    получает статус «Перенесено», создаётся новая (её и возвращаем)."""
    interview = _lock_interview(interview)
    application = interview.application
    new_start = data.pop("scheduled_at", interview.scheduled_at)
    moved = new_start != interview.scheduled_at
    if moved:
        _check_time(new_start)
    if moved or "interviewer" in data or "duration_minutes" in data:
        if not confirm:
            _raise_conflicts(find_conflicts(application, data.get("interviewer", interview.interviewer),
                                            new_start, data.get("duration_minutes", interview.duration_minutes),
                                            exclude=interview.pk))
    if not moved:
        for key, value in data.items():
            setattr(interview, key, value)
        interview.save()
        return interview
    details = {key: data.get(key, getattr(interview, key)) for key in RESCHEDULE_COPY}
    new = Interview.objects.create(application=application, scheduled_at=new_start, created_by=actor,
                                   reschedule_count=interview.reschedule_count + 1, **details)
    interview.status = I.RESCHEDULED
    interview.rescheduled_to = new
    interview.save(update_fields=["status", "rescheduled_to", "updated_at"])
    activity.log(HRActivity.Kind.INTERVIEW_RESCHEDULED, actor, application=application, interview=interview,
                 message=f"{_when(interview.scheduled_at)} → {_when(new_start)}")
    return new


def _after_meeting_lost(interview: Interview, application: Application, actor, message: str) -> None:
    still_planned = application.interviews.filter(status=I.SCHEDULED).exists()
    if application.status == S.INTERVIEW_SCHEDULED and not still_planned:
        set_status(application, _status_without_meetings(application), actor, interview=interview, message=message)


@transaction.atomic
def cancel_interview(interview: Interview, actor, reason: str) -> Interview:
    interview = _lock_interview(interview)
    application = _lock(interview.application)
    interview.status = I.CANCELLED
    interview.cancel_reason = reason
    interview.cancelled_at = timezone.now()
    interview.save(update_fields=["status", "cancel_reason", "cancelled_at", "updated_at"])
    activity.log(HRActivity.Kind.INTERVIEW_CANCELLED, actor, application=application, interview=interview,
                 message=reason)
    _after_meeting_lost(interview, application, actor, "Запланированных собеседований не осталось")
    return interview


@transaction.atomic
def mark_no_show(interview: Interview, actor, comment: str = "") -> Interview:
    """Кандидат не пришёл — фиксирует ответственный после начала встречи. Оценка не нужна."""
    interview = _lock_interview(interview)
    application = _lock(interview.application)
    if interview.scheduled_at > timezone.now():
        raise RecruitmentError("Неявку можно отметить только после начала собеседования.", "not_started")
    interview.status = I.NO_SHOW
    interview.cancel_reason = comment
    interview.save(update_fields=["status", "cancel_reason", "updated_at"])
    activity.log(HRActivity.Kind.INTERVIEW_NO_SHOW, actor, application=application, interview=interview,
                 message=comment or "Кандидат не пришёл")
    _after_meeting_lost(interview, application, actor, "Кандидат не пришёл на собеседование")
    return interview


@transaction.atomic
def complete_interview(interview: Interview, actor, *, result: str, next_step: str, overall_rating: int,
                       skills_rating: int, strengths: str = "", concerns: str = "", result_comment: str = "",
                       next_step_date=None) -> Interview:
    interview = _lock_interview(interview)
    application = _lock(interview.application)
    if interview.scheduled_at > timezone.now():
        raise RecruitmentError("Результат фиксируется после начала собеседования.", "not_started")
    if next_step_date and next_step_date < timezone.localtime(interview.scheduled_at).date():
        raise RecruitmentError("Дата следующего этапа не может быть раньше собеседования.", "invalid_date")
    interview.status = I.COMPLETED
    interview.result = result
    interview.overall_rating = overall_rating
    interview.skills_rating = skills_rating
    interview.strengths = strengths
    interview.concerns = concerns
    interview.result_comment = result_comment
    interview.next_step = next_step
    interview.next_step_date = next_step_date
    interview.completed_at = timezone.now()
    interview.save()
    activity.log(HRActivity.Kind.INTERVIEW_COMPLETED, actor, application=application, interview=interview,
                 message=f"{interview.get_result_display()}, оценка {overall_rating}/5; "
                         f"следующий шаг — {interview.get_next_step_display()}")

    target = NEXT_STEP_STATUS[next_step]
    if application.status in TERMINAL:
        return interview
    if target in CLOSING or target == S.OFFER:
        _cancel_open_interviews(application, actor, f"Отклик переведён в этап «{_label(target)}»")
    elif application.interviews.filter(status=I.SCHEDULED).exists():
        # Впереди ещё одна запланированная встреча — этап остаётся «назначено».
        return interview
    # История этапов: «проведено» фиксируется всегда, затем — выбранный шаг.
    set_status(application, S.INTERVIEW_DONE, actor, interview=interview, message="Собеседование проведено")
    set_status(application, target, actor, interview=interview)
    return interview
