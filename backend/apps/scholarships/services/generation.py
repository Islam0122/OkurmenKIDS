"""Generate, recalculate and approve scholarship periods.

Duplicate protection is layered:

1. `ScholarshipPeriod` is unique per (award_day, period_start) — a cycle can
   exist only once, whoever (scheduler, Admin, API) asks for it and however
   often. Creation goes through `get_or_create` inside a transaction, so
   two concurrent generators end with one period and one "already exists".
2. `ScholarshipAward` is unique per (student, period) and per (period, rank),
   and `ScholarshipEvaluation` per (period, student).
3. Recalculation and approval lock the period row (`select_for_update`) and
   re-check its status against the locked row, so an approval racing a
   recalculation can never leave a half-rebuilt ranking approved.
"""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..models import (
    ScholarshipAward,
    ScholarshipConfiguration,
    ScholarshipEvaluation,
    ScholarshipPeriod,
    ScholarshipRunLog,
    ScholarshipSubjectScore,
)
from .periods import cycle_window, due_cycles
from .scoring import StudentResult, evaluate_period, quantize, ranking_key

logger = logging.getLogger("apps.scholarships")

_BATCH = 1000


class ScholarshipError(ValidationError):
    """A business-rule refusal with a user-facing (Russian) message."""


@dataclass
class GenerationResult:
    period: ScholarshipPeriod
    created: bool


def get_active_configuration() -> ScholarshipConfiguration:
    config = ScholarshipConfiguration.objects.active()
    if config is None:
        raise ScholarshipError("Нет активной конфигурации стипендий — создайте её в админ-панели.")
    config.full_clean()
    return config


def _log(action, trigger, result, *, period=None, award_day=None, award_date=None, message="", user=None):
    ScholarshipRunLog.objects.create(
        action=action,
        trigger=trigger,
        result=result,
        period=period,
        award_day=award_day if award_day is not None else getattr(period, "award_day", None),
        award_date=award_date or getattr(period, "evaluation_date", None),
        message=message,
        triggered_by=user if getattr(user, "is_authenticated", False) else None,
    )
    log = logger.error if result == ScholarshipRunLog.Result.FAILED else logger.info
    log("scholarship %s (%s): %s — %s", action, trigger, result, message)


def _persist(period: ScholarshipPeriod, results: list[StudentResult]) -> None:
    """Replace the period's evaluations/awards with `results`. Caller holds
    the period lock and has checked it is still a DRAFT."""
    period.awards.all().delete()
    period.evaluations.all().delete()

    eligible = sorted((r for r in results if r.eligibility_status == "eligible"), key=ranking_key)
    rank_by_student = {r.student.id: index for index, r in enumerate(eligible, start=1)}

    # Three bulk INSERTs per period (evaluations, subject rows, awards) —
    # never one query per student. bulk_create sets primary keys on
    # PostgreSQL and SQLite, which the subject rows and awards need.
    ordered = sorted(results, key=lambda r: r.student.id)
    evaluations = ScholarshipEvaluation.objects.bulk_create(
        [
            ScholarshipEvaluation(
                period=period,
                student=result.student,
                student_name=str(result.student),
                group=result.student.group,
                group_name=result.student.group.name if result.student.group else "",
                course_name=result.student.group.course.name if result.student.group else "",
                enrollment_date=result.student.enrollment_date,
                overall_score=result.overall_score,
                attendance_score=result.attendance_score,
                homework_score=result.homework_score,
                feedback_score=result.feedback_score,
                lessons_count=result.lessons_count,
                subjects_count=len(result.counted_subjects),
                rank=rank_by_student.get(result.student.id),
                eligibility_status=result.eligibility_status,
                ineligibility_reason=result.ineligibility_reason,
                data_warnings=result.warnings,
            )
            for result in ordered
        ],
        batch_size=_BATCH,
    )
    ScholarshipSubjectScore.objects.bulk_create(
        [
            ScholarshipSubjectScore(
                evaluation=evaluation,
                subject_id=s.subject_id,
                subject_name=s.subject_name,
                lessons_attended=s.lessons_attended,
                lessons_missed=s.lessons_missed,
                lessons_excused=s.lessons_excused,
                lessons_unmarked=s.lessons_unmarked,
                homework_required=s.homework_required,
                homework_completed=s.homework_completed,
                feedback_expected=len(s.teacher_ids),
                feedback_received=len(s.feedback_scores),
                attendance_score=quantize(s.attendance_score),
                homework_score=quantize(s.homework_score),
                feedback_score=quantize(s.feedback_score),
                subject_score=quantize(s.subject_score),
                aggregation_weight=s.aggregation_weight,
            )
            for result, evaluation in zip(ordered, evaluations)
            for s in result.subjects
        ],
        batch_size=_BATCH,
    )
    ScholarshipAward.objects.bulk_create(
        [
            ScholarshipAward(
                period=period,
                student=result.student,
                evaluation=evaluation,
                rank=evaluation.rank,
                award_date=period.evaluation_date,
                amount=period.award_amount,
            )
            for result, evaluation in zip(ordered, evaluations)
            if evaluation.rank is not None and (period.is_unlimited or evaluation.rank <= period.max_recipients)
        ],
        batch_size=_BATCH,
    )

    period.last_calculated_at = timezone.now()
    period.save(update_fields=["last_calculated_at", "updated_at"])


def generate_period(
    award_date: dt.date,
    award_day: int,
    *,
    user=None,
    trigger: str = ScholarshipRunLog.Trigger.ADMIN,
    today: dt.date | None = None,
) -> GenerationResult:
    """Create and calculate the period for one award cycle. Idempotent: an
    existing period is returned untouched with `created=False`."""
    today = today or timezone.localdate()
    try:
        config = get_active_configuration()
        if award_day not in config.award_days:
            raise ScholarshipError(
                f"Цикл {award_day}-го числа не включён в текущем режиме начисления "
                f"(«{config.get_award_mode_display()}»)."
            )
        if award_date > today:
            raise ScholarshipError(
                f"Дата начисления {award_date:%d.%m.%Y} ещё не наступила — нельзя оценивать незавершённый период."
            )
        try:
            window = cycle_window(award_day, award_date)
        except ValueError as exc:
            raise ScholarshipError(str(exc)) from exc

        with transaction.atomic():
            period, created = ScholarshipPeriod.objects.get_or_create(
                award_day=award_day,
                period_start=window.period_start,
                defaults=dict(
                    **_snapshot(config),
                    period_end=window.period_end,
                    evaluation_date=window.award_date,
                    generated_by=user if getattr(user, "is_authenticated", False) else None,
                ),
            )
            if created:
                period = ScholarshipPeriod.objects.select_for_update().get(pk=period.pk)
                _persist(period, evaluate_period(period))
    except ScholarshipError as exc:
        _log(ScholarshipRunLog.Action.GENERATE, trigger, ScholarshipRunLog.Result.FAILED,
             award_day=award_day, award_date=award_date, message="; ".join(exc.messages), user=user)
        raise
    except Exception as exc:
        _log(ScholarshipRunLog.Action.GENERATE, trigger, ScholarshipRunLog.Result.FAILED,
             award_day=award_day, award_date=award_date, message=f"{type(exc).__name__}: {exc}", user=user)
        raise

    if not created:
        _log(ScholarshipRunLog.Action.GENERATE, trigger, ScholarshipRunLog.Result.SKIPPED, period=period,
             message="Период уже сформирован — повторное формирование пропущено.", user=user)
        return GenerationResult(period, created=False)

    _log(ScholarshipRunLog.Action.GENERATE, trigger, ScholarshipRunLog.Result.SUCCESS, period=period,
         message=_summary(period), user=user)
    if config.auto_approve:
        approve_period(period, user=user, trigger=trigger)
        period.refresh_from_db()
    return GenerationResult(period, created=True)


def limit_label(period: ScholarshipPeriod) -> str:
    return "без ограничения" if period.is_unlimited else str(period.max_recipients)


def _summary(period: ScholarshipPeriod) -> str:
    evaluated = period.evaluations.count()
    eligible = period.evaluations.filter(eligibility_status="eligible").count()
    awarded = period.awards.count()
    return f"Оценено: {evaluated}, допущено: {eligible}, стипендий: {awarded} из {limit_label(period)}."


def _snapshot(config: ScholarshipConfiguration) -> dict:
    """The configuration values copied into a new period."""
    return dict(
        configuration=config,
        max_recipients=config.max_recipients,
        attendance_weight=config.attendance_weight,
        homework_weight=config.homework_weight,
        feedback_weight=config.feedback_weight,
        subject_aggregation=config.subject_aggregation,
        late_homework_credit=config.late_homework_credit,
        min_overall_score=config.min_overall_score,
        min_marked_lessons=config.min_marked_lessons,
        require_complete_feedback=config.require_complete_feedback,
        award_amount=config.award_amount,
    )


def _validate_manual_window(period_start: dt.date, period_end: dt.date, *, exclude_pk=None) -> None:
    if period_end < period_start:
        raise ScholarshipError("Дата окончания не может быть раньше даты начала.")
    duplicate = ScholarshipPeriod.objects.filter(award_day__isnull=True, period_start=period_start, period_end=period_end)
    if exclude_pk is not None:
        duplicate = duplicate.exclude(pk=exclude_pk)
    if duplicate.exists():
        raise ScholarshipError(
            f"Период {period_start:%d.%m.%Y} — {period_end:%d.%m.%Y} уже существует."
        )


def _validate_limit(max_recipients: int | None) -> None:
    if max_recipients is not None and max_recipients < 1:
        raise ScholarshipError("Количество стипендиатов должно быть больше 0.")


def create_period(
    *,
    period_start: dt.date,
    period_end: dt.date,
    max_recipients: int | None,
    title: str = "Стипендия",
    user=None,
    trigger: str = ScholarshipRunLog.Trigger.ADMIN,
    today: dt.date | None = None,
) -> ScholarshipPeriod:
    """Create a manual period with arbitrary dates and its own limit
    (`None` = без ограничения). The rest of the parameters are snapshotted
    from the active configuration, exactly as for a generated cycle.

    A period that has already ended is calculated right away; one that is
    still running stays empty (trainers can already enter feedback) and is
    calculated once it ends — by «Рассчитать» or the daily schedule."""
    today = today or timezone.localdate()
    try:
        _validate_limit(max_recipients)
        _validate_manual_window(period_start, period_end)
        config = get_active_configuration()
        try:
            with transaction.atomic():
                period = ScholarshipPeriod.objects.create(
                    **{
                        **_snapshot(config),
                        "max_recipients": max_recipients,
                        "title": (title or "").strip() or "Стипендия",
                        "award_day": None,
                        "period_start": period_start,
                        "period_end": period_end,
                        "evaluation_date": period_end + dt.timedelta(days=1),
                        "generated_by": user if getattr(user, "is_authenticated", False) else None,
                    }
                )
                if period.evaluation_date <= today:
                    period = ScholarshipPeriod.objects.select_for_update().get(pk=period.pk)
                    _persist(period, evaluate_period(period))
        except IntegrityError as exc:  # a concurrent create of the same dates
            raise ScholarshipError(
                f"Период {period_start:%d.%m.%Y} — {period_end:%d.%m.%Y} уже существует."
            ) from exc
    except ScholarshipError as exc:
        _log(ScholarshipRunLog.Action.GENERATE, trigger, ScholarshipRunLog.Result.FAILED,
             award_date=period_end + dt.timedelta(days=1), message="; ".join(exc.messages), user=user)
        raise

    if period.is_calculated:
        _log(ScholarshipRunLog.Action.GENERATE, trigger, ScholarshipRunLog.Result.SUCCESS, period=period,
             message=_summary(period), user=user)
        if config.auto_approve:
            approve_period(period, user=user, trigger=trigger)
            period.refresh_from_db()
    else:
        _log(ScholarshipRunLog.Action.GENERATE, trigger, ScholarshipRunLog.Result.SUCCESS, period=period,
             message=f"Период создан, расчёт — после {period.period_end:%d.%m.%Y}. Лимит: {limit_label(period)}.",
             user=user)
    return period


_UNSET = object()


def update_period(
    period: ScholarshipPeriod,
    *,
    title=_UNSET,
    period_start=_UNSET,
    period_end=_UNSET,
    max_recipients=_UNSET,
    user=None,
    trigger: str = ScholarshipRunLog.Trigger.ADMIN,
) -> ScholarshipPeriod:
    """Edit a period. Only passed fields change.

    * title — always;
    * limit — only in a DRAFT, and never below the number of students who
      already have a scholarship (the Admin removes someone first). Raising
      it does not add anyone by itself: add students by hand or recalculate;
    * dates — only for a manual DRAFT that has not been calculated yet
      (a calculated ranking belongs to its dates; a cycle's dates are fixed).
    """
    changes = []
    try:
        with transaction.atomic():
            locked = ScholarshipPeriod.objects.select_for_update().get(pk=period.pk)
            fields = ["updated_at"]

            if title is not _UNSET:
                title = (title or "").strip() or "Стипендия"
                if title != locked.title:
                    changes.append(f"название «{title}»")
                    locked.title = title
                    fields.append("title")

            if max_recipients is not _UNSET and max_recipients != locked.max_recipients:
                if not locked.is_draft:
                    raise ScholarshipError("Лимит утверждённого периода изменить нельзя.")
                _validate_limit(max_recipients)
                awarded = locked.awards.count()
                if max_recipients is not None and awarded > max_recipients:
                    raise ScholarshipError(
                        f"Сейчас стипендию получают {awarded} студентов — лимит не может быть меньше. "
                        "Сначала уберите лишних студентов или пересчитайте период."
                    )
                locked.max_recipients = max_recipients
                changes.append(f"лимит {limit_label(locked)}")
                fields.append("max_recipients")

            new_start = locked.period_start if period_start is _UNSET else period_start
            new_end = locked.period_end if period_end is _UNSET else period_end
            if (new_start, new_end) != (locked.period_start, locked.period_end):
                if not locked.is_manual:
                    raise ScholarshipError("Даты автоматического цикла изменить нельзя.")
                if not locked.is_draft or locked.is_calculated:
                    raise ScholarshipError(
                        "Даты можно менять только до расчёта периода — рейтинг уже построен по этим датам."
                    )
                _validate_manual_window(new_start, new_end, exclude_pk=locked.pk)
                locked.period_start, locked.period_end = new_start, new_end
                locked.evaluation_date = new_end + dt.timedelta(days=1)
                changes.append(f"даты {locked.date_range}")
                fields += ["period_start", "period_end", "evaluation_date"]

            if changes:
                locked.save(update_fields=fields)
    except ScholarshipError as exc:
        _log(ScholarshipRunLog.Action.EDIT, trigger, ScholarshipRunLog.Result.FAILED, period=period,
             message="; ".join(exc.messages), user=user)
        raise
    if changes:
        _log(ScholarshipRunLog.Action.EDIT, trigger, ScholarshipRunLog.Result.SUCCESS, period=locked,
             message="Изменено: " + ", ".join(changes) + ".", user=user)
    return locked


def add_award(period: ScholarshipPeriod, evaluation: ScholarshipEvaluation, *, user=None,
              trigger: str = ScholarshipRunLog.Trigger.ADMIN) -> ScholarshipAward:
    """Give an eligible student of a DRAFT period a scholarship by hand.
    Refused once the limit is reached — the Admin raises the limit or
    removes someone first."""
    try:
        with transaction.atomic():
            locked = ScholarshipPeriod.objects.select_for_update().get(pk=period.pk)
            if not locked.is_draft:
                raise ScholarshipError("Период утверждён — список стипендиатов изменить нельзя.")
            evaluation = ScholarshipEvaluation.objects.get(pk=evaluation.pk)
            if evaluation.period_id != locked.pk:
                raise ScholarshipError("Студент не относится к этому периоду.")
            if not evaluation.is_eligible or evaluation.rank is None:
                raise ScholarshipError(
                    f"{evaluation.student_name} не допущен к стипендии: {evaluation.get_eligibility_status_display()}."
                )
            if ScholarshipAward.objects.filter(evaluation=evaluation).exists():
                raise ScholarshipError(f"{evaluation.student_name} уже получает стипендию.")
            awarded = locked.awards.count()
            if not locked.has_room_for(awarded):
                raise ScholarshipError(
                    f"Лимит стипендиатов достигнут: {awarded} из {locked.max_recipients}. "
                    "Увеличьте лимит или уберите одного студента."
                )
            award = ScholarshipAward.objects.create(
                period=locked, student_id=evaluation.student_id, evaluation=evaluation, rank=evaluation.rank,
                award_date=locked.evaluation_date, amount=locked.award_amount,
            )
    except ScholarshipError as exc:
        _log(ScholarshipRunLog.Action.AWARD, trigger, ScholarshipRunLog.Result.FAILED, period=period,
             message="; ".join(exc.messages), user=user)
        raise
    _log(ScholarshipRunLog.Action.AWARD, trigger, ScholarshipRunLog.Result.SUCCESS, period=locked,
         message=f"Добавлен стипендиат: {evaluation.student_name} (место {evaluation.rank}).", user=user)
    return award


def remove_award(period: ScholarshipPeriod, award: ScholarshipAward, *, user=None,
                 trigger: str = ScholarshipRunLog.Trigger.ADMIN) -> None:
    try:
        with transaction.atomic():
            locked = ScholarshipPeriod.objects.select_for_update().get(pk=period.pk)
            if not locked.is_draft:
                raise ScholarshipError("Период утверждён — список стипендиатов изменить нельзя.")
            award = ScholarshipAward.objects.select_related("evaluation").filter(pk=award.pk, period=locked).first()
            if award is None:
                raise ScholarshipError("Стипендия не найдена в этом периоде.")
            name = award.evaluation.student_name
            award.delete()
    except ScholarshipError as exc:
        _log(ScholarshipRunLog.Action.AWARD, trigger, ScholarshipRunLog.Result.FAILED, period=period,
             message="; ".join(exc.messages), user=user)
        raise
    _log(ScholarshipRunLog.Action.AWARD, trigger, ScholarshipRunLog.Result.SUCCESS, period=locked,
         message=f"Убран стипендиат: {name}.", user=user)


def recalculate_period(
    period: ScholarshipPeriod, *, user=None, trigger=ScholarshipRunLog.Trigger.ADMIN, today: dt.date | None = None,
) -> ScholarshipPeriod:
    try:
        with transaction.atomic():
            locked = ScholarshipPeriod.objects.select_for_update().get(pk=period.pk)
            if not locked.is_draft:
                raise ScholarshipError("Утверждённый период нельзя пересчитать.")
            # A cycle only ever exists once its period has ended; a manual
            # period can be created ahead of time and must not be ranked on
            # half a period's data.
            if locked.is_manual and locked.evaluation_date > (today or timezone.localdate()):
                raise ScholarshipError(
                    f"Период ещё идёт — расчёт возможен после {locked.period_end:%d.%m.%Y}."
                )
            _persist(locked, evaluate_period(locked))
    except ScholarshipError as exc:
        _log(ScholarshipRunLog.Action.RECALCULATE, trigger, ScholarshipRunLog.Result.FAILED, period=period,
             message="; ".join(exc.messages), user=user)
        raise
    except Exception as exc:
        _log(ScholarshipRunLog.Action.RECALCULATE, trigger, ScholarshipRunLog.Result.FAILED, period=period,
             message=f"{type(exc).__name__}: {exc}", user=user)
        raise
    _log(ScholarshipRunLog.Action.RECALCULATE, trigger, ScholarshipRunLog.Result.SUCCESS, period=locked,
         message=_summary(locked), user=user)
    return locked


def approve_period(period: ScholarshipPeriod, *, user=None, trigger=ScholarshipRunLog.Trigger.ADMIN) -> ScholarshipPeriod:
    now = timezone.now()
    approver = user if getattr(user, "is_authenticated", False) else None
    try:
        with transaction.atomic():
            locked = ScholarshipPeriod.objects.select_for_update().get(pk=period.pk)
            if not locked.is_draft:
                raise ScholarshipError("Период уже утверждён.")
            if not locked.is_calculated:
                raise ScholarshipError("Период ещё не рассчитан — утверждать нечего.")
            locked.awards.filter(status=ScholarshipAward.Status.PENDING).update(
                status=ScholarshipAward.Status.APPROVED, approved_by=approver, approved_at=now, updated_at=now
            )
            locked.status = ScholarshipPeriod.Status.APPROVED
            locked.approved_by = approver
            locked.approved_at = now
            locked.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    except ScholarshipError as exc:
        _log(ScholarshipRunLog.Action.APPROVE, trigger, ScholarshipRunLog.Result.FAILED, period=period,
             message="; ".join(exc.messages), user=user)
        raise
    _log(ScholarshipRunLog.Action.APPROVE, trigger, ScholarshipRunLog.Result.SUCCESS, period=locked,
         message=f"Утверждено стипендий: {locked.awards.count()}.", user=user)
    return locked


def run_schedule(*, today: dt.date | None = None, trigger=ScholarshipRunLog.Trigger.SCHEDULE, user=None) -> list[GenerationResult]:
    """Generate every due cycle for `today` (see periods.due_cycles). Safe
    to run as often as you like — existing periods are skipped."""
    today = today or timezone.localdate()
    try:
        config = get_active_configuration()
    except ScholarshipError as exc:
        _log(ScholarshipRunLog.Action.GENERATE, trigger, ScholarshipRunLog.Result.FAILED,
             award_date=today, message="; ".join(exc.messages), user=user)
        raise
    results = []
    for window in due_cycles(config.award_mode, today):
        results.append(generate_period(window.award_date, window.award_day, user=user, trigger=trigger, today=today))
    # Manual periods created ahead of time get their first calculation once
    # they have ended. A failure is logged by recalculate_period and must not
    # stop the other periods.
    pending = ScholarshipPeriod.objects.filter(
        award_day__isnull=True, status=ScholarshipPeriod.Status.DRAFT,
        last_calculated_at__isnull=True, evaluation_date__lte=today,
    )
    for period in pending:
        try:
            recalculate_period(period, user=user, trigger=trigger, today=today)
        except ValidationError:
            pass
    return results
