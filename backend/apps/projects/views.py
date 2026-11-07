"""API — /api/v1/projects/. Scope and rights come from access.py."""
from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.db.models import Count, Max, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.response import Response


from . import access
from .models import ProjectImage, StudentProject, Technology
from .serializers import (
    MAX_IMAGES,
    ProjectDetailSerializer,
    ProjectImageSerializer,
    ProjectImageUploadSerializer,
    ProjectListSerializer,
    ProjectWriteSerializer,
    group_ref,
)


class CanUseProjects(BasePermission):
    message = "Раздел «Проекты студентов» вам недоступен."

    def has_permission(self, request, view) -> bool:
        if not access.can_view(request.user):
            return False
        if request.method in SAFE_METHODS:
            return True
        if getattr(view, "action", None) == "create" and not access.can_create(request.user):
            self.message = "Добавлять проекты может только тренер."
            return False
        return True

    def has_object_permission(self, request, view, obj) -> bool:
        if request.method in SAFE_METHODS:
            return True
        if not access.can_edit(request.user, obj):
            self.message = "Изменять проект может только тренер, который его добавил."
            return False
        return True


def _parse_date(value: str | None, name: str):
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValidationError({name: "Дата в формате ГГГГ-ММ-ДД."})


def _int(value: str | None, name: str):
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise ValidationError({name: "Ожидается число."})


class ProjectPagination(PageNumberPagination):
    page_size = 12  # a full 3-column gallery
    page_size_query_param = "page_size"
    max_page_size = 60


class ProjectViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                     mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Student projects.

    List filters: ``q`` (title, description, student), ``group``, ``student``,
    ``technology`` (name), ``date_from`` / ``date_to``, ``status``, ``mine=1``.
    """

    permission_classes = [IsAuthenticated, CanUseProjects]
    pagination_class = ProjectPagination
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [OrderingFilter]
    ordering_fields = ["project_date", "created_at", "title", "rating"]
    ordering = ["-project_date", "-id"]

    def get_queryset(self):
        return (
            access.visible_projects(self.request.user)
            .select_related("student", "group__course", "created_by__teacher_profile")
            .prefetch_related("technologies", Prefetch("images", queryset=ProjectImage.objects.order_by("order", "id")))
        )

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return ProjectWriteSerializer
        if self.action == "list":
            return ProjectListSerializer
        return ProjectDetailSerializer

    def filter_queryset(self, queryset):
        params = self.request.query_params
        q = (params.get("q") or "").strip()
        if q:
            cond = Q(title__icontains=q) | Q(short_description__icontains=q) | Q(technologies__name__icontains=q)
            for word in q.split():
                cond |= Q(student__first_name__icontains=word) | Q(student__last_name__icontains=word)
            queryset = queryset.filter(cond)
        if (group := _int(params.get("group"), "group")) is not None:
            queryset = queryset.filter(group_id=group)
        if (student := _int(params.get("student"), "student")) is not None:
            queryset = queryset.filter(student_id=student)
        if tech := (params.get("technology") or "").strip():
            queryset = queryset.filter(technologies__name__iexact=tech)
        if date_from := _parse_date(params.get("date_from"), "date_from"):
            queryset = queryset.filter(project_date__gte=date_from)
        if date_to := _parse_date(params.get("date_to"), "date_to"):
            queryset = queryset.filter(project_date__lte=date_to)
        if (state := params.get("status")) in StudentProject.Status.values:
            queryset = queryset.filter(status=state)
        if params.get("mine") in ("1", "true"):
            queryset = queryset.filter(created_by=self.request.user)
        return super().filter_queryset(queryset.distinct())

    def _detail(self, project, code=status.HTTP_200_OK):
        project = self.get_queryset().get(pk=project.pk)
        return Response(ProjectDetailSerializer(project, context=self.get_serializer_context()).data, status=code)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        project = serializer.save(created_by=request.user)
        return self._detail(project, status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        return self._detail(serializer.save())

    # -- statistics & form data ---------------------------------------------

    @extend_schema(tags=["Projects"])
    @action(detail=False, methods=["get"])
    def stats(self, request):
        """KPI cards over everything the user may see."""
        qs = access.visible_projects(request.user)
        today = timezone.localdate()
        month_start = today.replace(day=1)
        prev_start = (month_start - dt.timedelta(days=1)).replace(day=1)
        this_month = qs.filter(project_date__gte=month_start, project_date__lte=today).count()
        prev_month = qs.filter(project_date__gte=prev_start, project_date__lt=month_start).count()
        change = None
        if prev_month:
            change = round((this_month - prev_month) * 100 / prev_month)
        return Response({
            "total_projects": qs.count(),
            "active_students": qs.values("student_id").distinct().count(),
            "projects_this_month": this_month,
            "projects_previous_month": prev_month,
            "month_change_percent": change,
            "groups_with_projects": qs.exclude(group__isnull=True).values("group_id").distinct().count(),
            "drafts": qs.filter(status=StudentProject.Status.DRAFT).count(),
        })

    @extend_schema(tags=["Projects"])
    @action(detail=False, methods=["get"])
    def options(self, request):
        """Filter and form choices: groups and students that have projects
        the user sees, the students the user may register a project for,
        and the tech names already in use."""
        user = request.user
        visible = access.visible_projects(user)
        group_rows = {}
        for g in visible.exclude(group__isnull=True).values("group_id", "group__name").distinct():
            group_rows[g["group_id"]] = {"id": g["group_id"], "name": g["group__name"]}
        student_rows = {}
        for s in visible.values("student_id", "student__first_name", "student__last_name").distinct():
            name = f"{s['student__first_name']} {s['student__last_name']}".strip()
            student_rows[s["student_id"]] = {"id": s["student_id"], "full_name": name}

        selectable = []
        if access.can_create(user):
            counts = dict(
                StudentProject.objects.filter(created_by=user).values("student_id")
                .annotate(n=Count("id")).values_list("student_id", "n")
            )
            for st in access.selectable_students(user).exclude(group__isnull=True).order_by("group__name", "first_name", "last_name"):
                selectable.append({
                    "id": st.pk, "full_name": str(st), "status": st.status,
                    "group": group_ref(st.group), "projects_count": counts.get(st.pk, 0),
                })

        used = Technology.objects.filter(projects__in=visible).annotate(n=Count("projects", distinct=True)).order_by("-n", "name")
        return Response({
            "can_create": access.can_create(user),
            "groups": sorted(group_rows.values(), key=lambda r: r["name"]),
            "students": sorted(student_rows.values(), key=lambda r: r["full_name"]),
            "selectable_students": selectable,
            "technologies": [t.name for t in used[:100]],
            "max_images": MAX_IMAGES,
        })

    # -- images -----------------------------------------------------------------

    def _editable(self, pk) -> StudentProject:
        project = self.get_object()
        if not access.can_edit(self.request.user, project):
            raise PermissionDenied("Изменять проект может только тренер, который его добавил.")
        return project

    @extend_schema(tags=["Projects"], request=ProjectImageUploadSerializer, responses=ProjectImageSerializer)
    @action(detail=True, methods=["post"], url_path="images", parser_classes=[MultiPartParser, FormParser])
    def upload_image(self, request, pk=None):
        project = self._editable(pk)
        serializer = ProjectImageUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            StudentProject.objects.select_for_update().filter(pk=project.pk).first()
            existing = project.images.count()
            if existing >= MAX_IMAGES:
                raise ValidationError({"image": f"Не больше {MAX_IMAGES} изображений в проекте."})
            make_cover = serializer.validated_data["is_cover"] or existing == 0
            if make_cover:
                project.images.update(is_cover=False)
            next_order = (project.images.aggregate(m=Max("order"))["m"] or 0) + 1
            image = ProjectImage.objects.create(project=project, image=serializer.validated_data["image"],
                                                is_cover=make_cover, order=next_order)
            StudentProject.objects.filter(pk=project.pk).update(updated_at=timezone.now())
        return Response(ProjectImageSerializer(image, context=self.get_serializer_context()).data,
                        status=status.HTTP_201_CREATED)

    @extend_schema(tags=["Projects"])
    @action(detail=True, methods=["patch", "delete"], url_path=r"images/(?P<image_id>\d+)")
    def image(self, request, pk=None, image_id=None):
        project = self._editable(pk)
        image = get_object_or_404(ProjectImage, pk=image_id, project=project)
        with transaction.atomic():
            if request.method == "DELETE":
                was_cover = image.is_cover
                image.delete()
                if was_cover and (first := project.images.order_by("order", "id").first()):
                    first.is_cover = True
                    first.save(update_fields=["is_cover"])
                return Response(status=status.HTTP_204_NO_CONTENT)
            if request.data.get("is_cover") in (True, "true", "1", 1):
                project.images.exclude(pk=image.pk).update(is_cover=False)
                image.is_cover = True
            if "order" in request.data:
                image.order = _int(str(request.data["order"]), "order") or 0
            image.save()
        return Response(ProjectImageSerializer(image, context=self.get_serializer_context()).data)
