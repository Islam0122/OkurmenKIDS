"""The four «Стипендии» admin pages: period cards, awards list, settings."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.urls import reverse

from apps.scholarships.models import ScholarshipConfiguration
from apps.scholarships.services.generation import approve_period, create_period

from .base import OCT_1, SEP_1, ScholarshipFixture

SEP_30 = dt.date(2026, 9, 30)


class AdminPagesFixture(ScholarshipFixture):
    def setUp(self):
        super().setUp()
        self.configure(require_complete_feedback=False, award_amount=Decimal("1500"))
        for index, name in enumerate(("Aibek", "Nurai")):
            student = self.student(name)
            self.study(student, self.python, self.t_python, attended=6 - index, missed=index)
        for index, name in enumerate(("Azamat", "Aidana", "Bakyt")):
            student = self.student(name, group=self.other_group)
            self.study(student, self.python, self.t_python, attended=6 - index, missed=index, group=self.other_group)
        self.first = create_period(
            period_start=SEP_1, period_end=SEP_30, max_recipients=1, groups=[self.group], today=OCT_1,
        )
        self.second = create_period(
            period_start=dt.date(2026, 8, 31), period_end=SEP_30, max_recipients=2,
            groups=[self.other_group], today=OCT_1,
        )
        self.web = self.client_class()
        self.web.force_login(self.admin)


class PeriodCardsTests(AdminPagesFixture):
    def test_each_card_lists_only_its_own_groups(self):
        response = self.web.get(reverse("admin:scholarships_scholarshipperiod_changelist"))
        groups = {p.pk: p.participating_groups for p in response.context["cl"].result_list}
        self.assertEqual(groups, {self.first.pk: ["Prog SOFT 1"], self.second.pk: ["Prog SOFT 2"]})
        self.assertContains(response, 'class="ok-per-row"', count=2)
        self.assertContains(response, 'title="Prog SOFT 1"')
        for column in ("Группы", "Стипендиаты", "Выплата", "Сумма"):
            self.assertContains(response, f"<th class=\"is-num\">{column}</th>" if column != "Выплата" else "<th>Выплата</th>")
        for removed in ("Оценено</th>", "Ожидают</th>"):
            self.assertNotContains(response, removed)
        # Every action lives in the one ⋮ menu of the row.
        for action in ("Открыть период", "Отчёт", "Редактировать"):
            self.assertContains(response, action)

    def test_status_filter_counts(self):
        approve_period(self.first, user=self.admin)
        response = self.web.get(reverse("admin:scholarships_scholarshipperiod_changelist"), {"status__exact": "draft"})
        self.assertEqual(response.context["status_counts"], {"all": 2, "draft": 1, "approved": 1})
        self.assertEqual([p.pk for p in response.context["cl"].result_list], [self.second.pk])


class AwardsPageTests(AdminPagesFixture):
    url = reverse("admin:scholarships_scholarshipaward_changelist")

    def test_summary_and_badges(self):
        approve_period(self.first, user=self.admin)
        response = self.web.get(self.url)
        self.assertEqual(response.context["summary"], {
            "total": 3, "paid": 0, "unpaid": 3, "awaiting_approval": 2,
            "accrued": Decimal("4500"), "paid_sum": None, "remaining": Decimal("4500"),
        })
        self.assertContains(response, "Не выдано")
        self.assertContains(response, "data-ok-pay-one", count=1)  # only the approved award can be paid
        self.assertContains(response, "Ждёт утверждения", count=2)
        self.assertContains(response, "4\u00a0500\u00a0сом")

    def test_filters(self):
        response = self.web.get(self.url, {"evaluation__group_name": "Prog SOFT 2"})
        self.assertEqual(response.context["summary"]["total"], 2)
        self.assertNotContains(response, "Aibek Test")

        response = self.web.get(self.url, {"period__id__exact": self.first.pk})
        self.assertEqual(response.context["summary"]["total"], 1)
        self.assertEqual(response.context["group_names"], ["Prog SOFT 1"])

        response = self.web.get(self.url, {"q": "zzz"})
        self.assertContains(response, "С выбранными фильтрами начислений нет")

    def test_empty_filter_fields_are_dropped(self):
        response = self.web.get(self.url, {"period__id__exact": "", "status__exact": "pending", "q": ""})
        self.assertRedirects(response, f"{self.url}?status__exact=pending")


class SettingsPageTests(ScholarshipFixture):
    def setUp(self):
        super().setUp()
        self.web = self.client_class()
        self.web.force_login(self.admin)
        self.url = reverse("admin:scholarships_scholarshipconfiguration_change", args=[self.config.pk])

    def data(self, **overrides):
        config = self.config
        data = {
            "name": config.name, "is_active": "on", "award_mode": config.award_mode,
            "max_recipients": config.max_recipients, "award_amount": "2500",
            "attendance_weight": "0.50", "homework_weight": "0.30", "feedback_weight": "0.20",
            "subject_aggregation": config.subject_aggregation, "late_homework_credit": "0.50",
            "min_overall_score": "10", "min_marked_lessons": "2", "_continue": "1",
        }
        data.update(overrides)
        return data

    def test_list_and_form(self):
        listing = self.web.get(reverse("admin:scholarships_scholarshipconfiguration_changelist"))
        self.assertContains(listing, "Активна")
        self.assertContains(listing, "Открыть настройки")
        page = self.web.get(self.url)
        for title in ("Настройки периода", "Настройки начислений", "Формула рейтинга", "Ограничения", "Правила расчёта"):
            self.assertContains(page, title)
        self.assertContains(page, "Сохранить изменения")

    def test_save(self):
        response = self.web.post(self.url, self.data())
        self.assertRedirects(response, self.url)
        config = ScholarshipConfiguration.objects.get(pk=self.config.pk)
        self.assertEqual((config.award_amount, config.attendance_weight, config.min_marked_lessons), (Decimal("2500"), Decimal("0.50"), 2))
        self.assertFalse(config.require_complete_feedback)

    def test_weights_error_is_shown(self):
        response = self.web.post(self.url, self.data(feedback_weight="0.50"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Сумма весов должна быть равна 1.00")
