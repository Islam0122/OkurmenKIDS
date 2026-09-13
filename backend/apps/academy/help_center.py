"""The "Центр помощи" ("Help Center") admin screen.

A static, model-less documentation page for OkurmenKIDS staff — not tied to
any model, so it follows the same site-wide custom-URL pattern as
"Расписание"/"Аналитика" (see the bottom of admin.py) instead of living on a
ModelAdmin. All content is rendered directly in the template; this view only
enforces admin-only access and hands the template a few reversed URLs for
the quick-action buttons.
"""
from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.urls import reverse

from .admin_views import _is_admin_user


def help_center_view(request):
    if not _is_admin_user(request.user):
        raise PermissionDenied("Раздел «Центр помощи» доступен только администратору.")

    context = {
        "quick_links": {
            "groups": reverse("admin:academy_group_changelist"),
            "students": reverse("admin:academy_student_changelist"),
            "teachers": reverse("admin:users_teacher_changelist"),
            "courses": reverse("admin:academy_course_changelist"),
            "lesson_plans": reverse("admin:academy_courselessonplan_changelist"),
            "schedule": reverse("admin:academy_schedule"),
            "lessons": reverse("admin:academy_lesson_changelist"),
            "attendance": reverse("admin:academy_attendance_changelist"),
            "homework": reverse("admin:academy_homework_changelist"),
            "homework_results": reverse("admin:academy_homeworkresult_changelist"),
            "analytics": reverse("admin:academy_analytics"),
        },
    }
    return render(request, "admin/academy/help_center.html", context)
