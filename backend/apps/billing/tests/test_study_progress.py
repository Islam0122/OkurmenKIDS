"""Три независимых показателя (`services.progress`):

* учебный месяц ГРУППЫ — проведённые IT-занятия текущей группы, тариф
  программы курса: 1–12 → месяц 1, 13–24 → месяц 2…; одинаков у всех
  учеников группы, не зависит от даты прихода и посещаемости;
* посещаемость ученика;
* финансовый пакет договора (начисления и сроки — по нему).

Смена преподавателя не сбрасывает прогресс; параллельные IT-программы и
неоднозначный тариф — предупреждение без цифр; после перевода — прогресс
новой группы; отображение не меняет финансовые записи."""
from __future__ import annotations

import datetime as dt

from django.test import SimpleTestCase

from apps.academy.models import Attendance, GroupTeacher, Lesson
from apps.academy.services.trainer_assignment import assign_trainer
from apps.accounting.models import StudentPayment
from apps.billing.models import (
    CreditLedgerEntry,
    Invoice,
    LessonPackage,
    PaymentAllocation,
)
from apps.billing.services import lessons, pricing, profiles, queues
from apps.billing.services.progress import WARNINGS, group_progress, study_progress
from apps.billing.tests.base import D, make_user
from apps.billing.tests.test_contracts import BASE
from apps.billing.tests.test_periods import PeriodFixture
from apps.users.models import Teacher

SEP1 = dt.date(2026, 9, 1)


class RuleTests(SimpleTestCase):
    def test_boundaries(self):
        cases = {0: (1, 0), 1: (1, 1), 11: (1, 11), 12: (1, 12), 13: (2, 1), 14: (2, 2), 24: (2, 12), 25: (3, 1),
                 36: (3, 12), 48: (4, 12)}
        for held, expected in cases.items():
            p = study_progress(held, 12, 4)
            self.assertEqual((p["month"], p["in_month"]), expected, held)
        self.assertEqual(study_progress(5, None, None)["month"], None)  # тариф не подтверждён — месяца нет


class GroupFixture(PeriodFixture):
    def setUp(self):
        super().setUp()
        self.at(SEP1)
        self.day = dt.date(2026, 9, 2)

    def contract(self, student=None, start=SEP1):
        return profiles.create_student_billing_profile(
            student=student or self.student(self.group_b), plan=self.kc, actor=self.accountant, start_date=start,
            responsible_accountant=self.accountant)

    def held(self, n, *, subject=None, group=None, status=Lesson.Status.COMPLETED, marks=None):
        out = []
        for _ in range(n):
            lesson = self.lesson(group=group or self.group_b, day=self.day, subject=subject, status=status)
            for student, mark in (marks or {}).items():
                Attendance.objects.update_or_create(lesson=lesson, student=student, defaults={"status": mark})
            lessons.sync_lesson(lesson.pk)
            self.day += dt.timedelta(days=1)
            out.append(lesson)
        return out

    def row(self, profile):
        return queues.contract_row(queues.base_queryset().get(pk=profile.pk))

    def shown(self, profile):
        r = self.row(profile)
        return (r["month_number"], r["lessons_used"], r["lessons_total"], r["package_number"], r["package_lessons_used"])

    def finance(self):
        return (list(Invoice.objects.order_by("pk").values_list("amount", "status", "amount_paid")),
                list(LessonPackage.objects.order_by("pk").values_list("lessons_used", "status")),
                StudentPayment.objects.count(), PaymentAllocation.objects.count(),
                list(CreditLedgerEntry.objects.order_by("pk").values_list("amount", flat=True)))


class GroupMonthTests(GroupFixture):
    def test_two_students_joined_at_different_times_see_the_same_group_month(self):
        early = self.contract()
        late_student = self.student(self.group_b)
        checkpoints = {11: (1, 11), 12: (1, 12), 13: (2, 1), 14: (2, 2), 24: (2, 12), 25: (3, 1)}
        done, late = 0, None
        for held, (month, in_month) in checkpoints.items():
            self.held(held - done)
            self.held(1, subject=self.english)  # English / Soft Skills не влияют
            self.held(1, subject=self.soft)
            done = held
            if late is None:  # второй ученик пришёл после 11 занятий группы
                late = self.contract(student=late_student, start=self.day)
            for profile in (early, late):
                r = self.row(profile)
                self.assertEqual((r["month_number"], r["lessons_used"], r["lessons_total"], r["group_progress"]["held"]),
                                 (month, in_month, 12, held), (held, profile.pk))
        # Финансовые пакеты — у каждого свои (по его договору).
        self.assertEqual(self.shown(early), (3, 1, 12, 3, 1))
        self.assertEqual(self.shown(late), (3, 1, 12, 2, 2))  # засчитано 14 → пакет №2, 2/12
        self.assertEqual((self.row(early)["course_lessons_counted"], self.row(late)["course_lessons_counted"]), (25, 14))

    def test_attendance_and_absence_do_not_change_group_month(self):
        a, b = self.student(self.group_b), self.student(self.group_b)
        pa, pb = self.contract(student=a), self.contract(student=b)
        self.held(13, marks={a: Attendance.Status.PRESENT, b: Attendance.Status.ABSENT})
        self.assertEqual(self.row(pa)["month_number"], self.row(pb)["month_number"])
        card_a = self.client_for(self.accountant).get(BASE + f"profiles/{pa.pk}/card/").data["progress"]
        card_b = self.client_for(self.accountant).get(BASE + f"profiles/{pb.pk}/card/").data["progress"]
        self.assertEqual((card_a["group"]["month"], card_b["group"]["month"]), (2, 2))
        self.assertEqual((card_a["attendance"], card_b["attendance"]), ({"attended": 13, "held": 13},
                                                                         {"attended": 0, "held": 13}))

    def test_cancelled_and_scheduled_lessons_are_not_counted(self):
        profile = self.contract()
        self.held(5)
        self.held(2, status=Lesson.Status.CANCELLED)
        self.held(3, status=Lesson.Status.SCHEDULED)
        self.assertEqual(self.row(profile)["group_progress"]["held"], 5)
        self.assertEqual(self.shown(profile)[:2], (1, 5))


class ProgramHistoryTests(GroupFixture):
    def test_teacher_change_keeps_progress_and_counts_each_lesson_once(self):
        profile = self.contract()
        self.held(10)
        new = Teacher.objects.create(user=make_user("trainer2"))
        program = GroupTeacher.objects.get(group=self.group_b, subject=self.it)
        assign_trainer(self.group_b, teacher=new, user=self.admin, program=program)  # та же строка программы
        self.held(4)
        r = self.row(profile)
        self.assertEqual((r["group_progress"]["status"], r["group_progress"]["held"], r["month_number"],
                          r["lessons_used"]), ("ok", 14, 2, 2))

    def test_sequential_program_rows_are_one_history(self):
        profile = self.contract()
        self.held(6)
        old = GroupTeacher.objects.get(group=self.group_b, subject=self.it)
        old.is_active = False
        old.save(update_fields=["is_active"])
        new = GroupTeacher.objects.create(group=self.group_b, teacher=Teacher.objects.create(user=make_user("t3")),
                                          subject=self.it)
        for _ in range(7):
            lesson = Lesson.objects.create(group=self.group_b, group_teacher=new, teacher=new.teacher, subject=self.it,
                                           lesson_number=900 + _, date=self.day, start_time=dt.time(10),
                                           end_time=dt.time(11), status=Lesson.Status.COMPLETED)
            lessons.sync_lesson(lesson.pk)
            self.day += dt.timedelta(days=1)
        r = self.row(profile)
        self.assertEqual((r["group_progress"]["status"], r["group_progress"]["held"], r["month_number"],
                          r["lessons_used"]), ("ok", 13, 2, 1))

    def test_parallel_it_programs_need_configuration(self):
        profile = self.contract()
        self.held(13)
        GroupTeacher.objects.create(group=self.group_b, teacher=Teacher.objects.create(user=make_user("t4")),
                                    subject=self.it)  # вторая активная IT-программа
        r = self.row(profile)
        self.assertEqual((r["group_progress"]["status"], r["month_number"], r["lessons_used"]),
                         ("multiple_programs", None, None))
        self.assertEqual(r["group_progress"]["warning"], WARNINGS["multiple_programs"])
        self.assertEqual((r["package_number"], r["package_lessons_used"]), (2, 1))  # финансы — как были

    def test_overlapping_lessons_of_two_rows_need_configuration(self):
        self.held(4)
        second = GroupTeacher.objects.create(group=self.group_b, teacher=Teacher.objects.create(user=make_user("t5")),
                                             subject=self.it, is_active=False)
        Lesson.objects.create(group=self.group_b, group_teacher=second, teacher=second.teacher, subject=self.it,
                              lesson_number=950, date=dt.date(2026, 9, 3), start_time=dt.time(15),
                              end_time=dt.time(16), status=Lesson.Status.COMPLETED)
        self.assertEqual(group_progress(self.group_b, self.it.pk)["status"], "multiple_programs")


class TransferAndTariffTests(GroupFixture):
    def test_transfer_takes_new_group_progress_and_keeps_packages(self):
        student = self.student(self.group_b)
        profile = self.contract(student=student)
        self.held(13)
        self.held(3, group=self.group)  # другая группа того же курса провела 3 занятия IT
        before = self.finance()
        self.transfer(student, self.group, self.day)
        r = self.row(profile)
        self.assertEqual((r["month_number"], r["lessons_used"], r["group_progress"]["group_name"]), (1, 3, "Group A"))
        self.assertEqual((r["package_number"], r["package_lessons_used"]), (2, 1))
        self.assertEqual(self.finance(), before)  # перевод и отображение финансы не меняют

    def test_conflicting_or_missing_tariff_shows_warning_not_12(self):
        profile = self.contract()
        self.held(13)
        pricing.create_plan(actor=self.accountant, name="Next 6", subject=self.it, course=self.course,
                            lessons_per_package=12, package_price=D("12000"), effective_from=self.start,
                            duration_months=6)
        r = self.row(profile)
        self.assertEqual((r["group_progress"]["status"], r["month_number"], r["lessons_total"]),
                         ("tariff_conflict", None, None))
        self.assertEqual(group_progress(None, self.it.pk)["status"], "no_group")

    def test_academy_programs_tab_uses_the_same_group_month(self):
        from apps.academy.admin_views import _teaching_program_cards

        profile = self.contract()
        self.held(14)
        cards = {c["obj"].subject_id: c for c in _teaching_program_cards(self.group_b)}
        it = cards[self.it.pk]["group_month"]
        self.assertEqual((it["month"], it["months"], it["in_month"], it["per_month"]), (2, 4, 2, 12))
        r = self.row(profile)
        self.assertEqual((r["month_number"], r["lessons_used"]), (it["month"], it["in_month"]))  # бухгалтерия = академия
        self.assertIsNone(cards[self.english.pk]["group_month"])  # у English учебных месяцев нет

    def test_display_is_read_only(self):
        profile = self.contract()
        self.held(13)
        before = self.finance()
        api = self.client_for(self.accountant)
        for _ in range(2):
            self.row(profile)
            self.assertEqual(api.get(BASE + f"profiles/{profile.pk}/card/").status_code, 200)
            self.assertEqual(api.get(BASE + "queues/all/").status_code, 200)
        self.assertEqual(self.finance(), before)
