"""Public academy news: only published articles whose time has come, a
closed field whitelist, optimized photos, admin management."""
from __future__ import annotations

import datetime as dt
import io
import os
import shutil
import tempfile

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.users.models import User

from .models import Article, ArticlePhoto
from .slugs import transliterate

API = "/api/v1/public/news/"
MEDIA = tempfile.mkdtemp()
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "public-news"}}


def picture(name="photo.jpg", fmt="JPEG", size=(2400, 1600)) -> SimpleUploadedFile:
    buf = io.BytesIO()
    Image.new("RGB", size, (22, 163, 74)).save(buf, fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f"image/{fmt.lower()}")


@override_settings(MEDIA_ROOT=MEDIA)
class Base(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.client = APIClient()
        self.editor = User.objects.create_user(username="editor", email="e@x.kg", password="x", first_name="Айгерим",
                                               last_name="Токтогулова", role=User.Role.ADMIN, is_verified=True)

    def article(self, title="Хакатон 2026", status=Article.Status.PUBLISHED, published_at=None, **extra) -> Article:
        extra.setdefault("excerpt", "Коротко о главном")
        extra.setdefault("body", "Первый абзац.\n\nВторой абзац.")
        return Article.objects.create(
            title=title, status=status, published_at=published_at or timezone.now() - dt.timedelta(hours=1),
            author=self.editor, **extra,
        )

    def get(self, path=API, **params):
        return self.client.get(path, params)


class VisibilityTests(Base):
    def test_only_published_articles_whose_time_has_come(self):
        self.article("Published")
        self.article("Draft", status=Article.Status.DRAFT)
        self.article("Scheduled", published_at=timezone.now() + dt.timedelta(days=1))
        r = self.get()
        self.assertEqual(r.status_code, 200)
        titles = [r.data["featured"]["title"], *[a["title"] for a in r.data["results"]]]
        self.assertEqual(titles, ["Published"])
        for title in ("Draft", "Scheduled"):
            slug = Article.objects.get(title=title).slug
            self.assertEqual(self.get(f"{API}{slug}/").status_code, 404, title)

    def test_scheduled_article_appears_on_time(self):
        article = self.article("Later", published_at=timezone.now() + dt.timedelta(minutes=5))
        self.assertEqual(self.get(f"{API}{article.slug}/").status_code, 404)
        Article.objects.filter(pk=article.pk).update(published_at=timezone.now() - dt.timedelta(seconds=1))
        self.assertEqual(self.get(f"{API}{article.slug}/").status_code, 200)

    def test_no_login_and_tokens_ignored_read_only(self):
        self.article()
        self.client.credentials(HTTP_AUTHORIZATION="Bearer junk")
        self.assertEqual(self.get().status_code, 200)
        self.assertEqual(self.client.post(API, {"title": "x"}).status_code, 405)

    def test_closed_whitelist_and_author_only_when_allowed(self):
        article = self.article()
        detail = self.get(f"{API}{article.slug}/").data
        self.assertEqual(set(detail), {"slug", "title", "excerpt", "body", "category", "published_at", "author",
                                       "cover", "photos", "related"})
        self.assertIsNone(detail["author"])
        self.assertNotIn("editor", str(detail))
        article.show_author = True
        article.save()
        self.assertEqual(self.get(f"{API}{article.slug}/").data["author"], "Айгерим Токтогулова")


class ListingTests(Base):
    def test_featured_is_the_marked_article_else_the_newest_and_not_repeated(self):
        old = self.article("Old", published_at=timezone.now() - dt.timedelta(days=3), is_featured=True)
        self.article("New")
        r = self.get()
        self.assertEqual(r.data["featured"]["slug"], old.slug)
        self.assertEqual([a["title"] for a in r.data["results"]], ["New"])
        self.assertIsNone(self.get(page=2).data["featured"])
        # A search or a category shows plain results, no featured block.
        filtered = self.get(category="events").data
        self.assertIsNone(filtered["featured"])
        self.assertEqual(filtered["count"], 2)

    def test_categories_counts_and_search(self):
        self.article("Robotics cup", category=Article.Category.COMPETITIONS)
        self.article("Open lesson", category=Article.Category.EDUCATION, body="Python для начинающих")
        r = self.get()
        self.assertEqual(r.data["counts"]["all"], 2)
        self.assertEqual(r.data["counts"]["competitions"], 1)
        self.assertEqual([a["title"] for a in self.get(category="competitions").data["results"]], ["Robotics cup"])
        self.assertEqual([a["title"] for a in self.get(q="python").data["results"]], ["Open lesson"])
        self.assertEqual(self.get(category="nope").status_code, 400)

    def test_related_prefers_the_same_category(self):
        main = self.article("Main", category=Article.Category.EVENTS)
        self.article("Same", category=Article.Category.EVENTS, published_at=timezone.now() - dt.timedelta(days=5))
        self.article("Other", category=Article.Category.EDUCATION)
        related = [a["title"] for a in self.get(f"{API}{main.slug}/").data["related"]]
        self.assertEqual(related, ["Same", "Other"])


class SlugTests(Base):
    def test_latin_slug_from_cyrillic_and_unique(self):
        self.assertEqual(transliterate("Жаңы өнүгүү"), "zhangy onuguu")
        a = self.article("Наш хакатон")
        b = self.article("Наш хакатон")
        self.assertEqual(a.slug, "nash-hakaton")
        self.assertEqual(b.slug, "nash-hakaton-2")


class PhotoTests(Base):
    def test_cover_and_photos_get_webp_copies_sizes_and_captions(self):
        article = self.article(cover=picture("cover.jpg"), cover_caption="Победители")
        ArticlePhoto.objects.create(article=article, image=picture("a.png", "PNG", (900, 1200)), caption="Команда", order=0)
        ArticlePhoto.objects.create(article=article, image=picture("b.jpg"), order=1)
        article.refresh_from_db()
        self.assertEqual((article.cover_width, article.cover_height), (2400, 1600))
        with Image.open(article.cover_large.path) as large:
            self.assertEqual((large.format, max(large.size)), ("WEBP", 1600))
        with Image.open(article.cover_thumb.path) as thumb:
            self.assertEqual(max(thumb.size), 640)

        detail = self.get(f"{API}{article.slug}/").data
        self.assertEqual(detail["cover"]["caption"], "Победители")
        self.assertTrue(detail["cover"]["url"].endswith(".webp"))
        self.assertEqual([p["caption"] for p in detail["photos"]], ["Команда", ""])
        self.assertEqual((detail["photos"][0]["width"], detail["photos"][0]["height"]), (900, 1200))
        card = self.get().data["featured"]
        self.assertEqual(card["photo_count"], 3)
        self.assertTrue(card["cover"]["thumb"].endswith(".webp"))

    def test_deleting_removes_every_file(self):
        article = self.article(cover=picture())
        photo = ArticlePhoto.objects.create(article=article, image=picture())
        paths = [article.cover.path, article.cover_large.path, photo.image.path, photo.large.path, photo.thumb.path]
        article.delete()
        self.assertFalse(any(os.path.exists(path) for path in paths))

    def test_not_an_image_is_rejected(self):
        from django.core.exceptions import ValidationError

        article = self.article()
        fake = SimpleUploadedFile("x.jpg", b"not an image", content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            ArticlePhoto(article=article, image=fake).full_clean()


@override_settings(CACHES=LOCMEM, PUBLIC_NEWS_CACHE_SECONDS=600)
class CacheTests(Base):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_unpublishing_removes_the_article_at_once(self):
        article = self.article()
        self.assertEqual(self.get(f"{API}{article.slug}/").status_code, 200)
        article.status = Article.Status.DRAFT
        article.save()
        self.assertEqual(self.get(f"{API}{article.slug}/").status_code, 404)


@override_settings(MEDIA_ROOT=MEDIA)
class AdminTests(Base):
    def setUp(self):
        super().setUp()
        self.boss = User.objects.create_superuser(username="boss", email="b@x.kg", password="x")
        self.client.force_login(self.boss)

    def test_create_with_cover_and_several_photos_at_once(self):
        r = self.client.post("/admin/academy_news/article/add/", {
            "title": "Выпускной", "slug": "", "category": "events", "excerpt": "Праздник", "body": "Текст",
            "cover": picture("cover.jpg"), "cover_caption": "", "status": "draft",
            "published_at_0": "2026-11-01", "published_at_1": "10:00:00",
            "new_photos": [picture("1.jpg"), picture("2.jpg"), picture("3.png", "PNG")],
            "photos-TOTAL_FORMS": "0", "photos-INITIAL_FORMS": "0", "photos-MIN_NUM_FORMS": "0", "photos-MAX_NUM_FORMS": "1000",
        })
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["adminform"].form.errors)
        article = Article.objects.get(title="Выпускной")
        self.assertEqual(article.author, self.boss)
        self.assertEqual(article.slug, "vypusknoy")
        self.assertEqual(list(article.photos.values_list("order", flat=True)), [0, 1, 2])
        self.assertTrue(all(photo.thumb for photo in article.photos.all()))
        self.assertEqual(self.get(f"{API}{article.slug}/").status_code, 404)  # still a draft

    def test_publish_and_unpublish_actions(self):
        article = self.article(status=Article.Status.DRAFT, published_at=timezone.now() + dt.timedelta(days=3))
        url = "/admin/academy_news/article/"
        self.client.post(url, {"action": "publish_now", "_selected_action": [article.pk]})
        article.refresh_from_db()
        self.assertTrue(article.is_public)
        self.client.post(url, {"action": "unpublish", "_selected_action": [article.pk]})
        article.refresh_from_db()
        self.assertEqual(article.status, Article.Status.DRAFT)

    def test_lms_trainer_has_no_access(self):
        trainer = User.objects.create_user(username="t", email="t@x.kg", password="x", role=User.Role.TEACHER,
                                           is_verified=True)
        self.client.force_login(trainer)
        self.assertNotEqual(self.client.get("/admin/academy_news/article/").status_code, 200)
