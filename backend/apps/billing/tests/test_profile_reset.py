"""«Полный сброс» бухгалтерии ученика (сценарий Jasmina Karimberdieva):
№39 на 38 000 сторнирован, №41 + №42 по 19 000 внесены взамен, ещё два
платежа по 19 000 внесены повторно — проведено 76 000 при договоре 38 000.

Обычное удаление по-прежнему блокируется; полный сброс удаляет только
бухгалтерию её профиля после явного подтверждения, без сторно / возвратов /
платежей «взамен», откатывается при ошибке; новый профиль Prog SOFT 3
создаётся с нуля и списывает каждый урок один раз."""
from __future__ import annotations

from unittest import mock

from apps.academy.models import Attendance
from apps.accounting.models import PayrollAuditLog, StudentPayment
from apps.billing.models import (
    LessonConsumption,
    PaymentMode,
    PaymentReplacement,
    Receipt,
)
from apps.billing.services import (
    BillingError,
    contracts,
    lessons,
    payments,
    pricing,
    profile_purge,
)
from apps.billing.services.reports import reconcile
from apps.billing.tests.base import D
from apps.billing.tests.test_profile_purge import AUG19, LIST, SEP1, PurgeFixture
from apps.users.models import User


class ResetFixture(PurgeFixture):
    def setUp(self):
        super().setUp()
        self.void()  # №39 сторнирован
        self.first = [payments.record_payment(profile=self.profile, amount="19000", received_date=AUG19,
                                              actor=self.accountant, replaces=self.payment)[0] for _ in range(2)]
        self.second = [self.pay(self.profile, "19000", on=AUG19) for _ in range(2)]  # повторный ввод
        self.confirmed = [p.pk for p in self.first + self.second]

    def full_body(self, **extra) -> dict:
        report = profile_purge.preview(self.profile, actor=self.admin)
        return {"mode": "full", "fingerprint": report["fingerprint"], "payment_ids": ",".join(map(str, self.confirmed)),
                "reason": "Ошибочный учёт — начинаем заново", "last_name": "Karimberdieva",
                "phrase": profile_purge.FULL_PHRASE, "money_acknowledged": "on", **extra}


class DiagnosisTests(ResetFixture):
    def test_76000_is_two_registrations_of_the_same_split_and_normal_mode_blocks(self):
        s = contracts.money_summary(self.profile)
        self.assertEqual((s["received"], s["voided"], self.profile.final_course_price), (D("76000"), D("38000"), 38000))
        report = profile_purge.preview(self.profile, actor=self.admin)
        self.assertFalse(report["can_delete"])
        self.assertTrue(report["full_reset_available"])
        self.assertEqual(report["money_total"], D("76000"))
        self.assertEqual([p["id"] for p in report["real_money"]], self.confirmed)
        self.assertTrue(all(p["possible_duplicate"] for p in report["real_money"]))
        with self.assertRaises(BillingError) as ctx:
            profile_purge.purge(self.profile, actor=self.admin, reason="x")
        self.assertEqual(ctx.exception.code, "real_money")
        page = self.client_as(self.admin).get(self.url())
        self.assertContains(page, "Полный сброс бухгалтерии ученика")
        self.assertContains(page, "возможен повторный ввод")


class ConfirmationTests(ResetFixture):
    def test_missing_confirmation_or_changed_data_changes_nothing(self):
        before = self.owned()
        client = self.client_as(self.admin)
        for wrong in ({"phrase": "сбросить"}, {"money_acknowledged": ""}, {"last_name": "Other"}):
            client.post(self.url(), self.full_body(**wrong))
        client.post(self.url(), self.full_body(payment_ids=",".join(map(str, self.confirmed[:3]))))
        body = self.full_body()
        self.pay(self.profile, "1000", on=AUG19)  # новый платёж после просмотра отчёта
        client.post(self.url(), body)
        with self.assertRaises(BillingError) as ctx:
            profile_purge.purge(self.profile, actor=self.admin, reason="x", full_reset=True,
                                confirmed_payment_ids=self.confirmed)
        self.assertEqual(ctx.exception.code, "stale")
        self.assertEqual({k: v for k, v in self.owned().items() if k not in ("payments", "receipts", "ledger",
                                                                            "allocations")},
                         {k: v for k, v in before.items() if k not in ("payments", "receipts", "ledger",
                                                                     "allocations")})
        self.assertEqual(StudentPayment.objects.filter(billing_profile=self.profile, status="confirmed").count(), 5)

    def test_closed_period_needs_explicit_confirmation(self):
        closed = [{"date": AUG19.isoformat(), "period": "Август 2026", "status": "APPROVED"}]
        with mock.patch("apps.billing.services.corrections.closed_periods", return_value=closed):
            with self.assertRaises(BillingError) as ctx:
                profile_purge.purge(self.profile, actor=self.admin, reason="x", full_reset=True,
                                    confirmed_payment_ids=self.confirmed)
            self.assertEqual(ctx.exception.code, "closed_period")
            self.assertContains(self.client_as(self.admin).get(self.url()), "Август 2026")
            profile_purge.purge(self.profile, actor=self.admin, reason="x", full_reset=True,
                                confirmed_payment_ids=self.confirmed, confirm_closed_period=True)
        self.assertEqual(self.owned()["profile"], 0)

    def test_error_midway_rolls_back_everything(self):
        before, education = self.owned(), self.education()
        original = profile_purge._delete_leaves_first

        def broken(collected):
            original(collected)
            raise RuntimeError("сбой после удаления")

        with mock.patch.object(profile_purge, "_delete_leaves_first", broken), self.assertRaises(RuntimeError):
            profile_purge.purge(self.profile, actor=self.admin, reason="x", full_reset=True,
                                confirmed_payment_ids=self.confirmed)
        self.assertEqual(self.owned(), before)
        self.assertEqual(self.education(), education)
        self.assertFalse(PayrollAuditLog.objects.filter(action=profile_purge.ACTION).exists())

    def test_only_active_superuser(self):
        staff = [self.staff]
        for role in (User.Role.ACCOUNTANT, User.Role.DIRECTOR, User.Role.ADMIN):
            user = self.make_staff(role)
            staff.append(user)
        before = self.owned()
        for user in staff:
            response = self.client_as(user).post(self.url(), self.full_body())
            self.assertIn(response.status_code, (302, 403), user)
        for actor in (*staff, self.accountant, self.director, self.manager, None):
            with self.assertRaises(BillingError) as ctx:
                profile_purge.purge(self.profile, actor=actor, reason="x", full_reset=True,
                                    confirmed_payment_ids=self.confirmed)
            self.assertEqual(ctx.exception.code, "forbidden")
        self.admin.is_active = False
        self.admin.save()
        with self.assertRaises(BillingError):
            profile_purge.purge(self.profile, actor=self.admin, reason="x", full_reset=True,
                                confirmed_payment_ids=self.confirmed)
        self.assertEqual(self.owned(), before)

    def make_staff(self, role):
        from django.contrib.auth.models import Permission

        from apps.billing.tests.base import make_user

        user = make_user(f"reset_{role}", role, is_staff=True)
        user.user_permissions.set(Permission.objects.all())
        return user


class FullResetTests(ResetFixture):
    def test_full_reset_removes_only_her_billing_and_keeps_education_and_others(self):
        education, other_money = self.education(), self.other_money()
        receipts = list(Receipt.objects.filter(profile=self.profile).values_list("number", flat=True))
        response = self.client_as(self.admin).post(self.url(), self.full_body())
        self.assertRedirects(response, LIST, fetch_redirect_response=False)

        self.assertEqual(set(self.owned().values()), {0})
        self.assertFalse(StudentPayment.objects.filter(pk__in=self.confirmed + [self.payment.pk]).exists())
        self.assertFalse(PaymentReplacement.objects.exists())  # связи только её платежей
        self.assertFalse(Receipt.objects.filter(number__in=receipts).exists())
        self.assertEqual(self.education(), education)
        self.assertEqual(self.other_money(), other_money)
        self.assertTrue(StudentPayment.objects.filter(pk=self.other_payment.pk, status="confirmed").exists())
        self.assertEqual(reconcile(), [])
        # Сторно, возвраты и платежи «взамен» не создавались: других платежей не прибавилось.
        self.assertEqual(StudentPayment.objects.count(), 1)
        entry = PayrollAuditLog.objects.get(action=profile_purge.ACTION)
        self.assertTrue(entry.new_values["full_reset"])
        self.assertEqual(entry.new_values["confirmed_total"], "76000.00")
        self.assertEqual(sorted(p["id"] for p in entry.new_values["confirmed_payments_deleted"]), sorted(self.confirmed))
        self.assertEqual(sorted(r["fields"]["number"] for r in entry.old_values["rows"]["billing.Receipt"]),
                         sorted(receipts))

    def test_new_prog_soft_3_profile_from_scratch_counts_each_lesson_once(self):
        profile_purge.purge(self.profile, actor=self.admin, reason="Начать заново", full_reset=True,
                            confirmed_payment_ids=self.confirmed)
        plan = pricing.create_plan(
            actor=self.accountant, name="Prog SOFT 3", subject=self.it, course=self.course, lessons_per_package=12,
            package_price=D("15000"), effective_from=self.start, duration_months=4, payment_deadline_lessons=3,
        )
        from apps.billing.services import profiles

        fresh = profiles.create_student_billing_profile(
            student=self.jasmina, plan=plan, actor=self.accountant, start_date=SEP1,
            payment_mode=PaymentMode.MONTHLY, discount_enabled=True, final_course_price="38000",
            discount_reason="Подтверждённый договор", responsible_accountant=self.accountant,
        )
        s = contracts.money_summary(fresh)
        self.assertEqual((fresh.standard_course_price, fresh.final_course_price, fresh.discount_amount,
                          fresh.payment_mode, fresh.duration_months, fresh.lessons_per_month),
                         (60000, 38000, 22000, PaymentMode.MONTHLY, 4, 12))
        self.assertEqual((s["received"], s["voided"], s["refunded"], s["credit"], s["allocated"]), (0, 0, 0, 0, 0))
        consumed = LessonConsumption.objects.filter(profile=fresh, kind="CONSUME", status="ACTIVE")
        self.assertEqual(consumed.count(), 12)
        self.assertEqual(sorted(consumed.values_list("lesson_ref", flat=True)), sorted(l.pk for l in self.lessons))
        lessons.sync_profile_history(fresh)  # повторная синхронизация — без дублей
        for lesson in self.lessons:
            lessons.sync_lesson(lesson.pk)
        self.assertEqual(LessonConsumption.objects.filter(student=self.jasmina, kind="CONSUME").count(), 12)
        self.assertTrue(Attendance.objects.filter(lesson=self.lessons[0], student=self.jasmina).exists())
