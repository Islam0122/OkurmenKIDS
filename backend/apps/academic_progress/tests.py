"""Monthly Academic Progress — the 10 checks of the task."""
from __future__ import annotations

import datetime as dt

from django.test import TestCase
from rest_framework.test import APIClient

from apps.academy.models import Attendance, Course, Group, GroupTeacher, Lesson, Student
from apps.attendance_matrix.models import TeamLeadDirection
from apps.users.models import Subject, Teacher, User

from . import progress
from .models import CurriculumMonth, GroupProgressAdjustment, ProgramCurriculum

START = dt.date(2026, 9, 17)
BASE = "/api/v1/academic-progress"


def user(username, role) -> User:
    return User.objects.create_user(username=username, email=f"{username}@x.kg", password="x", first_name=username,
                                    role=role, is_verified=True)


class Base(TestCase):
    def setUp(self):
        self.it, _ = Subject.objects.get_or_create(name="IT")
        self.english, _ = Subject.objects.get_or_create(name="English")
        self.react, _ = Subject.objects.get_or_create(name="React")
        self.course = Course.objects.create(name="NEXT", count_lesson=72)
        self.course.subjects.set([self.it, self.english])
        self.teacher = Teacher.objects.create(user=user("islam", User.Role.TEACHER))
        self.group = Group.objects.create(name="NEXT 1", course=self.course, start_date=START)
        self.gt = GroupTeacher.objects.create(group=self.group, teacher=self.teacher, subject=self.it)
        self.gt_en = GroupTeacher.objects.create(group=self.group, teacher=self.teacher, subject=self.english)
        self.n = 0

    def curriculum(self, per_month=12, months=6, **extra) -> ProgramCurriculum:
        c = ProgramCurriculum.objects.create(course=self.course, lessons_per_month=per_month, duration_months=months,
                                             main_subject=self.it, **extra)
        c.extra_subjects.set([self.english])
        return c

    def held(self, count, *, gt=None, status=Lesson.Status.COMPLETED, start_number=None):
        gt = gt or self.gt
        made = []
        number = start_number
        for _ in range(count):
            self.n += 1
            if number is None:
                number = Lesson.objects.filter(group_teacher=gt).count() + 1
            made.append(Lesson.objects.create(
                group=self.group, group_teacher=gt, teacher=self.teacher, subject=gt.subject, lesson_number=number,
                date=START + dt.timedelta(days=self.n), start_time=dt.time(16), end_time=dt.time(17), status=status,
            ))
            number += 1
        return made

    def p(self):
        return progress.group_progress(self.group, today=dt.date(2027, 6, 1))


class MonthTests(Base):
    def test_12_lessons_per_month(self):  # 1
        self.curriculum(12)
        self.held(15)
        p = self.p()
        self.assertEqual((p["status"], p["month"]["number"], p["month"]["done"], p["month"]["planned"], p["month"]["remaining"]),
                         ("in_progress", 2, 3, 12, 9))
        self.assertEqual(p["month"]["label"], "2-й месяц")
        self.assertEqual((p["course"]["done"], p["course"]["planned"]), (15, 72))
        self.assertEqual(p["month"]["subject"]["name"], "IT")

    def test_20_lessons_per_month(self):  # 2
        self.curriculum(20)
        self.held(15)
        p = self.p()
        self.assertEqual((p["month"]["number"], p["month"]["done"], p["month"]["planned"]), (1, 15, 20))
        self.assertEqual(p["course"]["planned"], 120)

    def test_different_months(self):  # 3
        c = self.curriculum(12, months=4)
        CurriculumMonth.objects.create(curriculum=c, number=3, subject=self.react, planned_lessons=20)
        self.held(30)
        p = self.p()
        self.assertEqual([m["planned"] for m in p["months"]], [12, 12, 20, 12])
        self.assertEqual((p["month"]["number"], p["month"]["done"], p["month"]["subject"]["name"]), (3, 6, "React"))
        self.assertEqual(p["months"][0]["subject"]["name"], "IT")  # default subject

    def test_month_switches_exactly_after_the_last_lesson(self):  # 4
        self.curriculum(12)
        self.held(11)
        self.assertEqual((self.p()["month"]["number"], self.p()["month"]["done"]), (1, 11))
        self.held(1)
        p = self.p()
        self.assertEqual((p["month"]["number"], p["month"]["done"], p["month"]["next_lesson"]), (2, 0, 1))
        self.assertEqual(p["months"][0]["state"], "done")

    def test_course_completed(self):
        self.curriculum(2, months=2)
        self.held(5)
        p = self.p()
        self.assertEqual((p["status"], p["course"]["done"], p["course"]["remaining"], p["course"]["extra"]), ("completed", 4, 0, 1))

    def test_not_started(self):
        self.curriculum(12)
        self.held(2, status=Lesson.Status.SCHEDULED)
        p = self.p()
        self.assertEqual((p["status"], p["month"]["number"], p["month"]["done"]), ("not_started", 1, 0))


class CountingTests(Base):
    def test_cancelled_and_scheduled_lessons_do_not_count(self):  # 5
        self.curriculum(12)
        self.held(3)
        self.held(2, status=Lesson.Status.CANCELLED)
        self.held(2, status=Lesson.Status.SCHEDULED)
        self.assertEqual(self.p()["month"]["done"], 3)

    def test_rescheduled_lesson_counts_once_after_it_is_held(self):  # 6
        self.curriculum(12)
        self.held(2)
        cancelled = self.held(1, status=Lesson.Status.CANCELLED)[0]
        self.assertEqual(self.p()["month"]["done"], 2)
        # The make-up lesson carries the same number; until held it does not count.
        makeup = self.held(1, status=Lesson.Status.SCHEDULED, start_number=cancelled.lesson_number)[0]
        self.assertEqual(self.p()["month"]["done"], 2)
        Lesson.objects.filter(pk=makeup.pk).update(status=Lesson.Status.COMPLETED)
        self.assertEqual(self.p()["month"]["done"], 3)

    def test_duplicate_records_count_once(self):  # 7
        self.curriculum(12)
        first = self.held(1)[0]
        # The same lesson recorded a second time (a legacy row without a program).
        Lesson.objects.create(group=self.group, teacher=self.teacher, subject=self.it, lesson_number=first.lesson_number,
                              date=first.date, start_time=first.start_time, end_time=first.end_time,
                              status=Lesson.Status.COMPLETED)
        self.assertEqual(Lesson.objects.filter(group=self.group, status="completed").count(), 2)
        self.assertEqual(self.p()["month"]["done"], 1)

    def test_extra_subject_lessons_only_count_in_all_mode(self):
        c = self.curriculum(12)
        self.held(3)
        self.held(4, gt=self.gt_en)
        self.assertEqual(self.p()["month"]["done"], 3)
        c.count_mode = ProgramCurriculum.CountMode.ALL
        c.save()
        self.assertEqual(self.p()["month"]["done"], 7)

    def test_group_progress_is_not_student_progress(self):  # 8
        self.curriculum(12)
        lessons = self.held(4)
        good = Student.objects.create(first_name="Good", group=self.group)
        missing = Student.objects.create(first_name="Missing", group=self.group)
        for lesson in lessons:
            Attendance.objects.create(lesson=lesson, student=good, status="present")
            Attendance.objects.create(lesson=lesson, student=missing, status="absent")
        p = self.p()
        self.assertEqual(p["month"]["done"], 4)  # absences don't reduce the group's lessons
        students = {s["name"]: s for s in progress.student_progress(self.group, p)}
        self.assertEqual((students["Good"]["month_attended"], students["Good"]["month_held"]), (4, 4))
        self.assertEqual((students["Missing"]["month_attended"], students["Missing"]["month_rate"]), (0, 0.0))


class HistoryTests(Base):
    def test_no_curriculum_needs_setup_and_history_is_kept(self):  # 9
        self.held(5)
        p = self.p()
        self.assertEqual((p["status"], p["month"], p["lessons_in_lms"]), ("needs_setup", None, 5))
        self.curriculum(12)
        self.assertEqual(self.p()["month"]["done"], 5)
        self.assertEqual(Lesson.objects.filter(group=self.group).count(), 5)  # nothing created or deleted

    def test_missing_first_lessons_need_confirmation(self):
        self.curriculum(12)
        self.held(3, start_number=25)  # lessons 1–24 were never entered into the LMS
        p = self.p()
        self.assertEqual(p["status"], "needs_setup")
        self.assertIn("до LMS", p["reason"])
        GroupProgressAdjustment.objects.create(group=self.group, lessons_before_lms=24)
        p = self.p()
        self.assertEqual((p["month"]["number"], p["month"]["done"], p["course"]["done"]), (3, 3, 27))

    def test_changing_settings_after_start_recomputes_without_losing_lessons(self):  # 10
        c = self.curriculum(12)
        self.held(15)
        self.assertEqual(self.p()["month"]["number"], 2)
        c.lessons_per_month = 20
        c.save()
        p = self.p()
        self.assertEqual((p["month"]["number"], p["month"]["done"]), (1, 15))
        self.assertEqual(Lesson.objects.filter(group=self.group, status="completed").count(), 15)


class ApiTests(Base):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.held(15)

    def as_(self, u):
        self.client.force_authenticate(u)
        return self.client

    def payload(self, **extra):
        return {"lessons_per_month": 12, "duration_months": 6, "main_subject": self.it.pk, "extra_subjects": [self.english.pk],
                "count_mode": "main", "months": [{"number": 3, "subject": self.react.pk, "planned_lessons": 20}], **extra}

    def test_operations_director_configures_a_program(self):
        od = user("ops", User.Role.OPERATIONS_DIRECTOR)
        r = self.as_(od).put(f"{BASE}/programs/{self.course.pk}/", self.payload(), format="json")
        self.assertEqual(r.status_code, 200, r.content)
        s = r.json()["settings"]
        self.assertEqual(([b["planned"] for b in s["blocks"]], s["total_lessons"]), ([12, 12, 20, 12, 12, 12], 80))
        g = self.as_(od).get(f"{BASE}/groups/{self.group.pk}/").json()
        self.assertEqual((g["progress"]["month"]["number"], g["progress"]["month"]["done"]), (2, 3))
        programs = self.as_(od).get(f"{BASE}/programs/").json()["results"]
        self.assertEqual(programs[0]["groups_need_setup"], 0)

    def test_validation(self):
        od = user("ops", User.Role.OPERATIONS_DIRECTOR)
        r = self.as_(od).put(f"{BASE}/programs/{self.course.pk}/", self.payload(lessons_per_month=0, main_subject=self.english.pk), format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(set(r.json()), {"lessons_per_month", "extra_subjects"})
        r = self.as_(od).put(f"{BASE}/programs/{self.course.pk}/", self.payload(months=[{"number": 9, "planned_lessons": 5}]), format="json")
        self.assertEqual(r.status_code, 400)

    def test_team_lead_manages_only_their_directions(self):
        tl = user("lead", User.Role.TEAM_LEAD)
        TeamLeadDirection.objects.create(team_lead=tl, subject=self.react)
        other = Course.objects.create(name="REACT", count_lesson=40)
        other.subjects.set([self.react])
        self.assertEqual([p["name"] for p in self.as_(tl).get(f"{BASE}/programs/").json()["results"]], ["REACT"])
        self.assertEqual(self.as_(tl).put(f"{BASE}/programs/{self.course.pk}/", self.payload(), format="json").status_code, 404)
        self.assertEqual(self.as_(tl).put(f"{BASE}/programs/{other.pk}/", self.payload(), format="json").status_code, 200)

    def test_other_roles_view_only(self):
        a = user("asel", User.Role.ASSISTANT)
        self.assertEqual(self.as_(a).get(f"{BASE}/programs/{self.course.pk}/").status_code, 200)
        self.assertEqual(self.as_(a).put(f"{BASE}/programs/{self.course.pk}/", self.payload(), format="json").status_code, 403)
        hr = user("hr", User.Role.HR_MANAGER)
        self.assertEqual(self.as_(hr).get(f"{BASE}/programs/").status_code, 403)

    def test_group_history_confirmation(self):
        ProgramCurriculum.objects.create(course=self.course, lessons_per_month=12, duration_months=6)
        od = user("ops", User.Role.OPERATIONS_DIRECTOR)
        r = self.as_(od).put(f"{BASE}/groups/{self.group.pk}/history/", {"lessons_before_lms": 12}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["progress"]["month"]["number"], 3)  # 12 before + 15 → month 3, 3 / 12

    def test_operations_groups_page_carries_the_study_month(self):
        self.curriculum(12)
        od = user("ops", User.Role.OPERATIONS_DIRECTOR)
        r = self.as_(od).get("/api/v1/operations/academy/groups/", {"period": "this_month"})
        self.assertEqual(r.status_code, 200, r.content[:300])
        row = next(g for g in r.json()["results"] if g["id"] == self.group.pk)
        self.assertEqual((row["academic"]["month"]["number"], row["academic"]["month"]["done"]), (2, 3))
        self.assertIn("plan", row)  # the old overall progress stays
