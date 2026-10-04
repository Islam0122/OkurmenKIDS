"""Public training portal API: content, tests, attempts by name, answers,
feedback, deadline, results, leaderboard, and what it must never expose.

Absolute imports only (see apps/academy/tests.py)."""
from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.testing.models import (
    Answer,
    AttemptStatus,
    FinishReason,
    QuestionType,
    SessionType,
    StudentAttempt,
    Test,
    TestSession,
    TestStatus,
)
from apps.testing.services import questions as svc
from apps.testing.services.question_rules import CodeTestData, OptionData, QuestionData
from apps.training.models import PortalSettings, TrainingLink, TrainingVideo
from apps.users.models import Subject


class TrainingFixture(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.subject = Subject.objects.get_or_create(name="Python")[0]
        self.test = Test.objects.create(
            title="Python Training", subject=self.subject, status=TestStatus.ACTIVE,
            time_limit_minutes=30, show_correct_answers=True, passing_score=50,
        )
        self.q1 = svc.save_question(self.test, QuestionData(QuestionType.SINGLE_CHOICE, "Backend?", options=[
            OptionData("Python", True), OptionData("HTML", False)]), points=2, explanation="Python — backend тил.")
        self.q2 = svc.save_question(self.test, QuestionData(QuestionType.MULTIPLE_CHOICE, "Immutable?", options=[
            OptionData("tuple", True), OptionData("str", True), OptionData("list", False)]))
        self.q3 = svc.save_question(self.test, QuestionData(
            QuestionType.TEXT, "list.append?", correct_answers=["append"]))
        self.q4 = svc.save_question(self.test, QuestionData(
            QuestionType.CODE, "add(a, b)", language="python", code_tests=[CodeTestData("2 3", "5")]), is_required=False)
        self.session = TestSession.objects.create(test=self.test, session_type=SessionType.TRAINING, is_public=True)
        self.session.start()

    def start(self, name="Islam", session=None):
        response = self.api.post(reverse("training-attempt-start"), {
            "test_id": str((session or self.session).pk), "student_name": name,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def auth(self, attempt):
        return {"HTTP_X_ATTEMPT_TOKEN": attempt["token"]}

    def put(self, attempt, question, body, token=True):
        return self.api.put(
            reverse("training-answer", args=[attempt["attempt_id"], question.pk]), body, format="json",
            **(self.auth(attempt) if token else {}),
        )

    def right_option(self, question):
        return str(question.options.get(is_correct=True).pk)


class ContentTests(TrainingFixture):
    def test_portal_settings_and_published_content_only(self):
        settings = PortalSettings.load()
        settings.exam_url = "https://lms.example.com/student/exams/"
        settings.save()
        TrainingVideo.objects.create(title="Shown", video_url="https://youtu.be/abcdefghijk", published=True, order=2)
        TrainingVideo.objects.create(title="Draft", video_url="https://youtu.be/abcdefghijk", published=False)
        TrainingLink.objects.create(title="Docs", url="https://docs.python.org/3/", published=True, icon="filetype-py")
        TrainingLink.objects.create(title="Hidden", url="https://example.com/", published=False)

        portal = self.api.get(reverse("training-portal")).json()
        self.assertEqual(portal["exam_url"], "https://lms.example.com/student/exams/")
        self.assertEqual(portal["hero_title"], "Экзаменге даярдан")
        self.assertEqual([v["title"] for v in self.api.get(reverse("training-videos")).json()], ["Shown"])
        self.assertEqual([l["title"] for l in self.api.get(reverse("training-links")).json()], ["Docs"])

    def test_only_running_public_training_sessions_of_active_tests(self):
        TestSession.objects.create(test=self.test, session_type=SessionType.TRAINING)            # not public
        exam = TestSession.objects.create(test=self.test, session_type=SessionType.EXAM, is_public=True, duration=timedelta(hours=1))
        exam.start()                                                                              # not training
        TestSession.objects.create(test=self.test, session_type=SessionType.TRAINING, is_public=True)  # not running
        draft = Test.objects.create(title="Draft test", status=TestStatus.DRAFT)
        hidden = TestSession.objects.create(test=draft, session_type=SessionType.TRAINING, is_public=True)
        hidden.start()

        tests = self.api.get(reverse("training-test-list")).json()
        self.assertEqual([t["id"] for t in tests], [str(self.session.pk)])
        self.assertEqual(tests[0]["questions_count"], 4)
        self.assertEqual(tests[0]["duration"], 30)
        self.assertEqual(tests[0]["subject"], "Python")
        self.assertEqual(self.api.get(reverse("training-test-detail", args=[hidden.pk])).status_code, 404)

    def test_no_login_needed_and_admin_api_stays_closed(self):
        self.assertEqual(self.api.get(reverse("training-test-list")).status_code, 200)
        self.assertEqual(self.api.get(reverse("testing-test-list")).status_code, 401)


class AttemptTests(TrainingFixture):
    def test_start_returns_token_and_deadline_and_no_correct_answers(self):
        attempt = self.start("  Ислам   Дуйшобаев ")
        self.assertEqual(attempt["student_name"], "Ислам Дуйшобаев")
        self.assertTrue(attempt["token"])
        self.assertIsNotNone(attempt["expires_at"])
        db = StudentAttempt.objects.get(pk=attempt["attempt_id"])
        self.assertIsNone(db.student_id)
        self.assertIsNone(db.user_id)

        state = self.api.get(reverse("training-attempt", args=[attempt["attempt_id"]]), **self.auth(attempt)).json()
        self.assertEqual(len(state["questions"]), 4)
        body = str(state)
        self.assertNotIn("is_correct", body)
        self.assertNotIn("correct_answers", body.replace("'feedback': None", ""))
        self.assertNotIn("append", body.replace("list.append?", ""))

    def test_name_validation(self):
        for name, code in (("", "name_required"), ("A", "name_too_short"), ("A" * 51, "name_too_long"), ("<script>", "name_invalid")):
            with self.subTest(name=name):
                response = self.api.post(reverse("training-attempt-start"), {"test_id": str(self.session.pk), "student_name": name}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()["code"], code)
        self.assertEqual(self.api.post(reverse("training-attempt-start"), {"test_id": "nope", "student_name": "Islam"}, format="json").status_code, 400)

    def test_same_name_gets_separate_attempts(self):
        self.assertNotEqual(self.start("Islam")["attempt_id"], self.start("Islam")["attempt_id"])

    def test_token_is_required_and_bound_to_the_attempt(self):
        mine, other = self.start("Islam"), self.start("Aibek")
        url = reverse("training-attempt", args=[mine["attempt_id"]])
        self.assertEqual(self.api.get(url).status_code, 403)
        self.assertEqual(self.api.get(url, HTTP_X_ATTEMPT_TOKEN=other["token"]).status_code, 403)
        self.assertEqual(self.api.get(url, HTTP_X_ATTEMPT_TOKEN="forged").status_code, 403)
        self.assertEqual(self.put(mine, self.q1, {"options": [self.right_option(self.q1)]}, token=False).status_code, 403)

    def test_answer_validation(self):
        attempt = self.start()
        foreign = Test.objects.create(title="Other")
        foreign_q = svc.save_question(foreign, QuestionData(QuestionType.SINGLE_CHOICE, "x?", options=[OptionData("a", True), OptionData("b", False)]))
        self.assertEqual(self.put(attempt, self.q1, {"options": [str(self.q2.options.first().pk)]}).status_code, 400)
        self.assertEqual(self.put(attempt, self.q1, {"options": [str(o.pk) for o in self.q1.options.all()]}).status_code, 400)
        self.assertEqual(self.put(attempt, self.q3, {"text": "x" * 6000}).status_code, 400)
        response = self.api.put(reverse("training-answer", args=[attempt["attempt_id"], foreign_q.pk]),
                                {"options": [str(foreign_q.options.first().pk)]}, format="json", **self.auth(attempt))
        self.assertEqual(response.status_code, 400)

    def test_check_locks_the_answer_and_returns_feedback(self):
        attempt = self.start()
        self.assertEqual(self.put(attempt, self.q1, {"options": [str(self.q1.options.get(is_correct=False).pk)]}).status_code, 200)
        check = self.api.post(reverse("training-answer-check", args=[attempt["attempt_id"], self.q1.pk]), **self.auth(attempt)).json()
        self.assertEqual(check["status"], "incorrect")
        self.assertEqual(check["correct_option_ids"], [self.right_option(self.q1)])
        self.assertEqual(check["explanation"], "Python — backend тил.")
        locked = self.put(attempt, self.q1, {"options": [self.right_option(self.q1)]})
        self.assertEqual(locked.status_code, 409)
        self.assertEqual(locked.json()["code"], "locked")

        state = self.api.get(reverse("training-attempt", args=[attempt["attempt_id"]]), **self.auth(attempt)).json()
        q1 = next(q for q in state["questions"] if q["id"] == str(self.q1.pk))
        self.assertTrue(q1["checked"])
        self.assertEqual(q1["feedback"]["status"], "incorrect")

    def test_check_disabled_when_the_test_hides_correct_answers(self):
        self.test.show_correct_answers = False
        self.test.save()
        attempt = self.start()
        self.put(attempt, self.q1, {"options": [self.right_option(self.q1)]})
        response = self.api.post(reverse("training-answer-check", args=[attempt["attempt_id"], self.q1.pk]), **self.auth(attempt))
        self.assertEqual(response.status_code, 403)

    def test_submit_is_graded_by_the_backend_and_final(self):
        attempt = self.start()
        self.put(attempt, self.q1, {"options": [self.right_option(self.q1)]})
        self.put(attempt, self.q2, {"options": [str(o.pk) for o in self.q2.options.filter(is_correct=True)]})
        self.put(attempt, self.q3, {"text": "  APPEND "})
        result = self.api.post(reverse("training-attempt-submit", args=[attempt["attempt_id"]]), **self.auth(attempt)).json()
        self.assertEqual(result["status"], "completed")
        self.assertEqual((result["correct"], result["incorrect"], result["skipped"]), (3, 0, 1))
        self.assertEqual((result["score"], result["max_score"], result["percentage"]), (4, 5, 80))
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["review"]), 4)
        self.assertEqual(Answer.objects.filter(attempt_id=attempt["attempt_id"]).count(), 3)

        again = self.put(attempt, self.q4, {"text": "def add(a, b): return a + b"})
        self.assertEqual(again.status_code, 409)
        self.assertEqual(self.api.get(reverse("training-attempt-result", args=[attempt["attempt_id"]])).json()["percentage"], 80)

    def test_deadline_is_enforced_by_the_backend(self):
        attempt = self.start()
        self.put(attempt, self.q1, {"options": [self.right_option(self.q1)]})
        db = StudentAttempt.objects.get(pk=attempt["attempt_id"])
        with mock.patch("django.utils.timezone.now", return_value=db.expires_at + timedelta(seconds=30)):
            late = self.put(attempt, self.q3, {"text": "append"})
        self.assertEqual(late.status_code, 409)
        db.refresh_from_db()
        self.assertEqual((db.status, db.finish_reason), (AttemptStatus.FINISHED, FinishReason.TIME_EXPIRED))
        self.assertEqual(db.finished_at, db.expires_at)
        self.assertEqual(db.score, 40.0)  # only the saved answer counted

    def test_hidden_result(self):
        self.test.show_result = False
        self.test.save()
        attempt = self.start()
        result = self.api.post(reverse("training-attempt-submit", args=[attempt["attempt_id"]]), **self.auth(attempt)).json()
        self.assertEqual(result["status"], "completed")
        self.assertNotIn("percentage", result)


class LeaderboardTests(TrainingFixture):
    def finish(self, name, right: bool):
        attempt = self.start(name)
        option = self.right_option(self.q1) if right else str(self.q1.options.get(is_correct=False).pk)
        self.put(attempt, self.q1, {"options": [option]})
        self.api.post(reverse("training-attempt-submit", args=[attempt["attempt_id"]]), **self.auth(attempt))

    def test_best_result_per_name_ranked(self):
        self.finish("Aibek", right=False)
        self.finish("Islam", right=True)
        self.finish("islam", right=False)  # same name, worse — not shown twice
        self.start("Unfinished")
        board = self.api.get(reverse("training-leaderboard"), {"test": str(self.session.pk)}).json()
        self.assertEqual([(r["rank"], r["student_name"], r["score"]) for r in board], [(1, "Islam", 40), (2, "Aibek", 0)])
        self.assertEqual(set(board[0]), {"rank", "student_name", "score", "duration_seconds", "finished_at", "test_id", "test_title"})


class SecurityTests(TrainingFixture):
    def test_rate_limited(self):
        with override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}):
            cache.clear()
            with mock.patch("apps.training.throttles.TrainingStartThrottle.get_rate", return_value="2/hour"):
                self.start("One")
                self.start("Two")
                response = self.api.post(reverse("training-attempt-start"), {"test_id": str(self.session.pk), "student_name": "Three"}, format="json")
        self.assertEqual(response.status_code, 429)

    def test_methods_not_allowed(self):
        self.assertEqual(self.api.post(reverse("training-test-list"), {}).status_code, 405)
        self.assertEqual(self.api.delete(reverse("training-videos")).status_code, 405)

    def test_question_editor_explanation_lives_in_metadata(self):
        self.assertEqual(self.q1.metadata["explanation"], "Python — backend тил.")

    def test_public_flag_only_for_training(self):
        from apps.testing.forms import SessionForm

        exam = TestSession.objects.create(test=self.test, group=None, session_type=SessionType.EXAM, duration=timedelta(hours=1))
        form = SessionForm({"title": "", "test": self.test.pk, "session_type": "exam", "is_public": "on", "all_students": "on"}, session=exam)
        self.assertFalse(form.is_valid())
        self.assertIn("is_public", form.errors)
        self.assertIsNotNone(timezone.now())
