"""Monthly report and its PDF — the sections agree with each other: the
period the data covers, every group of the month in the tables, one
attendance formula, assignments vs students' works, the group criteria,
one contact list without repeats, the «active» counts explained and
«Нет данных» instead of a made-up 0%.
"""
from __future__ import annotations

import datetime as dt
from unittest import mock

from apps.academy.models import Attendance, Group, Homework, HomeworkResult, Student
from apps.assistant import monthly, monthly_pdf
from apps.assistant.test_retention import P_END, P_START, PP_START, RetentionBase
from apps.assistant.tests import TODAY

A = Attendance.Status
R = HomeworkResult.Status


def pdf_text(report: dict) -> str:
    """Every string the PDF draws, in order — the rendered content, without a PDF parser."""
    drawn, original = [], monthly_pdf._Doc.text

    def spy(self, x, y, text, **kwargs):
        drawn.append(str(text))
        return original(self, x, y, text, **kwargs)

    with mock.patch.object(monthly_pdf._Doc, "text", spy):
        data = monthly_pdf.build_monthly_pdf(report)
    assert data.startswith(b"%PDF")
    return "\n".join(drawn)


class ConsistencyBase(RetentionBase):
    def report(self, start=P_START, **kwargs):
        return monthly.monthly_report(start.year, start.month, **kwargs)

    def marks(self, group, statuses_by_student: dict, *, first_day=1):
        """One held lesson per status position; returns the lessons."""
        count = max(len(v) for v in statuses_by_student.values())
        lessons = [self.lesson(P_START + dt.timedelta(days=first_day + i), group=group, number=i + 1) for i in range(count)]
        for student, statuses in statuses_by_student.items():
            for lesson, status_ in zip(lessons, statuses):
                self.mark(lesson, student, status_)
        return lessons


class PeriodTests(ConsistencyBase):
    def test_running_month_is_preliminary_up_to_today(self):
        report = self.report(TODAY.replace(day=1))
        self.assertFalse(report["is_complete"])
        self.assertEqual(report["until"], TODAY)
        self.assertTrue(report["comparison"]["partial"])
        text = pdf_text(report)
        self.assertIn(f"Период данных: {TODAY.replace(day=1):%d.%m.%Y} — {TODAY:%d.%m.%Y}", text)
        self.assertIn("ПРЕДВАРИТЕЛЬНЫЙ ОТЧЁТ", text)
        self.assertEqual(monthly_pdf._report_title(report), f"{report['title']} · предварительный")  # header, footer

    def test_closed_month_covers_the_whole_month(self):
        report = self.report()
        self.assertTrue(report["is_complete"])
        self.assertFalse(report["comparison"]["partial"])
        text = pdf_text(report)
        self.assertIn(f"Период данных: {P_START:%d.%m.%Y} — {P_END:%d.%m.%Y}", text)
        self.assertNotIn("ПРЕДВАРИТЕЛЬНЫЙ", text)

    def test_group_starting_later_this_month_is_not_counted_yet(self):
        later = Group.objects.create(name="LATER", course=self.course, start_date=TODAY + dt.timedelta(days=1))
        report = self.report(TODAY.replace(day=1))
        names = {g["group"]["name"] for g in report["attendance"]["groups"]}
        self.assertNotIn(later.name, names)
        self.assertEqual(report["overview"]["groups_total"], len(report["attendance"]["groups"]))


class GroupTableTests(ConsistencyBase):
    def test_every_group_of_the_month_is_in_both_tables(self):
        self.marks(self.g1, {self.s1: [A.PRESENT, A.PRESENT]})  # PRO-02 has no lessons at all
        report = self.report()
        att, hw = report["attendance"], report["homework"]
        self.assertEqual(report["overview"]["groups_total"], 2)
        self.assertEqual({g["group"]["name"] for g in att["groups"]}, {"PRO-01", "PRO-02"})
        self.assertEqual({g["group"]["name"] for g in hw["groups"]}, {"PRO-01", "PRO-02"})
        empty = next(g for g in att["groups"] if g["group"]["name"] == "PRO-02")
        self.assertEqual((empty["lessons"], empty["marked"], empty["percent"]), (0, 0, None))
        self.assertEqual(att["groups"][-1]["group"]["name"], "PRO-02")  # no data sorts last, not as 0%
        self.assertEqual(att["groups_with_data"], 1)
        self.assertIn("PRO-02", report["conclusions"]["groups_no_data"])
        self.assertIn("Нет данных", pdf_text(report))


class AttendanceFormulaTests(ConsistencyBase):
    def test_one_formula_for_groups_and_total(self):
        s3 = Student.objects.create(first_name="Third", group=self.g2, enrollment_date=PP_START)
        self.marks(self.g1, {self.s1: [A.PRESENT, A.LATE, A.ABSENT], self.s2: [A.PRESENT, A.EXCUSED, A.PRESENT]})
        self.marks(self.g2, {s3: [A.ABSENT, A.PRESENT]}, first_day=10)
        att = self.report()["attendance"]
        self.assertEqual((att["present"], att["late"], att["attended"], att["absent"], att["excused"], att["marked"]),
                         (4, 1, 5, 2, 1, 8))
        self.assertEqual(att["attended"], att["present"] + att["late"])
        self.assertEqual(att["marked"], att["attended"] + att["absent"] + att["excused"])
        self.assertEqual(att["percent"], round(5 / 8 * 100))
        for key in ("lessons", "marked", "attended", "present", "late", "absent", "excused"):
            self.assertEqual(att[key], sum(g[key] for g in att["groups"]), key)
        g1 = next(g for g in att["groups"] if g["group"]["name"] == "PRO-01")
        self.assertEqual(g1["percent"], round(4 / 6 * 100))


class HomeworkTests(ConsistencyBase):
    def test_assignments_and_works_are_counted_apart(self):
        lesson_a, lesson_b = self.marks(self.g1, {self.s1: [A.PRESENT, A.PRESENT]})
        due = Homework.objects.create(lesson=lesson_a, title="A", deadline=lesson_a.date + dt.timedelta(days=1))
        ahead = Homework.objects.create(lesson=lesson_b, title="B", deadline=TODAY + dt.timedelta(days=30))
        HomeworkResult.objects.create(homework=due, student=self.s1, status=R.CHECKED)
        HomeworkResult.objects.create(homework=due, student=self.s2, status=R.SUBMITTED)
        HomeworkResult.objects.create(homework=ahead, student=self.s1, status=R.SUBMITTED)
        hw = self.report()["homework"]
        self.assertEqual((hw["given"], hw["due"]), (2, 1))  # assignments
        self.assertEqual((hw["expected"], hw["done"], hw["not_done"]), (2, 2, 0))  # works on due assignments
        self.assertEqual(hw["expected"], hw["done"] + hw["not_done"])
        self.assertEqual((hw["pending_due"], hw["pending"]), (1, 2))  # unchecked: part of done / everything handed in
        self.assertEqual(hw["percent"], 100)

    def test_no_due_homework_is_no_data(self):
        self.marks(self.g1, {self.s1: [A.PRESENT]})
        report = self.report()
        self.assertIsNone(report["homework"]["percent"])
        self.assertIsNone(report["overview"]["homework_percent"])


class GroupCriteriaTests(ConsistencyBase):
    def test_attention_watch_and_good(self):
        s3 = Student.objects.create(first_name="Third", group=self.g2, enrollment_date=PP_START)
        s4 = Student.objects.create(first_name="Fourth", group=self.g2, enrollment_date=PP_START)
        # PRO-01: 6 of 8 = 75% — below «хорошо» (85%), not below the attention threshold (70%).
        self.marks(self.g1, {self.s1: [A.PRESENT] * 3 + [A.ABSENT], self.s2: [A.PRESENT] * 3 + [A.ABSENT]})
        # PRO-02: 3 of 6 = 50% — requires attention.
        self.marks(self.g2, {s3: [A.PRESENT, A.ABSENT, A.ABSENT], s4: [A.PRESENT, A.PRESENT, A.ABSENT]}, first_day=10)
        report = self.report()
        cons = report["conclusions"]
        self.assertEqual(cons["groups"], ["PRO-02"])
        self.assertEqual(cons["groups_watch"], ["PRO-01"])
        self.assertEqual(cons["criteria"]["attention_attendance_below"], monthly.LOW_GROUP_ATTENDANCE)
        text = pdf_text(report)
        self.assertIn("Ниже уровня «хорошо»", text)

    def test_empty_attention_list_states_the_rule(self):
        self.marks(self.g1, {self.s1: [A.PRESENT] * 3 + [A.ABSENT]})
        text = pdf_text(self.report())
        self.assertIn(f"Нет групп с посещаемостью ниже {monthly.LOW_GROUP_ATTENDANCE}%", text)


class ContactTests(ConsistencyBase):
    def test_risk_and_inactivity_merge_without_repeats(self):
        lessons = self.marks(self.g1, {self.s1: [A.ABSENT] * 4, self.s2: [A.PRESENT] * 4})
        for lesson in lessons[:2]:
            hw = Homework.objects.create(lesson=lesson, title=f"ДЗ {lesson.pk}", deadline=lesson.date + dt.timedelta(days=1))
            HomeworkResult.objects.create(homework=hw, student=self.s2, status=R.CHECKED)
        report = self.report()
        self.assertEqual([r["student_id"] for r in report["students"]["risk"]], [self.s1.pk])
        self.assertIn(self.s1.pk, [r["student_id"] for r in report["inactive"]["students"]])
        contacts = report["conclusions"]["students"]
        self.assertEqual([c["student_id"] for c in contacts], [self.s1.pk])  # once, though in several lists
        reasons = contacts[0]["reasons"]
        self.assertIn("В зоне риска", reasons)
        self.assertIn("Ни одного посещения за месяц", reasons)
        self.assertNotIn("Низкая посещаемость", reasons)  # implied by «ни одного»
        self.assertEqual(report["summary"]["contacts"], len(contacts))
        self.assertTrue(any(line.startswith("Связаться с семьями: 1 студент") for line in report["recommendations"]))


class ActiveScopeTests(ConsistencyBase):
    def test_active_counts_narrow_step_by_step(self):
        cancelled = Group.objects.create(name="CXL", course=self.course, start_date=PP_START, status=Group.Status.CANCELLED)
        Student.objects.create(first_name="NoGroup", group=None, enrollment_date=PP_START)
        Student.objects.create(first_name="Cancelled", group=cancelled, enrollment_date=PP_START)
        Student.objects.create(first_name="Quiet", group=self.g2, enrollment_date=PP_START)  # PRO-02: no lessons
        self.marks(self.g1, {self.s1: [A.PRESENT, A.PRESENT], self.s2: [A.PRESENT, A.ABSENT]})
        report = self.report()
        sc = report["active_scope"]
        self.assertEqual(sc["status_active"], report["overview"]["students_active"])
        self.assertEqual((sc["without_group"], sc["group_not_running"], sc["no_lessons"]), (1, 1, 1))
        self.assertEqual(sc["in_running_groups"], sc["status_active"] - sc["without_group"] - sc["group_not_running"])
        self.assertEqual(sc["analysed"], sc["in_running_groups"] - sc["no_lessons"])
        self.assertEqual(sc["analysed"], report["students"]["activity"]["analysed"])
        self.assertEqual(sc["analysed"], report["inactive"]["counts"]["total"])
        self.assertEqual(sc["engaged"] + sc["inactive"], sc["analysed"])
        self.assertEqual(sum(g["students"] for g in report["attendance"]["groups"]), sc["in_running_groups"])
        act = report["students"]["activity"]
        self.assertEqual(act["normal"] + act["attention"] + act["low"] + act["no_data"], act["analysed"])
        self.assertIn("Почему число активных студентов в разделах разное", pdf_text(report))


class NoDataTests(ConsistencyBase):
    def test_empty_month_shows_no_data_not_zero_percent(self):
        report = self.report()
        self.assertIsNone(report["attendance"]["percent"])
        self.assertIsNone(report["homework"]["percent"])
        text = pdf_text(report)
        self.assertIn("Нет данных", text)
        self.assertNotIn("0%", text.split("\n"))

    def test_summary_matches_tables(self):
        self.marks(self.g1, {self.s1: [A.PRESENT, A.ABSENT], self.s2: [A.PRESENT, A.PRESENT]})
        report = self.report()
        o = report["overview"]
        self.assertEqual(o["attendance_percent"], report["attendance"]["percent"])
        self.assertEqual(o["students_at_risk"], len(report["students"]["risk"]))
        self.assertEqual(o["students_at_risk"], report["students"]["activity"]["risk"])
        current = {r["key"]: r["current"] for r in report["comparison"]["rows"]}
        self.assertEqual(current["attendance"], report["attendance"]["percent"])
        self.assertEqual(current["active"], o["students_active"])
        self.assertEqual(current["departed"], o["students_deactivated"])
