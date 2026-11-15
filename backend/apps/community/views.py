"""Staff side of the community — /api/v1/community/.

Moderators (scope.is_moderator): admin, director, operations director, team
lead, assistant — everything; a trainer — their own groups. Family accounts
never reach this prefix (apps.portal.access). The media endpoint serves
photos only with a valid, short-lived signed link (media.signed_url).
"""
from __future__ import annotations

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academy.models import Group
from apps.portal.views import _drf_error

from . import media, payload, scope, services
from .models import Comment, Post, PostImage, PostStatus, Report, ReportStatus


class IsModerator(BasePermission):
    message = "Модерация сообщества вам недоступна."

    def has_permission(self, request, view) -> bool:
        return scope.is_moderator(request.user)


class _Staff(APIView):
    permission_classes = [IsAuthenticated, IsModerator]

    def post_for(self, post_id) -> Post:
        return get_object_or_404(scope.staff_posts(self.request.user), pk=post_id)


def _run(action):
    try:
        return action()
    except DjangoValidationError as exc:
        raise _drf_error(exc)
    except DjangoPermissionDenied as exc:
        raise PermissionDenied(str(exc) or "Недоступно.")


class _Pagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


def _post_json(request, post):
    post = services.annotate(Post.objects.filter(pk=post.pk)).get()
    return payload.post(post, request, staff=True)


class MetaView(_Staff):
    def get(self, request):
        user = request.user
        posts = scope.staff_posts(user)
        groups = scope.moderated_groups(user)
        group_qs = Group.objects.exclude(status=Group.Status.CANCELLED).order_by("name")
        if groups is not None:
            group_qs = group_qs.filter(pk__in=groups)
        reports = Report.objects.filter(status=ReportStatus.OPEN).filter(
            Q(post__in=posts) | Q(comment__post__in=posts))
        return Response({
            "pending": posts.filter(status=PostStatus.PENDING).count(),
            "open_reports": reports.count(),
            "can_announce_academy": scope.can_publish_academy_wide(user),
            "can_send_to_website": scope.can_send_to_website(user),
            "groups": [{"id": g.pk, "name": g.name} for g in group_qs],
        })


class PostsView(_Staff):
    """GET ?status=pending|approved|rejected|hidden|draft|all&category=&q="""

    def get(self, request):
        qs = scope.staff_posts(request.user)
        status = request.query_params.get("status") or PostStatus.PENDING
        # Drafts are the students' own unsent notes — never shown to staff.
        qs = qs.exclude(status=PostStatus.DRAFT)
        if status in PostStatus.values:
            qs = qs.filter(status=status)
        if request.query_params.get("category"):
            qs = qs.filter(category=request.query_params["category"])
        if request.query_params.get("q"):
            q = request.query_params["q"].strip()
            qs = qs.filter(Q(text__icontains=q) | Q(author_student__first_name__icontains=q)
                           | Q(author_student__last_name__icontains=q) | Q(group__name__icontains=q))
        order = ("submitted_at", "id") if status == PostStatus.PENDING else ("-published_at", "-created_at")
        paginator = _Pagination()
        page = paginator.paginate_queryset(services.annotate(qs).order_by(*order), request, view=self)
        return paginator.get_paginated_response([payload.post(p, request, staff=True) for p in page])


class PostView(_Staff):
    def get(self, request, post_id):
        post = self.post_for(post_id)
        if post.status == PostStatus.DRAFT:
            raise Http404
        data = _post_json(request, post)
        data["comment_list"] = payload.comment_tree(post, request, staff=True)
        data["reports"] = [
            {"id": r.pk, "reason": r.reason, "reason_display": r.get_reason_display(), "details": r.details,
             "status": r.status, "created_at": r.created_at}
            for r in post.reports.order_by("-created_at")
        ]
        return Response(data)

    def delete(self, request, post_id):
        post = self.post_for(post_id)
        if not post.is_announcement:
            return Response({"detail": "Публикацию ученика можно скрыть или отклонить, но не удалить."}, status=400)
        services.delete_post(post)
        return Response(status=204)


class ModerateView(_Staff):
    """POST posts/<id>/<action>/: approve, reject {note}, hide {note}, pin {pinned}, to-website {language}."""

    def post(self, request, post_id, action):
        post = self.post_for(post_id)
        user, data = request.user, request.data
        actions = {
            "approve": lambda: services.approve(user, post),
            "reject": lambda: services.reject(user, post, data.get("note", "")),
            "hide": lambda: services.hide(user, post, data.get("note", "")),
            "pin": lambda: services.pin(user, post, str(data.get("pinned", "true")).lower() != "false"),
            "to-website": lambda: services.send_to_website(user, post, data.get("language") or "ru"),
        }
        if action not in actions:
            raise Http404
        _run(actions[action])
        post.refresh_from_db()
        return Response(_post_json(request, post))


class AnnouncementsView(_Staff):
    def post(self, request):
        post = _run(lambda: services.announce(request.user, request.data, request.FILES.getlist("images")))
        return Response(_post_json(request, post), status=201)


class ReportsView(_Staff):
    def get(self, request):
        posts = scope.staff_posts(request.user)
        status = request.query_params.get("status") or ReportStatus.OPEN
        qs = Report.objects.filter(Q(post__in=posts) | Q(comment__post__in=posts)).select_related(
            "post", "comment__author_student", "reporter_student")
        if status in ReportStatus.values:
            qs = qs.filter(status=status)
        paginator = _Pagination()
        page = paginator.paginate_queryset(qs.order_by("-created_at"), request, view=self)
        return paginator.get_paginated_response([
            {
                "id": r.pk, "reason": r.reason, "reason_display": r.get_reason_display(), "details": r.details,
                "status": r.status, "created_at": r.created_at,
                "post_id": r.post_id or r.comment.post_id,
                "target": "post" if r.post_id else "comment",
                "comment": payload.comment(r.comment, request, staff=True) if r.comment_id else None,
                "post_excerpt": (r.post.text if r.post_id else r.comment.post.text)[:160],
                "reporter": services.display_name(r.reporter_student),
            }
            for r in page
        ])


class ReportCloseView(_Staff):
    def post(self, request, report_id):
        row = get_object_or_404(Report.objects.select_related("post", "comment__post"), pk=report_id)
        _run(lambda: services.close_report(request.user, row, request.data.get("status")))
        return Response({"ok": True})


class CommentModerationView(_Staff):
    def post(self, request, comment_id):
        comment = get_object_or_404(Comment.objects.select_related("post"), pk=comment_id)
        hidden = str(request.data.get("hidden", "true")).lower() != "false"
        comment = _run(lambda: services.set_comment_hidden(request.user, comment, hidden))
        return Response(payload.comment(comment, request, staff=True))


class MediaView(APIView):
    """A photo by its signed link. No session needed (an <img> sends none);
    the signature (6 h) is the permission. Never cached publicly, never indexed."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, token):
        parsed = media.read_token(token)
        if parsed is None:
            raise Http404
        image = PostImage.objects.filter(pk=parsed[0]).first()
        if image is None:
            raise Http404
        file = getattr(image, parsed[1])
        try:
            handle = file.storage.open(file.name, "rb")
        except FileNotFoundError:
            raise Http404
        response = FileResponse(handle, content_type="image/webp")
        response["Cache-Control"] = "private, max-age=3600"
        response["X-Robots-Tag"] = "noindex, nofollow, noarchive"
        response["X-Content-Type-Options"] = "nosniff"
        return response
