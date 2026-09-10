from __future__ import annotations

from django.http import JsonResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.filters import OrderingFilter, SearchFilter
from django_filters.rest_framework import DjangoFilterBackend

from .import_export.formats import UnsupportedFileFormat
from .import_export.teachers import (
    TeacherImportValidationError,
    export_teachers,
    import_teachers,
    preview_teachers_import,
)
from .models import Subject, User
from .permissions import IsAdmin, IsTeacher
from .serializers import ImportFileRequestSerializer, ImportPreviewSerializer, ImportResultSerializer, SubjectSerializer

from .models import Teacher
from .serializers import (
    LoginSerializer,
    TeacherSerializer,
    TrainerCreateSerializer,
    UserSerializer,
)


def health(request):
    return JsonResponse({"status": "ok"})


@extend_schema(tags=["Authentication"])
class LoginView(GenericAPIView):
    """POST /api/v1/users/auth/login/ — obtain a JWT access/refresh pair."""

    permission_classes = []
    authentication_classes = []
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


@extend_schema(tags=["Authentication"])
class RefreshView(TokenRefreshView):
    """POST /api/v1/users/auth/refresh/ — exchange a refresh token for a new access token."""


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Authentication"], responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)


@extend_schema(tags=["Trainers"])
class TrainerViewSet(viewsets.ModelViewSet):
    queryset = Teacher.objects.select_related("user").prefetch_related("subjects").all()
    serializer_class = TeacherSerializer
    http_method_names = ["get", "post", "delete"]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_active", "user__is_verified", "subjects"]
    search_fields = ["user__username", "user__email", "user__first_name", "user__last_name", "phone"]
    ordering_fields = ["user__first_name", "user__last_name", "created_at"]
    ordering = ["-created_at"]

    def get_permissions(self):
        if self.action == "me":
            return [IsAuthenticated(), IsTeacher()]
        return [IsAuthenticated(), IsAdmin()]

    def get_serializer_class(self):
        if self.action == "create":
            return TrainerCreateSerializer
        return TeacherSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        teacher = serializer.save()
        result = getattr(serializer, "_creation_result", None)
        data = TeacherSerializer(teacher).data
        if result is not None and not result.email_sent:
            data["_warning"] = (
                "Trainer создан, но письмо с учётными данными не отправлено. "
                "Используйте «Изменить пароль и отправить» в админ-панели."
            )
        headers = self.get_success_headers(data)
        return Response(data, status=status.HTTP_201_CREATED, headers=headers)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return Response(self.get_serializer(instance).data)

    def destroy(self, request, *args, **kwargs):
        # Trainers are deactivated, never hard-deleted (see spec §23).
        instance = self.get_object()
        instance.is_active = False
        instance.user.is_active = False
        instance.user.save(update_fields=["is_active", "updated_at"])
        instance.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        teacher = getattr(request.user, "teacher_profile", None)
        if teacher is None:
            raise PermissionDenied("У этого пользователя нет профиля тренера.")
        return Response(TeacherSerializer(teacher).data)

    @action(detail=True, methods=["post"], url_path="verify", permission_classes=[IsAuthenticated, IsAdmin])
    def verify(self, request, pk=None):
        teacher = self.get_object()
        teacher.user.is_verified = True
        teacher.user.save(update_fields=["is_verified", "updated_at"])
        return Response(TeacherSerializer(teacher).data)

    @extend_schema(
        tags=["Trainers"],
        parameters=[
            OpenApiParameter(name="export_format", type=str, enum=["csv", "xlsx"], required=False, description="csv (по умолчанию) или xlsx."),
        ],
        request=None,
        responses={200: bytes},
        description=(
            "Экспорт тренеров (текущего отфильтрованного списка) в CSV или XLSX. Пароль никогда "
            "не экспортируется. Параметр называется export_format (не format — это имя "
            "зарезервировано DRF для согласования типа содержимого ответа)."
        ),
    )
    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        fmt = request.query_params.get("export_format", "csv")
        queryset = self.filter_queryset(self.get_queryset())
        try:
            return export_teachers(queryset, fmt)
        except UnsupportedFileFormat as exc:
            raise DRFValidationError(str(exc))

    @extend_schema(
        tags=["Trainers"],
        request=ImportFileRequestSerializer,
        responses=ImportPreviewSerializer,
        description="Проверка файла импорта тренеров без сохранения изменений.",
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="import/preview",
        parser_classes=[MultiPartParser, FormParser],
    )
    def import_preview(self, request):
        file_obj = request.FILES.get("file")
        if not file_obj:
            raise DRFValidationError({"file": ["Файл обязателен."]})
        try:
            preview = preview_teachers_import(file_obj)
        except UnsupportedFileFormat as exc:
            raise DRFValidationError(str(exc))
        return Response(preview.as_dict())

    @extend_schema(
        tags=["Trainers"],
        request=ImportFileRequestSerializer,
        responses={201: ImportResultSerializer, 400: ImportPreviewSerializer},
        description=(
            "Импорт тренеров из CSV/XLSX. Транзакционный: при наличии хотя бы одной "
            "ошибки ни одна строка не сохраняется."
        ),
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="import",
        parser_classes=[MultiPartParser, FormParser],
    )
    def import_file(self, request):
        file_obj = request.FILES.get("file")
        if not file_obj:
            raise DRFValidationError({"file": ["Файл обязателен."]})
        try:
            result = import_teachers(file_obj)
        except UnsupportedFileFormat as exc:
            raise DRFValidationError(str(exc))
        except TeacherImportValidationError as exc:
            return Response(
                {"detail": "Импорт не выполнен — найдены ошибки.", **exc.preview.as_dict()},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result.as_dict(), status=status.HTTP_201_CREATED)


class SubjectViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SubjectSerializer
    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_fields = ["is_active"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at", "updated_at"]
    ordering = ["name"]

    def get_permissions(self):
        user = self.request.user

        if not user or not user.is_authenticated:
            return super().get_permissions()

        if getattr(user, "role", None) == User.Role.ADMIN:
            return [IsAdmin()]

        return [IsTeacher()]

    def get_queryset(self):
        user = self.request.user

        if not user or not user.is_authenticated:
            return Subject.objects.none()

        if getattr(user, "role", None) == User.Role.TEACHER:
            return Subject.objects.filter(is_active=True)

        return Subject.objects.all()