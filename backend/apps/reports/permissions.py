"""Who may build parent reports, for which groups, over whose lessons.

Follows the LMS's existing access rules — nothing new is invented:

* Admin / superuser — every group, every lesson; may generate.
* Team Lead — reads the whole academy (``can_view_academy``) but never
  writes: preview, history and downloads only, no generation.
* Trainer — only their own groups (``Group.objects.for_teacher``, the same
  rule as «Мои группы») and only the lessons they give
  (``LessonQuerySet.for_teacher`` isolation: another trainer's lessons in a
  shared group are never counted, so ``teacher_id`` scopes the analytics).
  The history shows only the reports built on their own lessons.
* Assistant, Director, Accountant and the staff-only roles have no KPI access
  in the LMS, so no access to reports either.
"""
from __future__ import annotations

from django.db.models import QuerySet
from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.academy.models import Group
from apps.users.models import User
from apps.users.permissions import can_view_academy, is_admin_user, is_team_lead

from .models import ParentReport


def teacher_of(user):
    """The trainer profile of a Trainer account, else None."""
    if not getattr(user, "is_authenticated", False) or getattr(user, "role", None) != User.Role.TEACHER:
        return None
    return getattr(user, "teacher_profile", None)


def can_use_reports(user) -> bool:
    return can_view_academy(user) or teacher_of(user) is not None


def teacher_scope(user):
    """Whose lessons the analytics count: None (all) for Admin / Team Lead,
    the trainer themselves for a Trainer."""
    return None if can_view_academy(user) else teacher_of(user)


def accessible_groups(user) -> QuerySet[Group]:
    if can_view_academy(user):
        return Group.objects.all()
    teacher = teacher_of(user)
    if teacher is None:
        return Group.objects.none()
    return Group.objects.for_teacher(teacher)


def accessible_reports(user) -> QuerySet[ParentReport]:
    qs = ParentReport.objects.select_related("created_by", "teacher_scope__user").prefetch_related("images")
    if can_view_academy(user):
        return qs
    teacher = teacher_of(user)
    if teacher is None:
        return qs.none()
    return qs.filter(teacher_scope=teacher, group__in=Group.objects.for_teacher(teacher))


class CanUseParentReports(BasePermission):
    message = "Отчёты для родителей доступны администратору, руководителю тренеров и тренерам своих групп."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not can_use_reports(user):
            return False
        if request.method not in SAFE_METHODS and is_team_lead(user) and not is_admin_user(user):
            self.message = "Руководитель тренеров может только просматривать отчёты."
            return False
        return True
