"""HR-кабинет: вакансии, кандидаты, этапы найма, собеседования, найм,
главная и отчёты. Все проверки — через API, как работает интерфейс."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase
from rest_framework.test import APIClient

from apps.recruitment.models import Candidate, HRActivity, Interview, Vacancy
from apps.users.models import User

TZ = ZoneInfo("Asia/Bishkek")
API = "/api/v1/hr"
PASSWORD = "Str0ngPassw0rd!"


def at(day: int, hour: int = 10, minute: int = 0, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=TZ)


@contextmanager
def frozen(moment: datetime):
    with mock.patch("django.utils.timezone.now", return_value=moment):
        yield


def make(username: str, role: str, **extra) -> User:
    return User.objects.create_user(username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
                                    first_name=username.capitalize(), last_name="Test", role=role, is_verified=True,
                                    **extra)


class RecruitmentFixture(TestCase):
    def setUp(self):
        self.hr = make("hr", User.Role.HR_MANAGER)
        self.interviewer = make("rop", User.Role.ROP)
        self.client = APIClient()
        self.client.force_authenticate(self.hr)
        with frozen(at(1, 9)):
            self.vacancy = self.post("vacancies/", {"title": "Менеджер по продажам", "department": "Продажи",
                                                    "responsible": self.hr.pk}).data

    def post(self, url, body=None, client=None):
        return (client or self.client).post(f"{API}/{url}", body or {}, format="json")

    def patch(self, url, body):
        return self.client.patch(f"{API}/{url}", body, format="json")

    def get(self, url, params=None):
        return self.client.get(f"{API}/{url}", params or {})

    def new_candidate(self, moment=None, **over) -> dict:
        body = {"last_name": "Асанов", "first_name": "Бакыт", "phone": "+996 555 123 456",
                "vacancy": self.vacancy["id"], "source": "job_site"}
        body.update(over)
        with frozen(moment or at(20, 9)):
            response = self.post("candidates/", body)
        assert response.status_code == 201, response.data
        return response.data

    def schedule(self, candidate_id, when, now=None, **over):
        body = {"candidate": candidate_id, "scheduled_at": when.isoformat(), "format": "online",
                "meeting_url": "https://meet.example.com/abc", "interviewer": self.interviewer.pk}
        body.update(over)
        with frozen(now or at(20, 9)):
            return self.post("interviews/", body)

    def status_of(self, candidate_id) -> str:
        return Candidate.objects.get(pk=candidate_id).status


class AccessTests(RecruitmentFixture):
    URLS = ("dashboard/", "meta/", "vacancies/", "candidates/", "interviews/?date_from=2026-10-01&date_to=2026-10-31",
            "reports/daily/", "reports/monthly/", "employees/")

    def test_only_active_hr_reaches_hr_api(self):
        candidate = self.new_candidate()
        anonymous = APIClient()
        for url in self.URLS:
            self.assertEqual(anonymous.get(f"{API}/{url}").status_code, 401, url)
        for role in (User.Role.ADMIN, User.Role.DIRECTOR, User.Role.ACCOUNTANT, User.Role.TEAM_LEAD,
                     User.Role.ASSISTANT, User.Role.TEACHER, User.Role.ROP, User.Role.DOP, User.Role.MARKETING):
            client = APIClient()
            client.force_authenticate(make(f"u_{role}", role))
            for url in self.URLS:
                self.assertEqual(client.get(f"{API}/{url}").status_code, 403, f"{role} {url}")
            # Контакты и заметки кандидата чужим ролям не отдаются.
            self.assertEqual(client.get(f"{API}/candidates/{candidate['id']}/").status_code, 403, role)
            self.assertEqual(self.post(f"candidates/{candidate['id']}/notes/", {"text": "x"}, client).status_code,
                             403, role)
        self.hr.is_active = False
        self.hr.save()
        self.assertEqual(self.get("candidates/").status_code, 403)

    def test_hr_api_reachable_with_jwt_through_isolation(self):
        client = APIClient()
        token = client.post("/api/v1/auth/login/", {"username": "hr", "password": PASSWORD}, format="json").data
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token['access']}")
        self.assertEqual(client.get(f"{API}/dashboard/").status_code, 200)
        self.assertEqual(client.get(f"{API}/candidates/").status_code, 200)
        # Остальная LMS для HR закрыта, как и раньше.
        self.assertEqual(client.get("/api/v1/trainers/").status_code, 403)


class VacancyTests(RecruitmentFixture):
    def test_create_update_and_no_delete(self):
        self.assertEqual(self.vacancy["status"], "open")
        self.assertEqual(self.vacancy["responsible_info"]["id"], self.hr.pk)
        response = self.patch(f"vacancies/{self.vacancy['id']}/", {"status": "paused"})
        self.assertEqual(response.data["status_label"], "Приостановлена")
        self.assertEqual(self.client.delete(f"{API}/vacancies/{self.vacancy['id']}/").status_code, 405)
        self.assertEqual(self.post("vacancies/", {"title": "  "}).status_code, 400)
        self.assertEqual(self.post("vacancies/", {"title": "X", "status": "nope"}).status_code, 400)
        kinds = set(HRActivity.objects.values_list("kind", flat=True))
        self.assertTrue({"vacancy_created", "vacancy_updated"} <= kinds)

    def test_candidate_only_for_open_vacancy(self):
        self.patch(f"vacancies/{self.vacancy['id']}/", {"status": "closed"})
        with frozen(at(20)):
            response = self.post("candidates/", {"last_name": "А", "first_name": "Б", "phone": "+996555",
                                                 "vacancy": self.vacancy["id"]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("vacancy", response.data)

    def test_filter_and_count(self):
        self.new_candidate()
        data = self.get("vacancies/", {"status": "open"}).data
        self.assertEqual(data["results"][0]["candidates_count"], 1)
        self.assertEqual(self.get("vacancies/", {"status": "closed"}).data["count"], 0)


class CandidateTests(RecruitmentFixture):
    def test_create_with_defaults_and_history(self):
        candidate = self.new_candidate(notes="Опыт 3 года")
        self.assertEqual(candidate["status"], "new")
        self.assertEqual(candidate["added_on"], "2026-10-20")
        self.assertEqual(candidate["responsible_info"]["id"], self.hr.pk)
        self.assertEqual(candidate["position_label"], "Менеджер по продажам")
        self.assertEqual([s["value"] for s in candidate["allowed_statuses"]], ["contacted", "rejected", "withdrawn"])
        history = self.get(f"candidates/{candidate['id']}/history/").data
        self.assertEqual({h["kind"] for h in history}, {"candidate_created", "candidate_status"})

    def test_validation(self):
        with frozen(at(20)):
            no_contacts = self.post("candidates/", {"last_name": "А", "first_name": "Б", "vacancy": self.vacancy["id"]})
            no_position = self.post("candidates/", {"last_name": "А", "first_name": "Б", "email": "a@b.kg"})
            bad_phone = self.post("candidates/", {"last_name": "А", "first_name": "Б", "phone": "call me",
                                                  "position": "SMM"})
            future = self.post("candidates/", {"last_name": "А", "first_name": "Б", "email": "a@b.kg",
                                               "position": "SMM", "added_on": "2026-10-25"})
            bad_status = self.post("candidates/", {"last_name": "А", "first_name": "Б", "email": "a@b.kg",
                                                   "position": "SMM", "status": "hired"})
        self.assertIn("phone", no_contacts.data)
        self.assertIn("vacancy", no_position.data)
        self.assertIn("phone", bad_phone.data)
        self.assertIn("added_on", future.data)
        # Этап при создании не задаётся — всегда «Новый кандидат».
        self.assertEqual(bad_status.status_code, 201)
        self.assertEqual(bad_status.data["status"], "new")

    def test_edit_logs_changed_fields_and_ignores_status(self):
        candidate = self.new_candidate()
        response = self.patch(f"candidates/{candidate['id']}/", {"phone": "+996 700 000 000", "status": "hired",
                                                                 "notes": "Перезвонить"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "new")
        entry = HRActivity.objects.filter(kind="candidate_updated").get()
        self.assertIn("Телефон", entry.message)
        self.assertNotIn("700", entry.message)  # значения контактов в журнал не пишутся

    def test_manual_transitions(self):
        cid = self.new_candidate()["id"]
        self.assertEqual(self.post(f"candidates/{cid}/status/", {"status": "offer"}).data["code"],
                         "invalid_transition")
        self.assertEqual(self.post(f"candidates/{cid}/status/", {"status": "hired"}).data["code"], "hire_required")
        self.assertEqual(self.post(f"candidates/{cid}/status/", {"status": "interview_done"}).data["code"],
                         "interview_required")
        with frozen(at(20, 11)):
            self.assertEqual(self.post(f"candidates/{cid}/status/", {"status": "contacted"}).status_code, 200)
            self.assertEqual(self.post(f"candidates/{cid}/status/", {"status": "withdrawn"}).status_code, 200)
            self.assertEqual(self.post(f"candidates/{cid}/status/", {"status": "new"}).status_code, 200)
        transitions = list(HRActivity.objects.filter(candidate_id=cid, kind="candidate_status")
                           .order_by("created_at", "id").values_list("from_status", "to_status"))
        self.assertEqual(transitions, [("", "new"), ("new", "contacted"), ("contacted", "withdrawn"),
                                       ("withdrawn", "new")])

    def test_notes_history(self):
        cid = self.new_candidate()["id"]
        self.assertEqual(self.post(f"candidates/{cid}/notes/", {"text": "  "}).status_code, 400)
        note = self.post(f"candidates/{cid}/notes/", {"text": "Позвонил, договорились о встрече"})
        self.assertEqual(note.status_code, 201)
        history = self.get(f"candidates/{cid}/history/").data
        self.assertEqual(history[0]["message"], "Позвонил, договорились о встрече")
        self.assertEqual(history[0]["actor"], "Hr Test")

    def test_search_filters_and_ordering(self):
        a = self.new_candidate(last_name="Абдыкадыров", source="referral")
        b = self.new_candidate(last_name="Бекова", vacancy=None, position="SMM-специалист", email="b@x.kg",
                               phone="", source="social")
        self.assertEqual([r["id"] for r in self.get("candidates/", {"search": "Бекова"}).data["results"]], [b["id"]])
        self.assertEqual([r["id"] for r in self.get("candidates/", {"source": "referral"}).data["results"]], [a["id"]])
        self.assertEqual([r["id"] for r in self.get("candidates/", {"position": "SMM"}).data["results"]], [b["id"]])
        self.assertEqual([r["id"] for r in self.get("candidates/", {"vacancy": self.vacancy["id"]}).data["results"]],
                         [a["id"]])
        ordered = self.get("candidates/", {"ordering": "last_name"}).data["results"]
        self.assertEqual([r["id"] for r in ordered], [a["id"], b["id"]])
        self.post(f"candidates/{a['id']}/status/", {"status": "rejected"})
        self.assertEqual([r["id"] for r in self.get("candidates/", {"active": "true"}).data["results"]], [b["id"]])


class InterviewTests(RecruitmentFixture):
    def test_schedule_sets_stage_and_validates(self):
        cid = self.new_candidate()["id"]
        self.assertEqual(self.schedule(cid, at(19)).data["code"], "past_time")
        self.assertIn("meeting_url", self.schedule(cid, at(22), meeting_url="").data)
        self.assertIn("location", self.schedule(cid, at(22), format="in_person", meeting_url="").data)
        response = self.schedule(cid, at(22, 15))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["vacancy_info"]["title"], "Менеджер по продажам")
        self.assertEqual(response.data["scheduled_at"], "2026-10-22T15:00:00+06:00")
        self.assertEqual(self.status_of(cid), "interview_scheduled")

    def test_duplicate_warning_and_confirm(self):
        cid = self.new_candidate()["id"]
        self.schedule(cid, at(22, 15))
        duplicate = self.schedule(cid, at(22, 16))
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.data["code"], "interview_conflict")
        self.assertEqual(duplicate.data["conflicts"][0]["type"], "candidate")
        self.assertEqual(Interview.objects.count(), 1)
        confirmed = self.schedule(cid, at(22, 16), confirm=True)
        self.assertEqual(confirmed.status_code, 201)
        # Далёкое время — не дубль.
        self.assertEqual(self.schedule(cid, at(23, 15)).status_code, 201)

    def test_interviewer_overlap_warning(self):
        a = self.new_candidate()["id"]
        b = self.new_candidate(last_name="Другой", phone="+996 700 1")["id"]
        self.schedule(a, at(22, 15))
        busy = self.schedule(b, at(22, 15, 30))
        self.assertEqual(busy.status_code, 409)
        self.assertEqual(busy.data["conflicts"][0]["type"], "interviewer")
        self.assertEqual(self.schedule(b, at(22, 16)).status_code, 201)  # встречи стыкуются

    def test_reschedule_and_cancel(self):
        cid = self.new_candidate()["id"]
        iid = self.schedule(cid, at(22, 15)).data["id"]
        with frozen(at(21)):
            moved = self.patch(f"interviews/{iid}/", {"scheduled_at": at(24, 11).isoformat(), "notes": "Перенос"})
            past = self.patch(f"interviews/{iid}/", {"scheduled_at": at(20, 11).isoformat()})
        self.assertEqual(moved.status_code, 200, moved.data)
        self.assertEqual(moved.data["reschedule_count"], 1)
        self.assertEqual(past.data["code"], "past_time")
        entry = HRActivity.objects.get(kind="interview_rescheduled")
        self.assertEqual(entry.message, "22.10.2026 15:00 → 24.10.2026 11:00")

        self.assertEqual(self.post(f"interviews/{iid}/cancel/", {"reason": ""}).status_code, 400)
        with frozen(at(21)):
            cancelled = self.post(f"interviews/{iid}/cancel/", {"reason": "Кандидат заболел"})
        self.assertEqual(cancelled.data["status"], "cancelled")
        # Встреч не осталось — кандидат возвращается на этап до собеседования.
        self.assertEqual(self.status_of(cid), "contacted")
        self.assertEqual(self.post(f"interviews/{iid}/cancel/", {"reason": "ещё раз"}).data["code"], "not_scheduled")
        self.assertEqual(self.patch(f"interviews/{iid}/", {"notes": "x"}).data["code"], "not_scheduled")

    def test_result_moves_stage(self):
        cases = {"offer": "offer", "reject": "rejected", "awaiting_decision": "awaiting_decision",
                 "next_interview": "interview_done"}
        for step, expected in cases.items():
            cid = self.new_candidate(last_name=step, phone=f"+996 {len(step)}00")["id"]
            iid = self.schedule(cid, at(22, 15)).data["id"]
            with frozen(at(22, 14)):
                early = self.post(f"interviews/{iid}/result/", {"result": "passed", "next_step": step})
            self.assertEqual(early.data["code"], "not_started")
            with frozen(at(22, 16)):
                response = self.post(f"interviews/{iid}/result/", {
                    "result": "passed", "next_step": step, "result_comment": "Хорошо", "next_step_date": "2026-10-25"})
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["status"], "completed")
            self.assertEqual(response.data["next_step_label"], dict(Interview.NextStep.choices)[step])
            self.assertEqual(self.status_of(cid), expected, step)
            path = list(HRActivity.objects.filter(candidate_id=cid, kind="candidate_status")
                        .order_by("id").values_list("to_status", flat=True))
            self.assertIn("interview_done", path)

    def test_result_validation(self):
        cid = self.new_candidate()["id"]
        iid = self.schedule(cid, at(22, 15)).data["id"]
        with frozen(at(22, 16)):
            self.assertEqual(self.post(f"interviews/{iid}/result/", {"result": "x", "next_step": "offer"}).status_code,
                             400)
            early_date = self.post(f"interviews/{iid}/result/", {"result": "passed", "next_step": "offer",
                                                                  "next_step_date": "2026-10-01"})
        self.assertEqual(early_date.data["code"], "invalid_date")

    def test_rejection_cancels_open_interviews(self):
        cid = self.new_candidate()["id"]
        iid = self.schedule(cid, at(22, 15)).data["id"]
        self.post(f"candidates/{cid}/status/", {"status": "rejected"})
        self.assertEqual(Interview.objects.get(pk=iid).status, "cancelled")
        self.assertEqual(self.schedule(cid, at(23)).data["code"], "not_schedulable")

    def test_calendar_range_and_filters(self):
        a = self.new_candidate()["id"]
        other_vacancy = self.post("vacancies/", {"title": "Маркетолог"}).data
        b = self.new_candidate(last_name="Маркетолог", phone="+996 1", vacancy=other_vacancy["id"])["id"]
        hr_interviewer = self.hr.pk
        self.schedule(a, at(22, 15))
        self.schedule(b, at(23, 10), interviewer=hr_interviewer)
        week = self.get("interviews/", {"date_from": "2026-10-19", "date_to": "2026-10-25"}).data
        self.assertEqual(len(week), 2)
        day = self.get("interviews/", {"date_from": "2026-10-23", "date_to": "2026-10-23"}).data
        self.assertEqual([i["candidate"] for i in day], [b])
        by_interviewer = self.get("interviews/", {"date_from": "2026-10-01", "date_to": "2026-10-31",
                                                  "interviewer": hr_interviewer}).data
        by_vacancy = self.get("interviews/", {"date_from": "2026-10-01", "date_to": "2026-10-31",
                                              "vacancy": other_vacancy["id"]}).data
        by_status = self.get("interviews/", {"date_from": "2026-10-01", "date_to": "2026-10-31",
                                             "status": "cancelled"}).data
        self.assertEqual([i["candidate"] for i in by_interviewer], [b])
        self.assertEqual([i["candidate"] for i in by_vacancy], [b])
        self.assertEqual(by_status, [])
        self.assertEqual(len(self.get("interviews/", {"candidate": a}).data), 1)
        self.assertEqual(self.get("interviews/").status_code, 400)
        self.assertEqual(self.get("interviews/", {"date_from": "2026-01-01", "date_to": "2026-12-31"}).status_code,
                         400)


class HireTests(RecruitmentFixture):
    def offer_candidate(self, **over) -> int:
        cid = self.new_candidate(email="bakyt@mail.kg", **over)["id"]
        iid = self.schedule(cid, at(22, 15)).data["id"]
        with frozen(at(22, 16)):
            self.post(f"interviews/{iid}/result/", {"result": "passed", "next_step": "offer"})
        return cid

    def hire(self, cid, **over):
        body = {"username": "bakyt", "role": "sales_manager", "password": PASSWORD, "password_confirm": PASSWORD}
        body.update(over)
        with frozen(at(23, 10)):
            return self.post(f"candidates/{cid}/hire/", body)

    def test_hire_creates_one_account(self):
        cid = self.offer_candidate()
        response = self.hire(cid)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "hired")
        user = User.objects.get(username="bakyt")
        self.assertEqual((user.email, user.first_name, user.last_name, user.role),
                         ("bakyt@mail.kg", "Бакыт", "Асанов", "sales_manager"))
        self.assertTrue(user.check_password(PASSWORD))
        self.assertFalse(user.is_staff or user.is_superuser)
        self.assertEqual(response.data["hired_user_info"]["id"], user.pk)
        # Повторный найм того же кандидата — отказ, второго аккаунта нет.
        again = self.hire(cid, username="bakyt2", email="other@mail.kg")
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.data["code"], "already_hired")
        self.assertFalse(User.objects.filter(username="bakyt2").exists())
        self.assertEqual(self.status_of(cid), "hired")
        self.assertEqual(self.post(f"candidates/{cid}/status/", {"status": "rejected"}).status_code, 400)
        # Карточка сотрудника показывает, из какого кандидата он принят.
        card = self.get(f"employees/{user.pk}/").data
        self.assertEqual(card["hired_from"]["id"], cid)
        self.assertIn("employee_created", [h["kind"] for h in card["history"]])

    def test_hire_requires_offer_and_allowed_role(self):
        cid = self.new_candidate(email="x@mail.kg")["id"]
        self.assertEqual(self.hire(cid).data["code"], "offer_required")
        cid = self.offer_candidate(last_name="Другой", phone="+996 2")
        for role in ("dop", "rom", "accountant", "operations_director", "admin", "director", "hr_manager",
                     "teacher", "assistant"):
            response = self.hire(cid, role=role)
            self.assertEqual(response.status_code, 400, role)
            self.assertIn("role", response.data)
        self.assertEqual(self.hire(cid, password_confirm="nope").status_code, 400)
        self.assertEqual(self.hire(cid, username="hr").status_code, 400)  # логин занят
        self.assertEqual(self.status_of(cid), "offer")
        self.assertEqual(User.objects.filter(role="sales_manager").count(), 0)


class ReportTests(RecruitmentFixture):
    def setUp(self):
        super().setUp()
        with frozen(at(1, 9)):
            self.referral = self.post("vacancies/", {"title": "Маркетолог"}).data
        # 20.10: два кандидата, 21.10: ещё один (рекомендация, другая вакансия).
        self.a = self.new_candidate(moment=at(20, 9))["id"]
        self.b = self.new_candidate(moment=at(20, 9), last_name="Бекова", phone="+996 2")["id"]
        self.c = self.new_candidate(moment=at(21, 9), last_name="Ценова", phone="+996 3", source="referral",
                                    vacancy=self.referral["id"], added_on="2026-10-21")["id"]
        with frozen(at(20, 10)):
            self.post(f"candidates/{self.b}/status/", {"status": "contacted"})
        ia = self.schedule(self.a, at(21, 11), now=at(20, 12)).data["id"]
        ib = self.schedule(self.b, at(21, 15), now=at(20, 12)).data["id"]
        ic = self.schedule(self.c, at(22, 11), now=at(21, 9, 30)).data["id"]
        with frozen(at(21, 12)):
            self.post(f"interviews/{ia}/result/", {"result": "passed", "next_step": "offer"})
        with frozen(at(21, 13)):
            self.patch(f"interviews/{ib}/", {"scheduled_at": at(23, 15).isoformat()})
            self.post(f"interviews/{ic}/cancel/", {"reason": "Не смог прийти"})
        with frozen(at(21, 14)):
            self.post(f"candidates/{self.c}/status/", {"status": "rejected"})
        with frozen(at(21, 18)):
            self.post(f"candidates/{self.a}/hire/", {"username": "asanov", "email": "asanov@mail.kg",
                                                     "role": "sales_manager", "password": PASSWORD,
                                                     "password_confirm": PASSWORD})

    def test_daily(self):
        with frozen(at(21, 20)):
            day = self.get("reports/daily/", {"date": "2026-10-21"}).data
        self.assertEqual(day["new_candidates"], 1)
        self.assertEqual(day["interviews_planned"], 1)  # 15:00 перенесено на 23.10
        self.assertEqual(day["interviews_conducted"], 1)
        self.assertEqual(day["interviews_rescheduled"], 1)
        self.assertEqual(day["interviews_cancelled"], 1)
        self.assertEqual(day["offers"], 1)
        self.assertEqual(day["hired"], 1)
        self.assertEqual(day["rejected"], 1)
        self.assertEqual(day["decisions"], 3)
        self.assertEqual(day["awaiting_decision_now"], 0)
        filtered = self.get("reports/daily/", {"date": "2026-10-21", "vacancy": self.referral["id"]}).data
        self.assertEqual((filtered["new_candidates"], filtered["hired"], filtered["rejected"]), (1, 0, 1))
        self.assertEqual(self.get("reports/daily/", {"date": "21.10.2026"}).status_code, 400)

    def test_monthly(self):
        month = self.get("reports/monthly/", {"month": "2026-10"}).data
        self.assertEqual(month["new_candidates"], 3)
        self.assertEqual(month["interviews_conducted"], 1)
        self.assertEqual(month["interviews_cancelled"], 1)
        self.assertEqual(month["interviews_rescheduled"], 1)
        self.assertEqual((month["hired"], month["rejected"], month["offers"]), (1, 1, 1))
        by_stage = {row["status"]: row["count"] for row in month["by_stage"]}
        self.assertEqual((by_stage["hired"], by_stage["interview_scheduled"], by_stage["rejected"]), (1, 1, 1))
        funnel = {row["status"]: (row["count"], row["conversion_percent"]) for row in month["funnel"]}
        self.assertEqual(funnel["new"], (3, None))
        self.assertEqual(funnel["interview_scheduled"], (3, 100.0))
        self.assertEqual(funnel["interview_done"], (1, 33.3))
        self.assertEqual(funnel["hired"], (1, 100.0))
        self.assertEqual({r["label"]: r["count"] for r in month["by_source"]},
                         {"Сайт вакансий": 2, "Рекомендация": 1})
        self.assertEqual({r["label"]: r["count"] for r in month["by_vacancy"]},
                         {"Менеджер по продажам": 2, "Маркетолог": 1})
        self.assertEqual(month["average_days_to_hire"], 1.0)
        durations = {row["status"]: row for row in month["stage_durations"]}
        self.assertEqual(durations["offer"]["average_hours"], 6.0)  # 12:00 → 18:00
        by_source = self.get("reports/monthly/", {"month": "2026-10", "source": "referral"}).data
        self.assertEqual(by_source["new_candidates"], 1)
        by_responsible = self.get("reports/monthly/", {"month": "2026-10", "responsible": self.interviewer.pk}).data
        self.assertEqual(by_responsible["new_candidates"], 0)
        by_position = self.get("reports/monthly/", {"month": "2026-10", "position": "Маркет"}).data
        self.assertEqual(by_position["new_candidates"], 1)
        self.assertEqual(self.get("reports/monthly/", {"month": "2026-13"}).status_code, 400)
        november = self.get("reports/monthly/", {"month": "2026-11"}).data
        self.assertEqual((november["new_candidates"], november["average_days_to_hire"]), (0, None))

    def test_csv_export(self):
        response = self.get("reports/monthly/", {"month": "2026-10", "export": "csv"})
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("hr-monthly-2026-10.csv", response["Content-Disposition"])
        text = response.content.decode("utf-8-sig")
        self.assertIn("Новые кандидаты;3", text)
        self.assertIn("Рекомендация;1", text)
        daily = self.get("reports/daily/", {"date": "2026-10-21", "export": "csv"}).content.decode("utf-8-sig")
        self.assertIn("Приняты на работу;1", daily)
        self.assertIn("Ценова", daily)

    def test_csv_escapes_formulas(self):
        self.new_candidate(moment=at(21, 9), last_name="=HYPERLINK(1)", phone="+996 9", added_on="2026-10-21")
        daily = self.get("reports/daily/", {"date": "2026-10-21", "export": "csv"}).content.decode("utf-8-sig")
        self.assertIn("'=HYPERLINK(1)", daily)

    def test_dashboard(self):
        make("old_sales", User.Role.SALES_MANAGER)
        with frozen(at(21, 20)):
            data = self.get("dashboard/").data
        self.assertEqual(data["employees_active"], 3)  # rop, asanov, old_sales
        self.assertEqual(data["candidates_total"], 3)
        self.assertEqual(data["hired"], 1)
        self.assertEqual(data["rejected"], 1)
        self.assertEqual(data["interviews_scheduled"], 1)
        self.assertEqual(data["vacancies_open"], 2)
        self.assertEqual([i["candidate"]["id"] for i in data["upcoming_interviews"]], [self.b])
        self.assertEqual(data["recent_activity"][0]["kind"], "candidate_hired")
        with frozen(at(23, 9)):
            self.assertEqual(self.get("dashboard/").data["interviews_today"], 1)
