"""Custom Django admin site for OkurmenKIDS.

Registered as the project's admin `default_site` (see
``apps.users.apps.OkurmenKidsAdminConfig``) for one reason only: to hand a
redesigned dashboard template real numbers. Everything else — login form,
change forms, tables, theming — still goes entirely through Jazzmin/AdminLTE
unchanged; we only touch ``index()``.
"""
from __future__ import annotations

from django.contrib.admin import AdminSite
from django.db.models import Count

from apps.users.models import Subject, Teacher, User


class OkurmenKidsAdminSite(AdminSite):
    site_header = "OkurmenKIDS"
    site_title = "OkurmenKIDS"
    index_title = "Панель управления"

    # A dedicated path (not "admin/index.html") so this template can never
    # collide with — or accidentally be shadowed by — Jazzmin's own index
    # template, regardless of INSTALLED_APPS ordering.
    index_template = "admin/okurmenkids/index.html"

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["ok_stats"] = self._build_dashboard_stats()
        return super().index(request, extra_context)

    @staticmethod
    def _build_dashboard_stats() -> dict:
        """Real numbers for the modules that exist today.

        Modules with no backend yet (students, groups, attendance, homework,
        KPI scoring) are deliberately NOT faked here — the dashboard template
        renders those as clearly-labelled "скоро" placeholders instead.
        """
        teachers = Teacher.objects.all()
        subjects_breakdown = list(
            Subject.objects.filter(is_active=True)
            .annotate(teacher_count=Count("teachers"))
            .order_by("-teacher_count")[:8]
            .values("name", "teacher_count")
        )
        return {
            "teachers_total": teachers.count(),
            "teachers_active": teachers.filter(is_active=True).count(),
            "teachers_verified": teachers.filter(user__is_verified=True).count(),
            "teachers_pending": teachers.filter(
                is_active=True, user__is_verified=False
            ).count(),
            "subjects_total": Subject.objects.count(),
            "subjects_active": Subject.objects.filter(is_active=True).count(),
            "admins_total": User.objects.filter(role=User.Role.ADMIN).count(),
            "subjects_breakdown": subjects_breakdown,
        }
