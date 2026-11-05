"""«Общая статистика»: расчёты, ежедневные снимки, история, API и права."""
from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import Attendance, Course, Group, GroupTeacher, Homework, HomeworkResult, Lesson, Student
from apps.performance.models import DailyPerformanceSnapshot
from apps.performance.services import dashboard
from apps.performance.services.metrics import compute_rates
from apps.performance.services.snapshots import backfill, capture
from apps.users.models import Subject, Teacher, User

PASSWORD = "Str0ngPassw0rd!"
URL = "/api/v1/monthly-performance/"


def at(day: dt.date, hour: int = 20, minute: int = 0) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(day, dt.time(hour, minute)))


@contextmanager
def frozen(moment: dt.datetime):
    with mock.patch("django.utils.timezone.now", return_value=moment):
        yield


def make_user(username, role, **extra):
    return User.objects.create_user(
        username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
        first_name=username.capitalize(), role=role, is_verified=True, **extra,
    )


class PerformanceFixture(TestCase):
    D1 = dt.date(2026, 11, 2)
    D2 = dt.date(2026, 11, 3)
    D3 = dt.date(2026, 11, 4)

    def setUp(self):
        self.subject, _ = Subject.objects.get_or_create(name="Python")
        self.course = Course.objects.create(name="Python", count_lesson=30)
        self.trainer = Teacher.objects.create(user=make_user("trainer", User.Role.TEACHER))
        self.group = self.make_group("PY-01")
        self.other_group = self.make_group("PY-02")
        self.students = [self.make_student(f"S{i}", self.group) for i in range(4)]
        self.number = 0

    def make_group(self, name, status=Group.Status.ACTIVE):
        group = Group.objects.create(name=name, course=self.course, teacher=self.trainer,
                                     start_date=dt.date(2026, 9, 1), status=status)
        GroupTeacher.objects.create(group=group, teacher=self.trainer, subject=self.subject)
        return group

    def make_student(self, name, group, status=Student.Status.ACTIVE):
        return Student.objects.create(first_name=name, group=group, status=status,
                                      is_active=status == Student.Status.ACTIVE)

    def lesson(self, day, group=None, status=Lesson.Status.COMPLETED, start=dt.time(10)):
        self.number += 1
        group = group or self.group
        return Lesson.objects.create(
            group=group, group_teacher=group.teachers.first(), teacher=self.trainer, subject=self.subject,
            lesson_number=self.number, date=day, start_time=start,
            end_time=(dt.datetime.combine(day, start) + dt.timedelta(hours=1)).time(), status=status,
        )

    def mark(self, lesson, statuses):
        for student, status in zip(self.students, statuses):
            Attendance.objects.create(lesson=lesson, student=student, status=status)

    def grade(self, lesson, statuses, when: dt.datetime):
        homework = Homework.objects.create(lesson=lesson, title="ДЗ")
        with frozen(when):
            for student, status in zip(self.students, statuses):
                HomeworkResult.objects.create(homework=homework, student=student, status=status)
        return homework


P, A, L, E = (Attendance.Status.PRESENT, Attendance.Status.ABSENT, Attendance.Status.LATE, Attendance.Status.EXCUSED)
S, N, C, LT = (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.NOT_SUBMITTED,
               HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE)


class CalculationTests(PerformanceFixture):
    def test_attendance_counts_present_and_late(self):
        self.mark(self.lesson(self.D1), [P, L, A, E])
        rates = compute_rates(self.D1, now=at(self.D1))
        self.assertEqual((rates.attendance_attended, rates.attendance_marked), (2, 4))
        self.assertEqual(rates.attendance_percent, Decimal("50.0"))

    def test_homework_counts_results_recorded_that_day(self):
        lesson = self.lesson(self.D1)
        self.grade(lesson, [S, C, LT, N], at(self.D2, 12))
        self.assertIsNone(compute_rates(self.D1, now=at(self.D2)).homework_percent)
        rates = compute_rates(self.D2, now=at(self.D2))
        self.assertEqual(rates.homework_percent, Decimal("75.0"))

    def test_day_without_lessons_is_none_not_zero(self):
        rates = compute_rates(self.D1, now=at(self.D1))
        self.assertIsNone(rates.attendance_percent)
        self.assertIsNone(rates.homework_percent)
        self.assertEqual(rates.lessons_count, 0)

    def test_cancelled_lessons_are_ignored(self):
        self.mark(self.lesson(self.D1), [P, P, P, P])
        cancelled = self.lesson(self.D1, status=Lesson.Status.CANCELLED, start=dt.time(15))
        self.mark(cancelled, [A, A, A, A])
        rates = compute_rates(self.D1, now=at(self.D1))
        self.assertEqual(rates.attendance_percent, Decimal("100.0"))
        self.assertEqual(rates.lessons_count, 1)

    def test_future_lessons_today_are_ignored(self):
        self.mark(self.lesson(self.D1, start=dt.time(9)), [P, P, A, A])
        later = self.lesson(self.D1, status=Lesson.Status.SCHEDULED, start=dt.time(18))
        self.mark(later, [P, P, P, P])  # отметка «заранее» не учитывается до начала занятия
        rates = compute_rates(self.D1, now=at(self.D1, 12))
        self.assertEqual(rates.attendance_percent, Decimal("50.0"))
        self.assertEqual(rates.lessons_count, 1)

    def test_only_active_groups_and_students(self):
        self.students[0].status = Student.Status.WITHDRAWN
        self.students[0].save()
        self.mark(self.lesson(self.D1), [A, P, P, P])
        paused = self.make_group("PY-03", status=Group.Status.PAUSED)
        lesson = self.lesson(self.D1, group=paused)
        Attendance.objects.create(lesson=lesson, student=self.make_student("X", paused), status=A)
        rates = compute_rates(self.D1, now=at(self.D1))
        self.assertEqual(rates.attendance_percent, Decimal("100.0"))
        self.assertEqual(rates.attendance_marked, 3)


class SnapshotTests(PerformanceFixture):
    def test_capture_creates_one_snapshot_per_day(self):
        self.mark(self.lesson(self.D1), [P, P, P, A])
        for hour in (10, 14, 22):
            capture(now=at(self.D1, hour))
        self.assertEqual(DailyPerformanceSnapshot.objects.filter(date=self.D1).count(), 1)
        snapshot = DailyPerformanceSnapshot.objects.get(date=self.D1)
        self.assertEqual(snapshot.attendance_percent, Decimal("75.0"))
        self.assertEqual((snapshot.active_groups, snapshot.active_students), (2, 4))
        self.assertEqual(snapshot.status, DailyPerformanceSnapshot.Status.PROVISIONAL)

    @override_settings(PERFORMANCE_FINALIZE_DELAY_DAYS=1)
    def test_history_is_not_changed_by_later_status_changes(self):
        capture(now=at(self.D1, 22))
        # На следующий день студент деактивирован, группа закрыта.
        self.students[0].status = Student.Status.WITHDRAWN
        self.students[0].save()
        self.other_group.status = Group.Status.COMPLETED
        self.other_group.save()
        capture(now=at(self.D2, 10))
        d1 = DailyPerformanceSnapshot.objects.get(date=self.D1)
        self.assertEqual((d1.active_groups, d1.active_students), (2, 4))
        d2 = DailyPerformanceSnapshot.objects.get(date=self.D2)
        self.assertEqual((d2.active_groups, d2.active_students), (1, 3))

    @override_settings(PERFORMANCE_FINALIZE_DELAY_DAYS=1)
    def test_late_marks_counted_within_delay_then_frozen(self):
        lesson = self.lesson(self.D1)
        capture(now=at(self.D1, 22))
        self.assertIsNone(DailyPerformanceSnapshot.objects.get(date=self.D1).attendance_percent)
        self.mark(lesson, [P, P, A, A])  # тренер отметил на следующий день
        capture(now=at(self.D2, 9))
        d1 = DailyPerformanceSnapshot.objects.get(date=self.D1)
        self.assertEqual(d1.attendance_percent, Decimal("50.0"))
        self.assertFalse(d1.is_final)
        capture(now=at(self.D3, 9))
        d1.refresh_from_db()
        self.assertTrue(d1.is_final)
        Attendance.objects.filter(lesson=lesson).update(status=P)
        capture(now=at(self.D3, 15))
        d1.refresh_from_db()
        self.assertEqual(d1.attendance_percent, Decimal("50.0"))

    def test_gaps_are_filled_without_inventing_counts(self):
        capture(now=at(self.D1, 22))
        self.mark(self.lesson(self.D2), [P, A, A, A])
        capture(now=at(dt.date(2026, 11, 5), 9))  # 3 и 4 ноября планировщик не работал
        d2 = DailyPerformanceSnapshot.objects.get(date=self.D2)
        self.assertEqual(d2.attendance_percent, Decimal("25.0"))
        self.assertIsNone(d2.active_groups)
        self.assertIsNone(d2.active_students)
        self.assertTrue(DailyPerformanceSnapshot.objects.filter(date=self.D3).exists())

    def test_backfill_command_is_idempotent(self):
        with frozen(at(self.D3, 9)):
            call_command("capture_performance_snapshots", "--backfill-from", "2026-11-01", stdout=open("/dev/null", "w"))
            call_command("capture_performance_snapshots", "--backfill-from", "2026-11-01", stdout=open("/dev/null", "w"))
        self.assertEqual(DailyPerformanceSnapshot.objects.count(), 4)  # 1–3 ноября + сегодня
        self.assertEqual(backfill(dt.date(2026, 11, 1), self.D3, now=at(self.D3)), 0)

    def test_manual_fields_survive_recalculation(self):
        capture(now=at(self.D1, 10))
        DailyPerformanceSnapshot.objects.filter(date=self.D1).update(
            active_students=10, manual_fields=["active_students"])
        capture(now=at(self.D1, 20))
        self.assertEqual(DailyPerformanceSnapshot.objects.get(date=self.D1).active_students, 10)

    def test_celery_task_runs_capture(self):
        from apps.performance.tasks import capture_daily_snapshots_task

        with frozen(at(self.D1, 12)):
            result = capture_daily_snapshots_task.apply().get()
        self.assertEqual(result["date"], "2026-11-02")


class DashboardTests(PerformanceFixture):
    def test_month_has_every_day_and_marks_future(self):
        days = dashboard.month_days(2026, 11, now=at(self.D2, 12))
        self.assertEqual(len(days), 30)
        self.assertEqual(len(dashboard.month_days(2028, 2, now=at(self.D2))), 29)
        self.assertEqual(len(dashboard.month_days(2026, 2, now=at(self.D2))), 28)
        self.assertTrue(days[3]["is_future"])
        self.assertEqual(days[2]["status"], "live")
        self.assertEqual(days[0]["status"], "missing")

    def test_summary_change_against_previous_day(self):
        self.mark(self.lesson(self.D1), [P, P, A, A])
        capture(now=at(self.D1, 22))
        self.mark(self.lesson(self.D2), [P, P, P, A])
        payload = dashboard.month_payload(2026, 11, now=at(self.D2, 20))
        card = payload["summary"]["attendance_percent"]
        self.assertEqual((card["value"], card["previous_value"], card["change"]), (75.0, 50.0, 25.0))
        self.assertEqual(card["month_average"], 62.5)
        self.assertEqual(payload["summary"]["active_groups"]["change"], 0)
        self.assertEqual(payload["trends"]["attendance"]["average"], 62.5)

    def test_empty_month(self):
        payload = dashboard.month_payload(2026, 10, now=at(self.D2))
        self.assertEqual(len(payload["days"]), 31)
        self.assertIsNone(payload["summary"]["attendance_percent"]["value"])
        self.assertIsNone(payload["summary"]["attendance_percent"]["month_average"])
        self.assertTrue(all(p["value"] is None for p in payload["trends"]["homework"]["points"]))


class ApiTests(PerformanceFixture):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def as_role(self, role, **extra):
        user = make_user(f"u_{role}_{User.objects.count()}", role, **extra)
        self.client.force_authenticate(user)
        return user

    def login_jwt(self, role):
        user = make_user(f"j_{role}", role)
        response = self.client.post("/api/v1/auth/login/", {"username": user.username, "password": PASSWORD},
                                    format="json")
        token = response.data.get("access") or response.data.get("tokens", {}).get("access")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_anonymous_is_rejected(self):
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_every_role_can_view(self):
        with frozen(at(self.D2, 12)):
            for role in User.Role.values:
                self.as_role(role)
                for suffix in ("", "snapshots/", "summary/", "trends/"):
                    response = self.client.get(URL + suffix)
                    self.assertEqual(response.status_code, 200, (role, suffix, response.content[:200]))

    def test_isolated_roles_pass_middleware_with_jwt(self):
        with frozen(at(self.D2, 12)):
            for role in (User.Role.ACCOUNTANT, User.Role.SALES_MANAGER, User.Role.DOP):
                self.client.credentials()
                self.login_jwt(role)
                self.assertEqual(self.client.get(URL).status_code, 200, role)

    def test_month_selection_and_validation(self):
        self.as_role(User.Role.TEACHER)
        with frozen(at(self.D2, 12)):
            response = self.client.get(URL, {"year": 2026, "month": 10})
            self.assertEqual(response.status_code, 200)
            self.assertEqual((response.data["month_label"], len(response.data["days"])), ("Октябрь", 31))
            self.assertFalse(response.data["can_edit"])
            self.assertEqual(self.client.get(URL, {"year": 2026, "month": 12}).status_code, 400)
            self.assertEqual(self.client.get(URL, {"month": 13}).status_code, 400)
            self.assertEqual(self.client.get(URL, {"year": "abc"}).status_code, 400)
            default = self.client.get(URL).data
            self.assertEqual((default["year"], default["month"], default["is_current_month"]), (2026, 11, True))

    def test_correction_requires_permission(self):
        with frozen(at(self.D2, 12)):
            for role in (User.Role.TEACHER, User.Role.TEAM_LEAD, User.Role.ACCOUNTANT, User.Role.ASSISTANT):
                self.as_role(role)
                response = self.client.patch(URL + "snapshots/2026-11-01/", {"active_groups": 5}, format="json")
                self.assertEqual(response.status_code, 403, role)
            self.assertFalse(DailyPerformanceSnapshot.objects.exists())

    def test_admin_corrects_past_day(self):
        admin = self.as_role(User.Role.ADMIN)
        with frozen(at(self.D2, 12)):
            response = self.client.patch(URL + "snapshots/2026-11-01/",
                                         {"active_groups": 5, "attendance_percent": "88.5", "comment": "Сверка"},
                                         format="json")
            self.assertEqual(response.status_code, 200, response.data)
            snapshot = DailyPerformanceSnapshot.objects.get(date=dt.date(2026, 11, 1))
            self.assertEqual((snapshot.active_groups, snapshot.attendance_percent), (5, Decimal("88.5")))
            self.assertEqual(set(snapshot.manual_fields), {"active_groups", "attendance_percent"})
            self.assertEqual(snapshot.corrected_by, admin)
            self.assertTrue(self.client.get(URL).data["can_edit"])
            self.assertEqual(self.client.patch(URL + "snapshots/2026-11-09/", {"active_groups": 1},
                                               format="json").status_code, 400)
            self.assertEqual(self.client.patch(URL + "snapshots/2026-11-01/", {}, format="json").status_code, 400)
            self.assertEqual(self.client.patch(URL + "snapshots/2026-11-01/", {"attendance_percent": 150},
                                               format="json").status_code, 400)

    def test_explicit_django_permission_allows_correction(self):
        from django.contrib.auth.models import Permission

        user = self.as_role(User.Role.TEAM_LEAD)
        user.user_permissions.add(Permission.objects.get(codename="change_dailyperformancesnapshot"))
        user = User.objects.get(pk=user.pk)
        self.client.force_authenticate(user)
        with frozen(at(self.D2, 12)):
            response = self.client.patch(URL + "snapshots/2026-11-03/", {"active_students": 7}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            today = self.client.get(URL).data["days"][2]
            self.assertEqual((today["active_students"], today["status"]), (7, "live"))
