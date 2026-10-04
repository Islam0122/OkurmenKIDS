"""Student portal and Exam Mode: sign-in, exams list, preparation, the
attempt API (autosave, events), server-side deadline, submit, result, and
the admin / teacher views of violations."""
from __future__ import annotations

import json
from datetime import timedelta
from unittest import mock

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.academy.models import Student
from apps.testing.models import (
    Answer,
    AttemptStatus,
    ExamEventType,
    FinishReason,
    QuestionType,
    SessionType,
    StudentAttempt,
    StudentPortalAccess,
    TestSession,
    TestStatus,
)
from apps.testing.services import exam_portal as portal
from apps.testing.services import questions as svc
from apps.testing.services.question_rules import OptionData, QuestionData
from apps.testing.tests.base import TestingFixture
from apps.users.models import User


class PortalFixture(TestingFixture):
    def setUp(self):
        super().setUp()
        self.test.status = TestStatus.ACTIVE
        self.test.passing_score = 50
        self.test.time_limit_minutes = 30
        self.test.save()
        self.q_single = svc.save_question(self.test, QuestionData(QuestionType.SINGLE_CHOICE, "Backend?", options=[
            OptionData("Python", True), OptionData("HTML", False)]), points=2)
        self.q_multi = svc.save_question(self.test, QuestionData(QuestionType.MULTIPLE_CHOICE, "Immutable?", options=[
            OptionData("tuple", True), OptionData("str", True), OptionData("list", False)]))
        self.q_text = svc.save_question(self.test, QuestionData(
            QuestionType.TEXT, "Что такое Python?", correct_answers=["Язык программирования"]), is_required=False)
        self.session = TestSession.objects.create(
            test=self.test, group=self.group, session_type=SessionType.EXAM, duration=timedelta(hours=2),
            title="Итоговый экзамен",
        )
        self.session.start()
        self.access = StudentPortalAccess.objects.create(student=self.student)
        self.login()

    def login(self, client=None, access=None):
        client = client or self.client
        response = client.post(reverse("student_portal_login"), {"code": (access or self.access).code})
        self.assertEqual(response.status_code, 302)
        return client

    def start(self, client=None):
        client = client or self.client
        response = client.post(reverse("student_exam_prepare", args=[self.session.pk]), {"rules_accepted": "1"})
        self.assertEqual(response.status_code, 302, response.content[:500])
        return StudentAttempt.objects.filter(session=self.session, student=self.student).latest("started_at")

    def patch_answers(self, attempt, answers, client=None, current=1):
        return (client or self.client).patch(
            reverse("student_api_attempt_answers", args=[attempt.pk]),
            data=json.dumps({"answers": answers, "current": current}),
            content_type="application/json",
        )

    def post_event(self, attempt, event_type, client=None):
        return (client or self.client).post(
            reverse("student_api_attempt_events", args=[attempt.pk]),
            data=json.dumps({"event_type": event_type, "metadata": {"question": 2, "answer": "secret"}}),
            content_type="application/json",
        )

    def right(self):
        return {
            str(self.q_single.pk): {"options": [str(self.q_single.options.get(is_correct=True).pk)]},
            str(self.q_multi.pk): {"options": [str(o.pk) for o in self.q_multi.options.filter(is_correct=True)]},
        }


class SignInTests(PortalFixture):
    def test_pages_need_sign_in(self):
        client = Client()
        response = client.get(reverse("student_exams"))
        self.assertRedirects(response, f"{reverse('student_portal_login')}?next=%2Fstudent%2Fexams%2F")
        response = client.get(reverse("student_api_attempt_state", args=["00000000-0000-0000-0000-000000000000"]))
        self.assertEqual(response.status_code, 401)

    def test_wrong_code_is_rejected(self):
        client = Client()
        response = client.post(reverse("student_portal_login"), {"code": "NOPE1234"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Код не найден")

    def test_code_is_case_and_space_insensitive(self):
        client = Client()
        response = client.post(reverse("student_portal_login"), {"code": f" {self.access.code.lower()[:4]} {self.access.code.lower()[4:]} "})
        self.assertRedirects(response, reverse("student_portal_dashboard"))

    def test_inactive_code_or_student_cannot_sign_in(self):
        self.access.is_active = False
        self.access.save()
        self.assertEqual(Client().post(reverse("student_portal_login"), {"code": self.access.code}).status_code, 200)

    def test_regenerated_code_signs_the_student_out(self):
        self.assertEqual(self.client.get(reverse("student_exams")).status_code, 200)
        self.access.regenerate_code()
        self.assertEqual(self.client.get(reverse("student_exams")).status_code, 302)

    def test_rate_limited(self):
        with mock.patch("apps.testing.student_auth.too_many_failed_codes", return_value=True):
            response = Client().post(reverse("student_portal_login"), {"code": self.access.code})
        self.assertEqual(response.status_code, 429)

    def test_logout(self):
        self.client.post(reverse("student_portal_logout"))
        self.assertEqual(self.client.get(reverse("student_exams")).status_code, 302)

    def test_open_redirect_is_ignored(self):
        response = Client().post(reverse("student_portal_login"), {"code": self.access.code, "next": "https://evil.example/"})
        self.assertRedirects(response, reverse("student_portal_dashboard"))


class ExamsListTests(PortalFixture):
    def test_lists_group_exams_with_status_and_summary(self):
        TestSession.objects.create(test=self.test, group=self.other_group, session_type=SessionType.EXAM,
                                   duration=timedelta(hours=1), title="Чужая группа")
        TestSession.objects.create(test=self.test, group=self.group, session_type=SessionType.EXAM,
                                   duration=timedelta(hours=1), title="Черновик")
        scheduled = TestSession.objects.create(
            test=self.test, group=self.group, session_type=SessionType.EXAM, title="Будущий",
            scheduled_start=timezone.now() + timedelta(days=2), scheduled_end=timezone.now() + timedelta(days=2, hours=1),
            duration=timedelta(hours=1),
        )
        response = self.client.get(reverse("student_exams"))
        self.assertEqual(response.status_code, 200)
        titles = [card.title for card in response.context["cards"]]
        self.assertEqual(titles, ["Итоговый экзамен", "Будущий"])
        cards = {c.title: c for c in response.context["cards"]}
        self.assertEqual(cards["Итоговый экзамен"].status, portal.ExamStatus.AVAILABLE)
        self.assertEqual(cards["Будущий"].status, portal.ExamStatus.UPCOMING)
        self.assertEqual(cards["Итоговый экзамен"].question_count, 3)
        self.assertEqual(cards["Итоговый экзамен"].max_points, 4)
        self.assertEqual(response.context["summary"].available, 1)
        self.assertContains(response, "Group 12")
        self.assertContains(response, "Python Beginner")
        self.assertNotContains(response, "Чужая группа")
        self.assertIsNotNone(scheduled.pk)

    def test_roster_session_only_for_its_students(self):
        other = Student.objects.create(first_name="Other", group=self.group)
        session = TestSession.objects.create(test=self.test, group=self.group, session_type=SessionType.EXAM,
                                             duration=timedelta(hours=1), title="Ростер")
        session.participants.create(student=other)
        session.start()
        titles = [c.title for c in portal.student_exam_cards(self.student)]
        self.assertNotIn("Ростер", titles)
        self.assertEqual(self.client.get(reverse("student_exam_prepare", args=[session.pk])).status_code, 404)

    def test_passed_status_and_average(self):
        attempt = self.start()
        self.patch_answers(attempt, self.right())
        self.client.post(reverse("student_exam_submit", args=[self.session.pk, attempt.pk]))
        card = portal.exam_card(self.session, self.student)
        self.assertEqual(card.status, portal.ExamStatus.PASSED)
        summary = portal.summarize([card])
        self.assertEqual((summary.completed, summary.passed, summary.average_percent), (1, 1, 75))


class StartTests(PortalFixture):
    def test_rules_must_be_accepted(self):
        response = self.client.post(reverse("student_exam_prepare", args=[self.session.pk]), {})
        self.assertContains(response, "Подтвердите, что ознакомились")
        self.assertFalse(StudentAttempt.objects.exists())

    def test_prepare_page_shows_rules_and_info(self):
        response = self.client.get(reverse("student_exam_prepare", args=[self.session.pk]))
        self.assertContains(response, "Подготовка к экзамену")
        self.assertContains(response, "Я ознакомился(ась) с правилами экзамена")
        self.assertContains(response, "Нельзя использовать контекстное меню.")

    def test_start_creates_exam_mode_attempt_with_deadline(self):
        before = timezone.now()
        attempt = self.start()
        self.assertTrue(attempt.exam_mode)
        self.assertEqual(attempt.status, AttemptStatus.ACTIVE)
        self.assertAlmostEqual((attempt.expires_at - before).total_seconds(), 30 * 60, delta=5)
        self.assertTrue(attempt.events.filter(event_type=ExamEventType.EXAM_STARTED).exists())
        response = self.client.get(reverse("student_exam_attempt", args=[self.session.pk, attempt.pk]))
        self.assertContains(response, "Exam Mode")
        self.assertContains(response, "data-seconds-left")

    def test_starting_twice_resumes_the_same_attempt(self):
        first = self.start()
        second = self.start()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.events.filter(event_type=ExamEventType.EXAM_STARTED).count(), 1)

    def test_attempt_limit(self):
        self.test.max_attempts = 1
        self.test.save()
        attempt = self.start()
        self.patch_answers(attempt, self.right())
        self.client.post(reverse("student_exam_submit", args=[self.session.pk, attempt.pk]))
        response = self.client.post(reverse("student_exam_prepare", args=[self.session.pk]), {"rules_accepted": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Все попытки использованы.")
        self.assertEqual(StudentAttempt.objects.count(), 1)
        self.assertEqual(response.context["card"].attempts_left, 0)


class OwnershipTests(PortalFixture):
    def setUp(self):
        super().setUp()
        self.attempt = self.start()
        self.other_student = Student.objects.create(first_name="Bakyt", group=self.group)
        self.other_client = self.login(Client(), StudentPortalAccess.objects.create(student=self.other_student))

    def test_other_student_cannot_open_or_change_the_attempt(self):
        url = reverse("student_exam_attempt", args=[self.session.pk, self.attempt.pk])
        self.assertEqual(self.other_client.get(url).status_code, 404)
        self.assertEqual(self.patch_answers(self.attempt, self.right(), client=self.other_client).status_code, 404)
        self.assertEqual(self.post_event(self.attempt, "TAB_SWITCH", client=self.other_client).status_code, 404)
        response = self.other_client.post(reverse("student_exam_submit", args=[self.session.pk, self.attempt.pk]))
        self.assertEqual(response.status_code, 404)
        self.attempt.refresh_from_db()
        self.assertEqual((self.attempt.status, self.attempt.draft_answers, self.attempt.tab_switch_count), ("active", {}, 0))

    def test_wrong_exam_in_url(self):
        other = TestSession.objects.create(test=self.test, group=self.group, session_type=SessionType.EXAM,
                                           duration=timedelta(hours=1))
        self.assertEqual(self.client.get(reverse("student_exam_attempt", args=[other.pk, self.attempt.pk])).status_code, 404)

    def test_csrf_is_enforced(self):
        client = Client(enforce_csrf_checks=True)
        client.cookies = self.client.cookies
        self.assertEqual(self.patch_answers(self.attempt, self.right(), client=client).status_code, 403)

    def test_legacy_exam_page_does_not_open_exam_mode_attempt(self):
        session = self.client.session
        session["testing_attempts"] = [str(self.attempt.pk)]
        session.save()
        response = self.client.get(reverse("testing_public_take", args=[self.attempt.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Exam Mode", status_code=403)


class AutosaveTests(PortalFixture):
    def setUp(self):
        super().setUp()
        self.attempt = self.start()

    def test_saves_drafts_without_grading(self):
        response = self.patch_answers(self.attempt, self.right(), current=2)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["saved"])
        self.assertGreater(response.json()["remaining_seconds"], 0)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.draft_answers, self.right())
        self.assertFalse(Answer.objects.exists())  # graded only on submit
        self.assertTrue(self.attempt.events.filter(event_type=ExamEventType.ANSWER_SAVED).exists())
        participant = self.session.participants.get(student=self.student)
        self.assertEqual((participant.current_question, participant.answered_count), (2, 2))

    def test_merges_partial_saves(self):
        self.patch_answers(self.attempt, {str(self.q_text.pk): {"text": "язык"}})
        self.patch_answers(self.attempt, {str(self.q_text.pk): {"text": "язык программирования"}})
        self.patch_answers(self.attempt, self.right())
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.draft_answers[str(self.q_text.pk)], {"text": "язык программирования"})
        self.assertEqual(len(self.attempt.draft_answers), 3)

    def test_validation(self):
        foreign = svc.save_question(self.test, QuestionData(QuestionType.SINGLE_CHOICE, "Not in attempt?", options=[
            OptionData("a", True), OptionData("b", False)]))
        cases = [
            {str(foreign.pk): {"options": [str(foreign.options.first().pk)]}},
            {str(self.q_single.pk): {"options": [str(self.q_multi.options.first().pk)]}},
            {str(self.q_single.pk): {"options": [str(o.pk) for o in self.q_single.options.all()]}},
            {str(self.q_text.pk): {"text": "x" * (portal.MAX_TEXT_ANSWER + 1)}},
            {str(self.q_text.pk): "plain"},
        ]
        for answers in cases:
            with self.subTest(answers=str(answers)[:60]):
                self.assertEqual(self.patch_answers(self.attempt, answers).status_code, 400)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.draft_answers, {})

    def test_paused_session_rejects_saves(self):
        self.session.pause()
        response = self.patch_answers(self.attempt, self.right())
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["paused"])


class EventTests(PortalFixture):
    def setUp(self):
        super().setUp()
        self.attempt = self.start()

    def test_tab_switch_is_counted_and_logged_without_extra_data(self):
        response = self.post_event(self.attempt, "TAB_SWITCH")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tab_switch_count"], 1)
        self.assertFalse(response.json()["terminated"])
        event = self.attempt.events.get(event_type=ExamEventType.TAB_SWITCH)
        self.assertEqual(event.metadata, {"question": 2})  # "answer" dropped
        self.assertEqual(event.ip_address, "127.0.0.1")
        self.attempt.refresh_from_db()
        self.assertEqual((self.attempt.tab_switch_count, self.attempt.violation_count), (1, 1))

    def test_violations_are_counted(self):
        for event in ("COPY_ATTEMPT", "PASTE_ATTEMPT", "CUT_ATTEMPT", "CONTEXT_MENU_ATTEMPT", "DEVTOOLS_ATTEMPT"):
            self.assertEqual(self.post_event(self.attempt, event).status_code, 200)
        self.post_event(self.attempt, "PAGE_LEAVE")
        self.attempt.refresh_from_db()
        self.assertEqual((self.attempt.violation_count, self.attempt.tab_switch_count), (5, 0))

    def test_fullscreen_exit_counts_only_when_required(self):
        self.post_event(self.attempt, "FULLSCREEN_EXIT")
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.violation_count, 0)
        self.test.require_fullscreen = True
        self.test.save()
        self.post_event(self.attempt, "FULLSCREEN_EXIT")
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.violation_count, 1)
        self.assertEqual(self.attempt.events.filter(event_type=ExamEventType.FULLSCREEN_EXIT).count(), 2)

    def test_server_only_and_unknown_events_are_rejected(self):
        for event in ("EXAM_SUBMITTED", "TIME_EXPIRED", "anything"):
            self.assertEqual(self.post_event(self.attempt, event).status_code, 400)

    def test_page_leave_beacon_with_form_data(self):
        response = self.client.post(reverse("student_api_attempt_events", args=[self.attempt.pk]),
                                    {"event_type": "PAGE_LEAVE", "question": "3"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.attempt.events.get(event_type="PAGE_LEAVE").metadata, {"question": 3})

    def test_exceeding_tab_switch_limit_ends_the_exam_with_saved_answers(self):
        self.patch_answers(self.attempt, self.right())
        for _ in range(3):
            self.assertEqual(self.post_event(self.attempt, "TAB_SWITCH").status_code, 200)
        response = self.post_event(self.attempt, "TAB_SWITCH")
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["terminated"])
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, AttemptStatus.FINISHED)
        self.assertEqual(self.attempt.finish_reason, FinishReason.VIOLATIONS)
        self.assertEqual(self.attempt.score, 75.0)
        self.assertTrue(self.attempt.events.filter(event_type=ExamEventType.EXAM_TERMINATED).exists())
        result = self.client.get(reverse("student_exam_result", args=[self.session.pk, self.attempt.pk]))
        self.assertContains(result, "превышения допустимого количества нарушений")

    def test_no_limit_never_terminates(self):
        self.test.max_tab_switches = None
        self.test.save()
        for _ in range(10):
            self.assertEqual(self.post_event(self.attempt, "TAB_SWITCH").status_code, 200)


class DeadlineTests(PortalFixture):
    def setUp(self):
        super().setUp()
        self.attempt = self.start()
        self.patch_answers(self.attempt, self.right())

    def later(self, seconds_after_deadline=10):
        return mock.patch("django.utils.timezone.now",
                          return_value=self.attempt.expires_at + timedelta(seconds=seconds_after_deadline))

    def test_backend_closes_expired_attempt_with_saved_answers(self):
        with self.later():
            response = self.patch_answers(self.attempt, {str(self.q_text.pk): {"text": "Язык программирования"}})
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.json()["closed"])
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, AttemptStatus.FINISHED)
        self.assertEqual(self.attempt.finish_reason, FinishReason.TIME_EXPIRED)
        self.assertEqual(self.attempt.finished_at, self.attempt.expires_at)
        self.assertEqual(self.attempt.score, 75.0)  # the late text answer was not accepted
        self.assertFalse(Answer.objects.filter(question=self.q_text).exists())
        self.assertTrue(self.attempt.events.filter(event_type=ExamEventType.TIME_EXPIRED).exists())

    def test_expired_attempt_page_redirects_to_result(self):
        with self.later():
            response = self.client.get(reverse("student_exam_attempt", args=[self.session.pk, self.attempt.pk]))
        self.assertRedirects(response, reverse("student_exam_result", args=[self.session.pk, self.attempt.pk]))

    def test_without_auto_submit_the_attempt_expires_ungraded(self):
        self.test.auto_submit = False
        self.test.save()
        with self.later():
            self.client.get(reverse("student_api_attempt_state", args=[self.attempt.pk]))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, AttemptStatus.EXPIRED)
        self.assertFalse(Answer.objects.exists())

    def test_auto_submit_at_zero_is_accepted(self):
        with self.later(seconds_after_deadline=2):
            response = self.client.post(reverse("student_exam_submit", args=[self.session.pk, self.attempt.pk]), {
                "timed_out": "1", f"answer_{self.q_text.pk}": "Язык программирования",
            })
        self.assertEqual(response.status_code, 302)
        self.attempt.refresh_from_db()
        self.assertEqual((self.attempt.status, self.attempt.finish_reason), (AttemptStatus.FINISHED, FinishReason.TIME_EXPIRED))
        self.assertEqual(self.attempt.score, 100.0)

    def test_timed_out_flag_early_does_not_skip_required_questions(self):
        response = self.client.post(reverse("student_exam_submit", args=[self.session.pk, self.attempt.pk]), {
            "timed_out": "1", f"answer_{self.q_single.pk}": "",
        })
        self.assertEqual(response.status_code, 302)
        self.attempt.refresh_from_db()
        # Drafts already hold the required answers, so this is a normal submit.
        self.assertEqual(self.attempt.finish_reason, FinishReason.SUBMITTED)

    def test_timer_on_attempt_page_comes_from_the_server(self):
        with mock.patch("django.utils.timezone.now", return_value=self.attempt.expires_at - timedelta(minutes=12)):
            response = self.client.get(reverse("student_exam_attempt", args=[self.session.pk, self.attempt.pk]))
        self.assertEqual(response.context["seconds_left"], 12 * 60)


class SubmitTests(PortalFixture):
    def setUp(self):
        super().setUp()
        self.attempt = self.start()

    def submit(self, data=None):
        return self.client.post(reverse("student_exam_submit", args=[self.session.pk, self.attempt.pk]), data or {})

    def test_required_questions_block_submit(self):
        response = self.submit()
        self.assertRedirects(response, reverse("student_exam_attempt", args=[self.session.pk, self.attempt.pk]),
                             fetch_redirect_response=False)
        page = self.client.get(response.url)
        self.assertContains(page, "Ответьте на обязательные вопросы: 1, 2")
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, AttemptStatus.ACTIVE)

    def test_submit_grades_drafts_and_locks_the_attempt(self):
        self.patch_answers(self.attempt, self.right())
        response = self.submit({f"answer_{self.q_text.pk}": "nope"})
        self.assertRedirects(response, reverse("student_exam_result", args=[self.session.pk, self.attempt.pk]))
        self.attempt.refresh_from_db()
        self.assertEqual((self.attempt.status, self.attempt.finish_reason), (AttemptStatus.FINISHED, FinishReason.SUBMITTED))
        self.assertEqual(self.attempt.score, 75.0)
        self.assertEqual(Answer.objects.filter(attempt=self.attempt).count(), 3)
        self.assertTrue(self.attempt.events.filter(event_type=ExamEventType.EXAM_SUBMITTED).exists())
        # No more changes: autosave, events and a second submit are refused / no-ops.
        self.assertEqual(self.patch_answers(self.attempt, {str(self.q_text.pk): {"text": "Язык программирования"}}).status_code, 409)
        self.assertEqual(self.post_event(self.attempt, "TAB_SWITCH").status_code, 409)
        self.submit({f"answer_{self.q_text.pk}": "Язык программирования"})
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.score, 75.0)
        self.assertEqual(self.attempt.events.filter(event_type=ExamEventType.EXAM_SUBMITTED).count(), 1)

    def test_result_page(self):
        self.patch_answers(self.attempt, self.right())
        self.submit()
        response = self.client.get(reverse("student_exam_result", args=[self.session.pk, self.attempt.pk]))
        self.assertContains(response, "3 / 4")
        self.assertContains(response, "75%")
        self.assertContains(response, "ПРОЙДЕН")
        self.assertNotContains(response, "Посмотреть разбор")
        self.assertEqual(self.client.get(reverse("student_exam_review", args=[self.session.pk, self.attempt.pk])).status_code, 404)

    def test_review_when_allowed(self):
        self.test.show_correct_answers = True
        self.test.save()
        self.patch_answers(self.attempt, self.right())
        self.submit()
        result = self.client.get(reverse("student_exam_result", args=[self.session.pk, self.attempt.pk]))
        self.assertContains(result, "Посмотреть разбор")
        review = self.client.get(reverse("student_exam_review", args=[self.session.pk, self.attempt.pk]))
        self.assertContains(review, "Правильный ответ")
        self.assertContains(review, "Язык программирования")

    def test_hidden_result(self):
        self.test.show_result = False
        self.test.save()
        self.patch_answers(self.attempt, self.right())
        self.submit()
        response = self.client.get(reverse("student_exam_result", args=[self.session.pk, self.attempt.pk]))
        self.assertContains(response, "Ответы отправлены")
        self.assertNotContains(response, "ПРОЙДЕН")
        self.assertEqual(portal.exam_card(self.session, self.student).status, portal.ExamStatus.FINISHED)


class StaffViewsTests(PortalFixture):
    def setUp(self):
        super().setUp()
        self.attempt = self.start()
        self.post_event(self.attempt, "TAB_SWITCH")
        self.post_event(self.attempt, "COPY_ATTEMPT")
        self.admin = User.objects.create_superuser(username="root", email="root@okurmen.kg", password="x")

    def test_admin_monitoring_and_event_log(self):
        admin_client = Client()
        admin_client.force_login(self.admin)
        response = admin_client.get(reverse("admin:testing_exam_monitoring"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aibek Asanov")
        response = admin_client.get(reverse("admin:testing_attempt_detail", args=[self.attempt.pk]))
        self.assertContains(response, "Журнал событий")
        self.assertContains(response, "Уход со страницы")
        self.assertContains(response, "Попытка копирования")

    def test_admin_settings_has_exam_mode_fields(self):
        admin_client = Client()
        admin_client.force_login(self.admin)
        response = admin_client.get(reverse("admin:testing_test_settings", args=[self.test.pk]))
        self.assertContains(response, "max_tab_switches")
        self.assertContains(response, "require_fullscreen")
        self.assertContains(response, "auto_submit")

    def test_admin_issues_codes_for_a_group(self):
        Student.objects.create(first_name="New", group=self.group)
        admin_client = Client()
        admin_client.force_login(self.admin)
        response = admin_client.post(reverse("admin:testing_studentportalaccess_issue_group"), {"group": self.group.pk})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(StudentPortalAccess.objects.filter(student__group=self.group).count(), 2)
        self.assertEqual(admin_client.get(reverse("admin:testing_studentportalaccess_changelist")).status_code, 200)

    def test_teacher_api_reports_violations(self):
        from apps.testing.teacher_api import ParticipantSerializer

        participant = self.session.participants.select_related("student", "attempt").get(student=self.student)
        data = ParticipantSerializer(participant).data
        self.assertEqual((data["tab_switch_count"], data["violation_count"]), (1, 2))
