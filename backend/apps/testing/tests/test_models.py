"""Model-level tests for the Testing module and its links to LMS entities.

Absolute imports only — see the note at the top of apps/academy/tests.py
(full test discovery imports modules under the `backend.` prefix too).
"""
from __future__ import annotations

import datetime as dt
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.academy.models import Course, Group, Lesson, Student
from apps.testing.models import (
    Answer,
    AttemptStatus,
    GradingStatus,
    Question,
    QuestionOption,
    QuestionType,
    SessionType,
    StudentAttempt,
    Test,
    TestSession,
)
from apps.testing.services.question_selector import TOTAL_QUESTIONS
from apps.users.models import Subject, Teacher, User


def make_teacher(username: str) -> Teacher:
    user = User.objects.create_user(
        username=username,
        email=f"{username}@okurmen.kg",
        password="Str0ngPassw0rd!",
        first_name=username.capitalize(),
        role=User.Role.TEACHER,
        is_verified=True,
    )
    return Teacher.objects.create(user=user)


class TestingFixture(TestCase):
    def setUp(self):
        self.subject = Subject.objects.get_or_create(name="Python")[0]
        self.teacher = make_teacher("tpython")
        self.course = Course.objects.create(name="Python Beginner", count_lesson=12)
        self.course.subjects.set([self.subject])
        self.group = Group.objects.create(name="Group 12", course=self.course, start_date=dt.date(2026, 9, 1))
        self.other_group = Group.objects.create(name="Group 13", course=self.course, start_date=dt.date(2026, 9, 1))
        self.lesson = self.make_lesson(self.group)
        self.student = Student.objects.create(first_name="Aibek", last_name="Asanov", group=self.group)
        self.test = Test.objects.create(title="Python Basics")

    def make_lesson(self, group, number=1) -> Lesson:
        return Lesson.objects.create(
            group=group, teacher=self.teacher, subject=self.subject, lesson_number=number,
            date=dt.date(2026, 9, 2), start_time=dt.time(10), end_time=dt.time(11),
        )

    def make_session(self, **fields) -> TestSession:
        fields.setdefault("test", self.test)
        return TestSession.objects.create(**fields)


class TestSessionLinksTests(TestingFixture):
    def test_session_links_to_group_lesson_and_teacher(self):
        session = self.make_session(group=self.group, lesson=self.lesson, teacher=self.teacher)
        session.full_clean()

        self.assertEqual(list(self.group.test_sessions.all()), [session])
        self.assertEqual(list(self.lesson.test_sessions.all()), [session])
        self.assertEqual(list(self.teacher.test_sessions.all()), [session])

    def test_legacy_session_without_lms_links_is_valid(self):
        session = self.make_session(title="Группа A, 01.04.2026")
        session.full_clean()
        self.assertIsNone(session.group)
        self.assertIsNone(session.lesson)
        self.assertIsNone(session.teacher)

    def test_session_without_lesson_is_valid(self):
        self.make_session(group=self.group).full_clean()

    def test_lesson_must_belong_to_the_session_group(self):
        foreign_lesson = self.make_lesson(self.other_group, number=2)
        session = self.make_session(group=self.group, lesson=foreign_lesson)
        with self.assertRaises(ValidationError) as ctx:
            session.full_clean()
        self.assertIn("lesson", ctx.exception.message_dict)

    def test_lesson_requires_a_group(self):
        session = self.make_session(lesson=self.lesson)
        with self.assertRaises(ValidationError) as ctx:
            session.full_clean()
        self.assertIn("group", ctx.exception.message_dict)

    def test_session_key_is_generated_and_unique(self):
        first, second = self.make_session(), self.make_session()
        self.assertTrue(first.key)
        self.assertNotEqual(first.key, second.key)


class DeletionKeepsHistoryTests(TestingFixture):
    """Deleting LMS entities is never blocked by, and never wipes, test history."""

    def setUp(self):
        super().setUp()
        self.session = self.make_session(group=self.group, lesson=self.lesson, teacher=self.teacher)
        self.attempt = StudentAttempt.objects.create(session=self.session, student=self.student)

    def test_deleting_lesson_keeps_session(self):
        self.lesson.delete()
        self.session.refresh_from_db()
        self.assertIsNone(self.session.lesson)
        self.assertEqual(self.session.group, self.group)

    def test_deleting_teacher_keeps_session(self):
        # A teacher with group assignments is already PROTECTed by academy
        # (GroupTeacher.teacher) — use one without, so only our FK is tested.
        creator = make_teacher("tcreator")
        session = self.make_session(group=self.group, teacher=creator)
        creator.delete()
        session.refresh_from_db()
        self.assertIsNone(session.teacher)

    def test_deleting_group_keeps_session_and_attempts(self):
        self.group.delete()
        self.session.refresh_from_db()
        self.assertIsNone(self.session.group)
        self.assertTrue(StudentAttempt.objects.filter(pk=self.attempt.pk).exists())

    def test_deleting_student_keeps_attempt_with_name_snapshot(self):
        self.student.delete()
        self.attempt.refresh_from_db()
        self.assertIsNone(self.attempt.student)
        self.assertEqual(self.attempt.student_name, "Aibek Asanov")


class StudentAttemptTests(TestingFixture):
    def setUp(self):
        super().setUp()
        self.session = self.make_session(group=self.group, max_attempts_per_student=1)

    def test_student_name_snapshot_is_filled_from_student(self):
        attempt = StudentAttempt.objects.create(session=self.session, student=self.student)
        self.assertEqual(attempt.student_name, "Aibek Asanov")
        self.assertEqual(list(self.student.test_attempts.all()), [attempt])

    def test_snapshot_survives_student_rename(self):
        attempt = StudentAttempt.objects.create(session=self.session, student=self.student)
        self.student.first_name = "Renamed"
        self.student.save()
        attempt.refresh_from_db()
        self.assertEqual(attempt.student_name, "Aibek Asanov")

    def test_explicit_student_name_is_kept(self):
        attempt = StudentAttempt.objects.create(session=self.session, student=self.student, student_name="Айбек")
        self.assertEqual(attempt.student_name, "Айбек")

    def test_legacy_attempt_without_student(self):
        attempt = StudentAttempt.objects.create(session=self.session, student_name="Typed Name")
        self.assertIsNone(attempt.student)
        self.assertEqual(attempt.student_name, "Typed Name")

    def test_attempt_limit_is_counted_per_lms_student(self):
        self.assertTrue(self.session.can_student_attempt(student=self.student))
        StudentAttempt.objects.create(session=self.session, student=self.student)
        self.assertFalse(self.session.can_student_attempt(student=self.student))
        # A different name no longer bypasses the limit for a linked student.
        self.assertFalse(self.session.can_student_attempt("Someone Else", student=self.student))

    def test_attempt_limit_by_name_for_legacy_attempts(self):
        StudentAttempt.objects.create(session=self.session, student_name="Typed Name")
        self.assertFalse(self.session.can_student_attempt("Typed Name"))
        self.assertTrue(self.session.can_student_attempt("Other Name"))

    def test_expired_attempts_do_not_count_toward_limit(self):
        attempt = StudentAttempt.objects.create(session=self.session, student=self.student)
        attempt.expire()
        self.assertEqual(attempt.status, AttemptStatus.EXPIRED)
        self.assertTrue(self.session.can_student_attempt(student=self.student))

    def test_training_session_has_no_limit(self):
        training = self.make_session(group=self.group, session_type=SessionType.TRAINING)
        StudentAttempt.objects.create(session=training, student=self.student)
        self.assertTrue(training.can_student_attempt(student=self.student))

    def test_finish_scores_correct_answers_out_of_total_questions(self):
        attempt = StudentAttempt.objects.create(session=self.session, student=self.student)
        right = Question.objects.create(test=self.test, text="2+2?")
        wrong = Question.objects.create(test=self.test, text="3+3?")
        pending = Question.objects.create(test=self.test, text="Explain", question_type=QuestionType.TEXT)
        QuestionOption.objects.create(question=right, text="4", is_correct=True)
        Answer.objects.create(attempt=attempt, question=right, is_correct=True, grading_status=GradingStatus.AUTO)
        Answer.objects.create(attempt=attempt, question=wrong, is_correct=False, grading_status=GradingStatus.AUTO)
        Answer.objects.create(attempt=attempt, question=pending)

        attempt.finish()

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, AttemptStatus.FINISHED)
        self.assertEqual(attempt.score, round(1 / TOTAL_QUESTIONS * 100, 2))
        with self.assertRaises(ValidationError):
            attempt.finish()


class SessionValidityTests(TestingFixture):
    def test_exam_expires_after_expires_at(self):
        session = self.make_session(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertFalse(session.is_valid)
        self.assertTrue(session.is_time_expired)

    def test_training_ignores_expires_at_and_survives_deactivate(self):
        session = self.make_session(session_type=SessionType.TRAINING, expires_at=timezone.now() - timedelta(minutes=1))
        self.assertTrue(session.is_valid)
        session.deactivate()
        self.assertTrue(session.is_active)

    def test_exam_deactivate(self):
        session = self.make_session()
        session.deactivate()
        self.assertFalse(session.is_active)


class QuestionTests(TestingFixture):
    def test_code_question_requires_language(self):
        question = Question(test=self.test, text="Write a loop", question_type=QuestionType.CODE)
        with self.assertRaises(ValidationError):
            question.full_clean()
        question.language = "python"
        question.full_clean()

    def test_auto_gradable_types(self):
        self.assertTrue(Question(question_type=QuestionType.SINGLE_CHOICE).is_auto_gradable)
        self.assertTrue(Question(question_type=QuestionType.MULTIPLE_CHOICE).is_auto_gradable)
        self.assertFalse(Question(question_type=QuestionType.TEXT).is_auto_gradable)
        self.assertFalse(Question(question_type=QuestionType.CODE).is_auto_gradable)
