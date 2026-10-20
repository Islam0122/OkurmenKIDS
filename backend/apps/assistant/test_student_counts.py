"""Monthly report — how students are counted: one student is one row,
whatever their group; total = active + paused + withdrawn + completed;
«Деактивированы» is the WITHDRAWN status on the month's last day, «за месяц»
the unique students deactivated within it; «новые» enrolled in the month.
"""
from __future__ import annotations

import datetime as dt

from django.utils import timezone

from apps.academy.models import Attendance, Group, Student
from apps.academy.services import student_status
from apps.academy.services.student_enrollment import transfer_student
from apps.assistant import monthly
from apps.assistant.test_retention import P_END, P_START, PP_START, RetentionBase
from apps.assistant.tests import TODAY

EARLY = PP_START - dt.timedelta(days=60)
STATUS_KEYS = ("students_active", "students_paused", "students_withdrawn", "students_completed")


class StudentCountTests(RetentionBase):
    def setUp(self):
        super().setUp()
        Student.objects.all().delete()  # every case builds its own roster

    def make(self, n: int, group: Group | None = None, enrolled: dt.date | None = EARLY) -> list[Student]:
        group = group or self.g1
        return [Student.objects.create(first_name=f"S{i}", last_name=group.name if group else "",
                                       group=group, enrollment_date=enrolled) for i in range(n)]

    def overview(self, start: dt.date = P_START) -> dict:
        return monthly.monthly_report(start.year, start.month)["overview"]

    def assertAddsUp(self, o: dict):
        self.assertEqual(o["students_total"], sum(o[k] for k in STATUS_KEYS))

    def test_88_students_8_deactivated_rest_active(self):
        students = self.make(44) + self.make(44, group=self.g2)
        for s in students[:8]:
            student_status.deactivate_student(s, reason="schedule", event_date=P_START + dt.timedelta(days=5))
        o = self.overview()
        self.assertEqual((o["students_total"], o["students_active"], o["students_withdrawn"]), (88, 80, 8))
        self.assertEqual(o["students_deactivated"], 8)
        self.assertAddsUp(o)

    def test_four_students_with_another_status_explain_the_gap(self):
        """88 total, 8 deactivated, 76 active: the other 4 are paused or have completed."""
        students = self.make(88)
        for s in students[:8]:
            student_status.deactivate_student(s, reason="schedule", event_date=P_START + dt.timedelta(days=5))
        for s in students[8:10]:
            student_status.pause_student(s, reason="health", event_date=P_START + dt.timedelta(days=3))
        for s in students[10:12]:
            Student.objects.filter(pk=s.pk).update(status=Student.Status.COMPLETED, is_active=False)
        o = self.overview()
        self.assertEqual(
            (o["students_total"], o["students_active"], o["students_withdrawn"], o["students_paused"], o["students_completed"]),
            (88, 76, 8, 2, 2),
        )
        self.assertAddsUp(o)

    def test_withdrawn_before_the_month_is_not_deactivated_in_it(self):
        students = self.make(10)
        student_status.deactivate_student(students[0], reason="schedule", event_date=PP_START + dt.timedelta(days=2))
        o = self.overview()
        self.assertEqual((o["students_withdrawn"], o["students_deactivated"]), (1, 0))  # a stock vs a flow
        self.assertEqual((o["students_total"], o["students_active"]), (10, 9))

    def test_student_in_two_groups_counts_once(self):
        """Moved between groups in the month: one student in the totals,
        each group keeps the attendance it really had."""
        (student,) = self.make(1)
        before = self.lesson(P_START + dt.timedelta(days=1), group=self.g1)
        self.mark(before, student)
        transfer_student(student, group=self.g2, event_date=P_START + dt.timedelta(days=10))
        after = self.lesson(P_START + dt.timedelta(days=15), group=self.g2)
        self.mark(after, student, Attendance.Status.ABSENT)
        report = monthly.monthly_report(P_START.year, P_START.month)
        o = report["overview"]
        self.assertEqual((o["students_total"], o["students_active"], o["students_without_group"]), (1, 1, 0))
        by_group = {g["group"]["name"]: g for g in report["attendance"]["groups"]}
        self.assertEqual((by_group["PRO-01"]["attended"], by_group["PRO-02"]["absent"]), (1, 1))
        self.assertEqual(sum(g["students"] for g in report["attendance"]["groups"]), 1)

    def test_active_student_without_group(self):
        self.make(3)
        Student.objects.create(first_name="No", last_name="Group", group=None, enrollment_date=EARLY)
        o = self.overview()
        self.assertEqual((o["students_total"], o["students_active"], o["students_without_group"]), (4, 4, 1))
        self.assertEqual(o["students_withdrawn"], 0)  # no group is not «deactivated»

    def test_new_students_in_the_selected_month(self):
        self.make(2)
        self.make(1, enrolled=P_START + dt.timedelta(days=4))
        self.make(1, enrolled=P_END)
        (no_date,) = self.make(1, enrolled=None)
        Student.objects.filter(pk=no_date.pk).update(
            created_at=timezone.make_aware(dt.datetime.combine(P_START + dt.timedelta(days=2), dt.time(12))))
        self.make(1, enrolled=TODAY)  # after the month: neither new nor counted in it
        o = self.overview()
        self.assertEqual((o["students_new"], o["students_total"]), (3, 5))
        previous = self.overview(PP_START)
        self.assertEqual((previous["students_new"], previous["students_total"]), (0, 2))

    def test_deactivated_after_the_period_starts(self):
        students = self.make(5)
        student_status.deactivate_student(students[0], reason="schedule", event_date=P_START + dt.timedelta(days=10))
        student_status.deactivate_student(students[1], reason="schedule", event_date=TODAY)  # after the month
        o = self.overview()
        self.assertEqual((o["students_total"], o["students_active"], o["students_withdrawn"], o["students_deactivated"]),
                         (5, 4, 1, 1))
        earlier = self.overview(PP_START)  # the month before: everybody was still active
        self.assertEqual((earlier["students_active"], earlier["students_withdrawn"], earlier["students_deactivated"]),
                         (5, 0, 0))

    def test_different_months_and_years(self):
        self.make(2)
        a_year_ago = dt.date(P_START.year - 1, P_START.month, 1)
        self.make(1, enrolled=a_year_ago + dt.timedelta(days=3))
        old = self.overview(a_year_ago)
        self.assertEqual((old["students_total"], old["students_new"]), (1, 1))
        o = self.overview()
        self.assertEqual((o["students_total"], o["students_new"]), (3, 0))
        self.assertEqual(monthly.monthly_report(a_year_ago.year, a_year_ago.month)["year"], a_year_ago.year)

    def test_empty_database(self):
        o = self.overview()
        for key in ("students_total", "students_new", "students_deactivated", "students_without_group", *STATUS_KEYS):
            self.assertEqual(o[key], 0, key)
        self.assertIsNone(o["attendance_percent"])

    def test_api_and_dashboard_use_the_same_counts(self):
        students = self.make(6)
        student_status.deactivate_student(students[0], reason="schedule", event_date=P_START + dt.timedelta(days=1))
        student_status.pause_student(students[1], reason="health", event_date=P_START + dt.timedelta(days=1))
        Student.objects.filter(pk=students[2].pk).update(status=Student.Status.COMPLETED, is_active=False)
        data = self.client.get(self.url("monthly-report"), {"year": P_START.year, "month": P_START.month}).data["overview"]
        self.assertEqual({k: data[k] for k in ("students_total", *STATUS_KEYS)},
                         {"students_total": 6, "students_active": 3, "students_paused": 1,
                          "students_withdrawn": 1, "students_completed": 1})
        cards = self.client.get(self.url("dashboard")).data["cards"]
        self.assertEqual((cards["students_total"], cards["active_students"]), (6, 3))
