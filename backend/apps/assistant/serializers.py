"""Request bodies of the Assistant Workspace API. Validation of the business
rules themselves (statuses, conflicts, capacity) stays in the academy
services these feed — these only parse and resolve ids."""
from __future__ import annotations

from rest_framework import serializers

from apps.academy.models import Attendance, Course, Group, Room, Student, StudentStatusEvent
from apps.users.models import Subject, Teacher

# «Пауза» is not a departure reason: it routes the same modal to
# services.student_status.pause_student instead of deactivate_student.
PAUSE = "pause"


class SlotSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    day = serializers.CharField()
    start = serializers.CharField()
    end = serializers.CharField()
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.filter(is_active=True), required=False, allow_null=True)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        room = value.get("room")
        value["room"] = room.pk if room is not None else None
        return value


class ProgramSerializer(serializers.Serializer):
    program = serializers.IntegerField(required=False, allow_null=True, help_text="Существующая программа (GroupTeacher) группы.")
    teacher = serializers.PrimaryKeyRelatedField(queryset=Teacher.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all())
    slots = SlotSerializer(many=True)


class GroupCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    course = serializers.PrimaryKeyRelatedField(queryset=Course.objects.all())
    start_date = serializers.DateField()
    end_date = serializers.DateField(required=False, allow_null=True)
    max_students = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    programs = ProgramSerializer(many=True, required=False, default=list)
    students = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all(), many=True, required=False, default=list)
    generate_lessons = serializers.BooleanField(required=False, default=False)


class GroupUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False, allow_null=True)
    max_students = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    description = serializers.CharField(required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=Group.Status.choices, required=False)


class StudentIdsSerializer(serializers.Serializer):
    students = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all(), many=True, allow_empty=False)
    event_date = serializers.DateField(required=False, allow_null=True)
    comment = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)


class StudentCreateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    parent_phone = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all())
    enrollment_date = serializers.DateField(required=False, allow_null=True)


class StudentUpdateSerializer(serializers.Serializer):
    """Contacts only — the group and status change through their own actions."""

    first_name = serializers.CharField(max_length=100, required=False)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    parent_phone = serializers.CharField(max_length=30, required=False, allow_blank=True)
    enrollment_date = serializers.DateField(required=False, allow_null=True)


class DeactivateSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=[(PAUSE, "Пауза"), *StudentStatusEvent.Reason.choices])
    event_date = serializers.DateField(required=False, allow_null=True)
    expected_return_date = serializers.DateField(required=False, allow_null=True)
    comment = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)


class ActivateSerializer(serializers.Serializer):
    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all(), required=False, allow_null=True)
    event_date = serializers.DateField(required=False, allow_null=True)
    comment = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)


class TransferSerializer(serializers.Serializer):
    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all())
    event_date = serializers.DateField(required=False, allow_null=True)
    comment = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)


class BulkActionSerializer(serializers.Serializer):
    ACTIONS = ("transfer", "add_to_group", "deactivate", "activate")

    action = serializers.ChoiceField(choices=[(a, a) for a in ACTIONS])
    students = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all(), many=True, allow_empty=False)
    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all(), required=False, allow_null=True)
    reason = serializers.ChoiceField(choices=[(PAUSE, "Пауза"), *StudentStatusEvent.Reason.choices], required=False)
    event_date = serializers.DateField(required=False, allow_null=True)
    comment = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)

    def validate(self, attrs):
        if attrs["action"] in ("transfer", "add_to_group") and not attrs.get("group"):
            raise serializers.ValidationError({"group": "Выберите группу."})
        if attrs["action"] == "deactivate" and not attrs.get("reason"):
            raise serializers.ValidationError({"reason": "Выберите причину."})
        return attrs


class LessonMoveSerializer(serializers.Serializer):
    date = serializers.DateField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()


class LessonCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=255)
    reschedule = serializers.BooleanField(required=False, default=True)


class AttendanceEntrySerializer(serializers.Serializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    status = serializers.ChoiceField(choices=Attendance.Status.choices)
    comment = serializers.CharField(required=False, allow_blank=True, default="", max_length=255)


class AwardAddSerializer(serializers.Serializer):
    evaluation = serializers.IntegerField()


class GenerateScholarshipSerializer(serializers.Serializer):
    award_day = serializers.IntegerField(min_value=1, max_value=31, required=False, allow_null=True)
    award_date = serializers.DateField(required=False, allow_null=True)
