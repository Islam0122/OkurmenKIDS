"""Раздел «Сотрудники» HR-менеджера (/api/v1/hr/employees/).

Сотрудник — существующий `users.User`; отдельной таблицы нет. HR управляет
только ролями из `User.HR_MANAGEABLE_ROLES` (белый список, единый источник и
для API, и для формы — `GET meta/`). Защищённые должности
(`User.HR_PROTECTED_ROLES`: директор, бухгалтер, ДОП — директор отдела продаж,
операционный директор), администраторы, суперпользователи, служебные (staff)
учётные записи и собственная учётная запись — вне полномочий: список их не
показывает, назначить такую роль нельзя (400), а любое действие с такой
учётной записью сервер отклоняет (403).

Тренер создаётся штатным механизмом LMS (`services.create_teacher`) — вместе с
профилем тренера. Поэтому роль «Тренер» при редактировании не меняется ни на
другую, ни с другой: без профиля тренера кабинет тренера не работает.

Пароль задаёт HR при создании или сбросе; хранится только хеш
(`set_password`), в ответах пароль не возвращается. Удаления нет: сотрудник
деактивируется, история посещаемости и связанные данные остаются.
"""
from __future__ import annotations

import logging

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from apps.recruitment.models import HRActivity
from apps.recruitment.services import activity
from apps.recruitment.services.reports import activity_brief

from .models import User
from .permissions import IsHRManager, hr_can_manage, hr_can_view
from .services import create_teacher

logger = logging.getLogger("apps.users.hr")

TAGS = ["HR employees"]
# Понятные названия должностей для HR (в модели — короткие подписи-аббревиатуры).
ROLE_TITLES = {
    User.Role.DOP: "ДОП — директор отдела продаж",
    User.Role.ROP: "РОП — руководитель отдела продаж",
    User.Role.ROM: "РОМ — руководитель отдела маркетинга",
    User.Role.TEAM_LEAD: "Руководитель тренеров (Team Lead)",
}


def role_title(role: str) -> str:
    return ROLE_TITLES.get(role) or dict(User.Role.choices).get(role, role)


ROLE_CHOICES = [(role.value, role_title(role)) for role in User.HR_MANAGEABLE_ROLES]


class HREmployeeSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    role_label = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "full_name", "role", "role_label",
                  "is_active", "can_manage", "created_at", "last_login"]
        read_only_fields = fields

    def get_can_manage(self, obj: User) -> bool:
        request = self.context.get("request")
        return bool(request and hr_can_manage(request.user, obj))

    def get_full_name(self, obj: User) -> str:
        return obj.get_full_name() or obj.username

    def get_role_label(self, obj: User) -> str:
        return role_title(obj.role)


class HREmployeeCardSerializer(HREmployeeSerializer):
    """Карточка: только данные, которые реально есть в системе, плюс история
    кадровых действий и кандидат, из которого сотрудник был принят."""

    hired_from = serializers.SerializerMethodField()
    history = serializers.SerializerMethodField()

    class Meta(HREmployeeSerializer.Meta):
        fields = [*HREmployeeSerializer.Meta.fields, "hired_from", "history"]
        read_only_fields = fields

    def get_hired_from(self, obj: User):
        application = getattr(obj, "hired_from_application", None)
        if application is None:
            return None
        return {"id": application.candidate_id, "application": application.pk, "number": application.number,
                "full_name": application.candidate.full_name, "position": application.position_label}

    def get_history(self, obj: User):
        entries = obj.hr_activities.select_related("actor", "candidate", "employee")[:50]
        return [activity_brief(entry) for entry in entries]


class HRPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class _PasswordMixin(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    def _check_password(self, attrs, user: User | None) -> None:
        if attrs.get("password") != attrs.get("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Пароли не совпадают."})
        try:
            validate_password(attrs["password"], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": exc.messages}) from exc


class HREmployeeWriteSerializer(serializers.ModelSerializer):
    role = serializers.ChoiceField(choices=ROLE_CHOICES)

    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name", "role"]
        extra_kwargs = {"last_name": {"required": False}}

    def validate_username(self, value):
        qs = User.objects.filter(username__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Пользователь с таким логином уже существует.")
        return value

    def validate_email(self, value):
        qs = User.objects.filter(email__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Пользователь с таким email уже существует.")
        return value

    def validate_role(self, value):
        # ChoiceField уже отклоняет роли вне белого списка; здесь — правило
        # для тренера: его учётная запись существует вместе с профилем тренера.
        current = getattr(self.instance, "role", None)
        if current is not None and value != current and User.Role.TEACHER in (current, value):
            raise serializers.ValidationError(
                "Роль «Тренер» не меняется на другую и не назначается существующему сотруднику: "
                "тренер создаётся вместе с профилем тренера. Создайте новую учётную запись."
            )
        return value


class HREmployeeCreateSerializer(_PasswordMixin, HREmployeeWriteSerializer):
    class Meta(HREmployeeWriteSerializer.Meta):
        fields = [*HREmployeeWriteSerializer.Meta.fields, "password", "password_confirm"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        self._check_password(attrs, User(username=attrs.get("username", ""), email=attrs.get("email", ""),
                                         first_name=attrs.get("first_name", ""),
                                         last_name=attrs.get("last_name", "")))
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        if validated_data.get("role") == User.Role.TEACHER:
            # Штатное создание тренера — вместе с профилем; письмо с паролем
            # не отправляется: пароль задаёт и передаёт HR, как и остальным.
            fields = {k: v for k, v in validated_data.items() if k != "role"}
            return create_teacher(password=password, send_email=False, **fields).teacher.user
        # Обычный пользователь без прав администратора (is_staff и
        # is_superuser не выставляются; для ролей LMS их сбрасывает User.save()).
        return User.objects.create_user(password=password, is_verified=True, **validated_data)


class HRPasswordSerializer(_PasswordMixin):
    def validate(self, attrs):
        self._check_password(attrs, self.context["target"])
        return attrs


class HREmployeeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                        mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Список, карточка, создание, изменение, пароль, деактивация/активация.
    DELETE нет — только деактивация."""

    permission_classes = [IsAuthenticated, IsHRManager]
    pagination_class = HRPagination
    http_method_names = ["get", "post", "patch", "put"]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["role", "is_active"]
    search_fields = ["first_name", "last_name", "username", "email"]
    ordering_fields = ["last_name", "first_name", "created_at", "role", "is_active"]
    ordering = ["-created_at"]
    lookup_value_regex = r"\d+"

    def get_queryset(self):
        return User.objects.filter(
            role__in=User.HR_MANAGEABLE_ROLES, is_superuser=False, is_staff=False,
        ).exclude(pk=self.request.user.pk)

    def get_object(self):
        # Ищем среди всех пользователей, чтобы на защищённого сотрудника
        # ответить явным отказом (403), а не «не найден».
        target = get_object_or_404(User, pk=self.kwargs["pk"])
        # Карточку можно открыть у всех, кого HR видит; менять — только тех,
        # кем HR управляет (коллеги-HR — только просмотр).
        allowed = hr_can_view if self.action == "retrieve" else hr_can_manage
        if not allowed(self.request.user, target):
            logger.warning("hr denied action=%s target=%s role=%s by=%s",
                           self.action, target.pk, target.role, self.request.user.pk)
            raise PermissionDenied("Этот сотрудник вне полномочий HR: управлять его учётной записью нельзя.")
        return target

    def get_serializer_class(self):
        if self.action == "create":
            return HREmployeeCreateSerializer
        if self.action in ("update", "partial_update"):
            return HREmployeeWriteSerializer
        if self.action == "retrieve":
            return HREmployeeCardSerializer
        return HREmployeeSerializer

    def _log(self, kind: str, target: User, message: str = "") -> None:
        # Журнал кадровых действий (apps.recruitment.HRActivity); пароль туда не пишется.
        activity.log(kind, self.request.user, employee=target, message=message)

    @extend_schema(tags=TAGS, responses=HREmployeeSerializer)
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        self._log(HRActivity.Kind.EMPLOYEE_CREATED, user, f"Учётная запись «{user.username}» ({user.get_role_display()})")
        return Response(HREmployeeSerializer(user, context=self.get_serializer_context()).data,
                        status=status.HTTP_201_CREATED)

    @extend_schema(tags=TAGS, responses=HREmployeeSerializer)
    def update(self, request, *args, **kwargs):
        target = self.get_object()
        serializer = self.get_serializer(target, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        changes = []
        for field, value in serializer.validated_data.items():
            old = getattr(target, field)
            if old != value:
                if field == "role":
                    changes.append(f"должность: {User.Role(old).label} → {User.Role(value).label}")
                else:
                    changes.append(str(User._meta.get_field(field).verbose_name).lower())
        user = serializer.save()
        if changes:
            self._log(HRActivity.Kind.EMPLOYEE_UPDATED, user, "Изменено: " + ", ".join(changes))
        return Response(HREmployeeSerializer(user, context=self.get_serializer_context()).data)

    @extend_schema(tags=TAGS, request=HRPasswordSerializer, responses=HREmployeeSerializer)
    @action(detail=True, methods=["post"], url_path="set-password")
    def set_password(self, request, pk=None):
        target = self.get_object()
        serializer = HRPasswordSerializer(data=request.data, context={"target": target})
        serializer.is_valid(raise_exception=True)
        target.set_password(serializer.validated_data["password"])
        target.save(update_fields=["password", "updated_at"])
        self._log(HRActivity.Kind.EMPLOYEE_PASSWORD, target, "Пароль изменён")
        return Response(HREmployeeSerializer(target, context=self.get_serializer_context()).data)

    @extend_schema(tags=TAGS, request=None, responses=HREmployeeSerializer)
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        return self._set_active(False)

    @extend_schema(tags=TAGS, request=None, responses=HREmployeeSerializer)
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return self._set_active(True)

    def _set_active(self, value: bool) -> Response:
        target = self.get_object()
        if target.is_active != value:
            target.is_active = value
            target.save(update_fields=["is_active", "updated_at"])
            self._log(HRActivity.Kind.EMPLOYEE_ACTIVATED if value else HRActivity.Kind.EMPLOYEE_DEACTIVATED, target)
        return Response(HREmployeeSerializer(target, context=self.get_serializer_context()).data)

    @extend_schema(tags=TAGS)
    @action(detail=False, methods=["get"])
    def meta(self, request):
        """Роли, которые HR может назначать, и защищённые категории (для подсказки)."""
        return Response({
            "roles": [{"value": value, "label": label} for value, label in ROLE_CHOICES],
            "protected_roles": [{"value": role.value, "label": role_title(role)} for role in User.HR_PROTECTED_ROLES],
        })
