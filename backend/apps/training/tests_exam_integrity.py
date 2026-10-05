"""Exam attempts in the exam portal — integrity: the current question
survives a reload, concurrent requests never lose or roll back an answer,
and nobody but the browser that started the attempt (through the token the
server issued) can read or change it. Also the session-key entry
(/exam/?key=…), the only way into an exam.

Absolute imports only (see apps/academy/tests.py)."""
from __future__ import annotations

import time
from datetime import timedelta
from unittest import mock

from django.core import signing
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.academy.models import Student
from apps.testing.models import (
    AttemptStatus,
    ExamEventType,
    SessionType,
    StudentAttempt,
    TestSession,
)
from apps.testing.services import exam_portal as portal
from apps.training.exam_api import EXAM_TOKEN_MAX_AGE, EXAM_TOKEN_SALT, exam_token
from apps.training.tests_exam import ExamApiFixture, roster_student


class IntegrityFixture(ExamApiFixture):
    def answer(self, attempt, question, options, seq=None, token=None):
        data = {"options": [str(o) for o in options]}
        if seq is not None:
            data["seq"] = seq
        return self.call("put", attempt, f"answers/{question.pk}/", token=token, **data)

    def move(self, attempt, question, seq, token=None):
        return self.call("patch", attempt, token=token, current_question_id=str(question.pk), seq=seq)

    def right_option(self, question):
        return question.options.get(is_correct=True).pk

    def wrong_option(self, question):
        return question.options.filter(is_correct=False).first().pk

    def finish_required(self, attempt):
        """Answer the required questions (single + multi) — submit is allowed then."""
        if str(self.q_single.pk) not in (StudentAttempt.objects.get(pk=attempt.pk).draft_answers or {}):
            self.answer(attempt, self.q_single, [self.right_option(self.q_single)])
        multi = [o.pk for o in self.q_multi.options.filter(is_correct=True)]
        self.answer(attempt, self.q_multi, multi)

    def second_student(self):
        """Student B — same roster, own browser, own exam link."""
        other = roster_student(self)
        response = self.join(Client(), other)
        attempt = StudentAttempt.objects.get(session=self.session, student=other)
        return attempt, response["Location"].split("#t=", 1)[1]


class CurrentQuestionTests(IntegrityFixture):
    def test_position_is_restored_after_a_reload(self):
        attempt = self.begin()
        self.assertIsNone(self.call("get", attempt).data["current_question_id"])
        moved = self.move(attempt, self.q_text, seq=1000)
        self.assertEqual((moved.status_code, moved.data["saved"]), (200, True))
        # A reload reads the position back from the server.
        self.assertEqual(self.call("get", attempt).data["current_question_id"], str(self.q_text.pk))

    def test_a_late_older_move_does_not_move_the_student_back(self):
        attempt = self.begin()
        self.move(attempt, self.q_text, seq=2000)
        late = self.move(attempt, self.q_single, seq=1500)  # sent earlier, arrived later
        self.assertEqual((late.status_code, late.data["saved"]), (200, False))
        self.assertEqual(self.call("get", attempt).data["current_question_id"], str(self.q_text.pk))

    def test_saving_an_answer_does_not_move_the_position(self):
        attempt = self.begin()
        self.move(attempt, self.q_text, seq=3000)
        self.answer(attempt, self.q_single, [self.right_option(self.q_single)], seq=2500)  # debounced, arrives after the move
        self.assertEqual(self.call("get", attempt).data["current_question_id"], str(self.q_text.pk))

    def test_only_questions_of_the_attempt_and_real_sequence_numbers(self):
        attempt = self.begin()
        foreign = "00000000-0000-0000-0000-000000000001"
        self.assertEqual(self.call("patch", attempt, current_question_id=foreign, seq=1).status_code, 400)
        self.assertEqual(self.call("patch", attempt, current_question_id="not-a-uuid", seq=1).status_code, 400)
        for seq in (None, 0, -5, "7", True, 2 ** 60):
            self.assertEqual(self.call("patch", attempt, current_question_id=str(self.q_text.pk), seq=seq).status_code, 400, seq)

    def test_a_closed_attempt_keeps_its_position(self):
        attempt = self.begin()
        self.move(attempt, self.q_multi, seq=10)
        self.finish_required(attempt)
        self.call("post", attempt, "submit/")
        self.assertEqual(self.move(attempt, self.q_single, seq=20).status_code, 409)
        attempt.refresh_from_db()
        self.assertEqual(str(attempt.current_question_id), str(self.q_multi.pk))


class RaceConditionTests(IntegrityFixture):
    def test_concurrent_autosaves_the_newer_answer_wins(self):
        attempt = self.begin()
        right, wrong = self.right_option(self.q_single), self.wrong_option(self.q_single)
        self.assertEqual(self.answer(attempt, self.q_single, [right], seq=200).status_code, 200)
        self.assertEqual(self.answer(attempt, self.q_single, [wrong], seq=100).status_code, 200)  # older request, late
        attempt.refresh_from_db()
        self.assertEqual(attempt.draft_answers[str(self.q_single.pk)]["options"], [str(right)])
        # A newer save still goes through; saves without a seq (the old page) always apply.
        self.answer(attempt, self.q_single, [wrong], seq=300)
        attempt.refresh_from_db()
        self.assertEqual(attempt.draft_answers[str(self.q_single.pk)]["options"], [str(wrong)])

    def test_two_tabs_share_one_attempt(self):
        attempt = self.begin()
        first_token = self.token
        # The key page opened again in a second tab: same attempt, a fresh token, no new attempt.
        second = self.begin()
        self.assertEqual(second.pk, attempt.pk)
        self.assertEqual(StudentAttempt.objects.filter(session=self.session, student=self.student).count(), 1)
        self.answer(attempt, self.q_single, [self.right_option(self.q_single)], seq=1, token=first_token)
        state = self.call("get", attempt).data  # the second tab sees the first tab's answer
        self.assertIsNotNone(next(q for q in state["questions"] if q["id"] == str(self.q_single.pk))["answer"])

    def test_double_submit_is_idempotent(self):
        attempt = self.begin()
        self.answer(attempt, self.q_single, [self.right_option(self.q_single)])
        self.finish_required(attempt)
        first = self.call("post", attempt, "submit/")
        graded = attempt.answers.count()
        second = self.call("post", attempt, "submit/")
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(first.data["percentage"], second.data["percentage"])
        self.assertEqual(StudentAttempt.objects.filter(session=self.session, student=self.student).count(), 1)
        self.assertEqual(attempt.events.filter(event_type=ExamEventType.EXAM_SUBMITTED).count(), 1)
        self.assertEqual(attempt.answers.count(), graded)

    def test_an_autosave_committed_during_submit_is_not_lost(self):
        attempt = self.begin()
        self.answer(attempt, self.q_single, [self.wrong_option(self.q_single)])
        self.finish_required(attempt)
        # The submit request read the attempt; then the last autosave committed.
        stale = StudentAttempt.objects.select_related("session__test").get(pk=attempt.pk)
        portal.save_drafts(StudentAttempt.objects.get(pk=attempt.pk), {
            str(self.q_single.pk): {"options": [str(self.right_option(self.q_single))]}})
        finished = portal.submit_exam(stale, {})
        self.assertEqual(finished.status, AttemptStatus.FINISHED)
        given = finished.answers.get(question=self.q_single)
        self.assertTrue(given.is_correct)  # the fresh answer, not the copy the submit read first

    def test_an_autosave_after_submit_is_refused_not_merged(self):
        attempt = self.begin()
        self.answer(attempt, self.q_single, [self.right_option(self.q_single)])
        self.finish_required(attempt)
        self.call("post", attempt, "submit/")
        late = self.answer(attempt, self.q_single, [self.wrong_option(self.q_single)], seq=99)
        self.assertEqual((late.status_code, late.data["code"]), (409, "closed"))
        self.assertTrue(attempt.answers.get(question=self.q_single).is_correct)

    def test_the_server_clock_decides_the_deadline(self):
        attempt = self.begin()
        # «timed_out» from the page far from the deadline is an ordinary submit (required questions apply).
        early = self.call("post", attempt, "submit/", timed_out=True)
        self.assertEqual((early.status_code, early.data["code"]), (400, "invalid"))
        # Within the network grace an autosave is still taken …
        StudentAttempt.objects.filter(pk=attempt.pk).update(expires_at=timezone.now() - timedelta(seconds=2))
        self.assertEqual(self.answer(attempt, self.q_single, [self.right_option(self.q_single)]).status_code, 200)
        # … past it the server closes the attempt with what was saved.
        StudentAttempt.objects.filter(pk=attempt.pk).update(expires_at=timezone.now() - timedelta(seconds=30))
        self.assertEqual(self.answer(attempt, self.q_single, [self.wrong_option(self.q_single)]).status_code, 409)
        attempt.refresh_from_db()
        self.assertEqual((attempt.status, attempt.finish_reason), (AttemptStatus.FINISHED, "time_expired"))
        self.assertTrue(attempt.answers.get(question=self.q_single).is_correct)


class ExamSecurityTests(IntegrityFixture):
    """The ten regression cases (IDOR/BOLA and the token)."""

    def setUp(self):
        super().setUp()
        self.mine = self.begin()
        self.theirs, self.their_token = self.second_student()

    def test_01_student_cannot_read_another_students_attempt(self):
        for suffix in ("", "result/"):
            response = self.call("get", self.theirs, suffix)  # my token, their attempt id
            self.assertEqual((response.status_code, response.data["code"]), (403, "forbidden"))
            self.assertNotIn("questions", response.data)

    def test_02_student_cannot_submit_another_students_attempt(self):
        self.assertEqual(self.call("post", self.theirs, "submit/", timed_out=True).status_code, 403)
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.status, AttemptStatus.ACTIVE)

    def test_03_student_cannot_save_into_another_students_attempt(self):
        self.assertEqual(self.answer(self.theirs, self.q_single, [self.right_option(self.q_single)]).status_code, 403)
        self.assertEqual(self.move(self.theirs, self.q_text, seq=5).status_code, 403)
        self.assertEqual(self.call("post", self.theirs, "events/", event_type="TAB_SWITCH").status_code, 403)
        self.theirs.refresh_from_db()
        self.assertEqual((self.theirs.draft_answers, self.theirs.current_question_id, self.theirs.tab_switch_count), ({}, None, 0))

    def test_04_invalid_token(self):
        for token in ("", "garbage", f"{self.mine.pk}", f"{self.mine.pk}:x:y"):
            self.assertEqual(self.call("get", self.mine, token=token).status_code, 403, token)

    def test_05_expired_token(self):
        with mock.patch("django.core.signing.time.time", return_value=time.time() - EXAM_TOKEN_MAX_AGE - 60):
            old = exam_token(self.mine)
        response = self.call("get", self.mine, token=old)
        self.assertEqual((response.status_code, response.data["code"]), (403, "forbidden"))

    def test_06_modified_token(self):
        value, signature = self.token.rsplit(":", 1)
        tampered = [
            value.replace(str(self.mine.pk), str(self.theirs.pk)) + ":" + signature,  # point it at B's attempt
            value.replace(f":{self.student.pk}:", f":{self.theirs.student_id}:") + ":" + signature,  # claim to be B
            value + ":" + signature[:-1] + ("A" if signature[-1] != "A" else "B"),  # broken signature
        ]
        for token in tampered:
            self.assertEqual(self.call("get", self.mine, token=token).status_code, 403, token)
            self.assertEqual(self.call("get", self.theirs, token=token).status_code, 403, token)

    def test_07_valid_token_with_another_attempt_id(self):
        missing = StudentAttempt(pk="00000000-0000-0000-0000-0000000000aa")
        self.assertEqual(self.call("get", missing).status_code, 403)  # no difference between «missing» and «not yours»
        self.assertEqual(self.call("get", self.theirs).status_code, 403)
        # Another exam of the same student: the token is bound to its own attempt and session.
        other_session = TestSession.objects.create(test=self.test, group=self.group, session_type=SessionType.EXAM,
                                                   duration=timedelta(hours=1), title="Пересдача")
        other_session.start()
        other = portal.start_exam(other_session, self.student)
        self.assertEqual(self.call("get", other).status_code, 403)
        # A token whose owner no longer matches the attempt (re-assigned row) is dead too.
        StudentAttempt.objects.filter(pk=self.mine.pk).update(student=self.theirs.student)
        self.assertEqual(self.call("get", self.mine).status_code, 403)

    def test_08_completed_attempt_cannot_be_modified(self):
        self.answer(self.mine, self.q_single, [self.right_option(self.q_single)])
        self.finish_required(self.mine)
        result = self.call("post", self.mine, "submit/").data
        for response in (
            self.answer(self.mine, self.q_single, [self.wrong_option(self.q_single)], seq=10 ** 12),
            self.move(self.mine, self.q_text, seq=10 ** 12),
            self.call("post", self.mine, "events/", event_type="TAB_SWITCH"),
        ):
            self.assertEqual((response.status_code, response.data["code"]), (409, "closed"))
        again = self.call("post", self.mine, "submit/")  # the token is reused: the same result, nothing re-graded
        self.assertEqual((again.status_code, again.data["percentage"]), (200, result["percentage"]))
        self.assertEqual(self.call("get", self.mine, "result/").status_code, 200)

    def test_09_time_expired_attempt_cannot_be_modified(self):
        StudentAttempt.objects.filter(pk=self.mine.pk).update(expires_at=timezone.now() - timedelta(minutes=5))
        self.assertEqual(self.answer(self.mine, self.q_single, [self.right_option(self.q_single)]).status_code, 409)
        self.assertEqual(self.move(self.mine, self.q_text, seq=1).status_code, 409)
        self.mine.refresh_from_db()
        self.assertEqual((self.mine.status, self.mine.draft_answers), (AttemptStatus.FINISHED, {}))

    def test_10_no_unlimited_attempts(self):
        self.session.max_attempts_per_student = 1
        self.session.save()
        for _ in range(3):  # the key page again and again while the attempt runs
            self.join()
        self.assertEqual(StudentAttempt.objects.filter(session=self.session, student=self.student).count(), 1)
        self.finish_required(self.mine)
        self.call("post", self.mine, "submit/")
        refused = self.join()  # the limit is used up
        self.assertContains(refused, "Лимит попыток")
        self.assertEqual(StudentAttempt.objects.filter(session=self.session, student=self.student).count(), 1)
        # The API itself never creates attempts: there is no start endpoint for exams.
        self.assertEqual(self.api.post("/api/v1/training/exam-attempts/", {}, format="json").status_code, 404)


class SessionKeyEntryTests(IntegrityFixture):
    """/exam/?key=… — the link the LMS shows on a session page."""

    def setUp(self):
        super().setUp()
        self.browser = Client()

    def join(self, browser=None, student=None, **extra):
        return super().join(browser or self.browser, student, **extra)

    def test_a_roster_student_lands_in_the_shared_test_ui(self):
        response = self.join()
        self.assertEqual(response.status_code, 302)
        attempt = StudentAttempt.objects.get(session=self.session, student=self.student)
        self.assertTrue(response["Location"].startswith(f"https://train.example.com/exam/{attempt.pk}#t="))
        self.assertTrue(attempt.exam_mode)
        self.assertIsNotNone(attempt.expires_at)  # the server timer runs from now
        self.token = response["Location"].split("#t=", 1)[1]
        self.assertEqual(self.call("get", attempt).data["mode"], "exam")

    def test_refresh_in_the_same_browser_resumes_without_a_second_attempt(self):
        first = self.join()["Location"]
        second = self.join()["Location"]
        self.assertEqual(first.split("#")[0], second.split("#")[0])
        self.assertEqual(StudentAttempt.objects.filter(session=self.session, student=self.student).count(), 1)

    def test_another_browser_cannot_take_over_a_running_exam(self):
        self.join()
        intruder = self.join(Client())
        self.assertEqual(intruder.status_code, 200)
        self.assertNotIn("Location", intruder)
        self.assertContains(intruder, "уже начат")
        self.assertEqual(StudentAttempt.objects.filter(session=self.session).count(), 1)

    def test_a_wrong_key_or_name_gives_no_token(self):
        wrong = self.browser.post(reverse("testing_public_join"), {"key": "NOPE-0000", "start": "1", "student": str(self.student.pk)})
        self.assertEqual(wrong.status_code, 200)
        outsider = Student.objects.create(first_name="Out", last_name="Sider", group=self.other_group)
        self.assertEqual(self.join(student=outsider).status_code, 200)
        self.assertFalse(StudentAttempt.objects.filter(session=self.session).exists())

    def test_a_key_of_an_ended_or_cancelled_session_gives_no_attempt(self):
        for close in ("finish", "cancel"):
            session = TestSession.objects.create(test=self.test, group=self.group, session_type=SessionType.EXAM,
                                                 duration=timedelta(hours=1), title=close)
            session.start()
            getattr(session, close)()
            response = self.browser.post(reverse("testing_public_join"), {"key": session.key, "start": "1", "student": str(self.student.pk)})
            self.assertEqual(response.status_code, 200, close)
            self.assertNotIn("Location", response)
            self.assertFalse(StudentAttempt.objects.filter(session=session).exists())

    def test_an_expired_session_key_gives_no_attempt(self):
        TestSession.objects.filter(pk=self.session.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        response = self.join()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StudentAttempt.objects.filter(session=self.session).exists())

    def test_the_student_cabinet_is_gone(self):
        for path in ("/student/", "/student/login/", "/student/exams/", "/student/results/"):
            self.assertEqual(self.browser.get(path).status_code, 404, path)


class TokenFormatTests(IntegrityFixture):
    def test_token_names_attempt_student_and_session(self):
        attempt = self.begin()
        subject = signing.TimestampSigner(salt=EXAM_TOKEN_SALT).unsign(self.token)
        self.assertEqual(subject, f"{attempt.pk}:{self.student.pk}:{self.session.pk}")
