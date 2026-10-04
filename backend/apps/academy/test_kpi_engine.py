"""One KPI across the LMS — acceptance tests for services.kpi_engine.

Every report that shows a KPI (Reports: overview / group rows / group and
teacher detail; Analytics dashboard; Academy Monthly Report; Teacher
Monthly Report) must show the same numbers for the same period and
filters, and must move together when the underlying data changes.

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt

from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academy.models import (
    AcademyMonthlyReport,
    Attendance,
    Group,
    GroupTeacher,
    Homework,
    HomeworkResult,
    Lesson,
    Student,
    StudentStatusEvent,
)
from apps.academy.services.academy_monthly_report import compute_academy_monthly_stats
from apps.academy.services.analytics import get_dashboard
from apps.academy.services.kpi_engine import (
    KPICounts,
    KPIEngine,
    from_counts,
    kpi_status,
    total_kpi,
)
from apps.academy.services.monthly_report import compute_monthly_stats
from apps.academy.services.reports import (
    ReportFilters,
    build_group_detail,
    build_group_rows,
    build_overview,
    build_teacher_detail,
    build_teacher_rows,
)
from apps.academy.test_reports import SEPT, TODAY, ReportsTestBase, make_teacher

START, END = dt.date(2026, 9, 1), dt.date(2026, 9, 30)


class KPIEngineUnitTests(ReportsTestBase):
    def test_total_uses_exact_values_and_rounds_once(self):
        # attendance 2/3 = 66.666…, homework 1/3 = 33.333…, lessons 1/1 = 100,
        # progress 7.25 -> 72.5. Exact mean = 68.125 -> 68.1. Rounding each
        # metric first (66.7 + 33.3 + 100 + 72.5) / 4 = 68.125 happens to
        # agree here, so also check a case where it would not:
        result = from_counts(KPICounts(
            attendance_total=3, attendance_attended=2, homework_results=3, homework_submitted=1,
            lessons_due=1, lessons_held=1, avg_score=7.25,
        ))
        self.assertEqual(result.total, round((200 / 3 + 100 / 3 + 100 + 72.5) / 4, 1))
        tricky = from_counts(KPICounts(
            attendance_total=6, attendance_attended=5,     # 83.333…
            homework_results=6, homework_submitted=5,      # 83.333…
            lessons_due=6, lessons_held=5,                 # 83.333…
            avg_score=None,
        ))
        # Exact: 83.333… -> 83.3. Rounding the components first gives the
        # same 83.3 — and the engine's own metrics must equal round1(exact).
        self.assertEqual(tricky.total, 83.3)
        self.assertEqual(tricky.metrics["attendance"], 83.3)

    def test_retention_and_teacher_workload_are_not_in_the_total(self):
        base = KPICounts(attendance_total=10, attendance_attended=9, homework_results=10, homework_submitted=8,
                         lessons_due=4, lessons_held=4, avg_score=9.0)
        low_extras = from_counts(KPICounts(**{**base.__dict__, "students_active": 1, "students_left": 9,
                                              "teachers_active": 10, "teachers_with_lessons": 1}))
        high_extras = from_counts(KPICounts(**{**base.__dict__, "students_active": 9, "students_left": 1,
                                               "teachers_active": 1, "teachers_with_lessons": 1}))
        self.assertNotEqual(low_extras.metrics["retention"], high_extras.metrics["retention"])
        self.assertNotEqual(low_extras.metrics["teacher_workload"], high_extras.metrics["teacher_workload"])
        self.assertEqual(low_extras.total, high_extras.total)
        self.assertEqual(low_extras.total, round((90 + 80 + 100 + 90) / 4, 1))

    @override_settings(KPI_WEIGHTS={"attendance": 0.4, "homework": 0.3, "lesson_completion": 0.2, "progress": 0.1})
    def test_weights_come_from_settings(self):
        metrics = {"attendance": 90, "homework": 80, "lesson_completion": 100, "progress": 70}
        self.assertAlmostEqual(total_kpi(metrics), 90 * 0.4 + 80 * 0.3 + 100 * 0.2 + 70 * 0.1)

    def test_status_thresholds(self):
        self.assertEqual([kpi_status(v) for v in (90, 89.9, 75, 74.9, None)],
                         ["good", "attention", "attention", "low", "no_data"])

    def test_contract_shape(self):
        contract = KPIEngine.calculate(start=START, end=END, today=TODAY).as_contract()
        self.assertEqual(set(contract), {"metrics", "kpi"})
        self.assertEqual(set(contract["metrics"]),
                         {"attendance", "homework", "lesson_completion", "progress", "retention", "teacher_workload",
                          "test_score", "test_pass_rate"})
        self.assertEqual({"total", "status", "status_label", "weights"}, set(contract["kpi"]))


class SameKPIEverywhereTests(ReportsTestBase):
    """The main acceptance criterion: identical filters -> identical KPI."""

    def filters(self, **params):
        return ReportFilters.from_query({**SEPT, **params}, today=TODAY)

    def analytics(self, **kwargs):
        return get_dashboard(period="custom", start_date=START, end_date=END, today=TODAY, **kwargs)

    def assert_same(self, *contracts):
        first = contracts[0]
        for other in contracts[1:]:
            self.assertEqual(other["metrics"], first["metrics"])
            self.assertEqual(other["kpi"]["total"], first["kpi"]["total"])
            self.assertEqual(other["kpi"]["status"], first["kpi"]["status"])

    def academy_contract(self):
        stats = compute_academy_monthly_stats(2026, 9)
        return {"metrics": stats["metrics"], "kpi": stats["kpi"]}

    def all_three(self):
        reports = build_overview(self.filters())
        analytics = self.analytics()
        academy = self.academy_contract()
        return reports, analytics, academy

    # 1. One data set -> one KPI (Reports = Analytics = Academy Report)
    def test_whole_academy_same_kpi_in_all_three_reports(self):
        reports, analytics, academy = self.all_three()
        self.assert_same(reports, analytics, academy)
        self.assertIsNotNone(reports["kpi"]["total"])

    # 2. Same period -> same values, via the HTTP API too
    def test_same_kpi_through_the_api(self):
        api = APIClient()
        api.force_authenticate(self.admin)
        reports = api.get(reverse("reports-overview"), SEPT).json()
        analytics = api.get(reverse("analytics-dashboard"),
                            {"period": "custom", "start_date": "2026-09-01", "end_date": "2026-09-30"}).json()
        report = AcademyMonthlyReport.objects.create(year=2026, month=9)
        academy = api.get(f"/api/v1/academy-reports/{report.id}/").json()["stats"]
        self.assertEqual(reports["kpi"]["total"], analytics["kpi"]["total"])
        self.assertEqual(reports["kpi"]["total"], academy["kpi"]["total"])
        self.assertEqual(reports["metrics"], analytics["metrics"])
        self.assertEqual(reports["metrics"], academy["metrics"])

    # 3. Same set of groups -> same values
    def test_same_group_filter_same_kpi(self):
        group_id = self.pro1.id
        reports = build_overview(self.filters(group=str(group_id)))
        analytics = self.analytics(group_id=group_id)
        engine = KPIEngine.calculate(start=START, end=END, group_id=group_id, today=TODAY).as_contract()
        detail = build_group_detail(self.pro1, self.filters())
        self.assert_same(reports, analytics, engine, detail)
        row = next(r for r in build_group_rows(self.filters()) if r["id"] == group_id)
        self.assertEqual(row["kpi"], engine["kpi"]["total"])

    def test_same_program_and_subject_filters(self):
        for params, kwargs in (
            ({"program": str(self.other_course.id)}, {"course_id": self.other_course.id}),
            ({"subject": str(self.english.id)}, {"subject_id": self.english.id}),
        ):
            self.assert_same(build_overview(self.filters(**params)), self.analytics(**kwargs))

    # 4. Attendance change moves every report identically
    def test_attendance_change_moves_all_reports(self):
        before = self.all_three()
        Attendance.objects.filter(lesson=self.l2, student=self.s2).update(status=Attendance.Status.PRESENT)
        after = self.all_three()
        self.assert_same(*after)
        self.assertGreater(after[0]["metrics"]["attendance"], before[0]["metrics"]["attendance"])
        self.assertGreater(after[0]["kpi"]["total"], before[0]["kpi"]["total"])

    # 5. Homework change moves every report identically
    def test_homework_change_moves_all_reports(self):
        before = self.all_three()
        HomeworkResult.objects.filter(student=self.s2).update(status=HomeworkResult.Status.CHECKED, score=10)
        after = self.all_three()
        self.assert_same(*after)
        self.assertGreater(after[0]["metrics"]["homework"], before[0]["metrics"]["homework"])
        self.assertNotEqual(after[0]["kpi"]["total"], before[0]["kpi"]["total"])

    # 6. Retention change moves every report identically (but not the total)
    def test_retention_change_moves_all_reports(self):
        before = self.all_three()
        self.s1.status, self.s1.is_active = Student.Status.WITHDRAWN, False
        self.s1.save()
        StudentStatusEvent.objects.create(
            student=self.s1, event_type=StudentStatusEvent.EventType.DEACTIVATED,
            reason=StudentStatusEvent.Reason.RELOCATION, group=self.pro1, event_date=dt.date(2026, 9, 20),
        )
        after = self.all_three()
        self.assert_same(*after)
        self.assertLess(after[0]["metrics"]["retention"], before[0]["metrics"]["retention"])
        self.assertEqual(after[0]["kpi"]["total"], before[0]["kpi"]["total"])  # retention is not in the formula

    # 7. Empty data
    def test_empty_period_everywhere(self):
        empty = ReportFilters.from_query({"period": "custom", "start_date": "2026-01-01", "end_date": "2026-01-31"},
                                         today=TODAY)
        reports = build_overview(empty)
        analytics = get_dashboard(period="custom", start_date=dt.date(2026, 1, 1), end_date=dt.date(2026, 1, 31),
                                  today=TODAY)
        stats = compute_academy_monthly_stats(2026, 1)
        academy = {"metrics": stats["metrics"], "kpi": stats["kpi"]}
        self.assert_same(reports, analytics, academy)
        self.assertIsNone(reports["kpi"]["total"])
        self.assertEqual(reports["kpi"]["status"], "no_data")

    # 8. No students
    def test_group_without_students(self):
        engine = KPIEngine.calculate(start=START, end=END, group_id=self.empty.id, today=TODAY)
        self.assertIsNone(engine.metrics["retention"])
        self.assertIsNone(engine.total)
        self.assert_same(build_overview(self.filters(group=str(self.empty.id))), self.analytics(group_id=self.empty.id))

    # 9. No lessons
    def test_lessons_without_attendance_or_homework(self):
        Lesson.objects.all().delete()
        reports, analytics, academy = self.all_three()
        self.assert_same(reports, analytics, academy)
        self.assertIsNone(reports["metrics"]["lesson_completion"])
        self.assertIsNone(reports["kpi"]["total"])

    # 10. Inactive students
    def test_inactive_students_counted_identically(self):
        paused = Student.objects.create(first_name="Erlan", group=self.pro1, status=Student.Status.PAUSED,
                                        is_active=False)
        Attendance.objects.create(lesson=self.l1, student=paused, status=Attendance.Status.ABSENT)
        reports, analytics, academy = self.all_three()
        self.assert_same(reports, analytics, academy)
        # Attendance of an inactive student on a lesson in the period still counts.
        self.assertEqual(reports["metrics"]["attendance"], round(5 / 8 * 100, 1))

    # 11. Several groups: the total is over all records, never an average of group KPIs
    def test_multiple_groups_total_is_record_weighted(self):
        reports = build_overview(self.filters())
        rows = [r["kpi"] for r in build_group_rows(self.filters()) if r["kpi"] is not None]
        self.assertEqual(len(rows), 2)
        engine = KPIEngine.calculate(start=START, end=END, today=TODAY)
        self.assertEqual(reports["kpi"]["total"], engine.total)
        self.assertNotEqual(reports["kpi"]["total"], round(sum(rows) / len(rows), 1))

    # 12. Several teachers: Reports teacher filter = Analytics = Teacher Monthly Report
    def test_multiple_teachers_same_kpi(self):
        for teacher in (self.aziza, self.bek):
            reports = build_overview(self.filters(teacher=str(teacher.id)))
            analytics = self.analytics(teacher_id=teacher.id)
            monthly = compute_monthly_stats(teacher, 2026, 9)
            detail = build_teacher_detail(teacher, self.filters())
            self.assert_same(reports, analytics, detail, {"metrics": monthly["metrics"], "kpi": monthly["kpi"]})
            row = next(r for r in build_teacher_rows(self.filters()) if r["id"] == teacher.id)
            self.assertEqual(row["kpi"], reports["kpi"]["total"])

    def test_teacher_workload_only_informational(self):
        before = build_overview(self.filters())
        make_teacher("idle", first_name="Idle")  # active, teaches nothing
        after = build_overview(self.filters())
        self.assertLess(after["metrics"]["teacher_workload"], before["metrics"]["teacher_workload"])
        self.assertEqual(after["kpi"]["total"], before["kpi"]["total"])

    def test_future_lessons_do_not_lower_lesson_completion_anywhere(self):
        gt = GroupTeacher.objects.get(group=self.eng1)
        self._lesson(gt, dt.date(2026, 9, 29), Lesson.Status.SCHEDULED)
        mid_month = dt.date(2026, 9, 20)
        reports = build_overview(ReportFilters.from_query(SEPT, today=mid_month))
        analytics = get_dashboard(period="custom", start_date=START, end_date=END, today=mid_month)
        self.assert_same(reports, analytics)
        self.assertEqual(analytics["lessons"]["lesson_completion_rate"]["value"],
                         analytics["metrics"]["lesson_completion"])

    def test_new_group_data_recomputes_everywhere(self):
        """No stored KPI — adding real data changes every report at once."""
        before = self.all_three()
        group = Group.objects.create(name="NEW-01", course=self.course, start_date=dt.date(2026, 9, 1))
        gt = GroupTeacher.objects.create(group=group, teacher=self.aziza, subject=self.python)
        student = Student.objects.create(first_name="Nur", group=group)
        lesson = self._lesson(gt, dt.date(2026, 9, 12), Lesson.Status.COMPLETED)
        Attendance.objects.create(lesson=lesson, student=student, status=Attendance.Status.ABSENT)
        HomeworkResult.objects.create(homework=Homework.objects.create(lesson=lesson, title="HW"), student=student,
                                      status=HomeworkResult.Status.NOT_SUBMITTED)
        after = self.all_three()
        self.assert_same(*after)
        self.assertNotEqual(after[0]["kpi"]["total"], before[0]["kpi"]["total"])
