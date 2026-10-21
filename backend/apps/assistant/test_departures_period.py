"""«Деактивированы за месяц» — only the students whose deactivation event is
dated within the period, both ends included; never today's status. The
overview, the departure table, the reasons, month over month, the summary
and the advice all read the same set.
"""
from __future__ import annotations

import datetime as dt

from apps.academy.models import Student
from apps.academy.services import student_status
from apps.assistant import monthly
from apps.assistant.test_monthly_consistency import pdf_text
from apps.assistant.test_retention import P_END, P_START, PP_START, RetentionBase
from apps.assistant.tests import TODAY


class DeparturePeriodTests(RetentionBase):
    def setUp(self):
        super().setUp()
        early = PP_START - dt.timedelta(days=60)
        self.before, self.first_day, self.last_day, self.after = (
            Student.objects.create(first_name=name, last_name="L", group=self.g1, enrollment_date=early)
            for name in ("Before", "FirstDay", "LastDay", "After")
        )
        leave = student_status.deactivate_student
        leave(self.before, reason="financial_issues", event_date=P_START - dt.timedelta(days=1))  # previous month
        leave(self.first_day, reason="schedule", event_date=P_START)
        leave(self.last_day, reason="transport", event_date=P_END)
        leave(self.after, reason="relocation", event_date=TODAY)  # after the month

    def report(self, start=P_START, **kwargs):
        return monthly.monthly_report(start.year, start.month, **kwargs)

    def test_only_deactivations_dated_in_the_month(self):
        report = self.report()
        d = report["departures"]
        self.assertEqual(report["overview"]["students_deactivated"], 2)
        self.assertEqual((d["total"], d["month_total"]), (2, 2))
        self.assertEqual({r["student_id"] for r in d["rows"]}, {self.first_day.pk, self.last_day.pk})
        self.assertEqual({r["key"] for r in d["by_reason"]}, {"schedule", "transport"})
        self.assertEqual({r["key"] for r in d["month_by_reason"]}, {"schedule", "transport"})

    def test_status_on_the_month_end_is_not_the_month_count(self):
        o = self.report()["overview"]
        # Withdrawn on the last day: the one who left before the month and the two who left in it.
        self.assertEqual(o["students_withdrawn"], 3)
        self.assertEqual(o["students_deactivated"], 2)
        # Today all four are withdrawn — today's status decides nothing about the month.
        self.assertEqual(Student.objects.filter(status=Student.Status.WITHDRAWN).count(), 4)

    def test_previous_month_and_comparison(self):
        previous = self.report(PP_START)
        self.assertEqual(previous["overview"]["students_deactivated"], 1)
        self.assertEqual([r["student_id"] for r in previous["departures"]["rows"]], [self.before.pk])
        d = self.report()["departures"]
        self.assertEqual((d["previous_total"], d["change"]), (1, 1))
        row = next(r for r in self.report()["comparison"]["rows"] if r["key"] == "departed")
        self.assertEqual((row["previous"], row["current"], row["label"]), (1, 2, "Деактивированы за месяц"))

    def test_running_month_counts_up_to_today(self):
        current = self.report(TODAY.replace(day=1))
        self.assertEqual(current["overview"]["students_deactivated"], 1)
        self.assertEqual([r["student_id"] for r in current["departures"]["rows"]], [self.after.pk])

    def test_returned_share_is_among_the_months_departures(self):
        # A return after the month still counts as that departure's return; a return
        # of the student who left before the month is not this month's.
        student_status.reactivate_student(self.first_day, group=self.g1, event_date=TODAY)
        student_status.reactivate_student(self.before, group=self.g1, event_date=P_START + dt.timedelta(days=3))
        d = self.report()["departures"]
        self.assertEqual((d["returned"], d["returned_percent"]), (1, 50))
        self.assertEqual((d["month_returned"], d["month_returned_percent"]), (1, 50))
        self.assertEqual(self.report()["overview"]["students_deactivated"], 2)  # returning does not undo the departure

    def test_left_twice_in_the_month_counts_once(self):
        student_status.reactivate_student(self.first_day, group=self.g1, event_date=P_START + dt.timedelta(days=2))
        student_status.deactivate_student(self.first_day, reason="no_interest", event_date=P_START + dt.timedelta(days=5))
        d = self.report()["departures"]
        self.assertEqual(self.report()["overview"]["students_deactivated"], 2)
        row = next(r for r in d["rows"] if r["student_id"] == self.first_day.pk)
        self.assertEqual((row["reason"], row["returned_on"]), ("no_interest", None))  # the later departure

    def test_filters_narrow_the_tables_not_the_summary(self):
        report = self.report(filters={"reason": "schedule"})
        d = report["departures"]
        self.assertEqual((d["total"], d["month_total"]), (1, 2))
        self.assertEqual(len(report["summary"]["top_reasons"]), 2)
        self.assertTrue(any("Неудобный адрес" in line for line in report["recommendations"]))

    def test_summary_and_advice_ignore_other_months(self):
        report = self.report()
        reasons = " ".join(report["summary"]["top_reasons"] + report["recommendations"])
        self.assertNotIn("Финансовые", reasons)  # left before the month
        self.assertNotIn("Переезд", reasons)  # left after it

    def test_withdrawn_without_a_date_belongs_to_no_month(self):
        Student.objects.create(first_name="Undated", group=None, status=Student.Status.WITHDRAWN, is_active=False,
                               enrollment_date=PP_START)
        report = self.report()
        self.assertEqual(report["overview"]["students_deactivated"], 2)
        self.assertEqual(report["departures"]["undated_withdrawn"], 1)
        self.assertIn("без сохранённой даты деактивации: 1", pdf_text(report))

    def test_pdf_shows_the_months_count_and_period(self):
        text = pdf_text(self.report())
        self.assertIn("Деактивированы за месяц", text)
        self.assertNotIn("Before L", text)  # left before the month: not in the departure table
        self.assertIn("FirstDay L", text)

