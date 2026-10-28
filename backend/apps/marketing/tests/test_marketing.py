"""Кабинет маркетинга: доступ по ролям, контент-план, задачи, главная и отчёты.
Всё — через API, так же, как работает интерфейс."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase
from rest_framework.test import APIClient

from apps.marketing.models import ContentItem, MarketingTask
from apps.users.models import User

TZ = ZoneInfo("Asia/Bishkek")
API = "/api/v1/marketing"
PASSWORD = "Str0ngPassw0rd!"


def at(day: int, hour: int = 10, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, 0, tzinfo=TZ)


@contextmanager
def frozen(moment: datetime):
    with mock.patch("django.utils.timezone.now", return_value=moment):
        yield


def make(username: str, role: str, **extra) -> User:
    return User.objects.create_user(username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
                                    first_name=username.capitalize(), last_name="Test", role=role, is_verified=True,
                                    **extra)


def jwt_client(username: str) -> APIClient:
    client = APIClient()
    response = client.post("/api/v1/auth/login/", {"username": username, "password": PASSWORD}, format="json")
    assert response.status_code == 200, response.data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    return client


class MarketingFixture(TestCase):
    def setUp(self):
        self.marketer = make("aida", User.Role.MARKETING)
        self.colleague = make("bermet", User.Role.MARKETING)
        self.client = APIClient()
        self.client.force_authenticate(self.marketer)

    def post(self, url, body, client=None):
        return (client or self.client).post(f"{API}/{url}", body, format="json")

    def patch(self, url, body, client=None):
        return (client or self.client).patch(f"{API}/{url}", body, format="json")

    def get(self, url, params=None, client=None):
        return (client or self.client).get(f"{API}/{url}", params or {})

    def content(self, moment=None, **over):
        body = {"title": "Набор на осенний курс", "channel": "instagram", "format": "reels", **over}
        with frozen(moment or at(1)):
            response = self.post("content/", body)
        assert response.status_code == 201, response.data
        return response.data

    def task(self, moment=None, **over):
        body = {"title": "Снять видео с занятия", "priority": "medium", **over}
        with frozen(moment or at(1)):
            response = self.post("tasks/", body)
        assert response.status_code == 201, response.data
        return response.data


class AccessTests(MarketingFixture):
    def test_marketing_and_admin_get_the_cabinet(self):
        admin = make("boss", User.Role.ADMIN)
        for user in (self.marketer, admin):
            client = jwt_client(user.username)
            for url in ("meta/", "dashboard/", "reports/", "content/", "tasks/"):
                self.assertEqual(self.get(url, client=client).status_code, 200, (user.role, url))

    def test_other_roles_are_refused_by_the_backend(self):
        roles = [User.Role.HR_MANAGER, User.Role.SALES_MANAGER, User.Role.ROP, User.Role.TEACHER,
                 User.Role.TEAM_LEAD, User.Role.ASSISTANT, User.Role.ACCOUNTANT, User.Role.DIRECTOR]
        for role in roles:
            client = jwt_client(make(f"user_{role}", role).username)
            for url in ("meta/", "dashboard/", "content/", "tasks/"):
                self.assertEqual(self.get(url, client=client).status_code, 403, (role, url))
            self.assertEqual(self.post("tasks/", {"title": "x"}, client=client).status_code, 403, role)
        self.assertEqual(MarketingTask.objects.count(), 0)
        self.assertEqual(APIClient().get(f"{API}/tasks/").status_code, 401)

    def test_inactive_marketer_is_refused(self):
        self.marketer.is_active = False
        self.marketer.save()
        self.assertEqual(self.get("tasks/").status_code, 403)

    def test_marketing_stays_isolated_from_the_rest_of_the_lms(self):
        client = jwt_client(self.marketer.username)
        # Бухгалтерия, сотрудники HR, студенты и прочие разделы LMS закрыты;
        # открыта только своя зарплата (/accounting/my/, test_my_salary_marketing).
        self.assertEqual(client.get("/api/v1/accounting/my/salary/").status_code, 200)
        for url in ("/api/v1/trainers/", "/api/v1/accounting/", "/api/v1/assistant/", "/api/v1/subjects/"):
            response = client.get(url)
            self.assertEqual(response.status_code, 403, url)
            self.assertEqual(response.json()["code"], "staff_only", url)
        self.assertEqual(client.get("/api/v1/hr/employees/").status_code, 403)
        self.assertEqual(client.get("/api/v1/staff-attendance/admin/records/").status_code, 403)

    def test_attendance_still_available(self):
        client = jwt_client(self.marketer.username)
        response = client.get("/api/v1/staff-attendance/me/status/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["employee"]["id"], self.marketer.pk)

    def test_meta_exposes_team_names_only(self):
        make("hr", User.Role.HR_MANAGER)
        make("gone", User.Role.MARKETING, is_active=False)
        data = self.get("meta/").data
        self.assertEqual({m["id"] for m in data["team"]}, {self.marketer.pk, self.colleague.pk})
        self.assertEqual(set(data["team"][0]), {"id", "full_name"})
        self.assertEqual(data["me"], self.marketer.pk)
        self.assertEqual([s["value"] for s in data["content_statuses"]],
                         ["idea", "preparing", "review", "scheduled", "published"])


class ContentPlanTests(MarketingFixture):
    def test_idea_without_date_and_full_lifecycle(self):
        item = self.content()
        self.assertEqual((item["status"], item["publish_date"], item["published_at"]), ("idea", None, None))
        self.assertEqual(item["created_by_info"]["id"], self.marketer.pk)
        self.assertTrue(item["can_delete"])

        refused = self.patch(f"content/{item['id']}/", {"status": "scheduled"})
        self.assertEqual(refused.status_code, 400)
        self.assertIn("publish_date", refused.data)

        scheduled = self.patch(f"content/{item['id']}/", {"status": "scheduled", "publish_date": "2026-10-20",
                                                          "publish_time": "18:30", "responsible": self.colleague.pk})
        self.assertEqual(scheduled.status_code, 200, scheduled.data)
        self.assertEqual(scheduled.data["responsible_info"]["full_name"], "Bermet Test")

        with frozen(at(20, 19)):
            published = self.patch(f"content/{item['id']}/", {"status": "published",
                                                              "post_url": "https://instagram.com/p/abc"})
        self.assertEqual(published.data["status_label"], "Опубликовано")
        self.assertTrue(published.data["published_at"].startswith("2026-10-20T19:00"))
        # Повторное сохранение не сдвигает момент публикации.
        with frozen(at(22)):
            again = self.patch(f"content/{item['id']}/", {"title": "Набор на курс"})
        self.assertEqual(again.data["published_at"], published.data["published_at"])

        back = self.patch(f"content/{item['id']}/", {"status": "review"})
        self.assertIsNone(back.data["published_at"])

    def test_responsible_must_be_active_marketer(self):
        hr = make("hr", User.Role.HR_MANAGER)
        response = self.post("content/", {"title": "Пост", "responsible": hr.pk})
        self.assertEqual(response.status_code, 400)
        self.assertIn("responsible", response.data)

    def test_time_requires_date_and_title_required(self):
        self.assertIn("publish_time", self.post("content/", {"title": "Пост", "publish_time": "10:00"}).data)
        self.assertIn("title", self.post("content/", {"title": "   "}).data)

    def test_calendar_range_and_filters(self):
        self.content(title="A", status="scheduled", publish_date="2026-10-05", channel="tiktok")
        self.content(title="B", status="preparing", publish_date="2026-10-25", responsible=self.colleague.pk)
        self.content(title="C", status="scheduled", publish_date="2026-11-03")
        self.content(title="D")
        october = self.get("content/", {"date_from": "2026-10-01", "date_to": "2026-10-31"}).data
        self.assertEqual([r["title"] for r in october["results"]], ["A", "B"])
        self.assertEqual([r["title"] for r in self.get("content/", {"channel": "tiktok"}).data["results"]], ["A"])
        self.assertEqual([r["title"] for r in self.get("content/", {"status": "scheduled,preparing"}).data["results"]],
                         ["A", "B", "C"])
        self.assertEqual([r["title"] for r in self.get("content/", {"no_date": "1"}).data["results"]], ["D"])
        self.assertEqual([r["title"] for r in self.get("content/", {"responsible": self.colleague.pk}).data["results"]],
                         ["B"])
        self.assertEqual(self.get("content/", {"date_from": "2026-01-01", "date_to": "2026-12-31"}).status_code, 400)
        self.assertEqual(self.get("content/", {"date_from": "10.10.2026"}).status_code, 400)

    def test_delete_only_by_author_or_admin(self):
        item = self.content()
        other = APIClient()
        other.force_authenticate(self.colleague)
        listed = self.get("content/", client=other).data["results"][0]
        self.assertFalse(listed["can_delete"])
        self.assertEqual(other.delete(f"{API}/content/{item['id']}/").status_code, 403)
        # Но редактировать общий план может любой сотрудник маркетинга.
        self.assertEqual(self.patch(f"content/{item['id']}/", {"status": "preparing"}, client=other).status_code, 200)
        self.assertEqual(self.client.delete(f"{API}/content/{item['id']}/").status_code, 204)
        self.assertFalse(ContentItem.objects.exists())


class TaskTests(MarketingFixture):
    def test_done_sets_completion_and_reopen_clears_it(self):
        task = self.task(due_date="2026-10-10", responsible=self.marketer.pk)
        self.assertEqual((task["status"], task["is_overdue"]), ("todo", False))
        with frozen(at(9, 15)):
            done = self.patch(f"tasks/{task['id']}/", {"status": "done"})
        self.assertTrue(done.data["completed_at"].startswith("2026-10-09T15:00"))
        reopened = self.patch(f"tasks/{task['id']}/", {"status": "in_progress"})
        self.assertIsNone(reopened.data["completed_at"])

    def test_overdue_and_due_filters(self):
        self.task(title="Old", due_date="2026-10-05")
        self.task(title="Today", due_date="2026-10-12", priority="low")
        self.task(title="Soon", due_date="2026-10-15", priority="high")
        self.task(title="Later", due_date="2026-11-30")
        self.task(title="Undated")
        done = self.task(title="Closed", due_date="2026-10-01")
        self.patch(f"tasks/{done['id']}/", {"status": "done"})
        with frozen(at(12)):
            def titles(**params):
                return [r["title"] for r in self.get("tasks/", params).data["results"]]

            self.assertEqual(titles(status="overdue"), ["Old"])
            self.assertEqual(titles(due="overdue"), ["Old"])
            self.assertEqual(titles(due="today"), ["Today"])
            self.assertEqual(titles(due="week"), ["Today", "Soon"])
            self.assertEqual(titles(due="none"), ["Undated"])
            self.assertEqual(titles(status="done"), ["Closed"])
            self.assertEqual(titles(priority="high"), ["Soon"])
            # Выполненные — в конце, открытые — по сроку.
            self.assertEqual(titles(), ["Old", "Today", "Soon", "Later", "Undated", "Closed"])
            self.assertTrue(self.get("tasks/", {"status": "overdue"}).data["results"][0]["is_overdue"])

    def test_mine_filter(self):
        self.task(title="My", responsible=self.marketer.pk)
        self.task(title="Theirs", responsible=self.colleague.pk)
        self.assertEqual([r["title"] for r in self.get("tasks/", {"mine": "1"}).data["results"]], ["My"])


class DashboardAndReportTests(MarketingFixture):
    def setUp(self):
        super().setUp()
        # Октябрь 2026: план из 4 публикаций (одна идея — не в плане).
        a = self.content(title="A", status="scheduled", publish_date="2026-10-05", responsible=self.marketer.pk)
        self.content(title="B", status="review", publish_date="2026-10-08", channel="tiktok")
        self.content(title="C", status="scheduled", publish_date="2026-10-20")
        self.content(title="D", status="preparing", publish_date="2026-10-28")
        self.content(title="Idea", publish_date="2026-10-10")
        with frozen(at(5, 18)):
            self.patch(f"content/{a['id']}/", {"status": "published"})
        on_time = self.task(title="On time", due_date="2026-10-10", responsible=self.marketer.pk)
        late = self.task(title="Late", due_date="2026-10-03")
        self.task(title="Overdue", due_date="2026-10-11", status="in_progress")
        self.task(title="Today", due_date="2026-10-12", responsible=self.marketer.pk)
        with frozen(at(9)):
            self.patch(f"tasks/{on_time['id']}/", {"status": "done"})
        with frozen(at(6)):
            self.patch(f"tasks/{late['id']}/", {"status": "done"})

    def test_dashboard_counts_real_data(self):
        with frozen(at(12)):
            data = self.get("dashboard/").data
        self.assertEqual(data["period"], {"date_from": "2026-10-01", "date_to": "2026-10-31"})
        self.assertEqual(data["tasks"], {"open": 2, "in_progress": 1, "overdue": 1, "due_today": 1, "mine_open": 1,
                                         "done_in_period": 2})
        self.assertEqual(data["content"], {"ideas": 1, "in_work": 2, "scheduled": 1, "planned_in_period": 4,
                                           "published_in_period": 1})
        self.assertEqual([t["title"] for t in data["upcoming_tasks"]], ["Overdue", "Today"])
        self.assertEqual([c["title"] for c in data["upcoming_content"]], ["C", "D"])

    def test_month_report(self):
        with frozen(at(12)):
            data = self.get("reports/", {"period": "month"}).data
        self.assertEqual(data["tasks"]["completed"], 2)
        self.assertEqual((data["tasks"]["completed_on_time"], data["tasks"]["completed_late"]), (1, 1))
        self.assertEqual(data["tasks"]["overdue_now"], 1)
        self.assertEqual(data["content"], {"planned": 4, "prepared": 3, "published": 1, "plan_due": 2,
                                           "plan_done": 1, "plan_completion": 50})
        self.assertEqual(len(data["series"]), 5)
        self.assertEqual(sum(b["published"] for b in data["series"]), 1)
        self.assertEqual(data["by_channel"][0], {"channel": "instagram", "label": "Instagram", "planned": 3,
                                                 "published": 1})
        mine = next(row for row in data["by_person"] if row["id"] == self.marketer.pk)
        self.assertEqual((mine["tasks_completed"], mine["content_published"]), (1, 1))

    def test_week_report_and_validation(self):
        with frozen(at(12)):
            week = self.get("reports/", {"period": "week", "date": "2026-10-07"}).data
            self.assertEqual(self.get("reports/", {"period": "year"}).status_code, 400)
            self.assertEqual(self.get("reports/", {"date": "07.10.2026"}).status_code, 400)
        self.assertEqual(week["period"], {"kind": "week", "date_from": "2026-10-05", "date_to": "2026-10-11"})
        self.assertEqual(len(week["series"]), 7)
        self.assertEqual(week["content"]["plan_completion"], 50)
        self.assertEqual(week["tasks"]["completed"], 2)

    def test_todays_post_counts_once_it_is_out(self):
        evening = self.content(title="Evening", status="scheduled", publish_date="2026-10-12", publish_time="19:00")
        with frozen(at(12)):
            before = self.get("reports/", {"period": "month"}).data["content"]
        self.assertEqual((before["plan_due"], before["plan_done"]), (2, 1))
        with frozen(at(12, 19)):
            self.patch(f"content/{evening['id']}/", {"status": "published"})
            after = self.get("reports/", {"period": "month"}).data["content"]
        self.assertEqual((after["plan_due"], after["plan_done"], after["plan_completion"]), (3, 2, 67))

    def test_empty_plan_has_no_completion_figure(self):
        with frozen(at(12)):
            data = self.get("reports/", {"period": "month", "date": "2026-12-01"}).data
        self.assertIsNone(data["content"]["plan_completion"])
        self.assertEqual(data["by_channel"], [])
