from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.academy.models import Course, CourseLessonPlan, Lesson, Homework
from apps.data_io.registry import get_adapter
from apps.data_io.services import commit_import, preview_import
from apps.users.models import Subject, User

# Absolute imports only — see the note at the top of apps/academy/tests.py.

HEADER = "Курс,Номер занятия,Предмет,Тема занятия,Домашнее задание,Описание домашнего задания"


def plans_csv(*rows: str, name: str = "plans.csv") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, ("\n".join([HEADER, *rows]) + "\n").encode("utf-8"), content_type="text/csv")


class CourseLessonPlanImportUpsertTests(TestCase):
    """CourseLessonPlan import is an UPSERT keyed on course + lesson_number +
    subject: an existing plan is updated in place (same ID), a missing one is
    created, nothing is deleted or duplicated."""

    def setUp(self):
        self.adapter = get_adapter("academy.courselessonplan")
        self.subject = Subject.objects.create(name="IT")
        self.other_subject = Subject.objects.create(name="Design")
        self.course = Course.objects.create(name="NEXT", count_lesson=300)
        self.course.subjects.set([self.subject, self.other_subject])
        self.plan1 = CourseLessonPlan.objects.create(
            course=self.course, lesson_number=1, subject=self.subject, topic="WEB RESTART"
        )
        self.plan2 = CourseLessonPlan.objects.create(course=self.course, lesson_number=2, subject=self.subject, topic="HTML")

    def test_create_new_plan(self):
        result = commit_import(self.adapter, plans_csv("NEXT,300,IT,Финал,,"))

        self.assertEqual((result.created, result.updated, result.skipped, result.error_count), (1, 0, 0, 0))
        plan = CourseLessonPlan.objects.get(course=self.course, lesson_number=300, subject=self.subject)
        self.assertEqual(plan.topic, "Финал")

    def test_update_existing_plan_keeps_its_id(self):
        result = commit_import(self.adapter, plans_csv("NEXT,1,IT,Новое название,ДЗ 1,Сделать сайт"))

        self.assertEqual((result.created, result.updated), (0, 1))
        self.assertEqual(CourseLessonPlan.objects.filter(course=self.course, lesson_number=1).count(), 1)
        plan = CourseLessonPlan.objects.get(course=self.course, lesson_number=1)
        self.assertEqual(plan.pk, self.plan1.pk)
        self.assertEqual(plan.topic, "Новое название")
        self.assertEqual(plan.homework_title, "ДЗ 1")
        self.assertEqual(plan.homework_description, "Сделать сайт")

    def test_mixed_import(self):
        result = commit_import(
            self.adapter,
            plans_csv("NEXT,1,IT,Новая тема,,", "NEXT,2,IT,HTML новая версия,,", "NEXT,300,IT,CSS,,"),
        )

        self.assertEqual((result.created, result.updated), (1, 2))
        self.assertEqual(CourseLessonPlan.objects.filter(course=self.course).count(), 3)
        self.plan1.refresh_from_db()
        self.plan2.refresh_from_db()
        self.assertEqual(self.plan1.topic, "Новая тема")
        self.assertEqual(self.plan2.topic, "HTML новая версия")

    def test_reimporting_the_same_file_creates_no_duplicates(self):
        rows = ("NEXT,1,IT,Новая тема,,", "NEXT,2,IT,HTML новая версия,,", "NEXT,300,IT,CSS,,")
        commit_import(self.adapter, plans_csv(*rows))
        ids_after_first = set(CourseLessonPlan.objects.values_list("pk", flat=True))

        result = commit_import(self.adapter, plans_csv(*rows))

        self.assertEqual((result.created, result.updated), (0, 3))
        self.assertEqual(CourseLessonPlan.objects.count(), 3)
        self.assertEqual(set(CourseLessonPlan.objects.values_list("pk", flat=True)), ids_after_first)

    def test_lesson_number_taken_by_another_subject_is_a_row_error_not_a_duplicate(self):
        result = commit_import(self.adapter, plans_csv("NEXT,1,Design,Другой предмет,,", "NEXT,3,IT,CSS,,"))

        self.assertEqual((result.created, result.updated, result.skipped, result.error_count), (1, 0, 1, 1))
        self.assertEqual(result.errors[0].row, 2)
        self.assertIn("уже есть с предметом «IT»", result.errors[0].errors[0])
        self.plan1.refresh_from_db()
        self.assertEqual((self.plan1.subject_id, self.plan1.topic), (self.subject.pk, "WEB RESTART"))

    def test_same_plan_twice_in_one_file_is_reported_and_saved_once(self):
        result = commit_import(self.adapter, plans_csv("NEXT,1,IT,Первая,,", "NEXT,1,IT,Вторая,,"))

        self.assertEqual((result.created, result.updated, result.skipped), (0, 1, 1))
        self.assertEqual(result.errors[0].row, 3)
        self.assertEqual(CourseLessonPlan.objects.filter(course=self.course, lesson_number=1).count(), 1)
        self.plan1.refresh_from_db()
        self.assertEqual(self.plan1.topic, "Первая")

    def test_invalid_rows_are_skipped_valid_rows_are_saved(self):
        result = commit_import(self.adapter, plans_csv("NEXT,2,IT,HTML 2,,", "НЕТ ТАКОГО,5,IT,X,,", "NEXT,abc,IT,Y,,"))

        self.assertEqual((result.created, result.updated, result.skipped, result.error_count), (0, 1, 2, 2))
        self.assertEqual([error.row for error in result.errors], [3, 4])

    def test_preview_writes_nothing(self):
        preview = preview_import(self.adapter, plans_csv("NEXT,1,IT,Новая,,", "NEXT,300,IT,CSS,,"))

        self.assertEqual((preview.total, preview.valid, preview.invalid), (2, 2, 0))
        self.assertEqual(CourseLessonPlan.objects.count(), 2)
        self.plan1.refresh_from_db()
        self.assertEqual(self.plan1.topic, "WEB RESTART")

    def test_import_never_touches_lessons_or_homework(self):
        lessons, homeworks = Lesson.objects.count(), Homework.objects.count()
        commit_import(self.adapter, plans_csv("NEXT,1,IT,Новая,ДЗ,", "NEXT,300,IT,CSS,ДЗ,"))
        self.assertEqual((Lesson.objects.count(), Homework.objects.count()), (lessons, homeworks))


class CourseLessonPlanAdminImportViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="admin", email="admin@okurmen.kg", password="Str0ngPassw0rd!")
        self.client.force_login(self.admin)
        self.subject = Subject.objects.create(name="IT")
        self.course = Course.objects.create(name="NEXT", count_lesson=10)
        self.course.subjects.set([self.subject])
        CourseLessonPlan.objects.create(course=self.course, lesson_number=1, subject=self.subject, topic="WEB RESTART")
        self.url = reverse("admin:academy_courselessonplan_io_import")

    def test_clean_import_redirects_with_summary_message(self):
        response = self.client.post(self.url, {"file": plans_csv("NEXT,1,IT,Новая тема,,", "NEXT,2,IT,HTML,,")}, follow=True)

        messages = [str(m) for m in response.context["messages"]]
        self.assertIn("Импорт завершён. Создано: 1 · Обновлено: 1 · Пропущено: 0 · Ошибок: 0", messages)

    def test_import_with_errors_shows_summary_and_rows(self):
        response = self.client.post(self.url, {"file": plans_csv("NEXT,1,IT,Новая тема,,", "NEXT,99,IT,Слишком большой,,")})

        self.assertEqual(response.status_code, 200)
        result = response.context["result"]
        self.assertEqual((result.created, result.updated, result.skipped, result.error_count), (0, 1, 1, 1))
        self.assertContains(response, "Импорт завершён")
        self.assertContains(response, "Строка 3")
