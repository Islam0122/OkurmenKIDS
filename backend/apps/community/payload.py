"""JSON of the community. What a student sees of another student is limited
to: first and last name, current group, photo, badges, community posts — never
contacts, birth date, branch, family, payments or grades."""
from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from apps.academy.models import Student

from . import media, scope, services
from .models import Category, Comment, CommentStatus, Post, PostStatus

ACADEMY_NAME = "Okurmen Kids"


def _abs(request, path: str) -> str:
    return request.build_absolute_uri(path) if request is not None else path


def _photo(request, student: Student) -> str | None:
    try:
        url = student.photo.url if student.photo else None
    except ValueError:
        url = None
    return _abs(request, url) if url else None


def author(post_or_comment, request) -> dict:
    student = post_or_comment.author_student
    if student is None:
        return {"type": "academy", "student_id": None, "name": ACADEMY_NAME, "group": None, "photo": None}
    group = getattr(post_or_comment, "group", None) or student.group
    return {
        "type": "student",
        "student_id": student.pk,
        "name": services.display_name(student),
        "first_name": student.first_name,
        "group": {"id": group.pk, "name": group.name} if group is not None else None,
        "photo": _photo(request, student),
    }


def images(post: Post, request) -> list[dict]:
    return [
        {"id": image.pk, "thumb": _abs(request, media.signed_url(image, "thumb")),
         "large": _abs(request, media.signed_url(image, "large")), "width": image.width, "height": image.height}
        for image in post.images.all()
    ]


def post(post: Post, request, *, student: Student | None = None, staff: bool = False) -> dict:
    mine = student is not None and post.author_student_id == student.pk
    data = {
        "id": post.pk,
        "category": post.category,
        "audience": post.audience,
        "text": post.text,
        "project_url": post.project_url,
        "status": post.status,
        "is_announcement": post.is_announcement,
        "is_pinned": post.is_pinned,
        "created_at": post.created_at,
        "published_at": post.published_at,
        "edited_at": post.edited_at,
        "author": author(post, request),
        "group": {"id": post.group_id, "name": post.group.name} if post.group_id else None,
        "images": images(post, request),
        "likes": getattr(post, "likes", None) if getattr(post, "likes", None) is not None else post.reactions.count(),
        "comments": getattr(post, "comments_total", None) if getattr(post, "comments_total", None) is not None
        else post.comments.filter(status=CommentStatus.VISIBLE).count(),
        "liked": bool(getattr(post, "liked", False)),
        "mine": mine,
        "can_edit": mine and post.status in services.EDITABLE,
        "can_delete": mine,
    }
    if mine or staff:
        data["moderation"] = {"note": post.moderation_note, "moderated_at": post.moderated_at,
                              "submitted_at": post.submitted_at}
        data["website_consent"] = post.website_consent
    if staff:
        data["moderation"]["by"] = (post.moderated_by.get_full_name() or post.moderated_by.username) \
            if post.moderated_by_id else None
        data["open_reports"] = post.reports.filter(status="open").count()
        data["website"] = ({"testimonial_id": post.website_testimonial_id,
                            "status": post.website_testimonial.status} if post.website_testimonial_id else None)
        data["author_account"] = post.author.username if post.author_id and post.is_announcement else None
    return data


def comment(row: Comment, request, *, student: Student | None = None, staff: bool = False) -> dict:
    removed = row.status != CommentStatus.VISIBLE
    data = {
        "id": row.pk,
        "parent": row.parent_id,
        "status": row.status,
        # Students never see the text of a hidden or deleted comment.
        "text": "" if removed and not staff else row.text,
        "author": author(row, request) if not (removed and not staff) else None,
        "created_at": row.created_at,
        "mine": student is not None and row.author_student_id == student.pk,
    }
    if staff:
        data["open_reports"] = row.reports.filter(status="open").count()
    return data


def comment_tree(post_obj: Post, request, *, student: Student | None = None, staff: bool = False) -> list[dict]:
    rows = list(post_obj.comments.select_related("author_student__group").order_by("created_at", "id"))
    by_parent: dict[int | None, list[Comment]] = {}
    for row in rows:
        by_parent.setdefault(row.parent_id, []).append(row)
    out = []
    for top in by_parent.get(None, []):
        replies = [r for r in by_parent.get(top.pk, []) if staff or r.status == CommentStatus.VISIBLE]
        if not staff and top.status != CommentStatus.VISIBLE and not replies:
            continue  # nothing left to show
        item = comment(top, request, student=student, staff=staff)
        item["replies"] = [comment(r, request, student=student, staff=staff) for r in replies]
        out.append(item)
    return out


def profile(viewer: Student, other: Student, request, *, today) -> dict:
    """A student's community card, as another student may see it."""
    from apps.portal.services import data as portal_data

    visible = scope.feed(viewer).filter(author_student=other)
    projects = services.annotate(visible.filter(category=Category.PROJECT), viewer).order_by("-published_at")[:12]
    badges = [b for b in portal_data.achievements(other, today=today) if b.get("code") != "scholarship"]
    return {
        "id": other.pk,
        "first_name": other.first_name,
        "last_name": other.last_name,
        "name": services.display_name(other),
        "group": {"id": other.group_id, "name": other.group.name} if other.group_id else None,
        "photo": _photo(request, other),
        "badges": badges,
        "posts_count": visible.count(),
        "likes_received": sum(p.reactions.count() for p in visible),
        "projects": [post(p, request, student=viewer) for p in projects],
        "is_me": viewer.pk == other.pk,
    }


def can_see_profile(viewer: Student, other: Student) -> bool:
    """Yourself, a classmate, or someone whose posts you can already read."""
    if viewer.pk == other.pk or (viewer.group_id and viewer.group_id == other.group_id):
        return True
    return scope.feed(viewer).filter(author_student=other).exists() or Comment.objects.filter(
        Q(author_student=other, status=CommentStatus.VISIBLE) & Q(post__in=scope.feed(viewer))).exists()


def notification(row, request) -> dict:
    return {
        "id": row.pk,
        "kind": row.kind,
        "post_id": row.post_id,
        "comment_id": row.comment_id,
        "actor": row.actor_name,
        "note": row.note,
        "is_read": row.is_read,
        "created_at": row.created_at,
        "post_excerpt": (row.post.text[:80] if row.post_id else ""),
    }


def stats(student: Student) -> dict:
    mine = Post.objects.filter(author_student=student)
    return {
        "published": mine.filter(status=PostStatus.APPROVED).count(),
        "pending": mine.filter(status=PostStatus.PENDING).count(),
        "drafts": mine.filter(status=PostStatus.DRAFT).count(),
        "rejected": mine.filter(status=PostStatus.REJECTED).count(),
        "unread": student.community_notifications.filter(is_read=False).count(),
        "can_post": scope.can_post(student),
        "today": timezone.localdate(),
    }
