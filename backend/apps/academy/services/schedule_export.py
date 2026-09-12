"""Export for GroupSchedule (Card 3 "Экспорт расписания").

Export-only, deliberately: GroupSchedule rows are validated against live
teacher/room conflicts and auto-derive `group_teacher` on save (see
`models.GroupSchedule.clean`/`save`), which makes a safe bulk-import path
meaningfully more complex than Student/Group's plain field upserts. The
task's own scope only calls for an export button here, so no importer is
built for it — see the module-level scope note in admin_views.py.
"""
from __future__ import annotations

from django.db.models import QuerySet
from django.http import HttpResponse

from apps.users.import_export.formats import build_export_response

from ..models import GroupSchedule

EXPORT_FIELDS = [
    "group",
    "teacher",
    "subject",
    "day_of_week",
    "start_time",
    "end_time",
    "room",
    "is_active",
]


def export_schedules(queryset: QuerySet[GroupSchedule], fmt: str = "csv") -> HttpResponse:
    rows = []
    for schedule in queryset.select_related("group", "teacher__user", "subject", "room"):
        rows.append(
            {
                "group": schedule.group.name,
                "teacher": str(schedule.teacher),
                "subject": schedule.subject.name if schedule.subject_id else "",
                "day_of_week": schedule.get_day_of_week_display(),
                "start_time": schedule.start_time.strftime("%H:%M"),
                "end_time": schedule.end_time.strftime("%H:%M"),
                "room": schedule.room.name if schedule.room_id else "",
                "is_active": schedule.is_active,
            }
        )
    return build_export_response(rows, EXPORT_FIELDS, fmt, "schedule")
