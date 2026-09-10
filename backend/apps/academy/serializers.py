from __future__ import annotations

from rest_framework import serializers

from apps.users.models import Teacher, User
from apps.users.serializers import SubjectSerializer

from .constants import WEEKDAY_CODES, WEEKDAY_LABELS_FULL
from .models import (
    Attendance,
    Course,
    CourseLessonPlan,
    Group,
    Homework,
    HomeworkResult,
    Lesson,
    Room,
    Student,
)
from .services.room_conflicts import find_room_schedule_conflict


def _is_teacher(user) -> bool:
    return bool(user and user.is_authenticated and user.role == User.Role.TEACHER)


def _teacher_group_ids(user):
    teacher = getattr(user, "teacher_profile", None)
    if teacher is None:
        return Group.objects.none().values_list("id", flat=True)
    return Group.objects.filter(teacher=teacher).values_list("id", flat=True)


class _RequestAwareSerializer(serializers.ModelSerializer):
    """Base for serializers that need to know the requesting user to scope fields."""

    def _request_user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)


# ---------------------------------------------------------------------------
# Course catalogue
# ---------------------------------------------------------------------------

class CourseSerializer(serializers.ModelSerializer):
    subjects_detail = SubjectSerializer(source="subjects", many=True, read_only=True)
    lesson_plans_count = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id",
            "name",
            "count_lesson",
            "subjects",
            "subjects_detail",
            "lesson_plans_count",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_lesson_plans_count(self, obj: Course) -> int:
        annotated = getattr(obj, "_lesson_plans_count", None)
        return annotated if annotated is not None else obj.lesson_plans.count()


class CourseLessonPlanSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="subject.name", read_only=True)
    course_name = serializers.CharField(source="course.name", read_only=True)

    class Meta:
        model = CourseLessonPlan
        fields = [
            "id",
            "course",
            "course_name",
            "lesson_number",
            "subject",
            "subject_name",
            "topic",
            "description",
            "youtube_url",
            "presentation_urls",
            "homework_title",
            "homework_description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_presentation_urls(self, value):
        if not value:
            return []
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise serializers.ValidationError("Ожидается список ссылок (строк).")
        return value

    def validate(self, attrs):
        course = attrs.get("course", getattr(self.instance, "course", None))
        lesson_number = attrs.get("lesson_number", getattr(self.instance, "lesson_number", None))
        subject = attrs.get("subject", getattr(self.instance, "subject", None))

        if course and lesson_number and lesson_number > course.count_lesson:
            raise serializers.ValidationError(
                {"lesson_number": f"Номер занятия не может превышать количество занятий курса ({course.count_lesson})."}
            )

        if course and subject and not course.subjects.filter(pk=subject.pk).exists():
            raise serializers.ValidationError({"subject": "Предмет должен входить в состав выбранного курса."})

        duplicates = CourseLessonPlan.objects.filter(course=course, lesson_number=lesson_number)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if course and lesson_number and duplicates.exists():
            raise serializers.ValidationError(
                {"lesson_number": "План с таким номером занятия для этого курса уже существует."}
            )

        return attrs


# ---------------------------------------------------------------------------
# Rooms & students
# ---------------------------------------------------------------------------

class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ["id", "name", "capacity", "description", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class RoomAvailabilityRequestSerializer(serializers.Serializer):
    """Query params for `GET /rooms/available/`."""

    date = serializers.DateField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()

    def validate(self, attrs):
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError({"end_time": "Время окончания должно быть позже времени начала."})
        return attrs


class RoomOccupancySerializer(serializers.Serializer):
    """One occupying Lesson, for the `occupied` list of `GET /rooms/available/`."""

    room = serializers.IntegerField()
    room_name = serializers.CharField()
    lesson = serializers.IntegerField()
    group = serializers.IntegerField(allow_null=True)
    group_name = serializers.CharField(allow_null=True)
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()


class RoomAvailabilitySerializer(serializers.Serializer):
    date = serializers.DateField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    available = RoomSerializer(many=True)
    occupied = RoomOccupancySerializer(many=True)


class StudentSerializer(_RequestAwareSerializer):
    full_name = serializers.SerializerMethodField()
    group_name = serializers.CharField(source="group.name", read_only=True, default=None)

    class Meta:
        model = Student
        fields = [
            "id",
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "parent_phone",
            "group",
            "group_name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self._request_user()
        if _is_teacher(user):
            self.fields["group"].queryset = Group.objects.filter(id__in=_teacher_group_ids(user))

    def get_full_name(self, obj: Student) -> str:
        return f"{obj.first_name} {obj.last_name}".strip()


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

class GroupSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source="teacher.__str__", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True, default=None)
    course_name = serializers.CharField(source="course.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    students_count = serializers.SerializerMethodField()
    students = serializers.PrimaryKeyRelatedField(
        queryset=Student.objects.all(),
        many=True,
        required=False,
        write_only=True,
        help_text="ID студентов, которых нужно закрепить за группой (заменяет текущий список).",
    )

    class Meta:
        model = Group
        fields = [
            "id",
            "name",
            "course",
            "course_name",
            "teacher",
            "teacher_name",
            "room",
            "room_name",
            "start_date",
            "end_date",
            "start_time",
            "end_time",
            "days_of_week",
            "students",
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
        # Only active teachers can be assigned to a group.
        self.fields["teacher"].queryset = Teacher.objects.filter(is_active=True)

    def get_students_count(self, obj: Group) -> int:
        annotated = getattr(obj, "active_students_count", None)
        return annotated if annotated is not None else obj.students_count

    def validate(self, attrs):
        start_date = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end_date = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if end_date and start_date and end_date < start_date:
            raise serializers.ValidationError({"end_date": "Дата окончания не может быть раньше даты начала."})

        start_time = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end_time = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError({"end_time": "Время окончания должно быть позже времени начала."})

        days_of_week = attrs.get("days_of_week", getattr(self.instance, "days_of_week", None))
        if not days_of_week:
            raise serializers.ValidationError({"days_of_week": "Укажите хотя бы один день недели."})

        room = attrs.get("room", getattr(self.instance, "room", None))
        max_students = attrs.get("max_students", getattr(self.instance, "max_students", None))
        if room is not None and room.capacity and max_students and max_students > room.capacity:
            raise serializers.ValidationError(
                {"max_students": f"Максимум студентов превышает вместимость аудитории «{room.name}» ({room.capacity})."}
            )

        if room is not None and days_of_week and start_time and end_time and start_date:
            conflict = find_room_schedule_conflict(
                room=room,
                days_of_week=days_of_week,
                start_time=start_time,
                end_time=end_time,
                start_date=start_date,
                end_date=end_date,
                exclude_group_id=getattr(self.instance, "pk", None),
            )
            if conflict is not None:
                raise serializers.ValidationError(
                    {"room": f"Аудитория «{room.name}» уже занята в это время группой «{conflict.name}»."}
                )

        return attrs

    def create(self, validated_data):
        students = validated_data.pop("students", None)
        group = super().create(validated_data)
        if students:
            Student.objects.filter(id__in=[s.id for s in students]).update(group=group)
        return group

    def update(self, instance, validated_data):
        students = validated_data.pop("students", None)
        group = super().update(instance, validated_data)
        if students is not None:
            selected_ids = [s.id for s in students]
            Student.objects.filter(group=group).exclude(id__in=selected_ids).update(group=None)
            Student.objects.filter(id__in=selected_ids).update(group=group)
        return group


class GenerateLessonsResponseSerializer(serializers.Serializer):
    created_count = serializers.IntegerField()
    first_lesson = serializers.IntegerField(allow_null=True)
    last_lesson = serializers.IntegerField(allow_null=True)
    first_date = serializers.DateField(allow_null=True)
    last_date = serializers.DateField(allow_null=True)


# ---------------------------------------------------------------------------
# Lessons
# ---------------------------------------------------------------------------

class LessonSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True, default=None)
    subject_name = serializers.CharField(source="subject.name", read_only=True, default=None)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Lesson
        fields = [
            "id",
            "group",
            "group_name",
            "plan",
            "lesson_number",
            "date",
            "start_time",
            "end_time",
            "room",
            "room_name",
            "subject",
            "subject_name",
            "topic",
            "description",
            "youtube_url",
            "presentation_urls",
            "status",
            "status_display",
            "cancellation_reason",
            "created_at",
            "updated_at",
        ]
        # Lessons are only ever created by the generator — the API only
        # updates content/status/scheduling on an already-generated lesson.
        read_only_fields = ["id", "group", "plan", "lesson_number", "created_at", "updated_at"]

    def validate(self, attrs):
        start_time = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end_time = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError({"end_time": "Время окончания должно быть позже времени начала."})
        return attrs


class GroupScheduleLessonSerializer(LessonSerializer):
    """LessonSerializer plus the lesson's weekday — for `GET /groups/{id}/schedule/`,
    so the frontend can group a group's lessons "Пн / Чт / Пт" without redoing
    the mon/tue/... mapping itself."""

    weekday = serializers.SerializerMethodField()
    weekday_label = serializers.SerializerMethodField()

    class Meta(LessonSerializer.Meta):
        fields = LessonSerializer.Meta.fields + ["weekday", "weekday_label"]

    def get_weekday(self, obj: Lesson) -> str:
        return WEEKDAY_CODES[obj.date.weekday()]

    def get_weekday_label(self, obj: Lesson) -> str:
        return WEEKDAY_LABELS_FULL[WEEKDAY_CODES[obj.date.weekday()]]


class GroupScheduleSerializer(serializers.Serializer):
    """Response of `GET /groups/{id}/schedule/`: the group itself plus its
    concrete, dated Lessons — the Trainer-facing "schedule of this group"."""

    group = GroupSerializer()
    lessons = GroupScheduleLessonSerializer(many=True)


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

class AttendanceSerializer(_RequestAwareSerializer):
    student_name = serializers.CharField(source="student.__str__", read_only=True)
    group_name = serializers.CharField(source="lesson.group.name", read_only=True)
    lesson_date = serializers.DateField(source="lesson.date", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Attendance
        fields = [
            "id",
            "student",
            "student_name",
            "lesson",
            "group_name",
            "lesson_date",
            "status",
            "status_display",
            "comment",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self._request_user()
        if _is_teacher(user):
            group_ids = _teacher_group_ids(user)
            self.fields["lesson"].queryset = Lesson.objects.filter(group_id__in=group_ids)
            self.fields["student"].queryset = Student.objects.filter(group_id__in=group_ids)

    def validate(self, attrs):
        student = attrs.get("student", getattr(self.instance, "student", None))
        lesson = attrs.get("lesson", getattr(self.instance, "lesson", None))

        if student.group_id != lesson.group_id:
            raise serializers.ValidationError({"student": "Студент не принадлежит группе этого занятия."})

        duplicates = Attendance.objects.filter(student=student, lesson=lesson)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("Посещаемость для этого студента на этом занятии уже отмечена.")

        return attrs


class BulkAttendanceItemSerializer(serializers.Serializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    status = serializers.ChoiceField(choices=Attendance.Status.choices)
    comment = serializers.CharField(required=False, allow_blank=True, default="")


# ---------------------------------------------------------------------------
# Homework & results
# ---------------------------------------------------------------------------

class HomeworkSerializer(_RequestAwareSerializer):
    group_name = serializers.CharField(source="lesson.group.name", read_only=True)
    lesson_date = serializers.DateField(source="lesson.date", read_only=True)
    results_count = serializers.SerializerMethodField()

    class Meta:
        model = Homework
        fields = [
            "id",
            "lesson",
            "group_name",
            "lesson_date",
            "title",
            "description",
            "deadline",
            "results_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self._request_user()
        if _is_teacher(user):
            self.fields["lesson"].queryset = Lesson.objects.filter(group_id__in=_teacher_group_ids(user))

    def get_results_count(self, obj: Homework) -> int:
        return obj.results.count()


class HomeworkResultSerializer(_RequestAwareSerializer):
    student_name = serializers.CharField(source="student.__str__", read_only=True)
    homework_title = serializers.CharField(source="homework.title", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = HomeworkResult
        fields = [
            "id",
            "homework",
            "homework_title",
            "student",
            "student_name",
            "status",
            "status_display",
            "score",
            "comment",
            "submitted_at",
            "checked_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self._request_user()
        if _is_teacher(user):
            group_ids = _teacher_group_ids(user)
            self.fields["homework"].queryset = Homework.objects.filter(lesson__group_id__in=group_ids)
            self.fields["student"].queryset = Student.objects.filter(group_id__in=group_ids)

    def validate(self, attrs):
        student = attrs.get("student", getattr(self.instance, "student", None))
        homework = attrs.get("homework", getattr(self.instance, "homework", None))

        if student.group_id != homework.lesson.group_id:
            raise serializers.ValidationError({"student": "Студент не принадлежит группе этого занятия."})

        duplicates = HomeworkResult.objects.filter(student=student, homework=homework)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError("Результат для этого студента по этому заданию уже существует.")

        return attrs


class BulkHomeworkResultItemSerializer(serializers.Serializer):
    student = serializers.PrimaryKeyRelatedField(queryset=Student.objects.all())
    status = serializers.ChoiceField(choices=HomeworkResult.Status.choices, default=HomeworkResult.Status.SUBMITTED)
    score = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=10)
    comment = serializers.CharField(required=False, allow_blank=True, default="")



# ---------------------------------------------------------------------------
# Analytics — read-only, computed on demand by apps.academy.services.analytics.
# Nothing here maps to a model: AnalyticsService returns plain dicts shaped
# exactly like these serializers, never a persisted KPI row.
# ---------------------------------------------------------------------------

class AnalyticsQuerySerializer(serializers.Serializer):
    """Query params for `GET /analytics/dashboard/`."""

    date_from = serializers.DateField()
    date_to = serializers.DateField()
    teacher = serializers.PrimaryKeyRelatedField(queryset=Teacher.objects.all(), required=False, allow_null=True)
    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all(), required=False, allow_null=True)

    def validate(self, attrs):
        if attrs["date_to"] < attrs["date_from"]:
            raise serializers.ValidationError({"date_to": "Дата окончания периода не может быть раньше даты начала."})
        return attrs


class AnalyticsOverviewSerializer(serializers.Serializer):
    groups = serializers.IntegerField()
    teachers = serializers.IntegerField()
    students = serializers.IntegerField()
    lessons = serializers.IntegerField()
    attendance_percent = serializers.FloatField()
    homework_completion_percent = serializers.FloatField()
    average_score = serializers.FloatField()


class AnalyticsLessonStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    completed = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    planned = serializers.IntegerField()
    completion_rate = serializers.FloatField()


class AnalyticsTimeSeriesPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    percent = serializers.FloatField()


class AnalyticsAttendanceStatsSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    present = serializers.IntegerField()
    absent = serializers.IntegerField()
    late = serializers.IntegerField()
    excused = serializers.IntegerField()
    percent = serializers.FloatField()
    by_date = AnalyticsTimeSeriesPointSerializer(many=True)


class AnalyticsHomeworkStatsSerializer(serializers.Serializer):
    total_homeworks = serializers.IntegerField()
    total_results = serializers.IntegerField()
    submitted = serializers.IntegerField()
    checked = serializers.IntegerField()
    late = serializers.IntegerField()
    not_submitted = serializers.IntegerField()
    completed = serializers.IntegerField()
    completion_percent = serializers.FloatField()
    average_score = serializers.FloatField()
    by_date = AnalyticsTimeSeriesPointSerializer(many=True)


class AnalyticsGroupRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    teacher = serializers.CharField()
    students = serializers.IntegerField()
    lessons = serializers.IntegerField()
    completed_lessons = serializers.IntegerField()
    cancelled_lessons = serializers.IntegerField()
    planned_lessons = serializers.IntegerField()
    attendance_percent = serializers.FloatField()
    homework_completion_percent = serializers.FloatField()
    average_score = serializers.FloatField()
    status = serializers.CharField()
    status_display = serializers.CharField()


class AnalyticsTeacherRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    groups = serializers.IntegerField()
    students = serializers.IntegerField()
    lessons = serializers.IntegerField()
    attendance_percent = serializers.FloatField()
    homework_completion_percent = serializers.FloatField()
    average_score = serializers.FloatField()


class AnalyticsStudentRowSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    group = serializers.CharField(allow_null=True)
    lessons = serializers.IntegerField()
    attendance_percent = serializers.FloatField()
    homework_completion_percent = serializers.FloatField()
    average_score = serializers.FloatField()


class AnalyticsLessonsByStatusSerializer(serializers.Serializer):
    status = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()


class AnalyticsGroupPerformanceSerializer(serializers.Serializer):
    group = serializers.CharField()
    attendance_percent = serializers.FloatField()


class AnalyticsTeacherPerformanceSerializer(serializers.Serializer):
    teacher = serializers.CharField()
    attendance_percent = serializers.FloatField()


class AnalyticsStudentsByGroupSerializer(serializers.Serializer):
    group = serializers.CharField()
    students = serializers.IntegerField()


class AnalyticsChartsSerializer(serializers.Serializer):
    attendance_over_time = AnalyticsTimeSeriesPointSerializer(many=True)
    lessons_by_status = AnalyticsLessonsByStatusSerializer(many=True)
    students_by_group = AnalyticsStudentsByGroupSerializer(many=True)
    homework_completion_over_time = AnalyticsTimeSeriesPointSerializer(many=True)
    teacher_performance = AnalyticsTeacherPerformanceSerializer(many=True)
    group_performance = AnalyticsGroupPerformanceSerializer(many=True)


class AnalyticsPeriodSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class AnalyticsFiltersSerializer(serializers.Serializer):
    teacher_id = serializers.IntegerField(allow_null=True)
    group_id = serializers.IntegerField(allow_null=True)


class AnalyticsDashboardSerializer(serializers.Serializer):
    """The full payload of `GET /analytics/dashboard/` — exactly what
    `AnalyticsService.get_dashboard()` returns, computed fresh on every call."""

    period = AnalyticsPeriodSerializer()
    filters = AnalyticsFiltersSerializer()
    overview = AnalyticsOverviewSerializer()
    lessons = AnalyticsLessonStatsSerializer()
    attendance = AnalyticsAttendanceStatsSerializer()
    homework = AnalyticsHomeworkStatsSerializer()
    groups = AnalyticsGroupRowSerializer(many=True)
    teachers = AnalyticsTeacherRowSerializer(many=True)
    top_students = AnalyticsStudentRowSerializer(many=True)
    charts = AnalyticsChartsSerializer()
