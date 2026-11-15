"""Monthly lesson numbering «Месяц N · Урок K»: derived from the global
lesson_number with 12 or 20 lessons per educational month (group > program
> 12), boundaries, cancellations, no renumbering of held lessons when the
setting changes, the settings API, and the same numbers in every module."""
from __future__ import annotations

import datetime as dt

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import Attendance, Homework, Lesson, Student
from apps.users.models import User

from . import numbering
from .models import GroupLessonNumbering, NumberingFreeze, ProgramCurriculum
from .tests import BASE, Base, user

TODAY = timezone.localdate()


def pair(n: int, per_month: int) -> tuple[int, int]:
    return numbering.split(n, per_month)


class FormulaTests(TestCase):
    def test_12_lessons_per_month(self):
        cases = {1: (1, 1), 12: (1, 12), 13: (2, 1), 24: (2, 12), 25: (3, 1)}
        for n, expected in cases.items():
            self.assertEqual(pair(n, 12), expected, n)

    def test_20_lessons_per_month(self):
        cases = {1: (1, 1), 20: (1, 20), 21: (2, 1), 40: (2, 20), 41: (3, 1)}
        for n, expected in cases.items():
            self.assertEqual(pair(n, 20), expected, n)

    def test_matches_the_formula_everywhere(self):
        for per_month in (12, 20):
            for n in range(1, 400):
                self.assertEqual(pair(n, per_month), ((n - 1) // per_month + 1, (n - 1) % per_month + 1))

    def test_labels(self):
        self.assertEqual(numbering.label(2, 1), "Месяц 2 · Урок 1")
        self.assertEqual(numbering.label(2, 1, "ky"), "2-ай · 1-сабак")


class NumberingBase(Base):
    def future(self, count, *, gt=None, first_number=1, status=Lesson.Status.SCHEDULED):
        """Lessons that have not taken place yet (nothing to freeze)."""
        gt = gt or self.gt
        return [
            Lesson.objects.create(
                group=self.group, group_teacher=gt, teacher=self.teacher, subject=gt.subject, lesson_number=n,
                date=TODAY + dt.timedelta(days=30 + n), start_time=dt.time(16), end_time=dt.time(17), status=status,
            )
            for n in range(first_number, first_number + count)
        ]

    def held_until(self, last_number, *, gt=None):
        gt = gt or self.gt
        return [
            Lesson.objects.create(
                group=self.group, group_teacher=gt, teacher=self.teacher, subject=gt.subject, lesson_number=n,
                date=TODAY - dt.timedelta(days=last_number - n + 1), start_time=dt.time(16), end_time=dt.time(17),
                status=Lesson.Status.COMPLETED,
            )
            for n in range(1, last_number + 1)
        ]

    def at(self, lesson):
        data = numbering.of(lesson)
        return data["month"], data["lesson"]


class ConfigurationTests(NumberingBase):
    def test_without_settings_12_per_month(self):
        lessons = {lesson.lesson_number: lesson for lesson in self.future(25)}
        self.assertEqual(self.at(lessons[12]), (1, 12))
        self.assertEqual(self.at(lessons[13]), (2, 1))
        self.assertEqual(numbering.of(lessons[13])["label"], "Месяц 2 · Урок 1")

    def test_program_with_20(self):
        self.curriculum(20)
        lessons = {lesson.lesson_number: lesson for lesson in self.future(45)}
        self.assertEqual(self.at(lessons[20]), (1, 20))
        self.assertEqual(self.at(lessons[21]), (2, 1))
        self.assertEqual(self.at(lessons[40]), (2, 20))
        self.assertEqual(self.at(lessons[41]), (3, 1))
        self.assertEqual(numbering.of(lessons[41])["per_month"], 20)

    def test_group_setting_beats_the_program(self):
        self.curriculum(12)
        lessons = {lesson.lesson_number: lesson for lesson in self.future(25)}
        GroupLessonNumbering.objects.create(group=self.group, lessons_per_month=20)
        self.assertEqual(self.at(lessons[13]), (1, 13))
        self.assertEqual(self.at(lessons[21]), (2, 1))
        # Another group of the same program still uses the program's 12.
        other = self.group.__class__.objects.create(name="NEXT 2", course=self.course, start_date=TODAY)
        gt = other.teachers.create(teacher=self.teacher, subject=self.it)
        lesson = Lesson.objects.create(group=other, group_teacher=gt, teacher=self.teacher, subject=self.it, lesson_number=13,
                                       date=TODAY + dt.timedelta(days=40), start_time=dt.time(16), end_time=dt.time(17))
        self.assertEqual(self.at(lesson), (2, 1))

    def test_each_program_of_a_group_has_its_own_sequence(self):
        it = {lesson.lesson_number: lesson for lesson in self.future(14)}
        en = {lesson.lesson_number: lesson for lesson in self.future(3, gt=self.gt_en)}
        self.assertEqual(self.at(it[14]), (2, 2))
        self.assertEqual(self.at(en[3]), (1, 3))

    def test_progress_months_use_the_group_setting(self):
        self.curriculum(12)
        GroupLessonNumbering.objects.create(group=self.group, lessons_per_month=20)
        self.held(15)
        p = self.p()
        self.assertEqual((p["month"]["number"], p["month"]["planned"]), (1, 20))
        self.assertEqual(p["lessons_per_month_source"], "group")


class HistoryTests(NumberingBase):
    def test_cancelled_lesson_and_its_make_up_keep_the_same_number(self):
        lessons = {lesson.lesson_number: lesson for lesson in self.future(14)}
        Lesson.objects.filter(pk=lessons[13].pk).update(status=Lesson.Status.CANCELLED)
        makeup = Lesson.objects.create(group=self.group, group_teacher=self.gt, teacher=self.teacher, subject=self.it,
                                       lesson_number=13, date=TODAY + dt.timedelta(days=90), start_time=dt.time(16),
                                       end_time=dt.time(17), rescheduled_from=lessons[13])
        self.assertEqual(self.at(makeup), (2, 1))
        self.assertEqual(self.at(lessons[14]), (2, 2))  # nothing after it shifts

    def test_changing_12_to_20_never_renumbers_held_lessons(self):
        self.curriculum(12)
        held = {lesson.lesson_number: lesson for lesson in self.held_until(30)}          # month 3, lesson 6
        later = {lesson.lesson_number: lesson for lesson in self.future(30, first_number=31)}
        before = {n: self.at(lesson) for n, lesson in held.items()}

        curriculum = ProgramCurriculum.objects.get(course=self.course)
        curriculum.lessons_per_month = 20
        curriculum.save()

        self.assertEqual({n: self.at(lesson) for n, lesson in held.items()}, before)
        self.assertEqual(self.at(held[30]), (3, 6))
        self.assertEqual(self.at(later[36]), (3, 12))   # the started month is finished as it began
        self.assertEqual(self.at(later[37]), (4, 1))    # the new size from the next month
        self.assertEqual(self.at(later[56]), (4, 20))
        self.assertEqual(self.at(later[57]), (5, 1))
        freeze = NumberingFreeze.objects.get(group_teacher=self.gt)
        self.assertEqual((freeze.first_lesson, freeze.last_lesson, freeze.first_month, freeze.lessons_per_month), (1, 36, 1, 12))
        # A sequence with no lesson held yet simply follows the new setting.
        en = self.future(21, gt=self.gt_en)
        self.assertEqual(self.at(en[20]), (2, 1))

    def test_a_second_change_keeps_both_histories(self):
        self.curriculum(12)
        self.held_until(14)                              # month 2 started with 12
        GroupLessonNumbering.objects.create(group=self.group, lessons_per_month=20)
        self.assertEqual(NumberingFreeze.objects.get().last_lesson, 24)
        # 20 more lessons held → month 3 (lessons 25…44) under 20; then back to 12.
        for n in range(15, 31):
            Lesson.objects.create(group=self.group, group_teacher=self.gt, teacher=self.teacher, subject=self.it,
                                  lesson_number=n, date=TODAY, start_time=dt.time(8 + n % 10), end_time=dt.time(9 + n % 10),
                                  status=Lesson.Status.COMPLETED)
        row = GroupLessonNumbering.objects.get(group=self.group)
        row.delete()                                     # back to the program's 12
        lessons = {lesson.lesson_number: lesson for lesson in self.future(30, first_number=31)}
        self.assertEqual(self.at(Lesson.objects.get(group_teacher=self.gt, lesson_number=25)), (3, 1))
        self.assertEqual(self.at(lessons[44]), (3, 20))
        self.assertEqual(self.at(lessons[45]), (4, 1))
        self.assertEqual(self.at(lessons[57]), (5, 1))
        self.assertEqual(NumberingFreeze.objects.count(), 2)

    def test_same_value_or_unrelated_edit_freezes_nothing(self):
        curriculum = self.curriculum(12)
        self.held_until(5)
        curriculum.duration_months = 8
        curriculum.save()
        GroupLessonNumbering.objects.create(group=self.group, lessons_per_month=12)
        self.assertFalse(NumberingFreeze.objects.exists())


class ApiTests(NumberingBase):
    def setUp(self):
        super().setUp()
        self.admin = user("boss", User.Role.ADMIN)
        self.client_ = APIClient()
        self.client_.force_authenticate(self.admin)

    def program_put(self, per_month):
        return self.client_.put(f"{BASE}/programs/{self.course.pk}/", {
            "lessons_per_month": per_month, "duration_months": 6, "main_subject": self.it.pk,
            "extra_subjects": [], "count_mode": "main", "months": [],
        }, format="json")

    def test_program_accepts_only_12_or_20(self):
        self.assertEqual(self.program_put(15).status_code, 400)
        self.assertEqual(self.program_put(20).status_code, 200)
        self.assertEqual(ProgramCurriculum.objects.get(course=self.course).lessons_per_month, 20)
        self.assertEqual(self.client_.get(f"{BASE}/meta/").data["presets"], [12, 20])

    def test_a_legacy_value_may_stay_until_changed(self):
        ProgramCurriculum.objects.create(course=self.course, lessons_per_month=16, duration_months=6)
        self.assertEqual(self.program_put(16).status_code, 200)
        self.assertEqual(self.program_put(8).status_code, 400)

    def test_group_setting(self):
        url = f"{BASE}/groups/{self.group.pk}/numbering/"
        self.assertEqual(self.client_.put(url, {"lessons_per_month": 13}, format="json").status_code, 400)
        data = self.client_.put(url, {"lessons_per_month": 20}, format="json").data
        self.assertEqual((data["numbering"]["lessons_per_month"], data["numbering"]["group_value"]), (20, 20))
        data = self.client_.put(url, {"lessons_per_month": None}, format="json").data
        self.assertEqual((data["numbering"]["lessons_per_month"], data["numbering"]["group_value"]), (12, None))
        teacher = APIClient()
        teacher.force_authenticate(self.teacher.user)
        self.assertIn(teacher.put(url, {"lessons_per_month": 20}, format="json").status_code, (403, 404))
        self.assertFalse(GroupLessonNumbering.objects.exists())


class ConsistencyTests(NumberingBase):
    """The same «Месяц · Урок» wherever the lesson appears."""

    def setUp(self):
        super().setUp()
        self.curriculum(20)
        self.lessons = {lesson.lesson_number: lesson for lesson in self.held_until(21)}
        self.lesson = self.lessons[21]
        self.student = Student.objects.create(first_name="Ali", last_name="Asanov", group=self.group,
                                              enrollment_date=TODAY - dt.timedelta(days=60))
        Attendance.objects.create(student=self.student, lesson=self.lesson, status=Attendance.Status.PRESENT)
        self.homework = Homework.objects.create(lesson=self.lesson, title="ДЗ")
        self.admin = user("boss", User.Role.ADMIN)
        self.api = APIClient()
        self.api.force_authenticate(self.admin)
        self.expected = {"number": 21, "month": 2, "lesson": 1, "per_month": 20, "label": "Месяц 2 · Урок 1"}

    def test_lesson_homework_and_attendance_api(self):
        self.assertEqual(self.api.get(f"/api/v1/lessons/{self.lesson.pk}/").data["numbering"], self.expected)
        lessons = self.api.get("/api/v1/lessons/", {"group": self.group.pk, "ordering": "-lesson_number"}).data
        rows = lessons["results"] if isinstance(lessons, dict) else lessons
        by_id = {row["id"]: row["numbering"] for row in rows}
        self.assertEqual(by_id[self.lesson.pk], self.expected)
        self.assertEqual(by_id[self.lessons[20].pk]["label"], "Месяц 1 · Урок 20")
        hw = self.api.get(f"/api/v1/homework/{self.homework.pk}/")
        self.assertEqual(hw.data["lesson_numbering"], self.expected)

    def test_student_portal_and_reports_services(self):
        from apps.portal.services import data

        row = data.lesson_row(self.lesson, None, None)
        self.assertEqual(row["numbering"], self.expected)
        hw_row = data.homework_row(self.homework, None, TODAY)
        self.assertEqual(hw_row["lesson"]["numbering"], self.expected)

    def test_attendance_matrix_and_assistant(self):
        from apps.assistant import records, selectors

        self.assertEqual(records._lesson_head(self.lesson)["numbering"], self.expected)
        self.assertEqual(selectors._lesson_row(self.lesson)["numbering"], self.expected)
        from apps.attendance_matrix import cells

        self.assertEqual(cells.detail(self.admin, self.lesson, self.student)["lesson"]["numbering"], self.expected)

    def test_one_request_reads_settings_once(self):
        for n in range(22, 60):
            Lesson.objects.create(group=self.group, group_teacher=self.gt, teacher=self.teacher, subject=self.it,
                                  lesson_number=n, date=TODAY + dt.timedelta(days=n), start_time=dt.time(16),
                                  end_time=dt.time(17))
        token = numbering._current.set(numbering.Numbering())
        try:
            lessons = list(Lesson.objects.filter(group=self.group))
            numbering.prime(lessons)
            with self.assertNumQueries(0):
                labels = [numbering.of(lesson)["label"] for lesson in lessons]
        finally:
            numbering._current.reset(token)
        self.assertIn("Месяц 3 · Урок 19", labels)
