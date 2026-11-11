"""Public website API (/api/v1/public/site/) and the marketing CMS
(/api/v1/marketing/site/): only published content, translations, privacy,
leads without duplicates, event registration rules, role separation."""
from __future__ import annotations

import datetime as dt
import shutil
import tempfile

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academy.models import Course
from apps.projects.tests import image_file, make_user
from apps.users.models import Teacher, User

from . import public
from .models import (
    Achievement, Branch, CoursePage, Event, EventRegistration, HomeSection, Lead, SiteSettings, TeamMember,
    Testimonial, Workflow,
)

PUBLIC = "/api/v1/public/site/"
CMS = "/api/v1/marketing/site/"
MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=MEDIA, PUBLIC_WEBSITE_URL="https://kids.example.kg")
class Base(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.anon = APIClient()
        self.client = APIClient()
        self.now = timezone.now()
        self.lms_course = Course.objects.create(name="Python Start", count_lesson=72)

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def course(self, title="Python", status=Workflow.PUBLISHED, **extra):
        return CoursePage.objects.create(title=title, status=status, **extra)

    def event(self, title="Хакатон", days=5, status=Workflow.PUBLISHED, **extra):
        return Event.objects.create(title=title, status=status, starts_at=self.now + dt.timedelta(days=days), **extra)


class PublicVisibilityTests(Base):
    def test_only_published_and_due_content_is_public(self):
        self.course("Visible", course=self.lms_course, age_min=8, age_max=12)
        self.course("Draft", status=Workflow.DRAFT)
        self.course("Review", status=Workflow.REVIEW)
        self.course("Archived", status=Workflow.ARCHIVED)
        self.course("Scheduled", published_at=self.now + dt.timedelta(days=1))
        r = self.anon.get(f"{PUBLIC}courses/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([c["title"] for c in r.data["results"]], ["Visible"])
        self.assertEqual(r.data["results"][0]["lessons"], 72)
        self.assertEqual(self.anon.get(f"{PUBLIC}courses/draft/").status_code, 404)

    def test_course_detail_has_outcomes_and_curriculum_from_lines(self):
        page = self.course(outcomes="- Переменные\n- Циклы\n", curriculum="Основы: синтаксис\nИгры: pygame")
        r = self.anon.get(f"{PUBLIC}courses/{page.slug}/")
        self.assertEqual(r.data["outcomes"], ["Переменные", "Циклы"])
        self.assertEqual(r.data["curriculum"][1], {"title": "Игры", "text": "pygame"})
        self.assertIsNone(r.data["price"])  # never invented

    def test_translation_falls_back_to_russian(self):
        page = self.course("Программирование", title_en="Programming")
        en = self.anon.get(f"{PUBLIC}courses/{page.slug}/", {"lang": "en"}).data
        ky = self.anon.get(f"{PUBLIC}courses/{page.slug}/", {"lang": "ky"}).data
        self.assertEqual(en["title"], "Programming")
        self.assertEqual(ky["title"], "Программирование")

    def test_slug_is_transliterated(self):
        self.assertEqual(self.course("Веб разработка").slug, "veb-razrabotka")

    def test_a_staff_token_is_ignored(self):
        self.anon.credentials(HTTP_AUTHORIZATION="Bearer nope")
        self.assertEqual(self.anon.get(f"{PUBLIC}home/").status_code, 200)

    def test_home_respects_section_visibility(self):
        self.course()
        HomeSection.objects.create(key="courses", is_visible=False, order=0)
        r = self.anon.get(f"{PUBLIC}home/")
        self.assertNotIn("courses", [s["key"] for s in r.data["sections"]])
        self.assertEqual(r.data["courses"], [])
        self.assertEqual(r.data["hero"]["title"], "Будущее начинается с первой строки кода")

    def test_contacts_are_links(self):
        s = SiteSettings.load()
        s.whatsapp, s.telegram, s.instagram = "+996 555 12-34-56", "@okurmen", "okurmenkids"
        s.save()
        contacts = self.anon.get(f"{PUBLIC}settings/").data["contacts"]
        self.assertEqual(contacts["whatsapp"], "https://wa.me/996555123456")
        self.assertEqual(contacts["telegram"], "https://t.me/okurmen")
        self.assertEqual(contacts["instagram"], "https://instagram.com/okurmenkids")

    def test_only_get(self):
        self.assertEqual(self.anon.post(f"{PUBLIC}courses/", {}).status_code, 405)


class EventTests(Base):
    def test_phases_and_order(self):
        self.event("Later", days=10)
        self.event("Soon", days=1)
        self.event("Past", days=-10)
        r = self.anon.get(f"{PUBLIC}events/")
        self.assertEqual([e["title"] for e in r.data["results"]], ["Soon", "Later", "Past"])
        self.assertEqual(r.data["counts"], {"all": 3, "upcoming": 2, "ongoing": 0, "completed": 1})
        past = self.anon.get(f"{PUBLIC}events/", {"phase": "completed"}).data["results"]
        self.assertEqual([e["phase"] for e in past], ["completed"])

    def test_registration_flow(self):
        event = self.event(registration_enabled=True, registration_limit=1)
        url = f"{PUBLIC}events/{event.slug}/register/"
        body = {"parent_name": "Айгуль", "phone": "0555 123 456", "child_age": 9}
        self.assertEqual(self.anon.post(url, body, format="json").status_code, 201)
        again = self.anon.post(url, body, format="json")
        self.assertEqual((again.status_code, again.data["duplicate"]), (200, True))
        full = self.anon.post(url, {**body, "phone": "+996700000000"}, format="json")
        self.assertEqual(full.status_code, 409)
        self.assertEqual(EventRegistration.objects.count(), 1)
        detail = self.anon.get(f"{PUBLIC}events/{event.slug}/").data
        self.assertEqual(detail["registration"]["spots_left"], 0)
        self.assertNotIn("Айгуль", str(detail))  # registrations never public

    def test_registration_closed_when_disabled_or_past(self):
        closed = self.event("Closed")
        past = self.event("Past", days=-1, registration_enabled=True)
        body = {"parent_name": "Айгуль", "phone": "0555123456"}
        for event in (closed, past):
            self.assertEqual(self.anon.post(f"{PUBLIC}events/{event.slug}/register/", body, format="json").status_code, 409)

    def test_draft_event_cannot_be_registered(self):
        event = self.event(status=Workflow.DRAFT, registration_enabled=True)
        r = self.anon.post(f"{PUBLIC}events/{event.slug}/register/", {"parent_name": "Ай", "phone": "0555123456"}, format="json")
        self.assertEqual(r.status_code, 404)


class LeadTests(Base):
    def body(self, **extra):
        return {"parent_name": "Нурлан", "phone": "+996 (555) 12-34-56", "child_age": 10, "contact_method": "whatsapp",
                **extra}

    def test_valid_lead_is_saved_and_duplicates_merged(self):
        page = self.course()
        branch = Branch.objects.create(name="Центр", address="ул. Киевская 1")
        r = self.anon.post(f"{PUBLIC}leads/", self.body(course=page.slug, branch=branch.pk, message="Пробный урок?"),
                           format="json")
        self.assertEqual(r.status_code, 201)
        lead = Lead.objects.get()
        self.assertEqual((lead.course, lead.branch, lead.phone_digits), (page, branch, "996555123456"))
        again = self.anon.post(f"{PUBLIC}leads/", self.body(phone="0555123456", message="Ещё вопрос"), format="json")
        self.assertEqual((again.status_code, again.data["duplicate"]), (200, True))
        lead.refresh_from_db()
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(lead.repeat_count, 1)
        self.assertIn("Ещё вопрос", lead.message)

    def test_single_active_branch_is_attached_automatically(self):
        only = Branch.objects.create(name="Okurmen Kids", address="Орозбекова, 136")
        Branch.objects.create(name="Закрыт", address="—", is_active=False)
        self.assertEqual(self.anon.post(f"{PUBLIC}leads/", self.body(), format="json").status_code, 201)
        self.assertEqual(Lead.objects.get().branch, only)

    def test_several_branches_leave_the_choice_to_the_visitor(self):
        Branch.objects.create(name="A", address="a")
        Branch.objects.create(name="B", address="b")
        self.anon.post(f"{PUBLIC}leads/", self.body(), format="json")
        self.assertIsNone(Lead.objects.get().branch)

    def test_validation(self):
        r = self.anon.post(f"{PUBLIC}leads/", {"parent_name": "", "phone": "12", "child_age": 1}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(set(r.data), {"parent_name", "phone", "child_age"})
        unknown = self.anon.post(f"{PUBLIC}leads/", self.body(course="nope"), format="json")
        self.assertIn("course", unknown.data)

    def test_honeypot_silently_drops_bots(self):
        r = self.anon.post(f"{PUBLIC}leads/", self.body(website="http://spam"), format="json")
        self.assertEqual(r.status_code, 201)
        self.assertFalse(Lead.objects.exists())


class PrivacyTests(Base):
    def test_team_photo_only_with_consent_and_inactive_trainer_hidden(self):
        user = make_user("aibek", User.Role.TEACHER, last_name="Тренеров")
        teacher = Teacher.objects.create(user=user, phone="+996555000000", image=image_file(), experience_years=4)
        member = TeamMember.objects.create(teacher=teacher, position="Тренер", status=Workflow.PUBLISHED)
        item = self.anon.get(f"{PUBLIC}team/").data["results"][0]
        self.assertEqual(item["name"], "aibek Тренеров")
        self.assertIsNone(item["photo"])
        # Experience from the LMS record is not published: only what the site profile states.
        self.assertIsNone(item["experience_years"])
        self.assertNotIn("+996555000000", str(item))
        member.photo_approved = True
        member.save()
        self.assertIsNotNone(self.anon.get(f"{PUBLIC}team/").data["results"][0]["photo"])
        Teacher.objects.filter(pk=teacher.pk).update(is_active=False)
        self.assertEqual(self.anon.get(f"{PUBLIC}team/").data["results"], [])

    def test_team_group_is_public(self):
        TeamMember.objects.create(name="Айбек", position="Тренер", group=TeamMember.Group.IT_TRAINERS,
                                  status=Workflow.PUBLISHED)
        TeamMember.objects.create(name="Бермет", position="Менеджер", status=Workflow.PUBLISHED)
        groups = [m["group"] for m in self.anon.get(f"{PUBLIC}team/").data["results"]]
        self.assertEqual(groups, ["it_trainers", None])

    def test_profile_page_by_slug(self):
        lead = TeamMember.objects.create(name="Хадижа Асангазиева", position="IT-специалист", position_en="IT Specialist",
                                         group=TeamMember.Group.IT_TRAINERS, career="2023–н.в.: Тренер\n2021–2023: Разработчик",
                                         achievements="- Программа A", status=Workflow.PUBLISHED)
        TeamMember.objects.create(name="Нурсултан Караталов", position="Тренер", group=TeamMember.Group.IT_TRAINERS,
                                  status=Workflow.PUBLISHED)
        TeamMember.objects.create(name="Черновик", position="—", group=TeamMember.Group.IT_TRAINERS)
        self.assertEqual(lead.slug, "hadizha-asangazieva")
        listing = self.anon.get(f"{PUBLIC}team/").data["results"][0]
        self.assertNotIn("career", listing)
        r = self.anon.get(f"{PUBLIC}team/{lead.slug}/", {"lang": "en"}).data
        self.assertEqual(r["position"], "IT Specialist")
        self.assertEqual(r["positions"], {"ru": "IT-специалист", "ky": None, "en": "IT Specialist"})
        self.assertEqual(r["career"], ["2023–н.в.: Тренер", "2021–2023: Разработчик"])
        self.assertEqual(r["achievements"], ["Программа A"])
        self.assertEqual([c["name"] for c in r["colleagues"]], ["Нурсултан Караталов"])
        self.assertEqual(self.anon.get(f"{PUBLIC}team/chernovik/").status_code, 404)

    def test_testimonial_needs_consent(self):
        Testimonial.objects.create(author_name="Без согласия", text="…", status=Workflow.PUBLISHED, consent=False)
        Testimonial.objects.create(author_name="Айгуль", text="Спасибо!", rating=5, status=Workflow.PUBLISHED,
                                   consent=True, video_url="https://youtu.be/dQw4w9WgXcQ")
        r = self.anon.get(f"{PUBLIC}testimonials/").data
        self.assertEqual([t["author_name"] for t in r["results"]], ["Айгуль"])
        self.assertEqual(r["results"][0]["kind"], "video")
        self.assertEqual(r["results"][0]["video_embed"], "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ")
        self.assertEqual(r["average_rating"], 5.0)


class AchievementTests(Base):
    def test_group_filter_and_recipient(self):
        Achievement.objects.create(title="Олимпиада", category="competition", recipient="Алия С.", status=Workflow.PUBLISHED)
        Achievement.objects.create(title="Диплом", category="award", status=Workflow.PUBLISHED)
        Achievement.objects.create(title="Сертификат", category="certificate", status=Workflow.PUBLISHED)
        r = self.anon.get(f"{PUBLIC}achievements/", {"category": "award,certificate,recognition"}).data
        self.assertEqual(sorted(a["title"] for a in r["results"]), ["Диплом", "Сертификат"])
        self.assertEqual(r["counts"]["all"], 3)
        one = self.anon.get(f"{PUBLIC}achievements/", {"category": "competition"}).data["results"][0]
        self.assertEqual(one["recipient"], "Алия С.")
        self.assertEqual(self.anon.get(f"{PUBLIC}achievements/", {"category": "award,nope"}).status_code, 400)


class PreviewTests(Base):
    def test_signed_preview_shows_a_draft(self):
        item = Achievement.objects.create(title="Победа", status=Workflow.DRAFT)
        token = public.preview_token("achievement", item.pk)
        r = self.anon.get(f"{PUBLIC}preview/{token}/")
        self.assertEqual((r.status_code, r.data["kind"], r.data["item"]["title"]), (200, "achievement", "Победа"))
        self.assertEqual(r["Cache-Control"], "no-store")
        self.assertEqual(self.anon.get(f"{PUBLIC}preview/{token}x/").status_code, 404)
        self.assertEqual(self.anon.get(f"{PUBLIC}achievements/{item.slug}/").status_code, 404)


class CMSPermissionTests(Base):
    def setUp(self):
        super().setUp()
        self.marketing = make_user("mkt", User.Role.MARKETING)
        self.director = make_user("dir", User.Role.DIRECTOR)
        self.admin = make_user("boss", User.Role.ADMIN)
        self.teacher = make_user("trainer", User.Role.TEACHER)
        self.sales = make_user("sales", User.Role.SALES_MANAGER)

    def test_roles(self):
        for user, code in ((self.marketing, 200), (self.director, 200), (self.admin, 200), (self.teacher, 403),
                           (self.sales, 403)):
            self.assertEqual(self.as_(user).get(f"{CMS}events/").status_code, code, user.role)
        self.assertEqual(APIClient().get(f"{CMS}events/").status_code, 401)
        # Sales sees leads, never content; a trainer sees neither.
        self.assertEqual(self.as_(self.sales).get(f"{CMS}leads/").status_code, 200)
        self.assertEqual(self.as_(self.teacher).get(f"{CMS}leads/").status_code, 403)

    def test_marketing_creates_publishes_and_previews(self):
        c = self.as_(self.marketing)
        r = c.post(f"{CMS}events/", {"title": "День открытых дверей", "category": "open_day",
                                     "starts_at": (self.now + dt.timedelta(days=3)).isoformat()}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data["workflow_state"], "draft")
        self.assertTrue(r.data["preview"]["url"].startswith("https://kids.example.kg/preview/"))
        published = c.post(f"{CMS}events/{r.data['id']}/publish/", {}, format="json")
        self.assertEqual(published.data["workflow_state"], "published")
        self.assertEqual(published.data["public_url"], f"https://kids.example.kg/events/{r.data['slug']}")
        self.assertEqual(self.anon.get(f"{PUBLIC}events/").data["count"], 1)

    def test_model_rules_apply_in_the_api(self):
        r = self.as_(self.marketing).post(f"{CMS}events/", {
            "title": "X", "starts_at": self.now.isoformat(), "ends_at": (self.now - dt.timedelta(hours=1)).isoformat(),
        }, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("ends_at", r.data)
        bad = self.as_(self.marketing).post(f"{CMS}testimonials/", {
            "author_name": "А", "text": "Да", "status": "published", "consent": False}, format="json")
        self.assertIn("consent", bad.data)

    @override_settings(WEBSITE_REQUIRE_APPROVAL=True)
    def test_approval_workflow(self):
        page = self.course("Robotics", status=Workflow.DRAFT)
        mkt = self.as_(self.marketing)
        self.assertEqual(mkt.post(f"{CMS}courses/{page.pk}/publish/").status_code, 403)
        self.assertEqual(mkt.patch(f"{CMS}courses/{page.pk}/", {"status": "published"}, format="json").status_code, 400)
        self.assertEqual(mkt.post(f"{CMS}courses/{page.pk}/submit_review/").data["workflow_state"], "review")
        approved = self.as_(self.director).post(f"{CMS}courses/{page.pk}/publish/")
        self.assertEqual(approved.data["workflow_state"], "published")
        self.assertEqual(approved.data["reviewed_by_name"], "dir")

    def test_upload_cover_and_gallery(self):
        c = self.as_(self.marketing)
        r = c.post(f"{CMS}achievements/", {"title": "Олимпиада", "cover": image_file()}, format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertTrue(r.data["cover"])
        item = Achievement.objects.get()
        self.assertTrue(item.cover_thumb.name.endswith(".webp"))
        photos = c.post(f"{CMS}achievements/{item.pk}/photos/", {"files": [image_file("a.png"), image_file("b.png")]},
                        format="multipart")
        self.assertEqual(len(photos.data["photos"]), 2)
        pid = photos.data["photos"][0]["id"]
        self.assertEqual(c.patch(f"{CMS}achievements/{item.pk}/photos/{pid}/", {"caption": "Диплом"}, format="json")
                         .data["photos"][0]["caption"], "Диплом")
        self.assertEqual(len(c.delete(f"{CMS}achievements/{item.pk}/photos/{pid}/").data["photos"]), 1)

    def test_news_management_for_marketing(self):
        c = self.as_(self.marketing)
        r = c.post(f"{CMS}news/", {"title": "Новый курс", "body": "Текст", "category": "announcements"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.anon.get("/api/v1/public/news/").data["count"], 0)
        c.post(f"{CMS}news/{r.data['id']}/publish/")
        self.assertEqual(self.anon.get(f"/api/v1/public/news/{r.data['slug']}/").status_code, 200)

    def test_sections_settings_and_meta(self):
        c = self.as_(self.marketing)
        sections = c.get(f"{CMS}sections/").data
        self.assertEqual(len(sections), len(HomeSection.Key.values))
        c.post(f"{CMS}sections/reorder/", {"keys": ["testimonials", "stats"]}, format="json")
        self.assertEqual(self.anon.get(f"{PUBLIC}settings/").data["sections"][0]["key"], "testimonials")
        self.assertEqual(c.patch(f"{CMS}settings/", {"phone": "+996 312 000 000"}, format="json").status_code, 200)
        meta = c.get(f"{CMS}meta/").data
        self.assertTrue(meta["permissions"]["can_edit"])
        self.assertIn("courses", meta["lms"])

    def test_lead_status_only_editable_fields(self):
        lead = Lead.objects.create(parent_name="Нурлан", phone="0555", phone_digits="555", child_age=9)
        r = self.as_(self.sales).patch(f"{CMS}leads/{lead.pk}/", {"status": "contacted", "parent_name": "X"},
                                       format="json")
        lead.refresh_from_db()
        self.assertEqual((lead.status, lead.parent_name), ("contacted", "Нурлан"))
        self.assertEqual(self.as_(self.sales).delete(f"{CMS}leads/{lead.pk}/").status_code, 403)
        self.assertEqual(r.status_code, 200)


class CorsTests(Base):
    def test_public_website_origin_is_allowed_by_default(self):
        site = "https://okurmen-public-website.vercel.app"
        r = self.anon.get(f"{PUBLIC}home/", {"lang": "ky"}, HTTP_ORIGIN=site)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Access-Control-Allow-Origin"], site)
        other = self.anon.get(f"{PUBLIC}home/", HTTP_ORIGIN="https://evil.example.com")
        self.assertNotIn("Access-Control-Allow-Origin", other)
