from __future__ import annotations

from django.http import JsonResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from apps.users.models import Teacher
from apps.users.permissions import IsAdmin, IsTeacher
from apps.users.serializers import (
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
    """GET /api/v1/users/auth/me/ — the authenticated user's own profile."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Authentication"], responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)


@extend_schema(tags=["Trainers"])
class TrainerViewSet(viewsets.ModelViewSet):
    """
    /api/v1/users/trainers/            — Admin: list, create
    /api/v1/users/trainers/{id}/       — Admin: retrieve, delete (deactivate)
    /api/v1/users/trainers/{id}/verify/  — Admin: confirm account
    /api/v1/users/trainers/me/         — Teacher: their own profile only

    Trainer profiles are read-only through the API in this version — editing
    (including changing a trainer's password) goes through Django Admin, via
    the "Изменить пароль и отправить" page. The API never generates or
    resends a password on its own.
    """

    queryset = Teacher.objects.select_related("user").prefetch_related("subjects").all()
    serializer_class = TeacherSerializer
    http_method_names = ["get", "post", "delete"]

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
