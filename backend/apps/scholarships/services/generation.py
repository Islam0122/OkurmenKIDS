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
from django.db import transaction
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
            if evaluation.rank is not None and evaluation.rank <= period.max_recipients
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
                    configuration=config,
                    period_end=window.period_end,
                    evaluation_date=window.award_date,
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


def _summary(period: ScholarshipPeriod) -> str:
    evaluated = period.evaluations.count()
    eligible = period.evaluations.filter(eligibility_status="eligible").count()
    awarded = period.awards.count()
    return f"Оценено: {evaluated}, допущено: {eligible}, стипендий: {awarded} из {period.max_recipients}."


def recalculate_period(period: ScholarshipPeriod, *, user=None, trigger=ScholarshipRunLog.Trigger.ADMIN) -> ScholarshipPeriod:
    try:
        with transaction.atomic():
            locked = ScholarshipPeriod.objects.select_for_update().get(pk=period.pk)
            if not locked.is_draft:
                raise ScholarshipError("Утверждённый период нельзя пересчитать.")
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
    return results
