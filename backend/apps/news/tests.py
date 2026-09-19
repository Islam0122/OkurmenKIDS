from __future__ import annotations

import datetime as dt

from django.contrib.admin.sites import site as admin_site
from django.test import Client as DjangoClient
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.news.admin import NewsAdmin, NewsAdminForm
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


def make_admin(username: str = "admin") -> User:
    return User.objects.create_superuser(
        username=username, email=f"{username}@okurmen.kg", password="Str0ngPassw0rd!", first_name="Admin"
    )


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


class NewsExpiryDefaultTests(TestCase):
    """News.expires_at defaults to "created + 7 days" (see
    models.default_news_expiry) — Admin can still override or clear it,
    and rows saved before this default existed keep whatever they have."""

    def test_new_news_defaults_to_about_seven_days_out(self):
        before = timezone.now()
        news = News.objects.create(title="Т", text="...")
        after = timezone.now()

        self.assertIsNotNone(news.expires_at)
        self.assertGreaterEqual(news.expires_at, before + dt.timedelta(days=6, hours=23))
        self.assertLessEqual(news.expires_at, after + dt.timedelta(days=7, minutes=1))

    def test_explicit_none_is_respected(self):
        news = News.objects.create(title="Т", text="...", expires_at=None)
        self.assertIsNone(news.expires_at)

    def test_explicit_value_overrides_the_default(self):
        custom = timezone.now() + dt.timedelta(days=30)
        news = News.objects.create(title="Т", text="...", expires_at=custom)
        self.assertEqual(news.expires_at, custom)


class NewsAdminFormTests(TestCase):
    """NewsAdminForm — the "Выбранным" audience must carry at least one
    Teacher; "Всем" never requires the (hidden-in-the-UI) teachers field."""

    def setUp(self):
        self.teacher = make_teacher("teacher1")

    def test_selected_audience_without_teachers_is_rejected(self):
        form = NewsAdminForm(
            data={
                "title": "Т",
                "text": "...",
                "type": News.NewsType.INFO,
                "audience": News.Audience.SELECTED,
                "teachers": [],
                "is_published": True,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("teachers", form.errors)

    def test_selected_audience_with_a_teacher_is_accepted(self):
        form = NewsAdminForm(
            data={
                "title": "Т",
                "text": "...",
                "type": News.NewsType.INFO,
                "audience": News.Audience.SELECTED,
                "teachers": [self.teacher.id],
                "is_published": True,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_all_audience_does_not_require_teachers(self):
        form = NewsAdminForm(
            data={
                "title": "Т",
                "text": "...",
                "type": News.NewsType.INFO,
                "audience": News.Audience.ALL,
                "teachers": [],
                "is_published": True,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)


class NewsAdminRegistrationTests(TestCase):
    """NewsRead must never appear as its own browsable admin section (spec
    §1/§16) — the only place to see read state is inside a News's own
    change form (see NewsAdminReadsOverviewTests below)."""

    def test_news_is_registered_newsread_is_not(self):
        self.assertIn(News, admin_site._registry)
        self.assertNotIn(NewsRead, admin_site._registry)

    def test_newsread_admin_url_does_not_exist(self):
        with self.assertRaises(NoReverseMatch):
            reverse("admin:news_newsread_changelist")


class NewsAdminReadsOverviewTests(NewsTestBase):
    """The read/unread breakdown shown inside News's own change form —
    scoped to exactly the Teachers the News was actually sent to."""

    def setUp(self):
        super().setUp()
        self.teacher3 = make_teacher("teacher3")
        self.admin_instance = NewsAdmin(News, admin_site)

    def test_reads_column_for_all_audience_counts_every_active_teacher(self):
        news = News.objects.create(title="Всем", text="...", audience=News.Audience.ALL)
        NewsRead.objects.create(news=news, teacher=self.teacher1)

        self.assertEqual(self.admin_instance.reads_column(news), "1 / 3")

    def test_reads_column_excludes_inactive_teachers_from_all_audience(self):
        self.teacher3.is_active = False
        self.teacher3.save(update_fields=["is_active"])
        news = News.objects.create(title="Всем", text="...", audience=News.Audience.ALL)

        self.assertEqual(self.admin_instance.reads_column(news), "0 / 2")

    def test_reads_column_for_selected_audience_counts_only_the_selected_teachers(self):
        news = News.objects.create(title="Избранным", text="...", audience=News.Audience.SELECTED)
        news.teachers.add(self.teacher1, self.teacher2)
        NewsRead.objects.create(news=news, teacher=self.teacher1)

        self.assertEqual(self.admin_instance.reads_column(news), "1 / 2")

    def test_reads_overview_lists_read_and_unread_rows(self):
        news = News.objects.create(title="Всем", text="...", audience=News.Audience.ALL)
        NewsRead.objects.create(news=news, teacher=self.teacher1)

        html = self.admin_instance.reads_overview(news)

        self.assertIn("Прочитали: 1 из 3", html)
        self.assertIn("Не прочитано", html)
        self.assertIn(str(self.teacher1), html)

    def test_reads_overview_never_lists_a_teacher_outside_the_selected_audience(self):
        news = News.objects.create(title="Избранным", text="...", audience=News.Audience.SELECTED)
        news.teachers.add(self.teacher1)

        html = self.admin_instance.reads_overview(news)

        self.assertIn(str(self.teacher1), html)
        self.assertNotIn(str(self.teacher2), html)
        self.assertNotIn(str(self.teacher3), html)

    def test_reads_overview_selected_audience_summary_mentions_recipient_count(self):
        news = News.objects.create(title="Избранным", text="...", audience=News.Audience.SELECTED)
        news.teachers.add(self.teacher1, self.teacher2)

        html = self.admin_instance.reads_overview(news)

        self.assertIn("Кому отправлено: 2 тренера", html)
        self.assertIn("Прочитали: 0 из 2", html)


class NewsAdminHttpTests(TestCase):
    """Smoke-tests the real admin views (changelist/changeform) render —
    catches wiring mistakes (e.g. a readonly field missing from
    get_readonly_fields) that a direct method call wouldn't."""

    def setUp(self):
        self.admin = make_admin()
        self.admin_web = DjangoClient()
        self.admin_web.force_login(self.admin)
        self.teacher = make_teacher("teacher1")

    def test_changelist_renders_and_has_no_standalone_reads_link(self):
        News.objects.create(title="Новость", text="...")
        response = self.admin_web.get(reverse("admin:news_news_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Прочтения Новостей")

    def test_change_view_renders_reads_overview(self):
        news = News.objects.create(title="Новость", text="...", audience=News.Audience.ALL)
        NewsRead.objects.create(news=news, teacher=self.teacher)

        response = self.admin_web.get(reverse("admin:news_news_change", args=[news.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Прочтения")
        self.assertContains(response, "1 из 1")

    def test_add_view_renders_without_a_reads_block(self):
        response = self.admin_web.get(reverse("admin:news_news_add"))
        self.assertEqual(response.status_code, 200)
