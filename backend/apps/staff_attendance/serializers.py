from __future__ import annotations

import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from apps.users.models import User

from .models import (
    AttendanceAdjustment,
    AttendanceAdminLog,
    AttendanceEvent,
    AttendanceLocation,
    AttendanceSession,
    AttendanceSettings,
    AttendanceWorkSchedule,
    validate_weekdays,
)
from .services.qr import scan_url
from .services.reports import STATUS_LABELS, DayRow

ROLE_LABELS = dict(User.Role.choices)


def local_iso(value, tz) -> str | None:
    """Время в часовом поясе офиса со смещением (2026-10-23T09:05:00+06:00)."""
    return timezone.localtime(value, tz).isoformat() if value else None


def photo_url(user) -> str | None:
    profile = getattr(user, "teacher_profile", None) if user.role == User.Role.TEACHER else None
    image = getattr(profile, "image", None)
    return image.url if image else None


def employee_brief(user) -> dict:
    return {
        "id": user.pk,
        "full_name": user.get_full_name() or user.username,
        "username": user.username,
        "role": user.role,
        "role_label": ROLE_LABELS.get(user.role, user.role),
        "photo_url": photo_url(user),
    }


def session_payload(session: AttendanceSession, tz, now=None) -> dict:
    now = now or timezone.now()
    if session.checked_out_at:
        duration = int((session.checked_out_at - session.checked_in_at).total_seconds())
    elif session.status == AttendanceSession.Status.OPEN:
        duration = max(0, int((now - session.checked_in_at).total_seconds()))
    else:
        duration = None
    return {
        "id": session.pk,
        "work_date": session.work_date.isoformat(),
        "checked_in_at": local_iso(session.checked_in_at, tz),
        "checked_out_at": local_iso(session.checked_out_at, tz),
        "status": session.status,
        "status_label": session.get_status_display(),
        "source": session.source,
        "duration_seconds": duration,
        "expected_start": local_iso(session.expected_start, tz),
        "late_minutes": session.late_minutes,
        "is_adjusted": session.is_adjusted,
        "location": {"id": session.location_id, "name": session.location.name} if session.location_id else None,
        "check_in_distance_m": session.check_in_distance_m,
        "check_out_distance_m": session.check_out_distance_m,
    }


def row_payload(row: DayRow, tz, now=None) -> dict:
    now = now or timezone.now()
    last = row.sessions[-1] if row.sessions else None
    return {
        "key": f"{row.user.pk}:{row.day.isoformat()}",
        "employee": employee_brief(row.user),
        "date": row.day.isoformat(),
        "status": row.status,
        "status_label": STATUS_LABELS[row.status],
        "check_in": local_iso(row.first_in, tz),
        "check_out": local_iso(row.last_out, tz),
        "duration_seconds": row.duration_seconds if row.sessions else None,
        "late_minutes": row.late_minutes,
        "is_late": row.is_late,
        "is_adjusted": row.is_adjusted,
        "expected_start": local_iso(row.window.start, tz) if row.window else None,
        "expected_end": local_iso(row.window.end, tz) if row.window else None,
        "sessions_count": len(row.sessions),
        "last_session_id": last.pk if last else None,
        "locations": sorted({s.location.name for s in row.sessions if s.location_id}),
        "sessions": [session_payload(s, tz, now) for s in row.sessions],
    }


class MarkSerializer(serializers.Serializer):
    """Тело отметки. Идентификатор сотрудника не принимается — только
    request.user; время устройства тоже не принимается."""

    location_code = serializers.CharField(max_length=64)
    latitude = serializers.FloatField(min_value=-90, max_value=90, required=False, allow_null=True)
    longitude = serializers.FloatField(min_value=-180, max_value=180, required=False, allow_null=True)
    accuracy = serializers.FloatField(min_value=0, max_value=100_000, required=False, allow_null=True)
    idempotency_key = serializers.UUIDField(required=False, allow_null=True)


class LocationSerializer(serializers.ModelSerializer):
    qr_url = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceLocation
        fields = ["id", "name", "address", "code", "latitude", "longitude", "radius_m", "is_active",
                  "qr_url", "created_at", "updated_at"]
        read_only_fields = ["id", "code", "qr_url", "created_at", "updated_at"]

    def get_qr_url(self, obj) -> str:
        return scan_url(obj)


class SettingsSerializer(serializers.ModelSerializer):
    work_days = serializers.ListField(child=serializers.IntegerField(min_value=0, max_value=6), allow_empty=True)
    tracked_roles = serializers.ListField(child=serializers.ChoiceField(choices=User.Role.choices), allow_empty=True)
    updated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceSettings
        fields = ["timezone", "max_gps_accuracy_m", "work_start", "work_end", "work_days", "late_grace_minutes",
                  "tracked_roles", "teacher_schedule_from_lessons", "teacher_arrival_before_lesson_minutes",
                  "tracking_started_on", "network_check_enabled", "office_networks", "updated_at", "updated_by_name"]
        read_only_fields = ["updated_at", "updated_by_name"]

    def get_updated_by_name(self, obj) -> str | None:
        return str(obj.updated_by) if obj.updated_by_id else None

    def validate(self, attrs):
        if "work_days" in attrs:
            attrs["work_days"] = sorted(set(attrs["work_days"]))
        probe = copy.copy(self.instance) if self.instance else AttendanceSettings()
        for key, value in attrs.items():
            setattr(probe, key, value)
        try:
            probe.full_clean(exclude=["updated_by"], validate_unique=False)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc
        return attrs


class WorkScheduleSerializer(serializers.ModelSerializer):
    work_days = serializers.ListField(child=serializers.IntegerField(min_value=0, max_value=6), allow_empty=True)
    employee = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceWorkSchedule
        fields = ["id", "user", "employee", "work_start", "work_end", "work_days", "late_grace_minutes",
                  "is_active", "note", "updated_at"]
        read_only_fields = ["id", "user", "employee", "updated_at"]

    def get_employee(self, obj) -> dict:
        return employee_brief(obj.user)

    def validate(self, attrs):
        start = attrs.get("work_start", getattr(self.instance, "work_start", None))
        end = attrs.get("work_end", getattr(self.instance, "work_end", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"work_end": "Окончание рабочего дня должно быть позже начала."})
        if "work_days" in attrs:
            validate_weekdays(attrs["work_days"])
            attrs["work_days"] = sorted(set(attrs["work_days"]))
        return attrs


class AdjustSerializer(serializers.Serializer):
    checked_in_at = serializers.DateTimeField()
    checked_out_at = serializers.DateTimeField(required=False, allow_null=True)
    reason = serializers.CharField(max_length=1000)
    location = serializers.PrimaryKeyRelatedField(queryset=AttendanceLocation.objects.all(), required=False,
                                                  allow_null=True)
    late_minutes = serializers.IntegerField(min_value=0, max_value=24 * 60, required=False, allow_null=True)


class ManualSessionSerializer(AdjustSerializer):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(is_active=True))


class AdjustmentSerializer(serializers.ModelSerializer):
    adjusted_by_name = serializers.SerializerMethodField()
    employee = serializers.SerializerMethodField()
    action_label = serializers.CharField(source="get_action_display", read_only=True)

    class Meta:
        model = AttendanceAdjustment
        fields = ["id", "session", "action", "action_label", "old_values", "new_values", "reason",
                  "adjusted_by", "adjusted_by_name", "employee", "created_at"]

    def get_adjusted_by_name(self, obj) -> str:
        return str(obj.adjusted_by)

    def get_employee(self, obj) -> dict:
        return employee_brief(obj.session.user)


class EventSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    location_name = serializers.CharField(source="location.name", default=None, read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceEvent
        fields = ["id", "session", "kind", "kind_label", "occurred_at", "location_name", "distance_m",
                  "accuracy_m", "created_by_name"]

    def get_created_by_name(self, obj) -> str | None:
        return str(obj.created_by) if obj.created_by_id else None


class AdminLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceAdminLog
        fields = ["id", "actor_name", "action", "object_type", "object_id", "changes", "created_at"]

    def get_actor_name(self, obj) -> str | None:
        return str(obj.actor) if obj.actor_id else None
