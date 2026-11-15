"""«Сообщество»: pre-moderation, visibility, contact filter, comments and
replies, likes, reports and auto-hide, moderator scope, private photos,
announcements, notifications, and the website hand-off of reviews."""
from __future__ import annotations

import io

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


class WebsiteTests(CommunityBase):
    def review(self, consent: bool):
        return self.approve(self.publish(category="review", text="Мне очень нравится учиться в Okurmen Kids!",
                                         website_consent="true" if consent else "false"))

    def test_review_with_family_consent_goes_to_the_cms_as_a_draft(self):
        post = self.review(True)
        response = self.admin_api.post(f"{STAFF}/posts/{post.pk}/to-website/", {"language": "ru"})
        self.assertEqual(response.status_code, 200, response.data)
        t = Testimonial.objects.get()
        self.assertEqual((t.author_name, t.author_role, t.status, t.consent, bool(t.photo)),
                         ("Айбек А., ученик Okurmen Kids", "student", Workflow.DRAFT, True, False))
        self.assertEqual(t.text, post.text)
        self.assertEqual(Testimonial.objects.public().count(), 0)   # not on the site until the CMS publishes it
        # Idempotent.
        self.admin_api.post(f"{STAFF}/posts/{post.pk}/to-website/")
        self.assertEqual(Testimonial.objects.count(), 1)

    def test_without_consent_or_by_a_trainer_nothing_goes_out(self):
        post = self.review(False)
        self.assertEqual(self.admin_api.post(f"{STAFF}/posts/{post.pk}/to-website/").status_code, 400)
        consented = self.review(True)
        self.assertEqual(self.teacher_api.post(f"{STAFF}/posts/{consented.pk}/to-website/").status_code, 403)
        self.assertFalse(Testimonial.objects.exists())

    def test_consent_only_for_reviews(self):
        post = self.publish(category="general", website_consent="true")
        self.assertFalse(post.website_consent)
