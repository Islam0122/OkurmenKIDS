"""Session analytics: numbers counted from attempts/answers (nothing stored),
the pass threshold taken from the test, filters, exports, the admin pages
(session tabs, attempt, group / subject / test / tree) and query counts."""
from __future__ import annotations

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.academy.models import GroupTeacher, Student
from apps.testing.models import QuestionType, Test, TestSession
from apps.testing.services import analytics, attempts
from apps.testing.services import questions as svc
from apps.testing.services.question_rules import QuestionData
from apps.testing.tests.test_sessions import SessionFixture
from apps.users.models import User


class AnalyticsFixture(SessionFixture):
    def setUp(self):
        super().setUp()
        self.test.subject = self.subject
        self.test.save()
        self.student3 = Student.objects.create(first_name="Bek", last_name="Not Started", group=self.group)
        self.session = self.create_session(date="", start_time="", end_time="", title="Final")
        self.session.start()

    def answer(self, attempt, right: int):
        """Answer the first `right` questions correctly, the rest wrongly."""
        answers = {}
        for i, q in enumerate(attempts.attempt_questions(attempt)):
            option = q.options.get(is_correct=i < right)
            answers[str(q.pk)] = attempts.SubmittedAnswer(options=[str(option.pk)])
        return attempts.submit(attempt, answers)

    def take(self, student, right: int, session=None):
        attempt = attempts.join(session or self.session, student=student)
        self.answer(attempt, right)
        attempt.refresh_from_db()
        return attempt

    def take_both(self):
        self.best = self.take(self.student, right=3)     # 100%
        self.weak = self.take(self.student2, right=1)    # 33.33%


class SessionAnalyticsTests(AnalyticsFixture):
    def test_kpis_pass_rate_and_distribution(self):
        self.take_both()
        a = analytics.session_analytics(self.session)
        self.assertEqual((a.total_students, a.finished, a.passed, a.failed, a.not_finished), (3, 2, 1, 1, 1))
        self.assertEqual(a.best, 100)
        self.assertAlmostEqual(a.worst, 33.33, places=1)
        self.assertAlmostEqual(a.average, 66.7, places=1)
        self.assertEqual(a.pass_rate, 33.3)
        counts = {c["label"]: c["count"] for c in a.distribution}
        self.assertEqual((counts["<50"], counts["90–100"], counts["60–69"]), (1, 1, 0))

        rows = {r.student_id: r for r in a.rows}
        self.assertEqual((rows[self.student2.pk].correct, rows[self.student2.pk].wrong), (1, 2))
        self.assertEqual(rows[self.student3.pk].status, "not_started")
        self.assertEqual([r.number for r in a.rows], [1, 2, 3])

        by_number = {s.number: s for s in a.questions}
        self.assertEqual((by_number[1].answered, by_number[1].correct, by_number[1].wrong), (2, 2, 0))
        self.assertEqual(sum(s.correct for s in a.questions), 4)
        self.assertEqual(a.grading.auto, 6)

    def test_threshold_comes_from_the_test(self):
        self.take_both()
        Test.objects.filter(pk=self.test.pk).update(passing_score=30)
        self.session.refresh_from_db()
        a = analytics.session_analytics(self.session)
        self.assertEqual((a.passed, a.failed), (2, 0))

    def test_text_answers_under_review_are_neither_passed_nor_failed(self):
        svc.save_question(self.test, QuestionData(QuestionType.CODE, "Write fizzbuzz", language="python"))
        attempt = attempts.join(self.session, student=self.student)
        answers = {}
        for q in attempts.attempt_questions(attempt):
            if q.question_type == QuestionType.CODE:
                answers[str(q.pk)] = attempts.SubmittedAnswer(text="print(1)")
            else:
                answers[str(q.pk)] = attempts.SubmittedAnswer(options=[str(q.options.get(is_correct=True).pk)])
        attempts.submit(attempt, answers)
        a = analytics.session_analytics(self.session)
        row = next(r for r in a.rows if r.student_id == self.student.pk)
        self.assertIsNone(row.passed)
        self.assertEqual((row.pending, a.under_review, a.grading.pending), (1, 1, 1))

    def test_filters(self):
        self.take_both()
        rows = analytics.session_analytics(self.session).rows
        names = lambda **f: [r.student_id for r in analytics.filter_rows(rows, **f)]  # noqa: E731
        self.assertEqual(names(result="passed"), [self.student.pk])
        self.assertEqual(names(result="failed"), [self.student2.pk])
        self.assertEqual(names(result="90-100"), [self.student.pk])
        self.assertEqual(names(result="lt60"), [self.student2.pk])
        self.assertEqual(names(status="not_started"), [self.student3.pk])
        self.assertEqual(names(query="islam"), [self.student2.pk])

    def test_latest_attempt_per_student(self):
        self.session.max_attempts_per_student = 2
        self.session.save()
        self.take(self.student, right=1)
        self.take(self.student, right=3)
        row = next(r for r in analytics.session_analytics(self.session).rows if r.student_id == self.student.pk)
        self.assertEqual((row.percent, row.attempts_count), (100, 2))

    def test_list_stats_are_annotations(self):
        self.take_both()
        session = analytics.with_list_stats(TestSession.objects.filter(pk=self.session.pk)).get()
        self.assertEqual(
            (session.roster_total, session.attempts_total, session.finished_total, session.passed_total),
            (3, 2, 2, 1),
        )
        self.assertAlmostEqual(session.average_score, 66.67, places=1)

    def test_query_count_does_not_grow_with_students(self):
        self.take_both()

        def count():
            with CaptureQueriesContext(connection) as ctx:
                analytics.session_analytics(self.session)
            return len(ctx.captured_queries)

        before = count()
        for i in range(6):
            student = Student.objects.create(first_name=f"S{i}", last_name="X", group=self.group)
            self.session.participants.create(student=student)
            self.take(student, right=i % 4)
        self.assertEqual(count(), before)

    def test_tree_and_summaries(self):
        self.take_both()
        other = self.create_session(date="", start_time="", end_time="", title="Other group", group=str(self.other_group.pk))
        other.start()
        self.take(self.outsider, right=3, session=other)
        tree = analytics.analytics_tree(TestSession.objects.all())
        self.assertEqual([g.label for g in tree], ["Group 12", "Group 13"])
        test_node = tree[0].children[0].children[0]
        self.assertEqual((tree[0].children[0].label, test_node.label), ("Python", "Python Basics"))
        self.assertEqual((test_node.summary.attempts, test_node.summary.passed), (2, 1))
        self.assertEqual([s.title for s in test_node.sessions], ["Final"])
        total = analytics.summarize_attempts(analytics.finished_attempts_of(TestSession.objects.all()))
        self.assertEqual((total.attempts, total.passed), (3, 2))


class AnalyticsAdminTests(AnalyticsFixture):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password="x")
        self.client.force_login(self.admin)
        self.take_both()

    def get(self, name, *args, **params):
        response = self.client.get(reverse(f"admin:{name}", args=args), params)
        self.assertEqual(response.status_code, 200, name)
        return response

    def test_session_analytics_page(self):
        response = self.get("testing_session_analytics", self.session.pk)
        for text in ("Всего студентов", "Процент прохождения", "Распределение баллов", "Вопросы с низкой успешностью",
                     "Вопросы с высокой успешностью", "Аналитика группы", "Проверка ответов", "Aibek"):
            self.assertContains(response, text)
        self.assertContains(response, reverse("admin:testing_attempt_detail", args=[self.weak.pk]))
        filtered = self.get("testing_session_analytics", self.session.pk, result="passed")
        self.assertEqual([r.student_id for r in filtered.context["rows"]], [self.student.pk])
        self.assertContains(self.get("testing_session_questions", self.session.pk), "% правильных")

    def test_exports(self):
        csv = self.get("testing_session_export", self.session.pk, "csv").content.decode("utf-8-sig")
        header, *lines = csv.strip().splitlines()
        self.assertEqual(header.split(","), analytics.EXPORT_HEADERS)
        self.assertEqual(len(lines), 3)
        self.assertIn("Group 12,Python,Python Basics,Final,", lines[0])
        only_failed = self.get("testing_session_export", self.session.pk, "csv", result="failed").content.decode("utf-8-sig")
        self.assertEqual(len(only_failed.strip().splitlines()), 2)
        self.assertTrue(self.get("testing_session_export", self.session.pk, "pdf").content.startswith(b"%PDF"))
        self.assertTrue(self.get("testing_session_export", self.session.pk, "xlsx").content.startswith(b"PK"))
        self.assertEqual(self.client.get(reverse("admin:testing_session_export", args=[self.session.pk, "exe"])).status_code, 404)

    def test_attempt_detail(self):
        response = self.get("testing_attempt_detail", self.weak.pk)
        for text in ("Ответ студента", "Правильный", "Неверно", "Верно", "Group 12", "Python Basics", "1 / 3"):
            self.assertContains(response, text)

    def test_section_pages(self):
        self.assertContains(self.get("testing_analytics"), "Group 12")
        self.assertContains(self.get("testing_analytics_group", self.group.pk), "Python Basics")
        self.assertContains(self.get("testing_analytics_subject", self.subject.pk, group=self.group.pk), "Final")
        self.assertContains(self.get("testing_analytics_test", self.test.pk), "Сравнение сессий")
        listing = self.get("testing_testsession_changelist")
        self.assertContains(listing, reverse("admin:testing_session_analytics", args=[self.session.pk]))
        self.assertContains(listing, "67%")

    def test_list_query_count_is_constant(self):
        url = reverse("admin:testing_testsession_changelist")
        self.client.get(url)
        with CaptureQueriesContext(connection) as before:
            self.client.get(url)
        for i in range(5):
            TestSession.objects.create(test=self.test, group=self.group, title=f"Extra {i}")
        with CaptureQueriesContext(connection) as after:
            self.client.get(url)
        self.assertEqual(len(after.captured_queries), len(before.captured_queries))

    def test_teacher_staff_has_no_access(self):
        user = self.teacher.user
        user.is_staff = True
        user.save()
        self.client.force_login(user)
        for url in (reverse("admin:testing_analytics"), reverse("admin:testing_session_analytics", args=[self.session.pk])):
            self.assertIn(self.client.get(url).status_code, (302, 403))


class VisibilityTests(AnalyticsFixture):
    def test_teacher_sees_only_their_groups(self):
        other = TestSession.objects.create(test=self.test, group=self.other_group, title="Other")
        self.assertEqual(set(analytics.visible_sessions(self.teacher.user)), set())
        GroupTeacher.objects.create(group=self.group, teacher=self.teacher, subject=self.subject)
        self.assertEqual(set(analytics.visible_sessions(self.teacher.user)), {self.session})
        admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password="x")
        self.assertEqual(set(analytics.visible_sessions(admin)), {self.session, other})
