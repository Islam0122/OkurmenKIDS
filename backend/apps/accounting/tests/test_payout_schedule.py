"""График выплат по датам: блок 1–15 → 15-е, 16–конец → 1-е следующего месяца,
каждая сумма — в одной дате, незавершённые блоки — отдельно, удержание месяца
не повторяется, выплаты обновляют остаток и статус."""
from __future__ import annotations

import datetime as dt
from unittest import mock

from apps.academy.models import GroupTeacher, Lesson
from apps.accounting.services import deductions as ded
from apps.accounting.services import earnings
from apps.accounting.services.approval_service import approve_payroll
from apps.accounting.services.payment_service import register_payment
from apps.accounting.tests.base import FIRST, SECOND, D, day, make_user
from apps.accounting.tests.test_earnings import Fixture
from apps.accounting.tests.test_subject_cycles import days

API = "/api/v1/accounting"
OCT = (2026, 10)
TODAY = day(10, 20)


class ScheduleFixture(Fixture):
    def setUp(self):
        super().setUp()
        for _ in range(10):
            self.student(self.group_b)

    def teach_group(self, group, dates):
        program = GroupTeacher.objects.filter(group=group, teacher=self.trainer).first()
        with self.captureOnCommitCallbacks(execute=True):
            for d in dates:
                Lesson.objects.create(group=group, group_teacher=program, teacher=program.teacher, subject=self.python,
                                      lesson_number=2000 + Lesson.objects.count(), date=d, start_time=dt.time(12),
                                      end_time=dt.time(13), status=Lesson.Status.COMPLETED)

    def schedule(self, user=None):
        data = earnings.summary(user or self.trainer_user, today=TODAY)
        return data, {e["date"]: e for e in data["schedule"]}

    def tax(self, amount="3000"):
        ded.create_rule(actor=self.accountant, name="Налог", kind="TAX", amount=D(amount), frequency="MONTHLY",
                        scope="EMPLOYEE", employee=self.trainer_user, effective_from=day(1, 1))


class DateRuleTests(ScheduleFixture):
    def test_completed_on_10th_paid_on_15th(self):
        self.teach(days(10, 1, 10) + [day(10, 9), day(10, 10)])  # 12-й урок — 10 октября
        data, by_date = self.schedule()
        self.assertEqual(list(by_date), [day(10, 15)])
        self.assertEqual(by_date[day(10, 15)]["gross"], D("10000.00"))
        self.assertEqual(by_date[day(10, 15)]["items"][0]["completed_on"], day(10, 10))
        payroll = self.calc(FIRST, year_month=OCT)  # в расчёте — та же дата, не вторая
        data, by_date = self.schedule()
        self.assertEqual(list(by_date), [day(10, 15)])
        self.assertEqual(by_date[day(10, 15)]["items"][0]["payroll_id"], payroll.pk)

    def test_completed_on_17th_paid_on_1st_of_next_month(self):
        self.teach(days(10, 6, 17))  # 12-й урок — 17 октября
        _, by_date = self.schedule()
        self.assertEqual(list(by_date), [day(11, 1)])
        self.calc(SECOND, year_month=OCT)
        _, by_date = self.schedule()
        self.assertEqual(list(by_date), [day(11, 1)])

    def test_open_block_shown_but_not_scheduled(self):
        self.teach(days(10, 1, 9))
        data, by_date = self.schedule()
        self.assertEqual(by_date, {})
        self.assertEqual(data["not_included"]["gross"], D("7500.00"))
        self.assertEqual(data["not_included"]["items"][0]["lessons_taught"], 9)

    def test_several_blocks_on_one_date_are_summed_once(self):
        self.teach(days(10, 1, 12))
        self.teach_group(self.group_b, days(10, 2, 13))
        self.teach(days(10, 13, 15))  # следующий блок группы A идёт — не в выплату
        data, by_date = self.schedule()
        self.assertEqual(list(by_date), [day(10, 15)])
        self.assertEqual(by_date[day(10, 15)]["gross"], D("20000.00"))
        self.assertEqual(len(by_date[day(10, 15)]["items"]), 2)
        self.calc(FIRST, year_month=OCT)
        data, by_date = self.schedule()
        entry = by_date[day(10, 15)]
        self.assertEqual((entry["gross"], len(entry["items"]), len(entry["items"][0]["blocks"])),
                         (D("20000.00"), 1, 2))
        scheduled = sum((e["gross"] for e in data["schedule"]), D("0"))
        self.assertEqual(scheduled + data["not_included"]["gross"], data["earned"]["gross"])  # ни одной суммы дважды


class MoneyTests(ScheduleFixture):
    def test_tax_once_per_month_across_dates_and_open_work(self):
        self.tax("3000")
        self.teach(days(10, 1, 12))                       # → 15.10
        approve_payroll(self.calc(FIRST, year_month=OCT), self.director)
        self.teach_group(self.group_b, days(10, 5, 16))   # → 01.11 (не в расчёте)
        self.teach(days(10, 16, 18))                      # незавершённый блок
        data, by_date = self.schedule()
        total_tax = sum((e["tax"] for e in data["schedule"]), D("0")) + data["not_included"]["tax"]
        self.assertEqual(total_tax, D("3000.00"))
        self.assertEqual(by_date[day(10, 15)]["tax"], D("3000.00"))  # фактически взято в утверждённом расчёте
        self.assertEqual(by_date[day(11, 1)]["tax"], D("0"))
        self.assertEqual(data["earned"]["tax"], D("3000.00"))

    def test_payment_updates_remaining_and_status(self):
        self.tax("1000")
        self.teach(days(10, 1, 12))
        payroll = approve_payroll(self.calc(FIRST, year_month=OCT), self.director)
        _, by_date = self.schedule()
        entry = by_date[day(10, 15)]
        self.assertEqual((entry["net"], entry["remaining"], entry["status"]), (D("9000.00"), D("9000.00"), "SCHEDULED"))
        register_payment(payroll, amount=D("4000"), payment_date=day(10, 15), actor=self.accountant)
        _, by_date = self.schedule()
        entry = by_date[day(10, 15)]
        self.assertEqual((entry["paid"], entry["remaining"], entry["status"]),
                         (D("4000.00"), D("5000.00"), "PARTIALLY_PAID"))
        register_payment(payroll, amount=D("5000"), payment_date=day(10, 16), actor=self.accountant)
        _, by_date = self.schedule()
        entry = by_date[day(10, 15)]
        self.assertEqual((entry["paid"], entry["remaining"], entry["status"]), (D("9000.00"), D("0"), "PAID"))


class AccessTests(ScheduleFixture):
    def test_employee_own_only_accountant_all(self):
        other = make_user("other_t")
        self.teach(days(10, 1, 12))
        approve_payroll(self.calc(FIRST, year_month=OCT), self.director)
        with mock.patch("django.utils.timezone.localdate", return_value=TODAY):
            mine = self.client_for(self.trainer_user).get(f"{API}/my/salary/").json()["earnings"]
            self.assertEqual([e["date"] for e in mine["schedule"]], ["2026-10-15"])
            self.assertEqual(self.client_for(self.trainer_user).get(f"{API}/earnings/schedule/").status_code, 403)
            self.assertEqual(self.client_for(other).get(f"{API}/my/salary/").json()["earnings"]["schedule"], [])
            data = self.client_for(self.accountant).get(f"{API}/earnings/schedule/").json()
        [date] = data["dates"]
        self.assertEqual((date["date"], date["gross"], date["remaining"]), ("2026-10-15", "10000.00", "10000.00"))
        self.assertEqual([e["employee"] for e in date["employees"]], [self.trainer_user.pk])
        self.assertEqual(date["employees"][0]["net"], mine["schedule"][0]["net"])  # одинаковые суммы
        boss = self.client_for(self.director).get(f"{API}/earnings/schedule/", {"date_from": "2026-11-01"}).json()
        self.assertEqual(boss["dates"], [])
