"""«Сообщество» — the private community of the Student & Parent Portal.

Publication policy (students are minors):

* Nothing a student writes is visible to others before a moderator (trainer
  of the student's group, assistant, team lead, admin) approves it:
  DRAFT → PENDING → APPROVED, or REJECTED with feedback. Editing an approved
  post sends it back to PENDING.
* Moderators can HIDE any post or comment at any time; three reports from
  different students hide a post or comment automatically until reviewed.
* Texts are checked for contact details (phones, e-mail, messengers, social
  handles, links); a link is allowed only as the project link, to a known
  site for student projects.
* Photos are stored outside the public /media/, re-encoded without metadata
  (no camera GPS), and served only by short-lived signed links. The
  community is never indexed and has no public pages.
* The only way out to the public website is a moderator handing an approved
  REVIEW, which the family explicitly allowed for the website, to the
  website's testimonials CMS as a draft — name and initial only, no photo;
  publishing it there is the CMS's own workflow (consent required).
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.academy.models import Group, Student

from .media import community_storage, image_path

USER = settings.AUTH_USER_MODEL

MAX_TEXT = 3000
MAX_COMMENT = 1000
MAX_IMAGES = 6


class Category(models.TextChoices):
    GENERAL = "general", "Общее"
    REVIEW = "review", "Отзыв"
    ACHIEVEMENT = "achievement", "Достижение"
    PROJECT = "project", "Проект"
    LEARNING_PROGRESS = "learning_progress", "Прогресс в учёбе"
    NEWS = "news", "Новости"


class Audience(models.TextChoices):
    ACADEMY = "academy", "Вся академия"
    GROUP = "group", "Только группа"


class PostStatus(models.TextChoices):
    DRAFT = "draft", "Черновик"
    PENDING = "pending", "На проверке"
    APPROVED = "approved", "Опубликовано"
    REJECTED = "rejected", "Отклонено"
    HIDDEN = "hidden", "Скрыто"


class Post(models.Model):
    # A student's post: author_student is one of the account's children.
    # An official announcement: author_student is empty, author is staff.
    author_student = models.ForeignKey(Student, on_delete=models.CASCADE, null=True, blank=True,
                                       related_name="community_posts", verbose_name="Ученик")
    author = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name="community_posts",
                               verbose_name="Аккаунт автора")
    # The author's group when posting (a student may change groups later).
    group = models.ForeignKey(Group, on_delete=models.SET_NULL, null=True, blank=True, related_name="community_posts",
                              verbose_name="Группа")
    audience = models.CharField(max_length=10, choices=Audience.choices, default=Audience.ACADEMY, verbose_name="Кто видит")
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.GENERAL, db_index=True,
                                verbose_name="Рубрика")
    text = models.TextField(max_length=MAX_TEXT, verbose_name="Текст")
    project_url = models.URLField(max_length=300, blank=True, verbose_name="Ссылка на проект")
    status = models.CharField(max_length=10, choices=PostStatus.choices, default=PostStatus.PENDING, db_index=True,
                              verbose_name="Статус")
    is_announcement = models.BooleanField(default=False, verbose_name="Объявление академии")
    is_pinned = models.BooleanField(default=False, db_index=True, verbose_name="Закреплено")
    pinned_at = models.DateTimeField(null=True, blank=True)
    moderation_note = models.CharField(max_length=500, blank=True, verbose_name="Комментарий модератора")
    moderated_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                     verbose_name="Модератор")
    moderated_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name="Отправлено на проверку")
    published_at = models.DateTimeField(null=True, blank=True, db_index=True, verbose_name="Опубликовано")
    edited_at = models.DateTimeField(null=True, blank=True)
    # Website testimonials: only an explicit «yes» from the family, only for reviews.
    website_consent = models.BooleanField(default=False, verbose_name="Семья разрешила показать на сайте")
    website_consent_at = models.DateTimeField(null=True, blank=True)
    website_testimonial = models.OneToOneField("website.Testimonial", on_delete=models.SET_NULL, null=True, blank=True,
                                               related_name="community_post", verbose_name="Отзыв на сайте")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Публикация"
        verbose_name_plural = "Публикации"
        ordering = ["-published_at", "-created_at", "-id"]
        indexes = [models.Index(fields=["status", "-published_at"], name="community_post_feed")]

    def __str__(self):
        return f"#{self.pk} {self.get_category_display()} — {self.get_status_display()}"


def _image_field(**kwargs):
    return models.ImageField(upload_to=image_path, storage=community_storage, max_length=255, **kwargs)


class PostImage(models.Model):
    """Re-encoded copies only (WebP, no metadata); the uploaded original is never kept."""

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="images")
    large = _image_field()
    thumb = _image_field()
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Фото публикации"
        verbose_name_plural = "Фото публикаций"
        ordering = ["order", "id"]

    def delete(self, *args, **kwargs):
        files = (self.large, self.thumb)
        result = super().delete(*args, **kwargs)
        for file in files:
            if file:
                file.storage.delete(file.name)
        return result


class CommentStatus(models.TextChoices):
    VISIBLE = "visible", "Виден"
    HIDDEN = "hidden", "Скрыт модератором"
    DELETED = "deleted", "Удалён автором"


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author_student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="community_comments")
    author = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    # A reply to a top-level comment (one level of replies).
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies")
    text = models.TextField(max_length=MAX_COMMENT)
    status = models.CharField(max_length=10, choices=CommentStatus.choices, default=CommentStatus.VISIBLE, db_index=True)
    moderated_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    moderated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Комментарий"
        verbose_name_plural = "Комментарии"
        ordering = ["created_at", "id"]


class Reaction(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="reactions")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="community_reactions")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Лайк"
        verbose_name_plural = "Лайки"
        constraints = [models.UniqueConstraint(fields=["post", "student"], name="unique_community_like")]


class ReportReason(models.TextChoices):
    PERSONAL_INFO = "personal_info", "Личные данные или контакты"
    BULLYING = "bullying", "Оскорбления или травля"
    INAPPROPRIATE = "inappropriate", "Неприемлемый контент"
    SPAM = "spam", "Спам или реклама"
    OTHER = "other", "Другое"


class ReportStatus(models.TextChoices):
    OPEN = "open", "Открыта"
    RESOLVED = "resolved", "Приняты меры"
    DISMISSED = "dismissed", "Отклонена"


class Report(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True, related_name="reports")
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, null=True, blank=True, related_name="reports")
    reporter_student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="community_reports")
    reason = models.CharField(max_length=20, choices=ReportReason.choices)
    details = models.CharField(max_length=500, blank=True)
    status = models.CharField(max_length=10, choices=ReportStatus.choices, default=ReportStatus.OPEN, db_index=True)
    resolved_by = models.ForeignKey(USER, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Жалоба"
        verbose_name_plural = "Жалобы"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(post__isnull=False) ^ models.Q(comment__isnull=False),
                                   name="community_report_one_target"),
            models.UniqueConstraint(fields=["post", "reporter_student"], condition=models.Q(post__isnull=False),
                                    name="unique_post_report"),
            models.UniqueConstraint(fields=["comment", "reporter_student"], condition=models.Q(comment__isnull=False),
                                    name="unique_comment_report"),
        ]


class NotificationKind(models.TextChoices):
    COMMENT = "comment", "Новый комментарий"
    REPLY = "reply", "Ответ на комментарий"
    LIKE = "like", "Лайк"
    APPROVED = "approved", "Публикация одобрена"
    REJECTED = "rejected", "Публикация отклонена"
    HIDDEN = "hidden", "Публикация скрыта"


class CommunityNotification(models.Model):
    """Stored events for one student (shown in the portal, ru / ky by code)."""

    recipient = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="community_notifications")
    kind = models.CharField(max_length=10, choices=NotificationKind.choices)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    actor_name = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=500, blank=True)
    dedup_key = models.CharField(max_length=120, unique=True)
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Уведомление сообщества"
        verbose_name_plural = "Уведомления сообщества"
        ordering = ["-created_at", "-id"]
