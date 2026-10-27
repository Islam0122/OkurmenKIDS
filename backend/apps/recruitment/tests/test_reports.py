"""Главная HR, ежедневный и периодический отчёты, CSV: показатели считаются
по событиям периода из базы, недостоверные — не выводятся."""
from __future__ import annotations

from apps.recruitment.models import Vacancy

from .base import RecruitmentFixture, at, frozen


class ReportsFixture(RecruitmentFixture):
    def setUp(self):
        super().setUp()
        # 20.10: два отклика с сайта, один — HR; первичный отбор, собеседование.
        self.a = self.app_from_site(moment=at(20, 9))
        self.b = self.app_from_site(moment=at(20, 11), email="b@mail.kg", phone="+996 700 000 001",
                                    full_name="Садыкова Айгерим")
        self.c = self.new_application(moment=at(20, 12), first_name="Нурлан", phone="+996 700 000 002",
                                      email="n@mail.kg", vacancy=None, position="SMM", source="referral")
        self.move(self.a, "screening", "shortlisted", moment=at(20, 14))
        self.interview = self.schedule(self.a, at(21, 15), now=at(20, 15)).data
        self.move(self.b, "rejected", moment=at(20, 16))

    def app_from_site(self, moment, **over):
        from apps.recruitment.models import Application

        number = self.apply(moment=moment, **over).data["number"]
        return Application.objects.get(number=number).pk


class DailyReportTests(ReportsFixture):
    def test_counts_events_of_the_day(self):
        with frozen(at(20, 18)):
            r = self.get("reports/daily/", {"date": "2026-10-20"}).data
        self.assertEqual(r["new_applications"], 3)
        self.assertEqual(r["new_by_vacancy"], [{"label": "Менеджер по продажам", "count": 2},
                                               {"label": "SMM", "count": 1}])
        self.assertEqual(r["passed_screening"], 1)
        self.assertEqual(r["interviews_scheduled"], 1)
        self.assertEqual(r["interviews_planned"], 0)  # встреча — 21-го
        self.assertEqual((r["decisions"], r["rejected"], r["hired"], r["offers"]), (1, 1, 0, 0))
        self.assertIn("new_applications", r["definitions"])

        self.result(self.interview["id"], at(21, 16))
        r = self.get("reports/daily/", {"date": "2026-10-21"}).data
        self.assertEqual((r["new_applications"], r["interviews_planned"], r["interviews_conducted"]), (0, 1, 1))
        self.assertEqual((r["decisions"], r["offers"]), (1, 1))

    def test_rescheduled_cancelled_no_show(self):
        with frozen(at(20, 17)):
            moved = self.patch(f"interviews/{self.interview['id']}/", {"scheduled_at": at(22, 10).isoformat()}).data
        second = self.schedule(self.c["id"], at(21, 11), now=at(20, 17)).data
        with frozen(at(20, 18)):
            self.post(f"interviews/{second['id']}/cancel/", {"reason": "Перенос по просьбе"})
        with frozen(at(22, 12)):
            self.post(f"interviews/{moved['id']}/no-show/")
        day20 = self.get("reports/daily/", {"date": "2026-10-20"}).data
        self.assertEqual((day20["interviews_rescheduled"], day20["interviews_cancelled"]), (1, 1))
        day22 = self.get("reports/daily/", {"date": "2026-10-22"}).data
        self.assertEqual((day22["interviews_no_show"], day22["interviews_conducted"]), (1, 0))

    def test_filters(self):
        r = self.get("reports/daily/", {"date": "2026-10-20", "vacancy": self.vacancy["id"]}).data
        self.assertEqual(r["new_applications"], 2)
        r = self.get("reports/daily/", {"date": "2026-10-20", "source": "referral"}).data
        self.assertEqual(r["new_applications"], 1)
        r = self.get("reports/daily/", {"date": "2026-10-20", "responsible": self.interviewer.pk}).data
        self.assertEqual(r["new_applications"], 0)
        self.assertEqual(self.get("reports/daily/", {"date": "20-10-2026"}).status_code, 400)


class MonthlyReportTests(ReportsFixture):
    def test_month(self):
        self.result(self.interview["id"], at(21, 16))
        with frozen(at(21, 17)):
            self.post(f"applications/{self.a}/hire/", {"username": "bakyt", "email": "bakyt@mail.kg", "role": "rop",
                                                       "password": "Str0ngPassw0rd!",
                                                       "password_confirm": "Str0ngPassw0rd!"})
        with frozen(at(25)):
            self.publish(self.vacancy["id"], "closed")
        r = self.get("reports/monthly/", {"month": "2026-10"}).data
        self.assertEqual((r["new_applications"], r["interviews_conducted"], r["hired"], r["rejected"], r["offers"]),
                         (3, 1, 1, 1, 1))
        funnel = {row["status"]: row["count"] for row in r["funnel"]}
        self.assertEqual((funnel["new"], funnel["screening"], funnel["interview_scheduled"], funnel["offer"],
                          funnel["hired"]), (3, 1, 1, 1, 1))
        self.assertEqual(r["funnel"][1]["conversion_percent"], 33.3)
        self.assertEqual(r["average_days_to_hire"], 1.0)
        self.assertEqual(r["vacancies_closed"], 1)
        self.assertEqual(r["vacancy_days_to_close"], 24.0)
        sales = next(row for row in r["by_vacancy"] if row["label"] == "Менеджер по продажам")
        self.assertEqual((sales["applications"], sales["interviews"], sales["hired"], sales["rejected"]), (2, 1, 1, 1))
        site = next(row for row in r["by_source"] if row["source"] == "company_site")
        # Двух откликов мало для вывода об эффективности источника.
        self.assertEqual((site["count"], site["enough_data"], site["hired_percent"]), (2, False, None))
        self.assertTrue(r["stage_durations"])
        self.assertEqual(self.get("reports/monthly/", {"month": "2026-09"}).data["new_applications"], 0)

    def test_custom_period_and_validation(self):
        r = self.get("reports/monthly/", {"date_from": "2026-10-20", "date_to": "2026-10-20"}).data
        self.assertEqual((r["date_from"], r["date_to"], r["new_applications"]), ("2026-10-20", "2026-10-20", 3))
        self.assertEqual(self.get("reports/monthly/", {"date_from": "2026-10-21", "date_to": "2026-10-20"}).status_code,
                         400)
        self.assertEqual(self.get("reports/monthly/", {"date_from": "2025-01-01", "date_to": "2026-10-20"}).status_code,
                         400)
        self.assertEqual(self.get("reports/monthly/", {"month": "2026-13"}).status_code, 400)

    def test_source_efficiency_needs_enough_data(self):
        for i in range(9):
            self.apply(moment=at(22, 9), email=f"x{i}@mail.kg", phone=f"+996 701 000 {i:03d}")
        site = next(row for row in self.get("reports/monthly/", {"month": "2026-10"}).data["by_source"]
                    if row["source"] == "company_site")
        self.assertEqual((site["count"], site["enough_data"]), (11, True))
        self.assertEqual(site["interview_percent"], 9.1)

    def test_csv(self):
        daily = self.get("reports/daily/", {"date": "2026-10-20", "export": "csv"})
        self.assertEqual(daily["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn('filename="hr-daily-2026-10-20.csv"', daily["Content-Disposition"])
        body = daily.content.decode("utf-8")
        self.assertTrue(body.startswith("﻿"))
        self.assertIn("Новые отклики;3", body)
        self.assertIn("Как считаются показатели", body)
        monthly = self.get("reports/monthly/", {"month": "2026-10", "export": "csv"})
        self.assertIn("hr-monthly-2026-10.csv", monthly["Content-Disposition"])
        self.assertIn("Воронка", monthly.content.decode("utf-8"))

    def test_csv_escapes_formulas(self):
        self.new_application(moment=at(20, 13), first_name="=HYPERLINK(1)", phone="+996 700 000 009",
                             email="f@mail.kg", position="SMM")
        body = self.get("reports/daily/", {"date": "2026-10-20", "export": "csv"}).content.decode("utf-8")
        self.assertNotIn(";=HYPERLINK", body)


class DashboardTests(ReportsFixture):
    def test_real_numbers(self):
        draft = self.new_vacancy(title="Черновик")
        closed = self.new_vacancy(title="Закрытая")
        self.publish(closed["id"])
        self.publish(closed["id"], "closed")
        with frozen(at(21, 9)):
            d = self.get("dashboard/").data
        self.assertEqual((d["vacancies_open"], d["vacancies_draft"], d["vacancies_closed"]), (1, 1, 1))
        self.assertEqual((d["applications_total"], d["applications_new"], d["shortlisted"]), (3, 1, 0))
        self.assertEqual((d["interviews_today"], d["interviews_upcoming"], d["rejected"]), (1, 1, 1))
        self.assertEqual([i["id"] for i in d["upcoming_interviews"]], [self.interview["id"]])
        self.assertEqual(len(d["recent_applications"]), 3)
        self.assertTrue(d["recent_activity"])
        self.assertEqual(Vacancy.objects.get(pk=draft["id"]).status, "draft")
        self.assertEqual(self.get("dashboard/", {"date_from": "2026-10-10", "date_to": "2026-10-01"}).status_code, 400)
