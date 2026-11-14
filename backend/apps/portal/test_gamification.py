"""«Жетишкендиктер»: XP equals the leaderboard's own rules, levels follow
the real thresholds, achievements unlock only from real records (with the
date of the record that unlocked them), goals and activity are real, and
only the family's own children are visible."""
from __future__ import annotations

import datetime as dt

from django.urls import reverse
from django.utils import timezone

from apps.academy.models import Attendance, Homework, HomeworkResult, Lesson, Student
from apps.leaderboard.services import Period, student_xp, student_xp_daily

from .services import data, gamification
from .tests import PortalTestBase

TODAY = timezone.localdate()


class GamificationTests(PortalTestBase):
    def setUp(self):
        super().setUp()
        self.client_, self.student, _ = self.portal_client()
        Student.objects.filter(pk=self.student.pk).update(enrollment_date=TODAY - dt.timedelta(days=200))
        self.student.refresh_from_db()

    def held(self, days_ago, number, *, mark=Attendance.Status.PRESENT, hw_status=None, score=None):
        lesson = self.lesson(self.g1, self.gt1, TODAY - dt.timedelta(days=days_ago), number=number)
        if mark:
            Attendance.objects.create(student=self.student, lesson=lesson, status=mark)
        if hw_status:
            hw = Homework.objects.create(lesson=lesson, title=f"HW{number}")
            HomeworkResult.objects.create(homework=hw, student=self.student, status=hw_status, score=score)
        return lesson

    def page(self):
        response = self.client_.get(reverse("portal:achievements", args=[self.student.pk]))
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_daily_xp_adds_up_to_the_leaderboard_total(self):
        for i in range(12):
            self.held(30 - i * 2, i + 1, mark=Attendance.Status.LATE if i % 4 == 0 else Attendance.Status.PRESENT,
                      hw_status="checked" if i % 3 else "late", score=(i % 11) if i % 2 else None)
        Lesson.objects.filter(group=self.g1, lesson_number=5).update(status=Lesson.Status.CANCELLED)
        period = Period("custom", dt.date(2000, 1, 1), TODAY)
        daily = student_xp_daily(period, self.student.pk)
        totals = student_xp(period, student_ids=[self.student.pk])[self.student.pk]
        for key in ("attendance", "homework", "tests"):
            self.assertEqual(sum(d[key] for d in daily.values()), totals[key], key)
        page = self.page()
        self.assertEqual(page["xp"]["total"]["total"], sum(totals.values()))

    def test_level_follows_the_real_thresholds(self):
        # 10 present lessons (100 XP) + 10 checked homeworks without grades (100 XP) = 200 XP → level 2 (100…300).
        for i in range(10):
            self.held(20 - i, i + 1, hw_status="checked")
        level = self.page()["level"]
        self.assertEqual((level["level"], level["total_xp"], level["floor"], level["next"], level["to_next"]), (2, 200, 100, 300, 100))
        self.assertEqual(level["progress"], 50)
        self.assertEqual(data.level_for(299)["level"], 2)
        self.assertEqual(data.level_for(300)["level"], 3)

    def test_achievements_unlock_only_from_records_with_their_real_date(self):
        lessons = [self.held(40 - i * 3, i + 1, hw_status="checked", score=10 if i == 2 else 7) for i in range(6)]
        items = {i["id"]: i for i in self.page()["achievements"]}
        fifth = items["homework_done-5"]
        self.assertTrue(fifth["unlocked"])
        self.assertEqual(fifth["unlocked_on"], lessons[4].date)  # the 5th completed homework
        self.assertEqual(items["top_homework-1"]["unlocked_on"], lessons[2].date)
        self.assertFalse(items["homework_done-20"]["unlocked"])
        self.assertEqual(items["homework_done-20"]["current"], 6)
        self.assertFalse(items["scholarship"]["unlocked"])
        self.assertTrue(all(i["xp_reward"] is None for i in items.values()))  # no rewards are configured in the LMS
        rarities = {i["rarity"] for i in items.values()}
        self.assertTrue(rarities <= set(gamification.RARITIES))

    def test_level_unlock_date_is_the_day_xp_reached_it(self):
        first = self.held(10, 1, hw_status="checked")   # 20 XP
        for i in range(4):
            self.held(9 - i, i + 2, hw_status="checked")  # +20 each → 100 XP on the 5th lesson
        items = {i["id"]: i for i in self.page()["achievements"]}
        self.assertEqual(items["level-2"]["unlocked_on"], TODAY - dt.timedelta(days=6))
        self.assertNotEqual(items["level-2"]["unlocked_on"], first.date)
        self.assertFalse(items["level-5"]["unlocked"])

    def test_perfect_month_is_a_whole_past_month_without_misses(self):
        last_month_end = TODAY.replace(day=1) - dt.timedelta(days=1)
        for i in range(4):
            self.held(0, i + 1, mark=None)  # today's lessons don't matter
            lesson = self.lesson(self.g1, self.gt1, last_month_end - dt.timedelta(days=i * 2), number=50 + i)
            Attendance.objects.create(student=self.student, lesson=lesson, status=Attendance.Status.PRESENT)
        items = {i["id"]: i for i in self.page()["achievements"]}
        key = f"perfect_month-{last_month_end:%Y-%m}"
        self.assertIn(key, items)
        self.assertEqual(items[key]["unlocked_on"], last_month_end)
        Attendance.objects.filter(lesson__lesson_number=50).update(status=Attendance.Status.ABSENT)
        self.assertNotIn(key, {i["id"] for i in self.page()["achievements"]})

    def test_weekly_activity_and_previous_week(self):
        self.held(1, 1, hw_status="checked", score=9)    # this week: 10 + 10 + 9
        self.held(9, 2)                                   # previous week: 10
        weekly = self.page()["weekly"]
        self.assertEqual(len(weekly["days"]), 7)
        yesterday = next(d for d in weekly["days"] if d["date"] == TODAY - dt.timedelta(days=1))
        self.assertEqual((yesterday["xp"], yesterday["xp_attendance"], yesterday["xp_homework"], yesterday["lessons"], yesterday["homework"]),
                         (29, 10, 19, 1, 1))
        self.assertEqual((weekly["total"], weekly["previous_total"]), (29, 10))

    def test_no_history_means_no_comparison_and_no_events(self):
        page = self.page()
        self.assertIsNone(page["weekly"]["previous_total"])
        self.assertEqual(page["weekly"]["total"], 0)
        self.assertEqual(page["timeline"], [])
        self.assertFalse(any(i["unlocked"] for i in page["achievements"]))

    def test_timeline_holds_real_events(self):
        for i in range(5):
            self.held(8 - i, i + 1, hw_status="checked")
        kinds = {e["kind"] for e in self.page()["timeline"]}
        self.assertEqual(kinds, {"xp", "achievement", "level"})

    def test_only_own_children(self):
        other = Student.objects.create(first_name="Other", last_name="Kid", group=self.g1)
        self.assertEqual(self.client_.get(reverse("portal:achievements", args=[other.pk])).status_code, 404)
        self.assertEqual(self.client_.post(reverse("portal:achievements", args=[self.student.pk])).status_code, 405)
