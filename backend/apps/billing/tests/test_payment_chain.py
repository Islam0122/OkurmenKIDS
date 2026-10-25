"""Цепочка исправления платежа (сценарий «Jasmina Karimberdieva»):
38 000 от 19.08 сторнирован, взамен внесены 19 000 (на месяцы 1–2) и 19 000
(аванс); договор 38 000, месяцы по 9 500. Деньги считаются один раз, сторно ≠
возврат, аванс на будущие месяцы — прогноз, а не распределение; повторное
сохранение той же стоимости не создаёт запись истории."""
from __future__ import annotations

import datetime as dt
import json
from io import StringIO

from django.core.management import call_command

from apps.accounting.models import PayrollAuditLog, StudentPayment
from apps.billing.models import BillingTermsChange, Invoice, PaymentReplacement, Receipt
from apps.billing.services import BillingError, contracts, corrections, money_audit, payment_chain, payments, profiles
from apps.billing.services.reports import reconcile
from apps.billing.tests.base import D
from apps.billing.tests.test_contracts import BASE
from apps.billing.tests.test_periods import OCT24, PeriodFixture

AUG19, SEP1 = dt.date(2026, 8, 19), dt.date(2026, 9, 1)


class ChainFixture(PeriodFixture):
    def setUp(self):
        super().setUp()
        self.at(AUG19)
        self.profile = self.contract(start_date=SEP1, discount_enabled=True, final_course_price="38000",
                                     discount_reason="Скидка")
        self.original = self.pay(self.profile, "38000", on=AUG19)  # №39
        self.at(OCT24)
        self.day = dt.date(2026, 9, 2)
        self.it_lessons(12)  # месяц 1 завершён → месяц 2 выставлен и оплачен из аванса
        payments.reverse_payment(self.original, actor=self.accountant, reason="Внесено одной суммой, делим на части")

    def summary(self):
        self.profile.refresh_from_db()
        return contracts.money_summary(self.profile)


class ReversalTests(ChainFixture):
    def test_reversal_is_not_a_refund_and_reopens_invoices(self):
        s = self.summary()
        self.assertEqual((s["received"], s["refunded"], s["voided"], s["voided_count"]), (D("0"), D("0"), D("38000"), 1))
        self.assertEqual((s["allocated"], s["credit"], s["due_now"]), (D("0"), D("0"), D("19000")))
        # Месяц 1 снова долг (и просрочен — 12 уроков прошли срок), месяц 2 — к оплате.
        self.assertEqual([i.status for i in self.live_invoices(self.profile)], [Invoice.Status.OVERDUE, Invoice.Status.OPEN])
        self.assertEqual(Receipt.objects.get(payment=self.original).status, Receipt.Status.CANCELLED)


class ReplacementTests(ChainFixture):
    def replace(self):
        first = payments.record_payment(profile=self.profile, amount="19000", received_date=AUG19,
                                        actor=self.accountant, replaces=self.original)[0]  # №41
        second = payments.record_payment(profile=self.profile, amount="19000", received_date=AUG19,
                                         actor=self.accountant, replaces=self.original)[0]  # №42
        return first, second

    def test_money_counted_once_and_advance_split_from_forecast(self):
        first, second = self.replace()
        m1, m2 = self.live_invoices(self.profile)
        self.assertEqual(sorted((a.invoice_id, a.amount) for a in first.billing_allocations.filter(status="ACTIVE")),
                         [(m1.pk, D("9500")), (m2.pk, D("9500"))])
        self.assertFalse(second.billing_allocations.exists())
        s = self.summary()
        self.assertEqual((s["received"], s["net_received"], s["allocated"], s["credit"]),
                         (D("38000"), D("38000"), D("19000"), D("19000")))  # не 76 000 и не 57 000
        self.assertEqual((s["credit_reserved_future"], s["credit_unreserved"], s["future"], s["due_now"], s["net_to_pay"]),
                         (D("19000"), D("0"), D("19000"), D("0"), D("0")))
        schedule = contracts.payment_schedule(self.profile)
        future = [m for m in schedule["months"] if m["state"] == "future"]
        self.assertEqual([(m["amount"], m["covered_by_credit"], m["paid"]) for m in future],
                         [(D("9500"), D("9500"), D("0"))] * 2)  # прогноз покрытия, не оплата
        self.assertEqual(reconcile(), [])

    def test_chain_is_traceable_in_api_and_receipts(self):
        first, second = self.replace()
        card = self.client_for(self.accountant).get(BASE + f"profiles/{self.profile.pk}/card/").data
        rows = {p["id"]: p for p in card["payments"]}
        self.assertEqual(sorted(rows[self.original.pk]["replaced_by"]), sorted([first.pk, second.pk]))
        self.assertEqual((rows[first.pk]["replaces"], rows[second.pk]["replaces"]), ([self.original.pk], [self.original.pk]))
        self.assertEqual(rows[self.original.pk]["status"], "void")
        statuses = sorted(Receipt.objects.filter(profile=self.profile).values_list("status", flat=True))
        self.assertEqual(statuses, [Receipt.Status.CANCELLED, Receipt.Status.ISSUED, Receipt.Status.ISSUED])
        self.assertTrue(PayrollAuditLog.objects.filter(action="billing_payment_replacement",
                                                       entity_id=self.original.pk).exists())

    def test_replacement_cannot_exceed_original_or_be_linked_twice(self):
        first, second = self.replace()
        with self.assertRaises(BillingError):
            payments.record_payment(profile=self.profile, amount="100", received_date=OCT24, actor=self.accountant,
                                    replaces=self.original)
        self.assertEqual(StudentPayment.objects.filter(amount=D("100")).count(), 0)  # откат всей операции
        self.assertEqual(payment_chain.link_replacement(self.original, [first], actor=self.accountant, reason="x"), [])
        with self.assertRaises(BillingError):  # подтверждённый платёж не может быть «исходным»
            payment_chain.link_replacement(first, [second], actor=self.accountant, reason="x")

    def test_correct_way_split_one_payment_without_new_money(self):
        """Правильнее: не сторно и два новых платежа, а исправление распределения одного."""
        self.at(OCT24)
        one = payments.record_payment(profile=self.profile, amount="38000", received_date=AUG19, actor=self.accountant)[0]
        m1, m2 = self.live_invoices(self.profile)
        corrections.correct_payment(one, actor=self.accountant, reason="Ровно на месяцы 1–2, остаток — аванс",
                                    allocations=[(m1, D("9500")), (m2, D("9500"))])
        s = self.summary()
        self.assertEqual((s["received"], s["allocated"], s["credit"]), (D("38000"), D("19000"), D("19000")))
        self.assertEqual(StudentPayment.objects.filter(billing_profile=self.profile, status="confirmed").count(), 1)
        self.assertEqual(Receipt.objects.filter(payment=one).count(), 1)


class UnlinkedHistoryTests(ChainFixture):
    def test_audit_finds_unlinked_replacements_and_links_on_confirm(self):
        first = payments.record_payment(profile=self.profile, amount="19000", received_date=AUG19, actor=self.accountant)[0]
        second = payments.record_payment(profile=self.profile, amount="19000", received_date=AUG19, actor=self.accountant)[0]
        problem = next(p for p in money_audit.profile_money_audit(self.profile)["problems"]
                       if p["type"] == "unlinked_replacement")
        self.assertEqual((problem["original"], problem["candidates"], problem["fix"]),
                         (self.original.pk, [first.pk, second.pk], "confirm"))
        args = {"link": self.original.pk, "replacements": f"{first.pk},{second.pk}", "reason": "Те же деньги, чек кассы"}
        out = StringIO()
        call_command("billing_money_audit", profile=self.profile.pk, stdout=out, **args)
        self.assertTrue(json.loads(out.getvalue())["link"]["would_link"])  # dry-run
        self.assertEqual(PaymentReplacement.objects.count(), 0)
        call_command("billing_money_audit", profile=self.profile.pk, confirm=True, stdout=StringIO(), **args)
        self.assertEqual(PaymentReplacement.objects.count(), 2)
        call_command("billing_money_audit", profile=self.profile.pk, confirm=True, stdout=StringIO(), **args)
        self.assertEqual(PaymentReplacement.objects.count(), 2)  # идемпотентно
        types = {p["type"] for p in money_audit.profile_money_audit(self.profile)["problems"]}
        self.assertNotIn("unlinked_replacement", types)
        self.assertEqual(self.summary()["received"], D("38000"))  # связь деньги не меняет


class PriceHistoryTests(ChainFixture):
    def test_saving_same_price_creates_no_history_record(self):
        before = BillingTermsChange.objects.filter(profile=self.profile).count()
        for _ in range(4):
            self.assertIsNone(profiles.request_course_terms_change(
                self.profile, actor=self.accountant, discount_enabled=True, final_course_price="38000", reason="x"))
        self.assertEqual(BillingTermsChange.objects.filter(profile=self.profile).count(), before)
        response = self.client_for(self.accountant).post(BASE + f"profiles/{self.profile.pk}/course-terms/", {
            "discount_enabled": True, "final_course_price": "38000", "reason": "повтор"}, format="json")
        self.assertEqual((response.status_code, response.data["changed"]), (200, False))
        # Настоящее изменение по-прежнему записывается.
        profiles.request_course_terms_change(self.profile, actor=self.accountant, discount_enabled=True,
                                             final_course_price="37000", reason="Ещё скидка")
        self.assertEqual(BillingTermsChange.objects.filter(profile=self.profile).count(), before + 1)

    def test_old_noop_records_kept_but_hidden_in_price_history(self):
        BillingTermsChange.objects.create(
            profile=self.profile, discount_enabled=True, final_course_price=D("38000"), discount_amount=D("22000"),
            reason="старый повтор", previous_terms={"final_course_price": "38000.00"},
            status=BillingTermsChange.Status.APPROVED, requested_by=self.accountant)
        changes = contracts.payment_schedule(self.profile)["price_changes"]
        self.assertFalse([c for c in changes if c["from"] == c["to"]])
        self.assertTrue(BillingTermsChange.objects.filter(reason="старый повтор").exists())  # не удалена
