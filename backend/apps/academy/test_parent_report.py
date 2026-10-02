"""«Мини-отчёт родителям» (services.parent_report, GET /lessons/{id}/parent-report/).

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt

from django.test import TestCase
from rest_framework.test import APIClient

from apps.academy.models import Attendance, Course, Group, GroupTeacher, Homework, HomeworkResult, Lesson, Student
from apps.academy.services.parent_report import ParentLessonReportService
from apps.users.models import Subject, Teacher, User

EXAMPLE = """Саламатсыздарбы, урматтуу ата-энелер! 🌟

Бүгүнкү сабакта окуучулар «Күчтүү жана коопсуз паролдор» темасын үйрөнүштү. 📚

👥 Сабакка катышкан окуучулар:
• Бекнур Абдыбеков
• Талант Аманжолов
• Эрбол Зулпукаров
• Айжамал Мурзабекова

🚫 Сабакка катышпаган окуучулар:
• Йасин Ибрахимов

❌ Үй тапшырмасын аткарбаган окуучулар:
• Эрбол Зулпукаров

📝 Кийинки үй тапшырмасы:

3 Strong Passwords — создать 3 уникальных безопасных пароля.

📚 Кийинки сабакта жаңы теманы улантабыз. Рахмат! 🌟"""


def make_teacher(username: str) -> Teacher:
    user = User.objects.create_user(
        username=username, email=f"{username}@okurmen.kg", password="Str0ngPassw0rd!",
        first_name=username.capitalize(), role=User.Role.TEACHER, is_verified=True,
    )
    return Teacher.objects.create(user=user)


class ParentReportTests(TestCase):
    def setUp(self):
        self.it = Subject.objects.get_or_create(name="IT")[0]
        course = Course.objects.create(name="Kids IT", count_lesson=20)
        course.subjects.set([self.it])
        self.teacher = make_teacher("aizhan")
        self.group = Group.objects.create(name="Kids 1", course=course, start_date=dt.date(2025, 1, 1))
        self.program = GroupTeacher.objects.create(group=self.group, teacher=self.teacher, subject=self.it)
        names = ["Бекнур Абдыбеков", "Талант Аманжолов", "Эрбол Зулпукаров", "Айжамал Мурзабекова", "Йасин Ибрахимов"]
        self.students = {}
        for full in names:
            first, last = full.split()
            self.students[first] = Student.objects.create(first_name=first, last_name=last, group=self.group)
        self.prev = self.lesson(1, dt.date(2025, 3, 3), topic="Интернет коопсуздугу", status=Lesson.Status.COMPLETED)
        self.today = self.lesson(2, dt.date(2025, 3, 5), topic="Күчтүү жана коопсуз паролдор", status=Lesson.Status.IN_PROGRESS)

    def lesson(self, number, date, **fields):
        return Lesson.objects.create(
            group=self.group, group_teacher=self.program, teacher=self.teacher, subject=self.it,
            lesson_number=number, date=date, start_time=dt.time(10), end_time=dt.time(11), **fields,
        )

    def mark(self, lesson, **statuses):
        for first, value in statuses.items():
            Attendance.objects.create(lesson=lesson, student=self.students[first], status=value)

    def grade(self, homework, **statuses):
        for first, value in statuses.items():
            HomeworkResult.objects.create(homework=homework, student=self.students[first], status=value)

    def full_example(self):
        self.mark(self.today, Бекнур="present", Талант="late", Эрбол="present", Айжамал="present", Йасин="absent")
        old = Homework.objects.create(lesson=self.prev, title="Безопасный браузер")
        self.grade(old, Бекнур="checked", Талант="submitted", Эрбол="not_submitted", Айжамал="late", Йасин="checked")
        Homework.objects.create(
            lesson=self.today, title="3 Strong Passwords", description="создать 3 уникальных безопасных пароля.",
        )

    def test_spec_example(self):
        self.full_example()
        report = ParentLessonReportService.generate(self.today.pk)
        self.assertEqual(report["message"], EXAMPLE)
        self.assertEqual(report["topic"], "Күчтүү жана коопсуз паролдор")
        self.assertEqual(report["absent_students"], ["Йасин Ибрахимов"])
        self.assertEqual(report["homework_not_completed"], ["Эрбол Зулпукаров"])
        self.assertEqual(report["homework_partial"], [])
        self.assertEqual(report["next_homework"], "3 Strong Passwords — создать 3 уникальных безопасных пароля.")
        self.assertEqual(report["homework_checked"]["lesson_id"], self.prev.pk)
        self.assertEqual(report["warnings"], [])

    def test_everyone_present_and_homework_done(self):
        self.mark(self.today, **{name: "present" for name in self.students})
        old = Homework.objects.create(lesson=self.prev, title="ДЗ")
        self.grade(old, **{name: "checked" for name in self.students})
        message = ParentLessonReportService.generate(self.today.pk)["message"]
        self.assertNotIn("🚫", message)
        self.assertIn("❌ Үй тапшырмасын аткарбаган окуучулар:\nБаары аткарды ✅", message)
        self.assertIn("📝 Кийинки үй тапшырмасы:\n\nҮй тапшырмасы азырынча берилген жок.", message)

    def test_missing_data_is_never_invented(self):
        Lesson.objects.filter(pk=self.today.pk).update(topic="")
        report = ParentLessonReportService.generate(self.today.pk)
        message = report["message"]
        self.assertIn("⚠️ Тема занятия не указана.", message)
        self.assertIn("👥 Сабакка катышкан окуучулар:\n⚠️ Посещаемость не отмечена.", message)
        self.assertNotIn("❌", message)  # no homework was given at the previous lesson
        self.assertNotIn("Баары аткарды", message)
        self.assertIsNone(report["next_homework"])
        self.assertEqual(len(report["warnings"]), 2)

    def test_partly_graded_homework_is_not_reported_as_all_done(self):
        self.mark(self.today, **{name: "present" for name in self.students})
        old = Homework.objects.create(lesson=self.prev, title="ДЗ")
        self.grade(old, Бекнур="checked")
        report = ParentLessonReportService.generate(self.today.pk)
        self.assertIn("⚠️ Результаты ДЗ отмечены не у всех.", report["message"])
        self.assertNotIn("Баары аткарды", report["message"])
        self.assertTrue(any("не отмечены у 4" in w for w in report["warnings"]))

    def test_previous_lesson_skips_cancelled_and_other_programs(self):
        self.full_example()
        cancelled = self.lesson(3, dt.date(2025, 3, 4), status=Lesson.Status.CANCELLED)
        Homework.objects.create(lesson=cancelled, title="Отменённое")
        other_program = GroupTeacher.objects.create(group=self.group, teacher=make_teacher("almaz"), subject=None)
        other = Lesson.objects.create(
            group=self.group, group_teacher=other_program, lesson_number=1, date=dt.date(2025, 3, 4),
            start_time=dt.time(10), end_time=dt.time(11),
        )
        Homework.objects.create(lesson=other, title="Чужой предмет")
        report = ParentLessonReportService.generate(self.today.pk)
        self.assertEqual(report["homework_checked"]["title"], "Безопасный браузер")

    def test_no_technical_data_in_the_message(self):
        self.full_example()
        message = ParentLessonReportService.generate(self.today.pk)["message"]
        for student in self.students.values():
            self.assertNotIn(f"#{student.pk}", message)
        self.assertNotIn("@", message)
        self.assertNotIn("%", message)

    def test_api(self):
        self.full_example()
        url = f"/api/v1/lessons/{self.today.pk}/parent-report/"
        client = APIClient()
        client.force_authenticate(self.teacher.user)
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], EXAMPLE)

        stranger = APIClient()
        stranger.force_authenticate(make_teacher("other").user)
        self.assertEqual(stranger.get(url).status_code, 404)
        self.assertEqual(APIClient().get(url).status_code, 401)

        scheduled = self.lesson(4, dt.date(2025, 3, 10))
        self.assertEqual(client.get(f"/api/v1/lessons/{scheduled.pk}/parent-report/").status_code, 400)
