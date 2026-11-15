"""Community API for the family account — /api/v1/portal/students/<id>/community/.

The child is resolved with the portal's own scope (scope.get_student → 404
for anyone else's child) and every action is done as that child. Only
approved posts of the academy / the child's group are readable; own posts in
any state are listed under «mine».
"""
from __future__ import annotations

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.academy.models import Student
from apps.portal.views import PortalView, _drf_error

from . import payload, scope, services
from .models import Category, Comment, CommentStatus, CommunityNotification, Post, PostStatus


class FeedPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 30


def _run(action):
    try:
        return action()
    except DjangoValidationError as exc:
        raise _drf_error(exc)
    except DjangoPermissionDenied as exc:
        raise PermissionDenied(str(exc) or "Недоступно.")


def _images(request):
    return request.FILES.getlist("images")


class _CommunityView(PortalView):
    def child(self, student_id) -> Student:
        return self.student(student_id)

    def paginate(self, request, qs, student):
        paginator = FeedPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator, [payload.post(p, request, student=student) for p in page]


class SummaryView(_CommunityView):
    def get(self, request, student_id):
        return Response(payload.stats(self.child(student_id)))


class FeedView(_CommunityView):
    """GET — the feed (newest first; pinned posts separately on page 1).
    POST — a new post (multipart: text, category, audience, project_url,
    website_consent, images[], submit=false to save a draft)."""

    def get(self, request, student_id):
        student = self.child(student_id)
        qs = scope.feed(student)
        category = request.query_params.get("category")
        if category in Category.values:
            qs = qs.filter(category=category)
        pinned = []
        if str(request.query_params.get("page") or "1") == "1" and not category:
            pinned = [payload.post(p, request, student=student)
                      for p in services.annotate(qs.filter(is_pinned=True), student).order_by("-pinned_at")[:3]]
            qs = qs.filter(is_pinned=False)
        paginator, rows = self.paginate(request, services.annotate(qs, student).order_by("-published_at", "-id"), student)
        response = paginator.get_paginated_response(rows)
        response.data["pinned"] = pinned
        return response

    def post(self, request, student_id):
        student = self.child(student_id)
        submit = str(request.data.get("submit", "true")).lower() != "false"
        post = _run(lambda: services.create_post(student, request.user, request.data, _images(request), submit=submit))
        return Response(payload.post(services.annotate(Post.objects.filter(pk=post.pk), student).get(), request,
                                     student=student), status=201)


class MineView(_CommunityView):
    def get(self, request, student_id):
        student = self.child(student_id)
        qs = services.annotate(Post.objects.filter(author_student=student), student)
        status = request.query_params.get("status")
        if status in PostStatus.values:
            qs = qs.filter(status=status)
        paginator, rows = self.paginate(request, qs.order_by("-updated_at", "-id"), student)
        return paginator.get_paginated_response(rows)


class PostView(_CommunityView):
    def get(self, request, student_id, post_id):
        student = self.child(student_id)
        post = scope.visible_post(student, post_id)
        post = services.annotate(Post.objects.filter(pk=post.pk), student).get()
        data = payload.post(post, request, student=student)
        data["comment_list"] = payload.comment_tree(post, request, student=student) \
            if post.status == PostStatus.APPROVED else []
        return Response(data)

    def patch(self, request, student_id, post_id):
        student = self.child(student_id)
        post = scope.own_post(student, post_id)
        submit = str(request.data.get("submit", "true")).lower() != "false"
        removed = request.data.getlist("remove_images") if hasattr(request.data, "getlist") else request.data.get("remove_images", [])
        _run(lambda: services.update_post(post, request.user, request.data, _images(request), removed, submit=submit))
        return self.get(request, student_id, post_id)

    def delete(self, request, student_id, post_id):
        student = self.child(student_id)
        services.delete_post(scope.own_post(student, post_id))
        return Response(status=204)


class LikeView(_CommunityView):
    def post(self, request, student_id, post_id):
        student = self.child(student_id)
        post = scope.visible_post(student, post_id)
        liked = str(request.data.get("liked", "true")).lower() != "false"
        liked, count = _run(lambda: services.set_like(student, post, liked))
        return Response({"liked": liked, "likes": count})


class CommentsView(_CommunityView):
    def get(self, request, student_id, post_id):
        student = self.child(student_id)
        post = scope.visible_post(student, post_id)
        if post.status != PostStatus.APPROVED:
            return Response([])
        return Response(payload.comment_tree(post, request, student=student))

    def post(self, request, student_id, post_id):
        student = self.child(student_id)
        post = scope.visible_post(student, post_id)
        comment = _run(lambda: services.add_comment(student, request.user, post, request.data.get("text"),
                                                    request.data.get("parent")))
        return Response(payload.comment(comment, request, student=student), status=201)


class CommentView(_CommunityView):
    def _comment(self, student, comment_id) -> Comment:
        comment = get_object_or_404(Comment.objects.select_related("post"), pk=comment_id)
        scope.visible_post(student, comment.post_id)  # 404 for a post the child cannot see
        return comment

    def delete(self, request, student_id, comment_id):
        student = self.child(student_id)
        _run(lambda: services.delete_comment(student, self._comment(student, comment_id)))
        return Response(status=204)


class ReportView(_CommunityView):
    def post(self, request, student_id, post_id=None, comment_id=None):
        student = self.child(student_id)
        target = {}
        if post_id is not None:
            target["post"] = scope.visible_post(student, post_id)
        else:
            comment = get_object_or_404(Comment, pk=comment_id, status=CommentStatus.VISIBLE)
            scope.visible_post(student, comment.post_id)
            target["comment"] = comment
        _run(lambda: services.report(student, reason=request.data.get("reason"), details=request.data.get("details", ""),
                                     **target))
        return Response({"ok": True}, status=201)


class ProfileView(_CommunityView):
    def get(self, request, student_id, other_id):
        student = self.child(student_id)
        other = get_object_or_404(Student.objects.select_related("group"), pk=other_id)
        if not payload.can_see_profile(student, other):
            return Response({"detail": "Не найдено."}, status=404)
        return Response(payload.profile(student, other, request, today=self.today()))


class NotificationsView(_CommunityView):
    def get(self, request, student_id):
        student = self.child(student_id)
        rows = CommunityNotification.objects.filter(recipient=student).select_related("post")[:50]
        return Response({"unread": student.community_notifications.filter(is_read=False).count(),
                         "results": [payload.notification(r, request) for r in rows]})

    def post(self, request, student_id):
        """Mark read: {"ids": [...]} or everything."""
        student = self.child(student_id)
        qs = CommunityNotification.objects.filter(recipient=student, is_read=False)
        ids = request.data.get("ids")
        if isinstance(ids, list):
            qs = qs.filter(Q(pk__in=[i for i in ids if str(i).isdigit()]))
        qs.update(is_read=True)
        return Response({"unread": student.community_notifications.filter(is_read=False).count()})
