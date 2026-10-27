"""Общие помощники тестов подбора: пользователи, замороженное время, вакансии,
отклики, файлы резюме. Всё создаётся через API — так же, как работает интерфейс."""
from __future__ import annotations

import io
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.recruitment.models import Application
from apps.users.models import User

TZ = ZoneInfo("Asia/Bishkek")
API = "/api/v1/hr"
PUBLIC = "/api/v1/public/careers"
PASSWORD = "Str0ngPassw0rd!"

VACANCY = {
    "title": "Менеджер по продажам", "department": "Продажи", "summary": "Продажи курсов для детей",
    "description": "Работа с входящими заявками родителей.", "responsibilities": "Звонки\nВстречи с родителями",
    "requirements": "Опыт продаж от 1 года\nГрамотная речь", "nice_to_have": "CRM", "conditions": "Обучение",
    "selection_stages": "Собеседование с HR\nВстреча с РОП", "location": "Бишкек", "work_format": "office",
    "employment_type": "full_time", "salary_min": 40000, "salary_max": 60000, "show_salary": True,
}


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


def pdf_file(name: str = "cv.pdf", size: int = 0) -> SimpleUploadedFile:
    body = b"%PDF-1.4\n%test resume\n" + b"0" * size
    return SimpleUploadedFile(name, body, content_type="application/pdf")


def docx_file(name: str = "cv.docx") -> SimpleUploadedFile:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    return SimpleUploadedFile(name, buffer.getvalue(),
                              content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


class RecruitmentFixture(TestCase):
    """HR, интервьюер (РОП) и опубликованная вакансия на 1 октября 2026."""

    def setUp(self):
        self.hr = make("hr", User.Role.HR_MANAGER)
        self.interviewer = make("rop", User.Role.ROP)
        self.client = APIClient()
        self.client.force_authenticate(self.hr)
        self.anon = APIClient()
        with frozen(at(1, 9)):
            self.vacancy = self.new_vacancy()
            self.publish(self.vacancy["id"])

    # --- HTTP ---------------------------------------------------------------

    def post(self, url, body=None, client=None, fmt="json"):
        return (client or self.client).post(f"{API}/{url}", body or {}, format=fmt)

    def patch(self, url, body):
        return self.client.patch(f"{API}/{url}", body, format="json")

    def get(self, url, params=None):
        return self.client.get(f"{API}/{url}", params or {})

    # --- Данные ---------------------------------------------------------------

    def new_vacancy(self, **over) -> dict:
        response = self.post("vacancies/", {**VACANCY, "responsible": self.hr.pk, **over})
        assert response.status_code == 201, response.data
        return response.data

    def publish(self, vacancy_id: int, status: str = "published"):
        response = self.post(f"vacancies/{vacancy_id}/status/", {"status": status})
        assert response.status_code == 200, response.data
        return response.data

    def apply(self, slug=None, moment=None, resume=None, **over):
        body = {"submission_token": str(uuid.uuid4()), "full_name": "Асанов Бакыт Уланович",
                "phone": "+996 555 123 456", "email": "bakyt@mail.kg", "consent": True}
        body.update(over)
        if resume is not None:
            body["resume"] = resume
        with frozen(moment or at(20, 9)):
            return self.anon.post(f"{PUBLIC}/vacancies/{slug or self.vacancy['slug']}/apply/", body,
                                  format="multipart")

    def new_application(self, moment=None, **over) -> dict:
        body = {"last_name": "Асанов", "first_name": "Бакыт", "phone": "+996 555 123 456",
                "vacancy": self.vacancy["id"], "source": "job_site"}
        body.update(over)
        with frozen(moment or at(20, 9)):
            response = self.post("applications/", body)
        assert response.status_code == 201, response.data
        return response.data

    def schedule(self, application_id, when, now=None, **over):
        body = {"application": application_id, "scheduled_at": when.isoformat(), "format": "online",
                "meeting_url": "https://meet.example.com/abc", "interviewer": self.interviewer.pk}
        body.update(over)
        with frozen(now or at(20, 9)):
            return self.post("interviews/", body)

    def result(self, interview_id, now, **over):
        body = {"result": "passed", "next_step": "offer", "overall_rating": 4, "skills_rating": 5,
                "strengths": "Коммуникация", "concerns": ""}
        body.update(over)
        with frozen(now):
            return self.post(f"interviews/{interview_id}/result/", body)

    def status_of(self, application_id) -> str:
        return Application.objects.get(pk=application_id).status

    def move(self, application_id, *statuses, moment=None):
        for value in statuses:
            with frozen(moment or at(20, 10)):
                response = self.post(f"applications/{application_id}/status/", {"status": value})
            assert response.status_code == 200, response.data

    def to_offer(self, application_id, day=20):
        """Отклик → собеседование → результат «предложение»."""
        interview = self.schedule(application_id, at(day + 1, 15), now=at(day, 9)).data
        response = self.result(interview["id"], at(day + 1, 16))
        assert response.status_code == 200, response.data
        return interview
