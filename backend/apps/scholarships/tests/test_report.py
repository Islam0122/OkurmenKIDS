"""«Отчёты по стипендиям»: period → participating groups → group stats →
students, and the PDF built from the same report."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.http import QueryDict
from django.urls import reverse

from apps.scholarships.services.generation import approve_period, create_period
from apps.scholarships.services.report import (
    PaymentStatus,
    ReportFilters,
    build_report,
    default_option,
    parse_filters,
    period_options,
    pick_period,
)
from apps.scholarships.services.report_pdf import render_report_pdf

from .base import OCT_1, SEP_1, ScholarshipFixture

SEP_30 = dt.date(2026, 9, 30)


class ReportFixture(ScholarshipFixture):
    def setUp(self):
        super().setUp()
        self.configure(require_complete_feedback=False, award_amount=Decimal("2000"))
        self.students = []
        for index, name in enumerate(["Aibek", "Nurai", "Azamat"]):
            group = self.group if index < 2 else self.other_group
            student = self.student(name, group=group)
            self.study(student, self.python, self.t_python, attended=8 - index, missed=index, group=group)
            self.students.append(student)
        # Aibek + Nurai (Prog SOFT 1) get a scholarship, Azamat (Prog SOFT 2) is outside the limit.
        self.period = create_period(period_start=SEP_1, period_end=SEP_30, max_recipients=2, today=OCT_1)


class ReportTests(ReportFixture):
    def test_groups_and_totals_of_the_period(self):
        report = build_report(self.period, ReportFilters())
        self.assertEqual(report.range_label, "01.09.2026 — 30.09.2026")
        self.assertEqual(report.group_names, ["Prog SOFT 1", "Prog SOFT 2"])
        self.assertEqual(report.programs, ["Prog SOFT"])

        soft1, soft2 = report.groups
        self.assertEqual((soft1.totals.students, soft1.totals.pending, soft1.totals.not_received), (2, 2, 0))
        self.assertEqual(soft1.totals.amount, Decimal("4000"))
        self.assertEqual((soft2.totals.students, soft2.totals.awarded, soft2.totals.not_received), (1, 0, 1))
        self.assertEqual(soft2.totals.amount, Decimal("0"))

        totals = report.totals
        self.assertEqual((totals.students, totals.received, totals.pending, totals.not_received), (3, 0, 2, 1))
        self.assertEqual(totals.average, Decimal("2000"))
        self.assertEqual(
            {row.student_name: row.status for row in report.rows},
            {"Aibek Test": PaymentStatus.PENDING, "Nurai Test": PaymentStatus.PENDING,
             "Azamat Test": PaymentStatus.NOT_RECEIVED},
        )

        approve_period(self.period, user=self.admin)
        totals = build_report(self.period, ReportFilters()).totals
        self.assertEqual((totals.received, totals.pending), (2, 0))

    def test_groups_come_from_the_period_snapshot(self):
        """A student moved to another group later stays in the group he was
        evaluated in — the report follows the stored calculation."""
        self.students[0].group = self.other_group
        self.students[0].save()
        report = build_report(self.period, ReportFilters())
        self.assertEqual(report.groups[0].name, "Prog SOFT 1")
        self.assertEqual(report.groups[0].totals.students, 2)

    def test_periods_are_not_mixed(self):
        october = create_period(
            period_start=OCT_1, period_end=dt.date(2026, 10, 31), max_recipients=1, today=dt.date(2026, 11, 1),
        )
        # Simulate a period whose evaluations were taken in another group.
        october.evaluations.update(group_name="PY-03", course_name="Python")
        options = period_options()
        self.assertEqual([o.pk for o in options], [october.pk, self.period.pk])
        self.assertEqual(options[0].groups, ["PY-03"])
        self.assertEqual(options[1].groups, ["Prog SOFT 1", "Prog SOFT 2"])
        self.assertEqual(build_report(october, ReportFilters()).group_names, ["PY-03"])
        self.assertEqual(build_report(self.period, ReportFilters()).group_names, ["Prog SOFT 1", "Prog SOFT 2"])
        self.assertEqual(pick_period(options, str(self.period.pk)).pk, self.period.pk)
        self.assertEqual(pick_period(options, "999999").pk, default_option(options).pk)

    def test_student_filters_do_not_change_period_blocks(self):
        report = build_report(self.period, parse_filters(QueryDict("group=Prog+SOFT+2")))
        self.assertEqual([r.student_name for r in report.rows], ["Azamat Test"])
        self.assertEqual(report.rows_totals.students, 1)
        self.assertEqual(report.totals.students, 3)
        self.assertEqual(len(report.groups), 2)
        report = build_report(self.period, parse_filters(QueryDict("student=nur&status=bogus")))
        self.assertEqual([r.student_name for r in report.rows], ["Nurai Test"])
        self.assertEqual(report.filters.status, "")


class ReportAdminTests(ReportFixture):
    def setUp(self):
        super().setUp()
        self.web = self.client_class()
        self.web.force_login(self.admin)

    def test_page(self):
        response = self.web.get(reverse("admin:scholarships_report"), {"period": self.period.pk})
        self.assertContains(response, "Стипендиальные периоды")
        self.assertContains(response, "Стипендиальный период")
        self.assertContains(response, "Участвующие группы")
        self.assertContains(response, "Группы в этом стипендиальном периоде")
        self.assertContains(response, "01.09.2026 — 30.09.2026")
        self.assertContains(response, "Prog SOFT 2")
        self.assertContains(response, "Aibek Test")
        self.assertContains(response, "Не получил")
        self.assertContains(response, "4 000 сом")

    def test_group_link_shows_its_students(self):
        response = self.web.get(reverse("admin:scholarships_report"), {"period": self.period.pk, "group": "Prog SOFT 2"})
        self.assertContains(response, "Azamat Test")
        self.assertNotContains(response, "Aibek Test")

    def test_empty(self):
        self.period.delete()
        response = self.web.get(reverse("admin:scholarships_report"))
        self.assertContains(response, "Отчётов пока нет")
        pdf = self.web.get(reverse("admin:scholarships_report_pdf"))
        self.assertEqual(pdf.status_code, 302)

    def test_pdf(self):
        response = self.web.get(
            reverse("admin:scholarships_report_pdf"), {"period": self.period.pk, "group": "Prog SOFT 1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("scholarship-report-2026-09-01-2026-09-30.pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_pdf_paginates_long_tables(self):
        report = build_report(self.period, ReportFilters())
        report.rows = report.rows * 60  # 180 rows → several pages
        pdf = render_report_pdf(report)
        self.assertGreaterEqual(pdf.count(b"/Type /Page\n"), 3)
