"""The public leaderboard: XP rules, period boundaries (project timezone),
ranking / ties / changes, group methodology, filters & pagination, and the
public API contract — open to anyone, read-only, no personal data.
"""
from __future__ import annotations

import datetime as dt
import json
import zoneinfo

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academy.models import Attendance, Course, Group, Homework, HomeworkResult, Lesson, Student
from apps.leaderboard import services
from apps.leaderboard.services import Period, month_period, resolve_period, week_period, year_period
from apps.testing.models import AttemptStatus, SessionType, StudentAttempt, Test, TestSession

BISHKEK = zoneinfo.ZoneInfo("Asia/Bishkek")
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "leaderboard-tests"}}
STUDENT_KEYS = {"key", "rank", "name", "initials", "hidden", "group", "course", "xp", "breakdown", "change"}
GROUP_KEYS = {"key", "rank", "name", "course", "members", "active_students", "total_xp", "average_xp", "top_members", "change"}
BOARD_KEYS = {"period", "previous_period", "generated_at", "participants", "podium", "count", "page", "page_size",
              "num_pages", "results"}


class LeaderboardFixture(TestCase):
    def setUp(self):
        cache.clear()
        self.course = Course.objects.create(name="Prog SOFT", count_lesson=40)
        self.design = Course.objects.create(name="Design", count_lesson=40)
        self.group = Group.objects.create(name="Prog 1", course=self.course, start_date=dt.date(2024, 9, 1))
        self.group2 = Group.objects.create(name="Design 1", course=self.design, start_date=dt.date(2024, 9, 1))
        self.alice = self.student("Алия", "Садыкова", self.group, phone="+996 700 111 222", parent_phone="+996 700 333 444")
        self.bob = self.student("Бакыт", "Асанов", self.group)
        self.cara = self.student("Чынара", "Омурова", self.group2)
        self.lessons: dict = {}
        self.test = Test.objects.create(title="Python Basics")
        self.api = APIClient()

    # -- builders ---------------------------------------------------------
    def student(self, first, last, group, **extra):
        return Student.objects.create(first_name=first, last_name=last, group=group, **extra)

    def lesson(self, group, date, status=Lesson.Status.COMPLETED):
        key = (group.pk, date, status)
        if key not in self.lessons:
            number = Lesson.objects.filter(group=group).count() + 1
            self.lessons[key] = Lesson.objects.create(
                group=group, lesson_number=number, date=date, start_time=dt.time(10), end_time=dt.time(11), status=status,
            )
        return self.lessons[key]

    def attend(self, student, date, status=Attendance.Status.PRESENT, lesson_status=Lesson.Status.COMPLETED, group=None):
        lesson = self.lesson(group or student.group, date, lesson_status)
        return Attendance.objects.create(student=student, lesson=lesson, status=status)

    def homework(self, student, date, status=HomeworkResult.Status.CHECKED, score=None):
        homework = Homework.objects.create(lesson=self.lesson(student.group, date), title="ДЗ")
        return HomeworkResult.objects.create(homework=homework, student=student, status=status, score=score)

    def attempt(self, student, finished_at, score, session=None, status=AttemptStatus.FINISHED):
        session = session or TestSession.objects.create(test=self.test, session_type=SessionType.TRAINING)
        return StudentAttempt.objects.create(
            session=session, student=student, student_name=str(student), status=status, score=score, finished_at=finished_at,
        )

    def board(self, period: Period) -> dict:
        return services.compute(period, today=dt.date(2026, 10, 14))

    def xp(self, period: Period) -> dict[str, int]:
        return {row["name"]: row["xp"] for row in self.board(period)["students"]}

    def get(self, name, **params):
        return self.api.get(reverse(name), params)


class XpRuleTests(LeaderboardFixture):
    def test_attendance_homework_and_test_rules(self):
        day = dt.date(2025, 3, 12)
        self.attend(self.alice, day)                                                # 10
        self.attend(self.alice, day + dt.timedelta(days=1), Attendance.Status.LATE)  # 5
        self.attend(self.alice, day + dt.timedelta(days=2), Attendance.Status.ABSENT)
        self.attend(self.alice, day + dt.timedelta(days=3), Attendance.Status.EXCUSED)
        self.homework(self.alice, day, HomeworkResult.Status.CHECKED, score=8)       # 10 + 8
        self.homework(self.alice, day, HomeworkResult.Status.LATE)                   # 5
        self.homework(self.alice, day, HomeworkResult.Status.NOT_SUBMITTED, score=9)  # 0
        self.attempt(self.alice, dt.datetime(2025, 3, 12, 12, tzinfo=BISHKEK), 87)   # round(17.4) = 17
        row = self.board(month_period(2025, 3))["students"][0]
        self.assertEqual(row["breakdown"], {"attendance": 15, "homework": 23, "tests": 17})
        self.assertEqual(row["xp"], 55)

    def test_cancelled_lessons_earn_nothing(self):
        day = dt.date(2025, 3, 12)
        self.attend(self.alice, day, lesson_status=Lesson.Status.CANCELLED)
        self.assertEqual(self.xp(month_period(2025, 3)), {})

    def test_retaking_a_test_never_credits_twice(self):
        session = TestSession.objects.create(test=self.test, session_type=SessionType.TRAINING)
        self.attempt(self.alice, dt.datetime(2025, 3, 3, 12, tzinfo=BISHKEK), 50, session)
        self.attempt(self.alice, dt.datetime(2025, 3, 4, 12, tzinfo=BISHKEK), 100, session)
        self.attempt(self.alice, dt.datetime(2025, 4, 2, 12, tzinfo=BISHKEK), 100, session)  # same best, later month
        self.attempt(self.alice, dt.datetime(2025, 4, 3, 12, tzinfo=BISHKEK), 0, session, AttemptStatus.ACTIVE)
        self.assertEqual(self.xp(month_period(2025, 3)), {"Алия С.": 20})
        self.assertEqual(self.xp(month_period(2025, 4)), {})

    def test_a_corrected_result_changes_the_leaderboard(self):
        record = self.attend(self.alice, dt.date(2025, 3, 12))
        self.assertEqual(self.xp(month_period(2025, 3)), {"Алия С.": 10})
        record.status = Attendance.Status.ABSENT
        record.save()
        self.assertEqual(self.xp(month_period(2025, 3)), {})


class PeriodTests(LeaderboardFixture):
    def test_period_bounds(self):
        self.assertEqual(year_period(2025), Period("year", dt.date(2025, 1, 1), dt.date(2025, 12, 31)))
        self.assertEqual(month_period(2024, 2).end, dt.date(2024, 2, 29))
        self.assertEqual(month_period(2025, 12).end, dt.date(2025, 12, 31))
        self.assertEqual(week_period(dt.date(2025, 3, 13)), Period("week", dt.date(2025, 3, 10), dt.date(2025, 3, 16)))
        self.assertEqual(month_period(2025, 1).previous(), month_period(2024, 12))
        self.assertEqual(week_period(dt.date(2025, 3, 10)).previous().start, dt.date(2025, 3, 3))
        self.assertEqual(year_period(2025).previous(), year_period(2024))

    def test_resolve_defaults_and_validation(self):
        today = dt.date(2026, 10, 14)
        self.assertEqual(resolve_period(today=today), month_period(2026, 10))
        self.assertEqual(resolve_period("week", today=today).start, dt.date(2026, 10, 12))
        self.assertEqual(resolve_period("year", "2025", today=today), year_period(2025))
        for args in (("day",), ("month", "2026", "13"), ("month", "abc"), ("year", "2027"), ("month", "2026", "11"),
                     ("week", None, None, "2026-10-13"), ("week", None, None, "2026-10-19"), ("week", None, None, "nope")):
            with self.subTest(args=args), self.assertRaises(services.LeaderboardError):
                resolve_period(*args, today=today)

    def test_year_counts_only_its_own_year(self):
        self.attend(self.alice, dt.date(2024, 12, 31))
        self.attend(self.alice, dt.date(2025, 1, 1))
        self.attend(self.alice, dt.date(2025, 12, 31))
        self.attend(self.alice, dt.date(2026, 1, 1))
        self.assertEqual(self.xp(year_period(2025)), {"Алия С.": 20})

    def test_month_counts_only_its_own_month(self):
        self.attend(self.bob, dt.date(2025, 2, 28))
        self.attend(self.bob, dt.date(2025, 3, 1))
        self.attend(self.bob, dt.date(2025, 3, 31))
        self.attend(self.bob, dt.date(2025, 4, 1))
        self.assertEqual(self.xp(month_period(2025, 3)), {"Бакыт А.": 20})

    def test_week_runs_monday_to_sunday(self):
        self.attend(self.cara, dt.date(2025, 3, 9))   # Sunday before
        self.attend(self.cara, dt.date(2025, 3, 10))  # Monday
        self.attend(self.cara, dt.date(2025, 3, 16))  # Sunday
        self.attend(self.cara, dt.date(2025, 3, 17))  # next Monday
        self.assertEqual(self.xp(week_period(dt.date(2025, 3, 10))), {"Чынара О.": 20})

    def test_test_attempts_use_the_project_timezone(self):
        # 19:30 UTC on Sunday 9 March is 01:30 on Monday 10 March in Bishkek.
        self.attempt(self.alice, dt.datetime(2025, 3, 9, 19, 30, tzinfo=dt.timezone.utc), 100)
        self.assertEqual(self.xp(week_period(dt.date(2025, 3, 10))), {"Алия С.": 20})
        self.assertEqual(self.xp(week_period(dt.date(2025, 3, 3))), {})
        # 23:59 local on 31 March stays in March even though UTC is still the 31st 17:59.
        self.attempt(self.bob, dt.datetime(2025, 3, 31, 23, 59, tzinfo=BISHKEK), 100)
        self.attempt(self.cara, dt.datetime(2025, 4, 1, 0, 1, tzinfo=BISHKEK), 100)
        self.assertEqual(set(self.xp(month_period(2025, 3))), {"Алия С.", "Бакыт А."})
        self.assertEqual(set(self.xp(month_period(2025, 4))), {"Чынара О."})


class RankingTests(LeaderboardFixture):
    def test_ties_share_a_place_and_sort_by_name(self):
        day = dt.date(2025, 3, 12)
        for student in (self.bob, self.alice, self.cara):
            self.attend(student, day)
        self.attend(self.cara, day + dt.timedelta(days=1))
        rows = self.board(month_period(2025, 3))["students"]
        self.assertEqual([(r["rank"], r["name"]) for r in rows], [(1, "Чынара О."), (2, "Алия С."), (2, "Бакыт А.")])

    def test_ineligible_students_are_not_listed(self):
        day = dt.date(2025, 3, 12)
        inactive = self.student("Неактивный", "Студент", self.group)
        Student.objects.filter(pk=inactive.pk).update(is_active=False, status=Student.Status.WITHDRAWN)
        closed = Group.objects.create(name="Old", course=self.course, start_date=dt.date(2024, 1, 1), status=Group.Status.CANCELLED)
        in_closed = self.student("Закрытая", "Группа", closed)
        nogroup = self.student("Без", "Группы", self.group)
        for student in (inactive, in_closed, nogroup):
            self.attend(student, day)
        Student.objects.filter(pk=nogroup.pk).update(group=None)
        self.attend(self.alice, day)
        self.assertEqual(self.xp(month_period(2025, 3)), {"Алия С.": 10})

    def test_students_without_xp_are_not_ranked(self):
        self.attend(self.alice, dt.date(2025, 3, 12), Attendance.Status.ABSENT)
        self.assertEqual(self.board(month_period(2025, 3))["students"], [])

    def test_hidden_student_keeps_their_place_without_a_name(self):
        Student.objects.filter(pk=self.alice.pk).update(show_in_leaderboard=False)
        self.attend(self.alice, dt.date(2025, 3, 12))
        self.attend(self.alice, dt.date(2025, 3, 13))
        self.attend(self.bob, dt.date(2025, 3, 12))
        board = self.board(month_period(2025, 3))
        first, second = board["students"]
        self.assertEqual((first["rank"], first["name"], first["hidden"], first["group"], first["initials"]),
                         (1, services.HIDDEN_NAME, True, None, ""))
        self.assertEqual((second["rank"], second["name"]), (2, "Бакыт А."))
        group = board["groups"][0]
        self.assertEqual(group["total_xp"], 30)
        self.assertEqual([m["name"] for m in group["top_members"]], ["Бакыт А."])

    def test_position_change_against_the_previous_period(self):
        # February: Bob 1st, Alice 2nd. March: Alice 1st, Bob 2nd, Cara new.
        self.attend(self.bob, dt.date(2025, 2, 10))
        self.attend(self.bob, dt.date(2025, 2, 11))
        self.attend(self.alice, dt.date(2025, 2, 10))
        for day in (10, 11, 12):
            self.attend(self.alice, dt.date(2025, 3, day))
        self.attend(self.bob, dt.date(2025, 3, 10))
        self.attend(self.bob, dt.date(2025, 3, 11))
        self.attend(self.cara, dt.date(2025, 3, 10))
        changes = {r["name"]: r["change"] for r in self.board(month_period(2025, 3))["students"]}
        self.assertEqual(changes["Алия С."], {"status": "up", "value": 1})
        self.assertEqual(changes["Бакыт А."], {"status": "down", "value": -1})
        self.assertEqual(changes["Чынара О."], {"status": "new", "value": 0})
        # April vs March: same order for Alice → "same".
        self.attend(self.alice, dt.date(2025, 4, 1))
        self.assertEqual(self.board(month_period(2025, 4))["students"][0]["change"], {"status": "same", "value": 0})

    def test_no_previous_data_means_no_change_is_invented(self):
        self.attend(self.alice, dt.date(2025, 3, 12))
        board = self.board(month_period(2025, 3))
        self.assertIsNone(board["students"][0]["change"])
        self.assertIsNone(board["groups"][0]["change"])


class GroupRankingTests(LeaderboardFixture):
    def test_groups_rank_by_average_not_by_size(self):
        # Prog 1: 3 students, 30 XP total (avg 10). Design 1: 1 student, 20 XP (avg 20).
        extra = self.student("Данияр", "Беков", self.group)
        day = dt.date(2025, 3, 12)
        for student in (self.alice, self.bob, extra):
            self.attend(student, day)
        self.attend(self.cara, day)
        self.attend(self.cara, day + dt.timedelta(days=1))
        groups = self.board(month_period(2025, 3))["groups"]
        self.assertEqual([(g["rank"], g["name"], g["total_xp"], g["average_xp"], g["members"]) for g in groups],
                         [(1, "Design 1", 20, 20.0, 1), (2, "Prog 1", 30, 10.0, 3)])

    def test_average_counts_every_listed_member_including_those_without_xp(self):
        self.attend(self.alice, dt.date(2025, 3, 12))
        group = self.board(month_period(2025, 3))["groups"][0]
        self.assertEqual((group["members"], group["active_students"], group["average_xp"]), (2, 1, 5.0))

    def test_group_change_and_empty_groups(self):
        self.attend(self.alice, dt.date(2025, 2, 12))
        self.attend(self.cara, dt.date(2025, 3, 12))
        self.attend(self.alice, dt.date(2025, 3, 12))
        self.attend(self.alice, dt.date(2025, 3, 13))
        self.attend(self.bob, dt.date(2025, 3, 13))
        groups = {g["name"]: g for g in self.board(month_period(2025, 3))["groups"]}
        self.assertEqual(groups["Prog 1"]["change"], {"status": "same", "value": 0})
        self.assertEqual(groups["Design 1"]["change"], {"status": "new", "value": 0})
        self.assertEqual(self.board(month_period(2025, 5))["groups"], [])


class PublicApiTests(LeaderboardFixture):
    def setUp(self):
        super().setUp()
        self.attend(self.alice, dt.date(2025, 3, 12))
        self.attend(self.alice, dt.date(2025, 3, 13))
        self.attend(self.bob, dt.date(2025, 3, 12), Attendance.Status.LATE)
        self.attend(self.cara, dt.date(2025, 3, 12))
        self.params = {"period": "month", "year": 2025, "month": 3}

    def test_anyone_can_read_without_login(self):
        for name in ("public-leaderboard-meta", "public-leaderboard-students", "public-leaderboard-groups"):
            with self.subTest(name=name):
                response = self.get(name, **self.params)
                self.assertEqual(response.status_code, 200)
                self.assertIn("public", response["Cache-Control"])
        self.api.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        self.assertEqual(self.get("public-leaderboard-students", **self.params).status_code, 200)

    def test_read_only(self):
        for name in ("public-leaderboard-meta", "public-leaderboard-students", "public-leaderboard-groups"):
            url = reverse(name)
            for method in ("post", "put", "patch", "delete"):
                with self.subTest(name=name, method=method):
                    self.assertEqual(getattr(self.api, method)(url, {"xp": 1000}, format="json").status_code, 405)
        self.assertEqual(Attendance.objects.count(), 4)

    def test_students_payload_is_a_closed_whitelist(self):
        data = self.get("public-leaderboard-students", **self.params).json()
        self.assertEqual(set(data), BOARD_KEYS)
        self.assertEqual(data["participants"], 3)
        self.assertEqual([r["name"] for r in data["results"]], ["Алия С.", "Чынара О.", "Бакыт А."])
        for row in data["results"] + data["podium"]:
            self.assertEqual(set(row), STUDENT_KEYS)
            self.assertEqual(set(row["group"]), {"key", "name"})
        raw = json.dumps(data, ensure_ascii=False)
        for secret in ("+996", "Садыкова", "Асанов", "phone", "status_label", '"id"', "email"):
            self.assertNotIn(secret, raw)
        self.assertNotIn(f'"key": "{self.alice.pk}"', raw)

    def test_groups_payload_is_a_closed_whitelist(self):
        data = self.get("public-leaderboard-groups", **self.params).json()
        self.assertEqual(set(data), BOARD_KEYS | {"students_ranked"})
        self.assertEqual(data["students_ranked"], 3)
        for row in data["results"]:
            self.assertEqual(set(row), GROUP_KEYS)
            for member in row["top_members"]:
                self.assertEqual(set(member), {"name", "initials", "xp"})
        self.assertNotIn("+996", json.dumps(data, ensure_ascii=False))

    def test_filters_search_order_and_pagination(self):
        group_key = services.public_key("group", self.group.pk)
        course_key = services.public_key("course", self.design.pk)

        def names(**extra):
            return [r["name"] for r in self.get("public-leaderboard-students", **self.params, **extra).json()["results"]]

        self.assertEqual(names(q="алия"), ["Алия С."])
        self.assertEqual(names(q="Садыкова"), [])  # the full surname is never searchable/public
        self.assertEqual(names(group=group_key), ["Алия С.", "Бакыт А."])
        self.assertEqual(names(course=course_key), ["Чынара О."])
        self.assertEqual(names(group="unknownkey"), [])
        self.assertEqual(names(group="../bad"), [])
        self.assertEqual(names(order="asc"), ["Бакыт А.", "Чынара О.", "Алия С."])

        page = self.get("public-leaderboard-students", **self.params, page_size=2, page=2).json()
        self.assertEqual((page["count"], page["num_pages"], page["page"]), (3, 2, 2))
        self.assertEqual([r["rank"] for r in page["results"]], [3])
        # Filtering keeps the global place and the podium.
        filtered = self.get("public-leaderboard-students", **self.params, group=group_key).json()
        self.assertEqual([r["rank"] for r in filtered["results"]], [1, 3])
        self.assertEqual(len(filtered["podium"]), 3)

        groups = self.get("public-leaderboard-groups", **self.params, q="design").json()["results"]
        self.assertEqual([g["name"] for g in groups], ["Design 1"])

    def test_invalid_parameters_are_rejected(self):
        for params in ({"period": "day"}, {"period": "month", "year": 2025, "month": 13},
                       {"period": "week", "week_start": "2025-03-11"}, {"period": "year", "year": 3000},
                       {"period": "month", "year": 2025, "month": 3, "page_size": 1000},
                       {"period": "month", "year": 2025, "month": 3, "order": "name"}):
            with self.subTest(params=params):
                self.assertEqual(self.get("public-leaderboard-students", **params).status_code, 400)

    def test_empty_period(self):
        data = self.get("public-leaderboard-students", period="week", week_start="2025-06-02").json()
        self.assertEqual((data["count"], data["participants"], data["results"], data["podium"]), (0, 0, [], []))
        groups = self.get("public-leaderboard-groups", period="year", year=2024).json()
        self.assertEqual(groups["results"], [])

    def test_meta(self):
        data = self.get("public-leaderboard-meta").json()
        self.assertEqual(data["timezone"], "Asia/Bishkek")
        self.assertIn(2025, data["years"])
        self.assertEqual({g["name"] for g in data["groups"]}, {"Prog 1", "Design 1"})
        self.assertEqual({c["name"] for c in data["courses"]}, {"Prog SOFT", "Design"})
        self.assertEqual(data["rules"]["group_method"], "average")
        self.assertNotIn("+996", json.dumps(data, ensure_ascii=False))

    @override_settings(CACHES=LOCMEM)
    def test_cache_is_invalidated_when_a_result_changes(self):
        cache.clear()
        first = self.get("public-leaderboard-students", **self.params).json()
        self.assertEqual(first["results"][0]["xp"], 20)
        self.attend(self.alice, dt.date(2025, 3, 14))
        second = self.get("public-leaderboard-students", **self.params).json()
        self.assertEqual(second["results"][0]["xp"], 30)
