from __future__ import annotations

from rest_framework import serializers

from apps.users.models import Subject, Teacher, User
from apps.users.serializers import SubjectSerializer, TeacherSerializer

from .constants import WEEKDAY_CODES, WEEKDAY_LABELS_FULL
from .services.analytics import PERIOD_CHOICES
from .models import (
    Attendance,
    Course,
    CourseLessonPlan,
    Group,
    GroupSchedule,
    GroupTeacher,
    GroupTeacherLessonPlan,
    Homework,
    HomeworkResult,
    Lesson,
    Room,
    Student,
)
from .services.group_schedule_conflicts import (
    find_group_teacher_conflict,
    find_schedule_room_conflict,
    find_schedule_teacher_conflict,
)
from .services.room_conflicts import find_room_schedule_conflict


def _is_teacher(user) -> bool:
    return bool(user and user.is_authenticated and user.role == User.Role.TEACHER)


def _teacher_group_ids(user):
    teacher = getattr(user, "teacher_profile", None)
    if teacher is None:
        return Group.objects.none().values_list("id", flat=True)
    return Group.objects.for_teacher(teacher).values_list("id", flat=True)


def _teacher_owned_lessons(user):
    """Only the Lessons `user`'s Teacher profile actually gives — see
    models.LessonQuerySet.for_teacher. Used to scope the `lesson`/`homework`
    FK choices offered to a Teacher on Attendance/Homework/HomeworkResult:
    a Group's other Teaching Programs (models.GroupTeacher) belong to other
    teachers, even within the same Group."""
    teacher = getattr(user, "teacher_profile", None)
    if teacher is None:
        return Lesson.objects.none()
    return Lesson.objects.for_teacher(teacher)


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


class TeacherAvailabilityRequestSerializer(serializers.Serializer):
    """Query params for `GET /teacher-availability/`."""

    date = serializers.DateField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()

    def validate(self, attrs):
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError({"end_time": "Время окончания должно быть позже времени начала."})
        return attrs


class TeacherOccupancySerializer(serializers.Serializer):
    """One occupying Lesson, for the `occupied` list of `GET /teacher-availability/`."""

    teacher = serializers.IntegerField()
    teacher_name = serializers.CharField()
    lesson = serializers.IntegerField()
    group = serializers.IntegerField(allow_null=True)
    group_name = serializers.CharField(allow_null=True)
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()


class TeacherAvailabilitySerializer(serializers.Serializer):
    date = serializers.DateField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    available = TeacherSerializer(many=True)
    occupied = TeacherOccupancySerializer(many=True)


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

class GroupScheduleSlotSerializer(serializers.ModelSerializer):
    """One recurring weekly slot of a Group's schedule — see models.GroupSchedule.

    Named "...Slot..." on purpose: `GroupScheduleSerializer` below is an
    unrelated, pre-existing name — the response payload of
    `GET /groups/{id}/schedule/` (the group's concrete, dated Lessons).
    """

    teacher_name = serializers.CharField(source="teacher.__str__", read_only=True)
    subject_name = serializers.CharField(source="subject.name", read_only=True, default=None)
    room_name = serializers.CharField(source="room.name", read_only=True, default=None)
    day_of_week_label = serializers.CharField(source="get_day_of_week_display", read_only=True)

    class Meta:
        model = GroupSchedule
        fields = [
            "id",
            "group",
            "teacher",
            "teacher_name",
            "subject",
            "subject_name",
            "day_of_week",
            "day_of_week_label",
            "start_time",
            "end_time",
            "room",
            "room_name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = Teacher.objects.filter(is_active=True)
        self.fields["subject"].queryset = Subject.objects.filter(is_active=True)

    def validate(self, attrs):
        start_time = attrs.get("start_time", getattr(self.instance, "start_time", None))
        end_time = attrs.get("end_time", getattr(self.instance, "end_time", None))
        if start_time and end_time and end_time <= start_time:
            raise serializers.ValidationError({"end_time": "Время окончания должно быть позже времени начала."})

        teacher = attrs.get("teacher", getattr(self.instance, "teacher", None))
        subject = attrs.get("subject", getattr(self.instance, "subject", None))
        room = attrs.get("room", getattr(self.instance, "room", None))
        day_of_week = attrs.get("day_of_week", getattr(self.instance, "day_of_week", None))
        exclude_id = getattr(self.instance, "pk", None)

        if teacher and not teacher.is_active:
            raise serializers.ValidationError({"teacher": "Тренер должен быть активным."})
        if subject and not subject.is_active:
            raise serializers.ValidationError({"subject": "Предмет должен быть активным."})
        if room and not room.is_active:
            raise serializers.ValidationError({"room": "Аудитория должна быть активной."})

        if teacher and day_of_week and start_time and end_time:
            conflict = find_schedule_teacher_conflict(
                teacher=teacher, day_of_week=day_of_week, start_time=start_time, end_time=end_time,
                exclude_schedule_id=exclude_id,
            )
            if conflict is not None:
                raise serializers.ValidationError(
                    {"teacher": f"Тренер «{teacher}» уже занят в это время в группе «{conflict.group.name}»."}
                )

        if room and day_of_week and start_time and end_time:
            conflict = find_schedule_room_conflict(
                room=room, day_of_week=day_of_week, start_time=start_time, end_time=end_time,
                exclude_schedule_id=exclude_id,
            )
            if conflict is not None:
                raise serializers.ValidationError(
                    {"room": f"Аудитория «{room.name}» уже занята в это время в группе «{conflict.group.name}»."}
                )

        return attrs


class GroupTeacherLessonPlanSerializer(serializers.ModelSerializer):
    """One row of a GroupTeacher's own lesson plan — the per-teacher
    counterpart of CourseLessonPlanSerializer (see models.GroupTeacherLessonPlan)."""

    class Meta:
        model = GroupTeacherLessonPlan
        fields = [
            "id",
            "group_teacher",
            "lesson_number",
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
        group_teacher = attrs.get("group_teacher", getattr(self.instance, "group_teacher", None))
        lesson_number = attrs.get("lesson_number", getattr(self.instance, "lesson_number", None))

        duplicates = GroupTeacherLessonPlan.objects.filter(group_teacher=group_teacher, lesson_number=lesson_number)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if group_teacher and lesson_number and duplicates.exists():
            raise serializers.ValidationError(
                {"lesson_number": "План с таким номером занятия для этого тренера уже существует."}
            )

        return attrs


class GroupTeacherSerializer(serializers.ModelSerializer):
    """"This Teacher teaches this Subject in this Group" — see models.GroupTeacher.

    `schedules` and `lesson_plans_count` are read-only conveniences: a
    GroupTeacher's actual schedule slots are managed via
    GroupScheduleViewSet/GroupScheduleSlotSerializer, and its plan rows via
    GroupTeacherLessonPlanViewSet — both are always derived from/scoped to
    this GroupTeacher, never set through this serializer.
    """

    teacher_detail = TeacherSerializer(source="teacher", read_only=True)
    subject_detail = SubjectSerializer(source="subject", read_only=True)
    schedules = GroupScheduleSlotSerializer(many=True, read_only=True)
    lesson_plans_count = serializers.SerializerMethodField()

    class Meta:
        model = GroupTeacher
        fields = [
            "id",
            "group",
            "teacher",
            "teacher_detail",
            "subject",
            "subject_detail",
            "is_active",
            "is_legacy_primary",
            "schedules",
            "lesson_plans_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_legacy_primary", "created_at", "updated_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = Teacher.objects.filter(is_active=True)
        self.fields["subject"].queryset = Subject.objects.filter(is_active=True)

    def get_lesson_plans_count(self, obj: GroupTeacher) -> int:
        annotated = getattr(obj, "_plan_count", None)
        return annotated if annotated is not None else obj.lesson_plans.count()


class GroupSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source="teacher.__str__", read_only=True)
    room_name = serializers.CharField(source="room.name", read_only=True, default=None)
    course_name = serializers.CharField(source="course.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    students_count = serializers.SerializerMethodField()
    schedules = GroupScheduleSlotSerializer(many=True, read_only=True)
    teachers = GroupTeacherSerializer(many=True, read_only=True)
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
            "schedules",
            "teachers",
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
        # Only active teachers can be assigned to a group. teacher/room/
        # start_time/end_time/days_of_week are legacy fields (see their
        # help_text on the model) — kept writable for historical data, but
        # never required: a Group is fully usable with every one of them
        # blank, once it has at least one GroupTeacher/GroupSchedule.
        self.fields["teacher"].queryset = Teacher.objects.filter(is_active=True)
        self.fields["teacher"].required = False
        self.fields["room"].required = False
        self.fields["start_time"].required = False
        self.fields["end_time"].required = False
        self.fields["days_of_week"].required = False

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

        teacher = attrs.get("teacher", getattr(self.instance, "teacher", None))
        if teacher is not None and days_of_week and start_time and end_time and start_date:
            conflict = find_group_teacher_conflict(
                teacher=teacher,
                days_of_week=days_of_week,
                start_time=start_time,
                end_time=end_time,
                start_date=start_date,
                end_date=end_date,
                exclude_group_id=getattr(self.instance, "pk", None),
            )
            if conflict is not None:
                raise serializers.ValidationError(
                    {"teacher": f"Тренер «{teacher}» уже занят в это время группой «{conflict.name}»."}
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
    teacher_name = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = [
            "id",
            "group",
            "group_name",
            "group_teacher",
            "plan",
            "individual_plan",
            "lesson_number",
            "date",
            "start_time",
            "end_time",
            "room",
            "room_name",
            "subject",
            "subject_name",
            "teacher",
            "teacher_name",
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
        read_only_fields = [
            "id", "group", "group_teacher", "plan", "individual_plan", "lesson_number", "teacher",
            "created_at", "updated_at",
        ]

    def get_teacher_name(self, obj: Lesson) -> str | None:
        teacher = obj.effective_teacher
        return str(teacher) if teacher else None

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
            # `lesson`: only Lessons the requesting Teacher actually gives —
            # a colleague's Teaching Program in the same Group is off
            # limits. `student`: the whole Group roster, since one student
            # can attend several teachers' Teaching Programs in the same
            # Group.
            self.fields["lesson"].queryset = _teacher_owned_lessons(user)
            self.fields["student"].queryset = Student.objects.filter(group_id__in=_teacher_group_ids(user))

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
            self.fields["lesson"].queryset = _teacher_owned_lessons(user)

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
            # `homework`: only Homework of Lessons this Teacher actually
            # gives. `student`: the whole Group roster (see AttendanceSerializer).
            self.fields["homework"].queryset = Homework.objects.filter(lesson__in=_teacher_owned_lessons(user))
            self.fields["student"].queryset = Student.objects.filter(group_id__in=_teacher_group_ids(user))

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
# Nothing here maps to a model: get_dashboard() returns a plain dict shaped
# exactly like these serializers, never a persisted KPI row.
#
# AnalyticsDashboardSerializer documents the response shape (drf-spectacular
# schema) only — the view returns get_dashboard()'s own dict directly rather
# than running it through `.data`, so int-valued metrics (counts) stay ints
# instead of being coerced through DRF's FloatField.
# ---------------------------------------------------------------------------

class AnalyticsQuerySerializer(serializers.Serializer):
    """Query params for `GET /analytics/dashboard/`.

    `compare` accepts "true" (shorthand for "previous_period"), "false"/blank
    (no comparison), or one of services.analytics.COMPARE_CHOICES directly —
    validated against the full set in the view, where the shorthand is
    resolved (keeps this serializer a plain CharField rather than a
    ChoiceField that would reject the boolean shorthand spec §5 shows).
    """

    period = serializers.ChoiceField(choices=list(PERIOD_CHOICES), default="this_month")
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    compare = serializers.CharField(required=False, allow_blank=True, default="")
    compare_start_date = serializers.DateField(required=False)
    compare_end_date = serializers.DateField(required=False)
    teacher = serializers.PrimaryKeyRelatedField(queryset=Teacher.objects.all(), required=False, allow_null=True)
    group = serializers.PrimaryKeyRelatedField(queryset=Group.objects.all(), required=False, allow_null=True)
    course = serializers.PrimaryKeyRelatedField(queryset=Course.objects.all(), required=False, allow_null=True)
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)

    def validate(self, attrs):
        if attrs["period"] == "custom" and not (attrs.get("start_date") and attrs.get("end_date")):
            raise serializers.ValidationError(
                {"start_date": "period=custom требует start_date и end_date."}
            )
        return attrs


class ComparisonMetricSerializer(serializers.Serializer):
    """`{value, previous_value, change, change_percent, trend}` — see
    services.analytics.metrics.build_metric. Every comparable KPI in the
    dashboard is shaped exactly like this."""

    value = serializers.FloatField()
    previous_value = serializers.FloatField(allow_null=True)
    change = serializers.FloatField(allow_null=True)
    change_percent = serializers.FloatField(allow_null=True)
    trend = serializers.ChoiceField(choices=["up", "down", "stable"])


class AnalyticsPeriodSerializer(serializers.Serializer):
    key = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class AnalyticsComparisonSerializer(serializers.Serializer):
    key = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class AnalyticsFiltersSerializer(serializers.Serializer):
    teacher_id = serializers.IntegerField(allow_null=True)
    group_id = serializers.IntegerField(allow_null=True)
    course_id = serializers.IntegerField(allow_null=True)
    subject_id = serializers.IntegerField(allow_null=True)


class AnalyticsStudentsSectionSerializer(serializers.Serializer):
    total_students = ComparisonMetricSerializer()
    active_students = ComparisonMetricSerializer()
    inactive_students = ComparisonMetricSerializer()
    new_students = ComparisonMetricSerializer()
    students_left = ComparisonMetricSerializer()
    average_students_per_group = ComparisonMetricSerializer()
    groups_with_free_capacity = ComparisonMetricSerializer()
    groups_at_capacity = ComparisonMetricSerializer()


class AnalyticsTeacherWorkloadRowSerializer(serializers.Serializer):
    teacher_id = serializers.IntegerField()
    teacher_name = serializers.CharField()
    lessons = serializers.IntegerField()


class AnalyticsTeachersSectionSerializer(serializers.Serializer):
    total_teachers = ComparisonMetricSerializer()
    active_teachers = ComparisonMetricSerializer()
    teachers_with_lessons = ComparisonMetricSerializer()
    teachers_without_lessons = ComparisonMetricSerializer()
    average_lessons_per_teacher = ComparisonMetricSerializer()
    teacher_workload = AnalyticsTeacherWorkloadRowSerializer(many=True)


class AnalyticsGroupsSectionSerializer(serializers.Serializer):
    total_groups = ComparisonMetricSerializer()
    active_groups = ComparisonMetricSerializer()
    paused_groups = ComparisonMetricSerializer()
    completed_groups = ComparisonMetricSerializer()
    cancelled_groups = ComparisonMetricSerializer()
    average_students_per_group = ComparisonMetricSerializer()
    groups_near_capacity = ComparisonMetricSerializer()


class AnalyticsLessonsByTeacherRowSerializer(serializers.Serializer):
    teacher_id = serializers.IntegerField()
    teacher_name = serializers.CharField()
    lessons = serializers.IntegerField()


class AnalyticsLessonsBySubjectRowSerializer(serializers.Serializer):
    subject_id = serializers.IntegerField()
    subject_name = serializers.CharField()
    lessons = serializers.IntegerField()


class AnalyticsLessonsSectionSerializer(serializers.Serializer):
    lessons_today = ComparisonMetricSerializer()
    lessons_scheduled = ComparisonMetricSerializer()
    lessons_completed = ComparisonMetricSerializer()
    lessons_cancelled = ComparisonMetricSerializer()
    lesson_completion_rate = ComparisonMetricSerializer()
    lessons_by_teacher = AnalyticsLessonsByTeacherRowSerializer(many=True)
    lessons_by_subject = AnalyticsLessonsBySubjectRowSerializer(many=True)


class AnalyticsTrendPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    percent = serializers.FloatField()


class AnalyticsAttendanceSectionSerializer(serializers.Serializer):
    attendance_rate = ComparisonMetricSerializer()
    present_count = ComparisonMetricSerializer()
    absent_count = ComparisonMetricSerializer()
    late_count = ComparisonMetricSerializer()
    excused_count = ComparisonMetricSerializer()
    students_with_repeated_absences = ComparisonMetricSerializer()
    attendance_trend = AnalyticsTrendPointSerializer(many=True)


class AnalyticsHomeworkSectionSerializer(serializers.Serializer):
    homework_count = ComparisonMetricSerializer()
    submitted_count = ComparisonMetricSerializer()
    not_submitted_count = ComparisonMetricSerializer()
    checked_count = ComparisonMetricSerializer()
    late_count = ComparisonMetricSerializer()
    submission_rate = ComparisonMetricSerializer()
    average_score = ComparisonMetricSerializer()
    homework_completion_trend = AnalyticsTrendPointSerializer(many=True)


class AnalyticsHealthComponentsSerializer(serializers.Serializer):
    attendance = serializers.FloatField()
    homework = serializers.FloatField()
    lesson_completion = serializers.FloatField()
    retention = serializers.FloatField()
    teacher_workload = serializers.FloatField()


class AnalyticsHealthSerializer(serializers.Serializer):
    """See services.analytics.health for the scoring formula — never stored."""

    score = serializers.IntegerField()
    level = serializers.ChoiceField(choices=["excellent", "good", "fair", "poor"])
    components = AnalyticsHealthComponentsSerializer()


class AnalyticsInsightSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["warning", "critical", "info"])
    title = serializers.CharField()
    message = serializers.CharField()
    metric = serializers.CharField()
    severity = serializers.ChoiceField(choices=["low", "medium", "high"])


class AnalyticsDashboardSerializer(serializers.Serializer):
    """The full payload of `GET /analytics/dashboard/` — exactly what
    `services.analytics.get_dashboard()` returns, computed fresh on every
    call. `comparison` is null whenever no comparison period was requested."""

    period = AnalyticsPeriodSerializer()
    comparison = AnalyticsComparisonSerializer(allow_null=True)
    filters = AnalyticsFiltersSerializer()
    health = AnalyticsHealthSerializer()
    students = AnalyticsStudentsSectionSerializer()
    teachers = AnalyticsTeachersSectionSerializer()
    groups = AnalyticsGroupsSectionSerializer()
    lessons = AnalyticsLessonsSectionSerializer()
    attendance = AnalyticsAttendanceSectionSerializer()
    homework = AnalyticsHomeworkSectionSerializer()
    insights = AnalyticsInsightSerializer(many=True)
