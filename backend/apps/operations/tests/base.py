"""Общие помощники тестов операционного модуля (абсолютные импорты — как в
остальных тестах проекта)."""
from __future__ import annotations

import datetime as dt

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.users.models import Teacher, User

PASSWORD = "Str0ngPassw0rd!"


def make(username: str, role: str, **extra) -> User:
    user = User.objects.create_user(username=username, email=f"{username}@okurmen.kg", password=PASSWORD,
                                    first_name=username.capitalize(), last_name="Test", role=role, is_verified=True,
                                    **extra)
    if role == User.Role.TEACHER:
        Teacher.objects.create(user=user)
    return user


def jwt_client(username: str) -> APIClient:
    """Клиент с настоящим JWT — так запрос проходит через middleware изоляции ролей."""
    client = APIClient()
    response = client.post("/api/v1/auth/login/", {"username": username, "password": PASSWORD}, format="json")
    assert response.status_code == 200, response.data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
    return client


def in_hours(hours: float) -> str:
    return (timezone.now() + dt.timedelta(hours=hours)).isoformat()


class OpsTestCase(TestCase):
    def setUp(self):
        R = User.Role
        self.od = make("odir", R.OPERATIONS_DIRECTOR)
        self.director = make("boss", R.DIRECTOR)
        self.admin = make("admin1", R.ADMIN)
        self.lead = make("tlead", R.TEAM_LEAD)
        self.trainer = make("trainer", R.TEACHER)
        self.trainer2 = make("trainer2", R.TEACHER)
        self.assistant = make("assist", R.ASSISTANT)
        self.manager = make("seller", R.SALES_MANAGER)
        self.rop = make("rop1", R.ROP)
        self.marketer = make("aida", R.MARKETING)
        self.hr = make("hrm", R.HR_MANAGER)
        self.accountant = make("acc", R.ACCOUNTANT)

    def client_for(self, user) -> APIClient:
        client = APIClient()
        client.force_authenticate(user)
        return client

    def create_task(self, actor, **body):
        body.setdefault("title", "Проверить журналы")
        response = self.client_for(actor).post("/api/v1/tasks/", body, format="json")
        assert response.status_code == 201, response.data
        return response.data
