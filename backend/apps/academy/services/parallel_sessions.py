"""Parallel lessons (shared classroom sessions): several groups study at the
same time, in one room, with ONE shared trainer — one actual lesson.

Data model (see models.ParallelSession):

* `ParallelSession` holds what is shared: trainer, room, date, start–end,
  topic, materials, notes and the session status.
* Every participating group keeps its own regular `Lesson` row
  (`Lesson.parallel_session`), in the group's own program (GroupTeacher) and
  with the session's trainer as `Lesson.teacher`. Attendance, homework,
  homework results, the lesson lifecycle, the attendance matrix, the student
  portal and payroll cycles therefore keep working per group, exactly as for
  any other lesson — students of different groups are never mixed, and no
  second attendance or homework system exists.
* `ParallelSessionGroup` is the participation history: removing a group
  marks the row «removed» and cancels (never deletes) its lesson.

Conflicts. A session occupies its trainer and its room once, and each of its
groups. It is checked against every live (not cancelled) Lesson — regular
lessons and the lessons of other parallel sessions alike, through the one
check the schedule board uses (services.schedule_board.find_conflicts) — and
against other open sessions (a session whose groups were all removed still
holds its trainer and room). Lessons of the *same* session never conflict
with each other. Touching ends (15:00–16:00 and 16:00–17:00) never clash.

Concurrency. Every write runs in one transaction that first locks the
trainer, the room and every group involved (always in the same order, so
two writers can't deadlock): two sessions that share any of them are
serialised and the second one sees the first one's lessons when it checks
for conflicts. The group lock is the same one lesson generation and
rescheduling take (services.lesson_generator / lesson_reschedule). On SQLite
row locks are a no-op (tests); on PostgreSQL they are real.

Payroll. One session = one lesson of each participating group (its
course progress) and ONE conducted session of the trainer. Payroll cycles
(apps.accounting.services.cycles) count completed lessons per group and
subject; the unique constraint `unique_active_parallel_session_group_lesson`
guarantees a session gives each group exactly one lesson, so no group's
cycle can count it twice, and re-saving/completing the session again never
adds anything. Salary rules are unchanged — see docs/parallel_lessons.md.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Q
from django.utils import timezone

from apps.users.models import Subject, Teacher

from ..models import (
    Attendance,
    CourseLessonPlan,
    Group,
    GroupTeacher,
    GroupTeacherLessonPlan,
    Homework,
    HomeworkResult,
    Lesson,
    ParallelSession,
    ParallelSessionGroup,
    Room,
    Student,
)
from . import lesson_lifecycle
from .schedule_board import CONFLICT_LABELS, find_conflicts
from .subject_start import check_lesson_date

Status = ParallelSession.Status
OPEN = (Status.SCHEDULED, Status.IN_PROGRESS)
LIVE_LESSON = ~Q(status=Lesson.Status.CANCELLED)

# Fields copied from the session to every participating group's lesson.
SHARED_CONTENT_FIELDS = ("topic", "description", "youtube_url", "presentation_urls")
SHARED_TIME_FIELDS = ("date", "start_time", "end_time")


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

@dataclass
class SessionInput:
    teacher: Teacher
    room: Room
    date: dt.date
    start_time: dt.time
    end_time: dt.time
    groups: list[Group]
    subject: Subject | None = None
    topic: str = ""
    description: str = ""
    notes: str = ""
    youtube_url: str = ""
    presentation_urls: list | None = None
    programs: dict[int, int] | None = None  # group id -> GroupTeacher id (optional override)


def _validate_basics(*, teacher: Teacher, room: Room, start_time: dt.time, end_time: dt.time) -> None:
    errors = {}
    if end_time <= start_time:
        errors["end_time"] = "Время окончания должно быть позже времени начала."
    if not teacher.is_active:
        errors["teacher"] = "Тренер должен быть активным."
    if not room.is_active:
        errors["room"] = "Аудитория должна быть активной."
    if errors:
        raise ValidationError(errors)


def _validate_groups(groups: list[Group]) -> None:
    if not groups:
        raise ValidationError({"groups": "Выберите хотя бы одну группу."})
    ids = [g.pk for g in groups]
    duplicates = sorted({g.name for g in groups if ids.count(g.pk) > 1})
    if duplicates:
        raise ValidationError({"groups": f"Группа указана несколько раз: {', '.join(duplicates)}."})
    closed = [g.name for g in groups if g.status != Group.Status.ACTIVE]
    if closed:
        raise ValidationError({"groups": f"Группа не активна: {', '.join(closed)}."})


# ---------------------------------------------------------------------------
# Programs and lesson numbers
# ---------------------------------------------------------------------------

def resolve_program(group: Group, teacher: Teacher, subject: Subject | None = None,
                    program_id: int | None = None) -> GroupTeacher:
    """The group's own program (GroupTeacher) the session's lesson belongs
    to — the program's lesson sequence, numbering and payroll cycle (per
    subject) are the group's. The session's trainer is recorded on the
    lesson itself (Lesson.teacher), exactly like a substitute trainer, so
    no new teacher assignment is ever created as a side effect."""
    active = GroupTeacher.objects.filter(group=group, is_active=True).select_related("subject", "teacher")
    if program_id:
        program = active.filter(pk=program_id).first()
        if program is None:
            raise ValidationError({"programs": f"Программа {program_id} не относится к группе «{group.name}» или не активна."})
        return program
    candidates = list(active.filter(subject=subject)) if subject is not None else list(active)
    if not candidates:
        what = f" по предмету «{subject.name}»" if subject is not None else ""
        raise ValidationError({"groups": f"У группы «{group.name}» нет активной учебной программы{what}."})
    own = [p for p in candidates if p.teacher_id == teacher.pk]
    if own:
        return sorted(own, key=lambda p: p.pk)[0]
    if len(candidates) == 1 or subject is not None:
        return sorted(candidates, key=lambda p: p.pk)[0]
    raise ValidationError({
        "groups": (
            f"У группы «{group.name}» несколько учебных программ — укажите предмет занятия "
            "или программу группы."
        ),
    })


def next_lesson_number(program: GroupTeacher) -> int:
    """A number past both the program's lessons and its plan: a session's
    lesson is an extra lesson of the program — the generator only ever
    creates lessons for plan rows, so it never claims (or skips) this
    number. Called under the group's lock."""
    used = Lesson.objects.filter(group_teacher=program).aggregate(m=Max("lesson_number"))["m"] or 0
    individual = GroupTeacherLessonPlan.objects.filter(group_teacher=program).aggregate(m=Max("lesson_number"))["m"]
    if individual is not None:
        planned = individual
    else:
        planned = CourseLessonPlan.objects.filter(course_id=program.group.course_id).aggregate(
            m=Max("lesson_number"))["m"] or 0
    return max(used, planned) + 1


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------

def _session_ref(session: ParallelSession) -> dict:
    return {
        "id": session.pk,
        "date": session.date,
        "start": session.start_time.strftime("%H:%M"),
        "end": session.end_time.strftime("%H:%M"),
        "teacher": {"id": session.teacher_id, "name": str(session.teacher)},
        "room": {"id": session.room_id, "name": session.room.name},
    }


def find_session_conflicts(*, date: dt.date, start_time: dt.time, end_time: dt.time, teacher: Teacher | None,
                           room: Room | None, groups: list[Group],
                           exclude_session_id: int | None = None) -> list[dict]:
    """Every clash a session at date/start–end with this trainer, room and
    groups would cause: [{"kind", "kind_label", "message", "lesson"|"session"}].
    Read only — the preview of the create/edit form and the check every
    write repeats under its locks."""
    found: list[dict] = []
    reported_sessions: set[int] = set()

    # Other open sessions holding the trainer or the room.
    others = (
        ParallelSession.objects.filter(status__in=OPEN, date=date, start_time__lt=end_time, end_time__gt=start_time)
        .filter(Q(teacher=teacher) | Q(room=room))
        .select_related("teacher__user", "room")
    )
    if exclude_session_id:
        others = others.exclude(pk=exclude_session_id)
    for other in others.order_by("start_time", "pk"):
        when = f"{other.start_time:%H:%M}–{other.end_time:%H:%M}"
        if teacher is not None and other.teacher_id == teacher.pk:
            found.append({"kind": "teacher", "kind_label": CONFLICT_LABELS["teacher"], "session": _session_ref(other),
                          "message": f"Тренер «{teacher}» уже ведёт параллельное занятие №{other.pk} ({when})."})
        if room is not None and other.room_id == room.pk:
            found.append({"kind": "room", "kind_label": CONFLICT_LABELS["room"], "session": _session_ref(other),
                          "message": f"Аудитория «{room.name}» уже занята параллельным занятием №{other.pk} ({when})."})
        reported_sessions.add(other.pk)

    def add(items):
        for item in items:
            other_session = (item["lesson"].get("parallel_session") or {}).get("id")
            if other_session in reported_sessions and item["kind"] in ("teacher", "room"):
                continue  # already reported once for the whole session
            found.append(item)

    common = dict(date=date, start_time=start_time, end_time=end_time,
                  exclude_parallel_session_id=exclude_session_id)
    add(find_conflicts(teacher_id=teacher.pk if teacher else None, room_id=room.pk if room else None,
                       teacher_name=str(teacher) if teacher else "", room_name=room.name if room else "", **common))
    for group in groups:
        add(find_conflicts(group_id=group.pk, group_name=group.name, **common))

    # One entry per (kind, other lesson/session).
    unique, seen = [], set()
    for item in found:
        key = (item["kind"], ("s", item["session"]["id"]) if "session" in item else ("l", item["lesson"]["id"]))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _raise_if_conflicts(conflicts: list[dict]) -> None:
    if conflicts:
        raise ValidationError({"conflicts": [c["message"] for c in conflicts]})


# ---------------------------------------------------------------------------
# Locking and logging
# ---------------------------------------------------------------------------

def _lock(*, teacher_ids=(), room_ids=(), group_ids=()) -> None:
    """Lock trainers, rooms, then groups — always by pk, always in this
    order — so concurrent writers touching the same resources serialise and
    never deadlock."""
    for model, ids in ((Teacher, teacher_ids), (Room, room_ids), (Group, group_ids)):
        ids = sorted({i for i in ids if i})
        if ids:
            list(model.objects.select_for_update().filter(pk__in=ids).order_by("pk").values_list("pk", flat=True))


def _lock_session(session: ParallelSession) -> ParallelSession:
    return ParallelSession.objects.select_for_update(of=("self",)).select_related("teacher__user", "room", "subject").get(
        pk=session.pk)


def _log(user, session: ParallelSession, message: str, flag: int = CHANGE) -> None:
    if user is None or not getattr(user, "pk", None):
        return
    LogEntry.objects.log_actions(user_id=user.pk, queryset=[session], action_flag=flag, change_message=message,
                                 single_object=True)


def history(session: ParallelSession) -> list[dict]:
    """The session's change log (Django admin history, newest first)."""
    content_type = ContentType.objects.get_for_model(ParallelSession)
    entries = (
        LogEntry.objects.filter(content_type=content_type, object_id=str(session.pk))
        .select_related("user").order_by("-action_time", "-pk")
    )
    return [
        {"at": e.action_time, "user": (e.user.get_full_name() or e.user.username) if e.user_id else None,
         "action": {ADDITION: "created", CHANGE: "changed"}.get(e.action_flag, "changed"),
         "message": e.get_change_message()}
        for e in entries
    ]


# ---------------------------------------------------------------------------
# Group lessons
# ---------------------------------------------------------------------------

def _live_lessons(session: ParallelSession):
    return Lesson.objects.filter(parallel_session=session).filter(LIVE_LESSON)


def _create_group_lesson(session: ParallelSession, group: Group, program: GroupTeacher) -> Lesson:
    lesson = Lesson(
        group=group,
        group_teacher=program,
        teacher=session.teacher,
        subject_id=program.subject_id or session.subject_id,
        lesson_number=next_lesson_number(program),
        date=session.date,
        start_time=session.start_time,
        end_time=session.end_time,
        room=session.room,
        topic=session.topic,
        description=session.description,
        youtube_url=session.youtube_url,
        presentation_urls=list(session.presentation_urls or []),
        status=Lesson.Status.SCHEDULED,
        # Not tied to a weekly slot: slot edits, «Сгенерировать занятия» and
        # subject re-planning never move it (services.schedule_lesson_sync).
        schedule_overridden=True,
        parallel_session=session,
    )
    check_lesson_date(lesson, session.date)
    try:
        with transaction.atomic():
            lesson.save()
    except IntegrityError:
        raise ValidationError({"groups": f"Группа «{group.name}» уже участвует в этом занятии."})
    return lesson


def _join(session: ParallelSession, group: Group, program_id: int | None, user) -> ParallelSessionGroup:
    program = resolve_program(group, session.teacher, session.subject, program_id)
    lesson = _create_group_lesson(session, group, program)
    participant, created = ParallelSessionGroup.objects.get_or_create(
        session=session, group=group,
        defaults={"lesson": lesson, "added_by": user if getattr(user, "pk", None) else None},
    )
    if not created:
        if participant.status == ParallelSessionGroup.Status.ACTIVE:
            raise ValidationError({"groups": f"Группа «{group.name}» уже участвует в этом занятии."})
        participant.status = ParallelSessionGroup.Status.ACTIVE
        participant.lesson = lesson
        participant.added_by = user if getattr(user, "pk", None) else None
        participant.added_at = timezone.now()
        participant.removed_by, participant.removed_at, participant.removal_reason = None, None, ""
        participant.save()
    return participant


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------

def create_session(data: SessionInput, user=None) -> ParallelSession:
    _validate_basics(teacher=data.teacher, room=data.room, start_time=data.start_time, end_time=data.end_time)
    _validate_groups(data.groups)
    programs = data.programs or {}
    with transaction.atomic():
        _lock(teacher_ids=[data.teacher.pk], room_ids=[data.room.pk], group_ids=[g.pk for g in data.groups])
        _raise_if_conflicts(find_session_conflicts(
            date=data.date, start_time=data.start_time, end_time=data.end_time,
            teacher=data.teacher, room=data.room, groups=data.groups,
        ))
        session = ParallelSession.objects.create(
            teacher=data.teacher, room=data.room, subject=data.subject, date=data.date,
            start_time=data.start_time, end_time=data.end_time, topic=data.topic, description=data.description,
            notes=data.notes, youtube_url=data.youtube_url, presentation_urls=list(data.presentation_urls or []),
            created_by=user if getattr(user, "pk", None) else None,
        )
        for group in sorted(data.groups, key=lambda g: g.name):
            _join(session, group, programs.get(group.pk), user)
        _log(user, session, (
            f"Создано: {session.date:%d.%m.%Y} {session.start_time:%H:%M}–{session.end_time:%H:%M}, "
            f"тренер {session.teacher}, аудитория {session.room.name}, группы: "
            f"{', '.join(sorted(g.name for g in data.groups))}."
        ), ADDITION)
    return session


def update_session(session: ParallelSession, changes: dict, user=None) -> ParallelSession:
    """Edit a scheduled session. Date/time/room/trainer are re-checked for
    conflicts and applied to every participating group's lesson; content
    (topic, description, materials) is copied to them too. A session in
    progress accepts content and notes only."""
    allowed_scheduling = {"teacher", "room", "subject", *SHARED_TIME_FIELDS}
    with transaction.atomic():
        current = ParallelSession.objects.get(pk=session.pk)
        group_ids = list(ParallelSessionGroup.objects.filter(session=current, status=ParallelSessionGroup.Status.ACTIVE)
                         .values_list("group_id", flat=True))
        teacher = changes.get("teacher", current.teacher)
        room = changes.get("room", current.room)
        _lock(teacher_ids=[current.teacher_id, teacher.pk], room_ids=[current.room_id, room.pk], group_ids=group_ids)
        session = _lock_session(current)
        if not session.is_open:
            raise ValidationError({"status": f"Нельзя изменить занятие в статусе «{session.get_status_display()}»."})
        scheduling = {k: v for k, v in changes.items() if k in allowed_scheduling and v != getattr(session, k)}
        if scheduling and session.status != Status.SCHEDULED:
            raise ValidationError({"status": "Дату, время, аудиторию и тренера можно менять только до начала занятия."})

        before = f"{session.date:%d.%m.%Y} {session.start_time:%H:%M}–{session.end_time:%H:%M}, {session.teacher}, {session.room.name}"
        for name, value in changes.items():
            setattr(session, name, value)
        _validate_basics(teacher=session.teacher, room=session.room, start_time=session.start_time,
                         end_time=session.end_time)
        if scheduling:
            groups = list(Group.objects.filter(pk__in=group_ids))
            _raise_if_conflicts(find_session_conflicts(
                date=session.date, start_time=session.start_time, end_time=session.end_time,
                teacher=session.teacher, room=session.room, groups=groups, exclude_session_id=session.pk,
            ))
        session.save()

        lesson_fields = [*SHARED_CONTENT_FIELDS, *SHARED_TIME_FIELDS]
        for lesson in _live_lessons(session).select_related("subject"):
            if scheduling and "date" in scheduling:
                check_lesson_date(lesson, session.date)
            for name in lesson_fields:
                setattr(lesson, name, getattr(session, name))
            lesson.room_id = session.room_id
            lesson.teacher_id = session.teacher_id
            lesson.save(update_fields=[*lesson_fields, "room", "teacher", "updated_at"])

        changed = sorted(changes)
        if changed:
            after = f"{session.date:%d.%m.%Y} {session.start_time:%H:%M}–{session.end_time:%H:%M}, {session.teacher}, {session.room.name}"
            detail = f" ({before} → {after})" if scheduling else ""
            _log(user, session, f"Изменено: {', '.join(changed)}{detail}.")
    return session


def add_group(session: ParallelSession, group: Group, user=None, program_id: int | None = None) -> ParallelSessionGroup:
    _validate_groups([group])
    with transaction.atomic():
        _lock(teacher_ids=[session.teacher_id], room_ids=[session.room_id], group_ids=[group.pk])
        session = _lock_session(session)
        if session.status != Status.SCHEDULED:
            raise ValidationError({"status": "Добавлять группы можно только в запланированное занятие."})
        if ParallelSessionGroup.objects.filter(session=session, group=group,
                                               status=ParallelSessionGroup.Status.ACTIVE).exists():
            raise ValidationError({"groups": f"Группа «{group.name}» уже участвует в этом занятии."})
        _raise_if_conflicts(find_session_conflicts(
            date=session.date, start_time=session.start_time, end_time=session.end_time,
            teacher=None, room=None, groups=[group], exclude_session_id=session.pk,
        ))
        participant = _join(session, group, program_id, user)
        _log(user, session, f"Добавлена группа «{group.name}».")
    return participant


def remove_group(session: ParallelSession, group: Group, user=None, reason: str = "") -> ParallelSessionGroup:
    """Take a group out of an open session: its participation row stays
    («removed»), its lesson is cancelled — never deleted, with whatever
    attendance/homework it already has."""
    with transaction.atomic():
        _lock(group_ids=[group.pk])
        session = _lock_session(session)
        if not session.is_open:
            raise ValidationError({"status": "Состав проведённого или отменённого занятия не меняется."})
        participant = ParallelSessionGroup.objects.select_for_update().filter(
            session=session, group=group, status=ParallelSessionGroup.Status.ACTIVE).first()
        if participant is None:
            raise ValidationError({"groups": f"Группа «{group.name}» не участвует в этом занятии."})
        if not ParallelSessionGroup.objects.filter(session=session, status=ParallelSessionGroup.Status.ACTIVE).exclude(
                pk=participant.pk).exists():
            raise ValidationError({"groups": "Это последняя группа занятия — отмените занятие целиком."})
        for lesson in _live_lessons(session).filter(group=group):
            if lesson.status == Lesson.Status.COMPLETED:
                raise ValidationError({"groups": f"Занятие группы «{group.name}» уже проведено — исключить нельзя."})
            lesson_lifecycle.cancel_lesson(lesson, user, reason or "Группа исключена из параллельного занятия.")
        participant.status = ParallelSessionGroup.Status.REMOVED
        participant.removed_by = user if getattr(user, "pk", None) else None
        participant.removed_at = timezone.now()
        participant.removal_reason = reason
        participant.save()
        _log(user, session, f"Исключена группа «{group.name}»{f': {reason}' if reason else ''}.")
    return participant


def start_session(session: ParallelSession, user=None) -> ParallelSession:
    with transaction.atomic():
        session = _lock_session(session)
        if session.status == Status.IN_PROGRESS:
            return session
        if session.status != Status.SCHEDULED:
            raise ValidationError({"status": f"Нельзя начать занятие в статусе «{session.get_status_display()}»."})
        for lesson in _live_lessons(session).select_for_update(of=("self",)):
            lesson_lifecycle.start_lesson(lesson, user)
        session.status = Status.IN_PROGRESS
        session.save(update_fields=["status", "updated_at"])
        _log(user, session, "Занятие начато.")
    return session


def complete_session(session: ParallelSession, user=None) -> ParallelSession:
    """Complete the session and every participating group's lesson — each
    under the regular completion rules (attendance marked for every student,
    homework added or «ДЗ не требуется»). All or nothing: if any group's
    lesson isn't ready, nothing is completed and the missing items are listed
    per group. Idempotent."""
    with transaction.atomic():
        session = _lock_session(session)
        if session.status == Status.COMPLETED:
            return session
        if session.status == Status.CANCELLED:
            raise ValidationError({"status": "Отменённое занятие нельзя завершить."})
        lessons = list(_live_lessons(session).select_for_update(of=("self",)).select_related("group"))
        if not lessons:
            raise ValidationError({"groups": "В занятии нет ни одной группы."})
        problems = []
        for lesson in lessons:
            if lesson.status == Lesson.Status.COMPLETED:
                continue  # this group's lesson was already completed on its own
            lesson_lifecycle.start_lesson(lesson, user)
            missing = [r.label for r in lesson_lifecycle.completion_requirements(lesson) if not r.satisfied]
            if missing:
                problems.append(f"«{lesson.group.name}»: {', '.join(missing)}")
        if problems:
            raise ValidationError({"completion": problems})
        counts = _active_students_by_group([lesson.group_id for lesson in lessons])
        for lesson in lessons:
            lesson_lifecycle.complete_lesson(lesson, user)
            ParallelSessionGroup.objects.filter(session=session, group_id=lesson.group_id).update(
                students_count=counts.get(lesson.group_id, 0))
        session.status = Status.COMPLETED
        session.completed_at = timezone.now()
        session.completed_by = user if getattr(user, "pk", None) else None
        session.save(update_fields=["status", "completed_at", "completed_by", "updated_at"])
        _log(user, session, "Занятие проведено.")
    return session


def cancel_session(session: ParallelSession, user=None, reason: str = "") -> ParallelSession:
    """Cancel the session and every participating group's lesson (kept as
    history with its data; topics are not shifted — the session is an extra
    lesson of each program). A completed session can't be cancelled.
    Idempotent."""
    with transaction.atomic():
        session = _lock_session(session)
        if session.status == Status.CANCELLED:
            return session
        if session.status == Status.COMPLETED:
            raise ValidationError({"status": "Нельзя отменить уже проведённое занятие."})
        for lesson in _live_lessons(session).select_for_update(of=("self",)):
            lesson_lifecycle.cancel_lesson(lesson, user, reason or "Параллельное занятие отменено.")
        session.status = Status.CANCELLED
        session.cancellation_reason = reason
        session.cancelled_at = timezone.now()
        session.cancelled_by = user if getattr(user, "pk", None) else None
        session.save(update_fields=["status", "cancellation_reason", "cancelled_at", "cancelled_by", "updated_at"])
        _log(user, session, f"Занятие отменено{f': {reason}' if reason else ''}.")
    return session


def add_shared_homework(session: ParallelSession, *, title: str, description: str = "", deadline=None,
                        group_ids: list[int] | None = None) -> list[Homework]:
    """Shared homework: one regular Homework per participating group's
    lesson (or only the listed groups — group-specific homework). The same
    Homework model and results as any lesson; nothing parallel to it."""
    if not title.strip():
        raise ValidationError({"title": "Укажите название задания."})
    with transaction.atomic():
        session = _lock_session(session)
        if session.status == Status.CANCELLED:
            raise ValidationError({"status": "Занятие отменено."})
        lessons = _live_lessons(session)
        if group_ids:
            known = set(lessons.values_list("group_id", flat=True))
            unknown = sorted(set(group_ids) - known)
            if unknown:
                raise ValidationError({"groups": f"Группы не участвуют в занятии: {unknown}."})
            lessons = lessons.filter(group_id__in=group_ids)
        return [Homework.objects.create(lesson=lesson, title=title, description=description, deadline=deadline)
                for lesson in lessons.order_by("group__name")]


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def teaching_occasions(lessons) -> int:
    """How many lessons a trainer actually gave among `lessons` (a Lesson
    queryset): every regular lesson, plus each parallel session once —
    however many of its groups' lessons are in the queryset."""
    return (lessons.filter(parallel_session__isnull=True).count()
            + lessons.filter(parallel_session__isnull=False).order_by().values("parallel_session").distinct().count())


def _active_students_by_group(group_ids) -> dict[int, int]:
    return dict(
        Student.objects.filter(group_id__in=list(group_ids), status=Student.Status.ACTIVE)
        .values_list("group_id").annotate(n=Count("id")).values_list("group_id", "n")
    )


def roster(session: ParallelSession) -> list[dict]:
    """Students grouped by their own group, each with their attendance on
    that group's lesson of the session (or None — not marked yet)."""
    lessons = {lesson.group_id: lesson for lesson in _live_lessons(session).select_related("group")}
    marks = {
        (a.lesson_id, a.student_id): a
        for a in Attendance.objects.filter(lesson__in=list(lessons.values()))
    }
    students = defaultdict(list)
    for student in (Student.objects.filter(group_id__in=list(lessons), is_active=True)
                    .order_by("last_name", "first_name")):
        students[student.group_id].append(student)
    rows = []
    for group_id, lesson in sorted(lessons.items(), key=lambda item: item[1].group.name):
        entries = []
        for student in students.get(group_id, []):
            mark = marks.get((lesson.pk, student.pk))
            entries.append({
                "student": student.pk, "student_name": str(student),
                "status": mark.status if mark else None,
                "status_display": mark.get_status_display() if mark else None,
                "comment": mark.comment if mark else "",
                "excuse_reason": mark.excuse_reason if mark else "",
            })
        rows.append({"group": {"id": group_id, "name": lesson.group.name}, "lesson": lesson.pk,
                     "lesson_status": lesson.status, "students": entries})
    return rows


def statistics(session: ParallelSession) -> dict:
    """Per group and in total: students, attendance by status, homework."""
    lessons = list(_live_lessons(session).select_related("group"))
    lesson_ids = [lesson.pk for lesson in lessons]
    attendance = defaultdict(lambda: defaultdict(int))
    for lesson_id, status, n in (Attendance.objects.filter(lesson_id__in=lesson_ids)
                                 .values_list("lesson_id", "status").annotate(n=Count("id"))):
        attendance[lesson_id][status] = n
    homework = dict(Homework.objects.filter(lesson_id__in=lesson_ids).values_list("lesson_id")
                    .annotate(n=Count("id")).values_list("lesson_id", "n"))
    results = defaultdict(lambda: defaultdict(int))
    for lesson_id, status, n in (HomeworkResult.objects.filter(homework__lesson_id__in=lesson_ids)
                                 .values_list("homework__lesson_id", "status").annotate(n=Count("id"))):
        results[lesson_id][status] = n
    snapshot = dict(ParallelSessionGroup.objects.filter(session=session, students_count__isnull=False)
                    .values_list("group_id", "students_count"))
    live_counts = _active_students_by_group([lesson.group_id for lesson in lessons])

    statuses = Attendance.Status.values
    groups, totals = [], {"students": 0, "marked": 0, **{s: 0 for s in statuses}}
    for lesson in sorted(lessons, key=lambda l: l.group.name):
        counts = {s: attendance[lesson.pk].get(s, 0) for s in statuses}
        students = snapshot.get(lesson.group_id, live_counts.get(lesson.group_id, 0))
        marked = sum(counts.values())
        attended = counts["present"] + counts["late"]
        groups.append({
            "group": {"id": lesson.group_id, "name": lesson.group.name},
            "lesson": lesson.pk,
            "lesson_status": lesson.status,
            "students": students,
            "marked": marked,
            **counts,
            "attendance_rate": round(attended / marked * 100, 1) if marked else None,
            "homework": homework.get(lesson.pk, 0),
            "homework_results": dict(results[lesson.pk]),
        })
        totals["students"] += students
        totals["marked"] += marked
        for s in statuses:
            totals[s] += counts[s]
    attended = totals["present"] + totals["late"]
    totals["attendance_rate"] = round(attended / totals["marked"] * 100, 1) if totals["marked"] else None
    totals["groups"] = len(groups)
    return {"session": session.pk, "status": session.status, "groups": groups, "totals": totals}


def analytics(*, start: dt.date, end: dt.date, teacher_id: int | None = None) -> dict:
    """Period report: sessions by status, participating groups and students,
    trainer workload (one session = one conducted lesson), attendance by
    group, the list of sessions."""
    sessions = ParallelSession.objects.filter(date__gte=start, date__lte=end)
    if teacher_id:
        sessions = sessions.filter(teacher_id=teacher_id)
    sessions = list(sessions.select_related("teacher__user", "room").order_by("-date", "-start_time"))
    ids = [s.pk for s in sessions]
    participants = list(ParallelSessionGroup.objects.filter(session_id__in=ids, status=ParallelSessionGroup.Status.ACTIVE)
                        .select_related("group"))
    by_session = defaultdict(list)
    for p in participants:
        by_session[p.session_id].append(p)
    live_counts = _active_students_by_group({p.group_id for p in participants})

    def students_of(p):
        return p.students_count if p.students_count is not None else live_counts.get(p.group_id, 0)

    by_status = defaultdict(int)
    workload: dict[int, dict] = {}
    for s in sessions:
        by_status[s.status] += 1
        row = workload.setdefault(s.teacher_id, {"teacher": {"id": s.teacher_id, "name": str(s.teacher)},
                                                 "sessions": 0, "completed": 0, "groups": 0, "minutes": 0})
        if s.status == Status.CANCELLED:
            continue
        row["sessions"] += 1
        row["groups"] += len(by_session[s.pk])
        if s.status == Status.COMPLETED:
            row["completed"] += 1
            start_dt = dt.datetime.combine(s.date, s.start_time)
            row["minutes"] += int((dt.datetime.combine(s.date, s.end_time) - start_dt).total_seconds() // 60)

    attendance_by_group = defaultdict(lambda: {"present": 0, "absent": 0, "late": 0, "excused": 0})
    names = {}
    rows = (Attendance.objects.filter(lesson__parallel_session_id__in=ids)
            .exclude(lesson__status=Lesson.Status.CANCELLED)
            .values_list("lesson__group_id", "lesson__group__name", "status").annotate(n=Count("id")))
    for group_id, group_name, status, n in rows:
        attendance_by_group[group_id][status] += n
        names[group_id] = group_name
    attendance = []
    for group_id, counts in sorted(attendance_by_group.items(), key=lambda item: names[item[0]]):
        marked = sum(counts.values())
        attendance.append({"group": {"id": group_id, "name": names[group_id]}, **counts, "marked": marked,
                           "attendance_rate": round((counts["present"] + counts["late"]) / marked * 100, 1)
                           if marked else None})

    live_sessions = [s for s in sessions if s.status != Status.CANCELLED]
    return {
        "start": start,
        "end": end,
        "totals": {
            "sessions": len(sessions),
            "scheduled": by_status[Status.SCHEDULED],
            "in_progress": by_status[Status.IN_PROGRESS],
            "completed": by_status[Status.COMPLETED],
            "cancelled": by_status[Status.CANCELLED],
            "group_participations": sum(len(by_session[s.pk]) for s in live_sessions),
            "groups": len({p.group_id for s in live_sessions for p in by_session[s.pk]}),
            "students": sum(students_of(p) for s in live_sessions for p in by_session[s.pk]),
        },
        "workload": sorted(workload.values(), key=lambda r: (-r["sessions"], r["teacher"]["name"])),
        "attendance_by_group": attendance,
        "sessions": [
            {"id": s.pk, "date": s.date, "start": s.start_time.strftime("%H:%M"), "end": s.end_time.strftime("%H:%M"),
             "teacher": str(s.teacher), "room": s.room.name, "status": s.status,
             "status_display": s.get_status_display(), "topic": s.topic,
             "groups": [p.group.name for p in sorted(by_session[s.pk], key=lambda p: p.group.name)],
             "students": sum(students_of(p) for p in by_session[s.pk])}
            for s in sessions
        ],
    }
