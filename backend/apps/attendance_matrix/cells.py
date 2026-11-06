"""One cell of the matrix: read it, change it, see its history.

A change writes the academy's own records — ``Attendance`` for attendance
(status, reason, comment) and ``HomeworkResult`` for each homework of the
lesson — in one transaction, and appends an ``AttendanceChangeLog`` row with
who changed what. Attendance and homework stay two separate records.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.academy.models import Attendance, Homework, HomeworkResult, Lesson, Student
from apps.academy.services import lesson_lifecycle

from . import access
from .matrix import HW_DONE, HW_LABELS, homework_status, is_held
from .models import AttendanceChangeLog, MatrixSettings

ATTENDANCE_LABELS = dict(Attendance.Status.choices)
FIELD_LABELS = {
    "attendance": "Посещаемость",
    "excuse_reason": "Причина отсутствия",
    "comment": "Комментарий",
    "homework": "Домашнее задание",
}


class CellError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _user_ref(user) -> dict | None:
    if user is None:
        return None
    return {"id": user.pk, "name": user.get_full_name() or user.username, "role": user.role}


def _display(field: str, value):
    if value in (None, ""):
        return "—"
    if field == "attendance":
        return ATTENDANCE_LABELS.get(value, value)
    if field == "homework":
        return HW_LABELS.get(value, value)
    return value


def history(lesson: Lesson, student: Student, limit: int = 50) -> list[dict]:
    rows = AttendanceChangeLog.objects.filter(lesson=lesson, student=student).select_related("actor")[:limit]
    return [
        {
            "id": row.pk,
            "at": row.created_at,
            "actor": _user_ref(row.actor),
            "actor_role": row.actor_role,
            "changes": [
                {"field": f, "label": FIELD_LABELS.get(f, f), "before": _display(f, v[0]), "after": _display(f, v[1])}
                for f, v in row.changes.items()
            ],
        }
        for row in rows
    ]


def resolve(user, lesson_id, student_id) -> tuple[Lesson, Student]:
    try:
        lesson = Lesson.objects.select_related("group__course", "subject", "teacher__user",
                                               "group_teacher__teacher__user").get(pk=int(lesson_id))
        student = Student.objects.get(pk=int(student_id))
    except (Lesson.DoesNotExist, Student.DoesNotExist, TypeError, ValueError):
        raise CellError("Запись не найдена.", 404) from None
    if not access.can_view_group(user, lesson.group):
        raise CellError("Запись не найдена.", 404)
    if not access.scoped_lessons(user, [lesson.group_id]).filter(pk=lesson.pk).exists():
        raise CellError("Запись не найдена.", 404)
    return lesson, student


def detail(user, lesson: Lesson, student: Student) -> dict:
    today = timezone.localdate()
    mark = Attendance.objects.filter(lesson=lesson, student=student).select_related("updated_by").first()
    homeworks = list(Homework.objects.filter(lesson=lesson).order_by("pk"))
    results = {(r.homework_id, r.student_id): r for r in HomeworkResult.objects.filter(homework__in=homeworks, student=student)}
    hw = homework_status(lesson, homeworks, results, student.pk, today)
    level, reason = access.edit_level(user, lesson)
    if lesson.date > today and level != access.NONE:
        level, reason = access.NONE, "Занятие ещё не прошло — отметить его можно в день занятия."
    if student.group_id != lesson.group_id and level != access.NONE:
        level, reason = access.NONE, "Студент больше не учится в этой группе."
    last_log = AttendanceChangeLog.objects.filter(lesson=lesson, student=student).select_related("actor").first()
    return {
        "student": {"id": student.pk, "name": str(student)},
        "group": {"id": lesson.group_id, "name": lesson.group.name},
        "lesson": {
            "id": lesson.pk,
            "date": lesson.date,
            "start": lesson.start_time.strftime("%H:%M"),
            "end": lesson.end_time.strftime("%H:%M"),
            "topic": lesson.topic,
            "number": lesson.lesson_number,
            "subject": lesson.subject.name if lesson.subject_id else "",
            "teacher": str(lesson.effective_teacher) if lesson.effective_teacher else "",
            "status": lesson.status,
            "status_display": lesson.get_status_display(),
            "held": is_held(lesson, today),
        },
        "attendance": mark.status if mark else None,
        "excuse_reason": mark.excuse_reason if mark else "",
        "comment": mark.comment if mark else "",
        "homework": hw,
        "homeworks": [
            {
                "id": h.pk,
                "title": h.title,
                "deadline": h.deadline,
                "status": results[(h.pk, student.pk)].status if (h.pk, student.pk) in results else None,
                "status_display": results[(h.pk, student.pk)].get_status_display() if (h.pk, student.pk) in results else "Нет результата",
            }
            for h in homeworks
        ],
        "homework_not_required": lesson.homework_not_required,
        "updated_by": _user_ref(mark.updated_by) if mark and mark.updated_by_id else (_user_ref(last_log.actor) if last_log else None),
        "updated_at": (last_log.created_at if last_log else None) or (mark.updated_at if mark else None),
        "edit_level": level,
        "edit_reason": reason,
        "history": history(lesson, student),
    }


VALID_ATTENDANCE = {c for c, _ in Attendance.Status.choices}


@transaction.atomic
def update(user, lesson: Lesson, student: Student, data: dict) -> dict:
    """Apply `data` ({attendance?, excuse_reason?, comment?, homework?}) to
    the cell. Every check is repeated here, whatever the UI offered."""
    today = timezone.localdate()
    level, reason = access.edit_level(user, lesson, MatrixSettings.load())
    if level == access.NONE:
        raise CellError(reason or "Нет прав на изменение.", 403)
    if lesson.date > today:
        raise CellError("Занятие ещё не прошло — отметить его можно в день занятия.")
    if student.group_id != lesson.group_id:
        raise CellError("Студент не принадлежит группе этого занятия.")

    mark = Attendance.objects.select_for_update().filter(lesson=lesson, student=student).first()
    before = {
        "attendance": mark.status if mark else None,
        "excuse_reason": mark.excuse_reason if mark else "",
        "comment": mark.comment if mark else "",
    }
    homeworks = list(Homework.objects.filter(lesson=lesson).order_by("pk"))
    results = {(r.homework_id, r.student_id): r for r in HomeworkResult.objects.select_for_update().filter(
        homework__in=homeworks, student=student)}
    before["homework"] = homework_status(lesson, homeworks, results, student.pk, today)

    after = dict(before)
    if "comment" in data:
        after["comment"] = str(data.get("comment") or "").strip()[:255]
    if level == access.COMMENT:
        extra = [k for k in ("attendance", "excuse_reason", "homework") if k in data and data[k] != before[k]]
        if extra:
            raise CellError("Вы можете только оставлять комментарии.", 403)
        if mark is None:
            raise CellError("Сначала нужно отметить посещаемость.")
    else:
        if "attendance" in data:
            value = data.get("attendance")
            if value not in VALID_ATTENDANCE and value is not None:
                raise CellError("Неверный статус посещаемости.")
            after["attendance"] = value
        if "excuse_reason" in data:
            after["excuse_reason"] = str(data.get("excuse_reason") or "").strip()[:255]
        if "homework" in data and data.get("homework") != before["homework"]:
            value = data.get("homework")
            if value not in ("done", "missed"):
                raise CellError("Неверный статус домашнего задания.")
            if not homeworks or lesson.homework_not_required:
                raise CellError("На этом занятии нет домашнего задания.")
            after["homework"] = value

    if after["attendance"] == Attendance.Status.EXCUSED:
        if not after["excuse_reason"]:
            raise CellError("Укажите уважительную причину отсутствия.")
    else:
        after["excuse_reason"] = ""
    if after["attendance"] is None and (after["comment"] and after["comment"] != before["comment"]):
        raise CellError("Сначала нужно отметить посещаемость.")

    changes = {f: [before[f], after[f]] for f in before if before[f] != after[f]}
    if not changes:
        return detail(user, lesson, student)

    # Attendance
    if after["attendance"] is None:
        if mark is not None:
            if access.role_of(user) != access.ADMIN and lesson_lifecycle.lesson_editing_locked(lesson):
                raise CellError("Занятие завершено — отметку можно изменить, но не удалить.", 403)
            mark.delete()
            mark = None
    elif any(f in changes for f in ("attendance", "excuse_reason", "comment")):
        if mark is None:
            mark = Attendance(lesson=lesson, student=student)
        mark.status = after["attendance"]
        mark.excuse_reason = after["excuse_reason"]
        mark.comment = after["comment"]
        mark.updated_by = user
        mark.save()

    # Homework — every homework of the lesson.
    if "homework" in changes:
        now = timezone.now()
        for hw in homeworks:
            result = results.get((hw.pk, student.pk))
            if after["homework"] == "done":
                if result is not None and result.status in HW_DONE:
                    continue
                if result is None:
                    result = HomeworkResult(homework=hw, student=student)
                result.status = HomeworkResult.Status.SUBMITTED
                result.submitted_at = result.submitted_at or now
            else:
                if result is None:
                    result = HomeworkResult(homework=hw, student=student)
                result.status = HomeworkResult.Status.NOT_SUBMITTED
                result.submitted_at = None
                result.checked_at = None
            result.save()

    AttendanceChangeLog.objects.create(
        lesson=lesson, student=student, attendance=mark, actor=user,
        actor_role=access.role_of(user) or "", changes=changes,
    )
    return detail(user, lesson, student)
