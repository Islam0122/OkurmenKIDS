"""Custom Django admin site for OkurmenKIDS.

Registered as the project's admin `default_site` (see
``apps.users.apps.OkurmenKidsAdminConfig``) for one reason only: to hand a
redesigned dashboard template real numbers. Everything else — login form,
change forms, tables, theming — still goes entirely through Jazzmin/AdminLTE
unchanged; we only touch ``index()``.
"""
from __future__ import annotations

from django.contrib.admin import AdminSite
from django.db.models import Avg, Count, Q
from django.utils import timezone

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
        """Real numbers for every module — Teacher/Subject plus academy."""
        # Imported lazily to avoid a hard app-loading-order dependency
        # between users and academy at import time.
        from apps.academy.models import Attendance, Group, HomeworkResult, KPIStudent, Lesson, Student

        teachers = Teacher.objects.all()
        subjects_breakdown = list(
            Subject.objects.filter(is_active=True)
            .annotate(teacher_count=Count("teachers"))
            .order_by("-teacher_count")[:8]
            .values("name", "teacher_count")
        )

        today = timezone.localdate()
        last_30_days = today - timezone.timedelta(days=30)

        attendance_recent = Attendance.objects.filter(lesson__date__gte=last_30_days)
        attendance_recent_total = attendance_recent.count()
        attendance_recent_attended = attendance_recent.filter(
            status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE]
        ).count()
        attendance_recent_rate = (
            round(attendance_recent_attended / attendance_recent_total * 100, 1)
            if attendance_recent_total
            else None
        )

        homework_recent = HomeworkResult.objects.filter(homework__lesson__date__gte=last_30_days)
        homework_avg_score = homework_recent.aggregate(avg=Avg("score"))["avg"]
        homework_recent_rate = (
            round(homework_avg_score / 10 * 100, 1) if homework_avg_score is not None else None
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
            "students_total": Student.objects.count(),
            "students_active": Student.objects.filter(is_active=True).count(),
            "groups_total": Group.objects.count(),
            "groups_active": Group.objects.filter(status=Group.Status.ACTIVE).count(),
            "lessons_today_count": Lesson.objects.filter(date=today).count(),
            "attendance_recent_rate": attendance_recent_rate,
            "homework_recent_rate": homework_recent_rate,
            "lessons_today": list(
                Lesson.objects.filter(date=today)
                .select_related("group", "group__teacher__user", "room", "subject")
                .order_by("start_time")[:8]
            ),
            "active_groups": list(
                Group.objects.filter(status=Group.Status.ACTIVE)
                .select_related("teacher__user", "course")
                .annotate(students_count_annotated=Count("students", filter=Q(students__is_active=True), distinct=True))
                .order_by("-start_date")[:8]
            ),
            "recent_students": list(
                Student.objects.select_related("group").order_by("-created_at")[:8]
            ),
            "recent_kpi": list(
                KPIStudent.objects.select_related("student", "group").order_by("-created_at")[:8]
            ),
        }
