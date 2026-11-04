"""«Архив студентов» бухгалтерии: деактивация в LMS → студент сразу в архиве
с теми же деньгами, что в карточке договора; история не теряется."""
from __future__ import annotations

import datetime as dt

from django.core.exceptions import ValidationError
from django.db.models import ProtectedError

from apps.academy.models import Lesson, Student, StudentStatusEvent
from apps.academy.services.student_status import deactivate_student, reactivate_student
from apps.accounting.models import PayrollAuditLog, StudentPayment
from apps.billing.models import Invoice, LessonConsumption, StudentBillingProfile
from apps.billing.services import archive, contracts, lessons, payments
from apps.users.models import User

from .base import D, BillingFixture, make_user

ARCHIVE = "/api/v1/accounting/billing/archive/"


class ArchiveFixture(BillingFixture):
    def deactivate(self, student, reason="relocation", **extra):
        with self.captureOnCommitCallbacks(execute=True):
            return deactivate_student(student, reason=reason, performed_by=self.manager,
                                      event_date=extra.pop("event_date", self.today), **extra)

    def pay(self, profile, amount):
        payment, _ = payments.record_payment(profile=profile, amount=amount, received_date=self.today,
                                             actor=self.accountant, comment="Оплата")
        return payment

    def row(self, student, client=None, **params):
        client = client or self.client_for(self.accountant)
        response = client.get(ARCHIVE, params)
        self.assertEqual(response.status_code, 200, response.data)
        return next((r for r in response.data["results"] if r["id"] == student.pk), None)

    def money_of(self, profile):
        profile.refresh_from_db()
        return contracts.money_summary(profile)


class DeactivationFinanceTests(ArchiveFixture):
    def test_1_without_debt(self):
        profile = self.profile()
        self.hold(3)
        self.pay(profile, "4000")
        self.deactivate(profile.student)
        row = self.row(profile.student)
        self.assertIsNotNone(row)
        self.assertEqual(row["finance"]["debt"], "0.00")
        self.assertFalse(row["finance"]["has_debt"])
        self.assertEqual(row["finance"]["paid"], "4000.00")
        self.assertEqual(row["finance"]["invoiced"], "4000.00")
        self.assertEqual((row["status_display"], row["reason"]), ("Неактивен", "relocation"))

    def test_2_with_debt_debt_is_kept(self):
        """30 000 / начислено 30 000 / оплачено 20 000 → долг 10 000 и после ухода."""
        profile = self.profile(plan=self._course_plan(), start_date=self.start)
        self._invoice_all(profile)
        self.pay(profile, "20000")
        before = self.money_of(profile)
        self.assertEqual((before["invoiced"], before["net_received"]), (D("30000"), D("20000")))
        self.deactivate(profile.student)
        row = self.row(profile.student)
        self.assertEqual(row["finance"]["contract_price"], "30000.00")
        self.assertEqual(row["finance"]["invoiced"], "30000.00")
        self.assertEqual(row["finance"]["paid"], "20000.00")
        self.assertEqual(row["finance"]["discount"], "0.00")
        self.assertEqual(row["finance"]["debt"], "10000.00")
        self.assertTrue(row["finance"]["has_debt"])
        # Та же формула, что карточка договора.
        self.assertEqual(row["finance"]["debt"], str(self.money_of(profile)["outstanding"]))

    def test_3_overpayment_is_kept(self):
        profile = self.profile()
        self.hold(3)
        self.pay(profile, "6000")
        self.deactivate(profile.student)
        row = self.row(profile.student)
        self.assertEqual(row["finance"]["debt"], "0.00")
        self.assertEqual(row["finance"]["overpayment"], "2000.00")
        self.assertEqual(self.credit(profile), D("2000"))  # аванс не списан

    def test_4_payment_history_is_kept(self):
        profile = self.profile()
        self.hold(2)
        payment = self.pay(profile, "1500")
        self.deactivate(profile.student)
        detail = self.client_for(self.accountant).get(f"{ARCHIVE}{profile.student_id}/").data
        self.assertEqual([p["id"] for p in detail["payments"]], [payment.pk])
        row = detail["payments"][0]
        self.assertEqual((row["amount"], row["comment"], row["accepted_by"]["id"]), ("1500.00", "Оплата", self.accountant.pk))
        self.assertEqual(StudentPayment.objects.get(pk=payment.pk).status, StudentPayment.Status.CONFIRMED)

    def test_5_contract_is_kept(self):
        profile = self.profile()
        self.hold(2)
        self.deactivate(profile.student)
        profile.refresh_from_db()
        self.assertEqual((profile.status, profile.stop_source), ("INACTIVE", "STUDENT_STATUS"))
        detail = self.client_for(self.accountant).get(f"{ARCHIVE}{profile.student_id}/").data
        self.assertEqual([c["id"] for c in detail["contracts"]], [profile.pk])
        self.assertEqual(detail["contracts"][0]["status"], "INACTIVE")
        self.assertEqual(detail["deactivation"]["performed_by"]["id"], self.manager.pk)
        self.assertEqual(detail["invoices"][0]["status"], Invoice.Status.OPEN)

    def test_6_new_charges_stop(self):
        profile = self.profile()
        self.hold(3)
        self.deactivate(profile.student)
        invoices_before = Invoice.objects.filter(profile=profile).count()
        consumed_before = LessonConsumption.objects.filter(profile=profile).count()
        for i in range(1, 15):  # больше пакета — следующий месяц не выставляется
            lesson = self.lesson(day=self.today + dt.timedelta(days=i))
            lessons.sync_lesson(lesson.pk)
        self.assertEqual(Invoice.objects.filter(profile=profile).count(), invoices_before)
        self.assertEqual(LessonConsumption.objects.filter(profile=profile).count(), consumed_before)

    def test_7_archived_student_can_pay_old_debt(self):
        profile = self.profile()
        self.hold(3)
        self.deactivate(profile.student)
        self.assertEqual(self.row(profile.student)["finance"]["debt"], "4000.00")
        response = self.client_for(self.accountant).post(
            "/api/v1/accounting/billing/payments/",
            {"profile": profile.pk, "amount": "4000", "received_date": self.today.isoformat(), "method": "cash",
             "comment": "Погашение долга после ухода"}, format="json", HTTP_IDEMPOTENCY_KEY="archive-pay-1")
        self.assertEqual(response.status_code, 201, response.data)
        row = self.row(profile.student)
        self.assertEqual((row["finance"]["debt"], row["finance"]["paid"]), ("0.00", "4000.00"))
        self.assertEqual(Student.objects.get(pk=profile.student_id).status, Student.Status.WITHDRAWN)
        # Повтор той же формы не проводит деньги дважды.
        self.client_for(self.accountant).post(
            "/api/v1/accounting/billing/payments/",
            {"profile": profile.pk, "amount": "4000", "received_date": self.today.isoformat(), "method": "cash"},
            format="json", HTTP_IDEMPOTENCY_KEY="archive-pay-1")
        self.assertEqual(StudentPayment.objects.filter(billing_profile=profile).count(), 1)

    # --- helpers -----------------------------------------------------------

    def _course_plan(self):
        from apps.billing.services import pricing

        return pricing.create_plan(
            actor=self.accountant, name="IT курс", subject=self.it, lessons_per_package=12, package_price=D("10000"),
            effective_from=self.start - dt.timedelta(days=30), duration_months=3,
        )

    def _invoice_all(self, profile):
        self.hold(36)  # три учебных месяца проведены → три начисления по 10 000
        profile.refresh_from_db()
        self.assertEqual(sum(i.amount for i in self.invoices(profile) if i.status != Invoice.Status.VOID), D("30000"))


class RestoreTests(ArchiveFixture):
    def test_8_restore_keeps_history_and_does_not_duplicate(self):
        profile = self.profile()
        self.hold(3)
        payment = self.pay(profile, "1000")
        self.deactivate(profile.student)
        invoices_before = list(Invoice.objects.filter(profile=profile).values_list("pk", "status", "amount"))
        check = self.client_for(self.admin).get(f"{ARCHIVE}{profile.student_id}/restore-check/").data
        self.assertTrue(check["can_restore"])
        self.assertEqual([c["id"] for c in check["resumable_contracts"]], [profile.pk])
        self.assertFalse(check["needs_new_contract"])
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client_for(self.admin).post(f"{ARCHIVE}{profile.student_id}/restore/",
                                                        {"group": self.group_b.pk, "comment": "Вернулся"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        student = Student.objects.get(pk=profile.student_id)
        self.assertEqual((student.status, student.is_active, student.group_id),
                         (Student.Status.ACTIVE, True, self.group_b.pk))
        profile.refresh_from_db()
        self.assertEqual(profile.status, StudentBillingProfile.Status.ACTIVE)
        self.assertEqual(list(Invoice.objects.filter(profile=profile).values_list("pk", "status", "amount")),
                         invoices_before)
        self.assertEqual(list(StudentPayment.objects.filter(student=student).values_list("pk", flat=True)),
                         [payment.pk])
        self.assertEqual([e["type"] for e in response.data["status_history"]], ["reactivated", "deactivated"])
        # Ушёл из текущего архива, вернулся в активный список.
        self.assertIsNone(self.row(student))
        self.assertEqual(self.client_for(self.accountant).get(f"{ARCHIVE}statistics/").data["total"], 0)
        self.assertTrue(PayrollAuditLog.objects.filter(action="billing_student_restored", entity_id=student.pk).exists())
        # Повторное восстановление — конфликт, ничего не меняется.
        again = self.client_for(self.admin).post(f"{ARCHIVE}{student.pk}/restore/", {"group": self.group.pk},
                                                 format="json")
        self.assertEqual(again.status_code, 409)
        self.assertEqual(StudentStatusEvent.objects.filter(student=student, event_type="reactivated").count(), 1)

    def test_restore_without_resumable_contract_asks_for_new_contract(self):
        student = self.student()
        self.deactivate(student)
        check = self.client_for(self.accountant).get(f"{ARCHIVE}{student.pk}/restore-check/").data
        self.assertTrue(check["needs_new_contract"])
        self.assertIn("оформите новый договор", " ".join(check["warnings"]))

    def test_restore_requires_open_group(self):
        student = self.student()
        self.deactivate(student)
        self.group_b.status = "completed"
        self.group_b.save(update_fields=["status"])
        response = self.client_for(self.admin).post(f"{ARCHIVE}{student.pk}/restore/", {"group": self.group_b.pk},
                                                    format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Student.objects.get(pk=student.pk).status, Student.Status.WITHDRAWN)


class AccessTests(ArchiveFixture):
    def test_9_roles(self):
        profile = self.profile()
        self.deactivate(profile.student)
        url = f"{ARCHIVE}{profile.student_id}/"
        trainer = User.objects.get(username="trainer")
        teacher = make_user("teacher2")
        for user, code in ((self.accountant, 200), (self.director, 200), (self.admin, 200),
                           (self.manager, 403), (trainer, 403), (teacher, 403)):
            for path in (ARCHIVE, f"{ARCHIVE}statistics/", url):
                self.assertEqual(self.client_for(user).get(path).status_code, code, (user.username, path))
        # Статусами управляет администратор системы: бухгалтеру и директору — 403.
        for user in (self.accountant, self.director):
            response = self.client_for(user).post(f"{url}restore/", {"group": self.group.pk}, format="json")
            self.assertEqual(response.status_code, 403)
        self.assertEqual(Student.objects.get(pk=profile.student_id).status, Student.Status.WITHDRAWN)
        self.assertFalse(self.client_for(self.accountant).get(url).data["can_restore"])
        self.assertTrue(self.client_for(self.admin).get(url).data["can_restore"])

    def test_10_no_physical_delete(self):
        profile = self.profile()
        self.hold(2)
        self.pay(profile, "1000")
        self.deactivate(profile.student)
        student = Student.objects.get(pk=profile.student_id)
        with self.assertRaises(ValidationError):
            profile.delete()
        with self.assertRaises(ValidationError):
            self.invoices(profile)[0].delete()
        with self.assertRaises(ProtectedError):
            student.delete()
        self.assertTrue(Student.objects.filter(pk=student.pk).exists())
        self.assertEqual(Invoice.objects.filter(profile=profile).count(), 1)
        # API архива — только чтение.
        self.assertEqual(self.client_for(self.admin).delete(f"{ARCHIVE}{student.pk}/").status_code, 405)

    def test_11_repeated_deactivation_is_refused(self):
        profile = self.profile()
        self.hold(3)
        self.deactivate(profile.student)
        with self.assertRaises(ValidationError):
            self.deactivate(Student.objects.get(pk=profile.student_id), reason="financial_issues")
        response = self.client_for(self.manager).post(
            f"/api/v1/assistant/students/{profile.student_id}/deactivate/", {"reason": "relocation"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(StudentStatusEvent.objects.filter(student_id=profile.student_id,
                                                           event_type="deactivated").count(), 1)
        self.assertEqual(PayrollAuditLog.objects.filter(action="billing_student_archived",
                                                        entity_id=profile.student_id).count(), 1)
        self.assertEqual(self.row(profile.student)["finance"]["debt"], "4000.00")  # долг не задвоился


class StatisticsAndFilterTests(ArchiveFixture):
    def test_12_kpis_from_real_data(self):
        debtor = self.profile()
        payer = self.profile(student=self.student())
        self.hold(3)
        self.pay(debtor, "1000")
        self.pay(payer, "4000")
        self.deactivate(debtor.student, reason="financial_issues")
        self.deactivate(payer.student, reason="relocation")
        self.deactivate(self.student(), reason="unreachable")  # без договора
        active = self.profile(student=self.student())  # активный — не в архиве
        stats = self.client_for(self.accountant).get(f"{ARCHIVE}statistics/").data
        self.assertEqual(stats, {
            "total": 3, "debt_total": "3000.00", "with_debt": 1, "without_debt": 2,
            "paid_total": "5000.00", "overpayment_total": "0.00",
        })
        listing = self.client_for(self.accountant).get(ARCHIVE).data
        self.assertEqual(listing["statistics"], stats)
        self.assertNotIn(active.student_id, [r["id"] for r in listing["results"]])

    def test_filters(self):
        debtor = self.profile()
        payer = self.profile(student=self.student(group=self.group_b))
        self.hold(3)
        self.hold(3, group=self.group_b)
        self.pay(payer, "4000")
        self.deactivate(debtor.student, reason="financial_issues")
        self.deactivate(payer.student, reason="relocation", event_date=self.today - dt.timedelta(days=5))
        ids = lambda **p: [r["id"] for r in self.client_for(self.accountant).get(ARCHIVE, p).data["results"]]  # noqa: E731
        self.assertEqual(ids(debt="yes"), [debtor.student_id])
        self.assertEqual(ids(debt="no"), [payer.student_id])
        self.assertEqual(ids(reason="relocation"), [payer.student_id])
        self.assertEqual(ids(group=self.group_b.pk), [payer.student_id])
        self.assertEqual(ids(contract=str(debtor.pk)), [debtor.student_id])
        self.assertEqual(ids(search=debtor.student.first_name), [debtor.student_id])
        self.assertEqual(ids(date_to=(self.today - dt.timedelta(days=1)).isoformat()), [payer.student_id])
        self.assertEqual(sorted(ids(subject=self.it.pk)), sorted([debtor.student_id, payer.student_id]))
        self.assertEqual(self.client_for(self.accountant).get(ARCHIVE, {"date_from": "bad"}).status_code, 400)


class AssistantToAccountingSyncTests(ArchiveFixture):
    def test_assistant_deactivates_accounting_sees_it_immediately(self):
        """Ассистент деактивировал → бухгалтерия сразу видит студента в архиве
        с правильными деньгами; бухгалтеру ничего не нужно делать вручную."""
        profile = self.profile()
        self.hold(3)
        self.pay(profile, "1000")
        assistant = self.client_for(self.manager)
        preview = assistant.get(f"/api/v1/assistant/students/{profile.student_id}/deactivation-preview/")
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data["finance"]["due_now"], "3000.00")
        self.assertEqual(preview.data["group"]["id"], self.group.pk)
        self.assertEqual([c["id"] for c in preview.data["contracts"]], [profile.pk])
        self.assertIsNone(self.row(profile.student))
        with self.captureOnCommitCallbacks(execute=True):
            response = assistant.post(f"/api/v1/assistant/students/{profile.student_id}/deactivate/",
                                      {"reason": "self_withdrawal", "comment": "Решили уйти"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        row = self.row(profile.student)
        self.assertIsNotNone(row)
        self.assertEqual((row["reason"], row["deactivated_on"]), ("self_withdrawal", self.today.isoformat()))
        self.assertEqual(row["group"]["id"], self.group.pk)
        self.assertEqual((row["finance"]["invoiced"], row["finance"]["paid"], row["finance"]["debt"]),
                         ("4000.00", "1000.00", "3000.00"))
        detail = self.client_for(self.accountant).get(f"{ARCHIVE}{profile.student_id}/").data
        self.assertEqual(detail["deactivation"]["performed_by"]["id"], self.manager.pk)
        self.assertEqual(detail["deactivation"]["comment"], "Решили уйти")
        self.assertTrue(PayrollAuditLog.objects.filter(action="billing_student_archived",
                                                       entity_id=profile.student_id, actor=self.manager).exists())

    def test_other_reason_requires_comment(self):
        student = self.student()
        response = self.client_for(self.manager).post(f"/api/v1/assistant/students/{student.pk}/deactivate/",
                                                      {"reason": "other"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Student.objects.get(pk=student.pk).status, Student.Status.ACTIVE)

    def test_new_reasons_are_offered(self):
        options = self.client_for(self.manager).get("/api/v1/assistant/options/").data["deactivation_reasons"]
        values = [o["value"] for o in options]
        for reason in ("self_withdrawal", "financial_issues", "stopped_attending", "other_academy", "relocation",
                       "unreachable", "other"):
            self.assertIn(reason, values)

    def test_reactivated_via_assistant_leaves_archive(self):
        profile = self.profile()
        self.deactivate(profile.student)
        self.assertIsNotNone(self.row(profile.student))
        with self.captureOnCommitCallbacks(execute=True):
            reactivate_student(Student.objects.get(pk=profile.student_id), group=self.group, event_date=self.today,
                               performed_by=self.manager)
        self.assertIsNone(self.row(profile.student))
        # Карточка с историей по-прежнему открывается.
        detail = self.client_for(self.accountant).get(f"{ARCHIVE}{profile.student_id}/").data
        self.assertFalse(detail["student"]["is_archived"])
        self.assertEqual(len(detail["status_history"]), 2)


class ServiceTests(ArchiveFixture):
    def test_stop_preview_counts_not_started_months(self):
        profile = self.profile()
        self.pay(profile, "4000")
        # Первый месяц выставлен, но ни одного урока — при остановке аннулируется.
        preview = archive.stop_preview(profile.student)
        self.assertEqual(preview["live_contracts"], 1)
        self.assertEqual(preview["voided_on_stop"], "4000.00")
        self.assertEqual(Lesson.objects.count(), 0)
