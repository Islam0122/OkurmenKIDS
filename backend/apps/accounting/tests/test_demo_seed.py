"""Генератор тестовых данных бухгалтерии (seed_accounting_demo)."""
from __future__ import annotations

import datetime as dt
import io
import os
from unittest import mock

from django.core.management import CommandError, call_command

from apps.academy.models import Course, Group, GroupTeacher, Lesson, Student
from apps.accounting.models import (
    CourseCycle,
    CycleAccrual,
    DemoSeedRecord,
    EmployeeSalaryProfile,
    Payroll,
    PayrollPayment,
    PayrollPeriod,
    SalaryRule,
    SalaryType,
    StudentPayment,
)
from apps.accounting.services import demo_seed as ds
from apps.accounting.services import estimates
from apps.accounting.services.approval_service import approve_payroll
from apps.accounting.services.payment_service import register_payment
from apps.accounting.services.payroll_calculator import calculate_payroll
from apps.accounting.tests.base import MONTH, D, AccountingFixture
from apps.users.models import Subject, Teacher, User

TODAY = dt.date(2026, 10, 10)
ALL = list(ds.MONTHS)


def demo_user(key):
    return ds.lookup(f"user:{key}")


class RealDataFixture(AccountingFixture):
    """Реальные (не тестовые) данные, которые генератор не должен трогать."""

    def setUp(self):
        super().setUp()
        self.rule(self.profile(), SalaryRule.RuleType.FIXED, amount=D("50000"))
        self.real_payroll = approve_payroll(self.calc(MONTH), self.director)
        register_payment(self.real_payroll, amount=D("1000"), payment_date=dt.date(2026, 9, 20), actor=self.accountant)
        self.student(self.group_a)

    def real_snapshot(self):
        return {
            "users": sorted(User.objects.exclude(username__startswith="demo_acc_").values_list("pk", flat=True)),
            "groups": sorted(Group.objects.filter(name__in=["Group A", "Group B"]).values_list("pk", flat=True)),
            "courses": Course.objects.filter(name__in=["Prog SOFT", "Robotics"]).count(),
            "payroll": Payroll.objects.filter(pk=self.real_payroll.pk).values_list("total_accrued", "total_paid",
                                                                                    "status").get(),
            "payments": PayrollPayment.objects.filter(payroll=self.real_payroll).count(),
            "profiles": EmployeeSalaryProfile.objects.filter(employee=self.trainer_user).count(),
            "students": Student.objects.filter(group__in=[self.group_a, self.group_b]).count(),
        }


class GenerateTests(RealDataFixture):
    def test_full_dataset_matches_the_scenarios(self):
        before = self.real_snapshot()
        result = ds.generate(seed=42, months=ALL, today=TODAY)
        s = result["summary"]
        months = {m: (r["accrued"], r["paid"], r["outstanding"], r["awaiting_approval"]) for m, r in s["months"].items()}
        self.assertEqual(months, {
            "2026-08": (D("91000.00"), D("76000.00"), D("15000.00"), D("0")),
            "2026-09": (D("115520.00"), D("54400.00"), D("61120.00"), D("0")),
            "2026-10": (D("0"), D("0"), D("0"), D("77200.00")),
        })
        self.assertEqual((s["employees"], s["salary_rules"], s["review_required"], s["completed_blocks"]), (6, 7, 1, 11))
        self.assertEqual(ds.verify(), [])
        self.assertEqual(self.real_snapshot(), before)

        t1, t2, t4 = demo_user("T1"), demo_user("T2"), demo_user("T4")
        # Плановые даты выплат по дате завершения блока.
        dates = sorted((a.completed_on, a.planned_payment_date) for a in CycleAccrual.objects.filter(employee=t1))
        self.assertIn((dt.date(2026, 8, 10), dt.date(2026, 8, 15)), dates)
        self.assertIn((dt.date(2026, 8, 20), dt.date(2026, 9, 1)), dates)
        self.assertIn((dt.date(2026, 9, 12), dt.date(2026, 9, 15)), dates)
        eng = sorted((a.completed_on, a.planned_payment_date, a.percentage, a.amount)
                     for a in CycleAccrual.objects.filter(employee=t2))
        self.assertIn((dt.date(2026, 9, 20), dt.date(2026, 10, 1), D("8"), D("8000.00")), eng)
        self.assertIn((dt.date(2026, 10, 10), dt.date(2026, 10, 15), D("9"), D("7200.00")), eng)  # история ставки
        # Блок двух тренеров — доли по урокам, каждому по его ставке.
        split = CycleAccrual.objects.filter(cycle__group__name="DEMO Prog B", cycle__number=2, cycle__subject__name="IT")
        self.assertEqual(sorted((a.employee_id, a.lessons_taught, a.amount) for a in split),
                         sorted([(t1.pk, 9, D("6000.00")), (t4.pk, 3, D("2800.00"))]))
        # Второй блок предмета за месяц — на проверке, расчёт с ошибкой, не утверждён.
        review = CycleAccrual.objects.get(status=CycleAccrual.Status.REVIEW_REQUIRED)
        self.assertEqual((review.cycle.group.name, review.completed_on), ("DEMO Prog B", dt.date(2026, 9, 29)))
        sep2 = Payroll.objects.get(employee=t1, period__year=2026, period__month=9, period__period_type="SECOND_HALF")
        self.assertEqual(sep2.status, Payroll.Status.CALCULATED)
        self.assertTrue(any("требует проверки" in e for e in sep2.errors))
        # Нет ставки у Soft Skills-тренера — ошибка расчёта, начислений нет.
        t3 = demo_user("T3")
        self.assertFalse(CycleAccrual.objects.filter(employee=t3).exists())
        self.assertTrue(all(any("Не настроена ставка" in e for e in p.errors) for p in Payroll.objects.filter(employee=t3)))
        # Частичные и множественные выплаты; переплат нет.
        fix2_aug = Payroll.objects.get(employee=demo_user("FIX2"), period__month=8)
        self.assertEqual((fix2_aug.total_accrued, fix2_aug.total_paid, fix2_aug.amount_due, fix2_aug.status),
                         (D("35000.00"), D("20000.00"), D("15000.00"), Payroll.Status.PARTIALLY_PAID))
        t2_aug = Payroll.objects.get(employee=t2, period__month=8)
        self.assertEqual((t2_aug.payments.count(), t2_aug.status), (2, Payroll.Status.PAID))
        self.assertEqual(Payroll.objects.get(employee=demo_user("FIX2"), period__month=9).total_accrued, D("40000.00"))
        # Предварительный расчёт 8/12: 10 × 10 000 × 10 % = 10 000, без начисления.
        open_it = CourseCycle.objects.get(group__name="DEMO Prog A", subject__name="IT", status="IN_PROGRESS")
        [row] = [r for r in estimates.all_open(today=TODAY) if r["cycle_id"] == open_it.pk]
        self.assertEqual((row["lessons_done"], row["lessons_remaining"], row["expected_amount"],
                          row["projected_completion_date"], row["expected_payment_date"]),
                         (8, 4, D("10000.00"), dt.date(2026, 10, 20), dt.date(2026, 11, 1)))
        self.assertFalse(CycleAccrual.objects.filter(cycle=open_it).exists())
        progress = sorted(c.lessons_done for c in CourseCycle.objects.filter(group__name__startswith="DEMO",
                                                                              status="IN_PROGRESS", lessons_done__gt=0))
        self.assertEqual(progress, [8, 10, 10, 11, 19])
        # Прогресс — из реальных уроков своего предмета.
        self.assertEqual(Lesson.objects.filter(group=open_it.group, subject=open_it.subject,
                                               status=Lesson.Status.COMPLETED).count(), 12 + 12 + 8)

    def test_rerun_is_idempotent_and_seed_is_locked(self):
        first = ds.generate(seed=42, months=ALL, today=TODAY)
        again = ds.generate(seed=42, months=ALL, today=TODAY)
        self.assertEqual((again["created"], again["fingerprint"]), ({}, first["fingerprint"]))
        self.assertEqual(PayrollPayment.objects.filter(reference__startswith="DEMO-").count(), 10)
        with self.assertRaises(ds.SeedError):
            ds.generate(seed=7, months=ALL, today=TODAY)

    def test_recalculating_an_accrued_block_creates_nothing_new(self):
        ds.generate(seed=42, months=ALL, today=TODAY)
        accruals = CycleAccrual.objects.count()
        payroll = Payroll.objects.get(employee=demo_user("T1"), period__month=8, period__period_type="FIRST_HALF")
        with self.assertRaises(ds.AccountingError):
            calculate_payroll(payroll.period, payroll.employee, demo_user("ACCOUNTANT"))
        ds.sync_demo_cycles(ds.Context(seed=42, today=TODAY, cutoff=TODAY, months=ALL, demo_password=None,
                                       groups={k: ds.lookup(f"group:{k}") for k in ds.GROUPS},
                                       users={"ACCOUNTANT": demo_user("ACCOUNTANT")}))
        self.assertEqual(CycleAccrual.objects.count(), accruals)

    def test_dry_run_writes_nothing(self):
        result = ds.generate(seed=42, months=ALL, today=TODAY, dry_run=True)
        self.assertGreater(sum(result["created"].values()), 500)
        self.assertFalse(DemoSeedRecord.objects.exists())
        self.assertFalse(User.objects.filter(username__startswith="demo_acc_").exists())

    def test_single_month_then_all(self):
        ds.generate(seed=42, months=["2026-08"], today=TODAY)
        aug = ds.summary()["months"]
        self.assertEqual((aug["2026-08"]["accrued"], aug["2026-08"]["paid"]), (D("91000.00"), D("40000.00")))
        self.assertFalse(Lesson.objects.filter(group__name__startswith="DEMO", date__gt=dt.date(2026, 8, 31)).exists())
        ds.generate(seed=42, months=ALL, today=TODAY)
        full = ds.summary()["months"]
        self.assertEqual((full["2026-08"]["paid"], full["2026-09"]["accrued"], full["2026-10"]["awaiting_approval"]),
                         (D("76000.00"), D("115520.00"), D("77200.00")))
        self.assertEqual(ds.verify(), [])


class ClearTests(RealDataFixture):
    def test_clear_removes_only_generated_records(self):
        before = self.real_snapshot()
        ds.generate(seed=42, months=ALL, today=TODAY)
        deleted = ds.clear()
        self.assertGreater(sum(deleted.values()), 800)
        self.assertFalse(DemoSeedRecord.objects.exists())
        self.assertFalse(User.objects.filter(username__startswith="demo_acc_").exists())
        self.assertFalse(Group.objects.filter(name__startswith="DEMO").exists())
        self.assertFalse(StudentPayment.objects.filter(student__group__name__startswith="DEMO").exists())
        self.assertEqual(self.real_snapshot(), before)
        self.assertTrue(Subject.objects.filter(pk=self.python.pk).exists())

    def test_clear_dry_run_keeps_everything(self):
        ds.generate(seed=42, months=ALL, today=TODAY)
        count = DemoSeedRecord.objects.count()
        ds.clear(dry_run=True)
        self.assertEqual(DemoSeedRecord.objects.count(), count)

    def test_clear_stops_if_real_data_depends_on_demo_records(self):
        ds.generate(seed=42, months=ALL, today=TODAY)
        demo_group = ds.lookup("group:G1")
        program = GroupTeacher.objects.filter(group=demo_group).first()
        Lesson.objects.create(group=demo_group, group_teacher=program, lesson_number=999, date=dt.date(2026, 10, 30),
                              start_time=dt.time(18), end_time=dt.time(19))  # реальный урок в DEMO-группе
        count = DemoSeedRecord.objects.count()
        with self.assertRaises(ds.SeedError) as ctx:
            ds.clear()
        self.assertIn("academy.Lesson", ctx.exception.message)
        self.assertEqual(DemoSeedRecord.objects.count(), count)
        self.assertTrue(Group.objects.filter(pk=demo_group.pk).exists())

    def test_clear_stops_on_real_m2m_link_to_demo_subject(self):
        ds.generate(seed=42, months=ALL, today=TODAY)
        demo_subjects = Subject.objects.filter(pk__in=ds.registered(Subject).values("pk"))
        if not demo_subjects.exists():
            self.skipTest("все предметы уже существовали — генератор их не создавал")
        self.trainer.subjects.add(demo_subjects.first())  # реальный тренер ссылается на DEMO-предмет
        with self.assertRaises(ds.SeedError):
            ds.clear()

    def test_period_shared_with_real_payroll_is_kept(self):
        ds.generate(seed=42, months=ALL, today=TODAY)
        period = ds.lookup("period:2026-10:FIRST_HALF")
        self.assertIsNotNone(period)
        other = User.objects.create_user(username="real_t", email="r@x.kg", password="x", role=User.Role.TEACHER)
        Teacher.objects.create(user=other)
        EmployeeSalaryProfile.objects.create(employee=other, salary_type=SalaryType.PERCENT,
                                             effective_from=dt.date(2026, 1, 1))
        calculate_payroll(period, other, self.accountant)
        ds.clear()
        period.refresh_from_db()
        self.assertIsNone(period.created_by)
        self.assertTrue(Payroll.objects.filter(employee=other, period=period).exists())
        self.assertFalse(DemoSeedRecord.objects.exists())


class CommandTests(RealDataFixture):
    def test_command_output_and_guards(self):
        out = io.StringIO()
        call_command("seed_accounting_demo", "--today", "2026-10-10", "--seed", "42", stdout=out)
        text = out.getvalue()
        for snippet in ("Тестовые данные готовы", "2026-08", "91000.00", "Проверки целостности: пройдены",
                        "начислений на проверке: 1"):
            self.assertIn(snippet, text)
        out = io.StringIO()
        call_command("seed_accounting_demo", "--today", "2026-10-10", stdout=out)
        self.assertIn("повторный запуск — без изменений", out.getvalue())
        with self.assertRaises(CommandError):
            call_command("seed_accounting_demo", "--month", "2026-12", stdout=io.StringIO())
        with mock.patch.dict(os.environ, {"DJANGO_ENV": "production"}), self.assertRaises(CommandError):
            call_command("seed_accounting_demo", stdout=io.StringIO())
        out = io.StringIO()
        call_command("seed_accounting_demo", "--clear", stdout=out)
        self.assertIn("Удалено записей набора", out.getvalue())
        self.assertFalse(PayrollPeriod.objects.filter(pk__in=ds.registered(PayrollPeriod).values("pk")).exists())
