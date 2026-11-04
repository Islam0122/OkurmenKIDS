"""Раздел «Академия» кабинета операционного директора: только чтение, цифры —
из существующих сервисов LMS и оплаты обучения."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.academy.models import Attendance, GroupSchedule, Homework, HomeworkResult, Student
from apps.billing.services import payments
from apps.billing.services.contracts import money_summary
from apps.billing.tests.base import BillingMixin, make_user
from apps.operations.tests.base import jwt_client
from apps.scholarships.tests.base import OCT_1, ScholarshipFixture
from apps.users.models import User

API = "/api/v1/operations/academy"
ENDPOINTS = ("meta/", "groups/", "students/", "performance/", "monthly/")


class AcademyCabinetTests(BillingMixin, TestCase):
    def setUp(self):
        self.build()
        self.od = make_user("odir", User.Role.OPERATIONS_DIRECTOR)
        self.good = self.student()
        self.absent = self.student()
        self.other = self.student(self.group_b)
        # Занятия — последние 4 дня; период тестов — свой (`custom`) вокруг них,
        # чтобы результат не зависел от того, какое сегодня число месяца.
        self.lessons = self.hold(4, start_day=self.today - dt.timedelta(days=3))
        self.range = {"period": "custom", "start_date": (self.today - dt.timedelta(days=5)).isoformat(),
                      "end_date": self.today.isoformat()}
        for lesson in self.lessons:
            self.mark(lesson, self.good, Attendance.Status.PRESENT)
            self.mark(lesson, self.absent, Attendance.Status.ABSENT)
        homework = Homework.objects.create(lesson=self.lessons[0], title="Циклы", deadline=self.today)
        HomeworkResult.objects.create(homework=homework, student=self.good, status=HomeworkResult.Status.CHECKED, score=9)
        HomeworkResult.objects.create(homework=homework, student=self.absent, status=HomeworkResult.Status.NOT_SUBMITTED)
        GroupSchedule.objects.create(group=self.group, teacher=self.trainer, subject=self.it, day_of_week="mon",
                                     start_time=dt.time(10), end_time=dt.time(11))
        self.contract = self.profile(self.good)
        payments.record_payment(profile=self.contract, amount=Decimal("4000"), received_date=self.today,
                                actor=self.accountant, comment="Оплата за 1 месяц")

    def get(self, path, user=None, **params):
        if "period" not in params:
            params.update(self.range)
        response = self.client_for(user or self.od).get(f"{API}/{path}", params)
        self.assertEqual(response.status_code, 200, getattr(response, "data", response.content))
        return response.data

    # -- права -------------------------------------------------------------

    def test_who_can_open_and_everything_is_read_only(self):
        detail_urls = (f"groups/{self.group.pk}/", f"students/{self.good.pk}/")
        for user in (self.od, self.director, self.admin):
            for path in (*ENDPOINTS, *detail_urls):
                with self.subTest(user=user.username, path=path):
                    self.get(path, user)
        for user in (self.trainer.user, self.manager, self.accountant, make_user("hrm", User.Role.HR_MANAGER)):
            self.assertEqual(self.client_for(user).get(f"{API}/groups/").status_code, 403, user.role)
        client = self.client_for(self.od)
        for path in (*ENDPOINTS, *detail_urls):
            for method in ("post", "put", "patch", "delete"):
                with self.subTest(path=path, method=method):
                    self.assertEqual(getattr(client, method)(f"{API}/{path}", {}, format="json").status_code, 405)
        # Настоящий JWT: изоляция ролей пропускает операционного директора в /operations/.
        self.assertEqual(jwt_client(self.od.username).get(f"{API}/students/").status_code, 200)

    def test_unknown_period_is_a_validation_error(self):
        response = self.client_for(self.od).get(f"{API}/groups/", {"period": "custom", "start_date": "2026-01-01"})
        self.assertEqual(response.status_code, 400)

    # -- группы ------------------------------------------------------------

    def test_groups_overview_and_filters(self):
        data = self.get("groups/")
        rows = {r["name"]: r for r in data["results"]}
        a = rows["Group A"]
        self.assertEqual((a["program"], a["students"]["active"], a["attendance_rate"]), ("Okurmen 144", 2, 50.0))
        self.assertEqual(a["trainers"][0]["name"], str(self.trainer))
        self.assertEqual(a["plan"]["completed"], 4)
        self.assertEqual(data["summary"]["groups"], 2)
        self.assertEqual([r["name"] for r in self.get("groups/", search="group b")["results"]], ["Group B"])
        self.assertEqual(self.get("groups/", status="closed")["results"], [])
        self.assertEqual(len(self.get("groups/", program=self.course.pk)["results"]), 2)
        self.assertEqual(self.get("groups/", teacher=self.trainer.pk)["summary"]["groups"], 2)
        self.assertEqual(self.get("groups/", page_size=1, page=2)["page"], 2)

    def test_list_plan_progress_matches_group_analytics(self):
        from apps.academy.models import Group
        from apps.operations.services.academy_cabinet import _plan_progress, plan_progress_for

        self.plan_lessons(3, start_day=self.today + dt.timedelta(days=1))
        groups = list(Group.objects.all())
        bulk = plan_progress_for(groups)
        for group in groups:
            self.assertEqual(bulk[group.pk], _plan_progress(group, self.today), group.name)

    def test_group_detail(self):
        data = self.get(f"groups/{self.group.pk}/")
        students = {s["id"]: s for s in data["student_progress"]}
        self.assertEqual((students[self.good.pk]["attendance_rate"], students[self.absent.pk]["attendance_rate"]),
                         (100.0, 0.0))
        self.assertEqual(students[self.good.pk]["homework_rate"], 100.0)
        self.assertGreater(students[self.good.pk]["xp"], 0)
        self.assertEqual(len(data["lesson_history"]), 4)
        self.assertEqual(data["lesson_history"][0]["attendance"], {"marked": 2, "attended": 1})
        self.assertEqual(len(data["monthly"]), 6)
        self.assertEqual([(x["day"], x["start"], x["subject"]) for x in data["schedule"]], [("Понедельник", "10:00", "IT")])
        self.assertEqual(data["group"]["name"], "Group A")
        self.assertIn("exams", data["assessments"])
        self.assertEqual(self.client_for(self.od).get(f"{API}/groups/999999/").status_code, 404)

    # -- студенты и деньги ---------------------------------------------------

    def test_student_directory_finance_matches_billing(self):
        data = self.get("students/")
        rows = {r["id"]: r for r in data["results"]}
        self.assertTrue(data["finance_visible"])
        summary = money_summary(self.contract)
        finance = rows[self.good.pk]["finance"]
        self.assertEqual((finance["paid"], finance["debt"]),
                         (str(summary["paid_total"]), str(summary["outstanding"])))
        self.assertIsNone(rows[self.other.pk]["finance"])  # нет договора — ничего не придумано
        self.assertEqual(rows[self.good.pk]["attendance_rate"], 100.0)
        self.assertEqual(rows[self.good.pk]["group"]["name"], "Group A")
        self.assertEqual(rows[self.good.pk]["trainers"], [str(self.trainer)])
        self.assertEqual([r["id"] for r in self.get("students/", group=self.group_b.pk)["results"]], [self.other.pk])
        self.assertEqual(self.get("students/", search=self.good.first_name)["count"], 1)
        self.assertEqual(self.get("students/", status="withdrawn")["count"], 0)

    def test_student_profile_contract_and_payments_read_only(self):
        data = self.get(f"students/{self.good.pk}/")
        contract = data["finance"]["contracts"][0]
        summary = money_summary(self.contract)
        self.assertEqual((contract["paid"], contract["debt"]), (str(summary["paid_total"]), str(summary["outstanding"])))
        payment = data["finance"]["payments"][0]
        self.assertEqual((payment["amount"], payment["status"], payment["comment"]), ("4000.00", "confirmed",
                                                                                      "Оплата за 1 месяц"))
        academic = data["academic"]
        self.assertEqual((academic["attended"], academic["attendance_rate"]), (4, 100.0))
        self.assertEqual(len(academic["lessons"]), 4)
        self.assertGreater(academic["xp"]["total"], 0)
        self.assertFalse(academic["badges_tracked"])
        self.assertEqual(data["student"]["program"], "Okurmen 144")

    def test_finance_hidden_without_money_access(self):
        from apps.operations.services import academy_cabinet
        from apps.operations.services.period import from_query

        f = from_query({"period": "this_month"})
        page = academy_cabinet.students_page(f, {}, with_finance=False)
        self.assertTrue(all(r["finance"] is None for r in page["results"]))
        self.assertIsNone(academy_cabinet.student_profile(self.good, f, with_finance=False)["finance"])

    def test_student_list_queries_do_not_grow_with_students(self):
        def count():
            with CaptureQueriesContext(connection) as ctx:
                self.get("students/", page_size=5)
            return len(ctx.captured_queries)

        for _ in range(4):
            self.student()
        before = count()
        for _ in range(20):
            self.student(self.group_b)
        self.assertEqual(count(), before)

    # -- успеваемость и месячные результаты ---------------------------------

    def test_performance_page(self):
        data = self.get("performance/")
        indicators = data["indicators"]
        self.assertEqual((indicators["attended"], indicators["missed"], indicators["attendance_rate"]), (4, 4, 50.0))
        self.assertEqual(indicators["homework_rate"], 50.0)
        self.assertGreater(indicators["xp"], 0)
        self.assertEqual((indicators["progress_rate"], indicators["active_students"], indicators["students"]), (90.0, 1, 3))
        self.assertEqual(indicators["activity_rate"], 33.3)
        self.assertIsInstance(indicators["kpi"], float)
        rows = {r["id"]: r for r in data["results"]}
        self.assertEqual((rows[self.absent.pk]["missed"], rows[self.absent.pk]["attended"]), (4, 0))
        self.assertIn("attendance_rate", rows[self.good.pk]["change"])
        self.assertIn("exams", data["indicators"])
        only_b = self.get("performance/", group=self.group_b.pk)
        self.assertEqual([r["id"] for r in only_b["results"]], [self.other.pk])
        self.assertEqual(only_b["indicators"]["attended"], 0)
        earlier = {"period": "custom", "start_date": (self.today - dt.timedelta(days=60)).isoformat(),
                   "end_date": (self.today - dt.timedelta(days=30)).isoformat()}
        self.assertEqual(self.get("performance/", **earlier)["indicators"]["attended"], 0)
        self.assertEqual(data["previous_period"]["end"], self.today - dt.timedelta(days=6))

    def test_monthly_report_and_attention(self):
        self.transfer(self.other, self.group, self.today)
        data = self.get("monthly/")
        ind = data["indicators"]
        self.assertEqual((ind["active_students"], ind["transferred_students"]), (3, 1))
        self.assertEqual(ind["attendance_rate"], 50.0)
        # Успеваемость — KPI «Прогресс (средний балл ДЗ)»: одна оценка 9 из 10; KPI — число, не объект.
        self.assertEqual(ind["academic_performance"], 90.0)
        self.assertIsInstance(ind["kpi"], float)
        self.assertEqual(data["dynamics"][-1]["progress_rate"], 90.0)
        self.assertEqual(len(data["dynamics"]), 6)
        self.assertEqual(data["dynamics"][-1]["attendance_rate"], 50.0)
        self.assertEqual({g["name"] for g in data["groups"]}, {"Group A", "Group B"})
        flagged = {r["id"]: r for r in data["attention"]}
        self.assertIn(self.absent.pk, flagged)
        self.assertNotIn(self.good.pk, flagged)
        reasons = " ".join(flagged[self.absent.pk]["reasons"])
        self.assertIn("Частые пропуски: 4", reasons)
        self.assertIn("Низкая посещаемость: 0%", reasons)
        self.assertEqual(ind["attention"], len(data["attention"]))

    def test_declining_performance_uses_configurable_threshold(self):
        from django.test import override_settings

        # Прошлый период для «последних 6 дней» — 6 дней перед ними.
        previous_lesson = self.lesson(day=self.today - dt.timedelta(days=8))
        self.mark(previous_lesson, self.good, Attendance.Status.PRESENT)
        self.mark(self.lessons[0], self.good, Attendance.Status.ABSENT)
        with override_settings(ASSISTANT_CONTROL_THRESHOLDS={"decline_points": 10}):
            reasons = {r["id"]: r["reasons"] for r in self.get("monthly/")["attention"]}
        self.assertTrue(any("Снизилась посещаемость: 100.0% → 75.0%" in r for r in reasons.get(self.good.pk, [])),
                        reasons)
        with override_settings(ASSISTANT_CONTROL_THRESHOLDS={"decline_points": 50}):
            reasons = {r["id"]: r["reasons"] for r in self.get("monthly/")["attention"]}
        self.assertFalse(any("Снизилась" in r for r in reasons.get(self.good.pk, [])))

    def test_no_writes_happen(self):
        before = (Student.objects.count(), Attendance.objects.count(), HomeworkResult.objects.count())
        for path in (*ENDPOINTS, f"groups/{self.group.pk}/", f"students/{self.good.pk}/"):
            self.get(path)
        self.assertEqual((Student.objects.count(), Attendance.objects.count(), HomeworkResult.objects.count()), before)



class AchievementsTests(ScholarshipFixture):
    """Достижения — утверждённые стипендии (других «достижений» и бейджей LMS не ведёт)."""

    def test_only_approved_scholarships_count(self):
        from apps.operations.services import academy_cabinet
        from apps.scholarships.models import ScholarshipAward

        self.configure(require_complete_feedback=False)
        student = self.student()
        self.study(student, self.python, self.t_python)
        award = self.generate().awards.get(student=student)
        self.assertEqual(academy_cabinet.achievements_by_student([student.pk]), {})
        ScholarshipAward.objects.filter(pk=award.pk).update(status=ScholarshipAward.Status.APPROVED)
        items = academy_cabinet.achievements_by_student([student.pk])[student.pk]
        self.assertEqual((len(items), items[0]["kind"], items[0]["date"]), (1, "scholarship", OCT_1))
        self.assertIn("1 место", items[0]["title"])
        self.assertEqual(academy_cabinet.achievements_by_student([student.pk], OCT_1.replace(day=2), OCT_1.replace(day=9)),
                         {})
