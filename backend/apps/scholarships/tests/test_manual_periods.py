"""Manual scholarship periods, the per-period student limit (incl. «без
ограничения») and adding/removing recipients by hand."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest import mock

from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from apps.scholarships.models import ScholarshipAward, ScholarshipPeriod, ScholarshipRunLog
from apps.scholarships.services.generation import (
    add_award,
    approve_period,
    create_period,
    recalculate_period,
    remove_award,
    run_schedule,
    update_period,
)

from .base import OCT_1, SEP_1, ScholarshipFixture

SEP_30 = dt.date(2026, 9, 30)


class ManualPeriodFixture(ScholarshipFixture):
    def setUp(self):
        super().setUp()
        self.configure(require_complete_feedback=False, award_amount=Decimal("2500"))
        self.students = []
        for index, name in enumerate(["Aibek", "Nurai", "Azamat", "Aidana"]):
            student = self.student(name)
            # Different attendance → a strict ranking Aibek > Nurai > Azamat > Aidana.
            self.study(student, self.python, self.t_python, attended=8 - index, missed=index)
            self.students.append(student)

    def create(self, limit=2, **kwargs):
        kwargs.setdefault("today", OCT_1)
        return create_period(period_start=SEP_1, period_end=SEP_30, max_recipients=limit, **kwargs)

    def winners(self, period):
        return sorted(period.awards.values_list("evaluation__student_name", flat=True))


class CreatePeriodTests(ManualPeriodFixture):
    def test_ended_period_is_calculated_with_its_limit(self):
        period = self.create(limit=2, title="Стипендия")
        self.assertTrue(period.is_manual)
        self.assertEqual(period.evaluation_date, OCT_1)
        self.assertEqual(period.title, "Стипендия")
        self.assertEqual(str(period), "Стипендия 01.09.2026 — 30.09.2026")
        self.assertEqual(period.evaluations.count(), 4)
        self.assertEqual(self.winners(period), ["Aibek Test", "Nurai Test"])
        self.assertEqual(period.awards.first().amount, Decimal("2500"))

    def test_limits_10_20_30_cap_the_recipients(self):
        for index in range(26):
            student = self.student(f"S{index:02d}")
            self.study(student, self.english, self.t_english, attended=4)
        for number, limit in enumerate((10, 20, 30)):
            period = create_period(
                period_start=SEP_1 + dt.timedelta(days=0), period_end=SEP_30 - dt.timedelta(days=number),
                max_recipients=limit, today=OCT_1,
            )
            self.assertEqual(period.awards.count(), min(limit, period.evaluations.filter(eligibility_status="eligible").count()))
            self.assertLessEqual(period.awards.count(), limit)
        self.assertEqual(ScholarshipPeriod.objects.get(max_recipients=30).awards.count(), 30)

    def test_unlimited_awards_every_eligible_student(self):
        period = self.create(limit=None)
        self.assertTrue(period.is_unlimited)
        self.assertEqual(period.awards.count(), 4)

    def test_running_period_waits_for_its_end(self):
        period = self.create(today=dt.date(2026, 9, 20))
        self.assertFalse(period.is_calculated)
        self.assertEqual(period.evaluations.count(), 0)
        with self.assertRaisesMessage(ValidationError, "Период ещё идёт"):
            recalculate_period(period, today=dt.date(2026, 9, 20))
        with self.assertRaisesMessage(ValidationError, "ещё не рассчитан"):
            approve_period(period)

        # The daily schedule calculates it once it has ended.
        run_schedule(today=OCT_1)
        period.refresh_from_db()
        self.assertTrue(period.is_calculated)
        self.assertEqual(period.awards.count(), 2)

    def test_validation(self):
        with self.assertRaisesMessage(ValidationError, "не может быть раньше даты начала"):
            create_period(period_start=SEP_30, period_end=SEP_1, max_recipients=5, today=OCT_1)
        with self.assertRaisesMessage(ValidationError, "больше 0"):
            create_period(period_start=SEP_1, period_end=SEP_30, max_recipients=0, today=OCT_1)
        self.create()
        with self.assertRaisesMessage(ValidationError, "уже существует"):
            self.create()
        self.assertEqual(ScholarshipPeriod.objects.count(), 1)
        self.assertTrue(ScholarshipRunLog.objects.filter(result=ScholarshipRunLog.Result.FAILED).exists())


class UpdatePeriodTests(ManualPeriodFixture):
    def test_title_and_limit(self):
        period = self.create(limit=2)
        period = update_period(period, title="Осенняя стипендия", max_recipients=3)
        self.assertEqual((period.title, period.max_recipients), ("Осенняя стипендия", 3))
        # Raising the limit adds nobody by itself…
        self.assertEqual(period.awards.count(), 2)
        # …a recalculation fills it.
        recalculate_period(period, today=OCT_1)
        self.assertEqual(period.awards.count(), 3)
        period = update_period(period, max_recipients=None)
        self.assertTrue(period.is_unlimited)

    def test_limit_cannot_drop_below_current_recipients(self):
        period = self.create(limit=3)
        with self.assertRaisesMessage(ValidationError, "лимит не может быть меньше"):
            update_period(period, max_recipients=2)
        remove_award(period, period.awards.order_by("-rank").first())
        self.assertEqual(update_period(period, max_recipients=2).max_recipients, 2)

    def test_dates_editable_only_before_calculation(self):
        running = create_period(period_start=SEP_1, period_end=dt.date(2026, 10, 31), max_recipients=5, today=OCT_1)
        running = update_period(running, period_end=dt.date(2026, 10, 15))
        self.assertEqual(running.evaluation_date, dt.date(2026, 10, 16))
        with self.assertRaisesMessage(ValidationError, "не может быть раньше"):
            update_period(running, period_end=dt.date(2026, 8, 1))

        calculated = self.create()
        with self.assertRaisesMessage(ValidationError, "только до расчёта"):
            update_period(calculated, period_start=dt.date(2026, 9, 2))

        cycle = self.generate()
        with self.assertRaisesMessage(ValidationError, "автоматического цикла"):
            update_period(cycle, period_end=dt.date(2026, 9, 29))

    def test_approved_period_limit_is_locked(self):
        period = self.create()
        approve_period(period)
        with self.assertRaisesMessage(ValidationError, "утверждённого"):
            update_period(period, max_recipients=10)
        self.assertEqual(update_period(period, title="Итог").title, "Итог")


class AwardLimitTests(ManualPeriodFixture):
    def test_cannot_exceed_limit(self):
        period = self.create(limit=2)
        outside = period.evaluations.get(student=self.students[2])
        with self.assertRaisesMessage(ValidationError, "Лимит стипендиатов достигнут: 2 из 2."):
            add_award(period, outside)
        self.assertEqual(period.awards.count(), 2)

        # Remove one → room for the next.
        remove_award(period, period.awards.get(student=self.students[1]))
        award = add_award(period, outside)
        self.assertEqual(award.rank, outside.rank)
        self.assertEqual(self.winners(period), ["Aibek Test", "Azamat Test"])

    def test_raising_the_limit_makes_room(self):
        period = self.create(limit=2)
        update_period(period, max_recipients=3)
        add_award(period, period.evaluations.get(student=self.students[2]))
        self.assertEqual(period.awards.count(), 3)

    def test_unlimited_never_blocks(self):
        period = self.create(limit=None)
        remove_award(period, period.awards.get(student=self.students[3]))
        add_award(period, period.evaluations.get(student=self.students[3]))
        self.assertEqual(period.awards.count(), 4)

    def test_refusals(self):
        period = self.create(limit=4)
        winner = period.evaluations.get(student=self.students[0])
        with self.assertRaisesMessage(ValidationError, "уже получает"):
            add_award(period, winner)

        late = self.student("Late", enrolled=dt.date(2026, 9, 10))
        self.study(late, self.python, self.t_python)
        recalculate_period(period, today=OCT_1)
        with self.assertRaisesMessage(ValidationError, "не допущен"):
            add_award(period, period.evaluations.get(student=late))

        approve_period(period)
        with self.assertRaisesMessage(ValidationError, "утверждён"):
            remove_award(period, period.awards.first())

    def test_award_from_other_period_is_refused(self):
        period = self.create(limit=1)
        other = create_period(period_start=SEP_1, period_end=dt.date(2026, 9, 29), max_recipients=1, today=OCT_1)
        with self.assertRaisesMessage(ValidationError, "не относится"):
            add_award(period, other.evaluations.get(student=self.students[1]))
        with self.assertRaisesMessage(ValidationError, "не найдена"):
            remove_award(period, other.awards.get())


class PeriodAPITests(ManualPeriodFixture):
    def setUp(self):
        super().setUp()
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def test_create_edit_and_manage_recipients(self):
        with mock.patch("django.utils.timezone.localdate", return_value=OCT_1):
            response = self.api.post(reverse("scholarship-period-list"), {
                "title": "Стипендия", "period_start": "2026-09-01", "period_end": "2026-09-30", "max_recipients": 2,
            }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        data = response.data
        self.assertEqual((data["title"], data["recipients_count"], data["max_recipients"]), ("Стипендия", 2, 2))
        self.assertTrue(data["is_manual"])
        self.assertEqual(Decimal(data["total_amount"]), Decimal("5000"))
        pk = data["id"]

        evaluation = ScholarshipPeriod.objects.get(pk=pk).evaluations.get(student=self.students[2])
        response = self.api.post(reverse("scholarship-period-add-award", args=[pk]), {"evaluation": evaluation.pk})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Лимит стипендиатов достигнут: 2 из 2.", str(response.data))

        response = self.api.patch(reverse("scholarship-period-detail", args=[pk]), {"max_recipients": None}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["is_unlimited"])

        response = self.api.post(reverse("scholarship-period-add-award", args=[pk]), {"evaluation": evaluation.pk})
        self.assertEqual(response.status_code, 201, response.data)
        award_id = response.data["id"]
        response = self.api.delete(reverse("scholarship-period-remove-award", args=[pk, award_id]))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(ScholarshipAward.objects.filter(pk=award_id).exists())

    def test_create_validation(self):
        url = reverse("scholarship-period-list")
        response = self.api.post(url, {"period_start": "2026-09-30", "period_end": "2026-09-01", "max_recipients": 5}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("period_end", response.data)
        response = self.api.post(url, {"period_start": "2026-09-01", "period_end": "2026-09-30", "max_recipients": 0}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("max_recipients", response.data)

    def test_teacher_cannot_create_or_edit(self):
        period = self.create()
        teacher = APIClient()
        teacher.force_authenticate(self.t_python.user)
        response = teacher.post(reverse("scholarship-period-list"), {
            "period_start": "2026-08-01", "period_end": "2026-08-31", "max_recipients": 5,
        }, format="json")
        self.assertEqual(response.status_code, 403)
        response = teacher.patch(reverse("scholarship-period-detail", args=[period.pk]), {"title": "x"}, format="json")
        self.assertEqual(response.status_code, 403)
        listing = teacher.get(reverse("scholarship-period-list")).json()["results"][0]
        self.assertEqual(listing["title"], "Стипендия")
        self.assertNotIn("max_recipients", listing)


class PeriodAdminPanelTests(ManualPeriodFixture):
    def setUp(self):
        super().setUp()
        self.web = self.client_class()
        self.web.force_login(self.admin)

    def test_create_period_from_admin(self):
        url = reverse("admin:scholarships_create")
        self.assertContains(self.web.get(url), "Создать период")
        with mock.patch("django.utils.timezone.localdate", return_value=OCT_1):
            response = self.web.post(url, {
                "title": "Стипендия", "period_start": "2026-09-01", "period_end": "2026-09-30",
                "limit_enabled": "on", "max_recipients": "2",
            })
        period = ScholarshipPeriod.objects.get()
        self.assertRedirects(response, reverse("admin:scholarships_scholarshipperiod_change", args=[period.pk]),
                             fetch_redirect_response=False)
        self.assertEqual(period.awards.count(), 2)

    def test_create_form_validation(self):
        url = reverse("admin:scholarships_create")
        response = self.web.post(url, {"title": "Стипендия", "period_start": "2026-09-30", "period_end": "2026-09-01",
                                       "limit_enabled": "on", "max_recipients": "0"})
        self.assertContains(response, "Дата окончания не может быть раньше даты начала.")
        self.assertContains(response, "Количество студентов должно быть больше 0.")
        response = self.web.post(url, {"title": "Стипендия", "period_start": "2026-09-01", "period_end": "2026-09-30",
                                       "limit_enabled": "on", "max_recipients": ""})
        self.assertContains(response, "Укажите количество стипендиатов")
        self.assertFalse(ScholarshipPeriod.objects.exists())

    def test_unlimited_from_admin(self):
        with mock.patch("django.utils.timezone.localdate", return_value=OCT_1):
            self.web.post(reverse("admin:scholarships_create"), {
                "title": "Стипендия", "period_start": "2026-09-01", "period_end": "2026-09-30", "max_recipients": "20",
            })
        period = ScholarshipPeriod.objects.get()
        self.assertIsNone(period.max_recipients)
        self.assertEqual(period.awards.count(), 4)

    def test_cards_dashboard_and_report(self):
        period = self.create(limit=2)
        cards = self.web.get(reverse("admin:scholarships_scholarshipperiod_changelist"))
        self.assertContains(cards, "01.09.2026 — 30.09.2026")
        self.assertContains(cards, "Открыть")
        self.assertContains(cards, "5 000 сом")

        dashboard = self.web.get(reverse("admin:scholarships_scholarshipperiod_change", args=[period.pk]))
        self.assertContains(dashboard, "Лимит стипендиатов достигнут: 2 из 2.")
        self.assertContains(dashboard, "Azamat Test")
        self.assertContains(dashboard, "disabled title=\"Лимит стипендиатов достигнут: 2 из 2.\"")
        awarded_only = self.web.get(reverse("admin:scholarships_scholarshipperiod_change", args=[period.pk]), {"show": "awarded"})
        self.assertNotContains(awarded_only, "Azamat Test")

        report = self.web.get(reverse("admin:scholarships_report"), {"period": period.pk})
        self.assertContains(report, "Всего студентов")
        self.assertContains(report, "Выбрано стипендиатов")

        self.assertEqual(self.web.get(reverse("admin:scholarships_edit", args=[period.pk])).status_code, 200)

    def test_add_and_remove_recipient_from_admin(self):
        period = self.create(limit=2)
        outside = period.evaluations.get(student=self.students[2])
        add_url = reverse("admin:scholarships_award_add", args=[period.pk])

        response = self.web.post(add_url, {"evaluation": outside.pk}, follow=True)
        self.assertContains(response, "Лимит стипендиатов достигнут: 2 из 2.")
        self.assertEqual(period.awards.count(), 2)

        award = period.awards.get(student=self.students[1])
        self.web.post(reverse("admin:scholarships_award_remove", args=[period.pk, award.pk]))
        self.web.post(add_url, {"evaluation": outside.pk, "show": "awarded"})
        self.assertEqual(self.winners(period), ["Aibek Test", "Azamat Test"])

    def test_edit_limit_from_admin(self):
        period = self.create(limit=3)
        url = reverse("admin:scholarships_edit", args=[period.pk])
        response = self.web.post(url, {"title": "Стипендия", "limit_enabled": "on", "max_recipients": "2"})
        self.assertContains(response, "лимит не может быть меньше")
        response = self.web.post(url, {"title": "Новая", "limit_enabled": "on", "max_recipients": "10"})
        self.assertEqual(response.status_code, 302)
        period.refresh_from_db()
        self.assertEqual((period.title, period.max_recipients), ("Новая", 10))
        # Dates of a calculated period are locked — posted values are ignored.
        self.assertEqual(period.period_start, SEP_1)
