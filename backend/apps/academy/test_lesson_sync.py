"""«Сгенерировать занятия» = create + sync: existing future lessons follow the
current CourseLessonPlan, history and trainers' manual edits never change.

Absolute imports only — see the note at the top of apps/academy/tests.py.
"""
from __future__ import annotations

import datetime as dt

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academy.models import (
    Attendance,
    Course,
    CourseLessonPlan,
    Group,
    Homework,
    HomeworkResult,
    Lesson,
    Room,
    Student,
)
from apps.academy.services import lesson_lifecycle
from apps.academy.services.lesson_generator import (
    generate_lessons_for_group,
    generate_lessons_for_group_with_report,
    preview_generation,
)
from apps.academy.tests import make_admin, make_teacher, sync_and_generate
from apps.users.models import Subject


class LessonPlanSyncTests(TestCase):
    """One IT program, Mon/Wed/Fri, a 6-lesson plan whose homework follows
    the project rule: lesson N checks the homework given at lesson N-1, so
    the first and the last lesson carry no homework."""

    COUNT = 6

    def setUp(self):
        self.admin = make_admin("sync_admin")
        self.teacher = make_teacher("sync_teacher")
        self.it = Subject.objects.create(name="SyncIT")
        self.room = Room.objects.create(name="SyncRoom", capacity=20)
        self.course = Course.objects.create(name="SyncCourse", count_lesson=self.COUNT)
        self.course.subjects.set([self.it])
        for number in range(1, self.COUNT + 1):
            has_homework = 1 < number < self.COUNT
            CourseLessonPlan.objects.create(
                course=self.course, lesson_number=number, subject=self.it, topic=f"Тема {number}",
                description=f"Описание {number}",
                homework_title=f"ДЗ {number - 1}" if has_homework else "",
                homework_description=f"Задание {number - 1}" if has_homework else "",
            )
        # 2026-09-14 is a Monday.
        self.group = Group.objects.create(
            name="SyncGroup", course=self.course, teacher=self.teacher, room=self.room,
            start_date=dt.date(2026, 9, 14), start_time=dt.time(8, 0), end_time=dt.time(9, 0),
            days_of_week=["mon", "wed", "fri"],
        )
        self.student = Student.objects.create(first_name="Алина", last_name="Иванова", group=self.group)
        sync_and_generate(self.group)

    # -- helpers --------------------------------------------------------------

    def lesson(self, number: int) -> Lesson:
        return Lesson.objects.get(group=self.group, lesson_number=number)

    def plan(self, number: int) -> CourseLessonPlan:
        return CourseLessonPlan.objects.get(course=self.course, lesson_number=number)

    def change_plan(self, number: int, **fields) -> None:
        CourseLessonPlan.objects.filter(course=self.course, lesson_number=number).update(**fields)

    def complete(self, number: int) -> Lesson:
        lesson = self.lesson(number)
        Attendance.objects.create(student=self.student, lesson=lesson, status=Attendance.Status.PRESENT)
        lesson_lifecycle.start_lesson(lesson, self.teacher.user)
        if not lesson.homeworks.exists():
            lesson_lifecycle.set_homework_not_required(lesson, True)
        return lesson_lifecycle.complete_lesson(lesson, self.teacher.user)

    def snapshot(self, lesson: Lesson) -> tuple:
        lesson.refresh_from_db()
        homework = [(h.pk, h.title, h.description) for h in lesson.homeworks.order_by("pk")]
        return (
            lesson.pk, lesson.topic, lesson.description, lesson.youtube_url, lesson.presentation_urls,
            lesson.date, lesson.start_time, lesson.status, lesson.completed_at, homework,
        )

    # -- 1. completed lessons are locked --------------------------------------

    def test_completed_lesson_not_changed_by_plan_change(self):
        completed = self.complete(1)
        before = self.snapshot(completed)
        self.change_plan(1, topic="Новая тема", description="Новое", youtube_url="https://youtu.be/new")

        report = generate_lessons_for_group_with_report(self.group)

        self.assertEqual(self.snapshot(completed), before)
        self.assertEqual(report.locked, 1)

    def test_in_progress_and_cancelled_lessons_are_locked(self):
        in_progress = self.lesson(1)
        lesson_lifecycle.start_lesson(in_progress, self.teacher.user)
        cancelled = self.lesson(2)
        lesson_lifecycle.cancel_lesson(cancelled, self.teacher.user, "Праздник")
        self.change_plan(1, topic="Новая 1")
        self.change_plan(2, topic="Новая 2")

        report = generate_lessons_for_group_with_report(self.group)

        self.assertEqual(self.lesson(1).topic, "Тема 1")
        self.assertEqual(Lesson.objects.get(pk=cancelled.pk).topic, "Тема 2")
        self.assertEqual(report.locked, 2)

    def test_scheduled_lesson_with_attendance_is_locked(self):
        lesson = self.lesson(3)
        Attendance.objects.create(student=self.student, lesson=lesson, status=Attendance.Status.PRESENT)
        self.change_plan(3, topic="Новая 3")

        generate_lessons_for_group(self.group)

        self.assertEqual(self.lesson(3).topic, "Тема 3")

    # -- 2. plain future lessons follow the plan ------------------------------

    def test_scheduled_lesson_synced_with_changed_plan(self):
        before = self.lesson(4)
        self.change_plan(
            4, topic="CSS Grid", description="Сетки", youtube_url="https://youtu.be/grid",
            presentation_urls=["https://slides.example/grid"],
        )

        report = generate_lessons_for_group_with_report(self.group)

        after = self.lesson(4)
        self.assertEqual(after.pk, before.pk)
        self.assertEqual(
            (after.topic, after.description, after.youtube_url, after.presentation_urls),
            ("CSS Grid", "Сетки", "https://youtu.be/grid", ["https://slides.example/grid"]),
        )
        # Content only: the schedule is never rebuilt by a sync.
        self.assertEqual((after.date, after.start_time, after.end_time), (before.date, before.start_time, before.end_time))
        self.assertFalse(after.manually_edited)
        self.assertEqual((report.created, report.updated, report.unchanged), (0, 1, self.COUNT - 1))

    def test_scenario_three_completed_three_future(self):
        for number in (1, 2, 3):
            self.complete(number)
        history = {number: self.snapshot(self.lesson(number)) for number in (1, 2, 3)}
        for number in range(1, self.COUNT + 1):
            self.change_plan(number, topic=f"Новая тема {number}")

        report = generate_lessons_for_group_with_report(self.group)

        for number in (1, 2, 3):
            self.assertEqual(self.snapshot(self.lesson(number)), history[number])
        for number in (4, 5, 6):
            self.assertEqual(self.lesson(number).topic, f"Новая тема {number}")
        self.assertEqual((report.updated, report.locked), (3, 3))

    # -- 3. manual edits win ---------------------------------------------------

    def test_manually_edited_lesson_not_overwritten(self):
        client = APIClient()
        client.force_authenticate(self.teacher.user)
        lesson = self.lesson(5)
        response = client.patch(
            f"/api/v1/lessons/{lesson.pk}/", {"topic": "JavaScript: функции + практика"}, format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["manually_edited"])
        self.change_plan(5, topic="JavaScript: функции")

        report = generate_lessons_for_group_with_report(self.group)

        self.assertEqual(self.lesson(5).topic, "JavaScript: функции + практика")
        self.assertEqual(report.manually_edited, 1)

    def test_patch_without_content_change_does_not_mark_edited(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        lesson = self.lesson(5)
        client.patch(f"/api/v1/lessons/{lesson.pk}/", {"topic": lesson.topic}, format="json")

        self.assertFalse(self.lesson(5).manually_edited)

    def test_editing_homework_by_hand_marks_lesson_edited(self):
        client = APIClient()
        client.force_authenticate(self.teacher.user)
        homework = self.lesson(3).homeworks.get()
        response = client.patch(f"/api/v1/homework/{homework.pk}/", {"title": "Своё ДЗ"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.change_plan(3, homework_title="ДЗ из плана")

        generate_lessons_for_group(self.group)

        self.assertTrue(self.lesson(3).manually_edited)
        self.assertEqual(self.lesson(3).homeworks.get().title, "Своё ДЗ")

    def test_deleting_homework_by_hand_is_not_undone_by_sync(self):
        client = APIClient()
        client.force_authenticate(self.teacher.user)
        homework = self.lesson(3).homeworks.get()
        self.assertEqual(client.delete(f"/api/v1/homework/{homework.pk}/").status_code, 204)

        generate_lessons_for_group(self.group)

        self.assertFalse(self.lesson(3).homeworks.exists())

    # -- 4/5. create missing, never duplicate ----------------------------------

    def test_missing_lesson_is_created_from_current_plan(self):
        self.lesson(6).delete()
        self.change_plan(6, topic="Финал")

        report = generate_lessons_for_group_with_report(self.group)

        self.assertEqual(report.created, 1)
        self.assertEqual(self.lesson(6).topic, "Финал")

    def test_existing_lesson_updated_not_duplicated(self):
        self.change_plan(2, topic="Обновлено")

        generate_lessons_for_group(self.group)

        self.assertEqual(Lesson.objects.filter(group=self.group, lesson_number=2).count(), 1)
        self.assertEqual(Lesson.objects.filter(group=self.group).count(), self.COUNT)

    def test_repeated_generation_is_stable(self):
        self.complete(1)
        self.change_plan(2, topic="Новая 2", homework_title="Новое ДЗ 1")
        ids = set(Lesson.objects.filter(group=self.group).values_list("pk", flat=True))

        reports = [generate_lessons_for_group_with_report(self.group) for _ in range(3)]

        self.assertEqual([(r.created, r.updated) for r in reports], [(0, 1), (0, 0), (0, 0)])
        self.assertEqual(set(Lesson.objects.filter(group=self.group).values_list("pk", flat=True)), ids)
        self.assertEqual(Homework.objects.filter(lesson__group=self.group).count(), self.COUNT - 2)
        self.assertEqual(self.lesson(2).homeworks.get().title, "Новое ДЗ 1")
        self.assertEqual(reports[-1].unchanged, self.COUNT - 1)

    # -- 6/7. homework ---------------------------------------------------------

    def test_completed_lesson_homework_and_results_unchanged(self):
        lesson = self.lesson(2)
        homework = lesson.homeworks.get()
        result = HomeworkResult.objects.create(
            homework=homework, student=self.student, status=HomeworkResult.Status.CHECKED, score=9, comment="Отлично",
        )
        self.complete(2)
        self.change_plan(2, homework_title="Другое ДЗ", homework_description="Другое")

        generate_lessons_for_group(self.group)

        homework.refresh_from_db()
        result.refresh_from_db()
        self.assertEqual((homework.title, homework.description), ("ДЗ 1", "Задание 1"))
        self.assertEqual((result.status, result.score, result.comment), (HomeworkResult.Status.CHECKED, 9, "Отлично"))

    def test_graded_homework_locks_scheduled_lesson(self):
        homework = self.lesson(3).homeworks.get()
        HomeworkResult.objects.create(homework=homework, student=self.student, status=HomeworkResult.Status.SUBMITTED)
        self.change_plan(3, homework_title="Другое ДЗ")

        generate_lessons_for_group(self.group)

        homework.refresh_from_db()
        self.assertEqual(homework.title, "ДЗ 2")

    def test_future_homework_follows_current_plan(self):
        homework = self.lesson(4).homeworks.get()
        self.change_plan(4, homework_title="ДЗ 3 (новое)", homework_description="Новое задание")

        generate_lessons_for_group(self.group)

        synced = self.lesson(4).homeworks.get()
        self.assertEqual(synced.pk, homework.pk)
        self.assertEqual((synced.title, synced.description), ("ДЗ 3 (новое)", "Новое задание"))

    def test_first_and_last_lessons_have_no_homework(self):
        self.assertFalse(self.lesson(1).homeworks.exists())
        self.assertFalse(self.lesson(self.COUNT).homeworks.exists())

        generate_lessons_for_group(self.group)

        self.assertFalse(self.lesson(1).homeworks.exists())
        self.assertFalse(self.lesson(self.COUNT).homeworks.exists())

    def test_lesson_n_carries_previous_lessons_homework(self):
        self.change_plan(3, homework_title="ДЗ 2 (новое)")

        generate_lessons_for_group(self.group)

        for number in range(2, self.COUNT):
            expected = "ДЗ 2 (новое)" if number == 3 else f"ДЗ {number - 1}"
            self.assertEqual(self.lesson(number).homeworks.get().title, expected)

    def test_homework_added_and_removed_with_plan(self):
        self.change_plan(1, homework_title="Вводное ДЗ")
        self.change_plan(5, homework_title="", homework_description="")

        generate_lessons_for_group(self.group)

        self.assertEqual(self.lesson(1).homeworks.get().title, "Вводное ДЗ")
        self.assertFalse(self.lesson(5).homeworks.exists())

    # -- surfaces ---------------------------------------------------------------

    def test_preview_counts_updates_without_writing(self):
        self.complete(1)
        self.change_plan(2, topic="Новая 2")

        preview = preview_generation(self.group)

        self.assertEqual((preview.to_create, preview.to_update, preview.locked), (0, 1, 1))
        self.assertTrue(preview.has_changes)
        self.assertEqual(self.lesson(2).topic, "Тема 2")

    def test_api_returns_sync_counts(self):
        self.complete(1)
        self.change_plan(2, topic="Новая 2")
        client = APIClient()
        client.force_authenticate(self.admin)

        response = client.post(f"/api/v1/groups/{self.group.pk}/generate-lessons/")

        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(
            (data["created_count"], data["updated_count"], data["unchanged_count"], data["locked_count"],
             data["manually_edited_count"]),
            (0, 1, self.COUNT - 2, 1, 0),
        )

    def test_workspace_button_shows_sync_summary(self):
        self.change_plan(2, topic="Новая 2")
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse("admin:academy_group_workspace_generate_lessons", args=[self.group.pk]), follow=True,
        )

        self.assertContains(response, "Синхронизация завершена")
        self.assertContains(response, "Обновлено: 1")
        self.assertContains(response, "Пропущено вручную изменённых: 0")
