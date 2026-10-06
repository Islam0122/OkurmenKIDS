"""Assistant Workspace API: access, and that every operation goes through
the existing academy services (history kept, conflicts refused)."""
from __future__ import annotations

import datetime as dt

from django.contrib.admin.models import LogEntry
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.academy.models import (
    Attendance,
    Course,
    Group,
    GroupSchedule,
    GroupTeacher,
    Lesson,
    Room,
    Student,
    StudentStatusEvent,
)
from apps.feedback.models import Survey
from apps.users.models import Subject, Teacher, User

PASSWORD = "Str0ngPassw0rd!"
TODAY = dt.date.today()


def make_teacher(username: str) -> Teacher:
    user = User.objects.create_user(
        username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
        first_name=username.capitalize(), role=User.Role.TEACHER, is_verified=True,
    )
    return Teacher.objects.create(user=user)


class AssistantTestBase(TestCase):
    def setUp(self):
        self.assistant = User.objects.create_user(
            username="assist", email="assist@okurmen.kg", password=PASSWORD,
            first_name="Asel", role=User.Role.ASSISTANT,
        )
        self.python, _ = Subject.objects.get_or_create(name="Python")
        self.course = Course.objects.create(name="Prog", count_lesson=4)
        self.course.subjects.set([self.python])
        self.islam = make_teacher("islam")
        self.aibek = make_teacher("aibek")
        self.room = Room.objects.create(name="A1")
        self.g1 = Group.objects.create(name="PRO-01", course=self.course, start_date=TODAY - dt.timedelta(days=30))
        self.g2 = Group.objects.create(name="PRO-02", course=self.course, start_date=TODAY - dt.timedelta(days=30))
        self.gt1 = GroupTeacher.objects.create(group=self.g1, teacher=self.islam, subject=self.python)
        GroupSchedule.objects.create(group=self.g1, teacher=self.islam, subject=self.python, day_of_week="mon",
                                     start_time=dt.time(16), end_time=dt.time(17, 30), room=self.room)
        self.s1 = Student.objects.create(first_name="Islam", last_name="Duishobaev", group=self.g1)
        self.s2 = Student.objects.create(first_name="Aida", last_name="K", group=self.g1)
        self.client = APIClient()
        self.client.force_authenticate(self.assistant)

    def url(self, name, *args):
        return reverse(f"assistant:{name}", args=args)


class AccessTests(AssistantTestBase):
    def test_teacher_and_team_lead_are_refused(self):
        lead = User.objects.create_user(username="lead", email="l@o.kg", password=PASSWORD, role=User.Role.TEAM_LEAD)
        for user in (self.islam.user, lead):
            client = APIClient()
            client.force_authenticate(user)
            self.assertEqual(client.get(self.url("dashboard")).status_code, status.HTTP_403_FORBIDDEN)
            response = client.post(self.url("student-deactivate", self.s1.pk), {"reason": "other", "comment": "x"})
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_is_refused(self):
        self.assertEqual(APIClient().get(self.url("dashboard")).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_inactive_assistant_is_refused(self):
        self.assistant.is_active = False
        self.assistant.save()
        self.assertEqual(self.client.get(self.url("dashboard")).status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_may_use_the_workspace(self):
        admin = User.objects.create_superuser(username="admin", email="a@o.kg", password=PASSWORD)
        client = APIClient()
        client.force_authenticate(admin)
        self.assertEqual(client.get(self.url("dashboard")).status_code, status.HTTP_200_OK)

    def test_assistant_is_never_staff_and_has_no_django_admin(self):
        self.assistant.is_staff = True
        self.assistant.is_superuser = True
        self.assistant.save()
        self.assistant.refresh_from_db()
        self.assertFalse(self.assistant.is_staff)
        self.assertFalse(self.assistant.is_superuser)
        self.client.force_login(self.assistant)
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("/admin/login/", response["Location"])

    def test_team_lead_and_admin_areas_stay_closed(self):
        """KPI, trainer control, reports, worklog, trainers, monitoring,
        scholarship rankings: 403. The generic academy lists are scoped to a
        trainer's own groups — an Assistant has none, so they come back empty
        (the Assistant works through /api/v1/assistant/ instead)."""
        for url in ("/api/v1/reports/overview/", "/api/v1/control/", "/api/v1/trainers/",
                    "/api/v1/worklog/entries/", "/api/v1/monitoring/overview/", "/api/v1/academy-reports/",
                    "/api/v1/scholarship-awards/", "/api/v1/feedback/analytics/overview/"):
            self.assertEqual(self.client.get(url).status_code, status.HTTP_403_FORBIDDEN, url)
        for url in ("/api/v1/students/", "/api/v1/groups/", "/api/v1/lessons/"):
            self.assertEqual(self.client.get(url).data["count"], 0, url)
        response = self.client.patch(f"/api/v1/students/{self.s1.pk}/", {"first_name": "X"})
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))

    def test_login_works_for_assistant(self):
        response = APIClient().post("/api/v1/auth/login/", {"username": "assist", "password": PASSWORD})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["role"], "assistant")


class DashboardTests(AssistantTestBase):
    def test_cards_today_and_attention(self):
        Lesson.objects.create(group=self.g1, group_teacher=self.gt1, subject=self.python, teacher=self.islam,
                              lesson_number=1, date=TODAY, start_time=dt.time(16), end_time=dt.time(17, 30))
        Student.objects.create(first_name="No", last_name="Group")
        data = self.client.get(self.url("dashboard")).data
        self.assertEqual(data["cards"]["active_groups"], 2)
        self.assertEqual(data["cards"]["active_students"], 3)
        self.assertEqual(data["cards"]["todays_lessons"], 1)
        self.assertEqual(data["today"][0]["group"]["name"], "PRO-01")
        self.assertEqual(data["today"][0]["students_count"], 2)
        self.assertIn("without_group", [item["key"] for item in data["attention"]])


class GroupTests(AssistantTestBase):
    def test_list_filters_and_card(self):
        self.g2.status = Group.Status.COMPLETED
        self.g2.save()
        data = self.client.get(self.url("groups")).data
        self.assertEqual([g["name"] for g in data["results"]], ["PRO-01"])
        card = data["results"][0]
        self.assertEqual(card["students_count"], 2)
        self.assertEqual(card["teachers"], ["Islam"])
        self.assertEqual(card["schedule"], "Пн — 16:00–17:30")
        archived = self.client.get(self.url("groups"), {"status": "archived"}).data
        self.assertEqual([g["name"] for g in archived["results"]], ["PRO-02"])

    def test_create_group_with_teacher_schedule_and_students(self):
        loose = Student.objects.create(first_name="New", last_name="One")
        response = self.client.post(self.url("groups"), {
            "name": "PRO-03", "course": self.course.pk, "start_date": str(TODAY),
            "programs": [{"teacher": self.aibek.pk, "subject": self.python.pk, "slots": [
                {"day": "wed", "start": "16:00", "end": "17:30"},
                {"day": "fri", "start": "16:00", "end": "17:30"},
            ]}],
            "students": [loose.pk, self.s2.pk],
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        group = Group.objects.get(name="PRO-03")
        self.assertEqual(group.schedules.filter(is_active=True).count(), 2)
        self.assertEqual(set(group.students.values_list("pk", flat=True)), {loose.pk, self.s2.pk})
        transfer = StudentStatusEvent.objects.get(student=self.s2, event_type="transferred")
        self.assertEqual((transfer.from_group, transfer.group), (self.g1, group))
        self.assertTrue(LogEntry.objects.filter(object_id=str(group.pk), object_repr="PRO-03").exists())

    def test_create_group_refuses_teacher_conflict_and_creates_nothing(self):
        response = self.client.post(self.url("groups"), {
            "name": "PRO-03", "course": self.course.pk, "start_date": str(TODAY),
            "programs": [{"teacher": self.islam.pk, "subject": self.python.pk, "slots": [
                {"day": "mon", "start": "17:00", "end": "18:00"},
            ]}],
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("уже занят", str(response.data))
        self.assertFalse(Group.objects.filter(name="PRO-03").exists())

    def test_detail(self):
        data = self.client.get(self.url("group-detail", self.g1.pk)).data
        self.assertEqual(data["name"], "PRO-01")
        self.assertEqual(len(data["students"]), 2)
        self.assertEqual(data["programs"][0]["slots"][0]["start"], "16:00")

    def test_missing_group_is_404(self):
        self.assertEqual(self.client.get(self.url("group-detail", 9999)).status_code, status.HTTP_404_NOT_FOUND)


class StudentTests(AssistantTestBase):
    def test_add_student(self):
        response = self.client.post(self.url("students"), {
            "first_name": "Nurs", "last_name": "A", "phone": "+996", "group": self.g2.pk,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        student = Student.objects.get(first_name="Nurs")
        self.assertEqual((student.group, student.status), (self.g2, Student.Status.ACTIVE))

    def test_add_student_refused_for_full_group(self):
        self.g1.max_students = 2
        self.g1.save()
        response = self.client.post(self.url("students"), {"first_name": "X", "last_name": "Y", "group": self.g1.pk})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("нет мест", str(response.data))

    def test_list_status_filter_and_search(self):
        self.s2.status = Student.Status.WITHDRAWN
        self.s2.is_active = False
        self.s2.save()
        data = self.client.get(self.url("students"), {"status": "inactive"}).data
        self.assertEqual([s["id"] for s in data["results"]], [self.s2.pk])
        data = self.client.get(self.url("students"), {"search": "duisho"}).data
        self.assertEqual([s["id"] for s in data["results"]], [self.s1.pk])

    def test_deactivate_keeps_student_and_history(self):
        response = self.client.post(self.url("student-deactivate", self.s1.pk),
                                    {"reason": "financial_issues", "comment": "Оплата"})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.s1.refresh_from_db()
        self.assertEqual(self.s1.status, Student.Status.WITHDRAWN)
        event = StudentStatusEvent.objects.get(student=self.s1)
        self.assertEqual((event.event_type, event.reason, event.performed_by), ("deactivated", "financial_issues", self.assistant))
        self.assertEqual(response.data["status"], "withdrawn")

    def test_deactivate_with_pause_reason_pauses(self):
        self.client.post(self.url("student-deactivate", self.s1.pk), {"reason": "pause"})
        self.s1.refresh_from_db()
        self.assertEqual(self.s1.status, Student.Status.PAUSED)

    def test_deactivation_date_cannot_be_in_future(self):
        response = self.client.post(self.url("student-deactivate", self.s1.pk), {
            "reason": "relocation", "event_date": str(TODAY + dt.timedelta(days=3)),
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_activate_withdrawn_requires_group_and_returns_to_active(self):
        self.client.post(self.url("student-deactivate", self.s1.pk), {"reason": "relocation"})
        refused = self.client.post(self.url("student-activate", self.s1.pk), {})
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(self.url("student-activate", self.s1.pk), {"group": self.g2.pk})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.s1.refresh_from_db()
        self.assertEqual((self.s1.status, self.s1.group), (Student.Status.ACTIVE, self.g2))

    def test_transfer_moves_same_student_and_records_history(self):
        response = self.client.post(self.url("student-transfer", self.s1.pk), {"group": self.g2.pk, "comment": "Время"})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.s1.refresh_from_db()
        self.assertEqual(self.s1.group, self.g2)
        self.assertEqual(Student.objects.filter(first_name="Islam").count(), 1)
        titles = [row["title"] for row in response.data["history"]]
        self.assertIn("Перевод: PRO-01 → PRO-02", titles)

    def test_transfer_to_same_group_or_closed_group_is_refused(self):
        same = self.client.post(self.url("student-transfer", self.s1.pk), {"group": self.g1.pk})
        self.assertEqual(same.status_code, status.HTTP_400_BAD_REQUEST)
        self.g2.status = Group.Status.CANCELLED
        self.g2.save()
        closed = self.client.post(self.url("student-transfer", self.s1.pk), {"group": self.g2.pk})
        self.assertEqual(closed.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_reports_per_student(self):
        self.client.post(self.url("student-deactivate", self.s2.pk), {"reason": "relocation"})
        response = self.client.post(self.url("students-bulk"), {
            "action": "transfer", "students": [self.s1.pk, self.s2.pk], "group": self.g2.pk,
        }, format="json")
        self.assertEqual(response.data["done"], 1)
        self.assertEqual(response.data["failed"], 1)
        self.s1.refresh_from_db()
        self.assertEqual(self.s1.group, self.g2)

    def test_profile_contains_tabs_data(self):
        data = self.client.get(self.url("student-detail", self.s1.pk)).data
        for key in ("schedule", "attendance", "homework", "exams", "scholarships", "surveys", "history"):
            self.assertIn(key, data)
        self.assertEqual(data["teachers"], ["Islam"])


class ScheduleTests(AssistantTestBase):
    def _lesson(self, group, gt, start, number=1):
        return Lesson.objects.create(group=group, group_teacher=gt, subject=self.python, teacher=gt.teacher,
                                     lesson_number=number, date=TODAY + dt.timedelta(days=1),
                                     start_time=dt.time(start), end_time=dt.time(start + 1))

    def test_move_refuses_teacher_conflict(self):
        gt2 = GroupTeacher.objects.create(group=self.g2, teacher=self.islam, subject=self.python)
        a = self._lesson(self.g1, self.gt1, 10)
        self._lesson(self.g2, gt2, 14)
        response = self.client.post(self.url("lesson-move", a.pk), {
            "date": str(TODAY + dt.timedelta(days=1)), "start_time": "14:30", "end_time": "15:30",
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Тренер «Islam» уже ведёт занятие в группе «PRO-02»", str(response.data))

    def test_move_to_free_time(self):
        a = self._lesson(self.g1, self.gt1, 10)
        response = self.client.post(self.url("lesson-move", a.pk), {
            "date": str(TODAY + dt.timedelta(days=2)), "start_time": "12:00", "end_time": "13:00",
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        a.refresh_from_db()
        self.assertTrue(a.schedule_overridden)
        self.assertEqual(a.start_time, dt.time(12))

    def test_add_slot_conflicting_with_teacher_is_refused(self):
        response = self.client.post(self.url("group-programs", self.g2.pk), {
            "teacher": self.islam.pk, "subject": self.python.pk,
            "slots": [{"day": "mon", "start": "16:30", "end": "18:00"}],
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("PRO-01", str(response.data))

    def test_week_listing(self):
        self._lesson(self.g1, self.gt1, 10)
        data = self.client.get(self.url("schedule"), {"start": str(TODAY), "end": str(TODAY + dt.timedelta(days=6))}).data
        self.assertEqual(len(data["lessons"]), 1)
        self.assertEqual(data["lessons"][0]["teacher"]["name"], "Islam")


class AttendanceTests(AssistantTestBase):
    def test_mark_and_correct(self):
        lesson = Lesson.objects.create(group=self.g1, group_teacher=self.gt1, subject=self.python, teacher=self.islam,
                                       lesson_number=1, date=TODAY, start_time=dt.time(16), end_time=dt.time(17))
        url = self.url("attendance-lesson", lesson.pk)
        response = self.client.post(url, [
            {"student": self.s1.pk, "status": "present"}, {"student": self.s2.pk, "status": "absent"},
        ], format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual((response.data["present"], response.data["absent"]), (1, 1))
        self.client.post(url, [{"student": self.s2.pk, "status": "late"}], format="json")
        self.assertEqual(Attendance.objects.get(lesson=lesson, student=self.s2).status, "late")
        day = self.client.get(self.url("attendance")).data
        self.assertEqual(day["lessons"][0]["present"], 2)

    def test_foreign_student_refused(self):
        lesson = Lesson.objects.create(group=self.g1, group_teacher=self.gt1, subject=self.python, teacher=self.islam,
                                       lesson_number=1, date=TODAY, start_time=dt.time(16), end_time=dt.time(17))
        other = Student.objects.create(first_name="Other", group=self.g2)
        response = self.client.post(self.url("attendance-lesson", lesson.pk), [{"student": other.pk, "status": "present"}],
                                    format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class SurveyAccessTests(AssistantTestBase):
    def test_assistant_manages_surveys_through_existing_api(self):
        response = self.client.post("/api/v1/feedback/surveys/", {
            "title": "Отзыв родителей", "audience": "parent", "group": self.g1.pk,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(Survey.objects.filter(title="Отзыв родителей", created_by=self.assistant).exists())
        self.assertEqual(self.client.get("/api/v1/feedback/analytics/overview/").status_code, status.HTTP_403_FORBIDDEN)


class LessonCancelTests(AssistantTestBase):
    def test_cancel(self):
        lesson = Lesson.objects.create(group=self.g1, group_teacher=self.gt1, subject=self.python, teacher=self.islam,
                                       lesson_number=1, date=TODAY + dt.timedelta(days=1), start_time=dt.time(16),
                                       end_time=dt.time(17))
        response = self.client.post(self.url("lesson-cancel", lesson.pk), {"reason": "Праздник", "reschedule": False})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        lesson.refresh_from_db()
        self.assertEqual(lesson.status, Lesson.Status.CANCELLED)


class SearchAndActivityTests(AssistantTestBase):
    def test_search_finds_students_groups_teachers_and_lessons(self):
        Lesson.objects.create(group=self.g1, group_teacher=self.gt1, subject=self.python, teacher=self.islam,
                              lesson_number=1, date=TODAY, start_time=dt.time(16), end_time=dt.time(17))
        data = self.client.get(self.url("search"), {"q": "islam"}).data
        self.assertEqual([s["id"] for s in data["students"]], [self.s1.pk])
        self.assertEqual([t["name"] for t in data["teachers"]], ["Islam"])
        self.assertEqual(data["lessons"][0]["group"]["name"], "PRO-01")
        data = self.client.get(self.url("search"), {"q": "PRO-0"}).data
        self.assertEqual([g["name"] for g in data["groups"]], ["PRO-01", "PRO-02"])

    def test_short_query_returns_nothing(self):
        self.assertEqual(self.client.get(self.url("search"), {"q": "a"}).data["students"], [])

    def test_search_is_assistant_only(self):
        client = APIClient()
        client.force_authenticate(self.islam.user)
        self.assertEqual(client.get(self.url("search"), {"q": "islam"}).status_code, status.HTTP_403_FORBIDDEN)

    def test_dashboard_activity_shows_transfers_and_deactivations(self):
        self.client.post(self.url("student-transfer", self.s1.pk), {"group": self.g2.pk})
        self.client.post(self.url("student-deactivate", self.s2.pk), {"reason": "relocation"})
        activity = self.client.get(self.url("dashboard")).data["activity"]
        details = [row["detail"] for row in activity]
        self.assertTrue(any("PRO-01 → PRO-02" in d for d in details), details)
        self.assertTrue(any(d.startswith("Деактивация") for d in details), details)

    def test_unmarked_past_lesson_needs_attention(self):
        Lesson.objects.create(group=self.g1, group_teacher=self.gt1, subject=self.python, teacher=self.islam,
                              lesson_number=1, date=TODAY - dt.timedelta(days=1), start_time=dt.time(16), end_time=dt.time(17))
        keys = [item["key"] for item in self.client.get(self.url("dashboard")).data["attention"]]
        self.assertIn("unmarked", keys)
        day = self.client.get(self.url("attendance"), {"unmarked": "1"}).data
        self.assertEqual(len(day["lessons"]), 1)

    def test_group_filter_by_weekday(self):
        data = self.client.get(self.url("groups"), {"day": "mon"}).data
        self.assertEqual([g["name"] for g in data["results"]], ["PRO-01"])
        self.assertEqual(self.client.get(self.url("groups"), {"day": "tue"}).data["count"], 0)

    def test_group_detail_today_and_next_lesson(self):
        for n, delta in ((1, 0), (2, 2)):
            Lesson.objects.create(group=self.g1, group_teacher=self.gt1, subject=self.python, teacher=self.islam,
                                  lesson_number=n, date=TODAY + dt.timedelta(days=delta), start_time=dt.time(16), end_time=dt.time(17))
        data = self.client.get(self.url("group-detail", self.g1.pk)).data
        self.assertEqual(data["today_lesson"]["lesson_number"], 1)
        self.assertEqual(data["next_lesson"]["lesson_number"], 2)
