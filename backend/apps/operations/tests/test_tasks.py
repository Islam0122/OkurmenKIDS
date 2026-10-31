"""Задачи: создание, назначение, права, workflow с проверкой, чек-лист,
комментарии, вложения, история, просрочки, «Мои задачи», повторяющиеся
задачи, уведомления — через API, как работает интерфейс."""
from __future__ import annotations

import datetime as dt

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.operations.models import Notification, Task, TaskHistory, TaskRecurrence, TaskStatus
from apps.operations.services.recurrence import generate_all, generate_for
from apps.users.models import User

from .base import OpsTestCase, in_hours, jwt_client

API = "/api/v1/tasks"


class TaskCreationAndAccessTests(OpsTestCase):
    def test_operations_director_assigns_any_employee_and_assignee_is_notified(self):
        task = self.create_task(self.od, assignee=self.manager.pk, deadline=in_hours(48), priority="high")
        self.assertEqual(task["department"], "sales")
        self.assertEqual(task["status"], "pending")
        self.assertEqual(task["created_by"]["id"], self.od.pk)
        self.assertTrue(Notification.objects.filter(recipient=self.manager, kind="task_assigned").exists())
        self.assertEqual(TaskHistory.objects.filter(task_id=task["id"], action="created").count(), 1)

    def test_team_lead_assigns_only_academy_staff(self):
        self.create_task(self.lead, assignee=self.trainer.pk)
        self.create_task(self.lead, assignee=self.assistant.pk)
        response = self.client_for(self.lead).post(f"{API}/", {"title": "x", "assignee": self.manager.pk},
                                                   format="json")
        self.assertEqual(response.status_code, 403)

    def test_rop_assigns_sales_but_not_marketing(self):
        self.create_task(self.rop, assignee=self.manager.pk)
        response = self.client_for(self.rop).post(f"{API}/", {"title": "x", "assignee": self.marketer.pk},
                                                  format="json")
        self.assertEqual(response.status_code, 403)

    def test_regular_employee_can_only_create_personal_tasks(self):
        own = self.create_task(self.trainer, assignee=self.trainer.pk)
        self.assertEqual(own["assignee"]["id"], self.trainer.pk)
        response = self.client_for(self.trainer).post(f"{API}/", {"title": "x", "assignee": self.trainer2.pk},
                                                      format="json")
        self.assertEqual(response.status_code, 403)

    def test_foreign_task_is_404_not_403(self):
        task = self.create_task(self.od, assignee=self.manager.pk)
        for user in (self.trainer, self.marketer, self.hr):
            response = self.client_for(user).get(f"{API}/{task['id']}/")
            self.assertEqual(response.status_code, 404, user.role)
        self.assertEqual(self.client_for(self.rop).get(f"{API}/{task['id']}/").status_code, 200)

    def test_list_is_scoped(self):
        self.create_task(self.od, assignee=self.manager.pk, title="Продажи")
        self.create_task(self.od, assignee=self.trainer.pk, title="Журнал")
        titles = lambda user: {t["title"] for t in self.client_for(user).get(f"{API}/").data["results"]}  # noqa: E731
        self.assertEqual(titles(self.manager), {"Продажи"})
        self.assertEqual(titles(self.trainer), {"Журнал"})
        self.assertEqual(titles(self.lead), {"Журнал"})
        self.assertEqual(titles(self.od), {"Продажи", "Журнал"})

    def test_department_task_without_assignee_is_taken_by_whoever_starts_it(self):
        task = self.create_task(self.od, department="marketing")
        self.assertIsNone(task["assignee"])
        response = self.client_for(self.marketer).post(f"{API}/{task['id']}/start/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["assignee"]["id"], self.marketer.pk)

    def test_staff_only_and_accountant_roles_reach_their_tasks_through_isolation(self):
        self.create_task(self.od, assignee=self.accountant.pk)
        self.create_task(self.od, assignee=self.hr.pk)
        for user in (self.accountant, self.hr, self.manager, self.od):
            self.assertEqual(jwt_client(user.username).get(f"{API}/my/").status_code, 200, user.role)

    def test_deadline_before_start_is_rejected(self):
        response = self.client_for(self.od).post(f"{API}/", {
            "title": "x", "assignee": self.trainer.pk, "start_date": "2026-12-10",
            "deadline": "2026-12-01T10:00:00+06:00"}, format="json")
        self.assertEqual(response.status_code, 400)


class WorkflowTests(OpsTestCase):
    def act(self, user, task_id, action, **body):
        return self.client_for(user).post(f"{API}/{task_id}/{action}/", body, format="json")

    def test_approval_flow_submit_review_reject_with_comment_then_approve(self):
        task = self.create_task(self.od, assignee=self.trainer.pk, requires_approval=True, deadline=in_hours(24))
        tid = task["id"]
        self.assertEqual(self.act(self.trainer, tid, "start").data["status"], "in_progress")
        submitted = self.act(self.trainer, tid, "submit", comment="Готово")
        self.assertEqual(submitted.data["status"], "review")
        self.assertTrue(Notification.objects.filter(recipient=self.od, kind="task_review").exists())

        # Исполнитель сам себя не подтверждает.
        self.assertEqual(self.act(self.trainer, tid, "approve").status_code, 403)
        # Возврат без комментария — нельзя.
        self.assertEqual(self.act(self.od, tid, "reject").status_code, 400)
        rejected = self.act(self.od, tid, "reject", comment="Добавьте фото журнала")
        self.assertEqual(rejected.data["status"], "rejected")
        self.assertEqual(rejected.data["reviews"][0]["comment"], "Добавьте фото журнала")
        self.assertTrue(Notification.objects.filter(recipient=self.trainer, kind="task_rejected").exists())

        self.act(self.trainer, tid, "start")
        self.act(self.trainer, tid, "submit")
        approved = self.act(self.od, tid, "approve", comment="Принято")
        self.assertEqual(approved.data["status"], "completed")
        self.assertIsNotNone(approved.data["completed_at"])
        actions = [h["action"] for h in approved.data["history"]]
        self.assertEqual(actions, ["created", "started", "submitted", "rejected", "started", "submitted", "approved"])

    def test_without_approval_submit_completes(self):
        task = self.create_task(self.od, assignee=self.trainer.pk)
        response = self.act(self.trainer, task["id"], "submit")
        self.assertEqual(response.data["status"], "completed")

    def test_only_assignee_executes(self):
        task = self.create_task(self.od, assignee=self.trainer.pk)
        self.assertEqual(self.act(self.trainer2, task["id"], "start").status_code, 404)  # не видит вовсе
        self.assertEqual(self.act(self.lead, task["id"], "start").status_code, 403)  # видит, но не исполнитель

    def test_checklist_must_be_done_before_submit(self):
        task = self.create_task(self.od, assignee=self.trainer.pk, checklist=["Посещаемость", "Оценки"])
        self.assertEqual(self.act(self.trainer, task["id"], "submit").status_code, 400)
        client = self.client_for(self.trainer)
        for item in task["checklist"] if "checklist" in task else client.get(f"{API}/{task['id']}/").data["checklist"]:
            r = client.patch(f"{API}/{task['id']}/checklist/{item['id']}/", {"is_done": True}, format="json")
            self.assertEqual(r.status_code, 200)
        self.assertEqual(self.act(self.trainer, task["id"], "submit").data["status"], "completed")

    def test_cancel_and_reopen_by_manager_only(self):
        task = self.create_task(self.od, assignee=self.trainer.pk)
        self.assertEqual(self.act(self.trainer, task["id"], "cancel").status_code, 403)
        self.assertEqual(self.act(self.od, task["id"], "cancel").data["status"], "cancelled")
        self.assertEqual(self.act(self.od, task["id"], "reopen").data["status"], "pending")

    def test_reassign_transfers_task_and_logs(self):
        task = self.create_task(self.od, assignee=self.trainer.pk)
        response = self.client_for(self.od).patch(f"{API}/{task['id']}/", {"assignee": self.trainer2.pk},
                                                  format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["assignee"]["id"], self.trainer2.pk)
        self.assertIn("assigned", [h["action"] for h in response.data["history"]])
        # Исполнитель условия задачи не меняет.
        self.assertEqual(self.client_for(self.trainer2).patch(f"{API}/{task['id']}/", {"title": "x"},
                                                              format="json").status_code, 403)

    def test_comments_notify_participants(self):
        task = self.create_task(self.od, assignee=self.trainer.pk)
        response = self.client_for(self.trainer).post(f"{API}/{task['id']}/comments/", {"text": "Вопрос"},
                                                      format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Notification.objects.filter(recipient=self.od, kind="task_comment").exists())

    def test_attachment_upload_download_and_access(self):
        task = self.create_task(self.od, assignee=self.trainer.pk)
        upload = SimpleUploadedFile("отчёт.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        response = self.client_for(self.trainer).post(f"{API}/{task['id']}/attachments/", {"file": upload},
                                                      format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        url = response.data["download_url"].replace("/api/v1/tasks", API)
        self.assertEqual(self.client_for(self.od).get(url).status_code, 200)
        self.assertEqual(self.client_for(self.marketer).get(url).status_code, 404)
        bad = SimpleUploadedFile("run.exe", b"MZ", content_type="application/octet-stream")
        self.assertEqual(self.client_for(self.trainer).post(f"{API}/{task['id']}/attachments/", {"file": bad},
                                                            format="multipart").status_code, 400)


class OverdueAndMyTasksTests(OpsTestCase):
    def test_overdue_is_computed_and_filterable(self):
        task = self.create_task(self.od, assignee=self.trainer.pk, deadline=in_hours(1))
        Task.objects.filter(pk=task["id"]).update(deadline=timezone.now() - dt.timedelta(hours=2))
        detail = self.client_for(self.trainer).get(f"{API}/{task['id']}/").data
        self.assertEqual(detail["status"], "overdue")
        self.assertEqual(detail["stored_status"], "pending")
        ids = [t["id"] for t in self.client_for(self.od).get(f"{API}/", {"status": "overdue"}).data["results"]]
        self.assertEqual(ids, [task["id"]])

    def test_my_tasks_sections(self):
        today = self.create_task(self.od, assignee=self.trainer.pk, title="Сегодня",
                                 deadline=timezone.localtime().replace(hour=23, minute=59).isoformat())
        later = self.create_task(self.od, assignee=self.trainer.pk, title="Потом", deadline=in_hours(72))
        late = self.create_task(self.od, assignee=self.trainer.pk, title="Просрочено", deadline=in_hours(5))
        Task.objects.filter(pk=late["id"]).update(deadline=timezone.now() - dt.timedelta(days=1))
        review = self.create_task(self.od, assignee=self.trainer.pk, title="Проверка", requires_approval=True)
        self.client_for(self.trainer).post(f"{API}/{review['id']}/submit/")
        data = self.client_for(self.trainer).get(f"{API}/my/").data
        ids = lambda key: [t["id"] for t in data[key]]  # noqa: E731
        self.assertIn(today["id"], ids("today"))
        self.assertIn(later["id"], ids("upcoming"))
        self.assertEqual(ids("overdue"), [late["id"]])
        self.assertEqual(ids("review"), [review["id"]])
        od_data = self.client_for(self.od).get(f"{API}/my/").data
        self.assertEqual([t["id"] for t in od_data["to_review"]], [review["id"]])


class RecurrenceTests(OpsTestCase):
    def rule(self, **extra):
        defaults = dict(title="Ежедневный отчёт", department="academy", assignee=self.trainer, created_by=self.od,
                        frequency="daily", starts_on=dt.date(2026, 3, 1))
        return TaskRecurrence.objects.create(**{**defaults, **extra})

    def test_daily_generation_is_idempotent_and_keeps_history_by_date(self):
        rule = self.rule()
        self.assertEqual(len(generate_for(rule, dt.date(2026, 3, 3))), 3)
        rule.refresh_from_db()
        rule.last_generated_on = None  # даже «забытая» отметка не создаёт дублей
        rule.save()
        self.assertEqual(len(generate_for(rule, dt.date(2026, 3, 3))), 0)
        dates = list(Task.objects.filter(recurrence=rule).order_by("occurrence_date").values_list("occurrence_date",
                                                                                                  flat=True))
        self.assertEqual(dates, [dt.date(2026, 3, 1), dt.date(2026, 3, 2), dt.date(2026, 3, 3)])

    def test_weekly_and_monthly_schedules(self):
        weekly = self.rule(frequency="weekly", weekdays=[0, 3])  # пн и чт
        created = generate_for(weekly, dt.date(2026, 3, 15))
        self.assertTrue(all(t.occurrence_date.weekday() in (0, 3) for t in created))
        self.assertEqual(len(created), 4)
        monthly = self.rule(frequency="monthly", month_day=31, starts_on=dt.date(2026, 2, 1))
        created = generate_for(monthly, dt.date(2026, 2, 28))
        self.assertEqual([t.occurrence_date for t in created], [dt.date(2026, 2, 28)])  # короткий месяц

    def test_api_creates_template_and_first_occurrence(self):
        response = self.client_for(self.lead).post(f"{API}/recurrences/", {
            "title": "Заполнить таблицу", "assignee": self.assistant.pk, "frequency": "daily",
            "starts_on": timezone.localdate().isoformat(), "checklist": ["Пропуски", "Родители"]}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        task = Task.objects.get(recurrence_id=response.data["id"])
        self.assertEqual(task.checklist.count(), 2)
        self.assertEqual(generate_all(), 0)
        bad = self.client_for(self.lead).post(f"{API}/recurrences/", {
            "title": "x", "assignee": self.manager.pk, "frequency": "daily"}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_weekly_requires_days(self):
        response = self.client_for(self.od).post(f"{API}/recurrences/", {
            "title": "x", "assignee": self.trainer.pk, "frequency": "weekly"}, format="json")
        self.assertEqual(response.status_code, 400)


class NotificationTests(OpsTestCase):
    def test_reminders_are_sent_once(self):
        from apps.operations.services.scheduler import deadline_reminders

        task = self.create_task(self.od, assignee=self.trainer.pk, deadline=in_hours(3))
        self.assertEqual(deadline_reminders()["deadline_soon"], 1)
        self.assertEqual(deadline_reminders()["deadline_soon"], 0)
        Task.objects.filter(pk=task["id"]).update(deadline=timezone.now() - dt.timedelta(hours=1))
        self.assertEqual(deadline_reminders()["overdue"], 2)  # исполнитель и автор
        self.assertEqual(deadline_reminders()["overdue"], 0)

    def test_notification_api_is_personal(self):
        self.create_task(self.od, assignee=self.trainer.pk)
        client = self.client_for(self.trainer)
        self.assertEqual(client.get("/api/v1/notifications/unread-count/").data["count"], 1)
        notification = Notification.objects.get(recipient=self.trainer)
        self.assertEqual(self.client_for(self.trainer2).post(f"/api/v1/notifications/{notification.pk}/read/")
                         .status_code, 404)
        self.assertTrue(client.post(f"/api/v1/notifications/{notification.pk}/read/").data["is_read"])
        self.assertEqual(client.get("/api/v1/notifications/unread-count/").data["count"], 0)

    def test_inactive_user_gets_nothing(self):
        self.trainer2.is_active = False
        self.trainer2.save()
        from apps.operations.services.notifications import notify

        self.assertIsNone(notify(self.trainer2, "task_assigned", "k1", "t"))
        self.assertEqual(User.objects.get(pk=self.trainer2.pk).ops_notifications.count(), 0)


class StatusValuesTests(OpsTestCase):
    def test_all_spec_statuses_exist(self):
        self.assertEqual(set(TaskStatus.values), {"pending", "in_progress", "review", "completed", "rejected",
                                                   "overdue", "cancelled"})
