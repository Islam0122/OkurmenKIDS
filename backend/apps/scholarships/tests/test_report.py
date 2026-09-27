"""«Отчёты по стипендиям»: filters, payment statuses, totals and the PDF."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.http import QueryDict
from django.urls import reverse

from apps.scholarships.services.generation import approve_period, create_period
from apps.scholarships.services.report import (
    PRESET_CUSTOM,
    PRESET_LAST_MONTH,
    PRESET_THIS_MONTH,
    PaymentStatus,
    build_report,
    parse_filters,
)
from apps.scholarships.services.report_pdf import render_report_pdf

from .base import OCT_1, SEP_1, ScholarshipFixture

SEP_30 = dt.date(2026, 9, 30)
TODAY = dt.date(2026, 10, 20)


def q(**params) -> QueryDict:
    query = QueryDict(mutable=True)
    query.update(params)
    return query


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
        # Aibek + Nurai get a scholarship, Azamat is outside the limit.
        self.period = create_period(period_start=SEP_1, period_end=SEP_30, max_recipients=2, today=OCT_1)

    def september(self, **params):
        return parse_filters(q(preset=PRESET_CUSTOM, date_from="2026-09-01", date_to="2026-09-30", **params), TODAY)


class FilterParsingTests(ReportFixture):
    def test_presets(self):
        last = parse_filters(q(), TODAY)
        self.assertEqual((last.preset, last.date_from, last.date_to), (PRESET_LAST_MONTH, SEP_1, SEP_30))
        this = parse_filters(q(preset=PRESET_THIS_MONTH), TODAY)
        self.assertEqual((this.date_from, this.date_to), (OCT_1, dt.date(2026, 10, 31)))
        self.assertEqual(this.range_label, "01.10.2026 — 31.10.2026")

    def test_custom_range_is_normalised(self):
        swapped = parse_filters(q(preset=PRESET_CUSTOM, date_from="2026-09-30", date_to="2026-09-01"), TODAY)
        self.assertEqual((swapped.date_from, swapped.date_to), (SEP_1, SEP_30))
        broken = parse_filters(q(preset=PRESET_CUSTOM, date_from="nope", status="bogus"), TODAY)
        self.assertEqual(broken.preset, PRESET_LAST_MONTH)
        self.assertEqual(broken.status, "")

    def test_period_link_opens_its_dates(self):
        filters = parse_filters(q(period=str(self.period.pk)), TODAY)
        self.assertEqual((filters.date_from, filters.date_to), (SEP_1, SEP_30))


class ReportTests(ReportFixture):
    def test_statuses_and_totals(self):
        report = build_report(self.september())
        statuses = {row.student_name: row.status for row in report.rows}
        self.assertEqual(statuses, {
            "Aibek Test": PaymentStatus.PENDING,
            "Nurai Test": PaymentStatus.PENDING,
            "Azamat Test": PaymentStatus.NOT_RECEIVED,
        })
        self.assertEqual([row.number for row in report.rows], [1, 2, 3])
        self.assertEqual(report.rows[0].period_label, "01.09.2026 — 30.09.2026")
        stats = report.stats
        self.assertEqual((stats.total_students, stats.received_students, stats.pending_students), (3, 0, 2))
        self.assertEqual(stats.total_amount, Decimal("4000"))
        self.assertEqual(stats.average_amount, Decimal("2000"))

        approve_period(self.period, user=self.admin)
        stats = build_report(self.september()).stats
        self.assertEqual((stats.received_students, stats.pending_students), (2, 0))
        self.assertEqual(stats.received_amount, Decimal("4000"))

    def test_filters(self):
        self.assertEqual(
            [r.student_name for r in build_report(self.september(group="Prog SOFT 2")).rows], ["Azamat Test"],
        )
        self.assertEqual(
            [r.student_name for r in build_report(self.september(student="nur")).rows], ["Nurai Test"],
        )
        received = build_report(self.september(status=PaymentStatus.NOT_RECEIVED))
        self.assertEqual([r.student_name for r in received.rows], ["Azamat Test"])
        self.assertEqual(received.group_options, ["Prog SOFT 1", "Prog SOFT 2"])
        self.assertEqual(received.program_options, ["Prog SOFT"])

    def test_period_must_end_in_range(self):
        august = parse_filters(q(preset=PRESET_CUSTOM, date_from="2026-08-01", date_to="2026-09-29"), TODAY)
        self.assertEqual(build_report(august).rows, [])


class ReportAdminTests(ReportFixture):
    def setUp(self):
        super().setUp()
        self.web = self.client_class()
        self.web.force_login(self.admin)

    def test_page(self):
        response = self.web.get(
            reverse("admin:scholarships_report"),
            {"preset": "custom", "date_from": "2026-09-01", "date_to": "2026-09-30"},
        )
        self.assertContains(response, "Отчёты по стипендиям")
        self.assertContains(response, "Просмотр, анализ и экспорт информации по выплатам стипендий.")
        self.assertContains(response, "01.09.2026 — 30.09.2026")
        self.assertContains(response, "Aibek Test")
        self.assertContains(response, "Ожидает")
        self.assertContains(response, "Не получил")
        self.assertContains(response, "4 000 сом")

    def test_pdf(self):
        response = self.web.get(
            reverse("admin:scholarships_report_pdf"),
            {"preset": "custom", "date_from": "2026-09-01", "date_to": "2026-09-30", "group": "Prog SOFT 1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("scholarship-report-2026-09-01-2026-09-30.pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_pdf_paginates_long_tables(self):
        report = build_report(self.september())
        report.rows = report.rows * 60  # 180 rows → several pages
        pdf = render_report_pdf(report)
        self.assertGreaterEqual(pdf.count(b"/Type /Page\n"), 3)
