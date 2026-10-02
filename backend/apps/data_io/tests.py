"""CourseLessonPlan import: upsert by course + lesson_number + subject."""
from __future__ import annotations

import csv
import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.academy.models import Course, CourseLessonPlan, Lesson
from apps.data_io.registry import get_adapter
from apps.data_io.services import commit_import
from apps.users.models import Subject, User

HEADERS = ["Курс", "Номер занятия", "Предмет", "Тема занятия", "Домашнее задание"]


def make_csv(rows: list[list], name: str = "plans.csv") -> SimpleUploadedFile:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(HEADERS)
    writer.writerows(rows)
    return SimpleUploadedFile(name, buffer.getvalue().encode("utf-8"), content_type="text/csv")


class CourseLessonPlanImportTests(TestCase):
    def setUp(self):
        self.adapter = get_adapter("academy.courselessonplan")
        self.it = Subject.objects.create(name="IT")
        self.robotics = Subject.objects.create(name="Robotics")
        self.course = Course.objects.create(name="NEXT", count_lesson=300)
        self.course.subjects.set([self.it, self.robotics])
        self.plan1 = CourseLessonPlan.objects.create(
            course=self.course, lesson_number=1, subject=self.it, topic="WEB RESTART"
        )
        self.plan2 = CourseLessonPlan.objects.create(
            course=self.course, lesson_number=2, subject=self.it, topic="HTML"
        )

    def import_rows(self, rows):
        return commit_import(self.adapter, make_csv(rows))

    def test_create_new_plan(self):
        result = self.import_rows([["NEXT", "300", "IT", "Финал", ""]])

        self.assertEqual((result.created, result.updated, result.skipped), (1, 0, 0))
        self.assertEqual(result.errors, [])
        plan = CourseLessonPlan.objects.get(course=self.course, lesson_number=300, subject=self.it)
        self.assertEqual(plan.topic, "Финал")

    def test_update_existing_plan_keeps_id(self):
        result = self.import_rows([["NEXT", "1", "IT", "Новая тема", "ДЗ 1"]])

        self.assertEqual((result.created, result.updated), (0, 1))
        plans = CourseLessonPlan.objects.filter(course=self.course, lesson_number=1, subject=self.it)
        self.assertEqual(plans.count(), 1)
        plan = plans.get()
        self.assertEqual(plan.pk, self.plan1.pk)
        self.assertEqual(plan.topic, "Новая тема")
        self.assertEqual(plan.homework_title, "ДЗ 1")

    def test_mixed_import(self):
        rows = [
            ["NEXT", "1", "IT", "Новая тема", ""],
            ["NEXT", "2", "IT", "HTML новая версия", ""],
            ["NEXT", "3", "IT", "CSS", ""],
        ]
        result = self.import_rows(rows)

        self.assertEqual((result.created, result.updated), (1, 2))
        self.assertEqual(CourseLessonPlan.objects.count(), 3)
        self.assertEqual(CourseLessonPlan.objects.get(pk=self.plan1.pk).topic, "Новая тема")
        self.assertEqual(CourseLessonPlan.objects.get(pk=self.plan2.pk).topic, "HTML новая версия")

    def test_reimport_same_file_creates_no_duplicates(self):
        rows = [
            ["NEXT", "1", "IT", "Новая тема", ""],
            ["NEXT", "2", "IT", "HTML новая версия", ""],
            ["NEXT", "300", "IT", "Финал", ""],
        ]
        first = self.import_rows(rows)
        ids_after_first = set(CourseLessonPlan.objects.values_list("pk", flat=True))

        second = self.import_rows(rows)

        self.assertEqual((first.created, first.updated), (1, 2))
        self.assertEqual((second.created, second.updated), (0, 3))
        self.assertEqual(CourseLessonPlan.objects.count(), 3)
        self.assertEqual(set(CourseLessonPlan.objects.values_list("pk", flat=True)), ids_after_first)

    def test_import_does_not_delete_plans_missing_from_file(self):
        self.import_rows([["NEXT", "3", "IT", "CSS", ""]])

        self.assertTrue(CourseLessonPlan.objects.filter(pk=self.plan1.pk).exists())
        self.assertTrue(CourseLessonPlan.objects.filter(pk=self.plan2.pk).exists())

    def test_import_does_not_create_real_lessons(self):
        self.import_rows([["NEXT", "3", "IT", "CSS", ""], ["NEXT", "1", "IT", "Новая тема", ""]])

        self.assertEqual(Lesson.objects.count(), 0)

    def test_duplicate_rows_in_file_are_reported_not_duplicated(self):
        rows = [
            ["NEXT", "1", "IT", "Первая", ""],
            ["NEXT", "1", "IT", "Вторая", ""],
        ]
        result = self.import_rows(rows)

        self.assertEqual((result.created, result.updated, result.skipped), (0, 1, 1))
        self.assertEqual([error.row for error in result.errors], [3])
        self.assertIn("строка 2", result.errors[0].errors[0])
        self.assertEqual(CourseLessonPlan.objects.filter(course=self.course, lesson_number=1).count(), 1)
        self.assertEqual(CourseLessonPlan.objects.get(pk=self.plan1.pk).topic, "Первая")

    def test_other_subject_on_taken_number_is_skipped_without_touching_plan(self):
        result = self.import_rows([["NEXT", "1", "Robotics", "Роботы", ""]])

        self.assertEqual((result.created, result.updated, result.skipped), (0, 0, 1))
        self.assertIn("«IT»", result.errors[0].errors[0])
        plan = CourseLessonPlan.objects.get(pk=self.plan1.pk)
        self.assertEqual((plan.subject, plan.topic), (self.it, "WEB RESTART"))
        self.assertEqual(CourseLessonPlan.objects.count(), 2)

    def test_invalid_rows_are_skipped_and_valid_rows_saved(self):
        rows = [
            ["NEXT", "1", "IT", "Новая тема", ""],
            ["NEXT", "abc", "IT", "Сломано", ""],
            ["NEXT", "3", "IT", "CSS", ""],
            ["UNKNOWN", "4", "IT", "Нет курса", ""],
        ]
        result = self.import_rows(rows)

        self.assertEqual((result.created, result.updated, result.skipped), (1, 1, 2))
        self.assertEqual([error.row for error in result.errors], [3, 5])
        self.assertEqual(CourseLessonPlan.objects.count(), 3)


class CourseLessonPlanImportAdminTests(TestCase):
    def setUp(self):
        admin = User.objects.create_superuser(
            username="admin", email="admin@okurmen.kg", password="Str0ngPassw0rd!", first_name="Admin"
        )
        self.client.force_login(admin)
        it = Subject.objects.create(name="IT")
        course = Course.objects.create(name="NEXT", count_lesson=10)
        course.subjects.set([it])
        self.plan = CourseLessonPlan.objects.create(course=course, lesson_number=1, subject=it, topic="WEB RESTART")
        self.url = reverse("admin:academy_courselessonplan_io_import")

    def test_clean_import_redirects_with_summary(self):
        file_obj = make_csv([["NEXT", "1", "IT", "Новая тема", ""], ["NEXT", "2", "IT", "HTML", ""]])
        response = self.client.post(self.url, {"file": file_obj, "confirm": "1"}, follow=True)

        messages = [str(m) for m in response.context["messages"]]
        self.assertIn("Импорт завершён. Создано: 1, обновлено: 1, пропущено: 0, ошибок: 0.", messages)

    def test_import_with_errors_shows_summary_and_rows(self):
        file_obj = make_csv([["NEXT", "1", "IT", "Новая тема", ""], ["NEXT", "99", "IT", "Слишком далеко", ""]])
        response = self.client.post(self.url, {"file": file_obj, "confirm": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Пропущено: <strong>1</strong>", html=False)
        self.assertContains(response, "Строка 3")
        self.assertEqual(CourseLessonPlan.objects.get(pk=self.plan.pk).topic, "Новая тема")
