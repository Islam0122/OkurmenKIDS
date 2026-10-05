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
    ExamAttemptEvent,
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
        settings.exam_url = "https://lms.example.com/exam/"
        settings.save()
        TrainingVideo.objects.create(title="Shown", video_url="https://youtu.be/abcdefghijk", published=True, order=2)
        TrainingVideo.objects.create(title="Draft", video_url="https://youtu.be/abcdefghijk", published=False)
        TrainingLink.objects.create(title="Docs", url="https://docs.python.org/3/", published=True, icon="filetype-py")
        TrainingLink.objects.create(title="Hidden", url="https://example.com/", published=False)

        portal = self.api.get(reverse("training-portal")).json()
        self.assertEqual(portal["exam_url"], "https://lms.example.com/exam/")
        self.assertEqual(portal["hero_title"], "Экзаменге даярдан")
        self.assertEqual([v["title"] for v in self.api.get(reverse("training-videos")).json()], ["Shown"])
        self.assertEqual([l["title"] for l in self.api.get(reverse("training-links")).json()], ["Docs"])

    def test_trainers_come_with_their_category_grouped_and_naturally_ordered(self):
        english = Subject.objects.get_or_create(name="English")[0]
        def trainer(title, subject):
            test = Test.objects.create(title=title, subject=subject, status=TestStatus.ACTIVE)
            svc.save_question(test, QuestionData(QuestionType.TEXT, "Q?", correct_answers=["a"]))
            session = TestSession.objects.create(test=test, session_type=SessionType.TRAINING, is_public=True)
            session.start()
        trainer("English Month 10", english)
        trainer("English Month 2", english)
        trainer("No category", None)
        tests = self.api.get(reverse("training-test-list")).json()
        self.assertEqual([t["title"] for t in tests], ["English Month 2", "English Month 10", "Python Training", "No category"])
        self.assertEqual(tests[0]["category"], {"id": english.pk, "name": "English", "slug": "english"})
        self.assertEqual(tests[2]["category"]["name"], "Python")
        self.assertIsNone(tests[3]["category"])

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


class EventTests(TrainingFixture):
    def post_event(self, attempt, event_type, **extra):
        return self.api.post(reverse("training-attempt-events", args=[attempt["attempt_id"]]),
                             {"event_type": event_type, "metadata": {"question": 1}}, format="json", **extra)

    def test_events_are_logged_counted_and_need_the_token(self):
        attempt = self.start()
        self.assertEqual(self.post_event(attempt, "TAB_SWITCH").status_code, 403)
        response = self.post_event(attempt, "TAB_SWITCH", **self.auth(attempt))
        self.assertEqual(response.json()["tab_switch_count"], 1)
        self.post_event(attempt, "TAB_RETURN", **self.auth(attempt))
        self.post_event(attempt, "COPY_ATTEMPT", **self.auth(attempt))
        self.assertEqual(self.post_event(attempt, "EXAM_SUBMITTED", **self.auth(attempt)).status_code, 400)
        db = StudentAttempt.objects.get(pk=attempt["attempt_id"])
        self.assertEqual((db.tab_switch_count, db.violation_count), (1, 2))
        types = list(db.events.values_list("event_type", flat=True))
        self.assertEqual(types, ["TRAINING_STARTED", "TAB_SWITCH", "TAB_RETURN", "COPY_ATTEMPT"])

    def test_server_events_and_termination(self):
        self.test.max_tab_switches = 1
        self.test.save()
        attempt = self.start()
        self.put(attempt, self.q1, {"options": [self.right_option(self.q1)]})
        self.post_event(attempt, "TAB_SWITCH", **self.auth(attempt))
        response = self.post_event(attempt, "TAB_SWITCH", **self.auth(attempt))
        self.assertEqual((response.status_code, response.json()["code"]), (409, "terminated"))
        db = StudentAttempt.objects.get(pk=attempt["attempt_id"])
        self.assertEqual((db.status, db.finish_reason), (AttemptStatus.FINISHED, FinishReason.VIOLATIONS))
        self.assertIn("ANSWER_SAVED", db.events.values_list("event_type", flat=True))
        self.assertIn("EXAM_TERMINATED", db.events.values_list("event_type", flat=True))
        self.assertEqual(db.score, 40.0)  # saved answers still graded

    def test_untracked_tab_switches_and_optional_fullscreen_are_not_violations(self):
        self.test.track_tab_switches = False
        self.test.max_tab_switches = 0
        self.test.save()
        attempt = self.start()
        self.assertEqual(self.post_event(attempt, "TAB_SWITCH", **self.auth(attempt)).status_code, 200)
        self.post_event(attempt, "FULLSCREEN_EXIT", **self.auth(attempt))
        db = StudentAttempt.objects.get(pk=attempt["attempt_id"])
        self.assertEqual((db.tab_switch_count, db.violation_count, db.status), (0, 0, AttemptStatus.ACTIVE))

    def test_security_settings_and_trainer_exam_url_in_the_api(self):
        self.test.require_fullscreen = True
        self.test.save()
        PortalSettings.objects.update_or_create(pk=1, defaults={"exam_url": "https://lms.example.com/"})
        data = self.api.get(reverse("training-test-detail", args=[self.session.pk])).json()
        self.assertEqual(data["security"], {"require_fullscreen": True, "track_tab_switches": True,
                                            "max_tab_switches": 3, "block_copy_paste": True})
        self.assertEqual(data["exam_url"], "https://lms.example.com/")
        self.session.exam_url = "https://lms.example.com/exam/7/"
        self.session.save()
        self.assertEqual(self.api.get(reverse("training-test-detail", args=[self.session.pk])).json()["exam_url"],
                         "https://lms.example.com/exam/7/")


class PublicAccessTests(TrainingFixture):
    """The trainer is a public product: a name is all it takes."""

    def test_anyone_trains_with_a_name_only(self):
        from apps.users.models import User

        users_before = User.objects.count()
        attempt = self.start("Islam")
        self.assertEqual(self.api.post(reverse("training-attempt-submit", args=[attempt["attempt_id"]]), **self.auth(attempt)).status_code, 200)
        db = StudentAttempt.objects.get(pk=attempt["attempt_id"])
        self.assertEqual((db.student_id, db.user_id, db.student_name), (None, None, "Islam"))
        self.assertEqual(User.objects.count(), users_before)
        board = self.api.get(reverse("training-leaderboard"), {"test": str(self.session.pk)}).json()
        self.assertEqual(board[0]["student_name"], "Islam")

    def test_events_keep_no_ip_or_browser_string(self):
        attempt = self.start()
        self.api.post(reverse("training-attempt-events", args=[attempt["attempt_id"]]), {"event_type": "TAB_SWITCH"},
                      format="json", HTTP_USER_AGENT="Mozilla/5.0", REMOTE_ADDR="10.1.2.3", **self.auth(attempt))
        events = ExamAttemptEvent.objects.filter(attempt_id=attempt["attempt_id"])
        self.assertTrue(events.exists())
        self.assertFalse(events.exclude(ip_address=None).exists())
        self.assertFalse(events.exclude(user_agent="").exists())

    def test_retry_follows_the_trainer_setting(self):
        attempt = self.start("Aizada")
        self.api.post(reverse("training-attempt-submit", args=[attempt["attempt_id"]]), **self.auth(attempt))
        self.start("Aizada")  # retry allowed by default
        self.test.allow_retry = False
        self.test.save()
        self.assertTrue(self.api.get(reverse("training-test-detail", args=[self.session.pk])).json()["allow_retry"] is False)
        other = self.start("Bek")
        self.api.post(reverse("training-attempt-submit", args=[other["attempt_id"]]), **self.auth(other))
        response = self.api.post(reverse("training-attempt-start"), {"test_id": str(self.session.pk), "student_name": "bek"}, format="json")
        self.assertEqual((response.status_code, response.json()["code"]), (409, "retry_disabled"))


class TrainerAdminTests(TestCase):
    def setUp(self):
        from apps.users.models import User

        self.admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password="x")
        self.client.force_login(self.admin)
        self.subject = Subject.objects.get_or_create(name="Python")[0]

    def form_data(self, **overrides):
        data = {
            "title": "Python тренажёр", "test": "", "description": "Негиздер", "subject": self.subject.pk, "course": "", "teacher": "", "publication": "draft",
            "image_url": "", "questions_per_attempt": "", "time_limit_minutes": "20", "passing_score": "60",
            "show_correct_answers": "on", "show_result": "on", "allow_retry": "on", "max_attempts_per_student": "",
            "shuffle_questions": "on", "require_fullscreen": "on", "track_tab_switches": "on", "max_tab_switches": "2",
            "block_copy_paste": "on", "exam_url": "",
        }
        data.update(overrides)
        return data

    def test_create_edit_publish_and_archive(self):
        from apps.training.models import Trainer, TrainerStatus

        response = self.client.post(reverse("admin:training_trainer_add"), self.form_data())
        self.assertEqual(response.status_code, 302, getattr(response, "context_data", {}).get("adminform") and response.context_data["adminform"].form.errors)
        trainer = Trainer.objects.get()
        test = trainer.test
        self.assertEqual((trainer.session_type, test.title, test.require_fullscreen, test.max_tab_switches), ("training", "Python тренажёр", True, 2))
        self.assertEqual(trainer.trainer_status, TrainerStatus.DRAFT)
        self.assertEqual(self.client.get(reverse("training-test-list")).json(), [])

        # Publishing needs questions.
        changelist = reverse("admin:training_trainer_changelist")
        self.client.post(changelist, {"action": "publish", "_selected_action": [trainer.pk]})
        trainer.refresh_from_db()
        self.assertEqual(trainer.trainer_status, TrainerStatus.DRAFT)
        svc.save_question(test, QuestionData(QuestionType.SINGLE_CHOICE, "Q?", options=[OptionData("a", True), OptionData("b", False)]))
        self.client.post(changelist, {"action": "publish", "_selected_action": [trainer.pk]})
        trainer.refresh_from_db()
        self.assertEqual(trainer.trainer_status, TrainerStatus.PUBLISHED)
        self.assertEqual([t["id"] for t in self.client.get(reverse("training-test-list")).json()], [str(trainer.pk)])

        page = self.client.get(reverse("admin:training_trainer_change", args=[trainer.pk]))
        self.assertContains(page, "Вопросы")
        PortalSettings.objects.update_or_create(pk=1, defaults={"portal_url": "https://train.example.com"})
        page = self.client.get(changelist)
        self.assertContains(page, f"https://train.example.com/training/{trainer.pk}")

        self.client.post(reverse("admin:training_trainer_change", args=[trainer.pk]), self.form_data(test=test.pk, max_tab_switches="5", publication="published"))
        test.refresh_from_db()
        trainer.refresh_from_db()
        self.assertEqual((test.max_tab_switches, trainer.trainer_status), (5, TrainerStatus.PUBLISHED))

        self.client.post(changelist, {"action": "archive", "_selected_action": [trainer.pk]})
        trainer.refresh_from_db()
        self.assertEqual(trainer.trainer_status, TrainerStatus.ARCHIVED)
        self.assertEqual(self.client.get(reverse("training-test-list")).json(), [])

    def test_status_field_publishes_for_everyone(self):
        from apps.training.models import Trainer, TrainerStatus

        # A new trainer has no questions yet: «Опубликован» is refused, nothing saved.
        response = self.client.post(reverse("admin:training_trainer_add"), self.form_data(publication="published"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("publication", response.context_data["adminform"].form.errors)
        self.assertFalse(Trainer.objects.exists())

        self.client.post(reverse("admin:training_trainer_add"), self.form_data())
        trainer = Trainer.objects.get()
        svc.save_question(trainer.test, QuestionData(QuestionType.SINGLE_CHOICE, "Q?", options=[OptionData("a", True), OptionData("b", False)]))
        change = reverse("admin:training_trainer_change", args=[trainer.pk])
        self.client.post(change, self.form_data(test=trainer.test.pk, publication="published"))
        trainer.refresh_from_db()
        self.assertEqual((trainer.trainer_status, trainer.group_id, trainer.teacher_id), (TrainerStatus.PUBLISHED, None, None))
        self.client.logout()  # anyone, no account
        listed = self.client.get(reverse("training-test-list")).json()
        self.assertEqual([t["id"] for t in listed], [str(trainer.pk)])
        for private in ("group", "teacher", "key", "status", "is_public"):
            self.assertNotIn(private, listed[0])

        self.client.force_login(self.admin)
        self.client.post(change, self.form_data(test=trainer.test.pk, publication="draft"))
        trainer.refresh_from_db()
        self.assertEqual(trainer.trainer_status, TrainerStatus.DRAFT)
        self.assertEqual(self.client.get(reverse("training-test-list")).json(), [])
        self.client.post(change, self.form_data(test=trainer.test.pk, publication="archived"))
        trainer.refresh_from_db()
        self.assertEqual(trainer.trainer_status, TrainerStatus.ARCHIVED)
        response = self.client.post(change, self.form_data(test=trainer.test.pk, publication="published"))
        self.assertIn("publication", response.context_data["adminform"].form.errors)

    def test_attempts_list_and_monitoring_pages_open(self):
        self.assertEqual(self.client.get(reverse("admin:training_trainingattempt_changelist")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:training_trainer_changelist")).status_code, 200)
