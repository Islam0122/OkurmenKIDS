"""Serializers of the «Параллельные занятия» API (parallel_session_views)."""
from __future__ import annotations

from rest_framework import serializers

from apps.users.models import Subject, Teacher

from .models import Attendance, Group, ParallelSession, ParallelSessionGroup, Room, Student


def _ref(obj, name=None) -> dict | None:
    if obj is None:
        return None
    return {"id": obj.pk, "name": name if name is not None else str(obj)}


class ParallelSessionGroupSerializer(serializers.ModelSerializer):
    group = serializers.SerializerMethodField()
    lesson_status = serializers.SerializerMethodField()
    students_count = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    program = serializers.SerializerMethodField()

    class Meta:
        model = ParallelSessionGroup
        fields = [
            "id", "group", "lesson", "lesson_status", "program", "status", "status_display", "students_count",
            "added_at", "removed_at", "removal_reason",
        ]

    def get_group(self, obj) -> dict:
        return {"id": obj.group_id, "name": obj.group.name}

    def get_lesson_status(self, obj) -> str | None:
        return obj.lesson.status if obj.lesson_id else None

    def get_program(self, obj) -> dict | None:
        if not obj.lesson_id or not obj.lesson.group_teacher_id:
            return None
        program = obj.lesson.group_teacher
        return {"id": program.pk, "subject": program.subject.name if program.subject_id else None}

    def get_students_count(self, obj) -> int:
        if obj.students_count is not None:
            return obj.students_count
        counts = self.context.get("student_counts")
        if counts is not None:
            return counts.get(obj.group_id, 0)
        return Student.objects.filter(group_id=obj.group_id, status=Student.Status.ACTIVE).count()


class ParallelSessionSerializer(serializers.ModelSerializer):
    """Read shape of a session: the shared data, its groups (with removed
    ones as history), the totals and what the requesting user may do."""

    teacher = serializers.SerializerMethodField()
    room = serializers.SerializerMethodField()
    subject = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    groups = serializers.SerializerMethodField()
    groups_count = serializers.SerializerMethodField()
    students_count = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    completed_by_name = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()

    class Meta:
        model = ParallelSession
        fields = [
            "id", "date", "start_time", "end_time", "teacher", "room", "subject", "topic", "description", "notes",
            "youtube_url", "presentation_urls", "status", "status_display", "cancellation_reason",
            "groups", "groups_count", "students_count", "created_by_name", "completed_at", "completed_by_name",
            "cancelled_at", "created_at", "updated_at", "capabilities",
        ]

    def _participants(self, obj) -> list[ParallelSessionGroup]:
        cache = getattr(obj, "_participants_cache", None)
        if cache is None:
            cache = list(obj.participants.select_related("group", "lesson__group_teacher__subject")
                         .order_by("status", "group__name"))
            obj._participants_cache = cache
        return cache

    def _active(self, obj):
        return [p for p in self._participants(obj) if p.status == ParallelSessionGroup.Status.ACTIVE]

    def get_teacher(self, obj) -> dict:
        return {"id": obj.teacher_id, "name": str(obj.teacher), "color": obj.teacher.color}

    def get_room(self, obj) -> dict:
        return _ref(obj.room, obj.room.name)

    def get_subject(self, obj) -> dict | None:
        return _ref(obj.subject, obj.subject.name if obj.subject_id else None) if obj.subject_id else None

    def get_groups(self, obj) -> list[dict]:
        return ParallelSessionGroupSerializer(self._participants(obj), many=True, context=self.context).data

    def get_groups_count(self, obj) -> int:
        return len(self._active(obj))

    def get_students_count(self, obj) -> int:
        serializer = ParallelSessionGroupSerializer(context=self.context)
        return sum(serializer.get_students_count(p) for p in self._active(obj))

    def get_created_by_name(self, obj) -> str | None:
        return str(obj.created_by) if obj.created_by_id else None

    def get_completed_by_name(self, obj) -> str | None:
        return str(obj.completed_by) if obj.completed_by_id else None

    def get_capabilities(self, obj) -> dict:
        from .parallel_session_views import capabilities

        request = self.context.get("request")
        return capabilities(request.user, obj) if request else {}


class ParallelSessionWriteSerializer(serializers.Serializer):
    """Create / edit input. `groups` — any number of group ids (no limit);
    `programs` — optional {group id: program id} when a group has several
    programs and no `subject` decides which one the lesson belongs to."""

    teacher = serializers.PrimaryKeyRelatedField(queryset=Teacher.objects.select_related("user"))
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all())
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)
    date = serializers.DateField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    groups = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)
    programs = serializers.DictField(child=serializers.IntegerField(min_value=1), required=False)
    topic = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    youtube_url = serializers.URLField(required=False, allow_blank=True, default="")
    presentation_urls = serializers.ListField(child=serializers.URLField(), required=False, default=list)

    def validate_groups(self, value):
        duplicates = sorted({v for v in value if value.count(v) > 1})
        if duplicates:
            raise serializers.ValidationError(f"Группа указана несколько раз: {duplicates}.")
        groups = {g.pk: g for g in Group.objects.filter(pk__in=value)}
        missing = [v for v in value if v not in groups]
        if missing:
            raise serializers.ValidationError(f"Группы не найдены: {missing}.")
        return [groups[v] for v in value]

    def validate_programs(self, value):
        try:
            return {int(k): v for k, v in value.items()}
        except (TypeError, ValueError):
            raise serializers.ValidationError("Ключи — id групп.")

    def validate(self, attrs):
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError({"end_time": "Время окончания должно быть позже времени начала."})
        return attrs


class ParallelSessionUpdateSerializer(serializers.Serializer):
    teacher = serializers.PrimaryKeyRelatedField(queryset=Teacher.objects.select_related("user"), required=False)
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all(), required=False)
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)
    date = serializers.DateField(required=False)
    start_time = serializers.TimeField(required=False)
    end_time = serializers.TimeField(required=False)
    topic = serializers.CharField(max_length=255, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    youtube_url = serializers.URLField(required=False, allow_blank=True)
    presentation_urls = serializers.ListField(child=serializers.URLField(), required=False)


class ConflictCheckSerializer(serializers.Serializer):
    teacher = serializers.PrimaryKeyRelatedField(queryset=Teacher.objects.select_related("user"), required=False,
                                                 allow_null=True)
    room = serializers.PrimaryKeyRelatedField(queryset=Room.objects.all(), required=False, allow_null=True)
    date = serializers.DateField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    groups = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, default=list)
    session = serializers.IntegerField(required=False, allow_null=True, help_text="Редактируемое занятие (исключается).")


class AddGroupSerializer(serializers.Serializer):
    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all())
    program = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class RemoveGroupSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class ParallelSessionCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class SessionAttendanceItemSerializer(serializers.Serializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    status = serializers.ChoiceField(choices=Attendance.Status.choices)
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class SessionAttendanceSerializer(serializers.Serializer):
    """One group's marks: {"group": id, "entries": [{student, status, comment}]}."""

    group = serializers.IntegerField(min_value=1)
    entries = SessionAttendanceItemSerializer(many=True)


class SharedHomeworkSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    deadline = serializers.DateField(required=False, allow_null=True)
    groups = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False, default=list,
                                   help_text="Пусто — всем группам занятия; иначе только этим (ДЗ для отдельных групп).")
