"""«Отчёты по стипендиям»: period → participating groups → group stats →
students, and the PDF built from the same report."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.http import QueryDict
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academy.models import Group
from apps.scholarships.models import ScholarshipPeriod

from apps.scholarships.services.generation import approve_period, create_period, update_period
from apps.scholarships.services.report import (
    PaymentStatus,
    ReportFilters,
    build_report,
    parse_filters,
    period_options,
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


class PeriodGroupsTests(ScholarshipFixture):
    """Each period has its own groups → its own students, awards, totals."""

    def setUp(self):
        super().setUp()
        self.configure(require_complete_feedback=False, award_amount=Decimal("1500"))
        self.py = [self.student(name) for name in ("Aibek", "Nurai")]  # Prog SOFT 1
        self.cs = [self.student(name, group=self.other_group) for name in ("Azamat", "Aidana", "Bakyt")]  # Prog SOFT 2
        for index, student in enumerate(self.py):
            self.study(student, self.python, self.t_python, attended=6 - index, missed=index)
        for index, student in enumerate(self.cs):
            self.study(student, self.python, self.t_python, attended=6 - index, missed=index, group=self.other_group)
        # Overlapping dates on purpose: groups, not dates, decide who is in.
        self.first = create_period(
            period_start=SEP_1, period_end=SEP_30, max_recipients=1, groups=[self.group], today=OCT_1,
        )
        self.second = create_period(
            period_start=dt.date(2026, 8, 31), period_end=SEP_30, max_recipients=2,
            groups=[self.other_group], today=OCT_1,
        )

    def test_calculation_takes_only_the_period_groups(self):
        self.assertEqual(
            sorted(self.first.evaluations.values_list("student_name", flat=True)), ["Aibek Test", "Nurai Test"],
        )
        self.assertEqual(self.second.evaluations.count(), 3)
        self.assertEqual(set(self.second.evaluations.values_list("group_name", flat=True)), {"Prog SOFT 2"})

    def test_each_card_gets_its_own_numbers(self):
        options = {o.pk: o for o in period_options()}
        first, second = options[self.first.pk], options[self.second.pk]
        self.assertEqual((first.groups, first.students, first.recipients, first.scope_all), (["Prog SOFT 1"], 2, 1, False))
        self.assertEqual((second.groups, second.students, second.recipients), (["Prog SOFT 2"], 3, 2))

    def test_switching_period_changes_everything(self):
        first = build_report(self.first, ReportFilters())
        second = build_report(self.second, ReportFilters())
        self.assertEqual(first.group_names, ["Prog SOFT 1"])
        self.assertEqual((first.totals.students, first.totals.awarded, first.totals.amount), (2, 1, Decimal("1500")))
        self.assertEqual(second.group_names, ["Prog SOFT 2"])
        self.assertEqual((second.totals.students, second.totals.awarded, second.totals.amount), (3, 2, Decimal("3000")))
        self.assertFalse({r.student_id for r in first.rows} & {r.student_id for r in second.rows})

    def test_empty_selection_is_the_whole_academy(self):
        whole = create_period(
            period_start=dt.date(2026, 8, 1), period_end=dt.date(2026, 8, 31), max_recipients=1, today=OCT_1,
        )
        report = build_report(whole, ReportFilters())
        self.assertTrue(report.scope_all)
        self.assertEqual(report.totals.students, 5)

    def test_selected_group_without_students_is_listed(self):
        empty = Group.objects.create(name="PY-09", course=self.course, start_date=dt.date(2026, 1, 10))
        self.first.groups.add(empty)
        report = build_report(self.first, ReportFilters())
        self.assertEqual(report.group_names, ["PY-09", "Prog SOFT 1"])
        self.assertEqual(report.groups[0].totals.students, 0)
        self.assertEqual(report.groups[0].programs, ["Prog SOFT"])

    def test_changing_groups_recalculates_a_draft(self):
        period = update_period(self.first, groups=[self.other_group], user=self.admin)
        self.assertEqual(set(period.evaluations.values_list("group_name", flat=True)), {"Prog SOFT 2"})
        approve_period(period, user=self.admin)
        with self.assertRaisesMessage(ValidationError, "Группы утверждённого периода изменить нельзя."):
            update_period(period, groups=[self.group], user=self.admin)

    def test_admin_form_and_report_page(self):
        web = self.client_class()
        web.force_login(self.admin)
        response = web.post(reverse("admin:scholarships_create"), {
            "title": "PY", "period_start": "2026-08-01", "period_end": "2026-08-31",
            "limit_enabled": "on", "max_recipients": "5", "groups": [self.group.pk],
        })
        self.assertEqual(response.status_code, 302)
        created = ScholarshipPeriod.objects.get(title="PY")
        self.assertEqual(created.group_ids, [self.group.pk])
        self.assertEqual(created.evaluations.count(), 2)
        self.assertContains(web.get(reverse("admin:scholarships_edit", args=[created.pk])), "Участвующие группы")

        page = web.get(reverse("admin:scholarships_report"), {"period": self.second.pk})
        self.assertContains(page, "Azamat Test")
        self.assertNotContains(page, "Aibek Test")
        page = web.get(reverse("admin:scholarships_report"), {"period": self.first.pk})
        self.assertContains(page, "Aibek Test")
        self.assertNotContains(page, "Azamat Test")

    def test_api_reads_and_writes_groups(self):
        api = APIClient()
        api.force_authenticate(self.admin)
        response = api.post(reverse("scholarship-period-list"), {
            "title": "API", "period_start": "2026-08-01", "period_end": "2026-08-31",
            "max_recipients": 3, "groups": [self.other_group.pk],
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["groups"], [{"id": self.other_group.pk, "name": "Prog SOFT 2"}])
