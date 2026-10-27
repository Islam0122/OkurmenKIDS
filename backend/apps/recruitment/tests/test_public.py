"""Карьерный сайт: список и страница вакансии, отклик, резюме, защита от
повторов и спама, связывание откликов одного кандидата, граница публичных и
внутренних данных."""
from __future__ import annotations

import importlib
import os
import uuid

from django.core.cache import cache
from django.test import override_settings
from django.urls import clear_url_caches

from apps.recruitment.models import Application, Candidate, HRActivity, Vacancy

from .base import PUBLIC, RecruitmentFixture, at, docx_file, frozen, pdf_file

PUBLIC_CARD_KEYS = {"slug", "title", "department", "location", "work_format", "work_format_label",
                    "employment_type", "employment_type_label", "salary", "summary", "published_at", "closes_on",
                    "is_open"}


class PublicVacancyTests(RecruitmentFixture):
    def list(self, **params):
        with frozen(at(20, 9)):
            return self.anon.get(f"{PUBLIC}/vacancies/", params)

    def test_only_published_and_open_vacancies_are_listed(self):
        draft = self.new_vacancy(title="Маркетолог")
        paused = self.new_vacancy(title="SMM-специалист")
        self.publish(paused["id"])
        self.publish(paused["id"], "paused")
        closed = self.new_vacancy(title="Бухгалтер")
        self.publish(closed["id"])
        self.publish(closed["id"], "closed")
        with frozen(at(1, 9)):
            expired = self.new_vacancy(title="Стажёр", closes_on="2026-10-10")
            self.publish(expired["id"])
        response = self.list()
        self.assertEqual(response.status_code, 200)
        titles = [item["title"] for item in response.data["results"]]
        self.assertEqual(titles, ["Менеджер по продажам"])
        self.assertEqual(response.data["count"], 1)
        self.assertNotIn(draft["title"], titles)
        self.assertEqual(response["Cache-Control"], "public, max-age=60")

    def test_list_returns_only_public_fields(self):
        response = self.list()
        card = response.data["results"][0]
        self.assertEqual(set(card), PUBLIC_CARD_KEYS)
        self.assertEqual(card["salary"], {"min": 40000, "max": 60000, "currency": "KGS", "currency_label": "сом"})
        self.assertEqual(card["published_at"], "2026-10-01")
        for leaked in ("id", "responsible", "applications_count", "status", "created_by"):
            self.assertNotIn(leaked, card)

    def test_hidden_salary_is_not_published(self):
        self.patch(f"vacancies/{self.vacancy['id']}/", {"show_salary": False})
        card = self.list().data["results"][0]
        self.assertIsNone(card["salary"])
        detail = self.anon.get(f"{PUBLIC}/vacancies/{self.vacancy['slug']}/")
        self.assertIsNone(detail.data["salary"])

    def test_search_filters_sorting_and_pagination(self):
        with frozen(at(5, 9)):
            remote = self.new_vacancy(title="Python-разработчик", department="IT", location="Ош",
                                      work_format="remote", employment_type="part_time", salary_max=120000,
                                      salary_min=None)
            self.publish(remote["id"])
        with frozen(at(6, 9)):
            hidden = self.new_vacancy(title="Дизайнер", department="IT", salary_min=500000, salary_max=900000,
                                      show_salary=False)
            self.publish(hidden["id"])
        self.assertEqual([v["title"] for v in self.list(search="python").data["results"]], ["Python-разработчик"])
        self.assertEqual(self.list(department="IT").data["count"], 2)
        self.assertEqual(self.list(location="Ош").data["count"], 1)
        self.assertEqual(self.list(work_format="remote").data["count"], 1)
        self.assertEqual(self.list(employment_type="full_time").data["count"], 2)
        self.assertEqual([v["title"] for v in self.list().data["results"]],
                         ["Дизайнер", "Python-разработчик", "Менеджер по продажам"])
        # Скрытая зарплата не влияет на сортировку: «Дизайнер» — в конце.
        self.assertEqual([v["title"] for v in self.list(ordering="salary_desc").data["results"]],
                         ["Python-разработчик", "Менеджер по продажам", "Дизайнер"])
        page = self.list(page_size=2, page=2).data
        self.assertEqual((page["count"], page["page"], len(page["results"])), (3, 2, 1))
        self.assertEqual(self.list(page="x").status_code, 400)

    def test_filters_endpoint(self):
        response = self.anon.get(f"{PUBLIC}/filters/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["departments"], ["Продажи"])
        self.assertEqual(response.data["locations"], ["Бишкек"])
        self.assertEqual(response.data["work_formats"], [{"value": "office", "label": "В офисе"}])
        self.assertEqual(response.data["total"], 1)

    def test_detail_page(self):
        response = self.anon.get(f"{PUBLIC}/vacancies/{self.vacancy['slug']}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["slug"], "menedzher-po-prodazham")
        self.assertEqual(response.data["requirements"], ["Опыт продаж от 1 года", "Грамотная речь"])
        self.assertEqual(response.data["selection_stages"], ["Собеседование с HR", "Встреча с РОП"])
        self.assertTrue(response.data["is_open"])
        self.assertNotIn("id", response.data)

    def test_closed_paused_draft_and_missing(self):
        draft = self.new_vacancy(title="Черновик")
        self.assertEqual(self.anon.get(f"{PUBLIC}/vacancies/{draft['slug']}/").status_code, 404)
        self.assertEqual(self.anon.get(f"{PUBLIC}/vacancies/net-takoy/").status_code, 404)
        self.publish(self.vacancy["id"], "paused")
        response = self.anon.get(f"{PUBLIC}/vacancies/{self.vacancy['slug']}/")
        self.assertEqual(response.status_code, 410)
        self.assertEqual(set(response.data), {"detail", "code", "title"})
        self.publish(self.vacancy["id"], "closed")
        response = self.anon.get(f"{PUBLIC}/vacancies/{self.vacancy['slug']}/")
        self.assertEqual((response.status_code, response.data["code"]), (410, "vacancy_closed"))

    def test_public_api_ignores_tokens_and_hr_api_is_closed(self):
        self.anon.credentials(HTTP_AUTHORIZATION="Bearer broken")
        self.assertEqual(self.anon.get(f"{PUBLIC}/vacancies/").status_code, 200)
        anon = self.client_class()
        for url in ("/api/v1/hr/applications/", "/api/v1/hr/candidates/", "/api/v1/hr/reports/daily/",
                    "/api/v1/hr/vacancies/"):
            self.assertEqual(anon.get(url).status_code, 401, url)


class ApplyTests(RecruitmentFixture):
    def test_successful_application(self):
        response = self.apply(city="Бишкек", experience="3 года", skills="Продажи", cover_letter="Хочу к вам",
                              portfolio_url="https://linkedin.com/in/bakyt", source="social", resume=pdf_file())
        self.assertEqual(response.status_code, 201, response.data)
        self.assertRegex(response.data["number"], r"^2026-[A-Z2-9]{6}$")
        self.assertEqual(set(response.data), {"number", "vacancy", "message"})
        application = Application.objects.get(number=response.data["number"])
        self.assertEqual(application.vacancy_id, self.vacancy["id"])
        self.assertEqual((application.status, application.channel, application.source), ("new", "public", "social"))
        self.assertEqual(application.responsible, self.hr)
        self.assertIsNotNone(application.consent_at)
        self.assertEqual(application.consent_version, "2026-10")
        self.assertEqual(application.submitted_data["city"], "Бишкек")
        self.assertEqual(application.cover_letter, "Хочу к вам")
        candidate = application.candidate
        self.assertEqual((candidate.last_name, candidate.first_name, candidate.middle_name),
                         ("Асанов", "Бакыт", "Уланович"))
        self.assertEqual((candidate.email, candidate.phone_digits), ("bakyt@mail.kg", "996555123456"))
        self.assertEqual(application.resume_name, "cv.pdf")
        self.assertTrue(application.resume.name.startswith("recruitment/resumes/"))
        self.assertNotIn("cv", os.path.basename(application.resume.name))
        self.assertTrue(HRActivity.objects.filter(application=application, kind="application_received").exists())

    def test_no_lms_account_is_created(self):
        users = self.hr.__class__.objects.count()
        self.assertEqual(self.apply().status_code, 201)
        self.assertEqual(self.hr.__class__.objects.count(), users)

    def test_validation(self):
        cases = [
            ({"full_name": ""}, "full_name"), ({"full_name": "1"}, "full_name"), ({"phone": "abc"}, "phone"),
            ({"phone": "12"}, "phone"), ({"email": "not-email"}, "email"), ({"consent": False}, "consent"),
            ({"portfolio_url": "javascript:alert(1)"}, "portfolio_url"), ({"submission_token": "x"}, "submission_token"),
            ({"source": "agency"}, "source"),
        ]
        for over, field in cases:
            with self.subTest(field=field, value=over):
                response = self.apply(**over)
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
        self.assertEqual(Application.objects.count(), 0)

    def test_resume_formats_and_size(self):
        self.assertEqual(self.apply(resume=docx_file()).status_code, 201)
        bad = [
            pdf_file("cv.exe"),
            pdf_file("cv.docx"),  # PDF-содержимое под видом DOCX
            type(pdf_file())("cv.pdf", b"MZ\x90\x00 not a pdf", content_type="application/pdf"),
            pdf_file(size=6 * 1024 * 1024),
        ]
        for upload in bad:
            with self.subTest(name=upload.name):
                response = self.apply(resume=upload, email=f"{uuid.uuid4().hex[:6]}@mail.kg",
                                      phone=f"+996 700 {uuid.uuid4().int % 1000000:06d}")
                self.assertEqual(response.status_code, 400)
                self.assertIn("resume", response.data)
        self.assertEqual(Application.objects.count(), 1)

    def test_same_form_twice_creates_one_application(self):
        token = str(uuid.uuid4())
        first = self.apply(submission_token=token)
        second = self.apply(submission_token=token)
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.data["number"], second.data["number"])
        self.assertEqual(Application.objects.count(), 1)

    def test_repeat_application_to_same_vacancy_is_rejected(self):
        self.assertEqual(self.apply().status_code, 201)
        again = self.apply(email="BAKYT@mail.kg", phone="0555 123 456")
        self.assertEqual((again.status_code, again.data["code"]), (409, "already_applied"))
        other_contacts_same_phone = self.apply(email="other@mail.kg")
        self.assertEqual(other_contacts_same_phone.status_code, 409)
        self.assertEqual(Application.objects.count(), 1)

    def test_honeypot(self):
        response = self.apply(website="http://spam.example")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Application.objects.count(), 0)

    def test_closed_or_draft_vacancy_does_not_accept(self):
        draft = self.new_vacancy(title="Черновик")
        self.assertEqual(self.apply(slug=draft["slug"]).status_code, 404)
        self.publish(self.vacancy["id"], "closed")
        self.assertEqual(self.apply().status_code, 410)

    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    def test_throttle(self):
        cache.clear()
        codes = [self.apply(email=f"u{i}@mail.kg", phone=f"+996 700 00{i:04d}").status_code for i in range(11)]
        self.assertEqual(codes[:10], [201] * 10)
        self.assertEqual(codes[10], 429)
        cache.clear()


class CandidateLinkingTests(RecruitmentFixture):
    def setUp(self):
        super().setUp()
        with frozen(at(2, 9)):
            self.second = self.new_vacancy(title="SMM-специалист", department="Маркетинг")
            self.publish(self.second["id"])

    def test_same_contacts_link_to_one_candidate(self):
        self.assertEqual(self.apply(city="Бишкек").status_code, 201)
        response = self.apply(slug=self.second["slug"], full_name="Другое Имя", email="Bakyt@Mail.kg",
                              phone="0555123456", education="КРСУ")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Candidate.objects.count(), 1)
        candidate = Candidate.objects.get()
        self.assertEqual(candidate.applications.count(), 2)
        # Профиль не перезаписан именем из второй анкеты, пустые поля дополнены.
        self.assertEqual(candidate.first_name, "Бакыт")
        self.assertEqual((candidate.city, candidate.education), ("Бишкек", "КРСУ"))
        self.assertFalse(Application.objects.filter(needs_duplicate_review=True).exists())

    def test_partial_match_is_flagged_not_merged(self):
        self.apply()
        response = self.apply(slug=self.second["slug"], email="new@mail.kg")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Candidate.objects.count(), 2)
        flagged = Application.objects.get(number=response.data["number"])
        self.assertTrue(flagged.needs_duplicate_review)

    def test_same_name_different_contacts_are_different_people(self):
        self.apply()
        self.apply(slug=self.second["slug"], email="other@mail.kg", phone="+996 777 000 111")
        self.assertEqual(Candidate.objects.count(), 2)
        self.assertFalse(Application.objects.filter(needs_duplicate_review=True).exists())

    def test_hr_merges_flagged_duplicate(self):
        first = Application.objects.get(number=self.apply().data["number"])
        second = Application.objects.get(number=self.apply(slug=self.second["slug"], email="new@mail.kg").data["number"])
        detail = self.get(f"candidates/{second.candidate_id}/")
        self.assertEqual([m["id"] for m in detail.data["possible_duplicates"]], [first.candidate_id])
        self.assertTrue(detail.data["possible_duplicates"][0]["same_phone"])
        response = self.post(f"candidates/{second.candidate_id}/merge/", {"target": first.candidate_id})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data["applications"]), 2)
        source = Candidate.objects.get(pk=second.candidate_id)
        self.assertEqual(source.merged_into_id, first.candidate_id)
        self.assertFalse(Application.objects.filter(needs_duplicate_review=True).exists())
        # Объединённая запись пропадает из списка, история сохранена у основной.
        ids = [c["id"] for c in self.get("candidates/").data["results"]]
        self.assertNotIn(source.pk, ids)
        self.assertTrue(HRActivity.objects.filter(candidate_id=first.candidate_id, kind="candidate_merged").exists())

    def test_not_duplicate(self):
        number = self.apply(slug=self.second["slug"], email="new@mail.kg", phone="+996 555 123 456")
        self.apply(email="other@mail.kg", phone="+996 555 123 456")
        application = Application.objects.get(number=number.data["number"])
        response = self.post(f"applications/{application.pk}/not-duplicate/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["needs_duplicate_review"])


class ResumeProtectionTests(RecruitmentFixture):
    def setUp(self):
        super().setUp()
        self.number = self.apply(resume=pdf_file()).data["number"]
        self.application = Application.objects.get(number=self.number)

    def test_hr_downloads_resume_with_safe_headers(self):
        response = self.get(f"applications/{self.application.pk}/resume/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertTrue(b"".join(response.streaming_content).startswith(b"%PDF-"))
        inline = self.get(f"applications/{self.application.pk}/resume/", {"inline": "1"})
        self.assertIn("inline", inline["Content-Disposition"])
        self.assertTrue(HRActivity.objects.filter(application=self.application, kind="resume_accessed").exists())

    def test_others_cannot_download(self):
        from apps.users.models import User

        from .base import make

        url = f"/api/v1/hr/applications/{self.application.pk}/resume/"
        self.assertEqual(self.client_class().get(url).status_code, 401)
        for role in (User.Role.ROP, User.Role.TEACHER, User.Role.ADMIN, User.Role.ACCOUNTANT):
            other = self.client_class()
            other.force_login(make(f"user_{role}", role))
            with self.subTest(role=role):
                self.assertEqual(other.get(url).status_code, 403)

    def test_no_public_media_url(self):
        import shutil
        import tempfile

        import config.urls

        media = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)
        os.makedirs(os.path.join(media, "private", "recruitment"))
        os.makedirs(os.path.join(media, "teachers"))
        with open(os.path.join(media, "private", "recruitment", "cv.pdf"), "wb") as fh:
            fh.write(b"%PDF-secret")
        with open(os.path.join(media, "teachers", "ok.txt"), "wb") as fh:
            fh.write(b"public")
        try:
            with override_settings(DEBUG=False, SERVE_MEDIA=True, MEDIA_ROOT=media):
                clear_url_caches()
                importlib.reload(config.urls)
                self.assertEqual(self.client_class().get("/media/teachers/ok.txt").status_code, 200)
                for url in ("/media/private/recruitment/cv.pdf", "/media/teachers/../private/recruitment/cv.pdf",
                            "/media/private/", "/media//private/recruitment/cv.pdf"):
                    with self.subTest(url=url):
                        response = self.client_class().get(url)
                        self.assertIn(response.status_code, (400, 404))
        finally:
            clear_url_caches()
            importlib.reload(config.urls)
        with self.assertRaises(ValueError):
            self.application.resume.url

    def test_hr_attaches_resume(self):
        response = self.client.post(f"/api/v1/hr/applications/{self.application.pk}/resume/",
                                    {"resume": docx_file("new.docx")}, format="multipart")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["resume_name"], "new.docx")
        bad = self.client.post(f"/api/v1/hr/applications/{self.application.pk}/resume/",
                               {"resume": pdf_file("x.txt")}, format="multipart")
        self.assertEqual((bad.status_code, bad.data["code"]), (400, "resume_format"))


class VacancyModelTests(RecruitmentFixture):
    def test_public_queryset(self):
        self.assertEqual(list(Vacancy.objects.public().values_list("title", flat=True)), ["Менеджер по продажам"])
