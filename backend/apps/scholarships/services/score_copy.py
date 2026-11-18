"""Bulk copy of trainer scores (TrainerFeedback) between subjects.

Typical use: the IT trainer's scores of a group are entered and the Soft
Skills scores must hold the same values — instead of re-typing every row, an
administrator copies them in one operation. Rules:

* **Matching is by Student id only** — a source row and a target row belong
  to the same student when their `student_id` is equal. Names, row numbers
  and table positions are never used.
* **Where a score may be written** is decided by the existing rule
  (services.feedback.validate_feedback_target): a target row needs a trainer
  who really gave the student lessons of the target subject in the target
  period, and the target period must be a draft. The trainer is taken from
  the group's real lessons; when several trainers taught the target subject,
  the administrator has to pick one (nothing is guessed).
* **Empty never erases**: a student with no source score is skipped; a copy
  never deletes or blanks a target score.
* **Existing target scores** are kept (`preserve`) or replaced
  (`overwrite`, which the apply step accepts only with an explicit
  confirmation). Identical values are reported as «unchanged» and not written,
  so running the same copy twice changes nothing the second time.
* **Preview → apply**: `plan()` is pure (no writes). `apply()` re-plans inside
  one database transaction with the target rows locked, refuses with a
  conflict when the data changed since the preview (fingerprint), and writes
  everything or nothing. Every created / overwritten row is kept in
  ScoreCopyItem with its values before and after.
* **Undo** restores each row only while it still holds exactly the copied
  values; a row edited by hand after the copy is left alone and reported.

A copy only changes TrainerFeedback; rankings change when the period is
recalculated (the same as any other feedback edit).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.academy.models import Attendance, Group, GroupTeacher, Lesson, Student, TrainerAssignment
from apps.academy.services.trainer_history import taught_by_q
from apps.users.models import Subject, Teacher

from ..models import ScholarshipPeriod, ScoreCopyItem, ScoreCopyOperation, TrainerFeedback
from .feedback import validate_feedback_target

CRITERIA = TrainerFeedback.CRITERIA
FIELDS = (*CRITERIA, "comment")


class ScoreCopyError(Exception):
    """A request that cannot be carried out — `code` maps to the HTTP status."""

    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.message = message
        self.code = code  # invalid | conflict | confirmation_required


# Row actions -----------------------------------------------------------------

CREATE = "create"
OVERWRITE = "overwrite"
UNCHANGED = "unchanged"
SKIP_EXISTING = "skip_existing"
SKIP_EMPTY = "skip_empty"
UNMATCHED_SOURCE = "unmatched_ambiguous_source"
UNMATCHED_TARGET = "unmatched_no_target"
UNMATCHED_TARGET_AMBIGUOUS = "unmatched_ambiguous_target"
NOT_SELECTED = "not_selected"

WRITES = (CREATE, OVERWRITE)
UNMATCHED = (UNMATCHED_SOURCE, UNMATCHED_TARGET, UNMATCHED_TARGET_AMBIGUOUS)

REASONS = {
    CREATE: "Будет создана новая оценка.",
    OVERWRITE: "Существующая оценка будет перезаписана.",
    UNCHANGED: "Оценка уже совпадает — ничего не меняется.",
    SKIP_EXISTING: "У студента уже есть оценка по целевому предмету — сохраняется.",
    SKIP_EMPTY: "Нет оценки по предмету-источнику — пропускается.",
    UNMATCHED_SOURCE: "Несколько тренеров оценили предмет-источник по-разному — выберите тренера-источника.",
    UNMATCHED_TARGET: "У студента не было занятий по целевому предмету в целевом периоде.",
    UNMATCHED_TARGET_AMBIGUOUS: "Целевой предмет вели несколько тренеров — выберите целевого тренера.",
    NOT_SELECTED: "Студент не выбран.",
}


@dataclass(frozen=True)
class CopyRequest:
    group: Group
    source_subject: Subject
    target_subject: Subject
    source_period: ScholarshipPeriod
    target_period: ScholarshipPeriod
    student_ids: tuple[int, ...] | None = None  # None = every student («copy all»)
    overwrite: bool = False
    copy_comment: bool = False
    source_teacher: Teacher | None = None
    target_teacher: Teacher | None = None

    def options(self) -> dict:
        return {
            "mode": "all" if self.student_ids is None else "selected",
            "student_ids": list(self.student_ids or []),
            "conflict": "overwrite" if self.overwrite else "preserve",
            "copy_comment": self.copy_comment,
            "source_teacher": self.source_teacher.pk if self.source_teacher else None,
            "target_teacher": self.target_teacher.pk if self.target_teacher else None,
        }


@dataclass
class Row:
    student: Student
    action: str
    source: TrainerFeedback | None = None
    target_teacher: Teacher | None = None
    target: TrainerFeedback | None = None
    values: dict | None = None  # what the target will hold after the copy
    target_teachers: list[Teacher] = field(default_factory=list)


@dataclass
class Plan:
    request: CopyRequest
    rows: list[Row]
    source_teachers: list[Teacher]
    target_teachers: list[Teacher]

    def count(self, *actions: str) -> int:
        return sum(1 for row in self.rows if row.action in actions)

    @property
    def writes(self) -> list[Row]:
        return [row for row in self.rows if row.action in WRITES]

    def summary(self) -> dict:
        considered = [row for row in self.rows if row.action != NOT_SELECTED]
        return {
            "students": len(considered),
            "matched": sum(1 for row in considered if row.action not in (*UNMATCHED, SKIP_EMPTY)),
            "copyable": self.count(CREATE, OVERWRITE),
            "create": self.count(CREATE),
            "overwrite": self.count(OVERWRITE),
            "unchanged": self.count(UNCHANGED),
            "skip_existing": self.count(SKIP_EXISTING),
            "empty": self.count(SKIP_EMPTY),
            "existing_target": sum(1 for row in considered if row.target is not None),
            "unmatched": self.count(*UNMATCHED),
            "not_selected": self.count(NOT_SELECTED),
        }

    def fingerprint(self) -> str:
        """Changes whenever the planned writes or the rows they replace change —
        apply() refuses a fingerprint taken from a stale preview."""
        payload = [
            (row.student.pk, row.action, row.target_teacher.pk if row.target_teacher else None,
             row.target.pk if row.target else None, _values(row.target) if row.target else None, row.values)
            for row in self.rows
        ]
        return hashlib.sha256(json.dumps([self.request.options(), payload], sort_keys=True, default=str).encode()).hexdigest()


def _values(feedback: TrainerFeedback) -> dict:
    return {name: getattr(feedback, name) for name in FIELDS}


def _scores(feedback: TrainerFeedback) -> tuple:
    return tuple(getattr(feedback, name) for name in CRITERIA)


# Validation -------------------------------------------------------------------

def validate_request(req: CopyRequest) -> None:
    if req.source_subject.pk == req.target_subject.pk and req.source_period.pk == req.target_period.pk:
        raise ScoreCopyError("Источник и цель совпадают: выберите другой предмет или период.")
    if not req.target_period.is_draft:
        raise ScoreCopyError("Целевой период уже утверждён — оценки в нём менять нельзя.")
    if req.student_ids is not None and not req.student_ids:
        raise ScoreCopyError("Выберите хотя бы одного студента.")


# Planning ----------------------------------------------------------------------

def _group_lessons(group: Group, period: ScholarshipPeriod, subject: Subject):
    return (
        Lesson.objects.filter(group=group, subject=subject, date__gte=period.period_start, date__lte=period.period_end)
        .exclude(status=Lesson.Status.CANCELLED)
    )


def _candidate_teacher_ids(group: Group, period: ScholarshipPeriod) -> set[int]:
    """Trainers who could have given this group's lessons in the period."""
    ids = set(
        Lesson.objects.filter(group=group, date__gte=period.period_start, date__lte=period.period_end,
                              teacher__isnull=False).values_list("teacher_id", flat=True)
    )
    ids |= set(TrainerAssignment.objects.filter(group=group).values_list("teacher_id", flat=True))
    ids |= set(GroupTeacher.objects.filter(group=group).values_list("teacher_id", flat=True))
    return ids


def target_teachers_by_student(group: Group, period: ScholarshipPeriod, subject: Subject) -> dict[int, set[int]]:
    """student id → trainers who gave that student lessons of `subject` in this
    group during `period` (attendance recorded — the feedback rule)."""
    lessons = _group_lessons(group, period, subject)
    result: dict[int, set[int]] = defaultdict(set)
    for teacher_id in _candidate_teacher_ids(group, period):
        taught = lessons.filter(taught_by_q(teacher_id))
        for student_id in Attendance.objects.filter(lesson__in=taught).values_list("student_id", flat=True).distinct():
            result[student_id].add(teacher_id)
    return result


def group_students(req: CopyRequest, target_map: dict[int, set[int]]) -> list[Student]:
    """Everyone who belongs to this copy: the group's students now, plus every
    student who had the group's source-subject lessons in the source period or
    target-subject lessons in the target period (a student who left the group
    still has scores). Ordered by name for display only — never matched by it."""
    source_students = Attendance.objects.filter(
        lesson__in=_group_lessons(req.group, req.source_period, req.source_subject)
    ).values_list("student_id", flat=True)
    ids = set(Student.objects.filter(group=req.group).values_list("pk", flat=True))
    ids |= set(source_students) | set(target_map)
    return list(Student.objects.filter(pk__in=ids).order_by("last_name", "first_name", "pk"))


def plan(req: CopyRequest, *, lock: bool = False) -> Plan:
    validate_request(req)
    target_map = target_teachers_by_student(req.group, req.target_period, req.target_subject)
    students = group_students(req, target_map)
    student_ids = [s.pk for s in students]

    source_qs = TrainerFeedback.objects.filter(period=req.source_period, subject=req.source_subject,
                                               student_id__in=student_ids).select_related("teacher__user")
    if req.source_teacher is not None:
        source_qs = source_qs.filter(teacher=req.source_teacher)
    sources: dict[int, list[TrainerFeedback]] = defaultdict(list)
    for fb in source_qs.order_by("pk"):
        sources[fb.student_id].append(fb)

    target_qs = TrainerFeedback.objects.filter(period=req.target_period, subject=req.target_subject,
                                               student_id__in=student_ids)
    if lock:
        target_qs = target_qs.select_for_update()
    targets = {(fb.student_id, fb.teacher_id): fb for fb in target_qs}

    teacher_ids = {tid for tids in target_map.values() for tid in tids}
    teacher_ids |= {fb.teacher_id for rows in sources.values() for fb in rows}
    teachers = Teacher.objects.select_related("user").in_bulk(teacher_ids)

    selected = None if req.student_ids is None else set(req.student_ids)
    rows: list[Row] = []
    for student in students:
        tids = target_map.get(student.pk, set())
        row = Row(student=student, action=SKIP_EMPTY,
                  target_teachers=[teachers[t] for t in sorted(tids) if t in teachers])
        rows.append(row)
        if selected is not None and student.pk not in selected:
            row.action = NOT_SELECTED
            continue

        # Source: one score per student, or several trainers who agree.
        found = sources.get(student.pk, [])
        if found:
            distinct = {_scores(fb) for fb in found}
            if len(distinct) > 1:
                row.action = UNMATCHED_SOURCE
                continue
            row.source = found[0]

        # Target trainer: the one chosen, else the only one who taught the subject.
        if req.target_teacher is not None:
            if req.target_teacher.pk not in tids:
                row.action = UNMATCHED_TARGET
                continue
            row.target_teacher = req.target_teacher
        elif len(tids) == 1:
            row.target_teacher = teachers.get(next(iter(tids)))
        elif not tids:
            row.action = UNMATCHED_TARGET
            continue
        else:
            row.action = UNMATCHED_TARGET_AMBIGUOUS
            row.target = None
            continue

        row.target = targets.get((student.pk, row.target_teacher.pk))
        if row.source is None:
            row.action = SKIP_EMPTY
            continue

        values = {name: getattr(row.source, name) for name in CRITERIA}
        current = _values(row.target) if row.target else None
        values["comment"] = row.source.comment if req.copy_comment else (current or {}).get("comment", "")
        row.values = values
        if current is None:
            row.action = CREATE
        elif current == values:
            row.action = UNCHANGED
        elif req.overwrite:
            row.action = OVERWRITE
        else:
            row.action = SKIP_EXISTING

    source_teachers = sorted({fb.teacher for rows_ in sources.values() for fb in rows_}, key=lambda t: str(t))
    all_target = sorted({teachers[t] for t in teacher_ids if any(t in tids for tids in target_map.values())},
                        key=lambda t: str(t))
    return Plan(request=req, rows=rows, source_teachers=source_teachers, target_teachers=all_target)


# Apply --------------------------------------------------------------------------

def apply(req: CopyRequest, *, user, fingerprint: str, operation_id: uuid.UUID,
          confirm_overwrite: bool = False) -> tuple[ScoreCopyOperation, bool]:
    """Runs the copy atomically. Returns (operation, replayed) — `replayed` is
    True when this `operation_id` was already applied (idempotent retry)."""
    existing = ScoreCopyOperation.objects.filter(operation_id=operation_id).first()
    if existing is not None:
        if existing.created_by_id != user.pk:
            raise ScoreCopyError("Этот идентификатор операции уже использован.", "conflict")
        return existing, True

    try:
        with transaction.atomic():
            # Lock the target period so it cannot be approved mid-copy.
            period = ScholarshipPeriod.objects.select_for_update().get(pk=req.target_period.pk)
            if not period.is_draft:
                raise ScoreCopyError("Целевой период уже утверждён — оценки в нём менять нельзя.")
            current = plan(req, lock=True)
            if current.fingerprint() != fingerprint:
                raise ScoreCopyError(
                    "Данные изменились после предпросмотра. Обновите предпросмотр и проверьте изменения ещё раз.",
                    "conflict",
                )
            if current.count(OVERWRITE) and not confirm_overwrite:
                raise ScoreCopyError(
                    f"Будет перезаписано оценок: {current.count(OVERWRITE)}. Подтвердите перезапись.",
                    "confirmation_required",
                )
            if not current.writes:
                raise ScoreCopyError("Нечего копировать: все оценки пропущены или уже совпадают.")

            skipped = {action: current.count(action) for action in
                       (UNCHANGED, SKIP_EXISTING, SKIP_EMPTY, *UNMATCHED) if current.count(action)}
            operation = ScoreCopyOperation.objects.create(
                operation_id=operation_id, group=req.group, group_name=req.group.name,
                source_subject=req.source_subject, source_subject_name=req.source_subject.name,
                target_subject=req.target_subject, target_subject_name=req.target_subject.name,
                source_period=req.source_period, target_period=req.target_period, options=req.options(),
                copied_count=current.count(CREATE), overwritten_count=current.count(OVERWRITE),
                skipped_count=sum(skipped.values()), skipped_details=skipped, created_by=user,
            )
            items = []
            for row in current.writes:
                # The existing ownership rule, re-checked for every written row.
                validate_feedback_target(period=period, teacher=row.target_teacher, student=row.student,
                                         subject=req.target_subject)
                if row.action == CREATE:
                    target = TrainerFeedback.objects.create(
                        period=period, student=row.student, subject=req.target_subject, teacher=row.target_teacher,
                        created_by=user, updated_by=user, **row.values,
                    )
                    before = None
                else:
                    target = row.target
                    before = _values(target)
                    for name, value in row.values.items():
                        setattr(target, name, value)
                    target.updated_by = user
                    target.full_clean()
                    target.save()
                items.append(ScoreCopyItem(
                    operation=operation, feedback=target, student=row.student, teacher=row.target_teacher,
                    source_feedback=row.source, action=ScoreCopyItem.Action.CREATED if before is None
                    else ScoreCopyItem.Action.OVERWRITTEN, before=before, after=_values(target),
                ))
            ScoreCopyItem.objects.bulk_create(items)
            return operation, False
    except ValidationError as exc:
        raise ScoreCopyError(" ".join(exc.messages)) from exc
    except IntegrityError as exc:
        # A concurrent copy or a manual entry created the same row first — nothing was written.
        raise ScoreCopyError("Оценки изменились во время копирования. Ничего не изменено — повторите предпросмотр.",
                             "conflict") from exc


# Undo -----------------------------------------------------------------------------

def undo(operation: ScoreCopyOperation, *, user) -> ScoreCopyOperation:
    with transaction.atomic():
        operation = ScoreCopyOperation.objects.select_for_update().get(pk=operation.pk)
        if operation.status != ScoreCopyOperation.Status.APPLIED:
            raise ScoreCopyError("Эта операция уже отменена.", "conflict")
        period = (ScholarshipPeriod.objects.select_for_update().filter(pk=operation.target_period_id).first()
                  if operation.target_period_id else None)
        if period is None or not period.is_draft:
            raise ScoreCopyError("Целевой период утверждён или удалён — отменить копирование нельзя.")

        results = defaultdict(int)
        items = list(operation.items.select_for_update().select_related("feedback"))
        feedback_ids = [item.feedback_id for item in items if item.feedback_id]
        live = {fb.pk: fb for fb in TrainerFeedback.objects.select_for_update().filter(pk__in=feedback_ids)}
        for item in items:
            fb = live.get(item.feedback_id)
            if fb is None:
                item.undo_result = ScoreCopyItem.UndoResult.SKIPPED_MISSING
            elif _values(fb) != item.after:
                # Edited by hand (or by a later copy) after this operation — never overwritten.
                item.undo_result = ScoreCopyItem.UndoResult.SKIPPED_CHANGED
            elif item.action == ScoreCopyItem.Action.CREATED:
                fb.delete()
                item.undo_result = ScoreCopyItem.UndoResult.DELETED
            else:
                for name, value in item.before.items():
                    setattr(fb, name, value)
                fb.updated_by = user
                fb.save()
                item.undo_result = ScoreCopyItem.UndoResult.RESTORED
            results[item.undo_result] += 1
        ScoreCopyItem.objects.bulk_update(items, ["undo_result"])

        untouched = results[ScoreCopyItem.UndoResult.SKIPPED_CHANGED] + results[ScoreCopyItem.UndoResult.SKIPPED_MISSING]
        operation.status = (ScoreCopyOperation.Status.PARTIALLY_REVERTED if untouched
                            else ScoreCopyOperation.Status.REVERTED)
        operation.reverted_by = user
        operation.reverted_at = timezone.now()
        operation.revert_details = dict(results)
        operation.save(update_fields=["status", "reverted_by", "reverted_at", "revert_details"])
        return operation


# Helpers for the API ----------------------------------------------------------------

def feedback_values(feedback: TrainerFeedback | None) -> dict | None:
    if feedback is None:
        return None
    return {**{name: getattr(feedback, name) for name in CRITERIA}, "score": float(round(feedback.score, 2))}


def values_score(values: dict | None) -> float | None:
    if not values:
        return None
    return round(sum(values[name] for name in CRITERIA) / len(CRITERIA) / 5 * 100, 2)


def subjects_of_group(group: Group) -> list[Subject]:
    ids = set(Lesson.objects.filter(group=group, subject__isnull=False).values_list("subject_id", flat=True))
    if group.course_id:
        ids |= set(group.course.subjects.values_list("pk", flat=True))
    return list(Subject.objects.filter(Q(pk__in=ids)).order_by("name"))
