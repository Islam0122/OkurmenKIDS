"""Test Results: the historical snapshot, the results API (scope, IDOR,
filters, aggregates, export), the KPI engine's test metrics, the student
portal pages and the admin section."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.academy.models import Group, Lesson, Student
from apps.academy.services.kpi_engine import KPIEngine
from apps.academy.services.reports import ReportFilters, build_teacher_detail, build_teacher_rows
from apps.testing.models import Answer, AttemptStatus, GradingStatus, StudentAttempt
from apps.users.models import Subject, User

from .test_monitoring import MonitoringFixture


class ResultsFixture(MonitoringFixture):
    def setUp(self):
        super().setUp()
        self.test.subject = self.subject
        self.test.save(update_fields=["subject"])

    def results(self, user, **params):
        return self.get(user, "results/", **params).data


class SnapshotTests(ResultsFixture):
    def test_snapshot_is_taken_at_start_and_kept(self):
        self.mine.refresh_from_db()  # drop the cached test from before the subject was set
        result = self.attempt(self.mine, self.student, status=AttemptStatus.FINISHED, score=80.0)
        result.refresh_from_db()
        self.assertEqual((result.group_id, result.teacher_id, result.subject_id, result.test_title),
                         (self.group.pk, self.teacher.pk, self.subject.pk, "Python Basics"))
        # The student moves to another group, the test is renamed and re-subjected:
        self.student.group = self.other_group
        self.student.save()
        self.test.title = "Renamed"
        self.test.subject = Subject.objects.create(name="Other subject")
        self.test.save()
        row = next(r for r in self.results(self.lead)["results"] if r["id"] == str(result.pk))
        self.assertEqual((row["group"]["name"], row["test"]["title"], row["test"]["subject"]), ("Group 12", "Python Basics", "Python"))
        # ...and the trainer of the old group still sees the old result.
        self.assertIn(str(result.pk), {r["id"] for r in self.results(self.teacher.user)["results"]})


class ApiTests(ResultsFixture):
    def test_results_are_finished_attempts_of_lms_students_only(self):
        ids = {r["id"] for r in self.results(self.lead)["results"]}
        self.assertEqual(ids, {str(self.passed.pk), str(self.foreign.pk)})  # not active, not anonymous
        row = next(r for r in self.results(self.lead)["results"] if r["id"] == str(self.passed.pk))
        self.assertEqual((row["correct_count"], row["incorrect_count"], row["attempt_no"], row["question_total"]), (1, 1, 2, 2))

    def test_teacher_scope_and_no_idor(self):
        ids = {r["id"] for r in self.results(self.teacher.user)["results"]}
        self.assertEqual(ids, {str(self.passed.pk)})
        self.assertEqual(self.get(self.teacher.user, f"attempts/{self.foreign.pk}/").status_code, 404)
        self.assertEqual(self.get(self.teacher.user, "results/", student=self.other_student.pk).data["count"], 0)
        self.assertEqual(self.get(self.teacher.user, "results/breakdown/", by="teacher").status_code, 403)
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get("/api/v1/monitoring/results/").status_code, 401)

    def test_detail_has_every_answer(self):
        data = self.get(self.lead, f"attempts/{self.passed.pk}/").data
        self.assertEqual([q["status"] for q in data["questions"]], ["correct", "wrong"])
        self.assertEqual(data["questions"][0]["correct"], ["x"])
        self.assertIn("answered_at", data["questions"][0])

    def test_filters(self):
        def ids(**params):
            return {r["id"] for r in self.results(self.lead, **params)["results"]}
        self.assertEqual(ids(result="passed"), {str(self.passed.pk)})
        self.assertEqual(ids(result="failed"), {str(self.foreign.pk)})
        self.assertEqual(ids(score_min=50), {str(self.passed.pk)})
        self.assertEqual(ids(score_max=30), {str(self.foreign.pk)})
        self.assertEqual(ids(student=self.other_student.pk), {str(self.foreign.pk)})
        self.assertEqual(ids(q="python basics"), {str(self.passed.pk), str(self.foreign.pk)})
        self.assertEqual(len(ids(score_min="abc", score_max=500)), 2)  # malformed: ignored

    def test_summary_students_breakdown(self):
        data = self.get(self.lead, "results/summary/").data
        self.assertEqual((data["attempts"], data["students_tested"], data["passed"], data["failed"]), (2, 2, 1, 1))
        self.assertEqual((data["average_score"], data["best_score"], data["lowest_score"], data["pass_rate"]), (60, 100, 20, 50))
        self.assertEqual((data["average_correct"], data["average_questions"]), (0.5, 2))
        self.assertEqual(data["best_student"]["name"], str(self.student))
        self.assertEqual(len(data["dynamics"]), 1)
        group = self.get(self.lead, "results/summary/", group=self.group.pk).data
        self.assertEqual((group["attempts"], group["students_total"]), (1, 1))
        students = self.get(self.lead, "results/students/", group=self.group.pk).data
        self.assertEqual((students[0]["attempts"], students[0]["best_score"], students[0]["last_passed"]), (1, 100, True))
        by_group = {r["name"]: r for r in self.get(self.lead, "results/breakdown/", by="group").data}
        self.assertEqual((by_group["Group 12"]["average_score"], by_group["Group 13"]["pass_rate"]), (100, 0))
        self.assertEqual(self.get(self.lead, "results/breakdown/", by="nope").status_code, 400)

    def test_export(self):
        self.api.force_authenticate(self.lead)
        response = self.api.get("/api/v1/monitoring/results/export/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertTrue(response.content.startswith(b"PK"))


class KpiTests(ResultsFixture):
    def test_test_metrics_in_the_kpi_engine_and_dashboard(self):
        today = timezone.localdate()
        result = KPIEngine.calculate(start=today - timedelta(days=1), end=today, today=today)
        self.assertEqual((result.metrics["test_score"], result.metrics["test_pass_rate"]), (60.0, 50.0))
        total_without = KPIEngine.calculate(start=date(2000, 1, 1), end=date(2000, 1, 2), today=today)
        self.assertIsNone(total_without.metrics["test_score"])
        mine = KPIEngine.calculate(start=today, end=today, teacher_id=self.teacher.pk, today=today)
        self.assertEqual(mine.metrics["test_score"], 100.0)
        self.api.force_authenticate(self.lead)
        dashboard = self.api.get(reverse("analytics-dashboard"), {"period": "custom", "start_date": str(today), "end_date": str(today)}).json()
        self.assertEqual(dashboard["tests"]["average_score"]["value"], 60.0)
        self.assertEqual(dashboard["tests"]["students_below_passing"]["value"], 1)
        self.assertEqual(dashboard["metrics"]["test_pass_rate"], 50.0)


class FiveCriteriaKpiTests(ResultsFixture):
    """«Результаты тестов» — the 5th KPI criterion, from real attempts."""

    SEPT_START, SEPT_END, TODAY = date(2026, 9, 1), date(2026, 9, 30), date(2026, 9, 30)

    def setUp(self):
        super().setUp()
        StudentAttempt.objects.filter(pk__in=[self.passed.pk, self.foreign.pk]).update(finished_at=self.at(10))
        # The trainer's only lesson of September is held -> «Активность» 100%.
        Lesson.objects.filter(pk=self.lesson.pk).update(status=Lesson.Status.COMPLETED)

    @staticmethod
    def at(day: int, month: int = 9):
        return timezone.make_aware(datetime(2026, month, day, 12))

    def finished(self, score: float, day: int = 12, month: int = 9, **fields):
        return self.attempt(self.mine, self.student, status=AttemptStatus.FINISHED, score=score,
                            finished_at=self.at(day, month), **fields)

    def engine(self, start=SEPT_START, end=SEPT_END):
        return KPIEngine.calculate(start=start, end=end, teacher_id=self.teacher.pk, today=self.TODAY)

    def row(self, start=SEPT_START, end=SEPT_END):
        filters = ReportFilters.from_query(
            {"period": "custom", "start_date": str(start), "end_date": str(end)}, today=self.TODAY,
        )
        return next(r for r in build_teacher_rows(filters) if r["id"] == self.teacher.pk), filters

    def test_all_criteria_available_and_the_same_kpi_everywhere(self):
        row, filters = self.row()
        self.assertEqual((row["activity_rate"], row["test_score_rate"], row["test_pass_rate"]), (100.0, 100.0, 100.0))
        self.assertEqual(row["kpi"], 100.0)
        self.finished(40.0)
        row, filters = self.row()
        self.assertEqual((row["test_score_rate"], row["kpi"]), (70.0, 85.0))
        engine = self.engine()
        detail = build_teacher_detail(self.teacher, filters)
        self.assertEqual((engine.metrics["test_score"], engine.total), (70.0, 85.0))
        self.assertEqual((detail["metrics"]["test_score"], detail["kpi"]["total"]), (70.0, 85.0))

    def test_unfinished_and_unreviewed_attempts_are_not_results(self):
        self.attempt(self.mine, self.student, status=AttemptStatus.EXPIRED, score=0.0, finished_at=self.at(12))
        pending = self.finished(0.0)
        answer = Answer.objects.create(attempt=pending, question=self.q1, selected_options=[],
                                       grading_status=GradingStatus.PENDING)
        # self.active (ACTIVE), the expired one and the one waiting for review are left out.
        engine = self.engine()
        self.assertEqual((engine.counts.test_attempts, engine.metrics["test_score"]), (1, 100.0))
        self.assertEqual(self.row()[0]["test_score_rate"], 100.0)
        # Once reviewed, it is a result.
        Answer.objects.filter(pk=answer.pk).update(grading_status=GradingStatus.MANUAL)
        StudentAttempt.objects.filter(pk=pending.pk).update(score=60.0)
        engine = self.engine()
        self.assertEqual((engine.counts.test_attempts, engine.metrics["test_score"]), (2, 80.0))

    def test_retakes_are_separate_attempts_each_counted_once(self):
        self.finished(40.0)
        self.finished(70.0, day=20)
        engine = self.engine()
        # self.passed has two answers: the join must not count it twice.
        self.assertEqual((engine.counts.test_attempts, engine.counts.test_passed), (3, 2))
        self.assertEqual(engine.metrics["test_score"], 70.0)  # (100 + 40 + 70) / 3
        self.assertEqual(engine.metrics["test_pass_rate"], 66.7)
        row = self.row()[0]
        self.assertEqual((row["test_score_rate"], row["test_pass_rate"]), (70.0, 66.7))

    def test_selected_period(self):
        self.finished(30.0, day=5, month=10)
        self.assertEqual(self.engine().metrics["test_score"], 100.0)
        october = self.engine(date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(october.metrics["test_score"], 30.0)
        self.assertEqual(self.engine(date(2026, 9, 1), date(2026, 10, 31)).metrics["test_score"], 65.0)
        august = self.engine(date(2026, 8, 1), date(2026, 8, 31))
        self.assertIsNone(august.metrics["test_score"])
        self.assertIsNone(august.total)

    def test_no_tests_in_the_period_is_no_data_not_zero(self):
        StudentAttempt.objects.all().delete()
        row = self.row()[0]
        self.assertIsNone(row["test_score_rate"])
        self.assertIsNone(row["test_pass_rate"])
        self.assertEqual(row["kpi"], 100.0)  # only «Активность» has data — not (100 + 0) / 2
        self.assertIsNone(self.engine().metrics["test_score"])


class AdminTests(ResultsFixture):
    def test_results_section_and_test_stats(self):
        admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password="x", role=User.Role.ADMIN)
        client = Client()
        client.force_login(admin)
        page = client.get(reverse("admin:testing_testresult_changelist"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Подробнее")
        self.assertEqual(page.context["cl"].result_count, 2)
        filtered = client.get(reverse("admin:testing_testresult_changelist"), {"result": "failed"})
        self.assertEqual(filtered.context["cl"].result_count, 1)
        stats = client.get(reverse("admin:testing_test_stats", args=[self.test.pk]))
        self.assertContains(stats, "Посмотреть результаты")
        self.assertEqual((stats.context["students_total"], stats.context["best_score"]), (2, 100.0))


class LeaderboardSortTests(ResultsFixture):
    def test_public_leaderboard_by_average_and_tests(self):
        from apps.testing.models import SessionType, StudentAttempt, TestSession

        public = TestSession.objects.create(test=self.test, session_type=SessionType.TRAINING, is_public=True)
        public.start()
        for name, score in (("Islam", 90.0), ("islam", 70.0), ("Bek", 85.0)):
            attempt = StudentAttempt.objects.create(session=public, student_name=name, status=AttemptStatus.FINISHED, score=score)
            attempt.finished_at = attempt.started_at + timedelta(minutes=5)
            attempt.save(update_fields=["finished_at"])
        rows = self.client.get(reverse("training-leaderboard"), {"sort": "average"}).json()
        self.assertEqual([(r["student_name"].lower(), r["average_score"], r["completed_tests"]) for r in rows],
                         [("bek", 85.0, 1), ("islam", 80.0, 1)])
        best = self.client.get(reverse("training-leaderboard")).json()
        self.assertEqual(best[0]["score"], 90)
