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

❌ Өткөн сабактын үй тапшырмасын аткарбагандар:
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
        self.assertEqual(report["messages"], {"system": EXAMPLE, "trainer": TRAINER_EXAMPLE})
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
        messages = ParentLessonReportService.generate(self.today.pk)["messages"]
        for message in messages.values():
            self.assertNotIn("🚫", message)
            self.assertNotIn("❌", message)
        self.assertIn("✅ Үй тапшырмасын баары аткарды.", messages["system"])
        self.assertIn("✅ Өткөн сабактын үй тапшырмасын баары аткарды.", messages["trainer"])
        self.assertIn("📚 Кийинки үй тапшырмасы:\n\nҮй тапшырмасы азырынча берилген жок.", messages["system"])
        self.assertIn("📚 Кийинки үй тапшырмасы:\nҮй тапшырмасы азырынча берилген жок.", messages["trainer"])

    def test_missing_data_is_never_invented(self):
        Lesson.objects.filter(pk=self.today.pk).update(topic="")
        report = ParentLessonReportService.generate(self.today.pk)
        message = report["message"]
        self.assertIn("⚠️ Тема занятия не указана.", message)
        self.assertIn("👥 Сабакка катышкан окуучулар:\n⚠️ Посещаемость не отмечена.", message)
        self.assertNotIn("❌", message)  # no homework was given at the previous lesson
        self.assertNotIn("баары аткарды", message)
        trainer = report["messages"]["trainer"]
        self.assertIn("⚠️ Тема занятия не указана.", trainer)
        self.assertIn("👥 Сабакка катышкандар:\n⚠️ Посещаемость не отмечена.", trainer)
        self.assertIsNone(report["next_homework"])
        self.assertEqual(len(report["warnings"]), 2)

    def test_partly_graded_homework_is_not_reported_as_all_done(self):
        self.mark(self.today, **{name: "present" for name in self.students})
        old = Homework.objects.create(lesson=self.prev, title="ДЗ")
        self.grade(old, Бекнур="checked")
        report = ParentLessonReportService.generate(self.today.pk)
        for message in report["messages"].values():
            self.assertIn("⚠️ Результаты ДЗ отмечены не у всех.", message)
            self.assertNotIn("баары аткарды", message)
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

        stranger = APIClient()
        stranger.force_authenticate(make_teacher("other").user)
        self.assertEqual(stranger.get(url).status_code, 404)
        self.assertEqual(APIClient().get(url).status_code, 401)

        scheduled = self.lesson(4, dt.date(2025, 3, 10))
        self.assertEqual(client.get(f"/api/v1/lessons/{scheduled.pk}/parent-report/").status_code, 400)

    def test_every_request_reflects_the_current_records(self):
        """The report is a view of the LMS, never a snapshot: whatever the trainer
        changes after the first opening shows up on the next one."""
        self.full_example()
        url = f"/api/v1/lessons/{self.today.pk}/parent-report/"
        client = APIClient()
        client.force_authenticate(self.teacher.user)
        Lesson.objects.filter(pk=self.today.pk).update(status=Lesson.Status.COMPLETED)
        self.assertEqual(client.get(url).json()["message"], EXAMPLE)

        # Next homework edited (title and description).
        Homework.objects.filter(lesson=self.today).update(
            title="5 Strong Passwords", description="создать 5 уникальных безопасных пароля.",
        )
        # Эрбол's homework checked after all; Йасин's grade and comment changed.
        old = Homework.objects.get(lesson=self.prev)
        HomeworkResult.objects.filter(homework=old, student=self.students["Эрбол"]).update(
            status=HomeworkResult.Status.CHECKED, score=10, comment="Молодец",
        )
        HomeworkResult.objects.filter(homework=old, student=self.students["Айжамал"]).update(
            status=HomeworkResult.Status.NOT_SUBMITTED,
        )
        # Йасин was actually present.
        Attendance.objects.filter(lesson=self.today, student=self.students["Йасин"]).update(
            status=Attendance.Status.PRESENT,
        )

        report = client.get(url).json()
        self.assertEqual(report["next_homework"], "5 Strong Passwords — создать 5 уникальных безопасных пароля.")
        self.assertEqual(report["homework_not_completed"], ["Айжамал Мурзабекова"])
        self.assertIn("Йасин Ибрахимов", report["present_students"])
        self.assertEqual(report["absent_students"], [])
        for message in report["messages"].values():
            self.assertIn("5 Strong Passwords — создать 5 уникальных безопасных пароля.", message)
            self.assertNotIn("3 Strong Passwords", message)
            self.assertNotIn("🚫", message)
            self.assertIn("• Айжамал Мурзабекова", message.split("❌", 1)[1])
            self.assertNotIn("Эрбол", message.split("❌", 1)[1])
        self.assertEqual(report["message"], report["messages"]["system"])

        # The next homework replaced entirely — the new one, not the old one, is reported.
        Homework.objects.filter(lesson=self.today).delete()
        Homework.objects.create(lesson=self.today, title="Создать адаптивную страницу Portfolio")
        report = client.get(url).json()
        self.assertEqual(report["next_homework"], "Создать адаптивную страницу Portfolio")
        self.assertIn("📚 Кийинки үй тапшырмасы:\n\nСоздать адаптивную страницу Portfolio", report["message"])

    def test_trainer_flow_through_the_api(self):
        """Step 9 of the spec, through the same endpoints the LMS screens use:
        report → «Проверить ДЗ» (save results) → report again."""
        self.full_example()
        Lesson.objects.filter(pk=self.today.pk).update(status=Lesson.Status.COMPLETED)
        client = APIClient()
        client.force_authenticate(self.teacher.user)
        report_url = f"/api/v1/lessons/{self.today.pk}/parent-report/"
        old = Homework.objects.get(lesson=self.prev)
        self.assertEqual(client.get(report_url).json()["homework_not_completed"], ["Эрбол Зулпукаров"])

        # Эрбол: «Не сдано» → «Сдано», 10/10; Бекнур: «Проверено» → «Сдано с опозданием» (still done).
        response = client.post(f"/api/v1/homework/{old.pk}/results/", [
            {"student": self.students["Эрбол"].pk, "status": "submitted", "score": 10, "comment": "Молодец"},
            {"student": self.students["Бекнур"].pk, "status": "late", "score": 8},
        ], format="json")
        self.assertEqual(response.status_code, 200, response.content)

        report = client.get(report_url).json()
        self.assertEqual(report["homework_not_completed"], [])
        for message in report["messages"].values():
            self.assertNotIn("❌", message)
            self.assertIn("✅", message)

        # Grade lowered back to «Не сдано» — he is listed again.
        client.post(f"/api/v1/homework/{old.pk}/results/", [
            {"student": self.students["Эрбол"].pk, "status": "not_submitted", "score": None},
        ], format="json")
        self.assertEqual(client.get(report_url).json()["homework_not_completed"], ["Эрбол Зулпукаров"])

    def test_homework_objects_and_current_group_only(self):
        self.full_example()
        report = ParentLessonReportService.generate(self.today.pk)
        old = Homework.objects.get(lesson=self.prev)
        current = Homework.objects.get(lesson=self.today)
        self.assertEqual(report["previous_homework"], {"id": old.pk, "title": "Безопасный браузер", "description": ""})
        self.assertEqual(report["current_homework"], {
            "id": current.pk, "title": "3 Strong Passwords", "description": "создать 3 уникальных безопасных пароля.",
        })

        # Homework text changed after the lesson — the report follows.
        Homework.objects.filter(pk=current.pk).update(title="Сверстать адаптивную карточку товара", description="")
        report = ParentLessonReportService.generate(self.today.pk)
        self.assertEqual(report["current_homework"]["title"], "Сверстать адаптивную карточку товара")
        self.assertIn("📚 Кийинки үй тапшырмасы:\n\nСверстать адаптивную карточку товара\n", report["message"])

        # A student who left the group is not reported as «не выполнил».
        Student.objects.filter(pk=self.students["Эрбол"].pk).update(is_active=False)
        self.assertEqual(ParentLessonReportService.generate(self.today.pk)["homework_not_completed"], [])

    def test_previous_lesson_is_by_number_not_by_date(self):
        """Lesson N checks Homework N-1 even when a later topic's date was moved
        before it — the report must read the homework the trainer actually grades."""
        self.full_example()
        moved = self.lesson(3, dt.date(2025, 3, 4), status=Lesson.Status.SCHEDULED)  # №3, dated before №2
        Homework.objects.create(lesson=moved, title="Чужая тема")
        report = ParentLessonReportService.generate(self.today.pk)
        self.assertEqual(report["homework_checked"]["lesson_id"], self.prev.pk)
        self.assertEqual(report["previous_homework"]["title"], "Безопасный браузер")

    def test_scenarios_from_the_spec(self):
        """12 students, 11 «Не сдано»: grading through the API moves the count and
        the names at once; a historical lesson's report is unaffected by later lessons."""
        for i in range(7):
            Student.objects.create(first_name=f"Окуучу{i}", last_name="Тест", group=self.group)
        active = list(self.group.students.filter(is_active=True))
        self.assertEqual(len(active), 12)
        Lesson.objects.filter(pk=self.today.pk).update(status=Lesson.Status.COMPLETED)
        old = Homework.objects.create(lesson=self.prev, title="Оформить страницу")
        self.grade(old, Бекнур="checked")
        for s in active:
            HomeworkResult.objects.get_or_create(homework=old, student=s)  # default «Не сдано»
        client = APIClient()
        client.force_authenticate(self.teacher.user)
        url = f"/api/v1/lessons/{self.today.pk}/parent-report/"
        response = client.get(url)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(len(response.json()["homework_not_completed"]), 11)

        # Scenario 1: one student «Не сдано» → «Сдано».
        save = lambda items: client.post(f"/api/v1/homework/{old.pk}/results/", items, format="json")
        self.assertEqual(save([{"student": self.students["Талант"].pk, "status": "submitted", "score": 7}]).status_code, 200)
        report = client.get(url).json()
        self.assertEqual(len(report["homework_not_completed"]), 10)
        self.assertNotIn("Талант Аманжолов", report["homework_not_completed"])

        # Scenarios 2–4: five students at once, statuses and scores.
        save([
            {"student": self.students["Эрбол"].pk, "status": "checked", "score": 8},
            {"student": self.students["Айжамал"].pk, "status": "checked", "score": 10},
            {"student": self.students["Йасин"].pk, "status": "late", "score": 9},
            {"student": self.students["Талант"].pk, "status": "checked", "score": 9},
            {"student": self.students["Бекнур"].pk, "status": "checked", "score": 10},
        ])
        report = client.get(url).json()
        self.assertEqual(len(report["homework_not_completed"]), 7)
        for name in ("Эрбол Зулпукаров", "Айжамал Мурзабекова", "Йасин Ибрахимов"):
            self.assertNotIn(name, report["homework_not_completed"])
            self.assertNotIn(name, report["message"].split("❌", 1)[1])

        # Scenario 6: the previous lesson's own report never looks at later lessons.
        Lesson.objects.filter(pk=self.prev.pk).update(status=Lesson.Status.COMPLETED)
        earlier = client.get(f"/api/v1/lessons/{self.prev.pk}/parent-report/").json()
        self.assertIsNone(earlier["homework_checked"])
        self.assertEqual(earlier["next_homework"], "Оформить страницу")


class ParentReportLiveResultsTests(TestCase):
    """The spec's acceptance tests 1–3 and 5, through POST /homework/{id}/results/."""

    lesson = ParentReportTests.lesson

    def setUp(self):
        ParentReportTests.setUp(self)
        for i in range(7):
            Student.objects.create(first_name=f"Окуучу{i}", last_name="Тест", group=self.group)
        self.roster = list(self.group.students.filter(is_active=True))
        Lesson.objects.filter(pk=self.today.pk).update(status=Lesson.Status.COMPLETED)
        self.old = Homework.objects.create(lesson=self.prev, title="Оформить страницу")
        for s in self.roster:
            HomeworkResult.objects.create(homework=self.old, student=s)  # «Не сдано»
        self.client = APIClient()
        self.client.force_authenticate(self.teacher.user)

    def save(self, *items):
        response = self.client.post(f"/api/v1/homework/{self.old.pk}/results/", list(items), format="json")
        self.assertEqual(response.status_code, 200, response.content)

    def report(self):
        return self.client.get(f"/api/v1/lessons/{self.today.pk}/parent-report/").json()

    def test_1_five_of_twelve_submitted_leaves_seven(self):
        self.assertEqual(len(self.roster), 12)
        self.assertEqual(len(self.report()["homework_not_completed"]), 12)
        self.save(*({"student": s.pk, "status": "submitted"} for s in self.roster[:5]))
        report = self.report()
        self.assertEqual(len(report["homework_not_completed"]), 7)
        self.assertEqual(report["message"].split("❌", 1)[1].split("\n\n")[0].count("• "), 7)

    def test_2_submitted_late_and_checked_all_count_as_done(self):
        self.save(
            {"student": self.students["Бекнур"].pk, "status": "submitted", "score": 8},
            {"student": self.students["Талант"].pk, "status": "late", "score": 7},
            {"student": self.students["Эрбол"].pk, "status": "checked", "score": 10},
        )
        report = self.report()
        for name in ("Бекнур Абдыбеков", "Талант Аманжолов", "Эрбол Зулпукаров"):
            self.assertNotIn(name, report["homework_not_completed"])
            for message in report["messages"].values():
                self.assertNotIn(name, message.split("❌", 1)[1])
        self.assertIn("Айжамал Мурзабекова", report["homework_not_completed"])

    def test_3_score_changes_are_read_fresh(self):
        # The report format has no average/score aggregate — only the «не выполнили» list.
        self.save({"student": self.students["Эрбол"].pk, "status": "checked", "score": 5})
        first = self.report()
        self.save({"student": self.students["Эрбол"].pk, "status": "checked", "score": 9})
        second = self.report()
        self.assertEqual(HomeworkResult.objects.get(homework=self.old, student=self.students["Эрбол"]).score, 9)
        self.assertNotIn("Эрбол Зулпукаров", second["homework_not_completed"])
        self.assertEqual(first["message"], second["message"])
        # A score on a «Не сдано» row does not make it done.
        self.save({"student": self.students["Эрбол"].pk, "status": "not_submitted", "score": 2})
        self.assertIn("Эрбол Зулпукаров", self.report()["homework_not_completed"])

    def test_5_other_lessons_homework_is_never_used(self):
        # Every student «Сдано» for the right homework…
        self.save(*({"student": s.pk, "status": "submitted"} for s in self.roster))
        # …but «Не сдано» everywhere else: this lesson's own homework and a later lesson's.
        later = self.lesson(3, dt.date(2025, 3, 7), status=Lesson.Status.SCHEDULED)
        for lesson in (self.today, later):
            hw = Homework.objects.create(lesson=lesson, title=f"ДЗ урока {lesson.lesson_number}")
            for s in self.roster:
                HomeworkResult.objects.create(homework=hw, student=s)
        report = self.report()
        self.assertEqual(report["previous_homework"]["id"], self.old.pk)
        self.assertEqual(report["homework_not_completed"], [])

    def test_user_scenario_three_of_twelve_and_the_wrong_homework_trap(self):
        """Lesson 5's own homework (the one the lesson page opens) is not the one its
        report checks: grading it leaves the list as is; grading lesson 4's updates it."""
        own = Homework.objects.create(lesson=self.today, title="Сверстать блоки карточек")
        graded = [
            {"student": s.pk, "status": "submitted", "score": score}
            for s, score in zip(self.roster[:3], (10, 9, 8))
        ]
        self.assertEqual(len(self.report()["homework_not_completed"]), 12)

        response = self.client.post(f"/api/v1/homework/{own.pk}/results/", graded, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.report()["homework_not_completed"]), 12)

        self.save(*graded)
        self.assertEqual(
            sorted(HomeworkResult.objects.filter(homework=self.old, status="submitted").values_list("score", flat=True)),
            [8, 9, 10],
        )
        self.assertEqual(len(self.report()["homework_not_completed"]), 9)
