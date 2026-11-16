"""«Сообщество»: pre-moderation, visibility, contact filter, comments and
replies, likes, reports and auto-hide, moderator scope, private photos,
announcements, notifications, and the website hand-off of reviews."""
from __future__ import annotations

import io

from django.test import override_settings
from django.urls import reverse
from PIL import Image
from rest_framework.test import APIClient

from apps.portal.tests import PortalTestBase
from apps.users.models import Teacher, User
from apps.website.models import Testimonial, Workflow

from .models import Comment, CommentStatus, CommunityNotification, Post, PostImage, PostStatus

STAFF = "/api/v1/community"


def jpeg_with_gps() -> io.BytesIO:
    image = Image.new("RGB", (800, 600), (40, 160, 90))
    exif = Image.Exif()
    exif[0x010F] = "PhoneMaker"          # Make
    exif[0x8825] = {2: (42, 52, 0)}      # GPSInfo
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif)
    buffer.seek(0)
    buffer.name = "photo.jpg"
    return buffer


class CommunityBase(PortalTestBase):
    def setUp(self):
        super().setUp()
        self.a_client, self.a, _ = self.portal_client("Айбек", "Асанов")
        self.b_client, self.b, _ = self.portal_client("Бек", "Бекова")
        self.c_client, self.c, _ = self.portal_client("Чынара", "Чынова", group=self.g2)
        self.admin = User.objects.create_user(username="boss", email="boss@x.kg", password="x", role=User.Role.ADMIN)
        self.admin_api = self.api(self.admin)
        self.assistant_api = self.staff
        self.teacher_api = self.api(self.teacher.user)

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def url(self, name, student, **kwargs):
        return reverse(f"portal:community-{name}", kwargs={"student_id": student.pk, **kwargs})

    def publish(self, client=None, student=None, **data):
        client, student = client or self.a_client, student or self.a
        body = {"text": "Сделал свою первую игру на Python!", "category": "achievement", **data}
        response = client.post(self.url("feed", student), body, format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        return Post.objects.get(pk=response.data["id"])

    def approve(self, post, client=None):
        response = (client or self.assistant_api).post(f"{STAFF}/posts/{post.pk}/approve/")
        self.assertEqual(response.status_code, 200, response.data)
        post.refresh_from_db()
        return post

    def feed_ids(self, client, student):
        data = client.get(self.url("feed", student)).data
        return [p["id"] for p in data["pinned"]] + [p["id"] for p in data["results"]]


class PublicationTests(CommunityBase):
    def test_a_post_is_reviewed_before_anyone_else_sees_it(self):
        post = self.publish()
        self.assertEqual(post.status, PostStatus.PENDING)
        self.assertNotIn(post.pk, self.feed_ids(self.b_client, self.b))
        self.assertEqual(self.b_client.get(self.url("post", self.b, post_id=post.pk)).status_code, 404)
        mine = self.a_client.get(self.url("mine", self.a)).data["results"]
        self.assertEqual([(p["id"], p["status"]) for p in mine], [(post.pk, "pending")])
        queue = self.assistant_api.get(f"{STAFF}/posts/", {"status": "pending"}).data["results"]
        self.assertEqual([p["id"] for p in queue], [post.pk])

        self.approve(post)
        self.assertIn(post.pk, self.feed_ids(self.b_client, self.b))
        self.assertIn(post.pk, self.feed_ids(self.c_client, self.c))   # academy-wide
        row = self.b_client.get(self.url("feed", self.b)).data["results"][0]
        self.assertEqual((row["author"]["name"], row["author"]["group"]["name"]), ("Айбек Асанов", "PRO-01"))
        for private in ("parent_phone", "birth_date", "branch", "phone"):
            self.assertNotIn(private, row["author"])
        self.assertTrue(CommunityNotification.objects.filter(recipient=self.a, kind="approved").exists())

    def test_group_only_posts_stay_in_the_group(self):
        post = self.approve(self.publish(audience="group"))
        self.assertIn(post.pk, self.feed_ids(self.b_client, self.b))
        self.assertNotIn(post.pk, self.feed_ids(self.c_client, self.c))
        self.assertEqual(self.c_client.get(self.url("post", self.c, post_id=post.pk)).status_code, 404)

    def test_reject_with_feedback_then_edit_goes_back_to_review(self):
        post = self.publish()
        self.assertEqual(self.assistant_api.post(f"{STAFF}/posts/{post.pk}/reject/", {"note": ""}).status_code, 400)
        self.assistant_api.post(f"{STAFF}/posts/{post.pk}/reject/", {"note": "Уберите фамилию друга"})
        post.refresh_from_db()
        self.assertEqual(post.status, PostStatus.REJECTED)
        note = CommunityNotification.objects.get(recipient=self.a, kind="rejected").note
        self.assertEqual(note, "Уберите фамилию друга")
        mine = self.a_client.get(self.url("mine", self.a)).data["results"][0]
        self.assertEqual(mine["moderation"]["note"], "Уберите фамилию друга")
        response = self.a_client.patch(self.url("post", self.a, post_id=post.pk),
                                       {"text": "Сделал игру!", "category": "achievement"}, format="multipart")
        self.assertEqual(response.data["status"], "pending")

    def test_editing_a_published_post_hides_it_until_reviewed(self):
        post = self.approve(self.publish())
        self.a_client.patch(self.url("post", self.a, post_id=post.pk), {"text": "Новый текст", "category": "general"},
                            format="multipart")
        post.refresh_from_db()
        self.assertEqual(post.status, PostStatus.PENDING)
        self.assertNotIn(post.pk, self.feed_ids(self.b_client, self.b))

    def test_drafts_are_private_to_the_author(self):
        response = self.a_client.post(self.url("feed", self.a), {"text": "черновик", "submit": "false"}, format="multipart")
        self.assertEqual(response.data["status"], "draft")
        self.assertEqual(self.assistant_api.get(f"{STAFF}/posts/", {"status": "all"}).data["count"], 0)
        self.assertEqual(self.assistant_api.get(f"{STAFF}/posts/{response.data['id']}/").status_code, 404)

    def test_only_the_author_edits_or_deletes(self):
        post = self.approve(self.publish())
        self.assertEqual(self.b_client.delete(self.url("post", self.b, post_id=post.pk)).status_code, 404)
        # The family account cannot act as someone else's child either.
        self.assertEqual(self.a_client.get(self.url("feed", self.b)).status_code, 404)
        self.assertEqual(self.a_client.delete(self.url("post", self.a, post_id=post.pk)).status_code, 204)
        self.assertFalse(Post.objects.filter(pk=post.pk).exists())

    def test_students_cannot_post_news(self):
        response = self.a_client.post(self.url("feed", self.a), {"text": "Новость", "category": "news"}, format="multipart")
        self.assertEqual(response.status_code, 400)


class SafetyTests(CommunityBase):
    def test_contact_details_and_links_are_refused(self):
        for text in ("Пиши мне +996 555 12 34 56", "мой ник @aibek_2014", "почта a@b.kg", "заходи на site.com",
                     "давай в телеграм", "живу ул. Токтогула 5"):
            response = self.a_client.post(self.url("feed", self.a), {"text": text}, format="multipart")
            self.assertEqual(response.status_code, 400, text)
            self.assertIn("text", response.data)
        self.assertFalse(Post.objects.exists())

    def test_project_link_only_to_project_sites(self):
        ok = self.publish(category="project", project_url="https://github.com/aibek/snake")
        self.assertEqual(ok.project_url, "https://github.com/aibek/snake")
        bad = self.a_client.post(self.url("feed", self.a), {"text": "проект", "project_url": "https://evil.example.com"},
                                 format="multipart")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("project_url", bad.data)

    def test_comments_are_filtered_too(self):
        post = self.approve(self.publish())
        response = self.b_client.post(self.url("comments", self.b, post_id=post.pk), {"text": "мой номер 0555123456"})
        self.assertEqual(response.status_code, 400)


class InteractionTests(CommunityBase):
    def test_like_unlike_and_one_notification(self):
        post = self.approve(self.publish())
        url = self.url("like", self.b, post_id=post.pk)
        self.assertEqual(self.b_client.post(url, {"liked": True}, format="json").data, {"liked": True, "likes": 1})
        self.b_client.post(url, {"liked": True}, format="json")
        self.assertEqual(self.b_client.post(url, {"liked": False}, format="json").data["likes"], 0)
        self.b_client.post(url, {"liked": True}, format="json")
        self.assertEqual(CommunityNotification.objects.filter(recipient=self.a, kind="like").count(), 1)
        row = self.b_client.get(self.url("feed", self.b)).data["results"][0]
        self.assertEqual((row["likes"], row["liked"]), (1, True))

    def test_pending_posts_cannot_be_liked_or_commented(self):
        post = self.publish()
        self.assertEqual(self.a_client.post(self.url("like", self.a, post_id=post.pk), {}, format="json").status_code, 403)
        self.assertEqual(self.a_client.post(self.url("comments", self.a, post_id=post.pk), {"text": "hi"}).status_code, 403)

    def test_comments_replies_notifications_and_deletion(self):
        post = self.approve(self.publish())
        top = self.b_client.post(self.url("comments", self.b, post_id=post.pk), {"text": "Круто!"}).data
        reply = self.a_client.post(self.url("comments", self.a, post_id=post.pk), {"text": "Спасибо", "parent": top["id"]}).data
        nested = self.c_client.post(self.url("comments", self.c, post_id=post.pk), {"text": "И я", "parent": reply["id"]}).data
        self.assertEqual(nested["parent"], top["id"])   # one level of replies
        tree = self.b_client.get(self.url("comments", self.b, post_id=post.pk)).data
        self.assertEqual([(c["text"], [r["text"] for r in c["replies"]]) for c in tree], [("Круто!", ["Спасибо", "И я"])])
        kinds = set(CommunityNotification.objects.values_list("recipient_id", "kind"))
        self.assertIn((self.a.pk, "comment"), kinds)
        self.assertIn((self.b.pk, "reply"), kinds)
        # Someone else's comment cannot be deleted; one's own can.
        self.assertEqual(self.a_client.delete(self.url("comment", self.a, comment_id=top["id"])).status_code, 403)
        self.assertEqual(self.b_client.delete(self.url("comment", self.b, comment_id=top["id"])).status_code, 204)
        tree = self.a_client.get(self.url("comments", self.a, post_id=post.pk)).data
        self.assertEqual((tree[0]["status"], tree[0]["text"], tree[0]["author"]), ("deleted", "", None))
        self.assertEqual(len(tree[0]["replies"]), 2)
        self.assertEqual(self.a_client.get(self.url("feed", self.a)).data["results"][0]["comments"], 2)

    def test_notifications_list_and_read(self):
        post = self.approve(self.publish())
        self.b_client.post(self.url("comments", self.b, post_id=post.pk), {"text": "Класс"})
        data = self.a_client.get(self.url("notifications", self.a)).data
        self.assertEqual(data["unread"], 2)   # approved + comment
        self.assertEqual({n["kind"] for n in data["results"]}, {"approved", "comment"})
        self.assertEqual(self.a_client.post(self.url("notifications", self.a), {}, format="json").data["unread"], 0)


class ReportTests(CommunityBase):
    def test_three_reports_hide_a_post_until_reviewed(self):
        post = self.approve(self.publish())
        d_client, d, _ = self.portal_client("Данияр", "Д")
        for client, student in ((self.b_client, self.b), (self.c_client, self.c)):
            response = client.post(self.url("report-post", student, post_id=post.pk), {"reason": "bullying"})
            self.assertEqual(response.status_code, 201)
        self.assertEqual(self.b_client.post(self.url("report-post", self.b, post_id=post.pk),
                                            {"reason": "spam"}).status_code, 400)  # once per student
        post.refresh_from_db()
        self.assertEqual(post.status, PostStatus.APPROVED)  # two reports: still visible
        self.assertEqual(d_client.post(self.url("report-post", d, post_id=post.pk), {"reason": "bullying"}).status_code, 201)
        post.refresh_from_db()
        self.assertEqual(post.status, PostStatus.HIDDEN)
        self.assertNotIn(post.pk, self.feed_ids(self.b_client, self.b))
        reports = self.assistant_api.get(f"{STAFF}/reports/").data
        self.assertEqual(reports["count"], 3)
        self.approve(post)  # a moderator restores it; the reports are closed
        self.assertEqual(self.assistant_api.get(f"{STAFF}/reports/").data["count"], 0)

    def test_reported_comment_hidden_by_moderator(self):
        post = self.approve(self.publish())
        comment = self.b_client.post(self.url("comments", self.b, post_id=post.pk), {"text": "глупый пост"}).data
        self.c_client.post(self.url("report-comment", self.c, comment_id=comment["id"]), {"reason": "bullying"})
        report = self.teacher_api.get(f"{STAFF}/reports/").data["results"][0]
        self.assertEqual(report["target"], "comment")
        self.teacher_api.post(f"{STAFF}/comments/{comment['id']}/hide/", {"hidden": True}, format="json")
        self.assertEqual(Comment.objects.get(pk=comment["id"]).status, CommentStatus.HIDDEN)
        self.assertEqual(self.a_client.get(self.url("comments", self.a, post_id=post.pk)).data, [])


class ModerationScopeTests(CommunityBase):
    def test_trainer_moderates_only_their_groups(self):
        post = self.publish()
        other = Teacher.objects.create(user=User.objects.create_user(username="t2", email="t2@x.kg", password="x",
                                                                     role=User.Role.TEACHER, is_verified=True))
        outsider = self.api(other.user)
        self.assertEqual(outsider.get(f"{STAFF}/posts/").data["count"], 0)
        self.assertEqual(outsider.post(f"{STAFF}/posts/{post.pk}/approve/").status_code, 404)
        self.approve(post, client=self.teacher_api)   # teaches PRO-01
        self.assertEqual(post.moderated_by, self.teacher.user)

    def test_non_staff_and_families_are_kept_out(self):
        accountant = self.api(User.objects.create_user(username="buh", email="b@x.kg", password="x",
                                                       role=User.Role.ACCOUNTANT))
        self.assertIn(accountant.get(f"{STAFF}/posts/").status_code, (403,))
        self.assertEqual(self.a_client.get(f"{STAFF}/posts/").status_code, 403)
        self.assertEqual(APIClient().get(f"{STAFF}/posts/").status_code, 401)

    def test_hide_and_pin(self):
        post = self.approve(self.publish())
        self.assistant_api.post(f"{STAFF}/posts/{post.pk}/pin/", {"pinned": True}, format="json")
        data = self.b_client.get(self.url("feed", self.b)).data
        self.assertEqual([p["id"] for p in data["pinned"]], [post.pk])
        self.assistant_api.post(f"{STAFF}/posts/{post.pk}/hide/", {"note": "Фото другого ребёнка"})
        post.refresh_from_db()
        self.assertEqual((post.status, post.is_pinned), (PostStatus.HIDDEN, False))
        self.assertNotIn(post.pk, self.feed_ids(self.b_client, self.b))
        self.assertTrue(CommunityNotification.objects.filter(recipient=self.a, kind="hidden").exists())

    def test_announcements(self):
        response = self.assistant_api.post(f"{STAFF}/announcements/", {"text": "Хакатон в субботу!", "pinned": "true"},
                                           format="multipart")
        self.assertEqual(response.status_code, 201)
        pinned = self.c_client.get(self.url("feed", self.c)).data["pinned"]
        self.assertEqual((pinned[0]["author"]["type"], pinned[0]["author"]["name"], pinned[0]["category"]),
                         ("academy", "Okurmen Kids", "news"))
        # A trainer: only for their own group.
        self.assertEqual(self.teacher_api.post(f"{STAFF}/announcements/", {"text": "Всем"}).status_code, 403)
        own = self.teacher_api.post(f"{STAFF}/announcements/", {"text": "Группе", "group": self.g1.pk})
        self.assertEqual(own.status_code, 201)
        self.assertIn(own.data["id"], self.feed_ids(self.b_client, self.b))
        self.assertNotIn(own.data["id"], self.feed_ids(self.c_client, self.c))


class MediaTests(CommunityBase):
    def test_photos_are_private_reencoded_and_signed(self):
        response = self.a_client.post(self.url("feed", self.a), {"text": "Мой робот", "images": [jpeg_with_gps()]},
                                      format="multipart")
        self.assertEqual(response.status_code, 201, response.data)
        image = PostImage.objects.get()
        with image.large.storage.open(image.large.name, "rb") as handle:
            stored = Image.open(handle)
            self.assertEqual(stored.format, "WEBP")
            self.assertFalse(dict(stored.getexif()))          # no camera / GPS metadata
        from apps.recruitment.storage import private_root

        self.assertTrue(image.large.storage.location.startswith(private_root()))  # outside the served /media/
        with self.assertRaises(ValueError):
            image.large.url                                     # no public address
        link = response.data["images"][0]["thumb"]
        anonymous = APIClient().get(link)
        self.assertEqual(anonymous.status_code, 200)
        self.assertEqual(anonymous["X-Robots-Tag"], "noindex, nofollow, noarchive")
        self.assertEqual(APIClient().get(link.replace("/media/", "/media/x")).status_code, 404)

    def test_not_an_image_and_too_many(self):
        bad = io.BytesIO(b"not an image")
        bad.name = "x.jpg"
        response = self.a_client.post(self.url("feed", self.a), {"text": "фото", "images": [bad]}, format="multipart")
        self.assertEqual(response.status_code, 400)
        many = [jpeg_with_gps() for _ in range(7)]
        response = self.a_client.post(self.url("feed", self.a), {"text": "фото", "images": many}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Post.objects.exists())


class ProfileTests(CommunityBase):
    def test_classmate_profile_without_private_data(self):
        project = self.approve(self.publish(category="project", project_url="https://scratch.mit.edu/projects/1"))
        data = self.b_client.get(self.url("profile", self.b, other_id=self.a.pk)).data
        self.assertEqual((data["name"], data["group"]["name"], data["posts_count"]), ("Айбек Асанов", "PRO-01", 1))
        self.assertEqual([p["id"] for p in data["projects"]], [project.pk])
        for private in ("parent_phone", "birth_date", "branch", "payments", "parent_name"):
            self.assertNotIn(private, data)

    def test_strangers_without_visible_posts_are_not_found(self):
        self.assertEqual(self.c_client.get(self.url("profile", self.c, other_id=self.a.pk)).status_code, 404)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "testimonials-lifecycle"}},
    PUBLIC_SITE_CACHE_SECONDS=120,
)
class WebsiteTests(CommunityBase):
    """The whole review lifecycle as okurmenkids.com sees it: the public site
    reads GET /api/v1/public/site/testimonials/ (cached like in production)."""

    PUBLIC = "/api/v1/public/site/testimonials/"

    def setUp(self):
        super().setUp()
        from django.core.cache import cache

        cache.clear()
        self.director = self.api(User.objects.create_user(username="dir", email="dir@x.kg", password="x",
                                                          role=User.Role.DIRECTOR))

    def review(self, consent: bool = True, text="Мне очень нравится учиться в Okurmen Kids!", client=None, student=None):
        return self.publish(client, student, category="review", text=text, website_consent="true" if consent else "false")

    def public(self, lang="ru"):
        response = APIClient().get(self.PUBLIC, {"lang": lang, "page_size": 36})
        self.assertEqual(response.status_code, 200)
        return {row["text"]: row for row in response.data["results"]}

    def test_submit_approve_and_it_is_on_the_site_in_every_language(self):
        post = self.review()
        self.assertEqual(self.public(), {})                                    # pending: not public
        response = self.admin_api.post(f"{STAFF}/posts/{post.pk}/approve/", {"website": True}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["website"]["is_public"])
        for lang in ("ru", "ky", "en"):                                         # /testimonials, /ky/…, /en/…
            row = self.public(lang)[post.text]
            self.assertEqual((row["author_name"], row["author_role"], row["course"], row["photo"], row["language"]),
                             ("Айбек А.", "student", "Prog", None, "ru"))
        self.assertNotIn("Асанов", str(self.public()))                           # no surname
        # Approving again / publishing again never duplicates the record.
        self.admin_api.post(f"{STAFF}/posts/{post.pk}/to-website/")
        self.assertEqual(Testimonial.objects.count(), 1)

    def test_approval_publishes_a_consented_review_automatically(self):
        """«там авто должен»: the moderator's approval is enough — no second step."""
        post = self.review()
        self.assistant_api.post(f"{STAFF}/posts/{post.pk}/approve/")         # an assistant, plain «Одобрить»
        self.assertIn(post.text, self.public())
        for lang in ("ky", "en"):
            self.assertIn(post.text, self.public(lang))
        self.assertEqual(Testimonial.objects.count(), 1)
        # A teacher approving a review of their own group: the same.
        other = self.review(text="Ислам агай лучший тренер")
        self.teacher_api.post(f"{STAFF}/posts/{other.pk}/approve/")
        self.assertIn(other.text, self.public())

    def test_language_of_the_review(self):
        post = self.approve(self.review(text="Эң жакшы академия, мугалимдер күчтүү!"))
        self.director.post(f"{STAFF}/posts/{post.pk}/to-website/")
        self.assertEqual(self.public()[post.text]["language"], "ky")

    def test_rejected_hidden_edited_or_deleted_reviews_leave_the_site(self):
        for action in ("reject", "hide", "edit", "delete"):
            post = self.approve(self.review(text=f"Отличные уроки — {action}"))
            self.admin_api.post(f"{STAFF}/posts/{post.pk}/to-website/")
            self.assertIn(post.text, self.public(), action)
            if action in ("reject", "hide"):
                self.assistant_api.post(f"{STAFF}/posts/{post.pk}/{action}/", {"note": "Не для сайта"})
            elif action == "edit":
                self.a_client.patch(self.url("post", self.a, post_id=post.pk),
                                    {"text": "Новый текст", "category": "review", "website_consent": "true"}, format="multipart")
            else:
                self.a_client.delete(self.url("post", self.a, post_id=post.pk))
            self.assertNotIn(post.text, self.public(), action)
        # Kept for history in the CMS, archived — never deleted, never duplicated.
        self.assertEqual(set(Testimonial.objects.values_list("status", flat=True)), {Workflow.ARCHIVED})

    def test_unpublish_and_republish_reuse_the_same_record(self):
        post = self.approve(self.review())
        self.admin_api.post(f"{STAFF}/posts/{post.pk}/to-website/")
        self.admin_api.post(f"{STAFF}/posts/{post.pk}/from-website/")
        self.assertNotIn(post.text, self.public())
        self.admin_api.post(f"{STAFF}/posts/{post.pk}/to-website/")
        self.assertIn(post.text, self.public())
        self.assertEqual(Testimonial.objects.count(), 1)

    def test_nothing_unapproved_or_unconsented_goes_public(self):
        pending = self.review()
        self.assertEqual(self.admin_api.post(f"{STAFF}/posts/{pending.pk}/to-website/").status_code, 400)
        no_consent = self.approve(self.review(consent=False, text="Без согласия"))
        self.assertEqual(self.admin_api.post(f"{STAFF}/posts/{no_consent.pk}/to-website/").status_code, 400)
        self.assertEqual(self.admin_api.post(f"{STAFF}/posts/{no_consent.pk}/approve/", {"website": True},
                                             format="json").status_code, 400)
        general = self.approve(self.publish(category="general", text="Обычный пост", website_consent="true"))
        self.assertEqual(self.admin_api.post(f"{STAFF}/posts/{general.pk}/to-website/").status_code, 400)
        self.assertEqual(self.public(), {})
        self.assertFalse(Testimonial.objects.filter(status=Workflow.PUBLISHED).exists())

    def test_publishing_by_hand_only_by_those_who_publish_on_the_website(self):
        post = self.approve(self.review())                                       # live automatically
        self.admin_api.post(f"{STAFF}/posts/{post.pk}/from-website/")
        for client in (self.teacher_api, self.assistant_api):
            self.assertEqual(client.post(f"{STAFF}/posts/{post.pk}/to-website/").status_code, 403)
            self.assertEqual(client.post(f"{STAFF}/posts/{post.pk}/from-website/").status_code, 403)
        self.assertEqual(self.public(), {})
        self.assertEqual(self.director.post(f"{STAFF}/posts/{post.pk}/to-website/").status_code, 200)
        self.assertIn(post.text, self.public())

    def test_backfill_publishes_reviews_approved_before(self):
        from importlib import import_module

        from django.apps import apps as django_apps

        legacy = self.review(text="Эмир: мне очень нравится")
        Post.objects.filter(pk=legacy.pk).update(status=PostStatus.APPROVED)
        no_consent = self.review(consent=False, text="Без согласия")
        Post.objects.filter(pk=no_consent.pk).update(status=PostStatus.APPROVED)
        general = self.publish(category="general", text="Обычный пост")
        Post.objects.filter(pk=general.pk).update(status=PostStatus.APPROVED)
        pending = self.review(text="Ещё на проверке")
        taken_off = self.approve(self.review(text="Снят администратором"))
        self.admin_api.post(f"{STAFF}/posts/{taken_off.pk}/from-website/")
        migration = import_module("apps.community.migrations.0002_publish_approved_reviews")
        migration.publish_waiting(django_apps, None)
        migration.publish_waiting(django_apps, None)                              # idempotent
        shown = self.public()
        self.assertIn(legacy.text, shown)
        self.assertEqual(shown[legacy.text]["author_name"], "Айбек А.")
        for post in (no_consent, general, pending, taken_off):
            self.assertNotIn(post.text, shown)
        self.assertEqual(Testimonial.objects.count(), 2)                           # legacy + the archived one

    def test_consent_only_for_reviews(self):
        post = self.publish(category="general", website_consent="true")
        self.assertFalse(post.website_consent)

    def test_taken_off_by_hand_is_waiting_until_published_again(self):
        live = self.approve(self.review(text="Ислам агай лучший тренер"))
        self.approve(self.review(consent=False, text="Без согласия"))
        self.assertIn(live.text, self.public())
        self.assertEqual(self.admin_api.get(f"{STAFF}/meta/").data["website_waiting"], 0)
        self.admin_api.post(f"{STAFF}/posts/{live.pk}/from-website/")
        self.assertNotIn(live.text, self.public())
        rows = self.admin_api.get(f"{STAFF}/posts/", {"status": "approved", "website": "waiting"}).data["results"]
        self.assertEqual([(r["id"], r["website_eligible"]) for r in rows], [(live.pk, True)])
        self.admin_api.post(f"{STAFF}/posts/{live.pk}/to-website/")
        self.assertIn(live.text, self.public())
        live_rows = self.admin_api.get(f"{STAFF}/posts/", {"status": "approved", "website": "live"}).data["results"]
        self.assertEqual([r["id"] for r in live_rows], [live.pk])
        self.assertEqual(Testimonial.objects.count(), 1)

    def test_audit_command_is_read_only_unless_asked(self):
        from io import StringIO

        from django.core.management import call_command

        # A review approved the old way (before automatic publishing): approved, consent, no testimonial.
        legacy = self.review(text="Талант: islam teacher the best")
        Post.objects.filter(pk=legacy.pk).update(status=PostStatus.APPROVED)
        self.approve(self.review(consent=False, text="Без согласия"))
        out = StringIO()
        call_command("community_website_audit", stdout=out)
        report = out.getvalue()
        self.assertIn("WAITING", report)
        self.assertIn("not eligible", report)
        self.assertIn("Eligible but not on the website: 1", report)
        self.assertFalse(Testimonial.objects.exists())                         # nothing changed
        call_command("community_website_audit", "--publish", str(legacy.pk), "--as", "boss", stdout=StringIO())
        self.assertIn(legacy.text, self.public())

    def test_existing_cms_testimonials_are_untouched(self):
        manual = Testimonial.objects.create(author_name="Айгуль, мама Эмира", text="Спасибо!", consent=True,
                                            status=Workflow.PUBLISHED)
        post = self.approve(self.review())
        self.admin_api.post(f"{STAFF}/posts/{post.pk}/to-website/")
        self.admin_api.post(f"{STAFF}/posts/{post.pk}/hide/", {"note": "x"})
        manual.refresh_from_db()
        self.assertEqual(manual.status, Workflow.PUBLISHED)
        self.assertEqual(set(self.public()), {"Спасибо!"})
