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
    def _lesson(self, number=1, date=TODAY):
        return Lesson.objects.create(group=self.g1, group_teacher=self.gt1, subject=self.python, teacher=self.islam,
                                     lesson_number=number, date=date, start_time=dt.time(16), end_time=dt.time(17))

    def test_assistant_cannot_mark_attendance(self):
        lesson = self._lesson()
        response = self.client.post(self.url("attendance-lesson", lesson.pk),
                                    [{"student": self.s1.pk, "status": "present"}], format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Attendance.objects.filter(lesson=lesson).exists())

    def test_admin_still_marks_and_assistant_reads(self):
        lesson = self._lesson()
        admin_user = User.objects.create_superuser(username="root", email="r@o.kg", password=PASSWORD)
        admin_client = APIClient()
        admin_client.force_authenticate(admin_user)
        response = admin_client.post(self.url("attendance-lesson", lesson.pk), [
            {"student": self.s1.pk, "status": "present"}, {"student": self.s2.pk, "status": "absent"},
        ], format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        day = self.client.get(self.url("attendance")).data
        self.assertEqual((day["lessons"][0]["present"], day["lessons"][0]["absent"]), (1, 1))


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


class ReadOnlyRecordsTests(AssistantTestBase):
    """Attendance / homework are read-only for the Assistant — in the
    workspace API and in the trainers' academy API alike."""

    def setUp(self):
        super().setUp()
        from apps.academy.models import Homework, HomeworkResult

        self.Homework, self.HomeworkResult = Homework, HomeworkResult
        self.lessons = []
        for n, days_ago in ((1, 6), (2, 4), (3, 2)):
            lesson = Lesson.objects.create(
                group=self.g1, group_teacher=self.gt1, subject=self.python, teacher=self.islam, lesson_number=n,
                date=TODAY - dt.timedelta(days=days_ago), start_time=dt.time(16), end_time=dt.time(17),
                status=Lesson.Status.COMPLETED, topic=f"Тема {n}",
            )
            self.lessons.append(lesson)
        # s1 came every time; s2 came once, then missed twice.
        for lesson, s2_status in zip(self.lessons, ("present", "absent", "absent")):
            Attendance.objects.create(lesson=lesson, student=self.s1, status="present")
            Attendance.objects.create(lesson=lesson, student=self.s2, status=s2_status)
        self.hw = Homework.objects.create(lesson=self.lessons[1], title="DNS", deadline=TODAY - dt.timedelta(days=3))
        self.open_hw = Homework.objects.create(lesson=self.lessons[2], title="HTTP", deadline=TODAY + dt.timedelta(days=2))
        HomeworkResult.objects.create(homework=self.hw, student=self.s1, status="submitted")
        # a future lesson is not «held»
        Lesson.objects.create(group=self.g1, group_teacher=self.gt1, subject=self.python, teacher=self.islam,
                              lesson_number=4, date=TODAY + dt.timedelta(days=1), start_time=dt.time(16), end_time=dt.time(17))

    def test_group_attendance_summary_lessons_and_students(self):
        data = self.client.get(self.url("group-attendance", self.g1.pk)).data
        self.assertEqual(data["summary"]["lessons"], 3)
        self.assertEqual((data["summary"]["attended"], data["summary"]["absent"], data["summary"]["marked"]), (4, 2, 6))
        self.assertEqual(data["summary"]["percent"], 67)
        aida = next(s for s in data["students"] if s["id"] == self.s2.pk)
        self.assertEqual((aida["percent"], aida["consecutive_absences"]), (33, 2))
        self.assertEqual(data["students"][0]["id"], self.s2.pk)  # who misses most first

    def test_group_attendance_filters(self):
        absent = self.client.get(self.url("group-attendance", self.g1.pk), {"status": "absent"}).data
        self.assertEqual([l["lesson_number"] for l in absent["lessons"]], [3, 2])
        one = self.client.get(self.url("group-attendance", self.g1.pk), {"student": self.s2.pk}).data
        self.assertEqual([l["student_status"] for l in one["lessons"]], ["absent", "absent", "present"])
        today = self.client.get(self.url("group-attendance", self.g1.pk), {"period": "today"}).data
        self.assertEqual(today["summary"]["lessons"], 0)

    def test_lesson_detail_links_homework(self):
        data = self.client.get(self.url("lesson-detail", self.lessons[1].pk)).data
        self.assertEqual(data["attendance"]["attended"], 1)
        self.assertEqual(data["homeworks"][0]["title"], "DNS")
        self.assertEqual((data["homeworks"][0]["done"], data["homeworks"][0]["expected"]), (1, 2))

    def test_group_homework_and_detail(self):
        data = self.client.get(self.url("group-homework", self.g1.pk)).data
        statuses = {h["title"]: h["status"] for h in data["homeworks"]}
        # Past the deadline with a student who did not hand in: missing outranks review.
        self.assertEqual(statuses, {"DNS": "missing", "HTTP": "open"})
        self.assertEqual((data["summary"]["total"], data["summary"]["missing"], data["summary"]["review"]), (2, 1, 1))
        detail = self.client.get(self.url("homework-detail", self.hw.pk)).data
        states = {row["student"]["id"]: row["state"] for row in detail["students"]}
        self.assertEqual(states, {self.s1.pk: "review", self.s2.pk: "not_done"})

    def test_assistant_cannot_write_through_academy_api(self):
        lesson = self.lessons[0]
        attempts = [
            ("post", f"/api/v1/lessons/{lesson.pk}/attendance/", [{"student": self.s1.pk, "status": "absent"}]),
            ("post", "/api/v1/attendance/", {"lesson": lesson.pk, "student": self.s1.pk, "status": "absent"}),
            ("post", "/api/v1/homework/", {"lesson": lesson.pk, "title": "X"}),
            ("patch", f"/api/v1/homework/{self.hw.pk}/", {"title": "Y"}),
            ("delete", f"/api/v1/homework/{self.hw.pk}/", None),
            ("post", f"/api/v1/homework/{self.hw.pk}/results/", [{"student": self.s2.pk, "status": "checked"}]),
            ("post", f"/api/v1/lessons/{lesson.pk}/complete/", None),
        ]
        for method, url, body in attempts:
            with self.subTest(url=url, method=method):
                response = getattr(self.client, method)(url, body, format="json")
                self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.content)
        self.assertEqual(Attendance.objects.get(lesson=lesson, student=self.s1).status, "present")
        self.assertTrue(self.Homework.objects.filter(pk=self.hw.pk, title="DNS").exists())

    def test_trainer_keeps_write_access(self):
        lesson = Lesson.objects.create(group=self.g1, group_teacher=self.gt1, subject=self.python, teacher=self.islam,
                                       lesson_number=9, date=TODAY, start_time=dt.time(9), end_time=dt.time(10))
        trainer = APIClient()
        trainer.force_authenticate(self.islam.user)
        response = trainer.post(f"/api/v1/lessons/{lesson.pk}/attendance/",
                                [{"student": self.s2.pk, "status": "late"}], format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertEqual(Attendance.objects.get(lesson=lesson, student=self.s2).status, "late")

    def test_read_endpoints_refuse_writes(self):
        for name, arg in (("group-attendance", self.g1.pk), ("group-homework", self.g1.pk),
                          ("lesson-detail", self.lessons[0].pk), ("homework-detail", self.hw.pk)):
            with self.subTest(name=name):
                self.assertEqual(self.client.post(self.url(name, arg), {}).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)


class ControlTests(AssistantTestBase):
    def setUp(self):
        super().setUp()
        from apps.academy.models import Homework, HomeworkResult

        self.s1.enrollment_date = self.s2.enrollment_date = TODAY - dt.timedelta(days=60)
        self.s1.save()
        self.s2.save()
        for n in range(1, 6):
            lesson = Lesson.objects.create(
                group=self.g1, group_teacher=self.gt1, subject=self.python, teacher=self.islam, lesson_number=n,
                date=TODAY - dt.timedelta(days=12 - 2 * n), start_time=dt.time(16), end_time=dt.time(17),
                status=Lesson.Status.COMPLETED,
            )
            Attendance.objects.create(lesson=lesson, student=self.s1, status="present")
            Attendance.objects.create(lesson=lesson, student=self.s2, status="present" if n == 1 else "absent")
            hw = Homework.objects.create(lesson=lesson, title=f"HW {n}", deadline=lesson.date)
            HomeworkResult.objects.create(homework=hw, student=self.s1, status="checked", score=9)
        # A brand-new student: no lessons since they joined — never a problem.
        self.newcomer = Student.objects.create(first_name="New", group=self.g1, enrollment_date=TODAY)
        # A withdrawn student is not analysed at all.
        Student.objects.create(first_name="Gone", group=self.g1, status=Student.Status.WITHDRAWN, is_active=False)

    def test_statuses_categories_and_streaks(self):
        data = self.client.get(self.url("control")).data
        rows = {r["student_id"]: r for r in data["students"]}
        self.assertNotIn("Gone", [r["name"] for r in data["students"]])
        self.assertEqual(rows[self.s1.pk]["status"], "normal")
        aida = rows[self.s2.pk]
        self.assertEqual((aida["attendance"], aida["homework"]), (20, 0))
        self.assertEqual(aida["status"], "risk")
        self.assertEqual((aida["consecutive_absences"], aida["consecutive_missed_homework"]), (4, 5))
        self.assertTrue({"not_attending", "no_homework", "both", "risk", "frequent_absence"} <= set(aida["categories"]))
        self.assertEqual(rows[self.newcomer.pk]["status"], "no_data")
        self.assertEqual(data["students"][0]["student_id"], self.s2.pk)  # risk first
        self.assertEqual(data["kpis"]["risk"], 1)

    def test_category_filter_and_profile_timeline(self):
        data = self.client.get(self.url("control"), {"category": "both"}).data
        self.assertEqual([r["student_id"] for r in data["students"]], [self.s2.pk])
        profile = self.client.get(self.url("control-student", self.s2.pk)).data
        self.assertEqual(profile["activity"]["status"], "risk")
        self.assertEqual(profile["timeline"][0]["text"], "Не пришёл")

    def test_transfer_starts_a_fresh_stint(self):
        self.client.post(self.url("student-transfer", self.s2.pk), {"group": self.g2.pk})
        rows = {r["student_id"]: r for r in self.client.get(self.url("control")).data["students"]}
        self.assertEqual(rows[self.s2.pk]["status"], "no_data")

    def test_thresholds_come_from_settings(self):
        with self.settings(ASSISTANT_CONTROL_THRESHOLDS={"risk_attendance": 10}):
            rows = {r["student_id"]: r for r in self.client.get(self.url("control")).data["students"]}
        self.assertEqual(rows[self.s2.pk]["status"], "low")

    def test_control_is_read_only_and_assistant_only(self):
        self.assertEqual(self.client.post(self.url("control"), {}).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        trainer = APIClient()
        trainer.force_authenticate(self.islam.user)
        self.assertEqual(trainer.get(self.url("control")).status_code, status.HTTP_403_FORBIDDEN)


class MonthlyReportTests(AssistantTestBase):
    """«Месячный отчёт» over the previous (closed) month."""

    def setUp(self):
        super().setUp()
        from decimal import Decimal

        from apps.academy.models import Attendance, Homework, HomeworkResult
        from apps.feedback.models import QuestionOption, SurveyAnswer, SurveyAnswerOption, SurveyQuestion, SurveyResponse
        from apps.scholarships.models import (
            EligibilityStatus, ScholarshipAward, ScholarshipConfiguration, ScholarshipEvaluation, ScholarshipPeriod,
        )
        from django.utils import timezone

        self.end = TODAY.replace(day=1) - dt.timedelta(days=1)
        self.start = self.end.replace(day=1)
        early = self.start - dt.timedelta(days=40)
        Group.objects.filter(pk=self.g1.pk).update(start_date=early)
        Student.objects.filter(pk__in=[self.s1.pk, self.s2.pk]).update(enrollment_date=early)

        def lesson(day, number, **extra):
            return Lesson.objects.create(group=self.g1, group_teacher=self.gt1, subject=self.python, teacher=self.islam,
                                         lesson_number=number, date=day, start_time=dt.time(16), end_time=dt.time(17, 30),
                                         **{"status": Lesson.Status.COMPLETED, **extra})
        days = [self.start + dt.timedelta(days=n) for n in (1, 4, 8, 12)]
        lessons = [lesson(day, i + 1) for i, day in enumerate(days)]
        lesson(self.start + dt.timedelta(days=14), 9, status=Lesson.Status.CANCELLED)
        lesson(self.start - dt.timedelta(days=3), 10)  # previous month: not counted
        for item in lessons:
            Attendance.objects.create(lesson=item, student=self.s1, status=Attendance.Status.ABSENT)
            Attendance.objects.create(lesson=item, student=self.s2, status=Attendance.Status.PRESENT)
        for i, item in enumerate(lessons[:3]):
            hw = Homework.objects.create(lesson=item, title=f"ДЗ {i + 1}", deadline=item.date + dt.timedelta(days=2))
            HomeworkResult.objects.create(homework=hw, student=self.s1, status=HomeworkResult.Status.NOT_SUBMITTED)
            HomeworkResult.objects.create(homework=hw, student=self.s2, status=(
                HomeworkResult.Status.SUBMITTED if i == 0 else HomeworkResult.Status.CHECKED))

        survey = Survey.objects.create(title="Качество обучения", audience=Survey.Audience.STUDENT, group=self.g1,
                                       status=Survey.Status.PUBLISHED)
        rating = SurveyQuestion.objects.create(survey=survey, text="Оценка", order=1,
                                               question_type=SurveyQuestion.QuestionType.SINGLE_CHOICE)
        options = {n: QuestionOption.objects.create(question=rating, text=str(n), order=n) for n in range(1, 6)}
        text = SurveyQuestion.objects.create(survey=survey, text="Что улучшить?", order=2, is_required=False,
                                             question_type=SurveyQuestion.QuestionType.TEXT)

        def respond(day, score, comment):
            response = SurveyResponse.objects.create(
                survey=survey, visibility=SurveyResponse.Visibility.ANONYMOUS,
                submitted_at=timezone.make_aware(dt.datetime.combine(day, dt.time(12))),
            )
            answer = SurveyAnswer.objects.create(response=response, question=rating)
            SurveyAnswerOption.objects.create(answer=answer, option=options[score])
            SurveyAnswer.objects.create(response=response, question=text, text_value=comment)
        respond(self.start + dt.timedelta(days=5), 5, "Больше практики!")
        respond(self.start + dt.timedelta(days=6), 1, "больше практики")
        respond(self.end + dt.timedelta(days=1), 5, "Другой месяц")

        config = ScholarshipConfiguration(name="Test")
        period = ScholarshipPeriod.objects.create(
            period_start=self.start - dt.timedelta(days=30), period_end=self.start - dt.timedelta(days=1),
            evaluation_date=self.end,
            **{f: getattr(config, f) for f in (
                "attendance_weight", "homework_weight", "feedback_weight", "subject_aggregation",
                "late_homework_credit", "min_overall_score", "min_marked_lessons", "require_complete_feedback",
            )},
        )
        evaluation = ScholarshipEvaluation.objects.create(
            period=period, student=self.s2, student_name="Aida K", group_name="PRO-01",
            eligibility_status=EligibilityStatus.ELIGIBLE, overall_score=Decimal("92.50"),
        )
        ScholarshipAward.objects.create(period=period, student=self.s2, evaluation=evaluation, rank=1,
                                        award_date=self.end, amount=Decimal("4000"))

    def report(self, **params):
        return self.client.get(self.url("monthly-report"), {"year": self.start.year, "month": self.start.month, **params})

    def test_sections_from_real_data(self):
        response = self.report()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertTrue(data["is_complete"])
        att = data["attendance"]
        self.assertEqual((att["lessons"], att["marked"], att["attended"], att["absent"], att["percent"]), (4, 8, 4, 4, 50))
        self.assertEqual(att["groups"][0]["group"]["name"], "PRO-01")
        hw = data["homework"]
        self.assertEqual((hw["given"], hw["expected"], hw["done"], hw["not_done"], hw["pending"], hw["percent"]),
                         (3, 6, 3, 3, 1, 50))

        students = data["students"]
        absent = students["attendance_attention"][0]
        self.assertEqual((absent["student_id"], absent["attendance"], absent["consecutive_absences"]), (self.s1.pk, 0, 4))
        self.assertEqual([r["student_id"] for r in students["homework_attention"]], [self.s1.pk])
        self.assertEqual([r["student_id"] for r in students["risk"]], [self.s1.pk])
        self.assertEqual(students["activity"]["normal"], 1)
        self.assertEqual(data["overview"]["students_at_risk"], 1)

        surveys = data["surveys"]
        self.assertEqual((surveys["surveys"], surveys["participants"], surveys["participation"]), (1, 2, 100))
        self.assertEqual((surveys["average"], surveys["low_ratings"]), (3.0, 1))
        self.assertEqual(surveys["quotes"][0]["text"].lower().strip("!"), "больше практики")
        self.assertEqual(surveys["quotes"][0]["count"], 2)
        self.assertNotIn("Другой месяц", [q["text"] for q in surveys["quotes"]])

        sch = data["scholarships"]
        self.assertEqual((sch["awards"], sch["recipients"], sch["total_amount"]), (1, 1, 4000))
        self.assertIn("1 место", sch["rows"][0]["reason"])
        self.assertIn("В зоне риска: 1 студент.", data["conclusions"]["attention"])

    def test_no_trainer_kpi(self):
        """A student's trainer is context of their group; trainer KPI, ratings
        and workload stay in the Team Lead's report."""
        body = self.report().content.decode().lower()
        for word in ("kpi", "rating_trainer", "teacher_kpi", "workload"):
            self.assertNotIn(word, body)

    def test_period_validation(self):
        future = TODAY.replace(day=28) + dt.timedelta(days=10)
        self.assertEqual(self.report(year=future.year, month=future.month).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.report(month=13).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.report(year="x").status_code, status.HTTP_400_BAD_REQUEST)
        current = self.client.get(self.url("monthly-report"))
        self.assertEqual((current.data["year"], current.data["month"]), (TODAY.year, TODAY.month))
        self.assertFalse(current.data["is_complete"])

    def test_read_only_and_assistant_only(self):
        self.assertEqual(self.client.post(self.url("monthly-report"), {}).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        client = APIClient()
        client.force_authenticate(self.islam.user)
        self.assertEqual(client.get(self.url("monthly-report")).status_code, status.HTTP_403_FORBIDDEN)


class MonthlyReportPdfTests(MonthlyReportTests):
    """The PDF is the same report, rendered: same month, same permission."""

    def pdf_url(self, year=None, month=None):
        return self.url("monthly-report-pdf", year or self.start.year, month or self.start.month)

    def test_pdf_download(self):
        from apps.assistant.monthly_pdf import MONTH_SLUGS

        response = self.client.get(self.pdf_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(
            response["Content-Disposition"],
            f'attachment; filename="monthly_report_{MONTH_SLUGS[self.start.month - 1]}_{self.start.year}.pdf"',
        )
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertGreaterEqual(response.content.count(b"/Type /Page\n") + response.content.count(b"/Type /Page "), 1)

    def test_pdf_uses_the_same_report_for_the_requested_month(self):
        from unittest import mock

        from apps.assistant import monthly

        with mock.patch("apps.assistant.monthly_pdf.build_monthly_pdf", return_value=b"%PDF-1.4") as build:
            self.client.get(self.pdf_url())
        report = build.call_args.args[0]
        expected = monthly.monthly_report(self.start.year, self.start.month)
        self.assertEqual((report["year"], report["month"], report["start"], report["end"]),
                         (self.start.year, self.start.month, self.start, self.end))
        for key in ("overview", "attendance", "homework", "surveys", "scholarships", "conclusions"):
            self.assertEqual(report[key], expected[key], key)
        self.assertEqual(report["students"]["risk"][0]["reason"], "Нет активности")

    def test_long_names_wrap_and_never_overflow(self):
        from reportlab.pdfbase import pdfmetrics

        from apps.academy.services.monthly_report_pdf import _REGULAR, _ensure_fonts
        from apps.assistant.monthly_pdf import _wrap

        _ensure_fonts()
        Student.objects.filter(pk=self.s1.pk).update(
            first_name="Абдыкадыр-Абдырахманова-Мамыткожоева" * 2, last_name="Нурсултановна Кыдырмаматова")
        self.assertEqual(self.client.get(self.pdf_url()).status_code, status.HTTP_200_OK)
        lines = _wrap("Очень-очень-длинное-имя-без-пробелов-которое-не-влезает " * 3, _REGULAR, 7.8, 80)
        self.assertGreater(len(lines), 3)
        self.assertTrue(all(pdfmetrics.stringWidth(line, _REGULAR, 7.8) <= 80 for line in lines))
        self.assertIn("не-влезает", "".join(lines))  # wrapped, not cut

    def test_pdf_period_and_permissions(self):
        future = TODAY.replace(day=28) + dt.timedelta(days=10)
        self.assertEqual(self.client.get(self.pdf_url(future.year, future.month)).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.get(self.pdf_url(month=13)).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(APIClient().get(self.pdf_url()).status_code, status.HTTP_401_UNAUTHORIZED)
        lead = User.objects.create_user(username="lead", email="l@o.kg", password=PASSWORD, role=User.Role.TEAM_LEAD)
        for user in (self.islam.user, lead):
            client = APIClient()
            client.force_authenticate(user)
            self.assertEqual(client.get(self.pdf_url()).status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.post(self.pdf_url()).status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
