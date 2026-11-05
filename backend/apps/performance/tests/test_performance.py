"""«Общая статистика»: расчёт по расписанию дня, история, снимки, API и права.

Календарь: октябрь 2026 — 5-е понедельник, 11-е воскресенье; «сейчас» —
четверг 5 ноября 2026 (Asia/Bishkek).
"""
from __future__ import annotations

import datetime as dt
import io
from contextlib import contextmanager
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import Attendance, Course, Group, GroupTeacher, Homework, HomeworkResult, Lesson, Student
from apps.academy.services.student_enrollment import transfer_student
from apps.academy.services.student_status import deactivate_student
from apps.performance.models import DailyPerformanceSnapshot
from apps.performance.services import dashboard
from apps.performance.services.metrics import compute_day, compute_days
from apps.performance.services.snapshots import backfill, capture
from apps.users.models import Subject, Teacher, User

PASSWORD = "Str0ngPassw0rd!"
URL = "/api/v1/monthly-performance/"
TODAY = dt.date(2026, 11, 5)  # четверг
MON, TUE, WED, THU, FRI, SAT, SUN = (dt.date(2026, 10, d) for d in (5, 6, 7, 8, 9, 10, 11))
P, A, L, E = (Attendance.Status.PRESENT, Attendance.Status.ABSENT, Attendance.Status.LATE, Attendance.Status.EXCUSED)
S, N, C, LT = (HomeworkResult.Status.SUBMITTED, HomeworkResult.Status.NOT_SUBMITTED,
               HomeworkResult.Status.CHECKED, HomeworkResult.Status.LATE)


def at(day: dt.date, hour: int = 20, minute: int = 0) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(day, dt.time(hour, minute)))


NOW = at(TODAY)


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
    """PROG 1 — Пн/Ср/Пт (3 студента), PROG 2 — Вт/Чт/Сб (2 студента)."""

    def setUp(self):
        self.subject, _ = Subject.objects.get_or_create(name="Python")
        self.course = Course.objects.create(name="Python", count_lesson=30)
        self.trainer = Teacher.objects.create(user=make_user("trainer", User.Role.TEACHER))
        self.prog1 = self.make_group("PROG 1")
        self.prog2 = self.make_group("PROG 2")
        self.a = [self.make_student(f"A{i}", self.prog1) for i in range(3)]
        self.b = [self.make_student(f"B{i}", self.prog2) for i in range(2)]
        self.number = 0

    def make_group(self, name, status=Group.Status.ACTIVE):
        group = Group.objects.create(name=name, course=self.course, teacher=self.trainer,
                                     start_date=dt.date(2026, 9, 1), status=status)
        GroupTeacher.objects.create(group=group, teacher=self.trainer, subject=self.subject)
        return group

    def make_student(self, name, group, status=Student.Status.ACTIVE):
        return Student.objects.create(first_name=name, group=group, status=status,
                                      is_active=status == Student.Status.ACTIVE, enrollment_date=dt.date(2026, 9, 1))

    def lesson(self, day, group, status=Lesson.Status.COMPLETED, start=dt.time(10)):
        self.number += 1
        return Lesson.objects.create(
            group=group, group_teacher=group.teachers.first(), teacher=self.trainer, subject=self.subject,
            lesson_number=self.number, date=day, start_time=start,
            end_time=(dt.datetime.combine(day, start) + dt.timedelta(hours=1)).time(), status=status,
        )

    def mark(self, lesson, marks: dict):
        for student, status in marks.items():
            Attendance.objects.create(lesson=lesson, student=student, status=status)

    def grade(self, lesson, results: dict):
        homework = Homework.objects.create(lesson=lesson, title="ДЗ")
        for student, status in results.items():
            HomeworkResult.objects.create(homework=homework, student=student, status=status)

    def week(self):
        """Неделя 5–10 октября по расписанию обеих групп, все отмечены."""
        for day in (MON, WED, FRI):
            self.mark(self.lesson(day, self.prog1), dict(zip(self.a, (P, L, A))))
        for day in (TUE, THU, SAT):
            self.mark(self.lesson(day, self.prog2), dict(zip(self.b, (P, A))))

    def day(self, day):
        with frozen(NOW):
            return compute_day(day, now=NOW)


class ScheduleTests(PerformanceFixture):
    def test_monday_only_first_group(self):  # сценарии 1, 3
        self.week()
        stats = self.day(MON)
        self.assertEqual((stats.scheduled_groups, stats.held_groups), (1, 1))
        self.assertEqual((stats.scheduled_students, stats.attended_students), (3, 2))
        self.assertEqual(stats.attendance_percent, Decimal("66.7"))

    def test_tuesday_only_second_group(self):  # сценарии 2, 4
        self.week()
        stats = self.day(TUE)
        self.assertEqual((stats.scheduled_groups, stats.scheduled_students, stats.attended_students), (1, 2, 1))
        self.assertEqual(stats.attendance_percent, Decimal("50.0"))

    def test_day_without_lessons(self):  # сценарий 5
        self.week()
        stats = self.day(SUN)
        self.assertEqual((stats.scheduled_groups, stats.held_groups, stats.scheduled_students, stats.attended_students),
                         (0, 0, 0, 0))
        self.assertIsNone(stats.attendance_percent)  # «Нет занятий», не 0 %
        self.assertIsNone(stats.homework_percent)

    def test_both_groups_on_one_day_and_unique_students(self):  # сценарий 6
        # Два занятия PROG 1 в один день (Python + английский) и занятие PROG 2.
        first = self.lesson(WED, self.prog1)
        second = self.lesson(WED, self.prog1, start=dt.time(12))
        other = self.lesson(WED, self.prog2, start=dt.time(15))
        self.mark(first, {self.a[0]: P, self.a[1]: A, self.a[2]: A})
        self.mark(second, {self.a[0]: P, self.a[1]: L, self.a[2]: A})
        self.mark(other, {self.b[0]: P, self.b[1]: P})
        stats = self.day(WED)
        self.assertEqual((stats.scheduled_groups, stats.lessons_count), (2, 3))
        self.assertEqual(stats.scheduled_students, 5)  # каждый студент — один раз
        self.assertEqual(stats.attended_students, 4)  # A0 был на двух занятиях — посчитан один раз
        self.assertEqual(stats.attendance_percent, Decimal("80.0"))

    def test_deactivated_student(self):  # сценарий 7
        self.week()
        with frozen(at(THU, 12)):
            deactivate_student(self.a[2], reason="stopped_attending", event_date=THU)
        monday_next = self.lesson(dt.date(2026, 10, 12), self.prog1)
        self.mark(monday_next, {self.a[0]: P, self.a[1]: P, self.a[2]: P})  # отметка ушедшего не считается
        after = self.day(dt.date(2026, 10, 12))
        self.assertEqual((after.scheduled_students, after.attended_students), (2, 2))
        self.assertEqual(after.attendance_percent, Decimal("100.0"))
        # До деактивации — как было.
        self.assertEqual(self.day(MON).scheduled_students, 3)

    def test_schedule_change(self):  # сценарий 8
        self.week()
        # С 13 октября PROG 1 занимается по Вт/Чт/Сб — вместе с PROG 2.
        tue_next = dt.date(2026, 10, 13)
        self.lesson(tue_next, self.prog1)
        self.lesson(tue_next, self.prog2)
        self.assertEqual(self.day(tue_next).scheduled_groups, 2)
        self.assertEqual(self.day(dt.date(2026, 10, 12)).scheduled_groups, 0)  # в понедельник занятий больше нет
        self.assertEqual((self.day(MON).scheduled_groups, self.day(TUE).scheduled_groups), (1, 1))  # прошлое не изменилось

    def test_history_after_group_composition_change(self):  # сценарий 10
        self.week()
        with frozen(at(FRI, 9)):
            transfer_student(self.b[0], group=self.prog1, event_date=FRI)
        self.assertEqual(self.day(TUE).scheduled_students, 2)  # во вторник B0 ещё был в PROG 2
        self.assertEqual(self.day(FRI).scheduled_students, 4)  # с пятницы — в PROG 1
        self.assertEqual(self.day(SAT).scheduled_students, 1)

    def test_cancelled_lessons_are_not_in_the_denominator(self):
        self.mark(self.lesson(MON, self.prog1), dict(zip(self.a, (P, P, P))))
        self.lesson(MON, self.prog2, status=Lesson.Status.CANCELLED)
        stats = self.day(MON)
        self.assertEqual((stats.scheduled_groups, stats.scheduled_students), (1, 3))
        self.assertEqual(stats.attendance_percent, Decimal("100.0"))

    def test_scheduled_but_not_held(self):
        self.mark(self.lesson(MON, self.prog1), dict(zip(self.a, (P, P, A))))
        self.lesson(MON, self.prog2, status=Lesson.Status.SCHEDULED, start=dt.time(15))  # не проведено, не отмечено
        stats = self.day(MON)
        self.assertEqual((stats.scheduled_groups, stats.held_groups), (2, 1))
        self.assertEqual((stats.scheduled_students, stats.attended_students), (5, 2))
        self.assertEqual(stats.attendance_percent, Decimal("40.0"))  # должно было состояться — в знаменателе

    def test_today_future_lessons_are_not_counted_in_attendance(self):
        self.mark(self.lesson(TODAY, self.prog2, start=dt.time(9)), dict(zip(self.b, (P, A))))
        self.lesson(TODAY, self.prog1, status=Lesson.Status.SCHEDULED, start=dt.time(18))
        with frozen(at(TODAY, 12)):
            stats = compute_day(TODAY, now=at(TODAY, 12))
        self.assertEqual((stats.scheduled_groups, stats.scheduled_students), (2, 5))  # план дня — весь
        self.assertEqual((stats.expected_students, stats.attended_students), (2, 1))  # ещё не начавшиеся — нет
        self.assertEqual(stats.attendance_percent, Decimal("50.0"))

    def test_paused_group_is_not_scheduled_today(self):
        self.lesson(TODAY, self.prog1, status=Lesson.Status.SCHEDULED, start=dt.time(18))
        self.prog1.status = Group.Status.PAUSED
        self.prog1.save()
        with frozen(at(TODAY, 12)):
            self.assertEqual(compute_day(TODAY, now=at(TODAY, 12)).scheduled_groups, 0)

    def test_homework_by_lesson_day_for_active_students(self):
        lesson = self.lesson(MON, self.prog1)
        self.grade(lesson, {self.a[0]: S, self.a[1]: C, self.a[2]: N})
        self.grade(self.lesson(TUE, self.prog2), {self.b[0]: LT, self.b[1]: N})
        self.assertEqual(self.day(MON).homework_percent, Decimal("66.7"))
        self.assertEqual(self.day(TUE).homework_percent, Decimal("50.0"))

    def test_batch_equals_single_day(self):
        self.week()
        with frozen(NOW):
            batch = compute_days(MON, SUN, now=NOW)
        for day, stats in batch.items():
            self.assertEqual(stats.as_values(), self.day(day).as_values(), day)


class SnapshotTests(PerformanceFixture):
    def test_one_snapshot_per_day_and_first_run_backfills_previous_month(self):
        self.week()
        for hour in (9, 14, 22):
            with frozen(at(TODAY, hour)):
                capture(now=at(TODAY, hour))
        self.assertEqual(DailyPerformanceSnapshot.objects.filter(date=TODAY).count(), 1)
        # 1 октября … 5 ноября — каждый день по одному снимку.
        self.assertEqual(DailyPerformanceSnapshot.objects.count(), 31 + 5)
        mon = DailyPerformanceSnapshot.objects.get(date=MON)
        self.assertEqual((mon.scheduled_groups, mon.scheduled_students, mon.attended_students), (1, 3, 2))
        self.assertEqual(mon.status, DailyPerformanceSnapshot.Status.FINAL)
        sun = DailyPerformanceSnapshot.objects.get(date=SUN)
        self.assertEqual((sun.scheduled_groups, sun.scheduled_students), (0, 0))
        self.assertIsNone(sun.attendance_percent)

    @override_settings(PERFORMANCE_FINALIZE_DELAY_DAYS=1)
    def test_finalized_history_is_frozen(self):
        lesson = self.lesson(MON, self.prog1)
        self.mark(lesson, dict(zip(self.a, (P, P, A))))
        for moment in (at(MON, 22), at(WED, 9)):  # планировщик работает каждый день
            with frozen(moment):
                capture(now=moment)
        self.assertTrue(DailyPerformanceSnapshot.objects.get(date=MON).is_final)
        # Позже: студента перевели, отметку исправили, расписание сменили.
        with frozen(at(dt.date(2026, 10, 20), 9)):
            transfer_student(self.a[0], group=self.prog2, event_date=dt.date(2026, 10, 20))
            Attendance.objects.filter(lesson=lesson).update(status=P)
            capture(now=at(dt.date(2026, 10, 20), 9))
        mon = DailyPerformanceSnapshot.objects.get(date=MON)
        self.assertTrue(mon.is_final)
        self.assertEqual((mon.scheduled_students, mon.attended_students, mon.attendance_percent), (3, 2, Decimal("66.7")))

    @override_settings(PERFORMANCE_FINALIZE_DELAY_DAYS=7)
    def test_late_marks_are_counted_within_the_delay(self):
        lesson = self.lesson(MON, self.prog1)
        with frozen(at(MON, 22)):
            capture(now=at(MON, 22))
        self.assertEqual(DailyPerformanceSnapshot.objects.get(date=MON).attendance_percent, Decimal("0.0"))
        self.mark(lesson, dict(zip(self.a, (P, P, P))))  # отметили на следующий день
        with frozen(at(TUE, 9)):
            capture(now=at(TUE, 9))
        mon = DailyPerformanceSnapshot.objects.get(date=MON)
        self.assertEqual(mon.attendance_percent, Decimal("100.0"))
        self.assertFalse(mon.is_final)

    def test_manual_fields_survive_recalculation(self):
        with frozen(NOW):
            capture(now=NOW)
            DailyPerformanceSnapshot.objects.filter(date=TODAY).update(
                scheduled_students=10, manual_fields=["scheduled_students"])
            capture(now=NOW)
        self.assertEqual(DailyPerformanceSnapshot.objects.get(date=TODAY).scheduled_students, 10)

    def test_project_timezone_decides_the_calendar_day(self):
        # 00:30 в Бишкеке 5 ноября = 18:30 UTC 4 ноября.
        moment = timezone.make_aware(dt.datetime(2026, 11, 4, 18, 30), dt.timezone.utc)
        with frozen(moment):
            result = capture(now=moment)
        self.assertEqual(result["date"], "2026-11-05")
        self.assertTrue(DailyPerformanceSnapshot.objects.filter(date=TODAY).exists())

    def test_backfill_command_is_idempotent(self):
        self.week()
        with frozen(NOW):
            for _ in range(2):
                call_command("capture_performance_snapshots", "--backfill-from", "2026-10-01", stdout=io.StringIO())
            self.assertEqual(backfill(dt.date(2026, 10, 1), TODAY, now=NOW), 0)
        self.assertEqual(DailyPerformanceSnapshot.objects.count(), 36)

    def test_celery_task_skips_while_migrations_are_pending(self):
        from apps.performance.tasks import capture_daily_snapshots_task

        with mock.patch("apps.billing.services.scheduler.pending_migrations",
                        return_value=["performance.0003_schedule_based_metrics"]):
            result = capture_daily_snapshots_task.apply().get()
        self.assertEqual(result["status"], "skipped_migrations")
        self.assertFalse(DailyPerformanceSnapshot.objects.exists())

    def test_celery_task_runs_capture(self):
        from apps.performance.tasks import capture_daily_snapshots_task

        with frozen(NOW):
            result = capture_daily_snapshots_task.apply().get()
        self.assertEqual(result["date"], "2026-11-05")


class DashboardTests(PerformanceFixture):
    def test_previous_month_shows_every_day_with_history(self):  # сценарий 9
        self.week()
        with frozen(NOW):
            capture(now=NOW)  # снимки за октябрь
            Student.objects.filter(pk=self.a[0].pk).update(status=Student.Status.WITHDRAWN, is_active=False)
            days = dashboard.month_days(2026, 10, now=NOW)
        self.assertEqual(len(days), 31)
        self.assertTrue(all(d["has_data"] and not d["is_future"] for d in days))
        mon = days[4]
        self.assertEqual((mon["scheduled_groups"], mon["scheduled_students"], mon["attended_students"]), (1, 3, 2))
        self.assertEqual(days[10]["no_lessons"], True)  # воскресенье — «Нет занятий»
        self.assertEqual(days[10]["scheduled_groups"], 0)

    def test_past_days_without_snapshot_are_restored_from_records(self):
        self.week()
        with frozen(NOW):
            days = dashboard.month_days(2026, 10, now=NOW)
        self.assertFalse(DailyPerformanceSnapshot.objects.exists())  # чтение ничего не пишет
        self.assertEqual(days[4]["status"], "computed")
        self.assertEqual(days[5]["scheduled_groups"], 1)

    def test_first_version_snapshot_is_computed_on_read(self):
        """Снимок до миграции 0003 (без показателей по расписанию) не показывает «Нет данных»."""
        self.week()
        DailyPerformanceSnapshot.objects.create(date=MON, legacy_active_groups=4, status="provisional")
        with frozen(NOW):
            days = dashboard.month_days(2026, 10, now=NOW)
        self.assertEqual((days[4]["status"], days[4]["scheduled_groups"], days[4]["scheduled_students"]),
                         ("computed", 1, 3))

    def test_month_without_records_is_no_data(self):
        with frozen(NOW):
            days = dashboard.month_days(2026, 8, now=NOW)
        self.assertEqual(len(days), 31)
        self.assertTrue(all(d["status"] == "missing" and d["scheduled_groups"] is None for d in days))

    def test_future_month_is_an_empty_calendar(self):
        self.lesson(dt.date(2026, 12, 7), self.prog1, status=Lesson.Status.SCHEDULED)
        with frozen(NOW):
            payload = dashboard.month_payload(2026, 12, now=NOW)
        self.assertTrue(payload["is_future_month"])
        self.assertEqual(len(payload["days"]), 31)
        self.assertTrue(all(d["is_future"] and d["scheduled_groups"] is None for d in payload["days"]))

    def test_current_month_lists_past_days_and_today(self):
        self.mark(self.lesson(dt.date(2026, 11, 2), self.prog1), dict(zip(self.a, (P, P, P))))  # понедельник
        self.mark(self.lesson(dt.date(2026, 11, 3), self.prog2), dict(zip(self.b, (P, A))))  # вторник
        with frozen(NOW):
            days = dashboard.month_days(2026, 11, now=NOW)
        self.assertEqual(len(days), 30)
        self.assertEqual([d["status"] for d in days[:6]], ["computed", "computed", "computed", "computed", "live", "future"])
        self.assertEqual((days[1]["scheduled_groups"], days[2]["scheduled_groups"]), (1, 1))
        self.assertEqual((days[1]["active_groups"], days[1]["active_students"]), (1, 3))  # прежние имена полей

    def test_summary_compares_study_days(self):
        self.week()
        with frozen(NOW):
            payload = dashboard.month_payload(2026, 10, now=NOW)
        groups = payload["summary"]["scheduled_groups"]
        self.assertEqual((groups["date"], groups["value"], groups["held_groups"]), (SAT, 1, 1))
        students = payload["summary"]["scheduled_students"]
        self.assertEqual((students["value"], students["previous_value"], students["change"]), (2, 3, -1))
        self.assertEqual(students["attended_students"], 1)
        attendance = payload["summary"]["attendance_percent"]
        self.assertEqual(attendance["month_average"], 60.0)  # 9 из 15 за неделю
        self.assertEqual(payload["trends"]["groups"]["average"], 1.0)  # по учебным дням
        self.assertEqual(payload["summary"]["active_groups"], groups)


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
        with frozen(NOW):
            for role in User.Role.values:
                self.as_role(role)
                for suffix in ("", "snapshots/", "summary/", "trends/"):
                    response = self.client.get(URL + suffix)
                    self.assertEqual(response.status_code, 200, (role, suffix, response.content[:200]))

    def test_isolated_roles_pass_middleware_with_jwt(self):
        with frozen(NOW):
            for role in (User.Role.ACCOUNTANT, User.Role.SALES_MANAGER, User.Role.DOP):
                self.client.credentials()
                self.login_jwt(role)
                self.assertEqual(self.client.get(URL).status_code, 200, role)

    def test_month_selection_and_validation(self):
        self.as_role(User.Role.TEACHER)
        self.week()
        with frozen(NOW):
            response = self.client.get(URL, {"year": 2026, "month": 10})
            self.assertEqual(response.status_code, 200)
            self.assertEqual((response.data["month_label"], len(response.data["days"])), ("Октябрь", 31))
            self.assertEqual(response.data["days"][4]["scheduled_students"], 3)
            self.assertFalse(response.data["can_edit"])
            future = self.client.get(URL, {"year": 2026, "month": 12})
            self.assertEqual(future.status_code, 200)
            self.assertTrue(future.data["is_future_month"])
            self.assertEqual(self.client.get(URL, {"year": 2028, "month": 1}).status_code, 400)
            self.assertEqual(self.client.get(URL, {"month": 13}).status_code, 400)
            self.assertEqual(self.client.get(URL, {"year": "abc"}).status_code, 400)
            default = self.client.get(URL).data
            self.assertEqual((default["year"], default["month"], default["is_current_month"]), (2026, 11, True))
            trends = self.client.get(URL + "trends/", {"year": 2026, "month": 10}).data["trends"]
            self.assertEqual(set(trends), {"attendance", "homework", "groups", "students"})

    def test_correction_requires_permission(self):
        with frozen(NOW):
            for role in (User.Role.TEACHER, User.Role.TEAM_LEAD, User.Role.ACCOUNTANT, User.Role.ASSISTANT):
                self.as_role(role)
                response = self.client.patch(URL + "snapshots/2026-11-01/", {"scheduled_groups": 5}, format="json")
                self.assertEqual(response.status_code, 403, role)
            self.assertFalse(DailyPerformanceSnapshot.objects.exists())

    def test_admin_corrects_past_day(self):
        admin = self.as_role(User.Role.ADMIN)
        self.week()
        with frozen(NOW):
            response = self.client.patch(URL + "snapshots/2026-10-05/",
                                         {"held_groups": 0, "attendance_percent": "88.5", "comment": "Сверка"},
                                         format="json")
            self.assertEqual(response.status_code, 200, response.data)
            snapshot = DailyPerformanceSnapshot.objects.get(date=MON)
            self.assertEqual((snapshot.held_groups, snapshot.attendance_percent), (0, Decimal("88.5")))
            self.assertEqual(snapshot.scheduled_groups, 1)  # остальное — из записей LMS
            self.assertEqual(set(snapshot.manual_fields), {"held_groups", "attendance_percent"})
            self.assertEqual(snapshot.corrected_by, admin)
            # Прежнее имя поля тоже принимается.
            self.assertEqual(self.client.patch(URL + "snapshots/2026-10-05/", {"active_students": 4},
                                               format="json").status_code, 200)
            self.assertEqual(DailyPerformanceSnapshot.objects.get(date=MON).scheduled_students, 4)
            self.assertTrue(self.client.get(URL).data["can_edit"])
            self.assertEqual(self.client.patch(URL + "snapshots/2026-11-09/", {"held_groups": 1},
                                               format="json").status_code, 400)
            self.assertEqual(self.client.patch(URL + "snapshots/2026-10-05/", {}, format="json").status_code, 400)
            self.assertEqual(self.client.patch(URL + "snapshots/2026-10-05/", {"attendance_percent": 150},
                                               format="json").status_code, 400)

    def test_explicit_django_permission_allows_correction(self):
        from django.contrib.auth.models import Permission

        user = self.as_role(User.Role.TEAM_LEAD)
        user.user_permissions.add(Permission.objects.get(codename="change_dailyperformancesnapshot"))
        self.client.force_authenticate(User.objects.get(pk=user.pk))
        with frozen(NOW):
            response = self.client.patch(URL + "snapshots/2026-11-05/", {"scheduled_students": 7}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            today = self.client.get(URL).data["days"][4]
            self.assertEqual((today["scheduled_students"], today["status"]), (7, "live"))
