"""Bulk copy of lesson records between groups / subjects / periods.

What is copied — only fields that are really transferable, in the existing
academy models (nothing is duplicated):

* **attendance** → ``Attendance``: status (normalised with the attendance
  matrix's own alias table), the excuse reason that belongs to an EXCUSED
  status, and — with «copy comments» — the trainer's comment;
* **homework** → ``HomeworkResult``: status, submitted_at, checked_at and —
  with «copy comments» — the trainer's feedback comment;
* **scores** → ``HomeworkResult.score`` (0–10). A score never exists without
  its result, so a result *created* for a score also takes the source status
  and timestamps.

Never copied: the homework assignments themselves (trainer content), exam
attempts (apps.testing — auto-graded answers, copying would invent results),
period-level trainer scores (apps.scholarships has its own copy tool), any
personal or account data.

Rules:

* **Students are matched by Student id only.** A source record belongs to a
  target row of the *same* student. The student must currently belong to the
  target lesson's group (the rule of Attendance.clean / HomeworkResult.clean),
  so in a cross-group copy only students who are in the target group now are
  matched; the rest are listed as unmatched.
* **Lessons are mapped explicitly**: a list of (source lesson → target lesson)
  pairs. The server suggests one (the n-th held lesson of the source subject →
  the n-th of the target subject, by date) but never assumes it; every pair is
  validated, invalid pairs are reported and skipped. Homework of a mapped pair
  is paired in creation order and only when both lessons have the same number
  of homework assignments.
* Target lessons must have happened (not in the future, not cancelled) — the
  same rule as marking attendance by hand.
* A missing source record never deletes or blanks anything. «Skip empty
  values» additionally keeps the target's value where the source field is
  empty (no score, no comment).
* Existing target records are preserved, or overwritten with explicit
  confirmation. Identical values are not rewritten («unchanged»), so the same
  copy run twice changes nothing.
* Preview is a pure dry run. Execution re-plans inside one transaction with
  the target rows locked and compares the preview's fingerprint: if anything
  changed in between, nothing is written. Any error rolls everything back.
* Side effects of the real models stay in force: saving attendance re-syncs
  billing write-offs of that lesson (apps.billing.signals), and every
  attendance change is written to the attendance matrix history
  (AttendanceChangeLog), exactly like a manual change.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.academy.models import Attendance, Group, Homework, HomeworkResult, Lesson, Student
from apps.attendance_matrix.matrix import normalize_status
from apps.attendance_matrix.models import AttendanceChangeLog
from apps.users.models import Subject

from .. import access
from ..models import BulkCopyItem, BulkCopyOperation, Category

MAX_RANGE_DAYS = 186
MAX_PAIRS = 120

ATT_FIELDS = ("status", "excuse_reason", "comment")
HW_FIELDS = ("status", "score", "comment", "submitted_at", "checked_at")

# Record actions
CREATE = "create"
OVERWRITE = "overwrite"
UNCHANGED = "unchanged"
SKIP_EXISTING = "skip_existing"
EMPTY = "empty"
INVALID = "invalid"
WRITES = (CREATE, OVERWRITE)


class CopyError(Exception):
    def __init__(self, message: str, code: str = "invalid"):
        super().__init__(message)
        self.message = message
        self.code = code  # invalid | conflict | confirmation_required | forbidden


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CopyRequest:
    source_group: Group
    source_subject: Subject
    source_start: dt.date
    source_end: dt.date
    target_group: Group
    target_subject: Subject
    target_start: dt.date
    target_end: dt.date
    categories: frozenset[str]
    lesson_map: tuple[tuple[int, int], ...] | None = None  # None → suggested by the server
    student_ids: tuple[int, ...] | None = None  # None → every matched student
    overwrite: bool = False
    skip_empty: bool = True
    copy_comments: bool = False

    def to_json(self) -> dict:
        return {
            "source_group": self.source_group.pk, "source_subject": self.source_subject.pk,
            "source_start": self.source_start.isoformat(), "source_end": self.source_end.isoformat(),
            "target_group": self.target_group.pk, "target_subject": self.target_subject.pk,
            "target_start": self.target_start.isoformat(), "target_end": self.target_end.isoformat(),
            "categories": sorted(self.categories),
            "lesson_map": [list(pair) for pair in self.lesson_map] if self.lesson_map is not None else None,
            "student_ids": list(self.student_ids) if self.student_ids is not None else None,
            "conflict": "overwrite" if self.overwrite else "preserve",
            "skip_empty": self.skip_empty, "copy_comments": self.copy_comments,
        }

    @classmethod
    def from_json(cls, data: dict) -> CopyRequest:
        return cls(
            source_group=Group.objects.get(pk=data["source_group"]),
            source_subject=Subject.objects.get(pk=data["source_subject"]),
            source_start=dt.date.fromisoformat(data["source_start"]),
            source_end=dt.date.fromisoformat(data["source_end"]),
            target_group=Group.objects.get(pk=data["target_group"]),
            target_subject=Subject.objects.get(pk=data["target_subject"]),
            target_start=dt.date.fromisoformat(data["target_start"]),
            target_end=dt.date.fromisoformat(data["target_end"]),
            categories=frozenset(data["categories"]),
            lesson_map=tuple(tuple(p) for p in data["lesson_map"]) if data.get("lesson_map") is not None else None,
            student_ids=tuple(data["student_ids"]) if data.get("student_ids") is not None else None,
            overwrite=data.get("conflict") == "overwrite",
            skip_empty=data.get("skip_empty", True),
            copy_comments=data.get("copy_comments", False),
        )


def validate_request(req: CopyRequest, user) -> None:
    if not req.categories or not req.categories <= set(Category.values):
        raise CopyError("Выберите, что копировать: посещаемость, домашние задания или оценки.")
    for start, end, label in ((req.source_start, req.source_end, "источника"), (req.target_start, req.target_end, "цели")):
        if end < start:
            raise CopyError(f"Период {label}: дата окончания раньше начала.")
        if (end - start).days > MAX_RANGE_DAYS:
            raise CopyError(f"Период {label} не может быть длиннее {MAX_RANGE_DAYS} дней.")
    if req.student_ids is not None and not req.student_ids:
        raise CopyError("Выберите хотя бы одного студента.")
    if req.lesson_map is not None and len(req.lesson_map) > MAX_PAIRS:
        raise CopyError(f"Не больше {MAX_PAIRS} пар занятий за одну операцию.")
    if not access.can_read_group(user, req.source_group):
        raise CopyError("Нет доступа к группе-источнику.", "forbidden")


# ---------------------------------------------------------------------------
# Lessons and mapping
# ---------------------------------------------------------------------------

def lessons(group: Group, subject: Subject, start: dt.date, end: dt.date) -> list[Lesson]:
    """The group's held-or-planned, not cancelled lessons of `subject` in the period, in order."""
    return list(
        Lesson.objects.filter(group=group, subject=subject, date__gte=start, date__lte=end)
        .exclude(status=Lesson.Status.CANCELLED)
        .select_related("teacher__user", "group_teacher__teacher__user")
        .order_by("date", "start_time", "pk")
    )


def suggest_map(source: list[Lesson], target: list[Lesson]) -> list[tuple[int, int]]:
    """n-th lesson → n-th lesson. Only a suggestion the administrator reviews."""
    return [(s.pk, t.pk) for s, t in zip(source, target)]


def _homeworks(lesson_ids) -> dict[int, list[Homework]]:
    result: dict[int, list[Homework]] = defaultdict(list)
    for hw in Homework.objects.filter(lesson_id__in=lesson_ids).order_by("created_at", "pk"):
        result[hw.lesson_id].append(hw)
    return result


@dataclass
class Pair:
    index: int
    source: Lesson | None
    target: Lesson | None
    source_id: int
    target_id: int
    problem: str | None = None
    homework_pairs: list[tuple[Homework, Homework]] = field(default_factory=list)
    homework_problem: str | None = None

    @property
    def valid(self) -> bool:
        return self.problem is None


def build_pairs(req: CopyRequest, source: list[Lesson], target: list[Lesson], gate: access.LessonGate) -> list[Pair]:
    by_source = {lesson.pk: lesson for lesson in source}
    by_target = {lesson.pk: lesson for lesson in target}
    raw = req.lesson_map if req.lesson_map is not None else suggest_map(source, target)
    today = timezone.localdate()
    homeworks = _homeworks([*by_source, *by_target]) if req.categories & {Category.HOMEWORK, Category.SCORES} else {}

    pairs: list[Pair] = []
    seen_source: set[int] = set()
    seen_target: set[int] = set()
    for index, (source_id, target_id) in enumerate(raw):
        pair = Pair(index=index, source=by_source.get(source_id), target=by_target.get(target_id),
                    source_id=source_id, target_id=target_id)
        pairs.append(pair)
        if pair.source is None:
            pair.problem = "Занятие-источник не входит в выбранные группу, предмет и период."
        elif pair.target is None:
            pair.problem = "Целевое занятие не входит в выбранные группу, предмет и период."
        elif source_id == target_id:
            pair.problem = "Занятие нельзя скопировать само в себя."
        elif source_id in seen_source:
            pair.problem = "Это занятие-источник уже сопоставлено."
        elif target_id in seen_target:
            pair.problem = "Это целевое занятие уже выбрано для другого занятия."
        elif pair.target.date > today:
            pair.problem = "Целевое занятие ещё не прошло — отметки в нём ставить нельзя."
        else:
            pair.problem = gate.write_problem(pair.target)
        seen_source.add(source_id)
        seen_target.add(target_id)
        if not pair.valid or not homeworks:
            continue
        src_hw, tgt_hw = homeworks.get(source_id, []), homeworks.get(target_id, [])
        if not src_hw:
            continue  # nothing to copy for homework in this pair
        if pair.target.homework_not_required or not tgt_hw:
            pair.homework_problem = "У целевого занятия нет домашнего задания — результаты ДЗ не копируются."
        elif len(src_hw) != len(tgt_hw):
            pair.homework_problem = f"Разное число домашних заданий ({len(src_hw)} → {len(tgt_hw)}) — результаты ДЗ не копируются."
        else:
            pair.homework_pairs = list(zip(src_hw, tgt_hw))
    return pairs


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

def _ser(value):
    if isinstance(value, dt.datetime):
        return value.isoformat()
    return value


def att_values(record: Attendance | None) -> dict | None:
    if record is None:
        return None
    return {"status": normalize_status(record.status) or record.status, "excuse_reason": record.excuse_reason,
            "comment": record.comment}


def hw_values(record: HomeworkResult | None) -> dict | None:
    if record is None:
        return None
    return {name: _ser(getattr(record, name)) for name in HW_FIELDS}


def _empty(value) -> bool:
    return value is None or value == ""


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

@dataclass
class Record:
    kind: str  # attendance | homework_result
    student: Student
    pair: Pair
    action: str
    source: Attendance | HomeworkResult | None = None
    target: Attendance | HomeworkResult | None = None
    target_homework: Homework | None = None
    values: dict | None = None
    problem: str | None = None

    @property
    def target_values(self) -> dict | None:
        return att_values(self.target) if self.kind == BulkCopyItem.Kind.ATTENDANCE else hw_values(self.target)

    @property
    def source_values(self) -> dict | None:
        return att_values(self.source) if self.kind == BulkCopyItem.Kind.ATTENDANCE else hw_values(self.source)


@dataclass
class Plan:
    request: CopyRequest
    source_lessons: list[Lesson]
    target_lessons: list[Lesson]
    pairs: list[Pair]
    students: list[dict]
    records: list[Record]

    def count(self, *actions) -> int:
        return sum(1 for r in self.records if r.action in actions)

    @property
    def writes(self) -> list[Record]:
        return [r for r in self.records if r.action in WRITES]

    def summary(self) -> dict:
        by_status = defaultdict(int)
        for student in self.students:
            by_status[student["status"]] += 1
        att_lessons = {r.pair.target_id for r in self.writes if r.kind == BulkCopyItem.Kind.ATTENDANCE}
        return {
            "students_matched": by_status["matched"],
            "students_unmatched": by_status["not_in_target_group"],
            "students_without_source": by_status["no_source_records"],
            "students_not_selected": by_status["not_selected"],
            "pairs": len(self.pairs),
            "invalid_pairs": sum(1 for p in self.pairs if not p.valid),
            "homework_problems": sum(1 for p in self.pairs if p.valid and p.homework_problem),
            "to_copy": self.count(*WRITES),
            "create": self.count(CREATE),
            "overwrite": self.count(OVERWRITE),
            "unchanged": self.count(UNCHANGED),
            "skip_existing": self.count(SKIP_EXISTING),
            "empty": self.count(EMPTY),
            "existing_target": sum(1 for r in self.records if r.target is not None),
            "invalid_records": self.count(INVALID),
            "attendance": sum(1 for r in self.writes if r.kind == BulkCopyItem.Kind.ATTENDANCE),
            "homework_results": sum(1 for r in self.writes if r.kind == BulkCopyItem.Kind.HOMEWORK_RESULT),
            # Saving attendance re-syncs billing write-offs of these lessons.
            "billing_lessons": len(att_lessons),
        }

    def fingerprint(self) -> str:
        payload = [
            (r.kind, r.student.pk, r.pair.source_id, r.pair.target_id,
             r.target_homework.pk if r.target_homework else None, r.action,
             r.target.pk if r.target else None, r.target_values, r.values)
            for r in self.records
        ]
        pairs = [(p.source_id, p.target_id, p.problem, p.homework_problem) for p in self.pairs]
        blob = json.dumps([self.request.to_json(), pairs, payload], sort_keys=True, default=str)
        return hashlib.sha256(blob.encode()).hexdigest()


def _att_new(req: CopyRequest, src: Attendance, tgt: Attendance | None) -> tuple[dict | None, str | None]:
    status = normalize_status(src.status)
    if status is None:
        return None, f"Неизвестный статус посещаемости в источнике: «{src.status}»."
    current = att_values(tgt) or {"status": None, "excuse_reason": "", "comment": ""}
    values = {"status": status, "excuse_reason": "", "comment": current["comment"]}
    if status == Attendance.Status.EXCUSED:
        reason = src.excuse_reason or (current["excuse_reason"] if req.skip_empty else "")
        if not reason:
            return None, "Уважительная причина не указана в источнике — отметка не копируется."
        values["excuse_reason"] = reason
    if req.copy_comments and not (req.skip_empty and _empty(src.comment)):
        values["comment"] = src.comment
    return values, None


def _hw_new(req: CopyRequest, src: HomeworkResult, tgt: HomeworkResult | None) -> dict:
    current = hw_values(tgt) or {"status": HomeworkResult.Status.NOT_SUBMITTED, "score": None, "comment": "",
                                 "submitted_at": None, "checked_at": None}
    source = hw_values(src)
    values = dict(current)
    fields: list[str] = []
    if Category.HOMEWORK in req.categories or tgt is None:
        # A new result for a score alone still needs the status it was given with.
        fields += ["status", "submitted_at", "checked_at"]
    if Category.SCORES in req.categories:
        fields.append("score")
    if req.copy_comments:
        fields.append("comment")
    for name in fields:
        if req.skip_empty and _empty(source[name]) and name not in ("status", "submitted_at", "checked_at"):
            continue
        values[name] = source[name]
    return values


def _decide(req: CopyRequest, current: dict | None, values: dict) -> str:
    if current is None:
        return CREATE
    if current == values:
        return UNCHANGED
    return OVERWRITE if req.overwrite else SKIP_EXISTING


def plan(req: CopyRequest, user, *, lock: bool = False) -> Plan:
    validate_request(req, user)
    gate = access.LessonGate(user)
    source = lessons(req.source_group, req.source_subject, req.source_start, req.source_end)
    target = lessons(req.target_group, req.target_subject, req.target_start, req.target_end)
    pairs = build_pairs(req, source, target, gate)
    valid = [p for p in pairs if p.valid]

    want_att = Category.ATTENDANCE in req.categories
    want_hw = bool(req.categories & {Category.HOMEWORK, Category.SCORES})
    src_lessons = [p.source_id for p in valid]
    tgt_lessons = [p.target_id for p in valid]
    src_hw = [s.pk for p in valid for s, _ in p.homework_pairs]
    tgt_hw = [t.pk for p in valid for _, t in p.homework_pairs]

    src_att = {(a.lesson_id, a.student_id): a for a in Attendance.objects.filter(lesson_id__in=src_lessons)} if want_att else {}
    src_res = {(r.homework_id, r.student_id): r for r in HomeworkResult.objects.filter(homework_id__in=src_hw)} if want_hw else {}

    tgt_att_qs = Attendance.objects.filter(lesson_id__in=tgt_lessons)
    tgt_res_qs = HomeworkResult.objects.filter(homework_id__in=tgt_hw)
    if lock:
        tgt_att_qs, tgt_res_qs = tgt_att_qs.select_for_update(), tgt_res_qs.select_for_update()
    tgt_att = {(a.lesson_id, a.student_id): a for a in tgt_att_qs} if want_att else {}
    tgt_res = {(r.homework_id, r.student_id): r for r in tgt_res_qs} if want_hw else {}

    # Students — by id only.
    source_ids = {sid for _, sid in src_att} | {sid for _, sid in src_res}
    target_ids = set(Student.objects.filter(group=req.target_group).values_list("pk", flat=True))
    selected = None if req.student_ids is None else set(req.student_ids)
    everyone = Student.objects.filter(pk__in=source_ids | target_ids).select_related("group").order_by(
        "last_name", "first_name", "pk")
    students, matched = [], []
    for student in everyone:
        if student.pk not in target_ids:
            status = "not_in_target_group"
        elif student.pk not in source_ids:
            status = "no_source_records"
        elif selected is not None and student.pk not in selected:
            status = "not_selected"
        else:
            status = "matched"
            matched.append(student)
        students.append({"id": student.pk, "name": f"{student.last_name} {student.first_name}".strip(),
                         "group": student.group.name if student.group_id else None, "status": status})

    records: list[Record] = []
    for pair in valid:
        for student in matched:
            if want_att:
                src = src_att.get((pair.source_id, student.pk))
                tgt = tgt_att.get((pair.target_id, student.pk))
                rec = Record(kind=BulkCopyItem.Kind.ATTENDANCE, student=student, pair=pair, action=EMPTY,
                             source=src, target=tgt)
                if src is not None:
                    values, problem = _att_new(req, src, tgt)
                    if problem:
                        rec.action, rec.problem = INVALID, problem
                    else:
                        rec.values, rec.action = values, _decide(req, att_values(tgt), values)
                records.append(rec)
            for shw, thw in pair.homework_pairs:
                src = src_res.get((shw.pk, student.pk))
                tgt = tgt_res.get((thw.pk, student.pk))
                rec = Record(kind=BulkCopyItem.Kind.HOMEWORK_RESULT, student=student, pair=pair, action=EMPTY,
                             source=src, target=tgt, target_homework=thw)
                if src is not None:
                    rec.values = _hw_new(req, src, tgt)
                    rec.action = _decide(req, hw_values(tgt), rec.values)
                records.append(rec)
    return Plan(request=req, source_lessons=source, target_lessons=target, pairs=pairs, students=students,
                records=records)


# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

def _parse_dt(value):
    return dt.datetime.fromisoformat(value) if value else None


def _write_attendance(rec: Record, user) -> tuple[Attendance, dict | None]:
    before = att_values(rec.target)
    mark = rec.target or Attendance(lesson=rec.pair.target, student=rec.student)
    mark.status = rec.values["status"]
    mark.excuse_reason = rec.values["excuse_reason"]
    mark.comment = rec.values["comment"]
    mark.updated_by = user
    mark.full_clean()
    mark.save()  # apps.billing re-syncs this lesson's write-offs after commit
    changes = {name: [(before or {}).get(name), rec.values[name]] for name in ATT_FIELDS
               if (before or {}).get(name) != rec.values[name]}
    changes = {("attendance" if k == "status" else k): v for k, v in changes.items()}
    AttendanceChangeLog.objects.create(lesson=rec.pair.target, student=rec.student, attendance=mark, actor=user,
                                       actor_role=access.actor_role(user), changes=changes)
    return mark, before


def _write_result(rec: Record) -> tuple[HomeworkResult, dict | None]:
    before = hw_values(rec.target)
    result = rec.target or HomeworkResult(homework=rec.target_homework, student=rec.student)
    for name in ("status", "score", "comment"):
        setattr(result, name, rec.values[name])
    result.submitted_at = _parse_dt(rec.values["submitted_at"])
    result.checked_at = _parse_dt(rec.values["checked_at"])
    result.full_clean()
    result.save()
    return result, before


def execute(operation: BulkCopyOperation) -> BulkCopyOperation:
    """Runs a queued operation (inline or from the Celery task). All or nothing."""
    user = operation.created_by
    try:
        with transaction.atomic():
            op = BulkCopyOperation.objects.select_for_update().get(pk=operation.pk)
            if op.status not in (BulkCopyOperation.Status.QUEUED, BulkCopyOperation.Status.RUNNING):
                return op
            if not access.can_use(user):
                raise CopyError("Нет прав на массовое копирование.", "forbidden")
            req = CopyRequest.from_json(op.request)
            current = plan(req, user, lock=True)
            if current.fingerprint() != op.fingerprint:
                raise CopyError("Данные изменились после предпросмотра. Обновите предпросмотр и проверьте его ещё раз.",
                                "conflict")
            if current.count(OVERWRITE) and not op.request.get("confirm_overwrite"):
                raise CopyError(f"Будет перезаписано записей: {current.count(OVERWRITE)}. Подтвердите перезапись.",
                                "confirmation_required")
            if not current.writes:
                raise CopyError("Нечего копировать: все записи пропущены или уже совпадают.")

            items = []
            for rec in current.writes:
                if rec.kind == BulkCopyItem.Kind.ATTENDANCE:
                    obj, before = _write_attendance(rec, user)
                    after, extra = att_values(obj), {"attendance": obj}
                else:
                    obj, before = _write_result(rec)
                    after, extra = hw_values(obj), {"homework_result": obj}
                items.append(BulkCopyItem(
                    operation=op, kind=rec.kind, student=rec.student, source_lesson=rec.pair.source,
                    target_lesson=rec.pair.target, action=BulkCopyItem.Action.CREATED if before is None
                    else BulkCopyItem.Action.OVERWRITTEN, before=before, after=after, **extra,
                ))
            BulkCopyItem.objects.bulk_create(items)

            skipped = {name: current.count(name) for name in (UNCHANGED, SKIP_EXISTING, EMPTY, INVALID)
                       if current.count(name)}
            if current.summary()["invalid_pairs"]:
                skipped["invalid_pairs"] = current.summary()["invalid_pairs"]
            op.status = BulkCopyOperation.Status.APPLIED
            op.copied_count = current.count(CREATE)
            op.overwritten_count = current.count(OVERWRITE)
            op.skipped_count = sum(v for k, v in skipped.items() if k != "invalid_pairs")
            op.skipped_details = skipped
            op.finished_at = timezone.now()
            op.save()
            return op
    except (CopyError, ValidationError) as exc:
        message = exc.message if isinstance(exc, CopyError) else " ".join(exc.messages)
        BulkCopyOperation.objects.filter(pk=operation.pk).update(
            status=BulkCopyOperation.Status.FAILED, error=message, finished_at=timezone.now())
        if isinstance(exc, CopyError):
            raise
        raise CopyError(message) from exc
    except Exception as exc:  # noqa: BLE001 — recorded, then re-raised; the transaction is already rolled back
        BulkCopyOperation.objects.filter(pk=operation.pk).update(
            status=BulkCopyOperation.Status.FAILED, error=f"Внутренняя ошибка: {exc.__class__.__name__}",
            finished_at=timezone.now())
        raise


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------

def undo(operation: BulkCopyOperation, *, user) -> BulkCopyOperation:
    from apps.billing.services.lessons import sync_lesson_safely

    with transaction.atomic():
        op = BulkCopyOperation.objects.select_for_update().get(pk=operation.pk)
        if op.status != BulkCopyOperation.Status.APPLIED:
            raise CopyError("Отменить можно только применённую операцию, и только один раз.", "conflict")
        items = list(op.items.select_for_update().order_by("pk"))
        att = {a.pk: a for a in Attendance.objects.select_for_update().filter(
            pk__in=[i.attendance_id for i in items if i.attendance_id])}
        res = {r.pk: r for r in HomeworkResult.objects.select_for_update().filter(
            pk__in=[i.homework_result_id for i in items if i.homework_result_id])}
        results: dict[str, int] = defaultdict(int)
        resync: set[int] = set()
        for item in items:
            is_att = item.kind == BulkCopyItem.Kind.ATTENDANCE
            obj = att.get(item.attendance_id) if is_att else res.get(item.homework_result_id)
            current = (att_values(obj) if is_att else hw_values(obj)) if obj is not None else None
            if obj is None:
                item.undo_result = BulkCopyItem.UndoResult.SKIPPED_MISSING
            elif current != item.after:
                # Changed by someone after the copy — their change is never undone.
                item.undo_result = BulkCopyItem.UndoResult.SKIPPED_CHANGED
            elif item.action == BulkCopyItem.Action.CREATED:
                if is_att:
                    AttendanceChangeLog.objects.create(
                        lesson_id=obj.lesson_id, student_id=obj.student_id, attendance=None, actor=user,
                        actor_role=access.actor_role(user),
                        changes={"attendance": [obj.status, None]})
                    resync.add(obj.lesson_id)  # billing has no post_delete hook for Attendance
                obj.delete()
                item.undo_result = BulkCopyItem.UndoResult.DELETED
            else:
                if is_att:
                    for name in ATT_FIELDS:
                        setattr(obj, name, item.before[name])
                    obj.updated_by = user
                    obj.save()
                    AttendanceChangeLog.objects.create(
                        lesson_id=obj.lesson_id, student_id=obj.student_id, attendance=obj, actor=user,
                        actor_role=access.actor_role(user),
                        changes={f: [item.after[k], item.before[k]] for k, f in (("status", "attendance"), ("excuse_reason", "excuse_reason"), ("comment", "comment")) if item.after[k] != item.before[k]})
                else:
                    for name in ("status", "score", "comment"):
                        setattr(obj, name, item.before[name])
                    obj.submitted_at = _parse_dt(item.before["submitted_at"])
                    obj.checked_at = _parse_dt(item.before["checked_at"])
                    obj.save()
                item.undo_result = BulkCopyItem.UndoResult.RESTORED
            results[item.undo_result] += 1
        BulkCopyItem.objects.bulk_update(items, ["undo_result"])
        for lesson_id in resync:
            transaction.on_commit(lambda lesson_id=lesson_id: sync_lesson_safely(lesson_id))

        kept = results[BulkCopyItem.UndoResult.SKIPPED_CHANGED] + results[BulkCopyItem.UndoResult.SKIPPED_MISSING]
        op.status = BulkCopyOperation.Status.PARTIALLY_REVERTED if kept else BulkCopyOperation.Status.REVERTED
        op.reverted_by, op.reverted_at, op.revert_details = user, timezone.now(), dict(results)
        op.save(update_fields=["status", "reverted_by", "reverted_at", "revert_details"])
        return op
