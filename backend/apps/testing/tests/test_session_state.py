"""TestSession state machine, timer (pause/resume/extend), keys and review state.

Absolute imports only — see the note at the top of apps/academy/tests.py
(full test discovery imports modules under the `backend.` prefix too).
"""
from __future__ import annotations

import datetime as dt
import re
from datetime import timedelta
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.testing.models import (
    SESSION_KEY_ALPHABET,
    Answer,
    AttemptStatus,
    GradingStatus,
    Question,
    SessionStatus,
    SessionTransitionError,
    SessionType,
    StudentAttempt,
    Test,
    TestSession,
    normalize_session_key,
    session_key_prefix,
)
from apps.testing.tests.base import TestingFixture
from apps.users.models import Subject

T0 = timezone.make_aware(dt.datetime(2026, 9, 29, 10, 0))
HOUR = timedelta(hours=1)
KEY_RE = re.compile(rf"^[A-Z]{{2}}-[{SESSION_KEY_ALPHABET}]{{5}}$")


class ClockMixin:
    """Freezes timezone.now() and lets a test move it forward."""

    def setUp(self):
        self.now = T0
        patcher = mock.patch("django.utils.timezone.now", side_effect=lambda: self.now)
        patcher.start()
        self.addCleanup(patcher.stop)
        super().setUp()

    def advance(self, delta: timedelta):
        self.now += delta


class SessionStateFixture(ClockMixin, TestingFixture):
    def exam(self, duration=HOUR, **fields) -> TestSession:
        return self.make_session(group=self.group, duration=duration, **fields)

    def running_exam(self, duration=HOUR) -> TestSession:
        session = self.exam(duration)
        session.start()
        return session


class TransitionTests(SessionStateFixture):
    def test_new_exam_is_created_without_a_deadline(self):
        session = self.exam()
        self.assertEqual(session.status, SessionStatus.CREATED)
        self.assertIsNone(session.expires_at)
        self.assertTrue(session.is_active)
        self.assertFalse(session.accepts_answers)
        self.assertEqual(session.remaining_time, HOUR)

    def test_start_sets_the_deadline_from_duration(self):
        session = self.running_exam()
        self.assertEqual(session.status, SessionStatus.RUNNING)
        self.assertEqual(session.started_at, T0)
        self.assertEqual(session.expires_at, T0 + HOUR)
        self.assertTrue(session.accepts_answers)

    def test_pause_freezes_the_timer_and_blocks_answers(self):
        session = self.running_exam()
        self.advance(timedelta(minutes=10))
        session.pause()

        self.assertEqual(session.status, SessionStatus.PAUSED)
        self.assertEqual(session.paused_at, T0 + timedelta(minutes=10))
        self.assertFalse(session.accepts_answers)
        self.assertEqual(session.remaining_time, timedelta(minutes=50))

        self.advance(3 * HOUR)  # a pause longer than the whole exam
        self.assertEqual(session.remaining_time, timedelta(minutes=50))
        self.assertEqual(session.effective_status, SessionStatus.PAUSED)

    def test_resume_continues_the_countdown_where_it_stopped(self):
        session = self.running_exam()
        self.advance(timedelta(minutes=10))
        session.pause()
        self.advance(timedelta(minutes=30))
        session.resume()

        self.assertEqual(session.status, SessionStatus.RUNNING)
        self.assertIsNone(session.paused_at)
        self.assertEqual(session.expires_at, T0 + HOUR + timedelta(minutes=30))
        self.assertEqual(session.remaining_time, timedelta(minutes=50))
        self.advance(timedelta(minutes=20))
        self.assertEqual(session.remaining_time, timedelta(minutes=30))

    def test_several_pauses_add_up(self):
        session = self.running_exam()
        for _ in range(3):
            self.advance(timedelta(minutes=5))
            session.pause()
            self.advance(timedelta(minutes=15))
            session.resume()
        self.assertEqual(session.remaining_time, timedelta(minutes=45))

    def test_finish_from_running(self):
        session = self.running_exam()
        self.advance(timedelta(minutes=5))
        session.finish()
        self.assertEqual(session.status, SessionStatus.FINISHED)
        self.assertEqual(session.ended_at, T0 + timedelta(minutes=5))
        self.assertFalse(session.is_active)
        self.assertFalse(session.accepts_answers)
        self.assertEqual(session.remaining_time, timedelta(0))

    def test_finish_from_paused(self):
        session = self.running_exam()
        session.pause()
        session.finish()
        self.assertEqual(session.status, SessionStatus.FINISHED)
        self.assertIsNone(session.paused_at)
        self.assertFalse(session.is_active)

    def test_running_session_expires_lazily_at_its_deadline(self):
        session = self.running_exam()
        self.advance(HOUR)
        self.assertEqual(session.status, SessionStatus.RUNNING)  # stored value lags…
        self.assertEqual(session.effective_status, SessionStatus.EXPIRED)  # …the effective one doesn't
        self.assertFalse(session.accepts_answers)

        session.expire()
        self.assertEqual(session.status, SessionStatus.EXPIRED)
        self.assertEqual(session.ended_at, T0 + HOUR)
        self.assertFalse(session.is_active)
        session.expire()  # idempotent

    def test_rejected_action_still_persists_lazy_expiry(self):
        session = self.running_exam()
        self.advance(HOUR + timedelta(seconds=1))
        with self.assertRaises(SessionTransitionError):
            session.pause()
        self.assertEqual(session.status, SessionStatus.EXPIRED)
        session.refresh_from_db()
        self.assertEqual(session.status, SessionStatus.EXPIRED)

    def test_only_the_documented_transitions_are_allowed(self):
        allowed = {
            SessionStatus.CREATED: {"start"},
            SessionStatus.RUNNING: {"pause", "finish", "expire"},
            SessionStatus.PAUSED: {"resume", "finish"},
            SessionStatus.FINISHED: set(),
            SessionStatus.EXPIRED: {"expire"},  # idempotent no-op
        }
        for status, ok_actions in allowed.items():
            for action in ("start", "pause", "resume", "finish", "expire"):
                with self.subTest(status=status, action=action):
                    session = self.exam()
                    TestSession.objects.filter(pk=session.pk).update(
                        status=status,
                        paused_at=T0 if status == SessionStatus.PAUSED else None,
                        expires_at=T0 + HOUR if status != SessionStatus.CREATED else None,
                    )
                    session.refresh_from_db()
                    if action in ok_actions:
                        getattr(session, action)()
                    else:
                        with self.assertRaises(SessionTransitionError):
                            getattr(session, action)()
                        session.refresh_from_db()
                        self.assertEqual(session.status, status)

    def test_transitions_read_the_row_not_a_stale_instance(self):
        session = self.running_exam()
        stale = TestSession.objects.get(pk=session.pk)
        session.finish()
        with self.assertRaises(SessionTransitionError):
            stale.pause()
        self.assertEqual(stale.status, SessionStatus.FINISHED)


class ExtendTests(SessionStateFixture):
    def test_extend_before_start_grows_the_duration(self):
        session = self.exam()
        session.extend(timedelta(minutes=15))
        self.assertEqual(session.duration, timedelta(minutes=75))
        self.assertIsNone(session.expires_at)
        session.start()
        self.assertEqual(session.expires_at, T0 + timedelta(minutes=75))

    def test_extend_running_session(self):
        session = self.running_exam()
        self.advance(timedelta(minutes=50))
        session.extend(timedelta(minutes=20))
        self.assertEqual(session.expires_at, T0 + HOUR + timedelta(minutes=20))
        self.assertEqual(session.duration, HOUR + timedelta(minutes=20))
        self.assertEqual(session.remaining_time, timedelta(minutes=30))

    def test_extend_paused_session_then_resume(self):
        session = self.running_exam()
        self.advance(timedelta(minutes=40))
        session.pause()
        session.extend(timedelta(minutes=10))
        self.assertEqual(session.status, SessionStatus.PAUSED)
        self.assertEqual(session.remaining_time, timedelta(minutes=30))
        self.advance(HOUR)
        session.resume()
        self.assertEqual(session.remaining_time, timedelta(minutes=30))

    def test_extend_after_pause_and_resume(self):
        session = self.running_exam()
        session.pause()
        self.advance(timedelta(minutes=30))
        session.resume()
        session.extend(timedelta(minutes=5))
        self.assertEqual(session.remaining_time, timedelta(minutes=65))

    def test_cannot_extend_a_finished_session(self):
        session = self.running_exam()
        session.finish()
        with self.assertRaises(SessionTransitionError):
            session.extend(timedelta(minutes=10))
        self.assertEqual(session.status, SessionStatus.FINISHED)

    def test_cannot_extend_a_stored_expired_session(self):
        session = self.running_exam()
        self.advance(HOUR)
        session.expire()
        with self.assertRaises(SessionTransitionError):
            session.extend(timedelta(minutes=10))
        self.assertEqual(session.expires_at, T0 + HOUR)

    def test_cannot_revive_a_running_session_past_its_deadline(self):
        session = self.running_exam()
        self.advance(HOUR + timedelta(minutes=1))
        with self.assertRaises(SessionTransitionError):
            session.extend(timedelta(minutes=30))
        self.assertEqual(session.status, SessionStatus.EXPIRED)
        self.assertEqual(session.expires_at, T0 + HOUR)

    def test_extend_rejects_bad_deltas(self):
        session = self.running_exam()
        for delta in (timedelta(0), timedelta(minutes=-5), timedelta(hours=13), 10):
            with self.subTest(delta=delta), self.assertRaises(SessionTransitionError):
                session.extend(delta)
        session.refresh_from_db()
        self.assertEqual(session.expires_at, T0 + HOUR)

    def test_cannot_extend_training(self):
        session = self.make_session(group=self.group, session_type=SessionType.TRAINING)
        session.start()
        with self.assertRaises(SessionTransitionError):
            session.extend(timedelta(minutes=10))


class TrainingAndLegacyTests(SessionStateFixture):
    def test_training_has_no_deadline(self):
        session = self.make_session(group=self.group, session_type=SessionType.TRAINING)
        session.start()
        self.advance(24 * HOUR)
        self.assertEqual(session.effective_status, SessionStatus.RUNNING)
        self.assertIsNone(session.remaining_time)
        self.assertTrue(session.accepts_answers)
        session.finish()
        self.assertEqual(session.status, SessionStatus.FINISHED)

    def test_legacy_training_with_old_ttl_does_not_expire(self):
        session = self.make_session(session_type=SessionType.TRAINING, expires_at=T0 - HOUR)
        self.assertEqual(session.effective_status, SessionStatus.CREATED)
        session.start()
        self.assertTrue(session.accepts_answers)

    def test_legacy_exam_keeps_its_old_deadline_on_start(self):
        session = self.make_session(expires_at=T0 + timedelta(minutes=30))  # no duration
        session.start()
        self.assertEqual(session.expires_at, T0 + timedelta(minutes=30))
        self.assertTrue(session.accepts_answers)

    def test_legacy_exam_past_its_ttl_is_expired(self):
        session = self.make_session(expires_at=T0 - timedelta(minutes=1))
        self.assertEqual(session.effective_status, SessionStatus.EXPIRED)
        with self.assertRaises(SessionTransitionError):
            session.start()
        self.assertEqual(session.status, SessionStatus.EXPIRED)
        self.assertFalse(session.is_active)


class SessionValidationTests(SessionStateFixture):
    def test_new_exam_requires_a_duration(self):
        session = TestSession(test=self.test, group=self.group)
        with self.assertRaises(ValidationError) as ctx:
            session.full_clean(exclude=["key"])
        self.assertIn("duration", ctx.exception.message_dict)

    def test_duration_bounds(self):
        for duration in (timedelta(hours=13), timedelta(0)):
            with self.subTest(duration=duration):
                session = TestSession(test=self.test, group=self.group, duration=duration)
                with self.assertRaises(ValidationError):
                    session.full_clean(exclude=["key"])

    def test_training_takes_no_duration(self):
        session = TestSession(test=self.test, session_type=SessionType.TRAINING, duration=HOUR)
        with self.assertRaises(ValidationError) as ctx:
            session.full_clean(exclude=["key"])
        self.assertIn("duration", ctx.exception.message_dict)

    def test_db_rejects_paused_without_paused_at(self):
        session = self.running_exam()
        with self.assertRaises(IntegrityError), transaction.atomic():
            TestSession.objects.filter(pk=session.pk).update(status=SessionStatus.PAUSED, paused_at=None)

    def test_db_rejects_non_positive_duration(self):
        session = self.exam()
        with self.assertRaises(IntegrityError), transaction.atomic():
            TestSession.objects.filter(pk=session.pk).update(duration=timedelta(0))


class SessionKeyTests(SessionStateFixture):
    def test_key_is_short_and_prefixed_by_subject(self):
        self.test.subject = Subject.objects.get_or_create(name="HTML")[0]
        self.test.save()
        session = self.exam()
        self.assertRegex(session.key, KEY_RE)
        self.assertTrue(session.key.startswith("HT-"))

    def test_prefix_falls_back_to_title_then_default(self):
        self.assertEqual(session_key_prefix("", "Python Basics"), "PY")
        self.assertEqual(session_key_prefix("Кибер", "Основы"), "OK")
        cyrillic = Test.objects.create(title="Основы безопасности")
        self.assertTrue(self.make_session(test=cyrillic, duration=HOUR).key.startswith("OK-"))

    def test_keys_are_unique_and_normalized(self):
        keys = {self.exam().key for _ in range(30)}
        self.assertEqual(len(keys), 30)
        self.assertEqual(normalize_session_key("  py-82x91 "), "PY-82X91")
        self.assertEqual(self.exam(key="py-abcde").key, "PY-ABCDE")

    def test_legacy_mixed_case_key_is_never_rewritten(self):
        session = self.make_session(expires_at=T0 + HOUR)
        TestSession.objects.filter(pk=session.pk).update(key="aB3_xYz-legacy")
        session.refresh_from_db()
        session.start()
        session.pause()
        session.refresh_from_db()
        self.assertEqual(session.key, "aB3_xYz-legacy")

    def test_key_collision_is_retried(self):
        taken = self.exam().key
        with mock.patch("apps.testing.models.generate_session_key", side_effect=[taken, "PY-ZZZZZ"]):
            session = self.exam()
        self.assertEqual(session.key, "PY-ZZZZZ")


class ReviewAndAnswerStateTests(SessionStateFixture):
    def setUp(self):
        super().setUp()
        self.session = self.running_exam()
        self.attempt = StudentAttempt.objects.create(session=self.session, student=self.student)
        self.question = Question.objects.create(test=self.test, text="Explain a loop", question_type="text")

    def test_review_is_computed_from_grading_statuses(self):
        answer = Answer.objects.create(attempt=self.attempt, question=self.question, grading_status=GradingStatus.AUTO)
        self.assertFalse(self.session.needs_review)
        for status in (GradingStatus.PENDING, GradingStatus.PROCESSING, GradingStatus.FAILED):
            with self.subTest(status=status):
                Answer.objects.filter(pk=answer.pk).update(grading_status=status)
                self.assertTrue(self.session.needs_review)
                self.assertTrue(self.attempt.needs_review)
        for status in (GradingStatus.DONE, GradingStatus.MANUAL, GradingStatus.AI):
            with self.subTest(status=status):
                Answer.objects.filter(pk=answer.pk).update(grading_status=status)
                self.assertFalse(self.session.needs_review)

    def test_attempt_can_answer_only_while_session_runs(self):
        self.assertTrue(self.attempt.can_answer)
        self.session.pause()
        self.attempt.refresh_from_db()
        self.assertFalse(self.attempt.can_answer)
        self.session.resume()
        self.attempt.refresh_from_db()
        self.assertTrue(self.attempt.can_answer)
        self.advance(2 * HOUR)
        self.assertFalse(self.attempt.can_answer)

    def test_finished_attempt_cannot_answer(self):
        self.attempt.status = AttemptStatus.FINISHED
        self.assertFalse(self.attempt.can_answer)


class TestSubjectTests(SessionStateFixture):
    def test_subject_is_optional_and_set_null_on_delete(self):
        self.assertIsNone(self.test.subject)
        html = Subject.objects.create(name="HTML")
        self.test.subject = html
        self.test.save()
        self.assertEqual(list(html.tests.all()), [self.test])
        html.delete()
        self.test.refresh_from_db()
        self.assertIsNone(self.test.subject)
