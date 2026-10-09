"""Monthly report — retention, churn and finance sections; the departure
history behind them (StudentStatusEvent) and every way a student leaves.
"""
from __future__ import annotations

import datetime as dt
import importlib

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.academy.models import Attendance, GroupTeacher, Homework, HomeworkResult, Lesson, Student, StudentStatusEvent
from apps.academy.services import student_status
from apps.assistant import monthly, retention
from apps.assistant.history import roster_on
from apps.assistant.monthly_pdf import build_monthly_pdf
from apps.assistant.tests import PASSWORD, TODAY, AssistantTestBase, make_teacher
from apps.users.models import User

E = StudentStatusEvent.EventType


def month_of(day: dt.date) -> tuple[dt.date, dt.date]:
    start = day.replace(day=1)
    nxt = (start + dt.timedelta(days=32)).replace(day=1)
    return start, nxt - dt.timedelta(days=1)


# The previous (closed) month and the one before it.
P_START, P_END = month_of(TODAY.replace(day=1) - dt.timedelta(days=1))
PP_START, PP_END = month_of(P_START - dt.timedelta(days=1))


class RetentionBase(AssistantTestBase):
    def setUp(self):
        super().setUp()
        early = PP_START - dt.timedelta(days=60)
        self.g1.start_date = early
        self.g1.save(update_fields=["start_date"])
        self.g2.start_date = early
        self.g2.save(update_fields=["start_date"])
        self.gt2 = GroupTeacher.objects.create(group=self.g2, teacher=self.aibek, subject=self.python)
        Student.objects.filter(pk__in=[self.s1.pk, self.s2.pk]).update(enrollment_date=early)
        self.s1.refresh_from_db()
        self.s2.refresh_from_db()
        self.admin = User.objects.create_superuser(username="root", email="root@o.kg", password=PASSWORD)

    def lesson(self, day, group=None, number=1, **extra):
        group = group or self.g1
        gt = self.gt1 if group == self.g1 else self.gt2
        return Lesson.objects.create(group=group, group_teacher=gt, subject=self.python, teacher=gt.teacher,
                                     lesson_number=number, date=day, start_time=dt.time(16), end_time=dt.time(17, 30),
                                     **{"status": Lesson.Status.COMPLETED, **extra})

    def mark(self, lesson, student, status_=Attendance.Status.PRESENT):
        return Attendance.objects.create(lesson=lesson, student=student, status=status_)

    def report(self, start=P_START, **kwargs):
        return monthly.monthly_report(start.year, start.month, **kwargs)


class HistoryOnDateTests(RetentionBase):
    """A past month is reported as it was, not as things are today."""

    def test_left_after_the_month_still_active_in_it(self):
        student_status.deactivate_student(self.s1, reason="schedule", event_date=TODAY)
        roster = {r.student.pk: r for r in roster_on(P_END)}
        self.assertEqual(roster[self.s1.pk].status, Student.Status.ACTIVE)
        self.assertEqual(roster[self.s1.pk].group_id, self.g1.pk)
        report = self.report()
        self.assertEqual(report["overview"]["students_active"], 2)
        self.assertEqual(report["departures"]["total"], 0)

    def test_left_and_returned_keeps_the_departure(self):
        student_status.deactivate_student(self.s1, reason="financial_issues", event_date=P_START + dt.timedelta(days=3))
        student_status.reactivate_student(self.s1, group=self.g1, event_date=TODAY)
        self.assertEqual(StudentStatusEvent.objects.filter(student=self.s1, event_type=E.DEACTIVATED).count(), 1)
        report = self.report()
        self.assertEqual(report["overview"]["students_active"], 1)  # on the month's last day they were gone
        self.assertEqual(report["overview"]["students_withdrawn"], 1)
        row = report["departures"]["rows"][0]
        self.assertEqual((row["student_id"], row["reason_label"], row["returned_on"]), (self.s1.pk, "Финансовые трудности", TODAY))
        self.assertEqual((report["departures"]["returned"], report["departures"]["returned_percent"]), (1, 100))

    def test_transfer_after_the_month_keeps_the_old_group(self):
        lesson = self.lesson(P_START + dt.timedelta(days=2))
        self.mark(lesson, self.s1)
        from apps.academy.services.student_enrollment import transfer_student
        transfer_student(self.s1, group=self.g2, event_date=TODAY)
        roster = {r.student.pk: r for r in roster_on(P_END)}
        self.assertEqual(roster[self.s1.pk].group_id, self.g1.pk)
        rows = self.report()["attendance"]["groups"]
        self.assertEqual([g["group"]["name"] for g in rows], ["PRO-01"])


class DepartureRecordTests(RetentionBase):
    def test_snapshot_last_activity_and_study_days(self):
        lesson = self.lesson(P_START + dt.timedelta(days=1))
        self.mark(lesson, self.s1)
        later = self.lesson(P_START + dt.timedelta(days=4), number=2)
        self.mark(later, self.s1, Attendance.Status.ABSENT)
        self.lesson(P_START + dt.timedelta(days=5), number=3, status=Lesson.Status.CANCELLED)
        day = P_START + dt.timedelta(days=10)
        event = student_status.deactivate_student(self.s1, reason="low_motivation", comment="", event_date=day,
                                                  performed_by=self.admin)
        self.assertEqual(event.last_activity_date, lesson.date)  # an absence is not activity
        self.assertEqual(event.study_days, (day - self.s1.enrollment_date).days)
        self.assertEqual((event.group, event.performed_by), (self.g1, self.admin))

    def test_reasons(self):
        with self.assertRaises(ValidationError):  # an earlier reason is no longer offered for a departure
            student_status.deactivate_student(self.s1, reason="family_circumstances")
        with self.assertRaises(ValidationError):
            student_status.deactivate_student(self.s1, reason="other", comment=" ")
        student_status.pause_student(self.s2, reason="health")  # pauses keep their reasons
        event = student_status.deactivate_student(self.s1, reason="other", comment="Уехали на сборы")
        self.assertEqual(event.comment, "Уехали на сборы")

    def test_assistant_api_offers_the_departure_reasons(self):
        reasons = [r["value"] for r in self.client.get(self.url("options")).data["deactivation_reasons"]]
        self.assertEqual(reasons, list(StudentStatusEvent.DEACTIVATION_REASONS))
        response = self.client.post(self.url("student-deactivate", self.s1.pk), {"reason": "health"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(self.url("student-deactivate", self.s1.pk), {"reason": "transport"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event = StudentStatusEvent.objects.get(student=self.s1, event_type=E.DEACTIVATED)
        self.assertEqual((event.reason, event.performed_by), ("transport", self.assistant))

    def test_backfill_migration_fills_old_departures(self):
        lesson = self.lesson(P_START + dt.timedelta(days=1))
        self.mark(lesson, self.s1)
        old = StudentStatusEvent.objects.create(student=self.s1, event_type=E.DEACTIVATED, reason="",
                                                group=self.g1, event_date=P_START + dt.timedelta(days=5))
        migration = importlib.import_module("apps.academy.migrations.0021_student_departure_history")
        migration.backfill_departures(django_apps, None)
        old.refresh_from_db()
        self.assertEqual(old.last_activity_date, lesson.date)
        self.assertEqual(old.reason, "")  # never a guessed reason


class DepartureSectionTests(RetentionBase):
    def setUp(self):
        super().setUp()
        self.s3 = Student.objects.create(first_name="Nur", last_name="B", group=self.g2,
                                         enrollment_date=PP_START - dt.timedelta(days=30))
        day = P_START + dt.timedelta(days=5)
        self.lesson(P_START + dt.timedelta(days=2))
        self.lesson(P_START + dt.timedelta(days=2), group=self.g2)
        student_status.deactivate_student(self.s1, reason="schedule", event_date=day)
        student_status.reactivate_student(self.s1, group=self.g1, event_date=day + dt.timedelta(days=1))
        student_status.deactivate_student(self.s1, reason="schedule", event_date=day + dt.timedelta(days=3))
        # A pre-reason record: blank reason → «Не указана».
        StudentStatusEvent.objects.create(student=self.s3, event_type=E.DEACTIVATED, reason="", group=self.g2,
                                          event_date=day, previous_status="active")
        Student.objects.filter(pk=self.s3.pk).update(status=Student.Status.WITHDRAWN, is_active=False)
        student_status.complete_student(self.s2)  # a graduate is not a departure (dated today)
        StudentStatusEvent.objects.create(student=self.s2, event_type=E.DEACTIVATED, reason="relocation",
                                          group=self.g1, event_date=PP_START + dt.timedelta(days=3))

    def test_counts_reasons_and_previous_month(self):
        d = self.report()["departures"]
        self.assertEqual(d["total"], 2)  # s1 left twice — counted once
        self.assertEqual({r["key"]: r["count"] for r in d["by_reason"]}, {"schedule": 1, "unknown": 1})
        self.assertEqual({r["key"]: r["percent"] for r in d["by_reason"]}, {"schedule": 50, "unknown": 50})
        self.assertEqual(d["unknown"], 1)
        self.assertEqual([r["reason_label"] for r in d["rows"] if r["reason"] == "unknown"], ["Не указана"])
        self.assertEqual((d["previous_total"], d["change"]), (1, 1))
        self.assertEqual({r["label"] for r in d["by_group"]}, {"PRO-01", "PRO-02"})
        self.assertEqual({r["label"] for r in d["by_trainer"]}, {"Islam", "Aibek"})
        self.assertEqual(d["completed"], 0)  # the completion is dated today, not in the month

    def test_filters(self):
        self.assertEqual(self.report(filters={"group": self.g2.pk})["departures"]["total"], 1)
        self.assertEqual(self.report(filters={"teacher": self.islam.pk})["departures"]["rows"][0]["student_id"], self.s1.pk)
        d = self.report(filters={"reason": "unknown"})["departures"]
        self.assertEqual(([r["student_id"] for r in d["rows"]], d["total_unfiltered"]), ([self.s3.pk], 2))
        self.assertEqual((d["total"], d["month_total"], d["change"]), (1, 2, 1))  # compared on all departures
        api = self.client.get(self.url("monthly-report"), {"year": P_START.year, "month": P_START.month, "reason": "schedule"})
        self.assertEqual([r["student_id"] for r in api.data["departures"]["rows"]], [self.s1.pk])

    def test_inactive_is_not_departed(self):
        report = self.report()
        departed = {r["student_id"] for r in report["departures"]["rows"]}
        inactive = {r["student_id"] for r in report["inactive"]["students"]}
        self.assertFalse(departed & inactive)


class InactivityTests(RetentionBase):
    def test_days_without_activity_need_held_lessons(self):
        first = self.lesson(P_START + dt.timedelta(days=1))
        self.mark(first, self.s1)
        self.mark(first, self.s2)
        for i, offset in enumerate((10, 15, 20), start=2):
            lesson = self.lesson(P_START + dt.timedelta(days=offset), number=i)
            self.mark(lesson, self.s1, Attendance.Status.ABSENT)
            self.mark(lesson, self.s2)
        self.lesson(P_END, number=9, status=Lesson.Status.CANCELLED)
        ina = self.report()["inactive"]
        rows = {r["student_id"]: r for r in ina["students"]}
        self.assertEqual(rows[self.s1.pk]["days_inactive"], (P_END - first.date).days)
        self.assertEqual(rows[self.s1.pk]["last_attended"], first.date)
        self.assertEqual(rows[self.s1.pk]["absent"], 3)
        self.assertTrue(rows[self.s1.pk]["action"])
        # s2 came to the last lesson; nothing held after it → not inactive however many days passed.
        self.assertTrue(self.s2.pk not in rows or rows[self.s2.pk]["days_inactive"] is None
                        or rows[self.s2.pk]["days_inactive"] < 7)
        self.assertEqual(ina["counts"]["inactive"], 1)

    @override_settings(ASSISTANT_INACTIVITY_DAYS=(3, 5, 8))
    def test_thresholds_from_settings(self):
        first = self.lesson(P_START + dt.timedelta(days=1))
        self.mark(first, self.s1)
        later = self.lesson(P_START + dt.timedelta(days=7), number=2)
        self.mark(later, self.s1, Attendance.Status.ABSENT)
        ina = self.report()["inactive"]
        self.assertEqual(ina["thresholds"], [3, 5, 8])
        self.assertGreaterEqual(ina["counts"]["long_inactive"], 1)

    def test_homework_counts_as_activity(self):
        first = self.lesson(P_START + dt.timedelta(days=1))
        self.mark(first, self.s1, Attendance.Status.ABSENT)
        hw = Homework.objects.create(lesson=first, title="DNS", deadline=first.date + dt.timedelta(days=2))
        from django.utils import timezone
        HomeworkResult.objects.create(homework=hw, student=self.s1, status=HomeworkResult.Status.CHECKED,
                                      submitted_at=timezone.make_aware(dt.datetime.combine(P_START + dt.timedelta(days=2), dt.time(12))))
        rows = {r["student_id"]: r for r in self.report()["inactive"]["students"]}
        if self.s1.pk in rows:
            self.assertEqual(rows[self.s1.pk]["last_homework"], P_START + dt.timedelta(days=2))


class FinanceAndAccessTests(RetentionBase):
    def test_finance_only_for_admin_and_never_invented(self):
        assistant = self.client.get(self.url("monthly-report"), {"year": P_START.year, "month": P_START.month}).data
        self.assertEqual(assistant["finance"], {"allowed": False, "note": "Финансовые данные доступны только администратору."})
        admin = APIClient()
        admin.force_authenticate(self.admin)
        finance = admin.get(self.url("monthly-report"), {"year": P_START.year, "month": P_START.month}).data["finance"]
        self.assertTrue(finance["allowed"])
        self.assertEqual(finance["status"], "insufficient_data")
        values = {m["label"]: m["value"] for m in finance["metrics"]}
        self.assertIsNone(values["Начислено за обучение"])
        self.assertIsNone(values["Фактические поступления"])
        self.assertIsNone(values["Потенциальный ежемесячный доход ушедших (оценка, не убыток)"])

    def test_roles(self):
        lead = User.objects.create_user(username="lead", email="l@o.kg", password=PASSWORD, role=User.Role.TEAM_LEAD)
        for user in (self.islam.user, lead):
            client = APIClient()
            client.force_authenticate(user)
            self.assertEqual(client.get(self.url("monthly-report")).status_code, status.HTTP_403_FORBIDDEN)

    def test_pdf_with_new_sections(self):
        self.lesson(P_START + dt.timedelta(days=1))
        student_status.deactivate_student(self.s1, reason="schedule", event_date=P_START + dt.timedelta(days=4))
        for allowed in (False, True):
            data = build_monthly_pdf(self.report(finance_allowed=allowed))
            self.assertTrue(data.startswith(b"%PDF"))

    def test_no_n_plus_one(self):
        def queries():
            with CaptureQueriesContext(connection) as ctx:
                self.report()
            return len(ctx.captured_queries)
        self.lesson(P_START + dt.timedelta(days=1))
        base = queries()
        for i in range(6):
            student = Student.objects.create(first_name=f"S{i}", last_name="X", group=self.g1, enrollment_date=PP_START)
            student_status.deactivate_student(student, reason="schedule", event_date=P_START + dt.timedelta(days=2))
        self.assertLessEqual(queries(), base + 2)


class AdminDepartureTests(RetentionBase):
    def setUp(self):
        super().setUp()
        self.web = Client()
        self.web.force_login(self.admin)

    def test_is_active_is_read_only_on_the_form(self):
        url = reverse("admin:academy_student_change", args=[self.s1.pk])
        form = self.web.get(url).context["adminform"].form
        self.assertNotIn("is_active", form.fields)

    def test_bulk_activate_goes_through_history(self):
        student_status.deactivate_student(self.s1, reason="schedule")
        self.web.post(reverse("admin:academy_student_changelist"),
                      {"action": "activate_students", "_selected_action": [self.s1.pk]})
        self.s1.refresh_from_db()
        self.assertEqual(self.s1.status, Student.Status.ACTIVE)
        self.assertTrue(StudentStatusEvent.objects.filter(student=self.s1, event_type=E.REACTIVATED).exists())
        self.assertTrue(StudentStatusEvent.objects.filter(student=self.s1, event_type=E.DEACTIVATED).exists())

    def test_departure_history_page(self):
        student_status.deactivate_student(self.s1, reason="schedule", event_date=P_START + dt.timedelta(days=3))
        student_status.reactivate_student(self.s1, group=self.g1, event_date=P_START + dt.timedelta(days=9))
        StudentStatusEvent.objects.create(student=self.s2, event_type=E.DEACTIVATED, reason="", group=self.g1,
                                          event_date=P_START + dt.timedelta(days=4))
        body = self.web.get(reverse("admin:academy_student_departure_history")).content.decode()
        self.assertIn("Не указана", body)
        self.assertIn("Вернулся", body)
        self.assertIn((P_START + dt.timedelta(days=9)).strftime("%d.%m.%Y"), body)
