"""Миграция 0003: данные прежнего HR-кабинета (кандидат = отклик) переходят
на модель «кандидат + отклик» без потерь и без автопубликации вакансий."""
from __future__ import annotations

from datetime import date

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

APP = "recruitment"


class CareersDataMigrationTests(TransactionTestCase):
    before = [(APP, "0001_initial")]
    after = [(APP, "0004_careers_cleanup")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        old = executor.loader.project_state(self.before).apps
        User = old.get_model("users", "User")
        Vacancy = old.get_model(APP, "Vacancy")
        Candidate = old.get_model(APP, "Candidate")
        Interview = old.get_model(APP, "Interview")
        HRActivity = old.get_model(APP, "HRActivity")
        hr = User.objects.create(username="hr_m", email="hr_m@okurmen.kg", role="hr_manager", first_name="HR")
        employee = User.objects.create(username="emp_m", email="emp_m@okurmen.kg", role="rop", first_name="E")
        open_vacancy = Vacancy.objects.create(title="Менеджер по продажам", status="open")
        Vacancy.objects.create(title="Закрытая", status="closed")
        now = timezone.now()
        self.contacted = Candidate.objects.create(
            last_name="Асанов", first_name="Бакыт", phone="0555 123 456", email="Bakyt@Mail.kg", vacancy=open_vacancy,
            source="referral", added_on=date(2026, 10, 1), responsible=hr, notes="Хороший опыт",
            status="contacted", status_changed_at=now, created_by=hr)
        self.hired = Candidate.objects.create(
            first_name="Нурлан", phone="+996 700 000 001", position="SMM", status="hired", hired_user=employee,
            status_changed_at=now, added_on=date(2026, 9, 1))
        Interview.objects.create(candidate=self.contacted, vacancy=open_vacancy, scheduled_at=now, interviewer=hr,
                                 status="cancelled")
        HRActivity.objects.create(kind="candidate_status", candidate=self.contacted, from_status="new",
                                  to_status="contacted", created_at=now)
        HRActivity.objects.create(kind="candidate_note", candidate=self.contacted, actor=hr, message="Звонил",
                                  created_at=now)
        executor.loader.build_graph()
        executor.migrate(self.after)
        self.apps = executor.loader.project_state(self.after).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_candidates_become_people_with_applications(self):
        Application = self.apps.get_model(APP, "Application")
        Candidate = self.apps.get_model(APP, "Candidate")
        Vacancy = self.apps.get_model(APP, "Vacancy")
        Interview = self.apps.get_model(APP, "Interview")
        HRActivity = self.apps.get_model(APP, "HRActivity")
        InternalNote = self.apps.get_model(APP, "InternalNote")

        first = Application.objects.get(candidate_id=self.contacted.pk)
        self.assertEqual((first.status, first.source, first.applied_on, first.channel),
                         ("screening", "referral", date(2026, 10, 1), "hr"))
        self.assertRegex(first.number, r"^\d{4}-[A-Z2-9]{6}$")
        person = Candidate.objects.get(pk=self.contacted.pk)
        self.assertEqual((person.email, person.phone_digits), ("bakyt@mail.kg", "996555123456"))
        hired = Application.objects.get(candidate_id=self.hired.pk)
        self.assertEqual((hired.status, hired.position), ("hired", "SMM"))
        self.assertIsNotNone(hired.hired_user_id)
        self.assertEqual(Interview.objects.get().application_id, first.pk)
        self.assertEqual(set(HRActivity.objects.values_list("to_status", flat=True)) - {""}, {"screening"})
        self.assertTrue(all(a.application_id == first.pk for a in HRActivity.objects.all()))
        self.assertEqual(sorted(InternalNote.objects.values_list("text", flat=True)), ["Звонил", "Хороший опыт"])
        statuses = dict(Vacancy.objects.values_list("title", "status"))
        self.assertEqual(statuses, {"Менеджер по продажам": "draft", "Закрытая": "closed"})
        self.assertTrue(Vacancy.objects.get(title="Менеджер по продажам").slug.startswith("menedzher-po-prodazham-"))
