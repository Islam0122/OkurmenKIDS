"""Who may see and change program settings (checked on the server).

* Admin, Operations director — every program, full access.
* Team Lead — the programs of their directions (TeamLeadDirection; none
  assigned — every program), view and change.
* Director, Trainer, Assistant — view only.
"""
from __future__ import annotations

from django.db.models import Q

from apps.academy.models import Course
from apps.attendance_matrix.access import lead_subject_ids
from apps.users.models import User

EDITORS = (User.Role.ADMIN, User.Role.OPERATIONS_DIRECTOR, User.Role.TEAM_LEAD)
VIEWERS = (*EDITORS, User.Role.DIRECTOR, User.Role.TEACHER, User.Role.ASSISTANT)


def _active(user) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False) and user.is_active)


def can_view(user) -> bool:
    return _active(user) and (user.is_superuser or user.role in VIEWERS)


def visible_courses(user):
    qs = Course.objects.all()
    if _active(user) and user.role == User.Role.TEAM_LEAD:
        subjects = lead_subject_ids(user)
        if subjects:
            qs = qs.filter(Q(subjects__in=subjects) | Q(curriculum__main_subject__in=subjects)).distinct()
    return qs if can_view(user) else qs.none()


def can_edit(user, course: Course | None = None) -> bool:
    if not _active(user):
        return False
    if user.is_superuser or user.role in (User.Role.ADMIN, User.Role.OPERATIONS_DIRECTOR):
        return True
    if user.role == User.Role.TEAM_LEAD:
        return course is None or visible_courses(user).filter(pk=course.pk).exists()
    return False
