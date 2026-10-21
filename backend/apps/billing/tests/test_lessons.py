"""Учёт уроков: завершение пакета, двойное списание, повторное начисление,
отсутствие, перенос, направления, перевод между группами."""
from __future__ import annotations

import datetime as dt

from django.db import IntegrityError, transaction

from apps.academy.models import Attendance, Lesson
from apps.billing.models import (
    AbsencePolicy,
    BillingNotification,
    Invoice,
    LessonConsumption,
    LessonPackage,
)
from apps.billing.services import BillingError, invoices, lessons, pricing
from apps.billing.tests.base import D, BillingFixture


class PackageCompletionTests(BillingFixture):
    def test_package_completes_after_configured_number_of_lessons(self):
        profile = self.profile()
        self.hold(11)
        first = self.packages(profile)[0]
        self.assertEqual((first.status, first.lessons_used), ("ACTIVE", 11))
        self.assertEqual(len(self.invoices(profile)), 1)

        self.hold(1, start_day=self.start + dt.timedelta(days=11))
        first.refresh_from_db()
        self.assertEqual(first.status, LessonPackage.Status.COMPLETED)
        self.assertEqual(first.completed_on, self.start + dt.timedelta(days=11))
        second = self.packages(profile)[1]
        self.assertEqual((second.status, second.lessons_total, second.lessons_used), ("ACTIVE", 12, 0))
        invoice = second.invoices.get()
        self.assertEqual((invoice.amount, invoice.issue_date), (D("4000"), first.completed_on))
        self.assertEqual(invoice.due_date, first.completed_on + dt.timedelta(days=5))

        # 13-й урок уходит во второй пакет.
        self.hold(1, start_day=self.start + dt.timedelta(days=12))
        second.refresh_from_db()
        self.assertEqual(second.lessons_used, 1)

    def test_lessons_per_package_comes_from_plan_not_code(self):
        profile = self.profile(plan=self.en_plan)
        self.hold(19, subject=self.english)
        self.assertEqual(self.packages(profile)[0].status, "ACTIVE")
        self.hold(1, subject=self.english, start_day=self.start + dt.timedelta(days=19))
        self.assertEqual([p.status for p in self.packages(profile)], ["COMPLETED", "ACTIVE"])
        self.assertEqual(self.packages(profile)[0].lessons_total, 20)

    def test_warning_after_ninth_lesson_once(self):
        profile = self.profile()
        self.hold(8)
        self.assertFalse(BillingNotification.objects.filter(kind="PACKAGE_ENDING").exists())
        self.hold(2, start_day=self.start + dt.timedelta(days=8))
        notes = BillingNotification.objects.filter(kind="PACKAGE_ENDING", profile=profile)
        self.assertEqual(notes.count(), 1)
        self.assertIn("использовано 9 из 12", notes.get().message)

    def test_scheduled_lesson_is_not_consumed_until_completed(self):
        profile = self.profile()
        lesson = self.lesson(status=Lesson.Status.SCHEDULED)
        lessons.sync_lesson(lesson.pk)
        self.assertFalse(LessonConsumption.objects.exists())
        lesson.status = Lesson.Status.COMPLETED
        lesson.save()
        lessons.sync_lesson(lesson.pk)
        self.assertEqual(self.packages(profile)[0].lessons_used, 1)

    def test_subject_of_profile_filters_lessons(self):
        it_profile = self.profile()
        en_profile = self.profile(student=it_profile.student, plan=self.en_plan)
        self.hold(3, subject=self.it)
        self.hold(2, subject=self.english, start_day=self.start + dt.timedelta(days=10))
        self.assertEqual(self.packages(it_profile)[0].lessons_used, 3)
        self.assertEqual(self.packages(en_profile)[0].lessons_used, 2)

    def test_lessons_before_start_date_are_not_charged(self):
        profile = self.profile(start_date=self.start + dt.timedelta(days=5))
        self.hold(10)
        self.assertEqual(self.packages(profile)[0].lessons_used, 5)


class DoubleConsumptionTests(BillingFixture):
    def test_sync_twice_consumes_once(self):
        profile = self.profile()
        lesson = self.lesson(day=self.start)
        lessons.sync_lesson(lesson.pk)
        lessons.sync_lesson(lesson.pk)
        _c, created = lessons.consume_lesson(profile, lesson)
        self.assertFalse(created)
        self.assertEqual(LessonConsumption.objects.filter(kind="CONSUME").count(), 1)
        self.assertEqual(self.packages(profile)[0].lessons_used, 1)

    def test_database_rejects_second_active_consumption(self):
        profile = self.profile()
        lesson = self.lesson(day=self.start)
        lessons.sync_lesson(lesson.pk)
        package = self.packages(profile)[0]
        with self.assertRaises(IntegrityError), transaction.atomic():
            LessonConsumption.objects.create(
                package=package, profile=profile, student=profile.student, lesson=lesson, lesson_ref=lesson.pk,
                lesson_date=lesson.date,
            )

    def test_cancelled_lesson_is_reversed_by_correcting_entry(self):
        profile = self.profile()
        lesson = self.hold(1)[0]
        lesson.status = Lesson.Status.CANCELLED
        lesson.save()
        result = lessons.sync_lesson(lesson.pk)
        self.assertEqual(len(result["reversed"]), 1)
        original = LessonConsumption.objects.get(kind="CONSUME")
        self.assertEqual(original.status, "REVERSED")
        reversal = LessonConsumption.objects.get(kind="REVERSAL")
        self.assertEqual(reversal.reversal_of, original)
        self.assertEqual(self.packages(profile)[0].lessons_used, 0)
        # Перенос: новый урок с rescheduled_from списывается, когда проведён.
        makeup = self.lesson(day=self.start + dt.timedelta(days=3))
        makeup.rescheduled_from = lesson
        makeup.save()
        lessons.sync_lesson(makeup.pk)
        self.assertEqual(self.packages(profile)[0].lessons_used, 1)

    def test_deleted_lesson_is_reversed(self):
        profile = self.profile()
        lesson = self.hold(1)[0]
        lesson_id = lesson.pk
        lesson.delete()
        lessons.sync_lesson(lesson_id)
        self.assertEqual(self.packages(profile)[0].lessons_used, 0)
        self.assertTrue(LessonConsumption.objects.filter(lesson_ref=lesson_id, kind="REVERSAL").exists())

    def test_reversal_in_completed_package_frees_slot_without_new_invoice(self):
        profile = self.profile()
        held = self.hold(12)
        self.assertEqual(len(self.invoices(profile)), 2)
        wrong = LessonConsumption.objects.get(lesson_ref=held[3].pk)
        lessons.reverse_consumption(wrong, actor=self.accountant, reason="Ошибочно отмечен проведённым")
        first, second = self.packages(profile)
        self.assertEqual((first.status, first.lessons_used), ("COMPLETED", 11))
        # Следующий урок закрывает «дырку» первого пакета, не второй пакет.
        self.hold(1, start_day=self.start + dt.timedelta(days=20))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.lessons_used, second.lessons_used), (12, 0))
        self.assertEqual(len(self.invoices(profile)), 2)

    def test_manager_cannot_reverse_consumption(self):
        self.profile()
        self.hold(1)
        consumption = LessonConsumption.objects.get()
        with self.assertRaises(BillingError):
            lessons.reverse_consumption(consumption, actor=self.manager, reason="x")


class AbsenceTests(BillingFixture):
    def test_absent_student_is_charged_by_default(self):
        profile = self.profile()
        lesson = self.lesson(day=self.start)
        self.mark(lesson, profile.student, Attendance.Status.ABSENT)
        lessons.sync_lesson(lesson.pk)
        self.assertEqual(self.packages(profile)[0].lessons_used, 1)

    def test_excused_absence_policy(self):
        pricing.update_plan_settings(self.it_plan, actor=self.accountant, absence_policy=AbsencePolicy.EXCEPT_EXCUSED)
        profile = self.profile()
        lesson = self.lesson(day=self.start)
        lessons.sync_lesson(lesson.pk)
        self.assertEqual(self.packages(profile)[0].lessons_used, 1)
        # Отсутствие отметили уважительным позже — списание сторнируется.
        self.mark(lesson, profile.student, Attendance.Status.EXCUSED)
        lessons.sync_lesson(lesson.pk)
        self.assertEqual(self.packages(profile)[0].lessons_used, 0)

    def test_attended_only_policy(self):
        pricing.update_plan_settings(self.it_plan, actor=self.accountant, absence_policy=AbsencePolicy.ATTENDED_ONLY)
        profile = self.profile()
        absent, present = self.lesson(day=self.start), self.lesson(day=self.start + dt.timedelta(days=1))
        self.mark(absent, profile.student, Attendance.Status.ABSENT)
        self.mark(present, profile.student, Attendance.Status.LATE)
        lessons.sync_lesson(absent.pk)
        lessons.sync_lesson(present.pk)
        self.assertEqual(self.packages(profile)[0].lessons_used, 1)


class NoDuplicateInvoiceTests(BillingFixture):
    def test_repeated_next_invoice_call_returns_existing(self):
        profile = self.profile()
        self.hold(12)
        package, invoice, created = invoices.create_next_package_invoice(profile, activate=True)
        self.assertFalse(created)
        self.assertEqual(Invoice.objects.filter(profile=profile).count(), 2)
        # Ещё раз: следующий (ACTIVE) уже есть, PLANNED нет — создаётся только
        # заранее и только один раз.
        p1, _i1, c1 = invoices.create_next_package_invoice(profile)
        p2, _i2, c2 = invoices.create_next_package_invoice(profile)
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(p1, p2)
        self.assertEqual(Invoice.objects.filter(profile=profile).count(), 3)

    def test_database_rejects_second_live_invoice_for_package(self):
        profile = self.profile()
        invoice = self.invoices(profile)[0]
        with self.assertRaises(IntegrityError), transaction.atomic():
            Invoice.objects.create(
                profile=profile, package=invoice.package, business_key="dup", amount=D("1"), status="OPEN",
                issue_date=self.today, due_date=self.today,
            )

    def test_early_invoice_only_with_setting(self):
        profile = self.profile()
        self.hold(9)
        self.assertEqual(len(self.invoices(profile)), 1)

        pricing.update_plan_settings(self.it_plan, actor=self.accountant, early_invoice_enabled=True,
                                     early_invoice_after_lessons=9)
        other = self.profile()
        self.hold(9, start_day=self.start + dt.timedelta(days=30))
        self.assertEqual(len(self.invoices(other)), 2)
        self.assertEqual([p.status for p in self.packages(other)], ["ACTIVE", "PLANNED"])
        # После 12-го урока — тот же заранее созданный пакет, без нового начисления.
        self.hold(3, start_day=self.start + dt.timedelta(days=39))
        self.assertEqual([p.status for p in self.packages(other)], ["COMPLETED", "ACTIVE"])
        self.assertEqual(len(self.invoices(other)), 2)

    def test_early_invoice_threshold_must_be_below_package(self):
        with self.assertRaises(BillingError):
            pricing.update_plan_settings(self.it_plan, actor=self.accountant, early_invoice_enabled=True,
                                         early_invoice_after_lessons=12)


class TransferTests(BillingFixture):
    def test_transfer_keeps_package_and_charges_new_group(self):
        student = self.student()
        profile = self.profile(student=student)
        self.hold(5)
        transfer_day = self.start + dt.timedelta(days=10)
        self.transfer(student, self.group_b, transfer_day)
        # Урок старой группы после перевода — не списывается; новой — в тот же пакет.
        old = self.lesson(group=self.group, day=transfer_day + dt.timedelta(days=1))
        new = self.lesson(group=self.group_b, day=transfer_day + dt.timedelta(days=1))
        lessons.sync_lesson(old.pk)
        lessons.sync_lesson(new.pk)
        package = self.packages(profile)[0]
        self.assertEqual(package.lessons_used, 6)
        self.assertEqual(LessonConsumption.objects.get(lesson_ref=new.pk).group, self.group_b)
        self.assertFalse(LessonConsumption.objects.filter(lesson_ref=old.pk).exists())
        # Ранние уроки старой группы при повторной обработке остаются списанными.
        lessons.sync_recent_lessons(days=90)
        package.refresh_from_db()
        self.assertEqual(package.lessons_used, 6)
        self.assertEqual(len(self.invoices(profile)), 1)
