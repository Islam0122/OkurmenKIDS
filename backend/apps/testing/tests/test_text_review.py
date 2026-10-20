"""Manual review of text answers in the admin («Проверка текстовых ответов»):
text answers wait for review, the reviewer's points are capped at the
question's points, the attempt is re-scored and choice answers stay as
graded automatically."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.testing.models import (
    Answer,
    AttemptStatus,
    GradingStatus,
    QuestionType,
    SessionParticipant,
    SessionType,
    StudentAttempt,
    TestSession,
    TestStatus,
)
from apps.testing.services import questions as svc
from apps.testing.services.attempts import SubmittedAnswer, grade_and_finish
from apps.testing.services.question_rules import OptionData, QuestionData
from apps.testing.services.review import reset_review, review_answer
from apps.testing.tests.base import TestingFixture
from apps.users.models import User


class TextReviewFixture(TestingFixture):
    def setUp(self):
        super().setUp()
        self.test.status = TestStatus.ACTIVE
        self.test.save()
        self.q_single = svc.save_question(self.test, QuestionData(QuestionType.SINGLE_CHOICE, "Backend?", options=[
            OptionData("Python", True), OptionData("HTML", False)]), points=2)
        self.q_multi = svc.save_question(self.test, QuestionData(QuestionType.MULTIPLE_CHOICE, "Immutable?", options=[
            OptionData("tuple", True), OptionData("list", False)]), points=2)
        self.q_text = svc.save_question(self.test, QuestionData(
            QuestionType.TEXT, "Что такое Python?", correct_answers=["Язык программирования"]), points=6)
        self.session = TestSession.objects.create(test=self.test, group=self.group, session_type=SessionType.EXAM)
        self.session.start()
        self.attempt = StudentAttempt.objects.create(
            session=self.session, student=self.student,
            question_ids=[str(q.pk) for q in (self.q_single, self.q_multi, self.q_text)],
        )
        SessionParticipant.objects.create(session=self.session, student=self.student, attempt=self.attempt)
        right = str(self.q_single.options.get(is_correct=True).pk)
        wrong = str(self.q_multi.options.get(is_correct=False).pk)
        grade_and_finish(self.attempt, {
            str(self.q_single.pk): SubmittedAnswer(options=[right]),
            str(self.q_multi.pk): SubmittedAnswer(options=[wrong]),
            str(self.q_text.pk): SubmittedAnswer(text="Язык программирования для бэкенда"),
        })
        self.attempt.refresh_from_db()
        self.text_answer = Answer.objects.get(question=self.q_text)


class ReviewServiceTests(TextReviewFixture):
    def test_text_answer_waits_for_review_and_choices_stay_auto(self):
        self.assertEqual((self.text_answer.grading_status, self.text_answer.is_correct), (GradingStatus.PENDING, None))
        self.assertEqual(self.attempt.status, AttemptStatus.FINISHED)
        self.assertEqual(self.attempt.score, 20.0)  # 2 of 10
        self.assertTrue(self.attempt.needs_review)

    def test_review_rescores_the_attempt_and_participant(self):
        reviewer = User.objects.create_superuser(username="root", email="root@okurmen.kg", password="x")
        review_answer(self.text_answer, 4.5, "Почти", reviewer)
        self.text_answer.refresh_from_db()
        self.attempt.refresh_from_db()
        self.assertEqual(self.text_answer.grading_status, GradingStatus.MANUAL)
        self.assertEqual((self.text_answer.points_awarded, self.text_answer.is_correct), (4.5, True))
        self.assertEqual((self.text_answer.review_comment, self.text_answer.reviewed_by), ("Почти", reviewer))
        self.assertIsNotNone(self.text_answer.reviewed_at)
        self.assertEqual(self.attempt.score, 65.0)  # (2 + 4.5) of 10
        self.assertFalse(self.attempt.needs_review)
        self.assertEqual(SessionParticipant.objects.get(attempt=self.attempt).score, 65.0)
        # The choice answers keep their automatic result.
        auto = Answer.objects.exclude(pk=self.text_answer.pk).order_by("question__order")
        self.assertEqual([(a.grading_status, a.is_correct) for a in auto],
                         [(GradingStatus.AUTO, True), (GradingStatus.AUTO, False)])

    def test_points_above_max_or_below_zero_are_rejected(self):
        for points in (7, -1, None):
            with self.assertRaises(ValidationError):
                review_answer(self.text_answer, points)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.score, 20.0)

    def test_reset_sends_the_answer_back(self):
        review_answer(self.text_answer, 6)
        reset_review(self.text_answer)
        self.text_answer.refresh_from_db()
        self.attempt.refresh_from_db()
        self.assertEqual((self.text_answer.grading_status, self.text_answer.points_awarded), (GradingStatus.PENDING, None))
        self.assertEqual(self.attempt.score, 20.0)

    def test_public_training_keeps_checking_text_automatically(self):
        session = TestSession.objects.create(test=self.test, session_type=SessionType.TRAINING, is_public=True)
        session.start()
        attempt = StudentAttempt.objects.create(session=session, student_name="Guest", question_ids=[str(self.q_text.pk)])
        grade_and_finish(attempt, {str(self.q_text.pk): SubmittedAnswer(text="язык программирования")})
        answer = attempt.answers.get()
        self.assertEqual((answer.grading_status, answer.is_correct), (GradingStatus.AUTO, True))


class ReviewAdminTests(TextReviewFixture):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password="x")
        self.client.force_login(self.admin)
        self.list_url = reverse("admin:testing_textanswerreview_changelist")
        self.change_url = reverse("admin:testing_textanswerreview_change", args=[self.text_answer.pk])

    def test_list_shows_only_text_answers_with_filters(self):
        page = self.client.get(self.list_url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Язык программирования для бэкенда")
        self.assertContains(page, "Ожидает проверки")
        self.assertEqual(list(page.context["cl"].queryset), [self.text_answer])
        self.assertEqual(len(self.client.get(self.list_url, {"review": "reviewed"}).context["cl"].queryset), 0)
        self.assertEqual(len(self.client.get(self.list_url, {"review": "pending_review"}).context["cl"].queryset), 1)
        self.assertEqual(len(self.client.get(self.list_url, {"q": "Asanov"}).context["cl"].queryset), 1)
        self.assertEqual(len(self.client.get(self.list_url, {"q": "Nobody"}).context["cl"].queryset), 0)

    def test_change_page_saves_the_review(self):
        page = self.client.get(self.change_url)
        self.assertContains(page, "Что такое Python?")
        self.assertContains(page, "совпадает с эталоном")
        response = self.client.post(self.change_url, {"points_awarded": "6", "review_comment": "Отлично"})
        self.assertEqual(response.status_code, 302)
        self.text_answer.refresh_from_db()
        self.attempt.refresh_from_db()
        self.assertEqual((self.text_answer.points_awarded, self.text_answer.reviewed_by), (6.0, self.admin))
        self.assertEqual(self.attempt.score, 80.0)

    def test_change_page_rejects_points_above_max(self):
        response = self.client.post(self.change_url, {"points_awarded": "10", "review_comment": ""})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Балл должен быть от 0 до 6.")
        self.text_answer.refresh_from_db()
        self.assertEqual(self.text_answer.grading_status, GradingStatus.PENDING)

    def test_bulk_max_points_action(self):
        self.client.post(self.list_url, {"action": "give_max_points", "_selected_action": [str(self.text_answer.pk)]})
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.score, 80.0)

    def test_teacher_has_no_access(self):
        from apps.testing.tests.base import make_teacher

        self.client.force_login(make_teacher("tother").user)
        self.assertNotEqual(self.client.get(self.list_url).status_code, 200)
