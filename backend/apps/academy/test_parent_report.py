"""«Мини-отчёт родителям» (services.parent_report, GET /lessons/{id}/parent-report/).

Lesson N's report uses Homework N (the homework of that same lesson) for
«не выполнили», and the program's next lesson's homework for «Кийинки үй
тапшырмасы».

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

📚 Бүгүнкү сабакта окуучулар «Күчтүү жана коопсуз паролдор» темасын үйрөнүштү.

👥 Сабакка катышкан окуучулар:
• Бекнур Абдыбеков
• Талант Аманжолов
• Эрбол Зулпукаров
• Айжамал Мурзабекова

🚫 Сабакка катышпаган окуучулар:
• Йасин Ибрахимов

❌ Үй тапшырмасын аткарбаган окуучулар:
• Эрбол Зулпукаров

📚 Кийинки үй тапшырмасы:

3 Strong Passwords — создать 3 уникальных безопасных пароля.

📚 Кийинки сабакта жаңы теманы улантабыз. Рахмат! 🌟"""

TRAINER_EXAMPLE = """Саламатсыздарбы, урматтуу ата-энелер! 🌟

Бүгүнкү сабакта «Күчтүү жана коопсуз паролдор» темасын өттүк. 📚

👥 Сабакка катышкандар:
• Бекнур Абдыбеков
• Талант Аманжолов
• Эрбол Зулпукаров
• Айжамал Мурзабекова

🚫 Сабакка катышпагандар:
• Йасин Ибрахимов

❌ Үй тапшырмасын аткарбагандар:
• Эрбол Зулпукаров

📚 Кийинки үй тапшырмасы:
3 Strong Passwords — создать 3 уникальных безопасных пароля.

Рахмат! Кийинки сабакта жолугушабыз 🌟"""


def make_teacher(username: str) -> Teacher:
    user = User.objects.create_user(
        username=username, email=f"{username}@okurmen.kg", password="Str0ngPassw0rd!",
        first_name=username.capitalize(), role=User.Role.TEACHER, is_verified=True,
    )
    return Teacher.objects.create(user=user)


def not_done_block(message: str) -> str:
    return message.split("❌", 1)[1].split("\n\n")[0] if "❌" in message else ""


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
        self.next = self.lesson(3, dt.date(2025, 3, 7), topic="Фишинг", status=Lesson.Status.SCHEDULED)

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
        self.own = Homework.objects.create(lesson=self.today, title="Безопасный браузер")
        self.grade(self.own, Бекнур="checked", Талант="submitted", Эрбол="not_submitted", Айжамал="late", Йасин="checked")
        Homework.objects.create(
            lesson=self.next, title="3 Strong Passwords", description="создать 3 уникальных безопасных пароля.",
        )

    def test_spec_example(self):
        self.full_example()
        report = ParentLessonReportService.generate(self.today.pk)
        self.assertEqual(report["message"], EXAMPLE)
        self.assertEqual(report["messages"], {"system": EXAMPLE, "trainer": TRAINER_EXAMPLE})
        self.assertEqual(report["topic"], "Күчтүү жана коопсуз паролдор")
        self.assertEqual(report["absent_students"], ["Йасин Ибрахимов"])
        self.assertEqual(report["homework_not_completed"], ["Эрбол Зулпукаров"])
        self.assertEqual(report["homework_partial"], [])
        self.assertEqual(report["homework"], {"id": self.own.pk, "title": "Безопасный браузер", "description": ""})
        self.assertEqual(report["next_homework"], "3 Strong Passwords — создать 3 уникальных безопасных пароля.")
        self.assertEqual(report["next_homework_details"]["title"], "3 Strong Passwords")
        self.assertEqual(report["warnings"], [])

    def test_results_and_next_homework_are_two_different_homeworks(self):
        self.full_example()
        report = ParentLessonReportService.generate(self.today.pk)
        self.assertEqual(Homework.objects.get(pk=report["homework"]["id"]).lesson_id, self.today.pk)
        self.assertEqual(Homework.objects.get(pk=report["next_homework_details"]["id"]).lesson_id, self.next.pk)
        self.assertNotEqual(report["homework"]["id"], report["next_homework_details"]["id"])

    def test_previous_lessons_homework_is_never_used(self):
        """Spec test 16: Homework №4 has everyone «Не сдано», Homework №5 has 3 done —
        lesson №5's report must show 9, never 12."""
        for i in range(7):
            Student.objects.create(first_name=f"Окуучу{i}", last_name="Тест", group=self.group)
        roster = list(self.group.students.order_by("pk"))
        self.assertEqual(len(roster), 12)
        hw_prev = Homework.objects.create(lesson=self.prev, title="Homework №4")
        hw_own = Homework.objects.create(lesson=self.today, title="Homework №5")
        for s in roster:
            HomeworkResult.objects.create(homework=hw_prev, student=s)
        for i, s in enumerate(roster):
            HomeworkResult.objects.create(homework=hw_own, student=s, status="submitted" if i < 3 else "not_submitted")
        report = ParentLessonReportService.generate(self.today.pk)
        self.assertEqual(report["homework"]["id"], hw_own.pk)
        self.assertEqual(len(report["homework_not_completed"]), 9)
        self.assertEqual(not_done_block(report["message"]).count("• "), 9)

    def test_everyone_present_and_homework_done(self):
        self.mark(self.today, **{name: "present" for name in self.students})
        own = Homework.objects.create(lesson=self.today, title="ДЗ")
        self.grade(own, **{name: "checked" for name in self.students})
        messages = ParentLessonReportService.generate(self.today.pk)["messages"]
        for message in messages.values():
            self.assertNotIn("🚫", message)
            self.assertNotIn("❌", message)
        self.assertIn("✅ Үй тапшырмасын баары аткарды.", messages["system"])
        self.assertIn("✅ Үй тапшырмасын баары аткарды.", messages["trainer"])
        self.assertIn("📚 Кийинки үй тапшырмасы:\n\nҮй тапшырмасы азырынча берилген жок.", messages["system"])
        self.assertIn("📚 Кийинки үй тапшырмасы:\nҮй тапшырмасы азырынча берилген жок.", messages["trainer"])

    def test_missing_data_is_never_invented(self):
        Lesson.objects.filter(pk=self.today.pk).update(topic="")
        report = ParentLessonReportService.generate(self.today.pk)
        message = report["message"]
        self.assertIn("⚠️ Тема занятия не указана.", message)
        self.assertIn("👥 Сабакка катышкан окуучулар:\n⚠️ Посещаемость не отмечена.", message)
        self.assertNotIn("❌", message)  # this lesson has no homework
        self.assertNotIn("баары аткарды", message)
        trainer = report["messages"]["trainer"]
        self.assertIn("⚠️ Тема занятия не указана.", trainer)
        self.assertIn("👥 Сабакка катышкандар:\n⚠️ Посещаемость не отмечена.", trainer)
        self.assertIsNone(report["homework"])
        self.assertIsNone(report["next_homework"])
        self.assertEqual(len(report["warnings"]), 2)

    def test_partly_graded_homework_is_not_reported_as_all_done(self):
        self.mark(self.today, **{name: "present" for name in self.students})
        own = Homework.objects.create(lesson=self.today, title="ДЗ")
        self.grade(own, Бекнур="checked")
        report = ParentLessonReportService.generate(self.today.pk)
        for message in report["messages"].values():
            self.assertIn("⚠️ Результаты ДЗ отмечены не у всех.", message)
            self.assertNotIn("баары аткарды", message)
        self.assertTrue(any("не отмечены у 4" in w for w in report["warnings"]))

    def test_next_homework_skips_cancelled_and_other_programs(self):
        self.full_example()
        Lesson.objects.filter(pk=self.next.pk).update(lesson_number=4)
        cancelled = self.lesson(3, dt.date(2025, 3, 6), status=Lesson.Status.CANCELLED)
        Homework.objects.create(lesson=cancelled, title="Отменённое")
        other_program = GroupTeacher.objects.create(group=self.group, teacher=make_teacher("almaz"), subject=None)
        other = Lesson.objects.create(
            group=self.group, group_teacher=other_program, lesson_number=3, date=dt.date(2025, 3, 6),
            start_time=dt.time(10), end_time=dt.time(11),
        )
        Homework.objects.create(lesson=other, title="Чужой предмет")
        report = ParentLessonReportService.generate(self.today.pk)
        self.assertEqual(report["next_homework_details"]["title"], "3 Strong Passwords")

    def test_no_technical_data_in_the_message(self):
        self.full_example()
        for message in ParentLessonReportService.generate(self.today.pk)["messages"].values():
            for student in self.students.values():
                self.assertNotIn(f"#{student.pk}", message)
            self.assertNotIn("@", message)
            self.assertNotIn("%", message)

    def test_trainer_text_has_no_lesson_description(self):
        Lesson.objects.filter(pk=self.today.pk).update(description="Узун сабактын сүрөттөмөсү")
        self.full_example()
        report = ParentLessonReportService.generate(self.today.pk)
        self.assertNotIn("Узун сабактын сүрөттөмөсү", report["messages"]["trainer"])
        self.assertEqual(report["messages"]["trainer"], TRAINER_EXAMPLE)

    def test_building_the_report_changes_nothing(self):
        self.full_example()
        tables = (Lesson, Attendance, Homework, HomeworkResult, Student)
        before = [list(model.objects.order_by("pk").values()) for model in tables]
        ParentLessonReportService.generate(self.today.pk)
        self.assertEqual([list(model.objects.order_by("pk").values()) for model in tables], before)

    def test_api(self):
        self.full_example()
        url = f"/api/v1/lessons/{self.today.pk}/parent-report/"
        client = APIClient()
        client.force_authenticate(self.teacher.user)
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], EXAMPLE)
        self.assertEqual(response.json()["messages"]["trainer"], TRAINER_EXAMPLE)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["Pragma"], "no-cache")

        stranger = APIClient()
        stranger.force_authenticate(make_teacher("other").user)
        self.assertEqual(stranger.get(url).status_code, 404)
        self.assertEqual(APIClient().get(url).status_code, 401)

        scheduled = self.lesson(4, dt.date(2025, 3, 10))
        self.assertEqual(client.get(f"/api/v1/lessons/{scheduled.pk}/parent-report/").status_code, 400)

    def test_every_request_reflects_the_current_records(self):
        self.full_example()
        url = f"/api/v1/lessons/{self.today.pk}/parent-report/"
        client = APIClient()
        client.force_authenticate(self.teacher.user)
        Lesson.objects.filter(pk=self.today.pk).update(status=Lesson.Status.COMPLETED)
        self.assertEqual(client.get(url).json()["message"], EXAMPLE)

        Homework.objects.filter(lesson=self.next).update(title="5 Strong Passwords", description="")
        HomeworkResult.objects.filter(homework=self.own, student=self.students["Эрбол"]).update(status="checked", score=10)
        HomeworkResult.objects.filter(homework=self.own, student=self.students["Айжамал"]).update(status="not_submitted")
        Attendance.objects.filter(lesson=self.today, student=self.students["Йасин"]).update(status="present")

        report = client.get(url).json()
        self.assertEqual(report["next_homework"], "5 Strong Passwords")
        self.assertEqual(report["homework_not_completed"], ["Айжамал Мурзабекова"])
        self.assertEqual(report["absent_students"], [])
        for message in report["messages"].values():
            self.assertNotIn("3 Strong Passwords", message)
            self.assertNotIn("Эрбол", not_done_block(message))

    def test_inactive_students_are_not_listed(self):
        self.full_example()
        Student.objects.filter(pk=self.students["Эрбол"].pk).update(is_active=False)
        self.assertEqual(ParentLessonReportService.generate(self.today.pk)["homework_not_completed"], [])


class ParentReportLiveResultsTests(TestCase):
    """End to end through the same endpoints the LMS screens use: grade this
    lesson's homework (POST /homework/{id}/results/) → GET the report."""

    lesson = ParentReportTests.lesson

    def setUp(self):
        ParentReportTests.setUp(self)
        for i in range(7):
            Student.objects.create(first_name=f"Окуучу{i}", last_name="Тест", group=self.group)
        self.roster = list(self.group.students.filter(is_active=True).order_by("pk"))
        Lesson.objects.filter(pk=self.today.pk).update(status=Lesson.Status.COMPLETED)
        self.own = Homework.objects.create(lesson=self.today, title="Сверстать блоки карточек")
        for s in self.roster:
            HomeworkResult.objects.create(homework=self.own, student=s)  # «Не сдано»
        self.client = APIClient()
        self.client.force_authenticate(self.teacher.user)

    def save(self, *items, homework=None):
        homework = homework or self.own
        response = self.client.post(f"/api/v1/homework/{homework.pk}/results/", list(items), format="json")
        self.assertEqual(response.status_code, 200, response.content)

    def report(self, lesson=None):
        lesson = lesson or self.today
        return self.client.get(f"/api/v1/lessons/{lesson.pk}/parent-report/").json()

    def test_spec_15_twelve_not_submitted_three_saved_nine_left(self):
        self.assertEqual(len(self.roster), 12)
        report = self.report()
        self.assertEqual(report["homework"]["id"], self.own.pk)
        self.assertEqual(len(report["homework_not_completed"]), 12)

        self.save(*({"student": s.pk, "status": "submitted"} for s in self.roster[:3]))

        rows = dict(HomeworkResult.objects.filter(homework=self.own).values_list("student_id", "status"))
        self.assertEqual([rows[s.pk] for s in self.roster[:3]], ["submitted"] * 3)
        self.assertEqual(sum(1 for v in rows.values() if v == "not_submitted"), 9)

        report = self.report()
        self.assertEqual(len(report["homework_not_completed"]), 9)
        for message in report["messages"].values():
            self.assertEqual(not_done_block(message).count("• "), 9)

    def test_five_of_twelve_submitted_leaves_seven(self):
        self.save(*({"student": s.pk, "status": "submitted"} for s in self.roster[:5]))
        self.assertEqual(len(self.report()["homework_not_completed"]), 7)

    def test_submitted_late_and_checked_all_count_as_done(self):
        self.save(
            {"student": self.students["Бекнур"].pk, "status": "submitted", "score": 8},
            {"student": self.students["Талант"].pk, "status": "late", "score": 7},
            {"student": self.students["Эрбол"].pk, "status": "checked", "score": 10},
        )
        report = self.report()
        for name in ("Бекнур Абдыбеков", "Талант Аманжолов", "Эрбол Зулпукаров"):
            self.assertNotIn(name, report["homework_not_completed"])
            for message in report["messages"].values():
                self.assertNotIn(name, not_done_block(message))
        self.assertIn("Айжамал Мурзабекова", report["homework_not_completed"])

    def test_last_one_done_turns_into_all_done(self):
        self.save(*({"student": s.pk, "status": "submitted"} for s in self.roster if s != self.students["Эрбол"]))
        self.assertEqual(self.report()["homework_not_completed"], ["Эрбол Зулпукаров"])
        self.save({"student": self.students["Эрбол"].pk, "status": "submitted"})
        report = self.report()
        self.assertEqual(report["homework_not_completed"], [])
        self.assertIn("✅ Үй тапшырмасын баары аткарды.", report["message"])

    def test_score_changes_are_read_fresh(self):
        # The report format has no average/score aggregate — only the «не выполнили» list.
        self.save({"student": self.students["Эрбол"].pk, "status": "checked", "score": 2})
        self.save({"student": self.students["Эрбол"].pk, "status": "checked", "score": 10})
        self.assertEqual(HomeworkResult.objects.get(homework=self.own, student=self.students["Эрбол"]).score, 10)
        self.assertNotIn("Эрбол Зулпукаров", self.report()["homework_not_completed"])
        self.save({"student": self.students["Эрбол"].pk, "status": "not_submitted", "score": 2})
        self.assertIn("Эрбол Зулпукаров", self.report()["homework_not_completed"])

    def test_grading_another_lessons_homework_does_not_change_this_report(self):
        hw_prev = Homework.objects.create(lesson=self.prev, title="Homework №1")
        self.save(*({"student": s.pk, "status": "submitted"} for s in self.roster), homework=hw_prev)
        self.assertEqual(len(self.report()["homework_not_completed"]), 12)

    def test_historical_lesson_is_unaffected_by_later_lessons(self):
        Lesson.objects.filter(pk=self.prev.pk).update(status=Lesson.Status.COMPLETED)
        hw_prev = Homework.objects.create(lesson=self.prev, title="Homework №1")
        self.save(*({"student": s.pk, "status": "submitted"} for s in self.roster), homework=hw_prev)
        self.save(*({"student": s.pk, "status": "not_submitted"} for s in self.roster))
        earlier = self.report(self.prev)
        self.assertEqual(earlier["homework"]["id"], hw_prev.pk)
        self.assertEqual(earlier["homework_not_completed"], [])
        self.assertEqual(earlier["next_homework"], "Сверстать блоки карточек")
