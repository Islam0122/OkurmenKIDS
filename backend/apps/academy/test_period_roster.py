"""Regression: Team Lead statistics must belong to the selected month.

Bug: with September selected the LMS showed October's 110 students instead
of September's 97 — every student count read the *live* roster
(Student.status today) while only lessons/attendance/homework followed the
period. Fixed by services.student_roster: the roster of a period is rebuilt
from the StudentStatusEvent ledger on the period's last day.

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import Course, Group, Student, StudentStatusEvent
from apps.academy.services import student_roster
from apps.academy.services.academy_monthly_report import compute_academy_monthly_stats
from apps.academy.services.analytics.dashboard import get_dashboard
from apps.academy.services.kpi_engine import KPIEngine
from apps.academy.services.reports import ReportFilters, build_group_rows, build_overview
from apps.academy.services.student_enrollment import transfer_student
from apps.academy.services.student_status import continue_student, deactivate_student, pause_student
from apps.users.models import User

TODAY = dt.date(2026, 11, 1)
SEPTEMBER = {"period": "custom", "start_date": "2026-09-01", "end_date": "2026-09-30"}
OCTOBER = {"period": "custom", "start_date": "2026-10-01", "end_date": "2026-10-31"}


class PeriodRosterTests(TestCase):
    """Group A/B. September: 97 active students; October: 110.

    * 93 study since August (group A), 2 joined in September;
    * Leaver: active all September, left on 5 October;
    * Mover: in group A in September, moved to B on 10 October;
    * Pauser: paused on 20 September, back on 3 October;
    * 13 joined in October.
    """

    def setUp(self):
        course = Course.objects.create(name="Python", count_lesson=10)
        self.group_a = Group.objects.create(name="A", course=course, start_date=dt.date(2026, 8, 1))
        self.group_b = Group.objects.create(name="B", course=course, start_date=dt.date(2026, 8, 1))

        self._students(93, self.group_a, dt.date(2026, 8, 10))
        self._students(2, self.group_a, dt.date(2026, 9, 15))
        self._students(13, self.group_b, dt.date(2026, 10, 12))
        self.leaver = self._students(1, self.group_a, dt.date(2026, 8, 10))[0]
        self.mover = self._students(1, self.group_a, dt.date(2026, 8, 10))[0]
        self.pauser = self._students(1, self.group_a, dt.date(2026, 8, 10))[0]

        deactivate_student(self.leaver, reason=StudentStatusEvent.Reason.RELOCATION, event_date=dt.date(2026, 10, 5))
        transfer_student(self.mover, group=self.group_b, event_date=dt.date(2026, 10, 10))
        pause_student(self.pauser, reason=StudentStatusEvent.Reason.HEALTH, event_date=dt.date(2026, 9, 20))
        continue_student(self.pauser, event_date=dt.date(2026, 10, 3))

    def _students(self, count: int, group: Group, since: dt.date) -> list[Student]:
        students = [
            Student.objects.create(first_name=f"{group.name}-{since}-{i}", group=group, enrollment_date=since)
            for i in range(count)
        ]
        Student.objects.filter(pk__in=[s.pk for s in students]).update(
            created_at=timezone.make_aware(dt.datetime.combine(since, dt.time(9)))
        )
        return students

    def filters(self, params) -> ReportFilters:
        return ReportFilters.from_query(params, today=TODAY)

    # -- Test 1-3: September 97, October 110, back to September 97 ------------

    def test_overview_september_october_and_back(self):
        self.assertEqual(build_overview(self.filters(SEPTEMBER))["students"]["active"], 97)
        self.assertEqual(build_overview(self.filters(OCTOBER))["students"]["active"], 110)
        self.assertEqual(build_overview(self.filters(SEPTEMBER))["students"]["active"], 97)

    def test_overview_other_student_figures_follow_the_month(self):
        september = build_overview(self.filters(SEPTEMBER))["students"]
        october = build_overview(self.filters(OCTOBER))["students"]
        # September: 97 active + the pauser; the 13 October students didn't exist yet.
        self.assertEqual((september["total"], september["paused"], september["new"], september["left"]), (98, 1, 2, 0))
        # October: 110 active + the leaver (withdrawn); the pauser is back.
        self.assertEqual((october["total"], october["paused"], october["new"], october["left"]), (111, 0, 13, 1))

    def test_last_month_preset_is_october(self):
        self.assertEqual(build_overview(self.filters({"period": "last_month"}))["students"]["active"], 110)

    def test_group_rows_use_the_month_groups(self):
        september = {row["name"]: row["students"] for row in build_group_rows(self.filters(SEPTEMBER))}
        october = {row["name"]: row["students"] for row in build_group_rows(self.filters(OCTOBER))}
        # The mover is A's in September and B's in October — never counted twice.
        self.assertEqual(september["A"]["active"], 97)
        self.assertEqual(september["B"]["active"], 0)
        self.assertEqual(october["A"]["active"], 93 + 2 + 1)  # + the pauser, back in A
        self.assertEqual(october["B"]["active"], 13 + 1)  # + the mover

    def test_academy_monthly_report(self):
        self.assertEqual(compute_academy_monthly_stats(2026, 9)["students_count"], 97)
        self.assertEqual(compute_academy_monthly_stats(2026, 10)["students_count"], 110)
        self.assertEqual(compute_academy_monthly_stats(2026, 9)["group_stats"]["students_active"], 97)

    def test_analytics_dashboard_and_kpi_engine(self):
        for start, end, expected in (
            (dt.date(2026, 9, 1), dt.date(2026, 9, 30), 97),
            (dt.date(2026, 10, 1), dt.date(2026, 10, 31), 110),
        ):
            dashboard = get_dashboard(period="custom", start_date=start, end_date=end, today=TODAY)
            self.assertEqual(dashboard["students"]["active_students"]["value"], expected)
            counts = KPIEngine.counts(self.filters({"period": "custom", "start_date": str(start), "end_date": str(end)}).scope(), today=TODAY)
            self.assertEqual(counts.students_active, expected)
        # The October leaver left in October, not in September.
        september = KPIEngine.counts(self.filters(SEPTEMBER).scope(), today=TODAY)
        october = KPIEngine.counts(self.filters(OCTOBER).scope(), today=TODAY)
        self.assertEqual((september.students_left, october.students_left), (0, 1))

    def test_roster_of_a_student_on_any_day(self):
        roster_sep = student_roster.roster_on(dt.date(2026, 9, 30))
        roster_oct = student_roster.roster_on(dt.date(2026, 10, 31))
        self.assertEqual(roster_sep[self.leaver.pk].status, Student.Status.ACTIVE)
        self.assertEqual(roster_oct[self.leaver.pk].status, Student.Status.WITHDRAWN)
        self.assertEqual((roster_sep[self.mover.pk].group_id, roster_oct[self.mover.pk].group_id),
                         (self.group_a.pk, self.group_b.pk))
        self.assertEqual(roster_sep[self.pauser.pk].status, Student.Status.PAUSED)
        self.assertEqual(roster_oct[self.pauser.pk].status, Student.Status.ACTIVE)
        self.assertEqual(len(student_roster.roster_on(dt.date(2026, 7, 31))), 0)

    # -- Test 4: the API answers by the requested month, every time ---------

    def test_team_lead_api(self):
        lead = User.objects.create_user(
            username="lead", email="lead@okurmen.kg", password="Str0ngPassw0rd!", first_name="Lead",
            role=User.Role.TEAM_LEAD,
        )
        client = APIClient()
        client.force_authenticate(lead)
        for params, expected in ((SEPTEMBER, 97), (OCTOBER, 110), (SEPTEMBER, 97)):
            response = client.get("/api/v1/reports/overview/", params)
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.data["students"]["active"], expected)
            self.assertEqual(str(response.data["filters"]["start_date"]), params["start_date"])
