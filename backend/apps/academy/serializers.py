from __future__ import annotations

from rest_framework import serializers

from apps.users.models import Teacher, User

from .models import KPI, Attendance, Group, Homework, Room, Schedule, Student
from .services import calculate_attendance_stats, calculate_homework_stats


def _teacher_group_ids(user) -> list[int]:
    teacher = getattr(user, "teacher_profile", None)
    if teacher is None:
        return []
    return list(Group.objects.filter(teacher=teacher).values_list("id", flat=True))


class _TeacherScopedSerializer(serializers.ModelSerializer):
    """Restricts `group`/`student` choice fields to the requesting teacher's own groups.

    Admin keeps the full queryset. This turns "assign to someone else's
    group" into a normal 400 validation error instead of a silent security
    hole, without needing extra permission checks for the create path.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or user.role != User.Role.TEACHER:
            return

        group_ids = _teacher_group_ids(user)
        if "group" in self.fields:
            self.fields["group"].queryset = Group.objects.filter(id__in=group_ids)
        if "student" in self.fields:
            self.fields["student"].queryset = Student.objects.filter(group_id__in=group_ids)


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = [
            "id",
            "name",
            "capacity",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class StudentSerializer(_TeacherScopedSerializer):
    full_name = serializers.SerializerMethodField()
    group_name = serializers.CharField(source="group.name", read_only=True, default=None)

    class Meta:
        model = Student
        fields = [
            "id",
            "first_name",
            "last_name",
            "full_name",
            "group",
            "group_name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_full_name(self, obj: Student) -> str:
        return f"{obj.first_name} {obj.last_name}".strip()


class GroupSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source="teacher.__str__", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    students_count = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = [
            "id",
            "name",
            "teacher",
            "teacher_name",
            "room",
            "room_name",
            "start_date",
            "end_date",
            "start_time",
            "end_time",
            "days_of_week",
            "students_count",
            "max_students",
            "status",
            "status_display",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only active teachers can be assigned to a group — this is what
        # keeps "assign a non-existent/inactive trainer" out of reach
        # without extra validate() plumbing.
        self.fields["teacher"].queryset = Teacher.objects.filter(is_active=True)

    def get_students_count(self, obj: Group) -> int:
        annotated = getattr(obj, "active_students_count", None)
        return annotated if annotated is not None else obj.students_count

    def validate(self, attrs):
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end_date = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if end_date and start_date and end_date < start_date:
            raise serializers.ValidationError(
                {"end_date": "Дата окончания не может быть раньше даты начала."}
            )

        start_time = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end_time = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError(
                {"end_time": "Время окончания должно быть позже времени начала."}
            )

        return attrs


class ScheduleSerializer(_TeacherScopedSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True, default=None)

    class Meta:
        model = Schedule
        fields = [
            "id",
            "group",
            "group_name",
            "date",
            "start_time",
            "end_time",
            "room",
            "room_name",
            "is_cancelled",
            "cancellation_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        start_time = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end_time = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError(
                {"end_time": "Время окончания должно быть позже времени начала."}
            )

        room = attrs.get("room", getattr(self.instance, "room", None))
        date = attrs.get("date", getattr(self.instance, "date", None))
        is_cancelled = attrs.get("is_cancelled", getattr(self.instance, "is_cancelled", False))

        if room is not None and self.instance is None and not room.is_active:
            raise serializers.ValidationError(
                {"room": "Нельзя назначить неактивную аудиторию для нового занятия."}
            )

        if room is not None and date and start_time and end_time and not is_cancelled:
            conflicts = Schedule.objects.filter(
                room=room, date=date, is_cancelled=False
            ).exclude(start_time__gte=end_time).exclude(end_time__lte=start_time)
            if self.instance is not None:
                conflicts = conflicts.exclude(pk=self.instance.pk)
            if conflicts.exists():
                raise serializers.ValidationError(
                    {"room": "В это время аудитория уже занята другим занятием."}
                )

        return attrs


class AttendanceSerializer(_TeacherScopedSerializer):
    student_name = serializers.CharField(source="student.__str__", read_only=True)
    group_name = serializers.CharField(source="group.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Attendance
        fields = [
            "id",
            "student",
            "student_name",
            "group",
            "group_name",
            "date",
            "status",
            "status_display",
            "comment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        student = attrs.get("student", getattr(self.instance, "student", None))
        group = attrs.get("group", getattr(self.instance, "group", None))
        date = attrs.get("date", getattr(self.instance, "date", None))

        if student.group_id != group.id:
            raise serializers.ValidationError(
                {"student": "Студент не принадлежит выбранной группе."}
            )

        duplicates = Attendance.objects.filter(student=student, group=group, date=date)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError(
                "Запись посещаемости для этого студента на эту дату уже существует."
            )

        return attrs


class HomeworkSerializer(_TeacherScopedSerializer):
    student_name = serializers.CharField(source="student.__str__", read_only=True)
    group_name = serializers.CharField(source="group.name", read_only=True)

    class Meta:
        model = Homework
        fields = [
            "id",
            "student",
            "student_name",
            "group",
            "group_name",
            "date",
            "score",
            "comment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        student = attrs.get("student", getattr(self.instance, "student", None))
        group = attrs.get("group", getattr(self.instance, "group", None))
        date = attrs.get("date", getattr(self.instance, "date", None))

        if student.group_id != group.id:
            raise serializers.ValidationError(
                {"student": "Студент не принадлежит выбранной группе."}
            )

        duplicates = Homework.objects.filter(student=student, group=group, date=date)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError(
                "Результат домашнего задания для этого студента на эту дату уже существует."
            )

        return attrs


class KPISerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.__str__", read_only=True)
    group_name = serializers.CharField(source="group.name", read_only=True)
    attendance = serializers.SerializerMethodField()
    homework = serializers.SerializerMethodField()

    class Meta:
        model = KPI
        fields = [
            "id",
            "student",
            "student_name",
            "group",
            "group_name",
            "date_from",
            "date_to",
            "attendance",
            "homework",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_attendance(self, obj: KPI) -> dict:
        return calculate_attendance_stats(obj.student_id, obj.group_id, obj.date_from, obj.date_to)

    def get_homework(self, obj: KPI) -> dict:
        return calculate_homework_stats(obj.student_id, obj.group_id, obj.date_from, obj.date_to)
