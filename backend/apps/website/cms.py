"""Marketing CMS API — /api/v1/marketing/site/ (inside the existing LMS).

The marketing team manages the public website from its LMS cabinet
(/marketing/site in the frontend). Marketing accounts never use the Django
admin (User.LMS_ONLY_ROLES), and the role isolation middleware already lets
them into /api/v1/marketing/ — rights are checked here:

* site content (courses, events, achievements, news, team, testimonials,
  homepage, banners, stats, branches, media) — marketing, director, admin;
* publishing — the same people, unless `WEBSITE_REQUIRE_APPROVAL=true`: then
  marketing moves content to «На согласовании» and only a director or an
  admin publishes it;
* leads and event registrations (personal data) — marketing, sales
  (sales manager, РОП, ДОП), director, admin;
* trainers cannot reach any of it; student projects stay in the trainers'
  LMS (apps.projects) and are only *selected* for the homepage here.
"""
from __future__ import annotations

import ipaddress
import posixpath
import socket
import urllib.request
from urllib.parse import urlparse

from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, parsers, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academy_news.images import validate_image
from apps.academy_news.models import Article, ArticlePhoto
from apps.projects.models import StudentProject
from apps.users.models import User
from apps.users.permissions import is_admin_user

from . import models as m
from . import public

TAGS = ["Marketing — website CMS"]
MAX_BULK_PHOTOS = 40


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

def _role(user) -> str | None:
    return getattr(user, "role", None) if getattr(user, "is_authenticated", False) and user.is_active else None


def can_edit_site(user) -> bool:
    return is_admin_user(user) or _role(user) in (User.Role.MARKETING, User.Role.DIRECTOR)


def can_approve(user) -> bool:
    return is_admin_user(user) or _role(user) == User.Role.DIRECTOR


def can_manage_leads(user) -> bool:
    return can_edit_site(user) or _role(user) in (User.Role.SALES_MANAGER, User.Role.ROP, User.Role.DOP)


def require_approval() -> bool:
    return getattr(settings, "WEBSITE_REQUIRE_APPROVAL", False)


class IsSiteEditor(BasePermission):
    message = "Управление сайтом доступно маркетингу, директору и администратору."

    def has_permission(self, request, view) -> bool:
        return can_edit_site(request.user)


class IsLeadManager(BasePermission):
    message = "Заявки доступны маркетингу, отделу продаж, директору и администратору."

    def has_permission(self, request, view) -> bool:
        return can_manage_leads(request.user)


class CMSPagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 200


def preview_url(kind: str, pk: int) -> dict:
    token = public.preview_token(kind, pk)
    base = getattr(settings, "PUBLIC_WEBSITE_URL", "").rstrip("/")
    return {"token": token, "url": f"{base}/preview/{token}" if base else None}


def public_url(path: str) -> str | None:
    base = getattr(settings, "PUBLIC_WEBSITE_URL", "").rstrip("/")
    return f"{base}{path}" if base else None


def _file_url(field_file) -> str | None:
    try:
        return field_file.url if field_file else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

IMAGE_DOWNLOAD_MAX = 15 * 1024 * 1024
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # a redirect could lead into the internal network
        raise ValidationError("Ссылка перенаправляет на другой адрес — укажите прямую ссылку на изображение.")


def _asset_copy(asset) -> ContentFile:
    with asset.file.open("rb") as handle:
        return ContentFile(handle.read(), name=posixpath.basename(asset.file.name))


def _download_image(url: str) -> ContentFile:
    """A picture from a direct public link (https://…/photo.jpg). Only public
    addresses, no redirects, image types only, at most 15 MB."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValidationError("Нужна ссылка вида https://…")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except OSError:
        raise ValidationError("Адрес не найден.")
    if not infos or any(not ipaddress.ip_address(info[4][0]).is_global for info in infos):
        raise ValidationError("Ссылка недоступна.")
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, headers={"User-Agent": "OkurmenKids-CMS/1.0", "Accept": "image/*"})
    try:
        with opener.open(request, timeout=10) as response:
            content_type = response.headers.get_content_type()
            if content_type not in IMAGE_TYPES:
                raise ValidationError("По ссылке не изображение JPEG, PNG или WebP.")
            data = response.read(IMAGE_DOWNLOAD_MAX + 1)
    except ValidationError:
        raise
    except Exception:  # noqa: BLE001 — network errors, HTTP errors, timeouts
        raise ValidationError("Не удалось загрузить изображение по ссылке.")
    if len(data) > IMAGE_DOWNLOAD_MAX:
        raise ValidationError("Изображение больше 15 МБ.")
    name = posixpath.basename(parsed.path) or "image"
    if not name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        name += IMAGE_TYPES[content_type]
    return ContentFile(data, name=name[:100])


def image_from_reference(value: str) -> ContentFile:
    """`media:<id>` — a picture from the media library; an http(s) link — the
    library file with that address, or a download from a direct public link."""
    value = value.strip()
    if value.startswith("media:"):
        pk = value[len("media:"):]
        asset = m.MediaAsset.objects.filter(pk=int(pk) if pk.isdigit() else 0, kind=m.MediaAsset.Kind.IMAGE).first()
        if asset is None:
            raise ValidationError("Изображение медиатеки не найдено.")
        return _asset_copy(asset)
    if value.startswith(("http://", "https://")):
        path = urlparse(value).path
        for asset in m.MediaAsset.objects.filter(kind=m.MediaAsset.Kind.IMAGE, file__endswith=posixpath.basename(path)):
            if path.endswith("/" + asset.file.name) or path == asset.file.name:
                return _asset_copy(asset)
        return _download_image(value)
    raise ValidationError("Выберите файл, изображение из медиатеки или прямую ссылку.")


class ImageField(serializers.ImageField):
    """Upload: a file (multipart), `media:<id>` (from the media library) or a
    direct link. Clear: an empty string. Read: the URL."""

    def to_representation(self, value):
        return _file_url(value)

    def to_internal_value(self, data):
        if data in ("", None):
            return None
        if isinstance(data, str):
            data = image_from_reference(data)
        value = super().to_internal_value(data)
        validate_image(value)
        return value


class WorkflowSerializer(serializers.ModelSerializer):
    workflow_state = serializers.CharField(read_only=True)
    created_by_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()
    preview = serializers.SerializerMethodField()
    public_url = serializers.SerializerMethodField()

    preview_kind: str | None = None
    public_prefix: str | None = None

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by_id else None

    def get_reviewed_by_name(self, obj):
        return obj.reviewed_by.get_full_name() if obj.reviewed_by_id else None

    def get_preview(self, obj):
        return preview_url(self.preview_kind, obj.pk) if self.preview_kind and obj.pk else None

    def get_public_url(self, obj):
        if self.public_prefix and obj.is_public:
            return public_url(f"{self.public_prefix}/{obj.slug}")
        return None

    def validate_status(self, value):
        request = self.context.get("request")
        user = request.user if request else None
        current = getattr(self.instance, "status", m.Workflow.DRAFT)
        if value == m.Workflow.PUBLISHED and current != m.Workflow.PUBLISHED and require_approval() and not can_approve(user):
            raise ValidationError("Публикует директор или администратор: отправьте материал на согласование.")
        return value

    def save(self, **kwargs):
        request = self.context["request"]
        if self.instance is None:
            kwargs.setdefault("created_by", request.user)
        if self.validated_data.get("status") == m.Workflow.PUBLISHED and (
                self.instance is None or self.instance.status != m.Workflow.PUBLISHED):
            kwargs["reviewed_by"] = request.user
        return super().save(**kwargs)

    def validate(self, attrs):
        return clean_copy(self, super().validate(attrs))


def clean_copy(serializer, attrs):
    """Run the model's clean() on an unsaved copy with the new values, so the
    same rules apply in the API as in the Django admin."""
    from django.core.exceptions import ValidationError as DjangoValidationError

    model = serializer.Meta.model
    target = model()
    if serializer.instance is not None:
        for field in model._meta.concrete_fields:
            setattr(target, field.attname, getattr(serializer.instance, field.attname))
    concrete = {f.name for f in model._meta.concrete_fields}
    for key, value in attrs.items():
        if key in concrete:
            setattr(target, key, value)
    try:
        target.clean()
    except DjangoValidationError as exc:
        raise ValidationError(exc.message_dict if hasattr(exc, "error_dict") else {"non_field_errors": exc.messages})
    return attrs


def photo_payload(photo) -> dict:
    return {
        "id": photo.pk,
        "url": _file_url(photo.large) or _file_url(photo.image),
        "thumb": _file_url(photo.thumb) or _file_url(photo.image),
        "caption": photo.caption,
        "order": photo.order,
    }


EXCLUDE_IMAGE_COPIES = ("cover_large", "cover_thumb", "cover_width", "cover_height")


class CoursePageSerializer(WorkflowSerializer):
    preview_kind = "course"
    public_prefix = "/courses"
    cover = ImageField(required=False, allow_null=True)
    course_name = serializers.CharField(source="course.name", read_only=True, default=None)
    lessons = serializers.IntegerField(source="course.count_lesson", read_only=True, default=None)

    class Meta:
        model = m.CoursePage
        exclude = EXCLUDE_IMAGE_COPIES
        read_only_fields = ("created_by", "reviewed_by")


class EventSerializer(WorkflowSerializer):
    preview_kind = "event"
    public_prefix = "/events"
    cover = ImageField(required=False, allow_null=True)
    photos = serializers.SerializerMethodField()
    registrations_count = serializers.IntegerField(read_only=True, default=0)
    phase = serializers.SerializerMethodField()
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)

    class Meta:
        model = m.Event
        exclude = EXCLUDE_IMAGE_COPIES
        read_only_fields = ("created_by", "reviewed_by")

    def get_photos(self, obj):
        return [photo_payload(p) for p in obj.photos.all()]

    def get_phase(self, obj):
        return obj.phase()


class AchievementSerializer(WorkflowSerializer):
    preview_kind = "achievement"
    public_prefix = "/achievements"
    cover = ImageField(required=False, allow_null=True)
    photos = serializers.SerializerMethodField()

    class Meta:
        model = m.Achievement
        exclude = EXCLUDE_IMAGE_COPIES
        read_only_fields = ("created_by", "reviewed_by")

    def get_photos(self, obj):
        return [photo_payload(p) for p in obj.photos.all()]


class TeamMemberSerializer(WorkflowSerializer):
    photo = ImageField(required=False, allow_null=True)
    display_name = serializers.CharField(read_only=True)
    teacher_name = serializers.SerializerMethodField()
    teacher_photo = serializers.SerializerMethodField()

    class Meta:
        model = m.TeamMember
        fields = "__all__"
        read_only_fields = ("created_by", "reviewed_by")

    def get_teacher_name(self, obj):
        return obj.teacher.user.get_full_name() if obj.teacher_id else None

    def get_teacher_photo(self, obj):
        return _file_url(obj.teacher.image) if obj.teacher_id else None


class TestimonialSerializer(WorkflowSerializer):
    photo = ImageField(required=False, allow_null=True)

    class Meta:
        model = m.Testimonial
        fields = "__all__"
        read_only_fields = ("created_by", "reviewed_by")


class NewsSerializer(serializers.ModelSerializer):
    """The existing public news (apps.academy_news) — draft / published."""

    cover = ImageField(required=False, allow_null=True)
    photos = serializers.SerializerMethodField()
    workflow_state = serializers.SerializerMethodField()
    preview = serializers.SerializerMethodField()
    public_url = serializers.SerializerMethodField()
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = Article
        exclude = ("cover_large", "cover_thumb", "cover_width", "cover_height")
        read_only_fields = ("author",)

    def get_photos(self, obj):
        return [photo_payload(p) for p in obj.photos.all()]

    def get_workflow_state(self, obj):
        if obj.status == Article.Status.PUBLISHED and obj.published_at > timezone.now():
            return "scheduled"
        return obj.status

    def get_preview(self, obj):
        return preview_url("news", obj.pk) if obj.pk else None

    def get_public_url(self, obj):
        return public_url(f"/news/{obj.slug}") if obj.pk and obj.is_public else None

    def get_author_name(self, obj):
        return obj.author.get_full_name() if obj.author_id else None

    def validate_status(self, value):
        user = self.context["request"].user
        current = getattr(self.instance, "status", Article.Status.DRAFT)
        if value == Article.Status.PUBLISHED and current != value and require_approval() and not can_approve(user):
            raise ValidationError("Публикует директор или администратор.")
        return value


class SettingsSerializer(serializers.ModelSerializer):
    hero_image = ImageField(required=False, allow_null=True)
    og_image = ImageField(required=False, allow_null=True)
    featured_projects = serializers.PrimaryKeyRelatedField(
        many=True, required=False,
        queryset=StudentProject.objects.all())
    featured_news = serializers.PrimaryKeyRelatedField(many=True, required=False, queryset=Article.objects.all())

    class Meta:
        model = m.SiteSettings
        exclude = ("id",)


class HomeSectionSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_key_display", read_only=True)

    class Meta:
        model = m.HomeSection
        fields = "__all__"
        read_only_fields = ("key",)


class StatisticSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Statistic
        fields = "__all__"


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = m.Branch
        fields = "__all__"


class BannerSerializer(serializers.ModelSerializer):
    image = ImageField(required=False, allow_null=True)

    class Meta:
        model = m.PromoBanner
        fields = "__all__"

    def validate(self, attrs):
        starts = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if starts and ends and ends < starts:
            raise ValidationError({"ends_at": "Окончание раньше начала."})
        return attrs


class MediaCategorySerializer(serializers.ModelSerializer):
    count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = m.MediaCategory
        fields = "__all__"


class MediaAssetSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    uploaded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = m.MediaAsset
        fields = "__all__"
        read_only_fields = ("kind", "size", "uploaded_by")
        extra_kwargs = {"file": {"write_only": True, "required": False}, "title": {"required": False}}

    def get_url(self, obj):
        url = _file_url(obj.file)
        request = self.context.get("request")
        return request.build_absolute_uri(url) if url and request and url.startswith("/") else url

    def get_uploaded_by_name(self, obj):
        return obj.uploaded_by.get_full_name() if obj.uploaded_by_id else None

    def validate(self, attrs):
        if self.instance is None and not attrs.get("file"):
            raise ValidationError({"file": "Выберите файл."})
        if not attrs.get("title") and attrs.get("file"):
            attrs["title"] = attrs["file"].name.rsplit(".", 1)[0][:200]
        return attrs


def lead_staff():
    """Who can be responsible for a lead: active marketing, sales, director, admin accounts."""
    roles = (User.Role.MARKETING, User.Role.SALES_MANAGER, User.Role.ROP, User.Role.DOP, User.Role.DIRECTOR,
             User.Role.ADMIN)
    return User.objects.filter(is_active=True, role__in=roles).order_by("first_name", "last_name")


class LeadSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source="course.title", read_only=True, default=None)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    assigned_to_name = serializers.SerializerMethodField()
    assigned_to = serializers.PrimaryKeyRelatedField(queryset=User.objects.none(), allow_null=True, required=False)
    status_history = serializers.JSONField(read_only=True)

    class Meta:
        model = m.Lead
        fields = "__all__"
        read_only_fields = [f.name for f in m.Lead._meta.fields
                            if f.name not in ("status", "note", "assigned_to", "child_name")]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = lead_staff()

    def get_assigned_to_name(self, obj):
        return obj.assigned_to.get_full_name() if obj.assigned_to_id else None

    def update(self, instance, validated_data):
        request = self.context.get("request")
        new_status = validated_data.get("status")
        if new_status and new_status != instance.status:
            by = request.user.get_full_name() if request and request.user.is_authenticated else ""
            history = list(instance.status_history or [])
            history.append({"at": timezone.now().isoformat(), "from": instance.status, "to": new_status, "by": by})
            instance.status_history = history[-100:]
        return super().update(instance, validated_data)


class RegistrationSerializer(serializers.ModelSerializer):
    event_title = serializers.CharField(source="event.title", read_only=True)

    class Meta:
        model = m.EventRegistration
        exclude = ("phone_digits",)
        read_only_fields = ("event", "parent_name", "phone", "child_name", "child_age", "comment", "created_at")


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

PARSERS = [parsers.JSONParser, parsers.MultiPartParser, parsers.FormParser]


class SiteViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsSiteEditor]
    pagination_class = CMSPagination
    parser_classes = PARSERS
    search_fields: tuple = ("title",)
    ordering_fields = "__all__"
    filterset_fields: tuple = ()


class WorkflowViewSet(SiteViewSet):
    """CRUD + `status` filter (`scheduled` too) + publish / archive / review actions."""

    def get_queryset(self):
        qs = super().get_queryset()
        state = self.request.query_params.get("status", "")
        now = timezone.now()
        if state == "scheduled":
            qs = qs.filter(status=m.Workflow.PUBLISHED, published_at__gt=now)
        elif state == "published":
            qs = qs.filter(status=m.Workflow.PUBLISHED, published_at__lte=now)
        elif state in m.Workflow.values:
            qs = qs.filter(status=state)
        return qs

    def _transition(self, request, target: str):
        obj = self.get_object()
        if target == m.Workflow.PUBLISHED and require_approval() and not can_approve(request.user):
            raise PermissionDenied("Публикует директор или администратор.")
        obj.status = target
        if target == m.Workflow.PUBLISHED:
            obj.reviewed_by = request.user
            when = request.data.get("published_at") if hasattr(request, "data") else None
            if when:
                parsed = serializers.DateTimeField().to_internal_value(when)
                obj.published_at = parsed
            elif obj.published_at > timezone.now() and not request.data.get("keep_schedule"):
                obj.published_at = timezone.now()
        if target == m.Workflow.PUBLISHED and isinstance(obj, m.Testimonial) and not obj.consent:
            raise ValidationError({"consent": "Отзыв публикуется только с согласия автора."})
        obj.save()
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        return self._transition(request, m.Workflow.PUBLISHED)

    @action(detail=True, methods=["post"])
    def submit_review(self, request, pk=None):
        return self._transition(request, m.Workflow.REVIEW)

    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        return self._transition(request, m.Workflow.DRAFT)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        return self._transition(request, m.Workflow.ARCHIVED)


class PhotosMixin:
    """`POST {id}/photos/` (multipart `files`, several at once),
    `PATCH {id}/photos/{photo_id}/` (caption, order), `DELETE` the same."""

    photo_model = None
    photo_fk = ""

    @action(detail=True, methods=["post"], url_path="photos", parser_classes=[parsers.MultiPartParser, parsers.JSONParser])
    def add_photos(self, request, pk=None):
        """Files (multipart `files`) and / or pictures from the media library
        (`media`: a list of asset ids)."""
        obj = self.get_object()
        files = list(request.FILES.getlist("files"))
        media_ids = request.data.getlist("media") if hasattr(request.data, "getlist") else request.data.get("media", [])
        if media_ids:
            if not isinstance(media_ids, list):
                raise ValidationError({"media": "Нужен список изображений."})
            ids = [int(x) for x in media_ids if str(x).isdigit()]
            assets = {a.pk: a for a in m.MediaAsset.objects.filter(pk__in=ids, kind=m.MediaAsset.Kind.IMAGE)}
            files += [_asset_copy(assets[i]) for i in ids if i in assets]
        if not files:
            raise ValidationError({"files": "Выберите фотографии."})
        if len(files) > MAX_BULK_PHOTOS:
            raise ValidationError({"files": f"За один раз — не больше {MAX_BULK_PHOTOS} фотографий."})
        for upload in files:
            try:
                validate_image(upload)
            except Exception as exc:  # noqa: BLE001
                raise ValidationError({"files": f"{upload.name}: {getattr(exc, 'message', exc)}"})
        start = (max((p.order for p in obj.photos.all()), default=-1) + 1)
        for offset, upload in enumerate(files):
            self.photo_model.objects.create(**{self.photo_fk: obj}, image=upload, order=start + offset)
        obj.save(update_fields=["updated_at"])
        return Response(self.get_serializer(self.get_object()).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path=r"photos/(?P<photo_id>\d+)")
    def photo(self, request, pk=None, photo_id=None):
        obj = self.get_object()
        photo = obj.photos.filter(pk=photo_id).first()
        if photo is None:
            return Response({"detail": "Фото не найдено."}, status=status.HTTP_404_NOT_FOUND)
        if request.method == "DELETE":
            photo.delete()
        else:
            if "caption" in request.data:
                photo.caption = str(request.data["caption"])[:200]
            if "order" in request.data:
                try:
                    photo.order = max(0, int(request.data["order"]))
                except (TypeError, ValueError):
                    raise ValidationError({"order": "Ожидается число."})
            photo.save(update_fields=["caption", "order"])
        obj.save(update_fields=["updated_at"])
        return Response(self.get_serializer(self.get_object()).data)


@extend_schema(tags=TAGS)
class CoursePageViewSet(WorkflowViewSet):
    queryset = m.CoursePage.objects.select_related("course", "created_by", "reviewed_by")
    serializer_class = CoursePageSerializer
    search_fields = ("title", "tagline", "body")


@extend_schema(tags=TAGS)
class EventViewSet(PhotosMixin, WorkflowViewSet):
    queryset = (m.Event.objects.select_related("branch", "created_by", "reviewed_by").prefetch_related("photos")
                .annotate(registrations_count=Count("registrations")).order_by("-starts_at", "-id"))
    serializer_class = EventSerializer
    photo_model = m.EventPhoto
    photo_fk = "event"
    search_fields = ("title", "excerpt", "location")
    filterset_fields = ("category", "registration_enabled")


@extend_schema(tags=TAGS)
class AchievementViewSet(PhotosMixin, WorkflowViewSet):
    queryset = m.Achievement.objects.select_related("created_by", "reviewed_by").prefetch_related("photos")
    serializer_class = AchievementSerializer
    photo_model = m.AchievementPhoto
    photo_fk = "achievement"
    search_fields = ("title", "excerpt", "body")
    filterset_fields = ("category",)


@extend_schema(tags=TAGS)
class TeamMemberViewSet(WorkflowViewSet):
    queryset = m.TeamMember.objects.select_related("teacher__user", "created_by", "reviewed_by")
    serializer_class = TeamMemberSerializer
    search_fields = ("name", "position", "specialization", "teacher__user__first_name", "teacher__user__last_name")
    filterset_fields = ("group",)


@extend_schema(tags=TAGS)
class TestimonialViewSet(WorkflowViewSet):
    queryset = m.Testimonial.objects.select_related("created_by", "reviewed_by")
    serializer_class = TestimonialSerializer
    search_fields = ("author_name", "text", "course_label")
    filterset_fields = ("author_role", "is_featured")


@extend_schema(tags=TAGS)
class NewsViewSet(PhotosMixin, SiteViewSet):
    """The existing public news (apps.academy_news), for marketing — same
    rules as the Django admin: draft → published (now or on a date)."""

    queryset = Article.objects.select_related("author").prefetch_related("photos")
    serializer_class = NewsSerializer
    photo_model = ArticlePhoto
    photo_fk = "article"
    search_fields = ("title", "excerpt", "body")
    filterset_fields = ("category", "is_featured")

    def get_queryset(self):
        qs = super().get_queryset()
        state = self.request.query_params.get("status", "")
        now = timezone.now()
        if state == "scheduled":
            qs = qs.filter(status=Article.Status.PUBLISHED, published_at__gt=now)
        elif state == "published":
            qs = qs.filter(status=Article.Status.PUBLISHED, published_at__lte=now)
        elif state == "draft":
            qs = qs.filter(status=Article.Status.DRAFT)
        return qs

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        obj = self.get_object()
        if require_approval() and not can_approve(request.user):
            raise PermissionDenied("Публикует директор или администратор.")
        obj.status = Article.Status.PUBLISHED
        if obj.published_at > timezone.now() and not request.data.get("keep_schedule"):
            obj.published_at = timezone.now()
        obj.save()
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        obj = self.get_object()
        obj.status = Article.Status.DRAFT
        obj.save()
        return Response(self.get_serializer(obj).data)


@extend_schema(tags=TAGS)
class StatisticViewSet(SiteViewSet):
    queryset = m.Statistic.objects.all()
    serializer_class = StatisticSerializer
    search_fields = ("label", "value")
    pagination_class = None


@extend_schema(tags=TAGS)
class BranchViewSet(SiteViewSet):
    queryset = m.Branch.objects.all()
    serializer_class = BranchSerializer
    search_fields = ("name", "address")
    pagination_class = None


@extend_schema(tags=TAGS)
class BannerViewSet(SiteViewSet):
    queryset = m.PromoBanner.objects.all()
    serializer_class = BannerSerializer
    search_fields = ("title", "text")
    pagination_class = None


@extend_schema(tags=TAGS)
class HomeSectionViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """All homepage blocks (missing ones are created on first read)."""

    permission_classes = [IsAuthenticated, IsSiteEditor]
    serializer_class = HomeSectionSerializer
    pagination_class = None

    def get_queryset(self):
        existing = set(m.HomeSection.objects.values_list("key", flat=True))
        for index, key in enumerate(public.DEFAULT_SECTIONS):
            if key not in existing:
                m.HomeSection.objects.create(key=key, order=index)
        return m.HomeSection.objects.all()

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        """`{"keys": ["stats", "courses", …]}` — the new order."""
        keys = request.data.get("keys")
        if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
            raise ValidationError({"keys": "Нужен список блоков."})
        current = list(self.get_queryset())
        listed = [key for key in dict.fromkeys(keys) if key in {s.key for s in current}]
        rest = [s.key for s in current if s.key not in listed]
        sections = {s.key: s for s in current}
        for index, key in enumerate(listed + rest):
            sections[key].order = index
            sections[key].save(update_fields=["order"])
        return Response(HomeSectionSerializer(self.get_queryset(), many=True).data)


@extend_schema(tags=TAGS)
class MediaCategoryViewSet(SiteViewSet):
    queryset = m.MediaCategory.objects.annotate(count=Count("assets")).order_by("name")
    serializer_class = MediaCategorySerializer
    search_fields = ("name",)
    pagination_class = None


@extend_schema(tags=TAGS)
class MediaAssetViewSet(SiteViewSet):
    queryset = m.MediaAsset.objects.select_related("category", "uploaded_by")
    serializer_class = MediaAssetSerializer
    search_fields = ("title", "alt")
    filterset_fields = ("kind", "category")

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


@extend_schema(tags=TAGS)
class LeadViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                  mixins.DestroyModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsLeadManager]
    queryset = m.Lead.objects.select_related("course", "branch", "assigned_to")
    serializer_class = LeadSerializer
    pagination_class = CMSPagination
    search_fields = ("parent_name", "child_name", "phone", "message", "note")
    filterset_fields = ("status", "course", "branch", "contact_method", "assigned_to", "utm_source")
    ordering_fields = ("created_at", "status")

    def perform_destroy(self, instance):
        if not is_admin_user(self.request.user):
            raise PermissionDenied("Удалить заявку может только администратор.")
        instance.delete()

    @action(detail=False, methods=["get"])
    def summary(self, request):
        counts = dict(m.Lead.objects.values_list("status").annotate(n=Count("id")))
        week = m.Lead.objects.filter(created_at__gte=timezone.now() - timezone.timedelta(days=7)).count()
        return Response({"by_status": {s: counts.get(s, 0) for s in m.Lead.Status.values}, "last_7_days": week})


@extend_schema(tags=TAGS)
class RegistrationViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsLeadManager]
    queryset = m.EventRegistration.objects.select_related("event")
    serializer_class = RegistrationSerializer
    pagination_class = CMSPagination
    search_fields = ("parent_name", "phone", "child_name")
    filterset_fields = ("event", "status")


@extend_schema(tags=TAGS, responses={200: dict})
class SettingsView(APIView):
    permission_classes = [IsAuthenticated, IsSiteEditor]
    parser_classes = PARSERS

    def get(self, request):
        return Response(SettingsSerializer(m.SiteSettings.load(), context={"request": request}).data)

    def patch(self, request):
        serializer = SettingsSerializer(m.SiteSettings.load(), data=request.data, partial=True,
                                        context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


def _choices(enum) -> list[dict]:
    return [{"value": value, "label": label} for value, label in enum.choices]


@extend_schema(tags=TAGS, responses={200: dict})
class MetaView(APIView):
    """Choices, permissions and what can be linked (LMS courses, trainers,
    published student projects, news)."""

    permission_classes = [IsAuthenticated, IsLeadManager]

    def get(self, request):
        from apps.academy.models import Course
        from apps.users.models import Teacher

        editor = can_edit_site(request.user)
        payload = {
            "permissions": {
                "can_edit": editor,
                "can_approve": can_approve(request.user),
                "require_approval": require_approval(),
                "can_delete_leads": is_admin_user(request.user),
            },
            "user_id": request.user.pk,
            "staff": [{"id": u.pk, "name": u.get_full_name() or u.username, "role": u.role} for u in lead_staff()],
            "public_site_url": getattr(settings, "PUBLIC_WEBSITE_URL", "") or None,
            "choices": {
                "workflow": _choices(m.Workflow) + [{"value": "scheduled", "label": "Запланировано"}],
                "event_category": _choices(m.Event.Category),
                "achievement_category": _choices(m.Achievement.Category),
                "course_icon": _choices(m.CoursePage.Icon),
                "project_category": [{"value": v, "label": label} for v, label in m.PROJECT_CATEGORIES if v],
                "testimonial_role": _choices(m.Testimonial.Role),
                "team_group": _choices(m.TeamMember.Group),
                "language": _choices(m.Testimonial.Language),
                "news_category": _choices(Article.Category),
                "lead_status": _choices(m.Lead.Status),
                "contact_method": _choices(m.Lead.ContactMethod),
                "registration_status": _choices(m.EventRegistration.Status),
                "media_kind": _choices(m.MediaAsset.Kind),
            },
        }
        if editor:
            payload["lms"] = {
                "courses": [{"id": c.pk, "name": c.name, "lessons": c.count_lesson} for c in Course.objects.all()],
                "teachers": [
                    {"id": t.pk, "name": t.user.get_full_name(), "position": t.position}
                    for t in Teacher.objects.filter(is_active=True).select_related("user")
                ],
                "projects": [
                    {"id": p.pk, "title": p.title, "date": p.project_date.isoformat()}
                    for p in StudentProject.objects.filter(status=StudentProject.Status.PUBLISHED).order_by("-project_date")[:200]
                ],
                "news": [
                    {"id": a.pk, "title": a.title, "published_at": a.published_at.isoformat()}
                    for a in Article.objects.public().order_by("-published_at")[:200]
                ],
            }
        return Response(payload)


# What the dashboard knows about each content type: model, the title, the
# Russian fields whose ky/en translations are checked, the cover field.
CONTENT_TYPES = {
    "courses": {"model": m.CoursePage, "title": "title", "i18n": ("title", "tagline"), "cover": "cover",
                "excerpt": "tagline", "label": "Курс"},
    "events": {"model": m.Event, "title": "title", "i18n": ("title", "excerpt"), "cover": "cover",
               "excerpt": "excerpt", "label": "Событие"},
    "achievements": {"model": m.Achievement, "title": "title", "i18n": ("title", "excerpt"), "cover": "cover",
                     "excerpt": "excerpt", "label": "Достижение"},
    "news": {"model": Article, "title": "title", "i18n": ("title", "excerpt"), "cover": "cover",
             "excerpt": "excerpt", "label": "Новость"},
    "team": {"model": m.TeamMember, "title": "display_name", "i18n": ("position", "bio"), "cover": "photo",
             "excerpt": "bio", "label": "Команда"},
    "testimonials": {"model": m.Testimonial, "title": "author_name", "i18n": (), "cover": None, "excerpt": None,
                     "label": "Отзыв"},
}


def _state(obj, now) -> str:
    if obj.status == "published":
        return "scheduled" if obj.published_at > now else "published"
    return obj.status


def _content_rows(now):
    """Every non-archived CMS record as a light dict (the site holds hundreds, not millions)."""
    rows = []
    for key, spec in CONTENT_TYPES.items():
        qs = spec["model"].objects.all()
        if key == "team":
            qs = qs.select_related("teacher__user")
        for obj in qs:
            state = _state(obj, now)
            cover = getattr(obj, spec["cover"]) if spec["cover"] else None
            issues = []
            if spec["cover"] and not cover and not (key == "team" and obj.teacher_id and obj.teacher.image):
                issues.append("cover")
            if spec["excerpt"] and not (getattr(obj, spec["excerpt"]) or "").strip():
                issues.append("excerpt")
            for lang in ("ky", "en"):
                if any((getattr(obj, f) or "").strip() and not (getattr(obj, f"{f}_{lang}") or "").strip()
                       for f in spec["i18n"]):
                    issues.append(lang)
            if key not in ("testimonials",) and not (obj.seo_title and obj.seo_description):
                issues.append("seo")
            rows.append({
                "resource": key,
                "type_label": spec["label"],
                "id": obj.pk,
                "title": str(getattr(obj, spec["title"]) or "—"),
                "state": state,
                "cover": _file_url(cover) if cover else None,
                "updated_at": obj.updated_at.isoformat(),
                "published_at": obj.published_at.isoformat(),
                "issues": issues,
            })
    return rows


@extend_schema(tags=TAGS, responses={200: dict})
class OverviewView(APIView):
    """Counters for the «Сайт» dashboard: what waits for review, new leads,
    recent changes, drafts, what needs to be filled, translation and SEO coverage."""

    permission_classes = [IsAuthenticated, IsSiteEditor]

    def get(self, request):
        now = timezone.now()
        rows = _content_rows(now)
        counts = {key: {"draft": 0, "review": 0, "scheduled": 0, "published": 0, "archived": 0} for key in CONTENT_TYPES}
        for row in rows:
            counts[row["resource"]][row["state"]] += 1
        live = [r for r in rows if r["state"] != "archived"]
        by_update = sorted(rows, key=lambda r: r["updated_at"], reverse=True)
        coverage = {
            key: {
                "total": sum(1 for r in live if r["resource"] == key),
                "ky": sum(1 for r in live if r["resource"] == key and "ky" not in r["issues"]),
                "en": sum(1 for r in live if r["resource"] == key and "en" not in r["issues"]),
                "seo": sum(1 for r in live if r["resource"] == key and "seo" not in r["issues"]),
            }
            for key in CONTENT_TYPES
        }
        leads = dict(m.Lead.objects.values_list("status").annotate(n=Count("id")))
        settings_obj = m.SiteSettings.load()
        return Response({
            **counts,
            "leads_new": leads.get(m.Lead.Status.NEW, 0),
            "leads_by_status": {s: leads.get(s, 0) for s in m.Lead.Status.values},
            "registrations_new": m.EventRegistration.objects.filter(status=m.EventRegistration.Status.NEW).count(),
            "upcoming_events": m.Event.objects.public().filter(starts_at__gte=now).count(),
            "media": m.MediaAsset.objects.count(),
            "projects": StudentProject.objects.filter(status=StudentProject.Status.PUBLISHED).count(),
            "featured_projects": settings_obj.featured_projects.count(),
            "recent": by_update[:10],
            "recently_published": sorted((r for r in rows if r["state"] == "published"),
                                         key=lambda r: r["published_at"], reverse=True)[:6],
            "drafts": [r for r in by_update if r["state"] in ("draft", "review")][:10],
            "attention": [r for r in by_update if r["state"] != "archived" and r["issues"]][:300],
            "coverage": coverage,
        })


@extend_schema(tags=TAGS, responses={200: dict})
class ProjectsView(APIView):
    """Published student projects (registered by trainers in the LMS — only
    trainers create them) as the public site shows them, and which of them
    are on the homepage. `POST {"id": 1, "featured": true}` toggles one."""

    permission_classes = [IsAuthenticated, IsSiteEditor]

    def get(self, request):
        from apps.projects import public as projects_public

        featured = set(m.SiteSettings.load().featured_projects.values_list("pk", flat=True))
        q = (request.query_params.get("search") or "").strip().casefold()
        show_trainer = projects_public.config()["show_trainer"]
        results = []
        for project in projects_public.published_queryset():
            record = projects_public._record(project, show_trainer)
            if q and q not in record["title"].casefold() and q not in (record["student"] or "").casefold():
                continue
            results.append({
                "id": project.pk,
                "title": record["title"],
                "short_description": record["short_description"],
                "student": record["student"],
                "group": record["group"],
                "date": record["date"],
                "technologies": record["technologies"],
                "cover": record["cover_url"],
                "public_url": public_url(f"/projects/{record['key']}"),
                "is_featured": project.pk in featured,
            })
        return Response({"count": len(results), "results": results})

    def post(self, request):
        pk = request.data.get("id")
        project = StudentProject.objects.filter(pk=pk if str(pk).isdigit() else 0,
                                                status=StudentProject.Status.PUBLISHED).first()
        if project is None:
            raise ValidationError({"id": "Опубликованный проект не найден."})
        site = m.SiteSettings.load()
        if request.data.get("featured"):
            site.featured_projects.add(project)
        else:
            site.featured_projects.remove(project)
        site.save(update_fields=["updated_at"])
        return Response({"id": project.pk, "is_featured": bool(request.data.get("featured"))})
