"""End to end: a published test, a running session, a student taking it
through the /exam/ pages, backend checking and scoring, the result."""
from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.urls import reverse
from django.utils import timezone

from apps.testing.models import (
    Answer,
    AttemptStatus,
    GradingStatus,
    QuestionType,
    SessionType,
    StudentAttempt,
    TestSession,
    TestStatus,
)
from apps.testing.services import attempts
from apps.testing.services import questions as svc
from apps.testing.services.question_rules import CodeTestData, OptionData, QuestionData
from apps.testing.tests.base import TestingFixture


class StudentFlowFixture(TestingFixture):
    def setUp(self):
        super().setUp()
        self.test.status = TestStatus.ACTIVE
        self.test.passing_score = 50
        self.test.save()
        self.q_single = svc.save_question(self.test, QuestionData(QuestionType.SINGLE_CHOICE, "Backend?", options=[
            OptionData("Python", True), OptionData("HTML", False), OptionData("CSS", False)]), points=2)
        self.q_multi = svc.save_question(self.test, QuestionData(QuestionType.MULTIPLE_CHOICE, "Immutable?", options=[
            OptionData("tuple", True), OptionData("str", True), OptionData("list", False)]))
        self.q_text = svc.save_question(self.test, QuestionData(
            QuestionType.TEXT, "Что такое Python?", correct_answers=["Язык программирования"]))
        self.q_code = svc.save_question(self.test, QuestionData(
            QuestionType.CODE, "Sum", language="python", code_tests=[CodeTestData("2 3", "5")]),
            starter_code="def add(a, b):\n    pass", is_required=False)
        self.session = TestSession.objects.create(test=self.test, session_type=SessionType.TRAINING)
        self.session.start()

    def join(self, name="Aibek Asanov", key=None):
        return self.client.post(reverse("testing_public_join"), {"key": key or self.session.key, "student_name": name, "start": "1"})

    def correct_post(self, **overrides):
        single_right = self.q_single.options.get(is_correct=True)
        multi_right = self.q_multi.options.filter(is_correct=True)
        data = {
            f"answer_{self.q_single.pk}": str(single_right.pk),
            f"answer_{self.q_multi.pk}": [str(o.pk) for o in multi_right],
            f"answer_{self.q_text.pk}": "  язык программирования ",
            f"answer_{self.q_code.pk}": "def add(a, b):\n    return a + b",
        }
        data.update(overrides)
        return data


class StudentFlowTests(StudentFlowFixture):
    def test_full_flow_scores_by_points_and_keeps_code_for_review(self):
        response = self.join()
        attempt = StudentAttempt.objects.get()
        self.assertRedirects(response, reverse("testing_public_take", args=[attempt.pk]))
        self.assertEqual(len(attempt.question_ids), 4)

        page = self.client.get(reverse("testing_public_take", args=[attempt.pk]))
        self.assertContains(page, "Вопрос 1 из 4")
        self.assertContains(page, "def add(a, b):")  # starter code in the editor
        self.assertContains(page, "data-code-editor")

        response = self.client.post(reverse("testing_public_take", args=[attempt.pk]), self.correct_post())
        self.assertRedirects(response, reverse("testing_public_result", args=[attempt.pk]))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.FINISHED)
        # 2 + 1 + 1 of 5 points (code waits for a teacher) → 80%.
        self.assertEqual(attempt.score, 80.0)
        code_answer = Answer.objects.get(question=self.q_code)
        self.assertEqual(code_answer.grading_status, GradingStatus.PENDING)
        self.assertIn("return a + b", code_answer.answer_text)

        result = self.client.get(reverse("testing_public_result", args=[attempt.pk]))
        self.assertContains(result, "80%")
        self.assertContains(result, "Часть ответов на проверке")

    def test_wrong_answers_and_pass_mark(self):
        self.join()
        attempt = StudentAttempt.objects.get()
        wrong = self.q_single.options.filter(is_correct=False).first()
        self.client.post(reverse("testing_public_take", args=[attempt.pk]), self.correct_post(**{
            f"answer_{self.q_single.pk}": str(wrong.pk),
            f"answer_{self.q_code.pk}": "",
        }))
        attempt.refresh_from_db()
        self.assertEqual(attempt.score, 40.0)  # 2 of 5
        self.assertFalse(attempts.is_passed(attempt))
        result = self.client.get(reverse("testing_public_result", args=[attempt.pk]))
        self.assertContains(result, "Тест не сдан")

    def test_required_questions_block_finishing_but_not_a_timeout(self):
        self.join()
        attempt = StudentAttempt.objects.get()
        url = reverse("testing_public_take", args=[attempt.pk])
        response = self.client.post(url, {f"answer_{self.q_single.pk}": ""})
        self.assertContains(response, "Ответьте на обязательные вопросы: 1, 2, 3")
        self.assertEqual(StudentAttempt.objects.get().status, AttemptStatus.ACTIVE)
        response = self.client.post(url, {"timed_out": "1"})
        self.assertRedirects(response, reverse("testing_public_result", args=[attempt.pk]))
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.score), (AttemptStatus.FINISHED, 0.0))

    def test_show_correct_answers_setting(self):
        self.join()
        attempt = StudentAttempt.objects.get()
        wrong = self.q_single.options.get(text="HTML")
        self.client.post(reverse("testing_public_take", args=[attempt.pk]),
                         self.correct_post(**{f"answer_{self.q_single.pk}": str(wrong.pk)}))
        url = reverse("testing_public_result", args=[attempt.pk])
        self.assertNotContains(self.client.get(url), "Правильно:")
        self.test.show_correct_answers = True
        self.test.save()
        self.assertContains(self.client.get(url), 'Правильно:</span> <span class="ex-inline-option">Python</span>')
        self.test.show_result = False
        self.test.save()
        page = self.client.get(url)
        self.assertContains(page, "Результат сообщит преподаватель")
        self.assertNotContains(page, "80%")

    def test_attempt_page_only_opens_in_the_students_browser(self):
        self.join()
        attempt = StudentAttempt.objects.get()
        self.client.logout()
        self.client.cookies.clear()
        self.assertEqual(self.client.get(reverse("testing_public_take", args=[attempt.pk])).status_code, 404)

    def test_rejoining_continues_the_unfinished_attempt(self):
        self.join()
        self.join()
        self.assertEqual(StudentAttempt.objects.count(), 1)


class JoinRulesTests(StudentFlowFixture):
    def test_unknown_key_and_not_running_session(self):
        response = self.client.get(reverse("testing_public_join"), {"key": "ZZ-NOPE1"})
        self.assertContains(response, "не найдена")
        created = TestSession.objects.create(test=self.test, session_type=SessionType.TRAINING)
        self.assertContains(self.join(key=created.key), "ещё не запущена")
        self.session.pause()
        self.assertContains(self.join(), "на паузе")

    def test_draft_archived_and_dated_tests_are_closed(self):
        self.test.status = TestStatus.DRAFT
        self.test.save()
        self.assertContains(self.join(), "Тест не опубликован")
        self.test.status = TestStatus.ACTIVE
        self.test.available_from = timezone.now() + timedelta(days=1)
        self.test.save()
        self.assertContains(self.join(), "ещё не начался")
        self.test.available_from, self.test.available_until = None, timezone.now() - timedelta(minutes=1)
        self.test.save()
        self.assertContains(self.join(), "истёк")

    def test_attempt_limits(self):
        self.test.allow_retry = False
        self.test.save()
        self.join()
        attempt = StudentAttempt.objects.get()
        self.client.post(reverse("testing_public_take", args=[attempt.pk]), self.correct_post())
        self.assertContains(self.join(), "все попытки")
        self.test.allow_retry, self.test.max_attempts = True, 2
        self.test.save()
        self.assertEqual(self.join().status_code, 302)

    def test_group_session_links_the_lms_student(self):
        session = TestSession.objects.create(test=self.test, group=self.group, session_type=SessionType.TRAINING)
        session.start()
        page = self.client.get(reverse("testing_public_join"), {"key": session.key})
        self.assertContains(page, str(self.student))
        response = self.client.post(reverse("testing_public_join"), {"key": session.key, "student": self.student.pk, "start": "1"})
        attempt = StudentAttempt.objects.get()
        self.assertRedirects(response, reverse("testing_public_take", args=[attempt.pk]))
        self.assertEqual((attempt.student, attempt.student_name), (self.student, str(self.student)))

    def test_too_many_wrong_keys_are_throttled(self):
        with mock.patch("apps.testing.public_views._too_many_failed_keys", return_value=True):
            response = self.client.get(reverse("testing_public_join"), {"key": self.session.key})
        self.assertEqual(response.status_code, 429)


class TimingAndSelectionTests(StudentFlowFixture):
    def test_time_limit_expires_the_attempt(self):
        self.test.time_limit_minutes = 10
        self.test.save()
        self.join()
        attempt = StudentAttempt.objects.get()
        later = timezone.now() + timedelta(minutes=10) + attempts.SUBMIT_GRACE + timedelta(seconds=5)
        with mock.patch("django.utils.timezone.now", return_value=later):
            response = self.client.post(reverse("testing_public_take", args=[attempt.pk]), self.correct_post())
        self.assertRedirects(response, reverse("testing_public_result", args=[attempt.pk]))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.EXPIRED)

    def test_submit_within_grace_after_deadline_is_accepted(self):
        self.test.time_limit_minutes = 10
        self.test.save()
        self.join()
        attempt = StudentAttempt.objects.get()
        later = timezone.now() + timedelta(minutes=10, seconds=30)
        with mock.patch("django.utils.timezone.now", return_value=later):
            self.client.post(reverse("testing_public_take", args=[attempt.pk]), {**self.correct_post(), "timed_out": "1"})
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.FINISHED)

    def test_questions_per_attempt_and_shuffle_are_stable_per_attempt(self):
        self.test.questions_per_attempt = 2
        self.test.shuffle_questions = True
        self.test.shuffle_options = True
        self.test.save()
        attempt = attempts.join(self.session, student_name="A")
        self.assertEqual(len(attempt.question_ids), 2)
        first = [(q.pk, [o.pk for o in q.display_options]) for q in attempts.attempt_questions(attempt)]
        second = [(q.pk, [o.pk for o in q.display_options]) for q in attempts.attempt_questions(attempt)]
        self.assertEqual(first, second)

    def test_new_attempts_store_their_question_list(self):
        """New attempts score by points over this list; legacy attempts
        (empty list) keep the legacy formula — see test_models."""
        attempt = attempts.join(self.session, student_name="B")
        self.assertTrue(attempt.question_ids)
