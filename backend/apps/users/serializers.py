from __future__ import annotations

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import Subject, Teacher, User
from apps.users.services import create_teacher


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class UserSerializer(serializers.ModelSerializer):
    """Read-only representation of a User. Never exposes the password."""

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_verified",
            "is_active",
        ]
        read_only_fields = fields


class TeacherSerializer(serializers.ModelSerializer):
    """Read representation of a Teacher profile, including its User info.

    On the first version teacher profiles are read-only through the API
    (per spec §13) — profile edits go through the admin.
    """

    user = UserSerializer(read_only=True)
    subjects = SubjectSerializer(many=True, read_only=True)

    class Meta:
        model = Teacher
        fields = [
            "id",
            "user",
            "subjects",
            "phone",
            "image",
            "position",
            "experience_years",
            "bio",
            "hire_date",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class TrainerCreateSerializer(serializers.Serializer):
    """Used by admins to create a Trainer through the API (POST /trainers/).

    Mirrors what the Django Admin "Add Trainer" form does: Admin sets the
    password directly (never backend-generated), it's hashed and emailed to
    the trainer, and the account always starts with ``is_verified=False`` —
    that flag is server-controlled and can only be flipped by
    ``POST /trainers/{id}/verify/`` or the equivalent admin action.
    """

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    image = serializers.ImageField(required=False, allow_null=True)
    subjects = serializers.PrimaryKeyRelatedField(
        queryset=Subject.objects.all(), many=True, required=False
    )
    position = serializers.CharField(max_length=100, required=False, default="Тренер")
    experience_years = serializers.IntegerField(required=False, min_value=0, max_value=60, default=0)
    bio = serializers.CharField(required=False, allow_blank=True)
    hire_date = serializers.DateField(required=False, allow_null=True)
    is_active = serializers.BooleanField(required=False, default=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Пользователь с таким логином уже существует.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Пользователь с таким email уже существует.")
        return value

    def validate(self, attrs):
        password = attrs.get("password")
        if password != attrs.get("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "Пароли не совпадают."}
            )
        validate_password(password)
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        subjects = validated_data.pop("subjects", [])
        result = create_teacher(subjects=subjects, **validated_data)
        # Stash the result on the serializer instance so the view can report
        # whether the credentials email actually went out.
        self._creation_result = result
        return result.teacher


class LoginSerializer(serializers.Serializer):
    """Validates credentials and enforces account verification rules.

    On success, returns access/refresh tokens plus the authenticated user's
    public profile — never the password.
    """

    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    default_error_messages = {
        "invalid_credentials": "Неверный логин или пароль.",
        "inactive": "Аккаунт деактивирован.",
        "not_verified": "Аккаунт ещё не подтверждён администратором.",
    }

    def validate(self, attrs):
        request = self.context.get("request")
        user = authenticate(
            request=request,
            username=attrs["username"],
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError(
                {"detail": self.error_messages["invalid_credentials"]}
            )

        if not user.is_active:
            raise serializers.ValidationError({"detail": self.error_messages["inactive"]})

        # Verification gating applies to Trainer accounts only — Admin
        # accounts are created via `createsuperuser` and are trusted from
        # the start (see users.models.User custom manager).
        if user.role == User.Role.TEACHER and not user.is_verified:
            raise serializers.ValidationError(
                {"detail": self.error_messages["not_verified"]}
            )

        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
        }
