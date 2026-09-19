from __future__ import annotations

import datetime as dt

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.news.models import News, NewsRead
from apps.users.models import Teacher, User


def make_teacher(username: str) -> Teacher:
    user = User.objects.create_user(
        username=username,
        email=f"{username}@okurmen.kg",
        password="Str0ngPassw0rd!",
        first_name=username.capitalize(),
        role=User.Role.TEACHER,
        is_verified=True,
    )
    return Teacher.objects.create(user=user, position="Тренер")


class NewsTestBase(TestCase):
    def setUp(self):
        self.teacher1 = make_teacher("teacher1")
        self.teacher2 = make_teacher("teacher2")

        self.teacher1_client = APIClient()
        self.teacher1_client.force_authenticate(self.teacher1.user)

        self.teacher2_client = APIClient()
        self.teacher2_client.force_authenticate(self.teacher2.user)

        self.anon_client = APIClient()


class NewsVisibilityModelTests(NewsTestBase):
    """News.objects.visible_to() — the queryset both the API views and the
    Dashboard rely on for scoping."""

    def test_all_audience_visible_to_every_teacher(self):
        news = News.objects.create(title="Всем", text="...", audience=News.Audience.ALL)
        self.assertIn(news, News.objects.visible_to(self.teacher1))
        self.assertIn(news, News.objects.visible_to(self.teacher2))

    def test_selected_audience_visible_only_to_selected_teachers(self):
        news = News.objects.create(title="Избранным", text="...", audience=News.Audience.SELECTED)
        news.teachers.add(self.teacher1)

        self.assertIn(news, News.objects.visible_to(self.teacher1))
        self.assertNotIn(news, News.objects.visible_to(self.teacher2))

    def test_expired_news_not_visible(self):
        news = News.objects.create(
            title="Просрочено",
            text="...",
            audience=News.Audience.ALL,
            expires_at=timezone.now() - dt.timedelta(days=1),
        )
        self.assertNotIn(news, News.objects.visible_to(self.teacher1))

    def test_future_expiry_still_visible(self):
        news = News.objects.create(
            title="Ещё активно",
            text="...",
            audience=News.Audience.ALL,
            expires_at=timezone.now() + dt.timedelta(days=1),
        )
        self.assertIn(news, News.objects.visible_to(self.teacher1))

    def test_unpublished_news_not_visible(self):
        news = News.objects.create(
            title="Черновик", text="...", audience=News.Audience.ALL, is_published=False
        )
        self.assertNotIn(news, News.objects.visible_to(self.teacher1))


class TeacherNewsAPITests(NewsTestBase):
    def setUp(self):
        super().setUp()
        self.all_news = News.objects.create(title="Всем", text="Текст для всех", audience=News.Audience.ALL)
        self.selected_news = News.objects.create(
            title="Только тренеру 1", text="Личное", audience=News.Audience.SELECTED
        )
        self.selected_news.teachers.add(self.teacher1)

    def test_list_returns_only_visible_news(self):
        response = self.teacher1_client.get("/api/v1/teacher/news/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = {item["title"] for item in response.data["results"]}
        self.assertEqual(titles, {"Всем", "Только тренеру 1"})

    def test_teacher_cannot_see_other_teachers_selected_news(self):
        response = self.teacher2_client.get("/api/v1/teacher/news/")
        titles = {item["title"] for item in response.data["results"]}
        self.assertEqual(titles, {"Всем"})

    def test_teacher_cannot_retrieve_another_teachers_personal_news(self):
        response = self.teacher2_client.get(f"/api/v1/teacher/news/{self.selected_news.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_is_read_false_until_marked(self):
        response = self.teacher1_client.get("/api/v1/teacher/news/")
        row = next(item for item in response.data["results"] if item["id"] == self.all_news.id)
        self.assertFalse(row["is_read"])

    def test_is_read_true_after_marking_and_is_per_teacher(self):
        NewsRead.objects.create(news=self.all_news, teacher=self.teacher1)

        response1 = self.teacher1_client.get("/api/v1/teacher/news/")
        row1 = next(item for item in response1.data["results"] if item["id"] == self.all_news.id)
        self.assertTrue(row1["is_read"])

        response2 = self.teacher2_client.get("/api/v1/teacher/news/")
        row2 = next(item for item in response2.data["results"] if item["id"] == self.all_news.id)
        self.assertFalse(row2["is_read"])

    def test_unread_count(self):
        response = self.teacher1_client.get("/api/v1/teacher/news/unread-count/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)

        NewsRead.objects.create(news=self.all_news, teacher=self.teacher1)

        response = self.teacher1_client.get("/api/v1/teacher/news/unread-count/")
        self.assertEqual(response.data["count"], 1)

    def test_mark_as_read_creates_record(self):
        response = self.teacher1_client.post(f"/api/v1/teacher/news/{self.all_news.id}/read/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"success": True})
        self.assertTrue(NewsRead.objects.filter(news=self.all_news, teacher=self.teacher1).exists())

    def test_mark_as_read_is_idempotent(self):
        self.teacher1_client.post(f"/api/v1/teacher/news/{self.all_news.id}/read/")
        response = self.teacher1_client.post(f"/api/v1/teacher/news/{self.all_news.id}/read/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            NewsRead.objects.filter(news=self.all_news, teacher=self.teacher1).count(), 1
        )

    def test_mark_as_read_rejects_news_not_visible_to_teacher(self):
        response = self.teacher2_client.post(f"/api/v1/teacher/news/{self.selected_news.id}/read/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(NewsRead.objects.filter(news=self.selected_news, teacher=self.teacher2).exists())

    def test_anonymous_user_denied(self):
        response = self.anon_client.get("/api/v1/teacher/news/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_denied_teacher_only_endpoint(self):
        admin = User.objects.create_superuser(
            username="admin", email="admin@okurmen.kg", password="Str0ngPassw0rd!", first_name="Admin"
        )
        admin_client = APIClient()
        admin_client.force_authenticate(admin)
        response = admin_client.get("/api/v1/teacher/news/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
