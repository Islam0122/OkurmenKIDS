"""Parallel lessons (shared classroom sessions): several groups, one room, one
shared trainer — one lesson (services.parallel_sessions, /api/v1/parallel-lessons/).
Only absolute imports — see the note in apps/academy/tests.py."""
from __future__ import annotations

import datetime as dt
import threading
from unittest import skipUnless

from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from apps.academy.models import (
    Attendance,
    Course,
    CourseLessonPlan,
    Group,
    GroupTeacher,
    Homework,
    Lesson,
    ParallelSession,
    ParallelSessionGroup,
    Room,
    Student,
)
from apps.academy.services import parallel_sessions as service
from apps.academy.services import schedule_board
from apps.academy.services.analytics import teachers as teacher_analytics
from apps.academy.services.lesson_move import move_lesson
from apps.academy.services.monthly_report import compute_monthly_stats
from apps.users.models import Subject, Teacher, User

PASSWORD = "Str0ngPassw0rd!"
DAY = dt.date(2026, 11, 26)
URL = "/api/v1/parallel-lessons/"
T = dt.time


def make_user(username, role=User.Role.TEACHER):
    return User.objects.create_user(username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
                                    first_name=username.capitalize(), last_name="Test", role=role, is_verified=True)


class ParallelFixture:
    """Ten groups of three students; Islam teaches Python in the first four,
    Aibek in the rest; rooms 101 and 102."""

    def build(self):
        self.python = Subject.objects.get_or_create(name="Python")[0]
        self.course = Course.objects.create(name="Programming", count_lesson=40)
        for n in range(1, 9):
            CourseLessonPlan.objects.create(course=self.course, lesson_number=n, subject=self.python, topic=f"T{n}")
        self.islam_user = make_user("islam")
        self.islam = Teacher.objects.create(user=self.islam_user)
        self.aibek_user = make_user("aibek")
        self.aibek = Teacher.objects.create(user=self.aibek_user)
        self.room = Room.objects.create(name="101")
        self.room2 = Room.objects.create(name="102")
        self.groups, self.programs = [], {}
        for i in range(10):
            group = Group.objects.create(name=f"G{i + 1:02d}", course=self.course, start_date=DAY - dt.timedelta(days=60))
            teacher = self.islam if i < 4 else self.aibek
            self.programs[group.pk] = GroupTeacher.objects.create(group=group, teacher=teacher, subject=self.python)
            for s in range(3):
                Student.objects.create(first_name=f"S{s}", last_name=group.name, group=group)
            self.groups.append(group)
        self.admin = make_user("root", User.Role.ADMIN)
        self.assistant = make_user("assist", User.Role.ASSISTANT)
        self.lead = make_user("lead", User.Role.TEAM_LEAD)
        self.accountant = make_user("buh", User.Role.ACCOUNTANT)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def payload(self, groups, *, teacher=None, room=None, start=T(15), end=T(16), date=DAY, **extra):
        return {"teacher": (teacher or self.islam).pk, "room": (room or self.room).pk, "date": str(date),
                "start_time": start.strftime("%H:%M"), "end_time": end.strftime("%H:%M"),
                "groups": [g.pk for g in groups], "topic": "Общая тема", **extra}

    def create(self, groups, **kwargs):
        response = self.client_for(self.assistant).post(URL, self.payload(groups, **kwargs), format="json")
        return response

    def session(self, groups, **kwargs) -> ParallelSession:
        response = self.create(groups, **kwargs)
        assert response.status_code == 201, response.data
        return ParallelSession.objects.get(pk=response.data["id"])

    def regular_lesson(self, group, start, end, *, room=None, teacher=None, date=DAY, number=1):
        program = self.programs[group.pk]
        return Lesson.objects.create(group=group, group_teacher=program, teacher=teacher or program.teacher,
                                     subject=self.python, lesson_number=number, date=date, start_time=start,
                                     end_time=end, room=room)

    def mark_all(self, session, status=Attendance.Status.PRESENT, user=None, groups=None):
        client = self.client_for(user or self.islam_user)
        for lesson in session.lessons.exclude(status=Lesson.Status.CANCELLED):
            if groups is not None and lesson.group not in groups:
                continue
            entries = [{"student": s.pk, "status": status} for s in lesson.group.students.all()]
            response = client.post(f"{URL}{session.pk}/attendance/", {"group": lesson.group_id, "entries": entries},
                                   format="json")
            assert response.status_code == 200, response.data


class ParallelBase(ParallelFixture, TestCase):
    def setUp(self):
        self.build()


# 1, 2 — creating sessions ----------------------------------------------------

class CreateTests(ParallelBase):
    def test_create_with_four_groups(self):
        response = self.create(self.groups[:4])
        self.assertEqual(response.status_code, 201, response.data)
        session = ParallelSession.objects.get(pk=response.data["id"])
        self.assertEqual(response.data["groups_count"], 4)
        self.assertEqual(response.data["students_count"], 12)
        lessons = list(session.lessons.order_by("group__name"))
        self.assertEqual([l.group for l in lessons], self.groups[:4])
        for lesson in lessons:
            # Each group's own lesson, in its own program, shared trainer/room/time.
            self.assertEqual(lesson.teacher, self.islam)
            self.assertEqual(lesson.room, self.room)
            self.assertEqual((lesson.date, lesson.start_time, lesson.end_time), (DAY, T(15), T(16)))
            self.assertEqual(lesson.group_teacher, self.programs[lesson.group_id])
            self.assertEqual(lesson.topic, "Общая тема")
            self.assertTrue(lesson.schedule_overridden)
            self.assertGreater(lesson.lesson_number, 8)  # past the plan: generation never claims it
        self.assertEqual(ParallelSessionGroup.objects.filter(session=session).count(), 4)
        self.assertEqual(len(service.history(session)), 1)

    def test_create_with_ten_groups_no_limit(self):
        response = self.create(self.groups)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["groups_count"], 10)
        self.assertEqual(Lesson.objects.filter(parallel_session_id=response.data["id"]).count(), 10)
        # Groups taught by another trainer get the session's trainer as a
        # substitute on their own program's lesson — no new assignment.
        self.assertEqual(GroupTeacher.objects.count(), 10)

    def test_end_must_be_after_start(self):
        response = self.create(self.groups[:2], start=T(16), end=T(15))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ParallelSession.objects.exists())

    def test_inactive_group_rejected(self):
        Group.objects.filter(pk=self.groups[0].pk).update(status=Group.Status.COMPLETED)
        self.assertEqual(self.create(self.groups[:2]).status_code, 400)
        self.assertFalse(Lesson.objects.exists())


# 3 — duplicates ----------------------------------------------------------------

class DuplicateGroupTests(ParallelBase):
    def test_duplicate_group_in_payload_rejected(self):
        payload = self.payload(self.groups[:2])
        payload["groups"].append(self.groups[0].pk)
        response = self.client_for(self.assistant).post(URL, payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ParallelSession.objects.exists())

    def test_adding_participating_group_again_rejected(self):
        session = self.session(self.groups[:2])
        response = self.client_for(self.assistant).post(f"{URL}{session.pk}/groups/", {"group": self.groups[0].pk})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(session.lessons.filter(group=self.groups[0]).count(), 1)

    def test_database_forbids_second_live_lesson_of_group_in_session(self):
        session = self.session(self.groups[:2])
        lesson = session.lessons.get(group=self.groups[0])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Lesson.objects.create(group=lesson.group, group_teacher=lesson.group_teacher, teacher=self.islam,
                                  lesson_number=99, date=DAY, start_time=T(15), end_time=T(16),
                                  parallel_session=session)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ParallelSessionGroup.objects.create(session=session, group=self.groups[0])


# 4-8 — conflicts ---------------------------------------------------------------

class ConflictTests(ParallelBase):
    def test_trainer_conflict_with_other_session(self):
        self.session(self.groups[:2])
        response = self.create(self.groups[2:4], room=self.room2, start=T(15, 30), end=T(16, 30))
        self.assertEqual(response.status_code, 400)
        self.assertIn("conflicts", response.data)
        self.assertTrue(any("Тренер" in m for m in response.data["conflicts"]))
        self.assertEqual(ParallelSession.objects.count(), 1)

    def test_classroom_conflict(self):
        self.session(self.groups[:2])
        response = self.create(self.groups[4:6], teacher=self.aibek, start=T(15, 30), end=T(16, 30))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(any("Аудитория" in m for m in response.data["conflicts"]))

    def test_group_conflict_with_other_session(self):
        self.session(self.groups[:2])
        response = self.create([self.groups[1], self.groups[5]], teacher=self.aibek, room=self.room2,
                               start=T(15, 30), end=T(16, 30))
        self.assertEqual(response.status_code, 400)
        self.assertTrue(any(self.groups[1].name in m for m in response.data["conflicts"]))

    def test_conflicts_with_regular_lessons(self):
        # Trainer busy with a regular lesson of another group.
        self.regular_lesson(self.groups[0], T(15, 30), T(16, 30), room=self.room2)
        self.assertEqual(self.create(self.groups[1:3]).status_code, 400)
        # Room busy with another trainer's regular lesson.
        Lesson.objects.all().delete()
        self.regular_lesson(self.groups[6], T(14, 30), T(15, 30), room=self.room)
        self.assertEqual(self.create(self.groups[1:3]).status_code, 400)
        # A group with its own regular lesson at that time (other trainer, other room).
        Lesson.objects.all().delete()
        self.regular_lesson(self.groups[5], T(15), T(16), room=self.room2)
        response = self.create([self.groups[1], self.groups[5]])
        self.assertEqual(response.status_code, 400)
        self.assertTrue(any(self.groups[5].name in m for m in response.data["conflicts"]))
        self.assertFalse(ParallelSession.objects.exists())

    def test_regular_lesson_cannot_be_moved_into_a_session(self):
        self.session(self.groups[:2])
        lesson = self.regular_lesson(self.groups[6], T(9), T(10), room=self.room)
        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            move_lesson(lesson, date=DAY, start_time=T(15, 30), end_time=T(16, 30))

    def test_consecutive_sessions_allowed(self):
        self.session(self.groups[:2], start=T(15), end=T(16))
        response = self.create(self.groups[:2], start=T(16), end=T(17))
        self.assertEqual(response.status_code, 201, response.data)
        response = self.create(self.groups[:2], start=T(14), end=T(15))
        self.assertEqual(response.status_code, 201, response.data)

    def test_check_endpoint_previews_conflicts(self):
        self.session(self.groups[:2])
        client = self.client_for(self.assistant)
        data = self.payload(self.groups[2:3], start=T(15, 30), end=T(16, 30))
        response = client.post(f"{URL}check/", data, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["ok"])
        kinds = {c["kind"] for c in response.data["conflicts"]}
        self.assertEqual(kinds, {"teacher", "room"})
        # Reported once per session, not once per group lesson.
        self.assertEqual(len(response.data["conflicts"]), 2)
        ok = client.post(f"{URL}check/", self.payload(self.groups[2:3], start=T(16), end=T(17)), format="json")
        self.assertTrue(ok.data["ok"])

    def test_session_groups_never_conflict_with_each_other_on_the_board(self):
        session = self.session(self.groups[:4])
        conflicts, by_lesson = schedule_board.period_conflicts(DAY, DAY)
        self.assertEqual(conflicts, [])
        board = schedule_board.board(DAY, DAY, schedule_board.ScheduleFilters(), can_edit=True)
        self.assertEqual(len(board["lessons"]), 4)
        self.assertTrue(all(row["parallel_session"] == {"id": session.pk, "groups_count": 4}
                            for row in board["lessons"]))
        self.assertEqual(board["stats"]["parallel_sessions"], 1)
        legend = {row["id"]: row["lessons_count"] for row in board["legend"]}
        self.assertEqual(legend[self.islam.pk], 1)  # one conducted lesson, not four

    def test_board_reports_regular_lesson_clashing_with_session_once(self):
        self.session(self.groups[:3])
        # Bypass validation (e.g. legacy data) — the board must still show it.
        self.regular_lesson(self.groups[6], T(15, 30), T(16, 30), room=self.room2, teacher=self.islam)
        conflicts, by_lesson = schedule_board.period_conflicts(DAY, DAY)
        self.assertEqual([c["kind"] for c in conflicts], ["teacher"])
        self.assertEqual(len(conflicts[0]["lessons"]), 4)
        self.assertEqual(len(by_lesson), 4)

    def test_edit_revalidates_and_moves_every_group_lesson(self):
        session = self.session(self.groups[:2])
        self.regular_lesson(self.groups[6], T(17), T(18), room=self.room)
        client = self.client_for(self.assistant)
        bad = client.patch(f"{URL}{session.pk}/", {"start_time": "17:00", "end_time": "18:00"}, format="json")
        self.assertEqual(bad.status_code, 400)
        good = client.patch(f"{URL}{session.pk}/", {"start_time": "18:00", "end_time": "19:00", "topic": "Новая"},
                            format="json")
        self.assertEqual(good.status_code, 200, good.data)
        for lesson in session.lessons.all():
            self.assertEqual((lesson.start_time, lesson.end_time, lesson.topic), (T(18), T(19), "Новая"))

    def test_group_lesson_cannot_be_moved_or_cancelled_alone(self):
        session = self.session(self.groups[:2])
        lesson = session.lessons.first()
        client = self.client_for(self.admin)
        self.assertEqual(client.patch(f"/api/v1/lessons/{lesson.pk}/", {"start_time": "09:00"}).status_code, 400)
        self.assertEqual(client.post(f"/api/v1/lessons/{lesson.pk}/cancel/", {}).status_code, 400)
        lesson.refresh_from_db()
        self.assertEqual(lesson.status, Lesson.Status.SCHEDULED)


# 9 — attendance ------------------------------------------------------------------

class AttendanceTests(ParallelBase):
    def test_attendance_is_separate_per_group(self):
        session = self.session(self.groups[:4])
        client = self.client_for(self.islam_user)
        a, b = self.groups[0], self.groups[1]
        a_students, b_students = list(a.students.all()), list(b.students.all())
        entries_a = [{"student": a_students[0].pk, "status": "present"}, {"student": a_students[1].pk, "status": "absent"},
                     {"student": a_students[2].pk, "status": "late"}]
        entries_b = [{"student": s.pk, "status": "excused"} for s in b_students]
        self.assertEqual(client.post(f"{URL}{session.pk}/attendance/", {"group": a.pk, "entries": entries_a},
                                     format="json").status_code, 200)
        self.assertEqual(client.post(f"{URL}{session.pk}/attendance/", {"group": b.pk, "entries": entries_b},
                                     format="json").status_code, 200)
        # A student of B can't be marked on A's lesson.
        mixed = client.post(f"{URL}{session.pk}/attendance/",
                            {"group": a.pk, "entries": [{"student": b_students[0].pk, "status": "present"}]},
                            format="json")
        self.assertEqual(mixed.status_code, 400)
        lesson_a, lesson_b = session.lessons.get(group=a), session.lessons.get(group=b)
        self.assertEqual(Attendance.objects.filter(lesson=lesson_a).count(), 3)
        self.assertEqual(Attendance.objects.filter(lesson=lesson_b).count(), 3)
        self.assertFalse(Attendance.objects.filter(lesson=lesson_a, student__group=b).exists())
        # Re-marking updates, never duplicates.
        client.post(f"{URL}{session.pk}/attendance/", {"group": a.pk, "entries": entries_a}, format="json")
        self.assertEqual(Attendance.objects.filter(lesson=lesson_a).count(), 3)

        stats = client.get(f"{URL}{session.pk}/statistics/").data
        rows = {row["group"]["id"]: row for row in stats["groups"]}
        self.assertEqual((rows[a.pk]["present"], rows[a.pk]["absent"], rows[a.pk]["late"]), (1, 1, 1))
        self.assertEqual(rows[b.pk]["excused"], 3)
        self.assertEqual(rows[self.groups[2].pk]["marked"], 0)
        self.assertEqual(stats["totals"]["students"], 12)
        roster = client.get(f"{URL}{session.pk}/attendance/").data
        self.assertEqual([r["group"]["name"] for r in roster], [g.name for g in self.groups[:4]])
        self.assertTrue(all(len(r["students"]) == 3 for r in roster))

    def test_attendance_also_reachable_through_regular_lesson_api(self):
        session = self.session(self.groups[:2])
        lesson = session.lessons.get(group=self.groups[0])
        response = self.client_for(self.islam_user).get(f"/api/v1/lessons/{lesson.pk}/attendance/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 3)


# 11, 12 — cancel / complete; group removal -----------------------------------------

class LifecycleTests(ParallelBase):
    def test_cancel_session(self):
        session = self.session(self.groups[:3])
        response = self.client_for(self.assistant).post(f"{URL}{session.pk}/cancel/", {"reason": "Свет отключили"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "cancelled")
        self.assertEqual(set(session.lessons.values_list("status", flat=True)), {"cancelled"})
        self.assertEqual(Lesson.objects.count(), 3)  # history kept, no make-up lessons created
        # Cancelled session frees trainer and room.
        self.assertEqual(self.create(self.groups[:3]).status_code, 201)
        # Idempotent.
        again = self.client_for(self.assistant).post(f"{URL}{session.pk}/cancel/", {})
        self.assertEqual(again.status_code, 200)

    def test_complete_session(self):
        session = self.session(self.groups[:4])
        client = self.client_for(self.islam_user)
        # Nothing marked yet: refused, nothing completed.
        refused = client.post(f"{URL}{session.pk}/complete/")
        self.assertEqual(refused.status_code, 400)
        self.assertEqual(len(refused.data["completion"]), 4)
        self.assertFalse(session.lessons.exclude(status=Lesson.Status.SCHEDULED).exists())

        self.mark_all(session)
        hw = client.post(f"{URL}{session.pk}/homework/", {"title": "Общее ДЗ"}, format="json")
        self.assertEqual(hw.status_code, 201, hw.data)
        self.assertEqual(Homework.objects.filter(lesson__parallel_session=session).count(), 4)
        response = client.post(f"{URL}{session.pk}/complete/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "completed")
        self.assertEqual(set(session.lessons.values_list("status", flat=True)), {"completed"})
        self.assertEqual(set(ParallelSessionGroup.objects.values_list("students_count", flat=True)), {3})
        # Completed: no cancel, no group changes, idempotent complete.
        self.assertEqual(self.client_for(self.assistant).post(f"{URL}{session.pk}/cancel/").status_code, 400)
        self.assertEqual(self.client_for(self.assistant).delete(f"{URL}{session.pk}/groups/{self.groups[0].pk}/").status_code, 400)
        self.assertEqual(client.post(f"{URL}{session.pk}/complete/").status_code, 200)

    def test_complete_is_all_or_nothing(self):
        session = self.session(self.groups[:2])
        self.mark_all(session, groups=[self.groups[0]])
        self.client_for(self.islam_user).post(f"{URL}{session.pk}/homework/", {"title": "ДЗ"}, format="json")
        response = self.client_for(self.islam_user).post(f"{URL}{session.pk}/complete/")
        self.assertEqual(response.status_code, 400)
        self.assertIn(self.groups[1].name, response.data["completion"][0])
        self.assertFalse(session.lessons.filter(status=Lesson.Status.COMPLETED).exists())

    def test_group_specific_homework(self):
        session = self.session(self.groups[:3])
        response = self.client_for(self.islam_user).post(
            f"{URL}{session.pk}/homework/", {"title": "Только для G01", "groups": [self.groups[0].pk]}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(list(Homework.objects.values_list("lesson__group", flat=True)), [self.groups[0].pk])

    def test_remove_group_keeps_history_and_readd(self):
        session = self.session(self.groups[:3])
        removed = self.groups[2]
        lesson = session.lessons.get(group=removed)
        Attendance.objects.create(lesson=lesson, student=removed.students.first(), status="present")
        client = self.client_for(self.assistant)
        response = client.delete(f"{URL}{session.pk}/groups/{removed.pk}/", {"reason": "Перевели"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["groups_count"], 2)
        lesson.refresh_from_db()
        self.assertEqual(lesson.status, Lesson.Status.CANCELLED)
        self.assertEqual(Attendance.objects.filter(lesson=lesson).count(), 1)  # data untouched
        participant = ParallelSessionGroup.objects.get(session=session, group=removed)
        self.assertEqual((participant.status, participant.removal_reason), ("removed", "Перевели"))
        # The removed group is free again at that time.
        self.assertEqual(self.create([removed], teacher=self.aibek, room=self.room2).status_code, 201)
        # Back into the session (after cancelling the other one).
        other = ParallelSession.objects.exclude(pk=session.pk).get()
        client.post(f"{URL}{other.pk}/cancel/")
        again = client.post(f"{URL}{session.pk}/groups/", {"group": removed.pk})
        self.assertEqual(again.status_code, 201, again.data)
        self.assertEqual(session.lessons.filter(group=removed).count(), 2)  # old cancelled + new live
        self.assertEqual(session.lessons.filter(group=removed).exclude(status="cancelled").count(), 1)
        self.assertEqual(len(client.get(f"{URL}{session.pk}/history/").data), 3)  # created, removed, re-added

    def test_last_group_cannot_be_removed(self):
        session = self.session(self.groups[:1])
        response = self.client_for(self.assistant).delete(f"{URL}{session.pk}/groups/{self.groups[0].pk}/")
        self.assertEqual(response.status_code, 400)


# 13 — permissions ------------------------------------------------------------------

class PermissionTests(ParallelBase):
    def test_roles(self):
        session = self.session(self.groups[:2])
        aibek_session = self.session(self.groups[4:6], teacher=self.aibek, room=self.room2)
        payload = self.payload(self.groups[6:8], start=T(9), end=T(10))

        # Team Lead: reads all, never writes.
        lead = self.client_for(self.lead)
        self.assertEqual(lead.get(URL).data["count"] if isinstance(lead.get(URL).data, dict) else len(lead.get(URL).data), 2)
        self.assertEqual(lead.post(URL, payload, format="json").status_code, 403)
        self.assertEqual(lead.post(f"{URL}{session.pk}/cancel/").status_code, 403)

        # Trainer: only own sessions, can't create/cancel, can mark and complete own.
        islam = self.client_for(self.islam_user)
        listed = islam.get(URL).data
        listed = listed["results"] if isinstance(listed, dict) else listed
        self.assertEqual([row["id"] for row in listed], [session.pk])
        self.assertEqual(islam.get(f"{URL}{aibek_session.pk}/").status_code, 404)
        self.assertEqual(islam.post(URL, payload, format="json").status_code, 403)
        self.assertEqual(islam.post(f"{URL}{session.pk}/cancel/").status_code, 403)
        self.assertEqual(islam.patch(f"{URL}{session.pk}/", {"topic": "x"}, format="json").status_code, 403)
        self.assertTrue(islam.get(f"{URL}{session.pk}/").data["capabilities"]["can_mark_attendance"])

        # Assistant: manages sessions, but attendance stays the trainer's.
        assistant = self.client_for(self.assistant)
        group = self.groups[0]
        entries = [{"student": s.pk, "status": "present"} for s in group.students.all()]
        self.assertEqual(assistant.post(f"{URL}{session.pk}/attendance/", {"group": group.pk, "entries": entries},
                                        format="json").status_code, 403)
        self.assertEqual(assistant.post(f"{URL}{session.pk}/complete/").status_code, 403)

        # Accountant (and any other role): no access at all.
        self.assertEqual(self.client_for(self.accountant).get(URL).status_code, 403)
        self.assertEqual(APIClient().get(URL).status_code, 401)

        # Admin: everything.
        admin = self.client_for(self.admin)
        self.assertEqual(admin.post(f"{URL}{session.pk}/attendance/", {"group": group.pk, "entries": entries},
                                    format="json").status_code, 200)

    def test_trainer_analytics_are_scoped_to_self(self):
        self.session(self.groups[:2])
        self.session(self.groups[4:6], teacher=self.aibek, room=self.room2)
        data = self.client_for(self.islam_user).get(f"{URL}analytics/", {"start": str(DAY), "end": str(DAY),
                                                                          "teacher": self.aibek.pk}).data
        self.assertEqual(data["totals"]["sessions"], 1)
        self.assertEqual(data["workload"][0]["teacher"]["id"], self.islam.pk)


# Analytics / trainer workload -----------------------------------------------------

class WorkloadTests(ParallelBase):
    def test_session_is_one_lesson_of_trainer_workload(self):
        session = self.session(self.groups[:4])
        self.regular_lesson(self.groups[0], T(9), T(10), room=self.room, number=1)
        self.mark_all(session)
        self.client_for(self.islam_user).post(f"{URL}{session.pk}/homework/", {"title": "ДЗ"}, format="json")
        self.client_for(self.islam_user).post(f"{URL}{session.pk}/complete/")

        stats = compute_monthly_stats(self.islam, DAY.year, DAY.month)
        self.assertEqual(stats["lessons_total"], 2)        # 1 regular + 1 session (not 5)
        self.assertEqual(stats["lessons_completed"], 1)
        self.assertEqual({g["name"]: g["lessons_count"] for g in stats["groups"]}[self.groups[1].name], 1)

        from apps.academy.services.analytics.period import DateRange
        from apps.academy.services.analytics.scope import AnalyticsScope

        scope = AnalyticsScope(date_range=DateRange(DAY, DAY))
        workload = {row["teacher_id"]: row["lessons"] for row in teacher_analytics._workload(scope, DateRange(DAY, DAY))}
        self.assertEqual(workload[self.islam.pk], 2)

        report = self.client_for(self.lead).get(f"{URL}analytics/", {"start": str(DAY), "end": str(DAY)}).data
        self.assertEqual(report["totals"]["sessions"], 1)
        self.assertEqual(report["totals"]["completed"], 1)
        self.assertEqual(report["totals"]["groups"], 4)
        self.assertEqual(report["totals"]["students"], 12)
        self.assertEqual(report["workload"][0]["sessions"], 1)
        self.assertEqual(report["workload"][0]["groups"], 4)
        self.assertEqual(len(report["attendance_by_group"]), 4)

    def test_list_filters(self):
        s1 = self.session(self.groups[:2])
        s2 = self.session(self.groups[4:6], teacher=self.aibek, room=self.room2, date=DAY + dt.timedelta(days=1))
        client = self.client_for(self.lead)

        def ids(**params):
            data = client.get(URL, params).data
            return sorted(row["id"] for row in (data["results"] if isinstance(data, dict) else data))

        self.assertEqual(ids(teacher=self.aibek.pk), [s2.pk])
        self.assertEqual(ids(room=self.room.pk), [s1.pk])
        self.assertEqual(ids(group=self.groups[0].pk), [s1.pk])
        self.assertEqual(ids(date=str(DAY)), [s1.pk])
        self.assertEqual(ids(status="scheduled"), sorted([s1.pk, s2.pk]))
        self.assertEqual(ids(status="cancelled"), [])


# 14 — concurrency ---------------------------------------------------------------------

@skipUnless(connection.vendor == "postgresql", "needs real concurrent transactions (PostgreSQL)")
class ConcurrencyTests(ParallelFixture, TransactionTestCase):
    def setUp(self):
        self.build()

    def test_concurrent_sessions_for_same_trainer_only_one_wins(self):
        barrier = threading.Barrier(2)
        results = []

        def worker(groups, room):
            try:
                barrier.wait()
                service.create_session(service.SessionInput(
                    teacher=self.islam, room=room, date=DAY, start_time=T(15), end_time=T(16),
                    groups=list(Group.objects.filter(pk__in=[g.pk for g in groups]))))
                results.append("ok")
            except Exception as exc:  # noqa: BLE001 — the loser's ValidationError
                results.append(type(exc).__name__)
            finally:
                connection.close()

        threads = [threading.Thread(target=worker, args=(self.groups[:2], self.room)),
                   threading.Thread(target=worker, args=(self.groups[2:4], self.room2))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results), ["ValidationError", "ok"])
        self.assertEqual(ParallelSession.objects.count(), 1)
        self.assertEqual(Lesson.objects.count(), 2)

    def test_concurrent_sessions_sharing_a_group_only_one_wins(self):
        barrier = threading.Barrier(2)
        results = []

        def worker(teacher, room, groups):
            try:
                barrier.wait()
                service.create_session(service.SessionInput(
                    teacher=teacher, room=room, date=DAY, start_time=T(15), end_time=T(16),
                    groups=list(Group.objects.filter(pk__in=[g.pk for g in groups]))))
                results.append("ok")
            except Exception as exc:  # noqa: BLE001
                results.append(type(exc).__name__)
            finally:
                connection.close()

        shared = self.groups[0]
        threads = [threading.Thread(target=worker, args=(self.islam, self.room, [shared, self.groups[1]])),
                   threading.Thread(target=worker, args=(self.aibek, self.room2, [shared, self.groups[5]]))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results), ["ValidationError", "ok"])
        self.assertEqual(Lesson.objects.filter(group=shared).count(), 1)


class LockingTests(ParallelBase):
    @skipUnless(connection.vendor == "postgresql", "row locks are only emitted on PostgreSQL")
    def test_create_locks_trainer_room_and_groups(self):
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            service.create_session(service.SessionInput(
                teacher=self.islam, room=self.room, date=DAY, start_time=T(15), end_time=T(16), groups=self.groups[:2]))
        locked = [q["sql"] for q in ctx.captured_queries if "FOR UPDATE" in q["sql"]]
        for table in ("users_teacher", "academy_room", "academy_group"):
            self.assertTrue(any(table in sql for sql in locked), table)
