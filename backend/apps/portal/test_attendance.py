"""«Катышуу» dashboard: numbers from the trainer's Attendance marks only, by
the KPI's rules (attended = present + late; missed = absent + excused;
percent over marked lessons; unmarked / cancelled lessons are not misses),
a month calendar with every lesson's state, filtered history, real
analytics, read-only, own children only."""
from __future__ import annotations

import datetime as dt

from django.urls import reverse
from django.utils import timezone

from apps.academy.models import Attendance, Lesson, Student
from apps.users.models import Subject

from .tests import PortalTestBase

TODAY = timezone.localdate()
P, A, L, E = (Attendance.Status.PRESENT, Attendance.Status.ABSENT, Attendance.Status.LATE, Attendance.Status.EXCUSED)


class AttendanceDashboardTests(PortalTestBase):
    def setUp(self):
        super().setUp()
        self.client_, self.student, _ = self.portal_client()
        Student.objects.filter(pk=self.student.pk).update(enrollment_date=TODAY - dt.timedelta(days=120))
        self.student.refresh_from_db()
        self.n = 0

    def lesson_on(self, day, *, mark=None, status=Lesson.Status.COMPLETED, start=16, group=None, gt=None):
        self.n += 1
        lesson = Lesson.objects.create(group=group or self.g1, group_teacher=gt or self.gt1, subject=self.python,
                                       teacher=self.teacher, lesson_number=self.n, date=day, start_time=dt.time(start),
                                       end_time=dt.time(start + 1), status=status, topic=f"Тема {self.n}")
        if mark:
            Attendance.objects.create(student=self.student, lesson=lesson, status=mark)
        return lesson

    def get(self, name, **params):
        response = self.client_.get(reverse(f"portal:{name}", args=[self.student.pk]), params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.data

    def test_percent_uses_marked_lessons_and_the_kpi_rules(self):
        for i, mark in enumerate([P, P, L, A, E, P]):
            self.lesson_on(TODAY - dt.timedelta(days=30 - i * 3), mark=mark)
        self.lesson_on(TODAY - dt.timedelta(days=2))                                   # held, not marked
        self.lesson_on(TODAY - dt.timedelta(days=1), mark=A, status=Lesson.Status.CANCELLED)  # cancelled: ignored
        self.lesson_on(TODAY + dt.timedelta(days=3), status=Lesson.Status.SCHEDULED)   # future: not held
        s = self.get("attendance-overview")["summary"]
        self.assertEqual((s["marked"], s["attended"], s["present"], s["late"], s["absent"], s["excused"], s["missed"]),
                         (6, 4, 3, 1, 1, 1, 2))
        self.assertEqual(s["percent"], round(4 / 6 * 100, 1))
        self.assertEqual((s["held"], s["unmarked"]), (7, 1))
        rules = self.get("attendance-overview")["rules"]
        self.assertEqual((rules["attended"], rules["missed"]), (["present", "late"], ["absent", "excused"]))

    def test_no_records_means_no_percent(self):
        overview = self.get("attendance-overview")
        self.assertIsNone(overview["summary"]["percent"])
        self.assertEqual(overview["streak"], {"current": 0, "best": 0})

    def test_calendar_shows_every_lesson_with_its_state(self):
        first = TODAY.replace(day=1)
        day = first if first < TODAY else TODAY
        morning = self.lesson_on(day, mark=P, start=10)
        evening = self.lesson_on(day, mark=L, start=16)            # two lessons on one day
        cancelled = self.lesson_on(day, status=Lesson.Status.CANCELLED, start=18)
        future = self.lesson_on(TODAY + dt.timedelta(days=1), status=Lesson.Status.SCHEDULED) \
            if (TODAY + dt.timedelta(days=1)).month == TODAY.month else None
        data = self.get("attendance", year=TODAY.year, month=TODAY.month)
        states = {row["id"]: row["state"] for row in data["lessons"]}
        self.assertEqual((states[morning.pk], states[evening.pk], states[cancelled.pk]), ("present", "late", "cancelled"))
        if future:
            self.assertEqual(states[future.pk], "future")
        same_day = [r for r in data["lessons"] if r["date"] == day]
        self.assertEqual([r["start"] for r in same_day], ["10:00", "16:00", "18:00"])
        self.assertEqual(same_day[0]["subject"]["name"], "Python")
        self.assertEqual(same_day[0]["teacher"]["name"], str(self.teacher))
        self.assertEqual(data["summary"]["marked"], 2)  # the cancelled lesson does not count

    def test_unmarked_past_lesson_is_not_a_miss(self):
        lesson = self.lesson_on(TODAY - dt.timedelta(days=1) if TODAY.day > 1 else TODAY, status=Lesson.Status.COMPLETED)
        data = self.get("attendance", year=lesson.date.year, month=lesson.date.month)
        self.assertEqual([r["state"] for r in data["lessons"]], ["unmarked"])
        self.assertEqual(data["summary"]["missed"], 0)

    def test_month_navigation(self):
        prev = (TODAY.replace(day=1) - dt.timedelta(days=1)).replace(day=10)
        old = self.lesson_on(prev, mark=A)
        data = self.get("attendance", year=prev.year, month=prev.month)
        self.assertEqual([r["id"] for r in data["lessons"]], [old.pk])
        self.assertEqual((data["year"], data["month"]), (prev.year, prev.month))
        bad = self.client_.get(reverse("portal:attendance", args=[self.student.pk]), {"year": TODAY.year, "month": 13})
        self.assertEqual(bad.status_code, 400)

    def test_history_filters_and_paginates(self):
        for i in range(25):
            self.lesson_on(TODAY - dt.timedelta(days=60 - i * 2), mark=[P, A, L, E][i % 4])
        page = self.get("attendance-history")
        self.assertEqual((page["count"], len(page["results"])), (25, 20))
        dates = [r["lesson"]["date"] for r in page["results"]]
        self.assertEqual(dates, sorted(dates, reverse=True))   # newest first
        self.assertEqual(self.get("attendance-history", page=2)["results"].__len__(), 5)
        absent = self.get("attendance-history", status="absent")
        self.assertEqual({r["status"] for r in absent["results"]}, {"absent"})
        self.assertEqual(absent["count"], 6)
        bad = self.client_.get(reverse("portal:attendance-history", args=[self.student.pk]), {"status": "nope"})
        self.assertEqual(bad.status_code, 400)

    def test_streaks_trend_subjects_and_weeks(self):
        english, _ = Subject.objects.get_or_create(name="English")
        for i, mark in enumerate([P, P, P, A, P, L, P]):
            self.lesson_on(TODAY - dt.timedelta(days=20 - i * 2), mark=mark)
        en = self.lesson_on(TODAY - dt.timedelta(days=1), mark=E)
        Lesson.objects.filter(pk=en.pk).update(subject=english)
        overview = self.get("attendance-overview")
        self.assertEqual(overview["streak"], {"current": 0, "best": 3})   # the last mark is «excused»
        subjects = {s["subject"]: (s["attended"], s["marked"]) for s in overview["subjects"]}
        self.assertEqual(subjects, {"English": (0, 1), "Python": (6, 7)})
        self.assertEqual(len(overview["months"]), 6)
        self.assertEqual(sum(m["marked"] for m in overview["months"]), 8)
        self.assertEqual(len(overview["weeks"]), 8)
        self.assertEqual(sum(w["marked"] for w in overview["weeks"]), 8)

    def test_only_own_children_and_read_only(self):
        other = Student.objects.create(first_name="Other", last_name="Kid", group=self.g1)
        for name in ("attendance", "attendance-overview", "attendance-history"):
            url = reverse(f"portal:{name}", args=[other.pk])
            self.assertEqual(self.client_.get(url).status_code, 404, name)
            own = reverse(f"portal:{name}", args=[self.student.pk])
            self.assertEqual(self.client_.post(own, {"status": "present"}, format="json").status_code, 405, name)
        # The trainer's marking API stays closed to the family.
        lesson = self.lesson_on(TODAY, mark=A)
        response = self.client_.post(f"/api/v1/lessons/{lesson.pk}/attendance/", [{"student": self.student.pk, "status": "present"}], format="json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Attendance.objects.get(lesson=lesson, student=self.student).status, A)
