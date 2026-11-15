"""Educational month and lesson — «3 месяц · 5 урок».

The fixture is the real shape of the data: ONE shared course plan whose rows
interleave IT, Soft Skills and English (row 1 IT, 2 Soft, 3 English, 4 IT…),
so IT lesson 29 is plan row 85. The month must come from the lesson's place
in its own subject (29 → 3 месяц · 5 урок at 12 per month), never from the
course-wide row number (85 → «8 месяц · 1 урок», the old bug)."""
from __future__ import annotations

import datetime as dt
from importlib import import_module

from django.apps import apps as django_apps
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import (
    Attendance,
    Course,
    CourseLessonPlan,
    Group,
    GroupTeacher,
    GroupTeacherLessonPlan,
    Homework,
    Lesson,
    Student,
)
from apps.users.models import Subject, Teacher, User

from . import numbering
from .models import CurriculumMonth, GroupLessonNumbering, NumberingFreeze, ProgramCurriculum

TODAY = timezone.localdate()
BASE = "/api/v1/academic-progress"
PER_SUBJECT = 72


def make_user(username, role) -> User:
    return User.objects.create_user(username=username, email=f"{username}@x.kg", password="x", role=role, is_verified=True)


class FormulaTests(TestCase):
    def test_12_and_20_boundaries(self):
        for n, expected in {1: (1, 1), 12: (1, 12), 13: (2, 1), 24: (2, 12), 25: (3, 1), 29: (3, 5)}.items():
            self.assertEqual(numbering.split(n, 12), expected, n)
        for n, expected in {1: (1, 1), 20: (1, 20), 21: (2, 1), 40: (2, 20), 41: (3, 1)}.items():
            self.assertEqual(numbering.split(n, 20), expected, n)

    def test_labels_in_three_languages(self):
        self.assertEqual(numbering.label(3, 5), "3 месяц · 5 урок")
        self.assertEqual(numbering.label(3, 5, "ky"), "3-ай · 5-сабак")
        self.assertEqual(numbering.label(3, 5, "en"), "Month 3 · Lesson 5")


class CurriculumBase(TestCase):
    def setUp(self):
        self.it, _ = Subject.objects.get_or_create(name="IT")
        self.soft, _ = Subject.objects.get_or_create(name="Soft Skills")
        self.english, _ = Subject.objects.get_or_create(name="English")
        self.course = Course.objects.create(name="NEXT", count_lesson=PER_SUBJECT * 3)
        self.course.subjects.set([self.it, self.soft, self.english])
        # The interleaved shared plan: IT k = row 3k-2, Soft k = 3k-1, English k = 3k.
        self.rows = {}
        for k in range(1, PER_SUBJECT + 1):
            for offset, subject in enumerate((self.it, self.soft, self.english)):
                row = CourseLessonPlan.objects.create(course=self.course, lesson_number=3 * (k - 1) + offset + 1,
                                                      subject=subject, topic=f"{subject.name} {k}")
                self.rows[(subject.pk, k)] = row
        self.teacher = Teacher.objects.create(user=make_user("islam", User.Role.TEACHER))
        self.group = Group.objects.create(name="NEXT-1", course=self.course, start_date=TODAY - dt.timedelta(days=200))
        self.programs = {s.pk: GroupTeacher.objects.create(group=self.group, teacher=self.teacher, subject=s)
                         for s in (self.it, self.soft, self.english)}
        self.slot = 0

    def lesson(self, subject, k, *, held=False, status=None, **extra):
        """Lesson k of a subject, generated from its shared plan row (as the generator does)."""
        row = self.rows[(subject.pk, k)]
        self.slot += 1
        date = TODAY - dt.timedelta(days=400 - self.slot) if held else TODAY + dt.timedelta(days=self.slot)
        fields = dict(group=self.group, group_teacher=self.programs[subject.pk], plan=row, teacher=self.teacher,
                      subject=subject, lesson_number=row.lesson_number, date=date,
                      start_time=dt.time(8 + self.slot % 10), end_time=dt.time(9 + self.slot % 10),
                      status=status or (Lesson.Status.COMPLETED if held else Lesson.Status.SCHEDULED))
        fields.update(extra)
        return Lesson.objects.create(**fields)

    def at(self, lesson):
        data = numbering.Numbering().of(lesson)
        return None if data is None else (data["month"], data["lesson"])

    def curriculum(self, per_month=12, months=6, main=None) -> ProgramCurriculum:
        return ProgramCurriculum.objects.create(course=self.course, lessons_per_month=per_month, duration_months=months,
                                                main_subject=main or self.it)


class SubjectSequenceTests(CurriculumBase):
    def test_lesson_29_of_it_is_month_3_lesson_5_not_month_8(self):
        lesson = self.lesson(self.it, 29)
        self.assertEqual(lesson.lesson_number, 85)            # course-wide plan row
        data = numbering.Numbering().of(lesson)
        self.assertEqual((data["month"], data["lesson"], data["number"]), (3, 5, 29))
        self.assertEqual(data["label"], "3 месяц · 5 урок")
        self.assertEqual(data["labels"], {"ru": "3 месяц · 5 урок", "ky": "3-ай · 5-сабак", "en": "Month 3 · Lesson 5"})

    def test_subjects_never_mix(self):
        it, soft, en = self.lesson(self.it, 29), self.lesson(self.soft, 29), self.lesson(self.english, 1)
        self.assertEqual(self.at(it), (3, 5))
        self.assertEqual(self.at(soft), (3, 5))                # row 86, its own sequence
        self.assertEqual(self.at(en), (1, 1))                  # row 3: English starts at its own lesson 1

    def test_12_per_month_boundaries_per_subject(self):
        self.curriculum(12)
        for subject in (self.it, self.english):
            self.assertEqual(self.at(self.lesson(subject, 12)), (1, 12))
            self.assertEqual(self.at(self.lesson(subject, 13)), (2, 1))

    def test_20_per_month_boundaries_per_subject(self):
        self.curriculum(20)
        for subject in (self.it, self.soft):
            self.assertEqual(self.at(self.lesson(subject, 20)), (1, 20))
            self.assertEqual(self.at(self.lesson(subject, 21)), (2, 1))
            self.assertEqual(self.at(self.lesson(subject, 41)), (3, 1))

    def test_group_setting_over_program(self):
        self.curriculum(12)
        GroupLessonNumbering.objects.create(group=self.group, lessons_per_month=20)
        self.assertEqual(self.at(self.lesson(self.english, 13)), (1, 13))
        self.assertEqual(self.at(self.lesson(self.it, 21)), (2, 1))

    def test_cancelled_lesson_and_make_up_keep_their_place(self):
        original = self.lesson(self.it, 13, status=Lesson.Status.CANCELLED)
        makeup = self.lesson(self.it, 13, rescheduled_from=original)
        nxt = self.lesson(self.it, 14)
        self.assertEqual((self.at(original), self.at(makeup), self.at(nxt)), ((2, 1), (2, 1), (2, 2)))

    def test_programs_own_plan(self):
        program = self.programs[self.english.pk]
        own = [GroupTeacherLessonPlan.objects.create(group_teacher=program, lesson_number=n, topic=f"Unit {n}")
               for n in range(1, 15)]
        lesson = Lesson.objects.create(group=self.group, group_teacher=program, individual_plan=own[12], teacher=self.teacher,
                                       subject=self.english, lesson_number=13, date=TODAY, start_time=dt.time(18),
                                       end_time=dt.time(19))
        self.assertEqual(self.at(lesson), (2, 1))

    def test_without_a_plan_link_the_plan_row_of_the_same_subject_is_used(self):
        lesson = self.lesson(self.it, 29)
        Lesson.objects.filter(pk=lesson.pk).update(plan=None)   # the plan row was deleted (SET_NULL)
        lesson.refresh_from_db()
        self.assertEqual(self.at(lesson), (3, 5))

    def test_nothing_is_invented_without_curriculum_information(self):
        stray = Lesson.objects.create(group=self.group, group_teacher=self.programs[self.it.pk], teacher=self.teacher,
                                      subject=self.it, lesson_number=999, date=TODAY, start_time=dt.time(20),
                                      end_time=dt.time(21))
        self.assertIsNone(numbering.Numbering().of(stray))


class CurriculumMonthsTests(CurriculumBase):
    def test_study_months_with_their_own_subject_and_size(self):
        react, _ = Subject.objects.get_or_create(name="React")
        curriculum = self.curriculum(12, months=6)
        CurriculumMonth.objects.create(curriculum=curriculum, number=2, planned_lessons=10)
        for n in (4, 5, 6):
            CurriculumMonth.objects.create(curriculum=curriculum, number=n, subject=react)
        # IT: month 1 = 12, month 2 = 10, month 3 = 12 → IT lesson 23 opens month 3.
        self.assertEqual(self.at(self.lesson(self.it, 22)), (2, 10))
        self.assertEqual(self.at(self.lesson(self.it, 23)), (3, 1))
        # React's own lessons start in the curriculum's month 4.
        react_program = GroupTeacher.objects.create(group=self.group, teacher=self.teacher, subject=react)
        plan = [GroupTeacherLessonPlan.objects.create(group_teacher=react_program, lesson_number=n, topic=f"React {n}")
                for n in range(1, 6)]
        react_lesson = Lesson.objects.create(group=self.group, group_teacher=react_program, individual_plan=plan[4],
                                             teacher=self.teacher, subject=react, lesson_number=5, date=TODAY,
                                             start_time=dt.time(19), end_time=dt.time(20))
        self.assertEqual(self.at(react_lesson), (4, 5))
        # English is not a study-month subject: plain months of 12.
        self.assertEqual(self.at(self.lesson(self.english, 23)), (2, 11))


class HistoryTests(CurriculumBase):
    def test_changing_12_to_20_keeps_held_lessons(self):
        curriculum = self.curriculum(12)
        held = {k: self.lesson(self.it, k, held=True) for k in range(1, 31)}     # IT: 3 месяц · 6 урок
        future = {k: self.lesson(self.it, k) for k in range(31, 61)}
        english = {k: self.lesson(self.english, k) for k in range(1, 25)}      # nothing held yet
        before = {k: self.at(lesson) for k, lesson in held.items()}
        curriculum.lessons_per_month = 20
        curriculum.save()
        self.assertEqual({k: self.at(lesson) for k, lesson in held.items()}, before)
        self.assertEqual(self.at(future[36]), (3, 12))
        self.assertEqual(self.at(future[37]), (4, 1))
        self.assertEqual(self.at(future[56]), (4, 20))
        self.assertEqual(self.at(english[21]), (2, 1))                         # follows the new size
        # IT follows the study months: its months 1–3 are kept, as months of 12.
        rows = list(NumberingFreeze.objects.order_by("first_lesson").values_list("subject_id", "first_lesson", "last_lesson",
                                                                                   "first_month", "lessons_per_month"))
        self.assertEqual(rows, [(self.it.pk, 1, 12, 1, 12), (self.it.pk, 13, 24, 2, 12), (self.it.pk, 25, 36, 3, 12)])

    def test_api_change_of_study_months_keeps_the_past(self):
        self.curriculum(12)
        held = self.lesson(self.it, 15, held=True)                               # 2 месяц · 3 урок
        api = APIClient()
        api.force_authenticate(make_user("boss", User.Role.ADMIN))
        response = api.put(f"{BASE}/programs/{self.course.pk}/", {
            "lessons_per_month": 12, "duration_months": 6, "main_subject": self.it.pk, "extra_subjects": [],
            "count_mode": "main", "months": [{"number": 1, "planned_lessons": 20}],
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.at(held), (2, 3))
        self.assertEqual(self.at(self.lesson(self.it, 25)), (3, 1))
        # Without held lessons the new month 1 of 20 applies directly.
        other = Group.objects.create(name="NEXT-2", course=self.course, start_date=TODAY)
        gt = GroupTeacher.objects.create(group=other, teacher=self.teacher, subject=self.it)
        fresh = Lesson.objects.create(group=other, group_teacher=gt, plan=self.rows[(self.it.pk, 15)], teacher=self.teacher,
                                      subject=self.it, lesson_number=43, date=TODAY + dt.timedelta(days=5),
                                      start_time=dt.time(8), end_time=dt.time(9))
        self.assertEqual(self.at(fresh), (1, 15))

    def test_unrelated_edits_freeze_nothing(self):
        curriculum = self.curriculum(12)
        self.lesson(self.it, 5, held=True)
        curriculum.duration_months = 8
        curriculum.save()
        GroupLessonNumbering.objects.create(group=self.group, lessons_per_month=12)
        self.assertFalse(NumberingFreeze.objects.exists())

    def test_old_freezes_are_converted_to_subject_positions(self):
        migration = import_module("apps.academic_progress.migrations.0003_freeze_by_subject")
        for k in range(1, 31):
            self.lesson(self.it, k, held=True)
        # A first-version freeze: course-wide numbers 1–96 of the IT program, 12 per month.
        NumberingFreeze.objects.create(group_teacher=self.programs[self.it.pk], first_lesson=1, last_lesson=96,
                                       first_month=1, lessons_per_month=12)
        migration.to_subject_positions(django_apps, None)
        row = NumberingFreeze.objects.get()
        self.assertEqual((row.group_id, row.subject_id, row.first_lesson, row.last_lesson), (self.group.pk, self.it.pk, 1, 36))


class EverywhereTests(CurriculumBase):
    """The same «3 месяц · 5 урок» in every module."""

    def setUp(self):
        super().setUp()
        self.target = self.lesson(self.it, 29, held=True)
        self.student = Student.objects.create(first_name="Ali", last_name="Asanov", group=self.group,
                                              enrollment_date=TODAY - dt.timedelta(days=600))
        Attendance.objects.create(student=self.student, lesson=self.target, status=Attendance.Status.PRESENT)
        self.homework = Homework.objects.create(lesson=self.target, title="ДЗ")
        self.api = APIClient()
        self.admin = make_user("boss", User.Role.ADMIN)
        self.api.force_authenticate(self.admin)

    def check(self, data):
        self.assertEqual((data["month"], data["lesson"], data["label"]), (3, 5, "3 месяц · 5 урок"))

    def test_lessons_homework_attendance_api(self):
        self.check(self.api.get(f"/api/v1/lessons/{self.target.pk}/").data["numbering"])
        self.check(self.api.get(f"/api/v1/homework/{self.homework.pk}/").data["lesson_numbering"])

    def test_portal_assistant_matrix(self):
        from apps.assistant import records, selectors
        from apps.attendance_matrix import cells
        from apps.portal.services import data

        self.check(data.lesson_row(self.target, None, None)["numbering"])
        self.check(data.homework_row(self.homework, None, TODAY)["lesson"]["numbering"])
        self.check(records._lesson_head(self.target)["numbering"])
        self.check(selectors._lesson_row(self.target)["numbering"])
        self.check(cells.detail(self.admin, self.target, self.student)["lesson"]["numbering"])

    def test_one_request_reads_the_curriculum_once(self):
        for k in range(1, 40):
            self.lesson(self.soft, k)
        lessons = list(Lesson.objects.filter(group=self.group))
        token = numbering._current.set(numbering.Numbering())
        try:
            numbering.prime(lessons)
            numbering.of(lessons[0])
            with self.assertNumQueries(0):   # everything after the first lookup comes from the cache
                labels = [numbering.of(lesson)["label"] for lesson in lessons]
        finally:
            numbering._current.reset(token)
        self.assertIn("3 месяц · 3 урок", labels)
