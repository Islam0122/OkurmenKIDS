"""Attendance & homework matrix: statuses, statistics, warnings, the four
roles' access (checked on the server), cell editing with the audit log and
the Excel exports."""
from __future__ import annotations

import datetime as dt
import io

from django.test import TestCase
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.academy.models import (
    Attendance, Course, Group, GroupSchedule, GroupTeacher, Homework, HomeworkResult, Lesson, Room, Student,
)
from apps.users.models import Subject, Teacher, User

from .models import AttendanceChangeLog, GroupAssistant, MatrixSettings, TeamLeadDirection

TODAY = dt.date.today()
# A closed month: last month, so every lesson in it is held.
MONTH = (TODAY.replace(day=1) - dt.timedelta(days=1)).replace(day=1)
BASE = "/api/v1/attendance-matrix"


def user(username, role, **extra) -> User:
    return User.objects.create_user(username=username, email=f"{username}@okurmen.kg", password="x",
                                    first_name=username.capitalize(), role=role, is_verified=True, **extra)


def teacher(username) -> Teacher:
    return Teacher.objects.create(user=user(username, User.Role.TEACHER))


class MatrixBase(TestCase):
    def setUp(self):
        self.python, _ = Subject.objects.get_or_create(name="Python")
        self.english, _ = Subject.objects.get_or_create(name="English")
        self.course = Course.objects.create(name="Programming", count_lesson=40)
        self.course.subjects.set([self.python])
        self.en_course = Course.objects.create(name="English course", count_lesson=40)
        self.en_course.subjects.set([self.english])
        self.room = Room.objects.create(name="A1")
        self.islam = teacher("islam")
        self.aibek = teacher("aibek")
        self.group = Group.objects.create(name="Prog SOFT 1", course=self.course, start_date=MONTH - dt.timedelta(days=60))
        self.other = Group.objects.create(name="English 1", course=self.en_course, start_date=MONTH - dt.timedelta(days=60))
        self.gt = GroupTeacher.objects.create(group=self.group, teacher=self.islam, subject=self.python)
        self.gt_other = GroupTeacher.objects.create(group=self.other, teacher=self.aibek, subject=self.english)
        GroupSchedule.objects.create(group=self.group, teacher=self.islam, subject=self.python, day_of_week="mon",
                                     start_time=dt.time(16), end_time=dt.time(17), room=self.room)
        GroupSchedule.objects.create(group=self.other, teacher=self.aibek, subject=self.english, day_of_week="tue",
                                     start_time=dt.time(16), end_time=dt.time(17), room=self.room)
        enrolled = MONTH - dt.timedelta(days=30)
        self.s1 = Student.objects.create(first_name="Бекнур", last_name="Абдыбеков", group=self.group, enrollment_date=enrolled)
        self.s2 = Student.objects.create(first_name="Талант", last_name="Аманжолов", group=self.group, enrollment_date=enrolled)
        self.s3 = Student.objects.create(first_name="Эрбол", last_name="Зулпукаров", group=self.group, enrollment_date=enrolled)
        self.o1 = Student.objects.create(first_name="Other", last_name="Student", group=self.other, enrollment_date=enrolled)
        self.lessons = [self.lesson(self.group, self.gt, self.islam, n, MONTH + dt.timedelta(days=2 * n)) for n in range(5)]
        self.other_lesson = self.lesson(self.other, self.gt_other, self.aibek, 0, MONTH + dt.timedelta(days=3))
        self.client = APIClient()

    def lesson(self, group, gt, t, n, date, **extra):
        return Lesson.objects.create(group=group, group_teacher=gt, teacher=t, subject=gt.subject, lesson_number=n + 1,
                                     date=date, start_time=dt.time(16), end_time=dt.time(17),
                                     status=extra.pop("status", Lesson.Status.COMPLETED), **extra)

    def mark(self, lesson, student, status, **extra):
        return Attendance.objects.create(lesson=lesson, student=student, status=status, **extra)

    def as_user(self, u):
        self.client.force_authenticate(u)
        return self.client

    def matrix(self, u, group=None, **params):
        params.setdefault("date", MONTH.isoformat())
        return self.as_user(u).get(f"{BASE}/groups/{(group or self.group).pk}/", params)

    @property
    def admin(self):
        return user("admin1", User.Role.ADMIN)


class StatusAndStatsTests(MatrixBase):
    def setUp(self):
        super().setUp()
        hw0 = Homework.objects.create(lesson=self.lessons[0], title="HW0", deadline=self.lessons[0].date + dt.timedelta(days=1))
        Homework.objects.create(lesson=self.lessons[1], title="HW1", deadline=self.lessons[1].date + dt.timedelta(days=1))
        HomeworkResult.objects.create(homework=hw0, student=self.s1, status="checked", score=9)
        # s1: P(hw done) P(hw missed) E A A ; s2: all present; s3: nothing marked.
        for lesson, status in zip(self.lessons, ["present", "present", "excused", "absent", "absent"]):
            self.mark(lesson, self.s1, status, excuse_reason="Болел" if status == "excused" else "")
        for lesson in self.lessons:
            self.mark(lesson, self.s2, "late" if lesson == self.lessons[2] else "present")

    def test_cells_codes_keep_attendance_and_homework_apart(self):
        data = self.matrix(self.islam.user).json()
        self.assertEqual(len(data["columns"]), 5)
        row = next(r for r in data["rows"] if r["student"]["id"] == self.s1.pk)
        self.assertEqual([c["code"] for c in row["cells"]], ["done", "partial", "excused", "absent", "absent"])
        self.assertEqual([c["homework"] for c in row["cells"]][:2], ["done", "missed"])
        s = row["stats"]
        self.assertEqual((s["present"], s["excused"], s["absent"], s["percent"]), (2, 1, 2, 40))
        self.assertEqual((s["hw_done"], s["hw_missed"], s["consecutive_absences"]), (1, 1, 2))
        empty = next(r for r in data["rows"] if r["student"]["id"] == self.s3.pk)
        self.assertEqual({c["code"] for c in empty["cells"]}, {"empty"})
        self.assertIsNone(empty["stats"]["percent"])

    def test_summary_cards_and_group_totals(self):
        data = self.matrix(self.islam.user).json()
        s = data["summary"]
        # present: s1 2 + s2 5 = 7, excused 1, absent 2 → marked 10, unmarked s3 5.
        self.assertEqual((s["present"], s["excused"], s["absent"], s["unmarked"], s["marked"]), (7, 1, 2, 5, 10))
        self.assertEqual(s["percent"], 70)
        self.assertEqual(s["cards"]["absent"], {"count": 2, "percent": 20})
        # Due homework without a result is missed: HW0 — s2, s3; HW1 — s1, s2, s3.
        self.assertEqual((s["hw_missed"], s["hw_done"], s["hw_due"]), (5, 1, 6))
        self.assertEqual(data["columns"][3]["stats"]["percent"], 50)
        self.assertEqual(data["ranking"][0]["student"]["id"], self.s2.pk)

    def test_warnings_follow_configurable_thresholds(self):
        row = next(r for r in self.matrix(self.islam.user).json()["rows"] if r["student"]["id"] == self.s1.pk)
        self.assertEqual({w["code"] for w in row["warnings"]}, {"absences_in_row"})
        settings = MatrixSettings.load()
        settings.monthly_absences_attention, settings.monthly_absences_critical = 1, 2
        settings.save()
        row = next(r for r in self.matrix(self.islam.user).json()["rows"] if r["student"]["id"] == self.s1.pk)
        self.assertEqual(row["level"], "critical")

    def test_cancelled_lessons_and_other_months_are_not_columns(self):
        self.lesson(self.group, self.gt, self.islam, 10, MONTH + dt.timedelta(days=20), status=Lesson.Status.CANCELLED)
        self.lesson(self.group, self.gt, self.islam, 11, MONTH - dt.timedelta(days=3))
        self.assertEqual(len(self.matrix(self.islam.user).json()["columns"]), 5)

    def test_week_and_day_periods(self):
        day = self.matrix(self.islam.user, period="day", date=self.lessons[1].date.isoformat()).json()
        self.assertEqual([c["lesson_id"] for c in day["columns"]], [self.lessons[1].pk])
        week = self.matrix(self.islam.user, period="week", date=self.lessons[1].date.isoformat()).json()
        self.assertTrue(all(week["period"]["start"] <= c["date"] <= week["period"]["end"] for c in week["columns"]))

    def test_student_joined_later_has_no_lesson_before(self):
        self.s3.enrollment_date = self.lessons[3].date
        self.s3.save()
        row = next(r for r in self.matrix(self.islam.user).json()["rows"] if r["student"]["id"] == self.s3.pk)
        self.assertEqual([c["code"] for c in row["cells"]], ["no_lesson"] * 3 + ["empty"] * 2)
        self.assertEqual(row["stats"]["lessons"], 2)

    def test_filters(self):
        rows = self.matrix(self.islam.user, status="absent").json()["rows"]
        self.assertEqual([r["student"]["id"] for r in rows], [self.s1.pk])
        rows = self.matrix(self.islam.user, search="тал").json()["rows"]
        self.assertEqual([r["student"]["id"] for r in rows], [self.s2.pk])


class AccessTests(MatrixBase):
    def test_trainer_sees_only_own_groups_and_own_lessons(self):
        self.assertEqual(self.matrix(self.islam.user).status_code, 200)
        self.assertEqual(self.matrix(self.islam.user, group=self.other).status_code, 404)
        # A colleague's program in the same group stays private.
        gt2 = GroupTeacher.objects.create(group=self.group, teacher=self.aibek, subject=self.english)
        foreign = self.lesson(self.group, gt2, self.aibek, 0, MONTH + dt.timedelta(days=1))
        ids = [c["lesson_id"] for c in self.matrix(self.islam.user).json()["columns"]]
        self.assertNotIn(foreign.pk, ids)
        r = self.as_user(self.islam.user).put(f"{BASE}/cell/", {"lesson": foreign.pk, "student": self.s1.pk,
                                                                "attendance": "present"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_assistant_only_assigned_groups_and_edit_by_permission(self):
        a = user("asel", User.Role.ASSISTANT)
        self.assertEqual(self.matrix(a).status_code, 404)
        assignment = GroupAssistant.objects.create(group=self.group, assistant=a, can_edit=False)
        data = self.matrix(a).json()
        self.assertEqual((data["capabilities"]["can_edit"], data["capabilities"]["can_comment"]), (False, True))
        cell = {"lesson": self.lessons[0].pk, "student": self.s1.pk}
        r = self.as_user(a).put(f"{BASE}/cell/", {**cell, "attendance": "present"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.mark(self.lessons[0], self.s1, "present")
        r = self.as_user(a).put(f"{BASE}/cell/", {**cell, "comment": "Опоздал на 5 минут"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        assignment.can_edit = True
        assignment.save()
        r = self.as_user(a).put(f"{BASE}/cell/", {**cell, "attendance": "absent"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(AttendanceChangeLog.objects.filter(actor=a).count(), 2)
        self.assertEqual(self.matrix(a, group=self.other).status_code, 404)

    def test_team_lead_sees_direction_and_is_read_only(self):
        tl = user("lead", User.Role.TEAM_LEAD)
        self.assertEqual(self.matrix(tl, group=self.other).status_code, 200)  # no direction — whole academy
        TeamLeadDirection.objects.create(team_lead=tl, subject=self.python)
        self.assertEqual(self.matrix(tl).status_code, 200)
        self.assertEqual(self.matrix(tl, group=self.other).status_code, 404)
        r = self.as_user(tl).put(f"{BASE}/cell/", {"lesson": self.lessons[0].pk, "student": self.s1.pk,
                                                   "attendance": "present"}, format="json")
        self.assertEqual(r.status_code, 403)
        overview = self.as_user(tl).get(f"{BASE}/overview/", {"date": MONTH.isoformat()}).json()
        self.assertEqual([g["name"] for g in overview["groups"]], [self.group.name])

    def test_operations_director_views_academy_edits_only_with_setting(self):
        od = user("ops", User.Role.OPERATIONS_DIRECTOR)
        self.assertEqual(self.matrix(od).status_code, 200)  # passes the staff-only isolation middleware
        self.assertEqual(self.matrix(od, group=self.other).status_code, 200)
        cell = {"lesson": self.lessons[0].pk, "student": self.s1.pk, "attendance": "present"}
        self.assertEqual(self.as_user(od).put(f"{BASE}/cell/", cell, format="json").status_code, 403)
        settings = MatrixSettings.load()
        settings.operations_director_can_edit = True
        settings.save()
        self.assertEqual(self.as_user(od).put(f"{BASE}/cell/", cell, format="json").status_code, 200)

    def test_other_roles_are_refused(self):
        for role in (User.Role.HR_MANAGER, User.Role.ACCOUNTANT, User.Role.MARKETING):
            u = user(f"u_{role}", role)
            self.assertEqual(self.matrix(u).status_code, 403, role)

    def test_only_admin_changes_edit_permissions(self):
        od = user("ops", User.Role.OPERATIONS_DIRECTOR)
        r = self.as_user(od).patch(f"{BASE}/settings/", {"monthly_absences_attention": 2}, format="json")
        self.assertEqual(r.status_code, 200)
        r = self.as_user(od).patch(f"{BASE}/settings/", {"operations_director_can_edit": True}, format="json")
        self.assertEqual(r.status_code, 403)
        r = self.as_user(self.islam.user).patch(f"{BASE}/settings/", {"monthly_absences_attention": 2}, format="json")
        self.assertEqual(r.status_code, 403)
        r = self.as_user(self.admin).patch(f"{BASE}/settings/", {"operations_director_can_edit": True}, format="json")
        self.assertEqual(r.status_code, 200)


class CellEditTests(MatrixBase):
    def put(self, u, **data):
        return self.as_user(u).put(f"{BASE}/cell/", {"lesson": self.lessons[0].pk, "student": self.s1.pk, **data}, format="json")

    def test_mark_creates_one_record_and_logs(self):
        r = self.put(self.islam.user, attendance="present", comment="Молодец")
        self.assertEqual(r.status_code, 200)
        self.put(self.islam.user, attendance="absent")
        self.assertEqual(Attendance.objects.filter(lesson=self.lessons[0], student=self.s1).count(), 1)
        mark = Attendance.objects.get(lesson=self.lessons[0], student=self.s1)
        self.assertEqual((mark.status, mark.comment, mark.updated_by), ("absent", "Молодец", self.islam.user))
        body = self.as_user(self.islam.user).get(f"{BASE}/cell/", {"lesson": self.lessons[0].pk, "student": self.s1.pk}).json()
        self.assertEqual(len(body["history"]), 2)
        self.assertEqual(body["history"][0]["changes"][0]["after"], "Отсутствовал")
        self.assertEqual(body["updated_by"]["id"], self.islam.user.pk)

    def test_excused_needs_a_reason(self):
        self.assertEqual(self.put(self.islam.user, attendance="excused").status_code, 400)
        r = self.put(self.islam.user, attendance="excused", excuse_reason="Справка от врача")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["excuse_reason"], "Справка от врача")
        # Leaving «excused» clears the reason.
        self.put(self.islam.user, attendance="present")
        self.assertEqual(Attendance.objects.get(lesson=self.lessons[0], student=self.s1).excuse_reason, "")

    def test_homework_is_stored_separately(self):
        self.assertEqual(self.put(self.islam.user, homework="done").status_code, 400)  # no homework set
        hw1 = Homework.objects.create(lesson=self.lessons[0], title="A")
        hw2 = Homework.objects.create(lesson=self.lessons[0], title="B")
        HomeworkResult.objects.create(homework=hw1, student=self.s1, status="checked", score=10)
        r = self.put(self.islam.user, attendance="absent", homework="done")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(HomeworkResult.objects.get(homework=hw1, student=self.s1).status, "checked")  # kept
        self.assertEqual(HomeworkResult.objects.get(homework=hw2, student=self.s1).status, "submitted")
        self.assertEqual(Attendance.objects.get(lesson=self.lessons[0], student=self.s1).status, "absent")
        self.put(self.islam.user, homework="missed")
        self.assertEqual(set(HomeworkResult.objects.filter(student=self.s1).values_list("status", flat=True)), {"not_submitted"})

    def test_future_and_cancelled_lessons_are_locked(self):
        future = self.lesson(self.group, self.gt, self.islam, 20, TODAY + dt.timedelta(days=3), status=Lesson.Status.SCHEDULED)
        r = self.as_user(self.islam.user).put(f"{BASE}/cell/", {"lesson": future.pk, "student": self.s1.pk,
                                                                "attendance": "present"}, format="json")
        self.assertEqual(r.status_code, 400)
        Lesson.objects.filter(pk=self.lessons[0].pk).update(status=Lesson.Status.CANCELLED)
        self.assertEqual(self.put(self.islam.user, attendance="present").status_code, 403)

    def test_student_of_another_group_is_refused(self):
        r = self.as_user(self.admin).put(f"{BASE}/cell/", {"lesson": self.lessons[0].pk, "student": self.o1.pk,
                                                           "attendance": "present"}, format="json")
        self.assertEqual(r.status_code, 400)


class ExportTests(MatrixBase):
    def test_group_export_keeps_colours(self):
        self.mark(self.lessons[0], self.s1, "present")
        self.mark(self.lessons[1], self.s1, "absent")
        r = self.matrix(self.islam.user)
        self.assertEqual(r.status_code, 200)
        r = self.as_user(self.islam.user).get(f"{BASE}/groups/{self.group.pk}/export/", {"date": MONTH.isoformat()})
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])
        ws = load_workbook(io.BytesIO(r.content))["Посещаемость"]
        names = [ws.cell(row=row, column=2).value for row in range(6, 9)]
        row = 6 + names.index(str(self.s1))
        self.assertEqual(ws.cell(row=row, column=3).value, "✓")
        self.assertEqual(ws.cell(row=row, column=3).fill.fgColor.rgb, "002F8F5B")
        self.assertEqual(ws.cell(row=row, column=4).fill.fgColor.rgb, "00E5533D")
        self.assertEqual(ws.cell(row=9, column=2).value, "Итого по группе")

    def test_overview_export_for_operations_director(self):
        od = user("ops", User.Role.OPERATIONS_DIRECTOR)
        self.mark(self.other_lesson, self.o1, "absent")
        r = self.as_user(od).get(f"{BASE}/overview/export/", {"date": MONTH.isoformat()})
        self.assertEqual(r.status_code, 200)
        wb = load_workbook(io.BytesIO(r.content))
        self.assertEqual(wb.sheetnames, ["Группы", "Тренеры", "Проблемные студенты", "Уважительные причины", "Ассистенты", "Динамика"])
        groups = {wb["Группы"].cell(row=i, column=1).value for i in range(5, 7)}
        self.assertEqual(groups, {self.group.name, self.other.name})


class OverviewTests(MatrixBase):
    def test_overview_matches_group_matrix(self):
        for lesson in self.lessons:
            self.mark(lesson, self.s1, "present")
            self.mark(lesson, self.s2, "absent")
        admin = self.admin
        overview = self.as_user(admin).get(f"{BASE}/overview/", {"date": MONTH.isoformat()}).json()
        group = next(g for g in overview["groups"] if g["id"] == self.group.pk)
        matrix = self.matrix(admin).json()["summary"]
        self.assertEqual((group["percent"], group["absent"], group["present"]), (matrix["percent"], matrix["absent"], matrix["present"]))
        self.assertIn(self.s2.pk, [p["student"]["id"] for p in overview["problem_students"]])
        self.assertEqual(overview["problem_students"][0]["level"], "critical")  # 5 absences
        islam = next(t for t in overview["trainers"] if t["id"] == self.islam.pk)
        self.assertEqual(islam["lessons"], 5)
        self.assertEqual(len(overview["trend"]), 6)
        self.assertEqual(overview["trend"][-1]["percent"], 50)

    def test_filters_by_direction_and_trainer(self):
        admin = self.admin
        r = self.as_user(admin).get(f"{BASE}/overview/", {"date": MONTH.isoformat(), "subject": self.english.pk}).json()
        self.assertEqual([g["id"] for g in r["groups"]], [self.other.pk])
        r = self.as_user(admin).get(f"{BASE}/overview/", {"date": MONTH.isoformat(), "teacher": self.islam.pk}).json()
        self.assertEqual([g["id"] for g in r["groups"]], [self.group.pk])
        meta = self.as_user(admin).get(f"{BASE}/meta/").json()
        self.assertEqual({s["name"] for s in meta["subjects"]}, {"Python", "English"})


class ReviewTests(MatrixBase):
    """Team Lead: checks excused reasons, assistants' work and the history."""

    def test_excused_reasons_assistants_and_history_in_overview(self):
        self.mark(self.lessons[0], self.s1, "excused", excuse_reason="Справка от врача")
        self.mark(self.lessons[1], self.s2, "excused")  # an old mark with no reason
        a = user("asel", User.Role.ASSISTANT)
        GroupAssistant.objects.create(group=self.group, assistant=a, can_edit=True)
        r = self.as_user(a).put(f"{BASE}/cell/", {"lesson": self.lessons[2].pk, "student": self.s3.pk,
                                                  "attendance": "absent", "comment": "Не дозвонились"}, format="json")
        self.assertEqual(r.status_code, 200)
        tl = user("lead", User.Role.TEAM_LEAD)
        TeamLeadDirection.objects.create(team_lead=tl, subject=self.python)
        data = self.as_user(tl).get(f"{BASE}/overview/", {"date": MONTH.isoformat()}).json()
        reasons = {e["student"]["id"]: e for e in data["excused"]}
        self.assertEqual(reasons[self.s1.pk]["reason"], "Справка от врача")
        self.assertTrue(reasons[self.s2.pk]["missing_reason"])
        self.assertEqual(len(data["assistants"]), 1)
        self.assertEqual((data["assistants"][0]["user"]["id"], data["assistants"][0]["changes"],
                          data["assistants"][0]["comments"], data["assistants"][0]["groups"]), (a.pk, 1, 1, [self.group.name]))
        self.assertEqual(data["history"][0]["actor"]["id"], a.pk)
        self.assertIn("Отсутствовал", [c["after"] for c in data["history"][0]["changes"]])

    def test_review_is_scoped_to_the_direction(self):
        self.mark(self.other_lesson, self.o1, "excused", excuse_reason="Семья")
        tl = user("lead", User.Role.TEAM_LEAD)
        TeamLeadDirection.objects.create(team_lead=tl, subject=self.python)
        data = self.as_user(tl).get(f"{BASE}/overview/", {"date": MONTH.isoformat()}).json()
        self.assertEqual(data["excused"], [])

    def test_group_matrix_lists_trainers_for_the_filter(self):
        gt2 = GroupTeacher.objects.create(group=self.group, teacher=self.aibek, subject=self.english)
        self.lesson(self.group, gt2, self.aibek, 0, MONTH + dt.timedelta(days=1))
        admin = self.admin
        data = self.matrix(admin).json()
        self.assertEqual({t["id"] for t in data["trainers"]}, {self.islam.pk, self.aibek.pk})
        filtered = self.matrix(admin, teacher=self.aibek.pk).json()
        self.assertEqual(len(filtered["columns"]), 1)
        self.assertEqual(len(filtered["trainers"]), 2)  # options stay complete
