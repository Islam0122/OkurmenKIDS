"""Django Admin → «Удалить профиль из бухгалтерии» (сценарий Jasmina
Karimberdieva): только суперпользователь; удаляются лишь записи профиля;
данные обучения, другие ученики и журнал аудита сохраняются; проведённые
платежи и связи с чужими профилями останавливают удаление."""
from __future__ import annotations

import datetime as dt

from django.contrib.auth.models import Permission
from django.test import Client

from apps.academy.models import Attendance, Group, GroupTeacher, Lesson, Student
from apps.accounting.models import PayrollAuditLog, StudentPayment
from apps.accounting.services.maintenance import other_app_counts
from apps.billing.models import (
    CreditLedgerEntry,
    Invoice,
    LessonConsumption,
    LessonPackage,
    PaymentAllocation,
    PaymentReplacement,
    Receipt,
    StudentBillingProfile,
)
from apps.billing.services import BillingError, contracts, payments, profile_purge
from apps.billing.services.prepayments import prepayments
from apps.billing.services.reports import dashboard, reconcile
from apps.billing.tests.base import make_user
from apps.billing.tests.test_periods import OCT24, PeriodFixture
from apps.users.models import User

AUG19, SEP1 = dt.date(2026, 8, 19), dt.date(2026, 9, 1)
LIST = "/admin/billing/studentbillingprofile/"


class PurgeFixture(PeriodFixture):
    def setUp(self):
        super().setUp()
        self.jasmina = Student.objects.create(first_name="Jasmina", last_name="Karimberdieva", group=self.group,
                                              enrollment_date=self.start, parent_phone="+996700000001")
        self.at(AUG19)
        self.profile = self.contract(student=self.jasmina, start_date=SEP1, discount_enabled=True,
                                     final_course_price="38000", discount_reason="Скидка")
        self.payment = self.pay(self.profile, "38000", on=AUG19)
        self.other = self.contract(start_date=SEP1)  # другой ученик той же группы — с реальными деньгами
        self.at(OCT24)
        self.other_payment = self.pay(self.other, "15000", on=SEP1)
        self.lessons = self.it_lessons(12)
        self.mark(self.lessons[0], self.jasmina, Attendance.Status.PRESENT)
        self.staff = make_user("staffadmin", User.Role.ADMIN, is_staff=True)
        self.staff.user_permissions.set(Permission.objects.all())  # любые разрешения — не суперпользователь

    def client_as(self, user) -> Client:
        client = Client()
        client.force_login(user)
        return client

    def url(self, profile=None) -> str:
        return f"{LIST}{(profile or self.profile).pk}/purge/"

    def void(self):
        payments.reverse_payment(self.payment, actor=self.accountant, reason="Ошибочный учёт — начинаем заново")

    def education(self) -> dict:
        student = Student.objects.filter(pk=self.jasmina.pk).values().get()
        return {
            "student": student, "group": Group.objects.filter(pk=self.group.pk).values().get(),
            "lessons": sorted(Lesson.objects.values_list("pk", "status", "date")),
            "attendance": sorted(Attendance.objects.values_list("lesson_id", "student_id", "status")),
            "programs": GroupTeacher.objects.count(), "other_modules": other_app_counts(),
        }

    def other_money(self) -> dict:
        self.other.refresh_from_db()
        s = contracts.money_summary(self.other)
        return {k: s[k] for k in ("received", "allocated", "credit", "invoiced", "due_now")}

    def owned(self) -> dict:
        p = self.profile.pk
        return {
            "profile": StudentBillingProfile.objects.filter(pk=p).count(),
            "packages": LessonPackage.objects.filter(profile_id=p).count(),
            "consumptions": LessonConsumption.objects.filter(profile_id=p).count(),
            "invoices": Invoice.objects.filter(profile_id=p).count(),
            "allocations": PaymentAllocation.objects.filter(profile_id=p).count(),
            "ledger": CreditLedgerEntry.objects.filter(profile_id=p).count(),
            "receipts": Receipt.objects.filter(profile_id=p).count(),
            "payments": StudentPayment.objects.filter(billing_profile_id=p).count(),
        }


class AccessTests(PurgeFixture):
    def test_only_superuser_sees_action_and_opens_page(self):
        root = self.client_as(self.admin)
        self.assertContains(root.get(LIST), "Удалить профиль из бухгалтерии")
        self.assertContains(root.get(self.url()), "Будет удалён бухгалтерский профиль ученика")
        response = root.post(LIST, {"action": "delete_from_billing", "_selected_action": [self.profile.pk]})
        self.assertRedirects(response, self.url(), fetch_redirect_response=False)

    def test_everyone_else_is_refused_on_every_path(self):
        before = self.owned()
        staff_users = [self.staff]
        for role in (User.Role.ACCOUNTANT, User.Role.DIRECTOR, User.Role.ASSISTANT, User.Role.ADMIN):
            user = make_user(f"staff_{role}", role, is_staff=True)
            user.user_permissions.set(Permission.objects.filter(content_type__app_label__in=("billing", "accounting")))
            staff_users.append(user)
        body = {"fingerprint": "x", "reason": "попытка", "last_name": "Karimberdieva"}
        for user in staff_users:
            client = self.client_as(user)
            listing = client.get(LIST)  # список — 403 или без действия
            self.assertTrue(listing.status_code == 403 or "Удалить профиль из бухгалтерии" not in listing.content.decode())
            for response in (client.get(self.url()), client.post(self.url(), body)):
                # 403 — проверка суперпользователя; 302 — роль LMS не пускается в админку вообще.
                self.assertIn(response.status_code, (302, 403), user)
                self.assertNotIn("Подтверждение", response.content.decode())
            if user.role not in (User.Role.DIRECTOR, User.Role.ASSISTANT):
                self.assertEqual(client.get(self.url()).status_code, 403, user)
            action = client.post(LIST, {"action": "delete_from_billing", "_selected_action": [self.profile.pk]})
            self.assertFalse(action.get("Location", "").endswith("/purge/"))
        for user in (self.accountant, self.director, self.manager):  # роли без is_staff — в админку не входят
            client = self.client_as(user)
            self.assertIn(client.get(self.url()).status_code, (302, 403), user)
            self.assertIn(client.post(self.url(), body).status_code, (302, 403), user)
        inactive = User.objects.create_superuser(username="oldroot", email="o@okurmen.kg", password="Str0ngPassw0rd!")
        inactive.is_active = False
        inactive.save()
        for actor in (*staff_users, self.accountant, self.director, self.manager, inactive, None):
            with self.assertRaises(BillingError) as ctx:
                profile_purge.purge(self.profile, actor=actor, reason="x")
            self.assertEqual(ctx.exception.code, "forbidden")
            with self.assertRaises(BillingError):
                profile_purge.preview(self.profile, actor=actor)
        self.assertEqual(self.owned(), before)  # ничего не удалено


class SafetyTests(PurgeFixture):
    def test_confirmed_payment_blocks_and_lists_real_money(self):
        report = profile_purge.preview(self.profile, actor=self.admin)
        self.assertFalse(report["can_delete"])
        self.assertEqual([p["id"] for p in report["real_money"]], [self.payment.pk])
        self.assertEqual(report["real_money"][0]["receipt"], self.payment.receipt.number)
        page = self.client_as(self.admin).get(self.url())
        self.assertContains(page, "Обычное удаление остановлено: проведённые платежи")
        self.assertFalse(page.context["report"]["can_delete"])  # обычная форма не показывается
        self.assertNotContains(page, "Подтверждение</span>")
        # Обычная форма удаления, отправленная напрямую, проведённый платёж не удаляет.
        body = {"fingerprint": page.context["report"]["fingerprint"], "reason": "x", "last_name": "Karimberdieva"}
        self.client_as(self.admin).post(self.url(), body)
        self.assertTrue(StudentPayment.objects.filter(pk=self.payment.pk, status="confirmed").exists())
        with self.assertRaises(BillingError) as ctx:
            profile_purge.purge(self.profile, actor=self.admin, reason="x")
        self.assertEqual(ctx.exception.code, "real_money")
        self.assertEqual(self.owned()["profile"], 1)

    def test_link_to_another_profile_blocks(self):
        self.void()
        PaymentReplacement.objects.create(original=self.payment, replacement=self.other_payment, reason="ошибка связи")
        report = profile_purge.preview(self.profile, actor=self.admin)
        self.assertFalse(report["can_delete"])
        self.assertTrue(any("другого профиля" in f or "ссылается" in f for f in report["foreign"]))
        with self.assertRaises(BillingError) as ctx:
            profile_purge.purge(self.profile, actor=self.admin, reason="x")
        self.assertEqual(ctx.exception.code, "foreign")
        self.assertTrue(StudentPayment.objects.filter(pk=self.other_payment.pk).exists())

    def test_stale_preview_and_wrong_name_change_nothing(self):
        self.void()
        client = self.client_as(self.admin)
        fp = profile_purge.preview(self.profile, actor=self.admin)["fingerprint"]
        self.assertContains(client.post(self.url(), {"fingerprint": fp, "reason": "x", "last_name": "Other"}),
                            "Фамилия не совпадает")
        client.post(self.url(), {"fingerprint": "stale", "reason": "x", "last_name": "Karimberdieva"})
        self.assertEqual(self.owned()["profile"], 1)


class PurgeTests(PurgeFixture):
    def test_deletes_only_billing_and_keeps_education_others_and_audit(self):
        self.void()
        education, other_money = self.education(), self.other_money()
        other_rows = Invoice.objects.filter(profile=self.other).count()
        audit_before = PayrollAuditLog.objects.count()
        client = self.client_as(self.admin)
        report = client.get(self.url()).context["report"]
        self.assertTrue(report["can_delete"])
        labels = {r["label"] for r in report["rows"]}
        self.assertTrue({"billing.StudentBillingProfile", "billing.Invoice", "billing.LessonPackage",
                         "billing.LessonConsumption", "billing.CreditLedgerEntry", "billing.Receipt",
                         "accounting.StudentPayment"} <= labels)
        self.assertNotIn("academy.Student", labels)
        response = client.post(self.url(), {"fingerprint": report["fingerprint"], "reason": "Ошибочно создан",
                                            "last_name": "karimberdieva"})
        self.assertRedirects(response, LIST, fetch_redirect_response=False)

        self.assertEqual(set(self.owned().values()), {0})  # бухгалтерии профиля нет
        self.assertContains(client.get(LIST), "удалён из бухгалтерии")  # сообщение об успехе
        self.assertNotContains(client.get(LIST), "Karimberdieva")  # в списке профилей её больше нет
        self.assertEqual(self.education(), education)  # ученик, группа, уроки, посещаемость, все модули LMS
        self.assertEqual(self.other_money(), other_money)
        self.assertEqual(Invoice.objects.filter(profile=self.other).count(), other_rows)
        self.assertEqual(reconcile(), [])
        self.assertNotIn(self.jasmina.pk, [r["student"] for r in prepayments({})["results"]])
        self.assertEqual(dashboard({})["prepayment_total"], str(prepayments({})["summary"]["prepayment"]))
        # Журнал аудита сохранён + одна запись об удалении с полной копией строк.
        self.assertEqual(PayrollAuditLog.objects.count(), audit_before + 1)
        entry = PayrollAuditLog.objects.get(action=profile_purge.ACTION)
        self.assertEqual((entry.entity_id, entry.actor_id, entry.reason), (self.profile.pk, self.admin.pk, "Ошибочно создан"))
        self.assertEqual(entry.old_values["rows"]["accounting.StudentPayment"][0]["pk"], self.payment.pk)
        self.assertEqual(entry.new_values["student"], self.jasmina.pk)

    def test_new_clean_profile_can_be_created_after_purge(self):
        self.void()
        profile_purge.purge(self.profile, actor=self.admin, reason="Начать учёт заново")
        fresh = self.contract(student=self.jasmina, start_date=SEP1, discount_enabled=True,
                              final_course_price="38000", discount_reason="Скидка подтверждена")
        s = contracts.money_summary(fresh)
        self.assertEqual((fresh.final_course_price, fresh.discount_amount, s["received"], s["voided"]),
                         (38000, 22000, 0, 0))
        self.assertEqual(LessonConsumption.objects.filter(profile=fresh).count(), 12)  # уроки — в новый профиль
        self.assertTrue(Student.objects.filter(pk=self.jasmina.pk, group=self.group).exists())
