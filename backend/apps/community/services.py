"""Every change in the community goes through here (views only parse input).

Publication policy: see models.py. In short — student posts are reviewed
before anyone else sees them; edits of a published post are reviewed again;
contact details are refused; three reports hide content until a moderator
looks at it; moderators approve / reject (with feedback) / hide / pin and
publish announcements; an approved review the family allowed for the website
can be handed to the website's testimonials CMS as a draft.
"""
from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from apps.academy.models import Student

from . import media, safety, scope
from .models import (
    MAX_COMMENT,
    MAX_IMAGES,
    MAX_TEXT,
    Audience,
    Category,
    Comment,
    CommentStatus,
    CommunityNotification,
    NotificationKind,
    Post,
    PostImage,
    PostStatus,
    Reaction,
    Report,
    ReportReason,
    ReportStatus,
)

AUTO_HIDE_REPORTS = 3
EDITABLE = (PostStatus.DRAFT, PostStatus.PENDING, PostStatus.REJECTED, PostStatus.APPROVED)


# ------------------------------------------------------------------ helpers

def _truthy(value) -> bool:
    return str(value).lower() in ("1", "true", "yes", "on")


def _text(value, field: str, limit: int, *, required: bool = True) -> str:
    text = (value or "").strip()
    if required and not text:
        raise ValidationError({field: "Напишите текст."})
    if len(text) > limit:
        raise ValidationError({field: f"Не длиннее {limit} символов."})
    codes = safety.problems(text)
    if codes:
        raise ValidationError({field: safety.explain(codes)})
    return text


def _choice(value, choices, field: str, default):
    value = value or default
    if value not in choices.values:
        raise ValidationError({field: "Неверное значение."})
    return value


def _post_fields(data, *, staff: bool = False) -> dict:
    categories = Category.values if staff else [c for c in Category.values if c != Category.NEWS]
    category = data.get("category") or Category.GENERAL
    if category not in categories:
        raise ValidationError({"category": "Рубрика «Новости» — только для объявлений академии."
                               if category == Category.NEWS else "Неверная рубрика."})
    project_url = (data.get("project_url") or "").strip()
    problem = safety.project_url_problem(project_url)
    if problem:
        raise ValidationError({"project_url": problem})
    consent = _truthy(data.get("website_consent")) and category == Category.REVIEW
    return {
        "category": category,
        "audience": _choice(data.get("audience"), Audience, "audience", Audience.ACADEMY),
        "text": _text(data.get("text"), "text", MAX_TEXT),
        "project_url": project_url,
        "website_consent": consent,
    }


def _add_images(post: Post, uploads) -> None:
    uploads = list(uploads or [])
    if not uploads:
        return
    if post.images.count() + len(uploads) > MAX_IMAGES:
        raise ValidationError({"images": f"Не больше {MAX_IMAGES} фото в публикации."})
    start = post.images.count()
    for index, upload in enumerate(uploads):
        try:
            width, height, variants = media.prepare(upload)
        except ValidationError as exc:
            raise ValidationError({"images": exc.messages}) from exc
        image = PostImage(post=post, width=width, height=height, order=start + index)
        image.large.save(variants["large"].name, variants["large"], save=False)
        image.thumb.save(variants["thumb"].name, variants["thumb"], save=False)
        image.save()


def _set_state(post: Post, submit: bool) -> None:
    now = timezone.now()
    if submit:
        post.status, post.submitted_at = PostStatus.PENDING, now
        post.moderation_note = ""
    else:
        post.status = PostStatus.DRAFT


def display_name(student: Student) -> str:
    return f"{student.first_name} {student.last_name}".strip()


def notify(recipient: Student | None, kind: str, *, post=None, comment=None, actor: str = "", note: str = "",
           key: str) -> None:
    if recipient is None:
        return
    CommunityNotification.objects.get_or_create(
        dedup_key=key[:120],
        defaults={"recipient": recipient, "kind": kind, "post": post, "comment": comment,
                  "actor_name": actor[:120], "note": note[:500]},
    )


# ------------------------------------------------------------------ posts (students)

@transaction.atomic
def create_post(student: Student, user, data, uploads=(), *, submit: bool = True) -> Post:
    if not scope.can_post(student):
        raise PermissionDenied("Публиковать могут только ученики, которые сейчас учатся.")
    fields = _post_fields(data)
    if fields["audience"] == Audience.GROUP and not student.group_id:
        raise ValidationError({"audience": "У ученика нет текущей группы."})
    post = Post(author_student=student, author=user, group_id=student.group_id, **fields)
    if fields["website_consent"]:
        post.website_consent_at = timezone.now()
    _set_state(post, submit)
    post.save()
    _add_images(post, uploads)
    return post


@transaction.atomic
def update_post(post: Post, user, data, uploads=(), remove_images=(), *, submit: bool = True) -> Post:
    if post.status not in EDITABLE:
        raise PermissionDenied("Скрытую модератором публикацию изменить нельзя.")
    fields = _post_fields(data)
    was_consent = post.website_consent
    for name, value in fields.items():
        setattr(post, name, value)
    if post.website_consent and not was_consent:
        post.website_consent_at = timezone.now()
    if post.status == PostStatus.APPROVED:
        post.edited_at = timezone.now()
    # Any edit of a published post is reviewed again before others see it.
    _set_state(post, submit)
    post.is_pinned = False if post.status != PostStatus.APPROVED else post.is_pinned
    post.save()
    for image in post.images.filter(pk__in=[int(i) for i in remove_images if str(i).isdigit()]):
        image.delete()
    _add_images(post, uploads)
    return post


@transaction.atomic
def delete_post(post: Post) -> None:
    for image in list(post.images.all()):
        image.delete()
    post.delete()


# ------------------------------------------------------------------ interactions

def _interactive(student: Student, post: Post) -> None:
    if post.status != PostStatus.APPROVED or not scope.feed(student).filter(pk=post.pk).exists():
        raise PermissionDenied("Эта публикация ещё не опубликована.")


def set_like(student: Student, post: Post, liked: bool) -> tuple[bool, int]:
    _interactive(student, post)
    if liked:
        try:
            with transaction.atomic():
                Reaction.objects.create(post=post, student=student)
        except IntegrityError:
            pass
        if post.author_student_id and post.author_student_id != student.pk:
            notify(post.author_student, NotificationKind.LIKE, post=post, actor=display_name(student),
                   key=f"like:{post.pk}:{student.pk}")
    else:
        Reaction.objects.filter(post=post, student=student).delete()
    return liked, Reaction.objects.filter(post=post).count()


@transaction.atomic
def add_comment(student: Student, user, post: Post, text, parent_id=None) -> Comment:
    _interactive(student, post)
    if not scope.can_post(student):
        raise PermissionDenied("Комментировать могут только ученики, которые сейчас учатся.")
    parent = None
    if parent_id not in (None, ""):
        parent = Comment.objects.filter(pk=parent_id, post=post, status=CommentStatus.VISIBLE).first()
        if parent is None:
            raise ValidationError({"parent": "Комментарий не найден."})
        parent = parent.parent or parent  # one level of replies
    comment = Comment.objects.create(post=post, author_student=student, author=user, parent=parent,
                                     text=_text(text, "text", MAX_COMMENT))
    name = display_name(student)
    if parent is not None and parent.author_student_id != student.pk:
        notify(parent.author_student, NotificationKind.REPLY, post=post, comment=comment, actor=name,
               key=f"reply:{comment.pk}")
    if post.author_student_id and post.author_student_id != student.pk and (
            parent is None or parent.author_student_id != post.author_student_id):
        notify(post.author_student, NotificationKind.COMMENT, post=post, comment=comment, actor=name,
               key=f"comment:{comment.pk}")
    return comment


def delete_comment(student: Student, comment: Comment) -> None:
    if comment.author_student_id != student.pk:
        raise PermissionDenied("Удалить можно только свой комментарий.")
    comment.status = CommentStatus.DELETED
    comment.save(update_fields=["status"])


def report(student: Student, *, post: Post | None = None, comment: Comment | None = None, reason, details="") -> Report:
    if reason not in ReportReason.values:
        raise ValidationError({"reason": "Выберите причину."})
    target_post = post or comment.post
    _interactive(student, target_post)
    try:
        with transaction.atomic():
            row = Report.objects.create(post=post, comment=comment, reporter_student=student, reason=reason,
                                        details=(details or "").strip()[:500])
    except IntegrityError:
        raise ValidationError({"detail": "Вы уже пожаловались на это."})
    # Several children saying the same thing: hide until a moderator decides.
    target = {"post": post} if post is not None else {"comment": comment}
    open_reports = Report.objects.filter(status=ReportStatus.OPEN, **target).values("reporter_student").distinct().count()
    if open_reports >= AUTO_HIDE_REPORTS:
        if post is not None and post.status == PostStatus.APPROVED:
            post.status, post.is_pinned = PostStatus.HIDDEN, False
            post.moderation_note = "Скрыто автоматически после жалоб — до проверки модератором."
            post.save(update_fields=["status", "is_pinned", "moderation_note", "updated_at"])
        elif comment is not None and comment.status == CommentStatus.VISIBLE:
            comment.status = CommentStatus.HIDDEN
            comment.save(update_fields=["status"])
    return row


# ------------------------------------------------------------------ moderation (staff)

def _check_staff_post(user, post: Post) -> None:
    if not scope.staff_posts(user).filter(pk=post.pk).exists():
        raise PermissionDenied("Эта публикация не относится к вашим группам.")


def _moderated(post: Post, user, status: str, note: str = "") -> None:
    post.status, post.moderated_by, post.moderated_at = status, user, timezone.now()
    post.moderation_note = note[:500]
    if status == PostStatus.APPROVED and post.published_at is None:
        post.published_at = timezone.now()
    if status != PostStatus.APPROVED:
        post.is_pinned = False
    post.save()


def approve(user, post: Post) -> Post:
    _check_staff_post(user, post)
    if post.status not in (PostStatus.PENDING, PostStatus.HIDDEN, PostStatus.REJECTED):
        raise ValidationError({"detail": "Одобрить можно публикацию на проверке, скрытую или отклонённую."})
    _moderated(post, user, PostStatus.APPROVED)
    Report.objects.filter(post=post, status=ReportStatus.OPEN).update(
        status=ReportStatus.DISMISSED, resolved_by=user, resolved_at=timezone.now())
    notify(post.author_student, NotificationKind.APPROVED, post=post, key=f"approved:{post.pk}:{int(post.moderated_at.timestamp())}")
    return post


def reject(user, post: Post, note: str) -> Post:
    _check_staff_post(user, post)
    note = (note or "").strip()
    if not note:
        raise ValidationError({"note": "Напишите ученику, что исправить."})
    if post.status not in (PostStatus.PENDING, PostStatus.APPROVED, PostStatus.HIDDEN):
        raise ValidationError({"detail": "Эту публикацию отклонить нельзя."})
    _moderated(post, user, PostStatus.REJECTED, note)
    notify(post.author_student, NotificationKind.REJECTED, post=post, note=note,
           key=f"rejected:{post.pk}:{int(post.moderated_at.timestamp())}")
    return post


def hide(user, post: Post, note: str = "") -> Post:
    _check_staff_post(user, post)
    _moderated(post, user, PostStatus.HIDDEN, (note or "").strip() or "Скрыто модератором.")
    Report.objects.filter(post=post, status=ReportStatus.OPEN).update(
        status=ReportStatus.RESOLVED, resolved_by=user, resolved_at=timezone.now())
    if not post.is_announcement:
        notify(post.author_student, NotificationKind.HIDDEN, post=post, note=post.moderation_note,
               key=f"hidden:{post.pk}:{int(post.moderated_at.timestamp())}")
    return post


def pin(user, post: Post, pinned: bool) -> Post:
    _check_staff_post(user, post)
    if pinned and post.status != PostStatus.APPROVED:
        raise ValidationError({"detail": "Закрепить можно только опубликованное."})
    if pinned and post.audience == Audience.ACADEMY and not scope.can_publish_academy_wide(user):
        raise PermissionDenied("Закреплять для всей академии может администрация.")
    post.is_pinned, post.pinned_at = pinned, timezone.now() if pinned else None
    post.save(update_fields=["is_pinned", "pinned_at", "updated_at"])
    return post


@transaction.atomic
def announce(user, data, uploads=()) -> Post:
    """An official academy post: published at once (staff wrote it)."""
    group_id = data.get("group") or None
    audience = Audience.GROUP if group_id else Audience.ACADEMY
    groups = scope.moderated_groups(user)
    if audience == Audience.ACADEMY and groups is not None:
        raise PermissionDenied("Объявление для всей академии публикует администрация — выберите свою группу.")
    if group_id and groups is not None and int(group_id) not in groups:
        raise PermissionDenied("Это не ваша группа.")
    text = (data.get("text") or "").strip()
    if not text:
        raise ValidationError({"text": "Напишите текст."})
    if len(text) > MAX_TEXT:
        raise ValidationError({"text": f"Не длиннее {MAX_TEXT} символов."})
    now = timezone.now()
    post = Post.objects.create(
        author=user, group_id=group_id, audience=audience, category=_choice(data.get("category"), Category, "category",
                                                                            Category.NEWS),
        text=text, status=PostStatus.APPROVED, is_announcement=True, moderated_by=user, moderated_at=now,
        published_at=now, is_pinned=_truthy(data.get("pinned")), pinned_at=now if _truthy(data.get("pinned")) else None,
    )
    _add_images(post, uploads)
    return post


def set_comment_hidden(user, comment: Comment, hidden: bool) -> Comment:
    _check_staff_post(user, comment.post)
    if comment.status == CommentStatus.DELETED:
        raise ValidationError({"detail": "Комментарий удалён автором."})
    comment.status = CommentStatus.HIDDEN if hidden else CommentStatus.VISIBLE
    comment.moderated_by, comment.moderated_at = user, timezone.now()
    comment.save(update_fields=["status", "moderated_by", "moderated_at"])
    Report.objects.filter(comment=comment, status=ReportStatus.OPEN).update(
        status=ReportStatus.RESOLVED if hidden else ReportStatus.DISMISSED, resolved_by=user, resolved_at=timezone.now())
    return comment


def close_report(user, report_row: Report, status: str) -> Report:
    _check_staff_post(user, report_row.post or report_row.comment.post)
    if status not in (ReportStatus.RESOLVED, ReportStatus.DISMISSED):
        raise ValidationError({"status": "Неверное значение."})
    report_row.status, report_row.resolved_by, report_row.resolved_at = status, user, timezone.now()
    report_row.save(update_fields=["status", "resolved_by", "resolved_at"])
    return report_row


# ------------------------------------------------------------------ website testimonials

def send_to_website(user, post: Post, language: str = "ru"):
    """Hand an approved review to the website CMS (okurmenkids.com/testimonials)
    as a DRAFT: first name + initial, course, text — no photo, no group, no
    contacts. It appears on the site only after the CMS workflow publishes it."""
    from apps.website.models import Testimonial, Workflow

    if not scope.can_send_to_website(user):
        raise PermissionDenied("Передавать отзывы на сайт может администрация.")
    if post.category != Category.REVIEW or post.status != PostStatus.APPROVED or post.author_student_id is None:
        raise ValidationError({"detail": "На сайт можно передать только опубликованный отзыв ученика."})
    if not post.website_consent:
        raise ValidationError({"detail": "Семья не разрешила показывать этот отзыв на сайте."})
    if post.website_testimonial_id:
        return post.website_testimonial
    if language not in Testimonial.Language.values:
        language = Testimonial.Language.RU
    student = post.author_student
    initial = f" {student.last_name[:1]}." if student.last_name else ""
    course = post.group.course.name if post.group_id else ""
    testimonial = Testimonial.objects.create(
        author_name=f"{student.first_name}{initial}, ученик Okurmen Kids"[:120],
        author_role=Testimonial.Role.STUDENT, course_label=course[:120], text=post.text, language=language,
        consent=True, status=Workflow.DRAFT, created_by=user,
    )
    post.website_testimonial = testimonial
    post.save(update_fields=["website_testimonial", "updated_at"])
    return testimonial


# ------------------------------------------------------------------ queries

def annotate(qs, student: Student | None = None):
    qs = qs.select_related("author_student__group", "group__course", "author", "moderated_by").prefetch_related("images")
    qs = qs.annotate(
        likes=Count("reactions", distinct=True),
        comments_total=Count("comments", filter=Q(comments__status=CommentStatus.VISIBLE), distinct=True),
    )
    if student is not None:
        qs = qs.annotate(liked=Exists(Reaction.objects.filter(post=OuterRef("pk"), student=student)))
    return qs
