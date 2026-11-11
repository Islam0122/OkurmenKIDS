"""Public gallery (/api/v1/public/projects/): only published work, a closed
field whitelist, students' privacy, no login ever required."""
from __future__ import annotations

import datetime as dt

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from apps.academy.models import Student

from .models import ProjectImage, StudentProject, Technology
from .public import public_key
from .tests import MEDIA, Base, image_file

PUBLIC = "/api/v1/public/projects/"
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "public-projects"}}


class PublicBase(Base):
    def setUp(self):
        super().setUp()
        self.anon = APIClient()

    def project(self, title="Weather App", status=StudentProject.Status.PUBLISHED, student=None, techs=("React",),
                **extra) -> StudentProject:
        student = student or self.student
        project = StudentProject.objects.create(
            student=student, group=student.group, created_by=self.trainer_user, title=title, status=status,
            short_description="Погода на неделю", description="Полное описание", project_date=dt.date(2026, 11, 2),
            trainer_comment="Слабая вёрстка", rating=3, github_url="https://github.com/aliya-private",
            figma_url="https://figma.com/x", demo_url="https://weather.example.kg", **extra,
        )
        project.technologies.set([Technology.objects.get_or_create(name=name)[0] for name in techs])
        return project

    def get(self, path=PUBLIC, **params):
        return self.anon.get(path, params)


class PublicListTests(PublicBase):
    def test_no_login_and_only_published_projects(self):
        self.project("Published")
        self.project("Draft", status=StudentProject.Status.DRAFT)
        r = self.get()
        self.assertEqual(r.status_code, 200)
        self.assertEqual([p["title"] for p in r.data["results"]], ["Published"])
        self.assertEqual(r.data["count"], 1)
        self.assertIn("public", r["Cache-Control"])

    def test_a_staff_token_is_ignored_not_required(self):
        self.project()
        self.anon.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        self.assertEqual(self.get().status_code, 200)

    def test_closed_whitelist_of_fields(self):
        project = self.project()
        item = self.get().data["results"][0]
        self.assertEqual(set(item), {"key", "title", "short_description", "technologies", "categories", "date",
                                     "student", "group", "cover_url"})
        self.assertEqual(item["key"], public_key(project.pk))
        self.assertNotEqual(item["key"], str(project.pk))
        self.assertEqual(item["student"], "Алия С.")  # first name + initial only
        self.assertEqual(item["group"], "NEXT 1")
        detail = self.get(f"{PUBLIC}{item['key']}/").data
        text = str(detail)
        for secret in ("Садыкова", "Слабая вёрстка", "github.com", "figma.com", "islam"):
            self.assertNotIn(secret, text)
        for field in ("id", "rating", "trainer_comment", "github_url", "figma_url", "status", "created_by", "author"):
            self.assertNotIn(field, detail)
        self.assertEqual(detail["demo_url"], "https://weather.example.kg")

    def test_hidden_student_is_published_without_a_name_and_cannot_be_found_by_it(self):
        Student.objects.filter(pk=self.student.pk).update(show_in_leaderboard=False)
        self.project()
        item = self.get().data["results"][0]
        self.assertIsNone(item["student"])
        self.assertEqual(self.get(q="Алия").data["count"], 0)

    def test_search_by_title_technology_group_and_shown_name(self):
        self.project("Weather App", techs=("React",))
        self.project("Snake", techs=("Python",), student=self.stranger)
        self.assertEqual([p["title"] for p in self.get(q="snake").data["results"]], ["Snake"])
        self.assertEqual([p["title"] for p in self.get(q="react").data["results"]], ["Weather App"])
        self.assertEqual([p["title"] for p in self.get(q="ART 1").data["results"]], ["Snake"])
        self.assertEqual([p["title"] for p in self.get(q="бекзат").data["results"]], ["Snake"])

    def test_categories_and_counts(self):
        self.project("Landing", techs=("HTML", "CSS"))
        self.project("Todo", techs=("JavaScript",))
        self.project("Shop", techs=("React", "TypeScript"))
        self.project("Bot", techs=("Python", "Aiogram"))
        self.project("Scratch game", techs=("Scratch",))
        r = self.get()
        self.assertEqual(r.data["counts"], {"all": 5, "html-css": 1, "javascript": 2, "react": 1, "python": 1, "other": 1})
        self.assertEqual([p["title"] for p in self.get(category="react").data["results"]], ["Shop"])
        self.assertEqual([p["title"] for p in self.get(category="other").data["results"]], ["Scratch game"])
        self.assertEqual(self.get(category="nope").status_code, 400)

    def test_technology_filter_and_facets(self):
        self.project("Weather", techs=("React", "TypeScript"))
        self.project("Bot", techs=("Python", "aiogram"))
        self.project("Game", techs=("python", "Pygame"))
        data = self.get().data
        self.assertEqual(data["technologies"][0], {"name": "Python", "count": 2})
        python = self.get(technology="PYTHON").data
        self.assertEqual(sorted(p["title"] for p in python["results"]), ["Bot", "Game"])
        self.assertEqual(python["counts"]["python"], 2)
        self.assertEqual(self.get(technology="Rust").data["count"], 0)

    def test_pagination(self):
        for index in range(5):
            self.project(f"P{index}")
        r = self.get(page_size=2, page=3)
        self.assertEqual((r.data["count"], r.data["num_pages"], len(r.data["results"])), (5, 3, 1))
        self.assertEqual(self.get(page_size=999).status_code, 400)

    def test_unsafe_demo_links_are_dropped(self):
        project = self.project()
        StudentProject.objects.filter(pk=project.pk).update(demo_url="javascript:alert(1)")
        self.assertIsNone(self.get(f"{PUBLIC}{public_key(project.pk)}/").data["demo_url"])

    def test_read_only(self):
        self.assertEqual(self.anon.post(PUBLIC, {"title": "x"}).status_code, 405)


@override_settings(MEDIA_ROOT=MEDIA)
class PublicDetailTests(PublicBase):
    def test_detail_with_images_and_404_for_drafts(self):
        project = self.project()
        ProjectImage.objects.create(project=project, image=image_file("a.png"), order=1)
        ProjectImage.objects.create(project=project, image=image_file("b.png"), order=0, is_cover=True)
        r = self.get(f"{PUBLIC}{public_key(project.pk)}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data["images"]), 2)
        self.assertTrue(r.data["images"][0]["is_cover"])
        self.assertEqual(r.data["cover_url"], r.data["images"][0]["url"])
        self.assertTrue(r.data["cover_url"].startswith("/media/projects/"))
        self.assertIsNone(r.data["trainer"])

        draft = self.project("Secret", status=StudentProject.Status.DRAFT)
        self.assertEqual(self.get(f"{PUBLIC}{public_key(draft.pk)}/").status_code, 404)
        self.assertEqual(self.get(f"{PUBLIC}{draft.pk}/").status_code, 404)  # a raw id is never a key
        self.assertEqual(self.get(f"{PUBLIC}nope!/").status_code, 404)

    @override_settings(PUBLIC_PROJECTS_SHOW_TRAINER=True)
    def test_trainer_name_only_when_the_academy_allows_it(self):
        self.trainer_user.first_name, self.trainer_user.last_name = "Ислам", "Дуйшобаев"
        self.trainer_user.save()
        project = self.project()
        self.assertEqual(self.get(f"{PUBLIC}{public_key(project.pk)}/").data["trainer"], "Ислам Дуйшобаев")


@override_settings(CACHES=LOCMEM, PUBLIC_PROJECTS_CACHE_SECONDS=600)
class PublicCacheTests(PublicBase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def test_unpublishing_in_the_lms_removes_the_project_at_once(self):
        project = self.project()
        self.assertEqual(self.get().data["count"], 1)
        project.status = StudentProject.Status.DRAFT
        project.save()
        self.assertEqual(self.get().data["count"], 0)

    def test_privacy_switch_applies_at_once(self):
        self.project()
        self.assertEqual(self.get().data["results"][0]["student"], "Алия С.")
        self.student.show_in_leaderboard = False
        self.student.save()
        self.assertIsNone(self.get().data["results"][0]["student"])
