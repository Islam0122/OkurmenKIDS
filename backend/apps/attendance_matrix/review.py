"""What a Team Lead / Operations director checks besides the numbers:
the excused absences with their reasons, how assistants work in the
matrix, and the journal of changes — always for the lessons the overview
already scoped to the user (their groups, month, trainer filter)."""
from __future__ import annotations

from collections import defaultdict

from apps.academy.models import Attendance, Lesson

from .cells import FIELD_LABELS, _display, _user_ref
from .matrix import status_q
from .models import AttendanceChangeLog

LIMIT = 200


def _live(lessons):
    return lessons.exclude(status=Lesson.Status.CANCELLED)


def excused(lessons) -> list[dict]:
    """Every «уважительная причина» of the period with its reason —
    a missing reason is flagged so it can be checked."""
    rows = (
        Attendance.objects.filter(status_q(Attendance.Status.EXCUSED), lesson__in=_live(lessons))
        .select_related("student", "lesson__group", "updated_by")
        .order_by("-lesson__date", "student__last_name")[:LIMIT]
    )
    return [
        {
            "id": a.pk,
            "student": {"id": a.student_id, "name": str(a.student)},
            "group": {"id": a.lesson.group_id, "name": a.lesson.group.name},
            "lesson_id": a.lesson_id,
            "date": a.lesson.date,
            "reason": a.excuse_reason,
            "comment": a.comment,
            "missing_reason": not a.excuse_reason.strip(),
            "updated_by": _user_ref(a.updated_by),
        }
        for a in rows
    ]


def assistants(lessons) -> list[dict]:
    """Assistants' work in the matrix for the period: how many cells they
    changed, in which groups, and when last."""
    logs = (
        AttendanceChangeLog.objects.filter(lesson__in=lessons, actor_role="assistant", actor__isnull=False)
        .select_related("actor", "lesson__group")
    )
    out: dict[int, dict] = {}
    groups: dict[int, set] = defaultdict(set)
    students: dict[int, set] = defaultdict(set)
    for log in logs:
        row = out.setdefault(log.actor_id, {"user": _user_ref(log.actor), "changes": 0, "attendance_changes": 0,
                                            "homework_changes": 0, "comments": 0, "last_change": None})
        row["changes"] += 1
        row["attendance_changes"] += "attendance" in log.changes
        row["homework_changes"] += "homework" in log.changes
        row["comments"] += "comment" in log.changes
        if row["last_change"] is None or log.created_at > row["last_change"]:
            row["last_change"] = log.created_at
        groups[log.actor_id].add(log.lesson.group.name)
        students[log.actor_id].add(log.student_id)
    result = [{**row, "groups": sorted(groups[uid]), "students": len(students[uid])} for uid, row in out.items()]
    result.sort(key=lambda r: (-r["changes"], r["user"]["name"]))
    return result


def history(lessons, limit: int = 100) -> list[dict]:
    """The latest changes of the period's cells, newest first."""
    logs = (
        AttendanceChangeLog.objects.filter(lesson__in=lessons)
        .select_related("actor", "student", "lesson__group")[:limit]
    )
    return [
        {
            "id": log.pk,
            "at": log.created_at,
            "actor": _user_ref(log.actor),
            "actor_role": log.actor_role,
            "student": {"id": log.student_id, "name": str(log.student)},
            "group": {"id": log.lesson.group_id, "name": log.lesson.group.name},
            "lesson_id": log.lesson_id,
            "date": log.lesson.date,
            "changes": [
                {"field": f, "label": FIELD_LABELS.get(f, f), "before": _display(f, v[0]), "after": _display(f, v[1])}
                for f, v in log.changes.items()
            ],
        }
        for log in logs
    ]
