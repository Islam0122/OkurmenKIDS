"""`seed_scholarships`: mock payment data — every payment state, idempotent,
and --clear/--remove touch only mock rows."""
from __future__ import annotations

import datetime as dt
import io
from decimal import Decimal

from django.core.management import call_command
from django.db.models import Sum

from apps.academy.models import Group, Student
from apps.scholarships.demo import mock_payments as mock
from apps.scholarships.models import PaymentMethod, PaymentStatus, ScholarshipAward, ScholarshipPeriod
from apps.scholarships.services.generation import create_period
from apps.scholarships.services.report import ReportFilters, build_report

from .base import OCT_1, ScholarshipFixture


def run(*args) -> str:
    out = io.StringIO()
    call_command("seed_scholarships", *args, stdout=out)
    return out.getvalue()


class MockSeedTests(ScholarshipFixture):
    def setUp(self):
        super().setUp()
        self.real_student = self.student("Real")
        self.study(self.real_student, self.python, self.t_python, attended=4)
        self.real_period = create_period(
            period_start=dt.date(2026, 8, 31), period_end=dt.date(2026, 9, 30), max_recipients=None, today=OCT_1,
        )

    def periods(self):
        return {p.period_start.strftime("%d.%m") + "-" + p.period_end.strftime("%d.%m"): p
                for p in ScholarshipPeriod.objects.filter(mock.mock_period_q())}

    def test_payment_states(self):
        output = run()
        self.assertIn("SCHOLARSHIP MOCK DATA", output)
        periods = self.periods()
        self.assertEqual(len(periods), 8)
        expected = {
            "01.05-31.05": (20, 20), "01.06-30.06": (20, 20), "01.07-31.07": (20, 0), "01.08-31.08": (20, 7),
            "15.08-15.09": (0, 0), "01.09-30.09": (20, 12), "01.10-31.10": (15, 9), "01.11-30.11": (20, 0),
        }
        for key, (total, paid) in expected.items():
            awards = periods[key].awards
            self.assertEqual((awards.count(), awards.filter(payment_status=PaymentStatus.PAID).count()), (total, paid), key)
        self.assertEqual(periods["15.08-15.09"].max_recipients, 10)
        self.assertTrue(periods["01.11-30.11"].is_draft)

        august = build_report(periods["01.08-31.08"], ReportFilters()).rows_totals
        self.assertEqual((august.amount, august.paid_amount, august.remaining),
                         (Decimal("30000"), Decimal("10500"), Decimal("19500")))

        paid = ScholarshipAward.objects.filter(payment_status=PaymentStatus.PAID)
        self.assertFalse(paid.filter(paid_at__isnull=True).exists())
        self.assertFalse(paid.exclude(status=ScholarshipAward.Status.APPROVED).exists())
        self.assertEqual(paid.filter(paid_by=self.admin).count(), paid.count())
        cash = paid.filter(payment_method=PaymentMethod.CASH).count()
        self.assertTrue(0.6 <= cash / paid.count() <= 0.8)
        self.assertGreater(len({a.paid_at.date() for a in paid}), 4)
        self.assertEqual(
            set(ScholarshipAward.objects.filter(period__in=periods.values()).values_list("amount", flat=True)),
            {Decimal(v) for v in ("1000", "1500", "2000", "2500", "3000")},
        )

    def test_idempotent(self):
        run()
        first = (Student.objects.count(), ScholarshipAward.objects.count(), sorted(p.pk for p in self.periods().values()))
        paid_sum = ScholarshipAward.objects.aggregate(s=Sum("paid_amount"))["s"]
        run()
        self.assertEqual(
            (Student.objects.count(), ScholarshipAward.objects.count(), sorted(p.pk for p in self.periods().values())),
            first,
        )
        self.assertEqual(ScholarshipAward.objects.aggregate(s=Sum("paid_amount"))["s"], paid_sum)

    def test_mock_students_stay_out_of_real_periods(self):
        run()
        self.assertFalse(self.real_period.evaluations.filter(mock.mock_student_q("student__")).exists())
        from apps.scholarships.services.generation import recalculate_period
        recalculate_period(self.real_period, user=self.admin, today=OCT_1)
        self.assertEqual(list(self.real_period.evaluations.values_list("student_id", flat=True)), [self.real_student.pk])

    def test_clear_and_remove_touch_only_mock_rows(self):
        real_awards = self.real_period.awards.count()
        run()
        run("--clear")
        self.assertEqual(len(self.periods()), 8)
        run("--remove")
        self.assertEqual(self.periods(), {})
        self.assertFalse(Student.objects.filter(mock.mock_student_q()).exists())
        self.assertFalse(Group.objects.filter(name__startswith=mock.GROUP_PREFIX).exists())
        self.assertTrue(Student.objects.filter(pk=self.real_student.pk).exists())
        self.assertTrue(Group.objects.filter(pk=self.group.pk).exists())
        self.assertEqual(self.real_period.awards.count(), real_awards)

    def test_real_period_with_same_dates_is_kept(self):
        manual = create_period(period_start=dt.date(2026, 5, 1), period_end=dt.date(2026, 5, 31),
                               max_recipients=5, today=OCT_1)
        output = run()
        self.assertIn("уже есть реальный период", output)
        self.assertEqual(len(self.periods()), 7)
        manual.refresh_from_db()
        self.assertFalse(manual.title.startswith(mock.TITLE_PREFIX))
