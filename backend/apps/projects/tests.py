"""Student projects: who registers, who sees, who changes; images; filters; stats."""
from __future__ import annotations

import datetime as dt
import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.academy.models import Course, Group, GroupTeacher, Student
from apps.attendance_matrix.models import TeamLeadDirection
from apps.users.models import Subject, Teacher, User

from .models import ProjectImage, StudentProject, Technology

BASE = "/api/v1/projects/"
MEDIA = tempfile.mkdtemp()


def make_user(username, role, **extra) -> User:
    return User.objects.create_user(username=username, email=f"{username}@x.kg", password="x", first_name=username,
                                    role=role, is_verified=True, **extra)


def image_file(name="shot.png", fmt="PNG", size=(40, 30)) -> SimpleUploadedFile:
    buf = io.BytesIO()
    Image.new("RGB", size, (47, 143, 91)).save(buf, fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f"image/{fmt.lower()}")


@override_settings(MEDIA_ROOT=MEDIA)
class Base(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.it, _ = Subject.objects.get_or_create(name="IT")
        self.design, _ = Subject.objects.get_or_create(name="Design")
        self.course = Course.objects.create(name="NEXT", count_lesson=72)
        self.course.subjects.set([self.it])
        self.design_course = Course.objects.create(name="ART", count_lesson=40)
        self.design_course.subjects.set([self.design])

        self.trainer_user = make_user("islam", User.Role.TEACHER)
        self.trainer = Teacher.objects.create(user=self.trainer_user)
        self.other_user = make_user("aibek", User.Role.TEACHER)
        self.other = Teacher.objects.create(user=self.other_user)

        self.group = Group.objects.create(name="NEXT 1", course=self.course, start_date=dt.date(2026, 9, 1))
        GroupTeacher.objects.create(group=self.group, teacher=self.trainer, subject=self.it)
        self.other_group = Group.objects.create(name="ART 1", course=self.design_course, start_date=dt.date(2026, 9, 1))
        GroupTeacher.objects.create(group=self.other_group, teacher=self.other, subject=self.design)

        self.student = Student.objects.create(first_name="Алия", last_name="Садыкова", group=self.group)
        self.stranger = Student.objects.create(first_name="Бекзат", last_name="Ушаков", group=self.other_group)

        self.admin = make_user("boss", User.Role.ADMIN)
        self.lead = make_user("lead", User.Role.TEAM_LEAD)
        self.director = make_user("dir", User.Role.DIRECTOR)
        self.accountant = make_user("acc", User.Role.ACCOUNTANT)
        self.client = APIClient()

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def create(self, user=None, **data):
        body = {"student": self.student.pk, "title": "Weather App", "short_description": "Погода",
                "technologies": ["React", "TypeScript"], "project_date": "2026-11-02", "status": "published"}
        body.update(data)
        return self.as_(user or self.trainer_user).post(BASE, body, format="json")


class CreateTests(Base):
    def test_trainer_registers_project_group_follows_student(self):
        r = self.create()
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["group"], {"id": self.group.pk, "name": "NEXT 1"})
        self.assertEqual(r.data["author"]["id"], self.trainer_user.pk)
        self.assertEqual(r.data["technologies"], ["React", "TypeScript"])
        self.assertTrue(r.data["can_edit"])
        self.assertEqual(r.data["course"]["name"], "NEXT")

    def test_only_trainers_create(self):
        for user in (self.admin, self.lead, self.director):
            self.assertEqual(self.create(user).status_code, 403, user.role)
        self.assertEqual(StudentProject.objects.count(), 0)

    def test_trainer_cannot_pick_student_outside_own_groups(self):
        r = self.create(student=self.stranger.pk)
        self.assertEqual(r.status_code, 400)
        self.assertIn("student", r.data)

    def test_title_required_and_rating_range(self):
        self.assertIn("title", self.create(title="  ").data)
        self.assertIn("rating", self.create(rating=6).data)
        self.assertIn("github_url", self.create(github_url="not a url").data)

    def test_technologies_are_deduplicated_case_insensitively(self):
        self.create(technologies=["React", "react ", "Python"])
        self.create(title="Second", technologies=["REACT"])
        self.assertEqual(Technology.objects.count(), 2)


class VisibilityTests(Base):
    def setUp(self):
        super().setUp()
        self.published = StudentProject.objects.create(student=self.student, group=self.group, created_by=self.trainer_user,
                                                       title="Shop", status="published")
        self.draft = StudentProject.objects.create(student=self.student, group=self.group, created_by=self.trainer_user,
                                                   title="Draft", status="draft")
        self.foreign = StudentProject.objects.create(student=self.stranger, group=self.other_group,
                                                     created_by=self.other_user, title="Poster", status="published")

    def titles(self, user, query=""):
        r = self.as_(user).get(BASE + query)
        self.assertEqual(r.status_code, 200, r.data)
        return sorted(p["title"] for p in r.data["results"])

    def test_trainer_sees_own_and_own_groups_published(self):
        self.assertEqual(self.titles(self.trainer_user), ["Draft", "Shop"])
        self.assertEqual(self.titles(self.other_user), ["Poster"])

    def test_team_lead_sees_published_of_direction(self):
        self.assertEqual(self.titles(self.lead), ["Poster", "Shop"])  # no direction — whole academy
        TeamLeadDirection.objects.create(team_lead=self.lead, subject=self.design)
        self.assertEqual(self.titles(self.lead), ["Poster"])

    def test_director_and_admin(self):
        self.assertEqual(self.titles(self.director), ["Poster", "Shop"])
        self.assertEqual(self.titles(self.admin), ["Draft", "Poster", "Shop"])

    def test_other_roles_denied(self):
        self.assertEqual(self.as_(self.accountant).get(BASE).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(BASE).status_code, 401)

    def test_edit_and_delete_only_own(self):
        r = self.as_(self.other_user).patch(f"{BASE}{self.published.pk}/", {"title": "Hacked"}, format="json")
        self.assertEqual(r.status_code, 404)  # not even visible: another trainer's group
        # A co-trainer of the group sees the published project but cannot change it.
        GroupTeacher.objects.create(group=self.group, teacher=self.other, subject=self.design)
        self.assertEqual(self.as_(self.other_user).get(f"{BASE}{self.published.pk}/").status_code, 200)
        r = self.as_(self.other_user).patch(f"{BASE}{self.published.pk}/", {"title": "Hacked"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertFalse(self.as_(self.other_user).get(f"{BASE}{self.published.pk}/").data["can_edit"])
        self.assertEqual(self.as_(self.lead).delete(f"{BASE}{self.published.pk}/").status_code, 403)
        self.assertEqual(self.as_(self.director).patch(f"{BASE}{self.published.pk}/", {"title": "x"}, format="json").status_code, 403)
        r = self.as_(self.trainer_user).patch(f"{BASE}{self.published.pk}/", {"title": "Shop 2"}, format="json")
        self.assertEqual((r.status_code, r.data["title"]), (200, "Shop 2"))
        self.assertEqual(self.as_(self.trainer_user).delete(f"{BASE}{self.draft.pk}/").status_code, 204)
        self.assertEqual(self.as_(self.admin).delete(f"{BASE}{self.foreign.pk}/").status_code, 204)

    def test_draft_of_another_trainer_is_hidden(self):
        self.assertEqual(self.as_(self.other_user).get(f"{BASE}{self.draft.pk}/").status_code, 404)
        self.assertEqual(self.as_(self.lead).get(f"{BASE}{self.draft.pk}/").status_code, 404)

    def test_filters(self):
        self.published.technologies.add(Technology.objects.create(name="Vue"))
        self.assertEqual(self.titles(self.admin, "?technology=vue"), ["Shop"])
        self.assertEqual(self.titles(self.admin, f"?group={self.other_group.pk}"), ["Poster"])
        self.assertEqual(self.titles(self.admin, "?q=Садыкова"), ["Draft", "Shop"])
        self.assertEqual(self.titles(self.admin, "?status=draft"), ["Draft"])
        self.assertEqual(self.as_(self.admin).get(BASE + "?date_from=bad").status_code, 400)

    def test_stats_and_options(self):
        r = self.as_(self.trainer_user).get(BASE + "stats/")
        self.assertEqual((r.data["total_projects"], r.data["active_students"], r.data["groups_with_projects"]), (2, 1, 1))
        o = self.as_(self.trainer_user).get(BASE + "options/").data
        self.assertTrue(o["can_create"])
        self.assertEqual([s["full_name"] for s in o["selectable_students"]], ["Алия Садыкова"])
        self.assertEqual(o["selectable_students"][0]["group"]["name"], "NEXT 1")
        o = self.as_(self.lead).get(BASE + "options/").data
        self.assertFalse(o["can_create"])
        self.assertEqual(o["selectable_students"], [])


class ImageTests(Base):
    def setUp(self):
        super().setUp()
        self.project_id = self.create().data["id"]
        self.url = f"{BASE}{self.project_id}/images/"

    def upload(self, user=None, **extra):
        return self.as_(user or self.trainer_user).post(self.url, {"image": image_file(**extra)}, format="multipart")

    def test_first_image_becomes_cover_and_cover_moves(self):
        first = self.upload()
        self.assertEqual(first.status_code, 201, first.data)
        self.assertTrue(first.data["is_cover"])
        second = self.upload(name="b.webp", fmt="WEBP")
        self.assertFalse(second.data["is_cover"])
        r = self.as_(self.trainer_user).patch(f"{self.url}{second.data['id']}/", {"is_cover": True}, format="json")
        self.assertTrue(r.data["is_cover"])
        self.assertFalse(ProjectImage.objects.get(pk=first.data["id"]).is_cover)
        detail = self.as_(self.trainer_user).get(f"{BASE}{self.project_id}/").data
        self.assertEqual(len(detail["images"]), 2)
        self.assertTrue(detail["cover_url"].endswith(".webp"))

    def test_deleting_cover_promotes_next(self):
        a = self.upload().data
        b = self.upload().data
        self.assertEqual(self.as_(self.trainer_user).delete(f"{self.url}{a['id']}/").status_code, 204)
        self.assertTrue(ProjectImage.objects.get(pk=b["id"]).is_cover)

    def test_rejects_non_image_and_gif(self):
        bad = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
        r = self.as_(self.trainer_user).post(self.url, {"image": bad}, format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.upload(name="a.gif", fmt="GIF").status_code, 400)

    def test_only_author_uploads(self):
        self.assertEqual(self.upload(self.other_user).status_code, 404)  # another trainer's group: not visible
        self.assertEqual(self.upload(self.lead).status_code, 403)


class RoleAccessThroughMiddlewareTests(Base):
    """Real JWT requests: they pass through AccountingIsolationMiddleware the
    way the browser's do (force_authenticate would bypass it — the middleware
    only sees the Authorization header)."""

    ENDPOINTS = (BASE + "?page=1", BASE + "options/", BASE + "stats/")

    def setUp(self):
        super().setUp()
        self.published = StudentProject.objects.create(student=self.student, group=self.group,
                                                       created_by=self.trainer_user, title="Shop", status="published")
        StudentProject.objects.create(student=self.student, group=self.group, created_by=self.trainer_user,
                                      title="Draft", status="draft")

    def jwt(self, user) -> APIClient:
        from rest_framework_simplejwt.tokens import RefreshToken

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
        return client

    def assert_reads(self, user, expected_titles):
        client = self.jwt(user)
        for url in self.ENDPOINTS:
            r = client.get(url)
            self.assertEqual(r.status_code, 200, f"{user.role} {url}: {r.status_code} {getattr(r, 'data', r.content)}")
        r = client.get(BASE)
        self.assertEqual(sorted(p["title"] for p in r.data["results"]), expected_titles)
        self.assertEqual(client.get(f"{BASE}{self.published.pk}/").status_code, 200)

    def test_operations_director_reads_published_only(self):
        ops = make_user("ops", User.Role.OPERATIONS_DIRECTOR)
        self.assert_reads(ops, ["Shop"])
        client = self.jwt(ops)
        self.assertFalse(client.get(BASE + "options/").data["can_create"])
        self.assertEqual(client.get(BASE + "stats/").data["total_projects"], 1)
        self.assertEqual(client.post(BASE, {"student": self.student.pk, "title": "x"}, format="json").status_code, 403)
        self.assertEqual(client.patch(f"{BASE}{self.published.pk}/", {"title": "x"}, format="json").status_code, 403)
        self.assertEqual(client.delete(f"{BASE}{self.published.pk}/").status_code, 403)

    def test_academy_roles_read(self):
        self.assert_reads(self.trainer_user, ["Draft", "Shop"])
        self.assert_reads(self.lead, ["Shop"])
        self.assert_reads(self.director, ["Shop"])
        self.assert_reads(self.admin, ["Draft", "Shop"])

    def test_trainer_creates_through_middleware(self):
        r = self.jwt(self.trainer_user).post(BASE, {"student": self.student.pk, "title": "New"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)

    def test_roles_without_access_get_403(self):
        roles = [User.Role.ASSISTANT, User.Role.ACCOUNTANT, User.Role.DOP, User.Role.ROP,
                 User.Role.HR_MANAGER, User.Role.SALES_MANAGER, User.Role.MARKETING]
        for role in roles:
            client = self.jwt(make_user(f"u_{role}", role))
            for url in self.ENDPOINTS:
                self.assertEqual(client.get(url).status_code, 403, f"{role} {url}")

    def test_no_token_is_401(self):
        for url in self.ENDPOINTS:
            self.assertEqual(APIClient().get(url).status_code, 401, url)
