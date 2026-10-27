"""HR-кабинет: доступ, вакансии, отклики и этапы, заметки, собеседования,
напоминания, найм с созданием учётной записи и согласованием, удаление
персональных данных."""
from __future__ import annotations

import io

from django.contrib.auth.hashers import check_password
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.recruitment.models import AccountRequest, Application, Candidate, HRActivity, InternalNote, Interview
from apps.recruitment.services import hiring
from apps.users.models import User

from .base import API, PASSWORD, RecruitmentFixture, at, frozen, make, pdf_file


class AccessTests(RecruitmentFixture):
    URLS = ("dashboard/", "meta/", "reminders/", "vacancies/", "candidates/", "applications/",
            "applications/board/", "account-requests/", "interviews/?date_from=2026-10-01&date_to=2026-10-31",
            "reports/daily/", "reports/monthly/", "employees/")

    def test_only_active_hr_reaches_hr_api(self):
        app = self.new_application()
        for url in self.URLS:
            self.assertEqual(self.get(url).status_code, 200, url)
        detail_urls = (f"applications/{app['id']}/", f"candidates/{app['candidate']}/",
                       f"candidates/{app['candidate']}/notes/", f"candidates/{app['candidate']}/history/")
        others = [make(f"u_{role}", role) for role in (
            User.Role.ADMIN, User.Role.TEACHER, User.Role.TEAM_LEAD, User.Role.ASSISTANT, User.Role.ACCOUNTANT,
            User.Role.DIRECTOR, User.Role.DOP, User.Role.ROP, User.Role.ROM, User.Role.OPERATIONS_DIRECTOR,
            User.Role.SALES_MANAGER, User.Role.MARKETING)]
        others.append(make("hr_off", User.Role.HR_MANAGER, is_active=False))
        for user in others:
            client = APIClient()
            client.force_authenticate(user)
            for url in (*self.URLS, *detail_urls):
                with self.subTest(role=user.role, url=url):
                    self.assertIn(client.get(f"{API}/{url}").status_code, (401, 403))
            with self.subTest(role=user.role, action="status"):
                response = client.post(f"{API}/applications/{app['id']}/status/", {"status": "screening"},
                                       format="json")
                self.assertIn(response.status_code, (401, 403))
        self.assertEqual(self.status_of(app["id"]), "new")
        anon = APIClient()
        for url in self.URLS:
            self.assertEqual(anon.get(f"{API}/{url}").status_code, 401, url)

    def test_hr_api_reachable_with_jwt_through_isolation(self):
        client = APIClient()
        token = client.post("/api/v1/auth/login/", {"username": "hr", "password": PASSWORD}, format="json")
        self.assertEqual(token.status_code, 200, token.data)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.data['access']}")
        self.assertEqual(client.get(f"{API}/applications/").status_code, 200)
        # Сотрудник с базовым доступом видит публичный сайт и с токеном.
        self.assertEqual(client.get("/api/v1/public/careers/vacancies/").status_code, 200)


class VacancyTests(RecruitmentFixture):
    def test_created_as_draft_with_slug_and_never_auto_published(self):
        vacancy = self.new_vacancy(title="Менеджер по продажам", status="published")
        self.assertEqual(vacancy["status"], "draft")
        self.assertIsNone(vacancy["published_at"])
        self.assertEqual(vacancy["slug"], "menedzher-po-prodazham-2")
        self.assertEqual(vacancy["allowed_statuses"], [{"value": "published", "label": "Опубликована"},
                                                       {"value": "closed", "label": "Закрыта"}])

    def test_lifecycle_keeps_dates_and_history(self):
        vacancy_id = self.vacancy["id"]
        self.assertEqual(self.vacancy["status"], "draft")  # создана черновиком
        detail = self.get(f"vacancies/{vacancy_id}/").data
        self.assertEqual(detail["status"], "published")
        published_at = detail["published_at"]
        with frozen(at(5)):
            self.assertEqual(self.publish(vacancy_id, "paused")["status"], "paused")
            self.assertEqual(self.publish(vacancy_id)["published_at"], published_at)
        app = self.apply_and_get()
        with frozen(at(25)):
            closed = self.publish(vacancy_id, "closed")
        self.assertIsNotNone(closed["closed_at"])
        archived = self.publish(vacancy_id, "archived")
        self.assertIsNotNone(archived["archived_at"])
        bad = self.post(f"vacancies/{vacancy_id}/status/", {"status": "published"})
        self.assertEqual((bad.status_code, bad.data["code"]), (400, "invalid_transition"))
        # Отклики и история после закрытия и архива остаются.
        self.assertTrue(Application.objects.filter(pk=app.pk).exists())
        self.assertEqual(self.get(f"vacancies/{vacancy_id}/").data["applications_count"], 1)
        kinds = list(HRActivity.objects.filter(vacancy_id=vacancy_id, kind="vacancy_status")
                     .values_list("to_status", flat=True))
        self.assertEqual(kinds, ["archived", "closed", "published", "paused", "published"])

    def apply_and_get(self):
        number = self.apply().data["number"]
        return Application.objects.get(number=number)

    def test_publish_requires_content(self):
        vacancy = self.new_vacancy(title="Пустая", description="", requirements="", location="")
        response = self.post(f"vacancies/{vacancy['id']}/status/", {"status": "published"})
        self.assertEqual((response.status_code, response.data["code"]), (400, "incomplete"))
        self.assertEqual(response.data["missing"], ["описание", "требования", "место работы"])

    def test_validation_and_edit(self):
        response = self.post("vacancies/", {**self.vacancy_body(), "salary_min": 90000, "salary_max": 1000})
        self.assertIn("salary_max", response.data)
        response = self.post("vacancies/", {**self.vacancy_body(), "slug": "Плохой адрес"})
        self.assertIn("slug", response.data)
        response = self.post("vacancies/", {**self.vacancy_body(), "slug": self.vacancy["slug"]})
        self.assertIn("slug", response.data)
        with frozen(at(10)):
            response = self.post("vacancies/", {**self.vacancy_body(), "closes_on": "2026-10-01"})
        self.assertIn("closes_on", response.data)
        response = self.patch(f"vacancies/{self.vacancy['id']}/", {"title": "Старший менеджер",
                                                                   "responsible": self.interviewer.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["responsible_info"]["id"], self.interviewer.pk)
        self.assertEqual(self.client.delete(f"{API}/vacancies/{self.vacancy['id']}/").status_code, 405)

    def vacancy_body(self):
        from .base import VACANCY
        return dict(VACANCY)

    def test_counts_and_filter(self):
        self.apply()
        self.new_application(phone="+996 700 111 222", email="x@mail.kg", first_name="Айгерим")
        row = self.get("vacancies/", {"status": "published"}).data["results"][0]
        self.assertEqual((row["applications_count"], row["active_count"], row["new_count"]), (2, 2, 2))


class ApplicationTests(RecruitmentFixture):
    def test_hr_creates_application_with_history(self):
        app = self.new_application(email="Bakyt@Mail.KG")
        self.assertEqual((app["status"], app["channel"], app["responsible"]), ("new", "hr", self.hr.pk))
        self.assertRegex(app["number"], r"^2026-")
        candidate = Candidate.objects.get(pk=app["candidate"])
        self.assertEqual((candidate.email, candidate.phone_digits), ("bakyt@mail.kg", "996555123456"))
        kinds = set(HRActivity.objects.filter(application_id=app["id"]).values_list("kind", flat=True))
        self.assertEqual(kinds, {"candidate_created", "candidate_status"})

    def test_hr_is_warned_about_existing_contacts(self):
        first = self.new_application()
        response = self.post("applications/", {"first_name": "Бакыт", "phone": "0555 123 456",
                                               "position": "Маркетолог"})
        self.assertEqual((response.status_code, response.data["code"]), (409, "possible_duplicates"))
        self.assertEqual(response.data["matches"][0]["id"], first["candidate"])
        # Существующему кандидату — второй отклик, без нового человека.
        response = self.post("applications/", {"candidate": first["candidate"], "position": "Маркетолог"})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Candidate.objects.count(), 1)
        # Или явно подтверждённый другой человек.
        response = self.post("applications/", {"first_name": "Бакыт", "phone": "0555 123 456",
                                               "position": "SMM", "confirm_new": True})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Candidate.objects.count(), 2)

    def test_one_active_application_per_vacancy(self):
        first = self.new_application()
        response = self.post("applications/", {"candidate": first["candidate"], "vacancy": self.vacancy["id"]})
        self.assertEqual((response.status_code, response.data["code"]), (409, "duplicate_application"))

    def test_validation(self):
        self.assertIn("first_name", self.post("applications/", {"phone": "+996 555 1", "position": "x"}).data)
        self.assertIn("phone", self.post("applications/", {"first_name": "A", "position": "x"}).data)
        self.assertIn("vacancy", self.post("applications/", {"first_name": "A", "phone": "+996 555 000 111"}).data)
        closed = self.new_vacancy(title="Закрытая")
        self.publish(closed["id"])
        self.publish(closed["id"], "closed")
        response = self.post("applications/", {"first_name": "A", "phone": "+996 555 000 111", "vacancy": closed["id"]})
        self.assertEqual(response.data["code"], "vacancy_closed")

    def test_manual_transitions_and_history(self):
        app = self.new_application()
        self.assertEqual([s["value"] for s in app["allowed_statuses"]], ["screening", "shortlisted", "rejected",
                                                                         "withdrawn"])
        self.move(app["id"], "screening", "shortlisted")
        for target, code in (("hired", "hire_required"), ("interview_done", "interview_required"),
                             ("offer", "invalid_transition")):
            response = self.post(f"applications/{app['id']}/status/", {"status": target})
            self.assertEqual((response.status_code, response.data["code"]), (400, code))
        with frozen(at(21)):
            self.post(f"applications/{app['id']}/status/", {"status": "rejected", "comment": "Нет опыта"})
        self.assertEqual(self.status_of(app["id"]), "rejected")
        rows = list(HRActivity.objects.filter(application_id=app["id"], kind="candidate_status")
                    .order_by("created_at", "id").values_list("from_status", "to_status", "actor_id"))
        self.assertEqual(rows, [("", "new", self.hr.pk), ("new", "screening", self.hr.pk),
                                ("screening", "shortlisted", self.hr.pk), ("shortlisted", "rejected", self.hr.pk)])
        # Отказ не удаляет ни отклик, ни историю; вернуть в работу — на просмотр.
        self.move(app["id"], "screening")
        self.assertEqual(self.status_of(app["id"]), "screening")

    def test_list_filters_search_and_board(self):
        a = self.new_application(moment=at(5))
        self.new_application(moment=at(18), first_name="Айгерим", last_name="Садыкова", phone="+996 700 111 222",
                             email="aigerim@mail.kg", vacancy=None, position="Маркетолог", source="referral")
        self.move(a["id"], "screening")
        list_ = lambda **p: [r["candidate_info"]["full_name"] for r in self.get("applications/", p).data["results"]]  # noqa: E731
        self.assertEqual(list_(search="Садык"), ["Садыкова Айгерим"])
        self.assertEqual(list_(search="700111"), ["Садыкова Айгерим"])
        self.assertEqual(list_(search=a["number"]), ["Асанов Бакыт"])
        self.assertEqual(list_(status="screening"), ["Асанов Бакыт"])
        self.assertEqual(list_(vacancy=self.vacancy["id"]), ["Асанов Бакыт"])
        self.assertEqual(list_(source="referral"), ["Садыкова Айгерим"])
        self.assertEqual(list_(date_from="2026-10-10"), ["Садыкова Айгерим"])
        self.assertEqual(list_(date_to="2026-10-10"), ["Асанов Бакыт"])
        self.assertEqual(list_(responsible=self.interviewer.pk), [])
        board = self.get("applications/board/").data["columns"]
        counts = {column["status"]: column["count"] for column in board}
        self.assertEqual((counts["new"], counts["screening"]), (1, 1))
        self.assertEqual(len(board), 11)

    def test_candidates_list_and_card(self):
        app = self.new_application()
        self.post("applications/", {"candidate": app["candidate"], "position": "Маркетолог"})
        row = self.get("candidates/", {"search": "Асанов"}).data["results"][0]
        self.assertEqual((row["applications_count"], row["active_count"]), (2, 2))
        card = self.get(f"candidates/{app['candidate']}/").data
        self.assertEqual(len(card["applications"]), 2)
        response = self.patch(f"candidates/{app['candidate']}/", {"phone": "0700 99 88 77", "city": "Ош"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Candidate.objects.get(pk=app["candidate"]).phone_digits, "996700998877")
        self.assertEqual(self.patch(f"candidates/{app['candidate']}/", {"phone": "буквы"}).status_code, 400)

    def test_internal_notes(self):
        app = self.new_application()
        response = self.post(f"candidates/{app['candidate']}/notes/", {"text": "Позвонить после 18:00",
                                                                       "application": app["id"]})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["application_number"], app["number"])
        self.assertEqual(self.post(f"candidates/{app['candidate']}/notes/", {"text": "  "}).status_code, 400)
        notes = self.get(f"candidates/{app['candidate']}/notes/").data
        self.assertEqual([n["text"] for n in notes], ["Позвонить после 18:00"])
        self.assertEqual(notes[0]["author_info"]["id"], self.hr.pk)
        history = self.get(f"candidates/{app['candidate']}/history/").data
        self.assertIn("candidate_note", [h["kind"] for h in history])
        # Текст заметки не дублируется в общую историю.
        self.assertNotIn("Позвонить после 18:00", [h["message"] for h in history])

    def test_responsible_and_edit(self):
        app = self.new_application()
        response = self.patch(f"applications/{app['id']}/", {"responsible": self.interviewer.pk})
        self.assertEqual(response.data["responsible_info"]["id"], self.interviewer.pk)
        self.assertTrue(HRActivity.objects.filter(application_id=app["id"], kind="candidate_updated").exists())


class InterviewTests(RecruitmentFixture):
    def setUp(self):
        super().setUp()
        self.app = self.new_application()

    def test_schedule_sets_stage_and_validates(self):
        response = self.schedule(self.app["id"], at(22, 15))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.status_of(self.app["id"]), "interview_scheduled")
        self.assertEqual(response.data["application_info"]["number"], self.app["number"])
        self.assertEqual(self.schedule(self.app["id"], at(19, 15)).data["code"], "past_time")
        self.assertIn("meeting_url", self.schedule(self.app["id"], at(23, 15), meeting_url="").data)
        self.assertIn("location", self.schedule(self.app["id"], at(23, 15), format="in_person").data)

    def test_duplicate_and_interviewer_warnings(self):
        self.schedule(self.app["id"], at(22, 15))
        response = self.schedule(self.app["id"], at(22, 16))
        self.assertEqual((response.status_code, response.data["code"]), (409, "interview_conflict"))
        self.assertEqual(response.data["conflicts"][0]["type"], "candidate")
        self.assertEqual(self.schedule(self.app["id"], at(22, 16), confirm=True).status_code, 201)
        other = self.new_application(first_name="Айгерим", phone="+996 700 111 222", email="a@mail.kg")
        response = self.schedule(other["id"], at(22, 15, 30))
        self.assertEqual(response.data["conflicts"][0]["type"], "interviewer")

    def test_reschedule_keeps_old_meeting(self):
        first = self.schedule(self.app["id"], at(22, 15)).data
        with frozen(at(21, 9)):
            response = self.patch(f"interviews/{first['id']}/", {"scheduled_at": at(23, 11).isoformat()})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotEqual(response.data["id"], first["id"])
        self.assertEqual(response.data["reschedule_count"], 1)
        self.assertEqual(response.data["status"], "scheduled")
        old = Interview.objects.get(pk=first["id"])
        self.assertEqual((old.status, old.rescheduled_to_id), ("rescheduled", response.data["id"]))
        self.assertEqual(self.status_of(self.app["id"]), "interview_scheduled")
        entry = HRActivity.objects.get(kind="interview_rescheduled")
        self.assertEqual(entry.message, "22.10.2026 15:00 → 23.10.2026 11:00")
        # Изменение без нового времени — та же встреча.
        with frozen(at(21, 9)):
            same = self.patch(f"interviews/{response.data['id']}/", {"notes": "Взять портфолио"})
        self.assertEqual(same.data["id"], response.data["id"])
        with frozen(at(21, 9)):
            again = self.patch(f"interviews/{first['id']}/", {"notes": "x"})
        self.assertEqual(again.data["code"], "not_scheduled")

    def test_cancel_returns_stage(self):
        interview = self.schedule(self.app["id"], at(22, 15)).data
        with frozen(at(21)):
            self.assertEqual(self.post(f"interviews/{interview['id']}/cancel/", {"reason": " "}).status_code, 400)
            response = self.post(f"interviews/{interview['id']}/cancel/", {"reason": "Кандидат заболел"})
        self.assertEqual(response.data["status"], "cancelled")
        self.assertEqual(self.status_of(self.app["id"]), "shortlisted")

    def test_no_show_without_evaluation(self):
        interview = self.schedule(self.app["id"], at(22, 15)).data
        with frozen(at(22, 14)):
            self.assertEqual(self.post(f"interviews/{interview['id']}/no-show/").data["code"], "not_started")
        with frozen(at(22, 16)):
            response = self.post(f"interviews/{interview['id']}/no-show/", {"comment": "Не вышел на связь"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data["status"], response.data["overall_rating"]), ("no_show", None))
        self.assertEqual(self.status_of(self.app["id"]), "shortlisted")

    def test_result_requires_evaluation_and_moves_stage(self):
        interview = self.schedule(self.app["id"], at(22, 15)).data
        self.assertEqual(self.result(interview["id"], at(22, 14)).data["code"], "not_started")
        missing = self.result(interview["id"], at(22, 16), overall_rating=None)
        self.assertEqual(missing.status_code, 400)
        self.assertIn("overall_rating", missing.data)
        self.assertIn("skills_rating", self.result(interview["id"], at(22, 16), skills_rating=7).data)
        response = self.result(interview["id"], at(22, 16), next_step="next_interview", strengths="Опыт",
                               concerns="Нет CRM", next_step_date="2026-10-25")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual((response.data["overall_rating"], response.data["skills_rating"]), (4, 5))
        self.assertEqual((response.data["strengths"], response.data["concerns"]), ("Опыт", "Нет CRM"))
        self.assertEqual(self.status_of(self.app["id"]), "next_stage")
        stages = list(HRActivity.objects.filter(application_id=self.app["id"], kind="candidate_status")
                      .order_by("id").values_list("to_status", flat=True))
        self.assertEqual(stages[-2:], ["interview_done", "next_stage"])
        # Следующий этап — снова собеседование.
        second = self.schedule(self.app["id"], at(25, 11), now=at(23)).data
        self.result(second["id"], at(25, 12), next_step="offer")
        self.assertEqual(self.status_of(self.app["id"]), "offer")

    def test_rejection_cancels_open_interviews(self):
        interview = self.schedule(self.app["id"], at(22, 15)).data
        self.move(self.app["id"], "rejected")
        self.assertEqual(Interview.objects.get(pk=interview["id"]).status, "cancelled")

    def test_calendar(self):
        self.schedule(self.app["id"], at(22, 15))
        self.assertEqual(len(self.get("interviews/", {"date_from": "2026-10-22", "date_to": "2026-10-22"}).data), 1)
        self.assertEqual(len(self.get("interviews/", {"date_from": "2026-10-23", "date_to": "2026-10-30"}).data), 0)
        self.assertEqual(len(self.get("interviews/", {"candidate": self.app["candidate"]}).data), 1)
        self.assertEqual(len(self.get("interviews/", {"application": self.app["id"]}).data), 1)
        self.assertEqual(self.get("interviews/", {"date_from": "2026-01-01", "date_to": "2026-12-01"}).status_code,
                         400)
        self.assertEqual(self.get("interviews/").status_code, 400)
        self.assertEqual(len(self.get("interviews/", {"date_from": "2026-10-01", "date_to": "2026-10-31",
                                                      "status": "completed"}).data), 0)

    def test_reminders(self):
        interview = self.schedule(self.app["id"], at(22, 15)).data
        with frozen(at(22, 9)):
            kinds = [r["kind"] for r in self.get("reminders/").data["results"]]
        self.assertIn("interview_soon", kinds)
        with frozen(at(22, 18)):
            items = self.get("reminders/").data["results"]
        self.assertIn(("interview_result", interview["id"]), [(r["kind"], r.get("interview")) for r in items])
        with frozen(at(22, 18)):
            mine = self.get("reminders/", {"mine": "true"}).data["results"]
        self.assertTrue(any(r["kind"] == "interview_result" for r in mine))  # HR — ответственный за отклик


class HireTests(RecruitmentFixture):
    def setUp(self):
        super().setUp()
        self.app = self.new_application(email="bakyt@mail.kg")
        self.to_offer(self.app["id"])

    def hire_body(self, **over):
        body = {"username": "bakyt", "email": "bakyt@mail.kg", "role": "sales_manager", "password": PASSWORD,
                "password_confirm": PASSWORD}
        body.update(over)
        return body

    def test_hire_creates_one_account_and_keeps_application(self):
        response = self.post(f"applications/{self.app['id']}/hire/", self.hire_body())
        self.assertEqual(response.status_code, 200, response.data)
        user = User.objects.get(username="bakyt")
        self.assertEqual((user.role, user.is_staff, user.is_superuser, user.first_name), ("sales_manager", False,
                                                                                         False, "Бакыт"))
        self.assertTrue(check_password(PASSWORD, user.password))
        self.assertEqual(response.data["status"], "hired")
        self.assertEqual(response.data["hired_user_info"]["id"], user.pk)
        again = self.post(f"applications/{self.app['id']}/hire/", self.hire_body(username="bakyt2", email="b2@mail.kg"))
        self.assertEqual((again.status_code, again.data["code"]), (409, "already_hired"))
        self.assertEqual(User.objects.filter(role="sales_manager").count(), 1)
        self.assertTrue(Application.objects.filter(pk=self.app["id"]).exists())
        employee = self.get(f"employees/{user.pk}/").data
        self.assertEqual(employee["hired_from"]["application"], self.app["id"])
        kinds = set(HRActivity.objects.filter(application_id=self.app["id"]).values_list("kind", flat=True))
        self.assertTrue({"employee_created", "candidate_hired"} <= kinds)

    def test_second_application_of_hired_candidate_cannot_create_another_account(self):
        self.post(f"applications/{self.app['id']}/hire/", self.hire_body())
        other = self.post("applications/", {"candidate": self.app["candidate"], "position": "Маркетолог"}).data
        self.to_offer(other["id"], day=22)
        response = self.post(f"applications/{other['id']}/hire/", self.hire_body(username="b3", email="b3@mail.kg"))
        self.assertEqual(response.data["code"], "already_hired")

    def test_hire_requires_offer_unique_account_and_allowed_role(self):
        fresh = self.new_application(first_name="Айгерим", phone="+996 700 111 222", email="a@mail.kg")
        self.assertEqual(self.post(f"applications/{fresh['id']}/hire/", self.hire_body(username="a")).data["code"],
                         "offer_required")
        make("taken", User.Role.ROP)
        response = self.post(f"applications/{self.app['id']}/hire/", self.hire_body(username="taken"))
        self.assertIn("username", response.data)
        response = self.post(f"applications/{self.app['id']}/hire/", self.hire_body(email="taken@okurmen.kg"))
        self.assertIn("email", response.data)
        for role in ("admin", "director", "accountant", "dop", "operations_director"):
            with self.subTest(role=role):
                response = self.post(f"applications/{self.app['id']}/hire/", self.hire_body(role=role))
                self.assertEqual((response.status_code, response.data["code"]), (403, "role_requires_approval"))
        self.assertFalse(User.objects.filter(username="bakyt").exists())
        self.assertEqual(self.status_of(self.app["id"]), "offer")

    def test_account_request_flow(self):
        body = {"role": "accountant", "username": "bakyt", "email": "bakyt@mail.kg", "first_name": "Бакыт",
                "comment": "Бухгалтер на полставки"}
        for role in ("admin", "director", "rop"):
            self.assertIn("role", self.post(f"applications/{self.app['id']}/account-request/",
                                            {**body, "role": role}).data)
        response = self.post(f"applications/{self.app['id']}/account-request/", body)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(self.post(f"applications/{self.app['id']}/account-request/", body).data["code"],
                         "request_pending")
        self.assertEqual(self.post(f"applications/{self.app['id']}/hire/", self.hire_body()).data["code"],
                         "request_pending")
        self.assertEqual(self.get(f"applications/{self.app['id']}/").data["pending_account_request"]["username"],
                         "bakyt")
        self.assertFalse(User.objects.filter(username="bakyt").exists())
        # HR не может одобрить сам — только администратор.
        request = AccountRequest.objects.get()
        admin = make("boss", User.Role.ADMIN, is_staff=True, is_superuser=True)
        hiring.approve_request(request, admin)
        user = User.objects.get(username="bakyt")
        self.assertEqual((user.role, user.has_usable_password()), ("accountant", False))
        self.assertEqual(self.status_of(self.app["id"]), "hired")
        self.assertEqual(Application.objects.get(pk=self.app["id"]).hired_user, user)
        request.refresh_from_db()
        self.assertEqual((request.status, request.decided_by), ("approved", admin))

    def test_admin_action_in_django_admin(self):
        self.post(f"applications/{self.app['id']}/account-request/",
                  {"role": "operations_director", "username": "trainer", "email": "trainer@mail.kg",
                   "first_name": "Бакыт"})
        request = AccountRequest.objects.get()
        admin = make("boss", User.Role.ADMIN, is_staff=True, is_superuser=True)
        self.client.force_login(admin)
        changelist = "/admin/recruitment/accountrequest/"
        self.assertEqual(self.client.get(changelist).status_code, 200)
        response = self.client.post(changelist, {"action": "approve", "_selected_action": [request.pk]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(User.objects.get(username="trainer").role, "operations_director")
        hr_web = APIClient()
        hr_web.force_login(self.hr)
        self.assertNotEqual(hr_web.get(changelist).status_code, 200)

    def test_hire_as_teacher_creates_trainer_profile(self):
        from apps.users.models import Teacher

        response = self.post(f"applications/{self.app['id']}/hire/", self.hire_body(role="teacher"))
        self.assertEqual(response.status_code, 200, response.data)
        user = User.objects.get(username="bakyt")
        self.assertEqual(user.role, "teacher")
        self.assertTrue(Teacher.objects.filter(user=user).exists())
        self.assertFalse(user.is_staff or user.is_superuser)

    def test_rejected_request(self):
        self.post(f"applications/{self.app['id']}/account-request/",
                  {"role": "dop", "username": "dop1", "email": "dop1@mail.kg", "first_name": "Бакыт"})
        request = AccountRequest.objects.get()
        hiring.reject_request(request, make("boss", User.Role.ADMIN), "Нет ставки")
        self.assertEqual(self.status_of(self.app["id"]), "offer")
        self.assertEqual(self.post(f"applications/{self.app['id']}/hire/", self.hire_body()).status_code, 200)


class EraseTests(RecruitmentFixture):
    def test_erase_personal_data_keeps_statistics(self):
        number = self.apply(resume=pdf_file(), cover_letter="Письмо", city="Бишкек").data["number"]
        application = Application.objects.get(number=number)
        self.post(f"candidates/{application.candidate_id}/notes/", {"text": "Личное"})
        response = self.post(f"candidates/{application.candidate_id}/erase/", {"confirm": True})
        self.assertEqual((response.status_code, response.data["code"]), (409, "active"))
        self.move(application.pk, "rejected")
        self.assertEqual(self.post(f"candidates/{application.candidate_id}/erase/", {"confirm": False}).status_code,
                         400)
        storage, path = application.resume.storage, application.resume.name
        response = self.post(f"candidates/{application.candidate_id}/erase/", {"confirm": True,
                                                                              "reason": "Запрос кандидата"})
        self.assertEqual(response.status_code, 200, response.data)
        candidate = Candidate.objects.get(pk=application.candidate_id)
        self.assertEqual((candidate.first_name, candidate.email, candidate.phone, candidate.city),
                         ("Данные удалены", "", "", ""))
        application.refresh_from_db()
        self.assertEqual((application.cover_letter, application.submitted_data, application.resume.name), ("", {}, ""))
        self.assertFalse(storage.exists(path))
        self.assertEqual(InternalNote.objects.get().text, "[удалено]")
        self.assertEqual(application.status, "rejected")
        self.assertEqual(self.post(f"candidates/{candidate.pk}/erase/", {"confirm": True}).data["code"],
                         "already_erased")

    def test_hired_candidate_is_not_erased(self):
        app = self.new_application()
        self.to_offer(app["id"])
        self.post(f"applications/{app['id']}/hire/", {"username": "b", "email": "b@mail.kg", "role": "rop",
                                                       "password": PASSWORD, "password_confirm": PASSWORD})
        self.assertEqual(self.post(f"candidates/{app['candidate']}/erase/", {"confirm": True}).data["code"], "hired")

    def test_retention_command(self):
        with frozen(at(1, 12, month=1)):
            old = self.new_application(moment=at(1, 12, month=1))
            self.move(old["id"], "rejected", moment=at(1, 12, month=1))
        Candidate.objects.filter(pk=old["candidate"]).update(updated_at=at(1, 12, month=1))
        Application.objects.filter(pk=old["id"]).update(updated_at=at(1, 12, month=1))
        fresh = self.new_application(first_name="Айгерим", phone="+996 700 111 222", email="a@mail.kg")
        with frozen(at(20, month=10)):
            call_command("purge_candidate_data", "--days", "180", "--apply", stdout=io.StringIO())
        self.assertIsNotNone(Candidate.objects.get(pk=old["candidate"]).erased_at)
        self.assertIsNone(Candidate.objects.get(pk=fresh["candidate"]).erased_at)
