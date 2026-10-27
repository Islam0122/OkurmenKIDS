"""Блокировки при смене этапа отклика.

Отклик читается вместе с кандидатом и вакансией (`select_related`), а вакансия
— nullable FK, т. е. LEFT OUTER JOIN. PostgreSQL не умеет FOR UPDATE для
nullable-стороны внешнего соединения («FOR UPDATE cannot be applied to the
nullable side of an outer join»), поэтому блокируется только строка отклика
(`FOR UPDATE OF "recruitment_application"`). SQLite блокировок не выполняет —
проверки SQL и конкурентности идут на PostgreSQL (TEST_DATABASE_URL).
"""
from __future__ import annotations

import threading
from unittest import skipUnless

from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext

from apps.recruitment.models import Application, Candidate, HRActivity, Interview
from apps.recruitment.services import hiring, pipeline
from apps.recruitment.services.common import RecruitmentError, new_application_number
from apps.users.models import User

from .base import RecruitmentFixture, at, frozen

LOCK_OF_APPLICATION = 'FOR UPDATE OF "recruitment_application"'


class StatusChangeTests(RecruitmentFixture):
    def test_application_without_vacancy(self):
        app = self.new_application(vacancy=None, position="SMM")
        self.move(app["id"], "screening", "shortlisted")
        self.assertEqual(self.status_of(app["id"]), "shortlisted")
        self.assertIsNone(Application.objects.get(pk=app["id"]).vacancy_id)

    def test_application_with_vacancy(self):
        app = self.new_application()
        self.move(app["id"], "screening", "rejected")
        self.assertEqual(self.status_of(app["id"]), "rejected")

    def test_repeated_request_changes_status_once(self):
        app = self.new_application()
        self.move(app["id"], "screening")
        with frozen(at(20, 11)):
            again = self.post(f"applications/{app['id']}/status/", {"status": "screening"})
        self.assertEqual((again.status_code, again.data["code"]), (400, "invalid_transition"))
        transitions = HRActivity.objects.filter(application_id=app["id"], kind="candidate_status", to_status="screening")
        self.assertEqual(transitions.count(), 1)

    def test_interview_flow_and_hire_lock_application(self):
        """Все места с `_lock`: назначение, перенос, отмена, результат, найм — в том числе без вакансии."""
        for vacancy in (self.vacancy["id"], None):
            with self.subTest(vacancy=vacancy):
                n = Application.objects.count()
                app = self.new_application(vacancy=vacancy, position="SMM", first_name=f"Кандидат{n}",
                                           phone=f"+996 700 000 {n:03d}", email=f"c{n}@mail.kg")
                first = self.schedule(app["id"], at(22, 10 + n)).data
                with frozen(at(21, 9)):
                    moved = self.patch(f"interviews/{first['id']}/", {"scheduled_at": at(23, 10 + n).isoformat()}).data
                with frozen(at(21, 9)):
                    self.assertEqual(self.post(f"interviews/{moved['id']}/cancel/", {"reason": "Перенос"}).status_code, 200)
                self.to_offer(app["id"], day=23 + n)
                response = self.post(f"applications/{app['id']}/hire/", {
                    "username": f"emp{n}", "email": f"emp{n}@mail.kg", "role": "rop",
                    "password": "Str0ngPassw0rd!", "password_confirm": "Str0ngPassw0rd!"})
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(self.status_of(app["id"]), "hired")

    @skipUnless(connection.vendor == "postgresql", "row locks are only emitted on PostgreSQL")
    def test_lock_is_restricted_to_application_row(self):
        app = self.new_application(vacancy=None, position="SMM")
        application = Application.objects.get(pk=app["id"])
        with CaptureQueriesContext(connection) as ctx:
            pipeline.change_status(application, "screening", self.hr)
        locking = [q["sql"] for q in ctx.captured_queries if "FOR UPDATE" in q["sql"]]
        joined = [sql for sql in locking if "LEFT OUTER JOIN" in sql]
        self.assertTrue(joined, "отклик по-прежнему читается вместе с nullable-вакансией")
        for sql in joined:
            self.assertIn(LOCK_OF_APPLICATION, sql)

    @skipUnless(connection.vendor == "postgresql", "row locks are only emitted on PostgreSQL")
    def test_hiring_and_interview_locks(self):
        app = self.new_application()
        interview = self.schedule(app["id"], at(22, 15)).data
        with CaptureQueriesContext(connection) as ctx, frozen(at(21)):
            pipeline.cancel_interview(Interview.objects.get(pk=interview["id"]), self.hr, "Перенос")
        locking = [q["sql"] for q in ctx.captured_queries if "FOR UPDATE" in q["sql"]]
        self.assertTrue(any('FOR UPDATE OF "recruitment_interview"' in sql for sql in locking))
        self.assertTrue(any(LOCK_OF_APPLICATION in sql for sql in locking))
        with CaptureQueriesContext(connection) as ctx:
            with self.assertRaises(RecruitmentError):
                hiring.hire(Application.objects.get(pk=app["id"]), self.hr, lambda: None)
        self.assertTrue(any(LOCK_OF_APPLICATION in q["sql"] for q in ctx.captured_queries))


@skipUnless(connection.vendor == "postgresql", "needs real concurrent transactions (PostgreSQL)")
class StatusChangeConcurrencyTests(TransactionTestCase):
    """Два одновременных запроса «Отказ компании» по одному отклику без вакансии:
    один меняет этап, второй видит уже изменённый этап и получает отказ."""

    def test_concurrent_status_changes_apply_once(self):
        hr = User.objects.create_user(username="hr_c", email="hr_c@okurmen.kg", password="x", first_name="HR",
                                      role=User.Role.HR_MANAGER, is_verified=True)
        candidate = Candidate.objects.create(first_name="Бакыт", phone="+996 555 000 111", phone_digits="996555000111")
        application = Application.objects.create(number=new_application_number(), candidate=candidate, position="SMM")
        barrier = threading.Barrier(2)
        done, errors = [], []

        def worker():
            try:
                barrier.wait(timeout=10)
                pipeline.change_status(Application.objects.get(pk=application.pk), "rejected", hr)
                done.append(True)
            except RecruitmentError as exc:
                errors.append(exc.code)
            except Exception as exc:  # всё остальное — провал теста (в том числе ошибка FOR UPDATE)
                errors.append(repr(exc))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertEqual((len(done), errors), (1, ["invalid_transition"]))
        application.refresh_from_db()
        self.assertEqual(application.status, "rejected")
        self.assertEqual(HRActivity.objects.filter(application=application, to_status="rejected").count(), 1)
