"""A group's academic configuration — who teaches what, on which days, when
and where — as one editable unit for the Team Lead («Учебная конфигурация»).

Nothing new is stored. The configuration *is* the existing data:

    Group
      └── GroupTeacher (Teaching Program: trainer + subject; one per subject,
          │             several trainers per group are possible)
          └── GroupSchedule[] (one weekly slot each: weekday, start, end, room)

and every write goes through services.program_editing.save_teaching_program —
the admin Workspace's own «Сохранить»: trainer / subject change, and the
program's slot list made exactly the given one (created / changed / removed)
in one transaction, with every slot validated by GroupSchedule.clean():
end after start, active trainer / subject / room, and no overlap with the
trainer's, the room's or the group's other slots (touching ends — 14:00–15:30
and 15:30–17:00 — are not an overlap). Lesson generation then uses each
slot's own day, time and room (services.lesson_generator).

Each save is written to Django's admin history (LogEntry) of the program,
with the configuration before and after.
"""
from __future__ import annotations

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.users.models import Subject, Teacher

from ..constants import WEEKDAY_CODES, WEEKDAY_LABELS_FULL, WEEKDAY_LABELS_SHORT
from ..models import Group, GroupTeacher, Room
from .program_editing import parse_schedule_specs, save_teaching_program
from .trainer_history import acting_user
from .trainer_assignment import _last_change, _user_label, available_trainers

_WEEKDAY_NAMES = {
    "monday": "mon", "tuesday": "tue", "wednesday": "wed", "thursday": "thu",
    "friday": "fri", "saturday": "sat", "sunday": "sun",
}


def _slot_row(slot) -> dict:
    return {
        "id": slot.pk,
        "day": slot.day_of_week,
        "day_label": WEEKDAY_LABELS_FULL.get(slot.day_of_week, slot.day_of_week),
        "start": slot.start_time.strftime("%H:%M"),
        "end": slot.end_time.strftime("%H:%M"),
        "room": {"id": slot.room_id, "name": slot.room.name} if slot.room_id else None,
        "is_active": slot.is_active,
    }


def _program_row(program: GroupTeacher) -> dict:
    entry = _last_change(program)
    slots = sorted(
        program.schedules.select_related("room").all(),
        key=lambda s: (WEEKDAY_CODES.index(s.day_of_week), s.start_time),
    )
    return {
        "id": program.pk,
        "subject": {"id": program.subject_id, "name": program.subject.name} if program.subject_id else None,
        "teacher": {"id": program.teacher_id, "name": str(program.teacher)},
        "is_active": program.is_active,
        "has_lessons": program.lessons.exists(),
        "assigned_by": _user_label(entry.user) if entry else None,
        "assigned_at": entry.action_time if entry else program.updated_at,
        "slots": [_slot_row(slot) for slot in slots],
    }


def config_overview(group: Group) -> dict:
    programs = group.teachers.select_related("teacher__user", "subject").order_by("-is_active", "subject__name", "id")
    return {
        "group": {"id": group.pk, "name": group.name, "course": group.course.name, "status": group.status},
        "programs": [_program_row(p) for p in programs],
        "subjects": [{"id": s.pk, "name": s.name} for s in group.course.subjects.filter(is_active=True).order_by("name")],
        "trainers": [
            {"id": t.pk, "name": str(t), "subjects": [s.name for s in t.subjects.all()]}
            for t in available_trainers()
        ],
        "rooms": [
            {"id": r.pk, "name": r.name, "capacity": r.capacity}
            for r in Room.objects.filter(is_active=True).order_by("name")
        ],
        "weekdays": [{"code": code, "label": WEEKDAY_LABELS_FULL[code]} for code in WEEKDAY_CODES],
    }


def normalize_slot_items(items) -> list:
    """Accept the existing slot format ({id, day: "mon", start, end, room})
    and the friendlier aliases (weekday 1–7 / "monday", start_time, end_time,
    room_id) — then hand it to parse_schedule_specs, which validates it."""
    if not isinstance(items, list):
        raise ValidationError({"schedule": ["Некорректные данные расписания."]})
    normalized = []
    for item in items:
        if not isinstance(item, dict):
            raise ValidationError({"schedule": ["Некорректные данные расписания."]})
        day = item.get("day", item.get("weekday"))
        if isinstance(day, int) and not isinstance(day, bool) and 1 <= day <= 7:
            day = WEEKDAY_CODES[day - 1]
        elif isinstance(day, str):
            day = _WEEKDAY_NAMES.get(day.strip().lower(), day.strip().lower())
        if day not in WEEKDAY_CODES:
            raise ValidationError({"schedule": [f"Неизвестный день недели: «{item.get('day', item.get('weekday'))}»."]})
        room = item.get("room", item.get("room_id"))
        if isinstance(room, dict):
            room = room.get("id")
        normalized.append({
            "id": item.get("id"),
            "day": day,
            "start": item.get("start", item.get("start_time")),
            "end": item.get("end", item.get("end_time")),
            "room": room if room not in ("", None) else None,
        })
    return normalized


def describe(program: GroupTeacher | None) -> str:
    if program is None:
        return "—"
    slots = sorted(
        program.schedules.filter(is_active=True).select_related("room"),
        key=lambda s: (WEEKDAY_CODES.index(s.day_of_week), s.start_time),
    )
    schedule = ", ".join(
        f"{WEEKDAY_LABELS_SHORT[s.day_of_week]} {s.start_time:%H:%M}–{s.end_time:%H:%M}"
        + (f" ({s.room.name})" if s.room_id else "")
        for s in slots
    ) or "без расписания"
    subject = program.subject.name if program.subject_id else "без предмета"
    return f"Тренер: {program.teacher}; Предмет: {subject}; {schedule}"


def _as_field_errors(exc: ValidationError) -> ValidationError:
    if hasattr(exc, "error_dict"):
        return exc
    return ValidationError({"schedule": exc.messages})


@transaction.atomic
def save_program_config(group: Group, *, user, teacher: Teacher, subject: Subject | None, slot_items,
                        program: GroupTeacher | None = None) -> GroupTeacher:
    """See _save_program_config; trainer changes are recorded as made by `user`."""
    with acting_user(user):
        return _save_program_config(group, user=user, teacher=teacher, subject=subject, slot_items=slot_items,
                                    program=program)


def _save_program_config(group: Group, *, user, teacher: Teacher, subject: Subject | None, slot_items,
                         program: GroupTeacher | None = None) -> GroupTeacher:
    """Create (``program`` None) or update one Teaching Program of ``group``:
    trainer, subject and the exact list of its weekly slots. All or nothing;
    raises ValidationError keyed by field (slot problems under "schedule")."""
    if program is not None and program.group_id != group.pk:
        raise ValidationError({"program": ["Эта программа относится к другой группе."]})
    if subject is None:
        raise ValidationError({"subject": ["Выберите предмет."]})

    created = False
    before = describe(program)
    if program is None:
        existing = group.teachers.filter(subject=subject).select_related("teacher__user")
        if existing.filter(is_active=True).exists():
            raise ValidationError({
                "subject": [f"У группы уже есть программа по предмету «{subject.name}» — измените её."]
            })
        program = existing.filter(teacher=teacher).first()
        if program is None:
            program = GroupTeacher(group=group, teacher=teacher, subject=subject)
            program.full_clean()
            program.save()
            created = True
        before = describe(program) if not created else "—"

    try:
        specs = parse_schedule_specs(program, normalize_slot_items(slot_items))
        save_teaching_program(
            program, teacher=teacher, subject=subject, is_active=True,
            reassign_future_lessons=True, slots=specs,
        )
    except ValidationError as exc:
        raise _as_field_errors(exc)

    program.refresh_from_db()
    after = describe(program)
    LogEntry.objects.log_actions(
        user_id=user.pk, queryset=[program], action_flag=ADDITION if created else CHANGE,
        change_message=f"Учебная конфигурация группы «{group.name}». Было: {before}. Стало: {after}.",
        single_object=True,
    )
    return program
