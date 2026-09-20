from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from apps.users.import_export.formats import UnsupportedFileFormat
from apps.users.models import Teacher, User
from apps.users.permissions import IsAdmin
from apps.users.serializers import (
    ImportFileRequestSerializer,
    ImportPreviewSerializer,
    ImportResultSerializer,
    TeacherSerializer,
)

from .filters import (
    AttendanceFilter,
    CourseFilter,
    GroupFilter,
    HomeworkFilter,
    LessonFilter,
    StudentFilter,
)
from .models import (
    AcademyMonthlyReport,
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
    MonthlyTeacherReport,
    Room,
    Student,
)
from .permissions import IsAdminOrOwningTeacher, IsAdminOrReadOnly
from .serializers import (
    AcademyMonthlyReportCommentSerializer,
    AcademyMonthlyReportCreateSerializer,
    AcademyMonthlyReportSerializer,
    AnalyticsDashboardSerializer,
    AnalyticsQuerySerializer,
    AttendanceSerializer,
    BulkAttendanceItemSerializer,
    BulkHomeworkResultItemSerializer,
    CourseLessonPlanSerializer,
    CourseSerializer,
    GenerateLessonsResponseSerializer,
    GroupScheduleLessonSerializer,
    GroupScheduleSerializer,
    GroupScheduleSlotSerializer,
    GroupSerializer,
    GroupTeacherLessonPlanSerializer,
    GroupTeacherSerializer,
    HomeworkNotRequiredRequestSerializer,
    HomeworkResultSerializer,
    HomeworkSerializer,
    LessonCancelRequestSerializer,
    LessonSerializer,
    MonthlyTeacherReportCommentSerializer,
    MonthlyTeacherReportCreateSerializer,
    MonthlyTeacherReportSerializer,
    RoomAvailabilityRequestSerializer,
    RoomAvailabilitySerializer,
    RoomSerializer,
    StudentSerializer,
    TeacherAvailabilityRequestSerializer,
    TeacherAvailabilitySerializer,
)
from .services.analytics import COMPARE_CHOICES, get_dashboard
from .services.attendance_service import bulk_mark_attendance
from .services.homework_service import bulk_upsert_homework_results
from .services import lesson_lifecycle
from .services.monthly_report_pdf import build_monthly_report_pdf
from .services.academy_monthly_report_pdf import build_academy_monthly_report_pdf
from .services.import_export import (
    StudentImportValidationError,
    export_students,
    import_students,
    preview_students_import,
)
from .services.lesson_generator import LessonGenerationError, generate_lessons_for_group


def _teacher_profile(request):
    return getattr(request.user, "teacher_profile", None)


def _teacher_group_ids(teacher):
    """IDs of every Group `teacher` has a stake in — as its primary teacher
    or via any active GroupSchedule slot (see Group.objects.for_teacher)."""
    return Group.objects.for_teacher(teacher).values_list("id", flat=True)


def _is_admin(user) -> bool:
    # AnonymousUser has no `.role` — guard so schema generation (which
    # introspects get_queryset with an anonymous request) and any
    # accidentally-unauthenticated call never crash with an AttributeError.
    if not getattr(user, "is_authenticated", False):
        return False
    return bool(user.is_superuser or user.role == User.Role.ADMIN)


def _as_drf_validation_error(exc: DjangoValidationError) -> DRFValidationError:
    return DRFValidationError(getattr(exc, "messages", None) or [str(exc)])


def _assert_teacher_owns_lesson(request, lesson) -> None:
    """Defense-in-depth for Attendance/Homework/HomeworkResult creation.

    The serializer's own `lesson`/`homework`/`student` fields are already
    scoped to the requesting teacher's own lessons (see AttendanceSerializer/
    HomeworkSerializer/HomeworkResultSerializer `__init__`), so a non-owning
    teacher's request never validates in the first place — `lesson` here
    should always already be theirs. This re-checks it anyway, independent
    of that field-scoping, so a future refactor of the serializers can never
    silently reopen cross-teacher writes without this also failing.
    """
    if _is_admin(request.user):
        return
    teacher = _teacher_profile(request)
    owner = lesson.effective_teacher if lesson is not None else None
    if not (teacher and owner and owner.id == teacher.id):
        raise PermissionDenied("Вы можете работать только со своими занятиями.")


def _assert_homework_results_editable(request, lesson) -> None:
    """Once a lesson is COMPLETED, its homework results are frozen for a
    Teacher — grades/statuses/comments already fed into the completion
    record and must not keep changing under it. Admin keeps write access
    (the same "Admin can manage all lessons" override every other lesson
    lifecycle rule in this app grants — see services.lesson_lifecycle)."""
    if _is_admin(request.user):
        return
    if lesson is not None and lesson_lifecycle.homework_results_locked(lesson):
        raise PermissionDenied(
            "Занятие завершено — результаты домашнего задания больше нельзя редактировать."
        )


def _assert_lesson_editable(request, lesson) -> None:
    """A completed or cancelled lesson is an immutable historical record for
    a Teacher — no new Attendance or Homework may be attached to it, on top
    of the lesson's own status/cancellation_reason already being read-only
    (see LessonSerializer) and its homework results being separately locked
    by `_assert_homework_results_editable`. Admin keeps write access, same
    override as everywhere else in the lesson lifecycle."""
    if _is_admin(request.user):
        return
    if lesson is not None and lesson_lifecycle.lesson_editing_locked(lesson):
        raise PermissionDenied(
            "Занятие завершено или отменено — данные больше нельзя изменять."
        )


# ---------------------------------------------------------------------------
# Course catalogue
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(tags=["Courses"]),
    retrieve=extend_schema(tags=["Courses"]),
    create=extend_schema(tags=["Courses"]),
    update=extend_schema(tags=["Courses"]),
    partial_update=extend_schema(tags=["Courses"]),
    destroy=extend_schema(tags=["Courses"]),
)
class CourseViewSet(viewsets.ModelViewSet):
    """Courses. Admin manages the catalogue; a Teacher can only read it."""

    serializer_class = CourseSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = CourseFilter
    search_fields = ["name", "description"]
    ordering_fields = ["name", "count_lesson", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        return (
            Course.objects.prefetch_related("subjects")
            .annotate(_lesson_plans_count=Count("lesson_plans", distinct=True))
        )

    @extend_schema(tags=["Courses"], responses=CourseLessonPlanSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="lesson-plans")
    def lesson_plans(self, request, pk=None):
        course = self.get_object()
        qs = course.lesson_plans.select_related("subject").order_by("lesson_number")
        return Response(CourseLessonPlanSerializer(qs, many=True).data)


@extend_schema_view(
    list=extend_schema(tags=["Course lesson plans"]),
    retrieve=extend_schema(tags=["Course lesson plans"]),
    create=extend_schema(tags=["Course lesson plans"]),
    update=extend_schema(tags=["Course lesson plans"]),
    partial_update=extend_schema(tags=["Course lesson plans"]),
    destroy=extend_schema(tags=["Course lesson plans"]),
)
class CourseLessonPlanViewSet(viewsets.ModelViewSet):
    """The full lesson-by-lesson template of a course. Admin-managed."""

    queryset = CourseLessonPlan.objects.select_related("course", "subject")
    serializer_class = CourseLessonPlanSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["course", "subject"]
    search_fields = ["topic", "description"]
    ordering_fields = ["lesson_number", "created_at"]
    ordering = ["course", "lesson_number"]


# ---------------------------------------------------------------------------
# Rooms & students
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(tags=["Rooms"]),
    retrieve=extend_schema(tags=["Rooms"]),
    create=extend_schema(tags=["Rooms"]),
    update=extend_schema(tags=["Rooms"]),
    partial_update=extend_schema(tags=["Rooms"]),
    destroy=extend_schema(tags=["Rooms"]),
)
class RoomViewSet(viewsets.ModelViewSet):
    """Classrooms. Admin manages them; everyone authenticated can read."""

    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["is_active"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "capacity"]
    ordering = ["name"]

    @extend_schema(
        tags=["Rooms"],
        parameters=[RoomAvailabilityRequestSerializer],
        responses=RoomAvailabilitySerializer,
        description=(
            "Free vs. occupied rooms for a given date + time window, based on "
            "existing Lesson rows (any Lesson whose [start_time, end_time) "
            "overlaps the requested window occupies its room; cancelled "
            "lessons never occupy a room)."
        ),
    )
    @action(detail=False, methods=["get"], url_path="available", permission_classes=[IsAuthenticated])
    def available(self, request):
        params = RoomAvailabilityRequestSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        date_ = params.validated_data["date"]
        start_time = params.validated_data["start_time"]
        end_time = params.validated_data["end_time"]

        overlapping_lessons = (
            Lesson.objects.filter(date=date_, room__isnull=False)
            .exclude(status=Lesson.Status.CANCELLED)
            .filter(start_time__lt=end_time, end_time__gt=start_time)
            .select_related("room", "group")
        )

        occupied_room_ids = set()
        occupied = []
        for lesson in overlapping_lessons:
            occupied_room_ids.add(lesson.room_id)
            occupied.append(
                {
                    "room": lesson.room_id,
                    "room_name": lesson.room.name,
                    "lesson": lesson.id,
                    "group": lesson.group_id,
                    "group_name": lesson.group.name,
                    "start_time": lesson.start_time,
                    "end_time": lesson.end_time,
                }
            )

        available_rooms = Room.objects.filter(is_active=True).exclude(id__in=occupied_room_ids).order_by("name")

        payload = {
            "date": date_,
            "start_time": start_time,
            "end_time": end_time,
            "available": RoomSerializer(available_rooms, many=True).data,
            "occupied": occupied,
        }
        return Response(RoomAvailabilitySerializer(payload).data)


@extend_schema_view(
    list=extend_schema(tags=["Students"]),
    retrieve=extend_schema(tags=["Students"]),
    create=extend_schema(tags=["Students"]),
    update=extend_schema(tags=["Students"]),
    partial_update=extend_schema(tags=["Students"]),
    destroy=extend_schema(tags=["Students"]),
)
class StudentViewSet(viewsets.ModelViewSet):
    """Students. Admin sees/manages all; a Teacher only sees their own groups' students."""

    serializer_class = StudentSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = StudentFilter
    search_fields = ["first_name", "last_name", "phone", "parent_phone"]
    ordering_fields = ["last_name", "first_name", "created_at"]
    ordering = ["last_name", "first_name"]

    def get_queryset(self):
        qs = Student.objects.select_related("group")
        user = self.request.user
        if _is_admin(user):
            return qs
        teacher = _teacher_profile(self.request)
        if teacher is None:
            return qs.none()
        return qs.filter(group_id__in=_teacher_group_ids(teacher))

    @extend_schema(
        tags=["Students"],
        parameters=[
            OpenApiParameter(name="export_format", type=str, enum=["csv", "xlsx"], required=False, description="csv (по умолчанию) или xlsx."),
        ],
        request=None,
        responses={200: bytes},
        description=(
            "Экспорт студентов (текущего отфильтрованного списка — учитывает ?group=, "
            "?is_active=, ?search= и т.д.) в CSV или XLSX. Group экспортируется по имени. "
            "Параметр называется export_format (не format — это имя зарезервировано DRF "
            "для согласования типа содержимого ответа)."
        ),
    )
    @action(detail=False, methods=["get"], url_path="export")
    def export(self, request):
        fmt = request.query_params.get("export_format", "csv")
        queryset = self.filter_queryset(self.get_queryset())
        try:
            return export_students(queryset, fmt)
        except UnsupportedFileFormat as exc:
            raise DRFValidationError(str(exc))

    @extend_schema(
        tags=["Students"],
        request=ImportFileRequestSerializer,
        responses=ImportPreviewSerializer,
        description="Проверка файла импорта студентов без сохранения изменений.",
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
            preview = preview_students_import(file_obj)
        except UnsupportedFileFormat as exc:
            raise DRFValidationError(str(exc))
        return Response(preview.as_dict())

    @extend_schema(
        tags=["Students"],
        request=ImportFileRequestSerializer,
        responses={201: ImportResultSerializer, 400: ImportPreviewSerializer},
        description=(
            "Импорт студентов из CSV/XLSX. Group ищется по имени (не создаётся автоматически). "
            "Строка с `id` обновляет существующего студента, без `id` — создаёт нового. "
            "Транзакционный: при наличии хотя бы одной ошибки ни одна строка не сохраняется."
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
            result = import_students(file_obj)
        except UnsupportedFileFormat as exc:
            raise DRFValidationError(str(exc))
        except StudentImportValidationError as exc:
            return Response(
                {"detail": "Импорт не выполнен — найдены ошибки.", **exc.preview.as_dict()},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result.as_dict(), status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(tags=["Groups"]),
    retrieve=extend_schema(tags=["Groups"]),
    create=extend_schema(tags=["Groups"]),
    update=extend_schema(tags=["Groups"]),
    partial_update=extend_schema(tags=["Groups"]),
    destroy=extend_schema(tags=["Groups"]),
)
class GroupViewSet(viewsets.ModelViewSet):
    """Groups. Admin manages all groups; a Teacher only reads their own."""

    serializer_class = GroupSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = GroupFilter
    search_fields = ["name", "teacher__user__first_name", "teacher__user__last_name"]
    ordering_fields = ["name", "start_date", "created_at"]
    ordering = ["-start_date", "name"]

    def get_queryset(self):
        qs = (
            Group.objects.select_related("teacher__user", "room", "course")
            .annotate(
                active_students_count=Count(
                    "students", filter=Q(students__is_active=True), distinct=True
                )
            )
        )
        user = self.request.user
        if _is_admin(user):
            return qs
        teacher = _teacher_profile(self.request)
        if teacher is None:
            return qs.none()
        return qs.filter(id__in=_teacher_group_ids(teacher))

    @extend_schema(
        tags=["Groups"],
        request=None,
        responses=GenerateLessonsResponseSerializer,
    )
    @action(detail=True, methods=["post"], url_path="generate-lessons", permission_classes=[IsAuthenticated, IsAdmin])
    def generate_lessons(self, request, pk=None):
        group = self.get_object()
        try:
            created = generate_lessons_for_group(group)
        except LessonGenerationError as exc:
            raise DRFValidationError(str(exc))

        if created:
            first_lesson, last_lesson = created[0], created[-1]
        else:
            existing = list(group.lessons.order_by("lesson_number"))
            first_lesson = existing[0] if existing else None
            last_lesson = existing[-1] if existing else None

        payload = {
            "created_count": len(created),
            "first_lesson": first_lesson.lesson_number if first_lesson else None,
            "last_lesson": last_lesson.lesson_number if last_lesson else None,
            "first_date": first_lesson.date if first_lesson else None,
            "last_date": last_lesson.date if last_lesson else None,
        }
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(GenerateLessonsResponseSerializer(payload).data, status=response_status)

    @extend_schema(tags=["Groups"], responses=GroupScheduleSerializer)
    @action(detail=True, methods=["get"], url_path="schedule")
    def schedule(self, request, pk=None):
        """The Trainer-facing "schedule of this group": the group itself plus
        every one of its concrete, dated Lessons (day-by-day, not a generic
        flat Lesson list) — what `GroupsListPage -> Group -> schedule` opens.

        Looked up via `get_queryset()` directly rather than `self.get_object()`:
        the latter also runs this viewset's `GroupFilter` (via
        `filter_queryset()`), and `?status=` here means *Lesson* status, not
        the `Group.status` field `GroupFilter` defines under the same name —
        applying that filter to a single-object lookup by id would wrongly
        404 e.g. an active group when `?status=cancelled` is passed.
        """
        group = get_object_or_404(self.get_queryset(), pk=pk)
        lessons = group.lessons.select_related("room", "subject", "plan").order_by("date", "start_time")

        # Even within a group they share, one teacher's Lessons must stay
        # invisible to another teacher of the same group's other Teaching
        # Programs (see models.GroupTeacher / models.LessonQuerySet.for_teacher) —
        # Admin still sees every lesson of the group.
        if not _is_admin(request.user):
            teacher = _teacher_profile(request)
            lessons = lessons.for_teacher(teacher) if teacher is not None else lessons.none()

        status_param = request.query_params.get("status")
        if status_param:
            lessons = lessons.filter(status=status_param)

        payload = {
            "group": GroupSerializer(group, context=self.get_serializer_context()).data,
            "lessons": GroupScheduleLessonSerializer(lessons, many=True, context=self.get_serializer_context()).data,
        }
        return Response(payload)

    @extend_schema(tags=["Groups"], responses=StudentSerializer(many=True))
    @action(detail=True, methods=["get"], url_path="students")
    def students(self, request, pk=None):
        group = get_object_or_404(self.get_queryset(), pk=pk)
        qs = group.students.select_related("group").order_by("last_name", "first_name")

        is_active_param = request.query_params.get("is_active")
        if is_active_param is not None:
            qs = qs.filter(is_active=is_active_param.lower() in ("1", "true", "yes"))
        else:
            qs = qs.filter(is_active=True)

        return Response(StudentSerializer(qs, many=True, context=self.get_serializer_context()).data)


@extend_schema_view(
    list=extend_schema(tags=["Groups"]),
    retrieve=extend_schema(tags=["Groups"]),
    create=extend_schema(tags=["Groups"]),
    update=extend_schema(tags=["Groups"]),
    partial_update=extend_schema(tags=["Groups"]),
    destroy=extend_schema(tags=["Groups"]),
)
class GroupScheduleViewSet(viewsets.ModelViewSet):
    """Recurring weekly schedule slots of a Group — see models.GroupSchedule.

    A Group's "primary" slot (its own teacher/room/start_time/end_time/
    days_of_week) is mirrored here automatically; this viewset is for the
    *additional* slots that give a Group several teachers, subjects, days
    or time ranges (see `GroupSerializer.schedules` for the read-only,
    nested view of all of a group's slots together). Admin manages them —
    typically through the Group admin page's inline — a Teacher only reads
    the slots of groups they already have access to.
    """

    serializer_class = GroupScheduleSlotSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["group", "teacher", "subject", "day_of_week", "room", "is_active"]
    search_fields = ["group__name"]
    ordering_fields = ["day_of_week", "start_time"]
    ordering = ["group", "day_of_week", "start_time"]

    def get_queryset(self):
        qs = GroupSchedule.objects.select_related("group", "teacher__user", "subject", "room")
        user = self.request.user
        if _is_admin(user):
            return qs
        teacher = _teacher_profile(self.request)
        if teacher is None:
            return qs.none()
        # Own schedule slots only — a Group's other Teaching Programs (see
        # models.GroupTeacher) belong to other teachers, even within the
        # same Group.
        return qs.filter(teacher=teacher)


@extend_schema_view(
    list=extend_schema(tags=["Groups"]),
    retrieve=extend_schema(tags=["Groups"]),
    create=extend_schema(tags=["Groups"]),
    update=extend_schema(tags=["Groups"]),
    partial_update=extend_schema(tags=["Groups"]),
    destroy=extend_schema(tags=["Groups"]),
)
class GroupTeacherViewSet(viewsets.ModelViewSet):
    """"This Teacher teaches this Subject in this Group" — see models.GroupTeacher.

    Get-or-created automatically from GroupSchedule (typically via the Group
    admin page's inline) — this viewset mainly exists to *read* a group's
    teacher assignments (see `GroupSerializer.teachers`) and to toggle
    `is_active`; Admin manages it, a Teacher only reads their own.
    """

    serializer_class = GroupTeacherSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["group", "teacher", "subject", "is_active"]
    search_fields = ["group__name", "teacher__user__first_name", "teacher__user__last_name"]
    ordering_fields = ["group", "created_at"]
    ordering = ["group", "id"]

    def get_queryset(self):
        qs = GroupTeacher.objects.select_related("group", "teacher__user", "subject").prefetch_related("schedules")
        user = self.request.user
        if _is_admin(user):
            return qs
        teacher = _teacher_profile(self.request)
        if teacher is None:
            return qs.none()
        # Own Teaching Programs only — another teacher's assignment in the
        # same Group (e.g. a colleague's Subject) isn't this teacher's to see.
        return qs.filter(teacher=teacher)


@extend_schema_view(
    list=extend_schema(tags=["Groups"]),
    retrieve=extend_schema(tags=["Groups"]),
    create=extend_schema(tags=["Groups"]),
    update=extend_schema(tags=["Groups"]),
    partial_update=extend_schema(tags=["Groups"]),
    destroy=extend_schema(tags=["Groups"]),
)
class GroupTeacherLessonPlanViewSet(viewsets.ModelViewSet):
    """A GroupTeacher's own lesson-by-lesson plan — see models.GroupTeacherLessonPlan.

    Admin manages it; a Teacher can only read their own plan(s). Adding rows
    here (and re-running `generate-lessons`) is what switches a GroupTeacher
    from the group's shared course plan onto its own independent
    plan/numbering (see services.lesson_generator).
    """

    serializer_class = GroupTeacherLessonPlanSerializer
    permission_classes = [IsAdminOrReadOnly]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["group_teacher"]
    search_fields = ["topic", "description"]
    ordering_fields = ["lesson_number", "created_at"]
    ordering = ["group_teacher", "lesson_number"]

    def get_queryset(self):
        qs = GroupTeacherLessonPlan.objects.select_related("group_teacher__group", "group_teacher__teacher__user")
        user = self.request.user
        if _is_admin(user):
            return qs
        teacher = _teacher_profile(self.request)
        if teacher is None:
            return qs.none()
        return qs.filter(group_teacher__teacher=teacher)


# ---------------------------------------------------------------------------
# Lessons — list / retrieve / update only; created exclusively by the generator
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(tags=["Lessons"]),
    retrieve=extend_schema(tags=["Lessons"]),
    update=extend_schema(tags=["Lessons"]),
    partial_update=extend_schema(tags=["Lessons"]),
)
class LessonViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = LessonSerializer
    permission_classes = [IsAuthenticated, IsAdminOrOwningTeacher]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = LessonFilter
    search_fields = ["topic", "description"]
    ordering_fields = ["date", "start_time", "lesson_number"]
    ordering = ["date", "start_time"]

    def get_queryset(self):
        qs = Lesson.objects.select_related("group__teacher__user", "teacher__user", "room", "subject", "plan")
        user = self.request.user
        if _is_admin(user):
            return qs
        teacher = _teacher_profile(self.request)
        if teacher is None:
            return qs.none()
        # Only Lessons this teacher actually gives — a Group's other Teaching
        # Programs (see models.GroupTeacher) belong to other teachers.
        return qs.for_teacher(teacher)

    @extend_schema(
        tags=["Attendance"],
        request=BulkAttendanceItemSerializer(many=True),
        responses=AttendanceSerializer(many=True),
        description=(
            "GET returns the lesson's full student roster (existing Attendance "
            "or a not-yet-marked placeholder for each). POST bulk-creates/updates "
            "Attendance for the given students in one call."
        ),
    )
    @action(detail=True, methods=["get", "post"], url_path="attendance")
    def attendance(self, request, pk=None):
        lesson = self.get_object()

        if request.method.lower() == "get":
            students = lesson.group.students.filter(is_active=True).order_by("last_name", "first_name")
            existing = {
                a.student_id: a
                for a in Attendance.objects.filter(lesson=lesson).select_related("student")
            }
            payload = []
            for student in students:
                record = existing.get(student.id)
                if record is not None:
                    payload.append(AttendanceSerializer(record).data)
                else:
                    payload.append(
                        {
                            "id": None,
                            "student": student.id,
                            "student_name": str(student),
                            "lesson": lesson.id,
                            "group_name": lesson.group.name,
                            "lesson_date": lesson.date,
                            "status": None,
                            "status_display": None,
                            "comment": "",
                            "created_at": None,
                            "updated_at": None,
                        }
                    )
            return Response(payload)

        _assert_lesson_editable(request, lesson)

        item_serializer = BulkAttendanceItemSerializer(data=request.data, many=True)
        item_serializer.is_valid(raise_exception=True)
        try:
            records = bulk_mark_attendance(lesson, item_serializer.validated_data)
        except DjangoValidationError as exc:
            raise _as_drf_validation_error(exc)

        records_qs = Attendance.objects.filter(pk__in=[r.pk for r in records]).select_related("student")
        return Response(AttendanceSerializer(records_qs, many=True).data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Lessons"],
        request=None,
        responses=LessonSerializer,
        description="SCHEDULED → IN_PROGRESS. Idempotent — starting an already in-progress lesson is a no-op.",
    )
    @action(detail=True, methods=["post"], url_path="start")
    def start(self, request, pk=None):
        lesson = self.get_object()
        try:
            lesson = lesson_lifecycle.start_lesson(lesson, request.user)
        except DjangoValidationError as exc:
            raise _as_drf_validation_error(exc)
        return Response(LessonSerializer(lesson, context=self.get_serializer_context()).data)

    @extend_schema(
        tags=["Lessons"],
        request=None,
        responses=LessonSerializer,
        description=(
            "IN_PROGRESS → COMPLETED. Rejected (400) unless attendance is fully marked and either a "
            "Homework exists or homework_not_required has been set. Idempotent — completing an already "
            "completed lesson is a no-op and never re-checks requirements."
        ),
    )
    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, pk=None):
        lesson = self.get_object()
        try:
            lesson = lesson_lifecycle.complete_lesson(lesson, request.user)
        except DjangoValidationError as exc:
            raise _as_drf_validation_error(exc)
        return Response(LessonSerializer(lesson, context=self.get_serializer_context()).data)

    @extend_schema(
        tags=["Lessons"],
        request=LessonCancelRequestSerializer,
        responses=LessonSerializer,
        description=(
            "SCHEDULED/IN_PROGRESS → CANCELLED. A completed lesson can never be cancelled. "
            "Idempotent — cancelling an already cancelled lesson is a no-op."
        ),
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        lesson = self.get_object()
        body = LessonCancelRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            lesson = lesson_lifecycle.cancel_lesson(lesson, request.user, reason=body.validated_data.get("reason", ""))
        except DjangoValidationError as exc:
            raise _as_drf_validation_error(exc)
        return Response(LessonSerializer(lesson, context=self.get_serializer_context()).data)

    @extend_schema(
        tags=["Lessons"],
        request=HomeworkNotRequiredRequestSerializer,
        responses=LessonSerializer,
        description=(
            "Explicitly mark (or unmark) that this lesson needs no Homework — the only alternative to a "
            "real Homework row for satisfying the completion checklist. Only while the lesson is still "
            "open (scheduled/in_progress)."
        ),
    )
    @action(detail=True, methods=["post"], url_path="homework-not-required")
    def homework_not_required(self, request, pk=None):
        lesson = self.get_object()
        body = HomeworkNotRequiredRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            lesson = lesson_lifecycle.set_homework_not_required(lesson, body.validated_data["value"])
        except DjangoValidationError as exc:
            raise _as_drf_validation_error(exc)
        return Response(LessonSerializer(lesson, context=self.get_serializer_context()).data)


# ---------------------------------------------------------------------------
# Attendance (direct CRUD, for a single record or ?group=&date= listing)
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(tags=["Attendance"]),
    retrieve=extend_schema(tags=["Attendance"]),
    create=extend_schema(tags=["Attendance"]),
    update=extend_schema(tags=["Attendance"]),
    partial_update=extend_schema(tags=["Attendance"]),
    destroy=extend_schema(tags=["Attendance"]),
)
class AttendanceViewSet(viewsets.ModelViewSet):
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated, IsAdminOrOwningTeacher]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = AttendanceFilter
    search_fields = ["student__first_name", "student__last_name"]
    ordering_fields = ["lesson__date", "created_at"]
    ordering = ["-lesson__date"]

    def get_queryset(self):
        qs = Attendance.objects.select_related("student", "lesson__group__teacher__user")
        user = self.request.user
        if _is_admin(user):
            return qs
        teacher = _teacher_profile(self.request)
        if teacher is None:
            return qs.none()
        # Only Attendance of Lessons this teacher actually gives (see
        # models.LessonQuerySet.for_teacher) — a colleague's Teaching Program
        # in the same Group is off limits.
        return qs.filter(lesson__in=Lesson.objects.for_teacher(teacher))

    def perform_create(self, serializer):
        lesson = serializer.validated_data.get("lesson")
        _assert_teacher_owns_lesson(self.request, lesson)
        _assert_lesson_editable(self.request, lesson)
        serializer.save()

    def perform_update(self, serializer):
        _assert_lesson_editable(self.request, serializer.instance.lesson)
        serializer.save()


# ---------------------------------------------------------------------------
# Homework & results
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(tags=["Homework"]),
    retrieve=extend_schema(tags=["Homework"]),
    create=extend_schema(tags=["Homework"]),
    update=extend_schema(tags=["Homework"]),
    partial_update=extend_schema(tags=["Homework"]),
    destroy=extend_schema(tags=["Homework"]),
)
class HomeworkViewSet(viewsets.ModelViewSet):
    """The assignment itself. A Teacher manages homework only for their own lessons."""

    serializer_class = HomeworkSerializer
    permission_classes = [IsAuthenticated, IsAdminOrOwningTeacher]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = HomeworkFilter
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "deadline"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Homework.objects.select_related("lesson__group__teacher__user")
        user = self.request.user
        if _is_admin(user):
            return qs
        teacher = _teacher_profile(self.request)
        if teacher is None:
            return qs.none()
        # Only Homework of Lessons this teacher actually gives — a
        # colleague's Homework in the same Group is off limits.
        return qs.filter(lesson__in=Lesson.objects.for_teacher(teacher))

    def perform_create(self, serializer):
        lesson = serializer.validated_data.get("lesson")
        _assert_teacher_owns_lesson(self.request, lesson)
        _assert_lesson_editable(self.request, lesson)
        serializer.save()

    @extend_schema(
        methods=["GET"],
        tags=["Homework"],
        operation_id="homework_list_own_results",
        responses=HomeworkResultSerializer(many=True),
        description="Every active student of the lesson's group with their current result (or a not_submitted placeholder).",
    )
    @extend_schema(
        methods=["POST"],
        tags=["Homework"],
        operation_id="homework_bulk_grade_results",
        request=BulkHomeworkResultItemSerializer(many=True),
        responses=HomeworkResultSerializer(many=True),
        description="Bulk-grade the given students' results for this Homework in one call.",
    )
    @action(detail=True, methods=["get", "post"], url_path="results")
    def results(self, request, pk=None):
        homework = self.get_object()

        if request.method.lower() == "get":
            students = homework.lesson.group.students.filter(is_active=True).order_by("last_name", "first_name")
            existing = {
                r.student_id: r
                for r in HomeworkResult.objects.filter(homework=homework).select_related("student")
            }
            payload = []
            for student in students:
                record = existing.get(student.id)
                if record is not None:
                    payload.append(HomeworkResultSerializer(record).data)
                else:
                    payload.append(
                        {
                            "id": None,
                            "homework": homework.id,
                            "homework_title": homework.title,
                            "student": student.id,
                            "student_name": str(student),
                            "status": HomeworkResult.Status.NOT_SUBMITTED,
                            "status_display": HomeworkResult.Status.NOT_SUBMITTED.label,
                            "score": None,
                            "comment": "",
                            "submitted_at": None,
                            "checked_at": None,
                            "created_at": None,
                            "updated_at": None,
                        }
                    )
            return Response(payload)

        _assert_homework_results_editable(request, homework.lesson)

        item_serializer = BulkHomeworkResultItemSerializer(data=request.data, many=True)
        item_serializer.is_valid(raise_exception=True)
        try:
            records = bulk_upsert_homework_results(homework, item_serializer.validated_data)
        except DjangoValidationError as exc:
            raise _as_drf_validation_error(exc)

        records_qs = HomeworkResult.objects.filter(pk__in=[r.pk for r in records]).select_related("student", "homework")
        return Response(HomeworkResultSerializer(records_qs, many=True).data, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(tags=["Homework"]),
    retrieve=extend_schema(tags=["Homework"]),
    create=extend_schema(tags=["Homework"]),
    update=extend_schema(tags=["Homework"]),
    partial_update=extend_schema(tags=["Homework"]),
    destroy=extend_schema(tags=["Homework"]),
)
class HomeworkResultViewSet(viewsets.ModelViewSet):
    serializer_class = HomeworkResultSerializer
    permission_classes = [IsAuthenticated, IsAdminOrOwningTeacher]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["homework", "student", "status"]
    search_fields = ["student__first_name", "student__last_name"]
    ordering_fields = ["created_at", "score"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = HomeworkResult.objects.select_related("student", "homework__lesson__group__teacher__user")
        user = self.request.user
        if _is_admin(user):
            return qs
        teacher = _teacher_profile(self.request)
        if teacher is None:
            return qs.none()
        # Only results of Homework belonging to Lessons this teacher
        # actually gives.
        return qs.filter(homework__lesson__in=Lesson.objects.for_teacher(teacher))

    def perform_create(self, serializer):
        homework = serializer.validated_data.get("homework")
        lesson = homework.lesson if homework is not None else None
        _assert_teacher_owns_lesson(self.request, lesson)
        _assert_homework_results_editable(self.request, lesson)
        serializer.save()

    def perform_update(self, serializer):
        _assert_homework_results_editable(self.request, serializer.instance.homework.lesson)
        serializer.save()


# ---------------------------------------------------------------------------
# Teacher availability — the Teacher counterpart of RoomViewSet.available:
# which active Teachers are free for a given date + time window, based on
# existing Lesson rows (mirrors the room check exactly, keyed on
# Lesson.effective_teacher instead of Lesson.room; a cancelled lesson never
# occupies a teacher, same as it never occupies a room).
# ---------------------------------------------------------------------------

class TeacherAvailabilityView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Teachers"],
        parameters=[TeacherAvailabilityRequestSerializer],
        responses=TeacherAvailabilitySerializer,
        description=(
            "Free vs. occupied teachers for a given date + time window, based on "
            "existing Lesson rows (any Lesson whose [start_time, end_time) "
            "overlaps the requested window occupies its effective teacher — "
            "Lesson.teacher if set, else its group's own teacher; cancelled "
            "lessons never occupy anyone)."
        ),
    )
    def get(self, request):
        params = TeacherAvailabilityRequestSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        date_ = params.validated_data["date"]
        start_time = params.validated_data["start_time"]
        end_time = params.validated_data["end_time"]

        overlapping_lessons = (
            Lesson.objects.filter(date=date_)
            .exclude(status=Lesson.Status.CANCELLED)
            .filter(start_time__lt=end_time, end_time__gt=start_time)
            .select_related("teacher__user", "group__teacher__user", "group")
        )

        occupied_teacher_ids = set()
        occupied = []
        for lesson in overlapping_lessons:
            teacher = lesson.effective_teacher
            if teacher is None:
                continue
            occupied_teacher_ids.add(teacher.id)
            occupied.append(
                {
                    "teacher": teacher.id,
                    "teacher_name": str(teacher),
                    "lesson": lesson.id,
                    "group": lesson.group_id,
                    "group_name": lesson.group.name,
                    "start_time": lesson.start_time,
                    "end_time": lesson.end_time,
                }
            )

        available_teachers = (
            Teacher.objects.filter(is_active=True)
            .exclude(id__in=occupied_teacher_ids)
            .select_related("user")
            .order_by("user__first_name")
        )

        payload = {
            "date": date_,
            "start_time": start_time,
            "end_time": end_time,
            "available": TeacherSerializer(available_teachers, many=True).data,
            "occupied": occupied,
        }
        return Response(TeacherAvailabilitySerializer(payload).data)


# ---------------------------------------------------------------------------
# Analytics — one read-only endpoint backed by services.analytics.get_dashboard.
# Every number is computed fresh from Lesson/Attendance/Homework/
# HomeworkResult/Student/Group/Teacher on each call; nothing here is
# persisted or kept in sync with anything (spec: read-only, calculation-based,
# no KPI tables).
# ---------------------------------------------------------------------------

_COMPARE_TRUE_ALIASES = {"true", "1", "yes"}
_COMPARE_FALSE_ALIASES = {"", "false", "0", "no"}


def _resolve_compare_mode(raw: str) -> str | None:
    """"true" is shorthand for "previous_period" (spec §5's `compare=true`
    example); blank/"false" means no comparison; anything else must be one
    of services.analytics.COMPARE_CHOICES (spec §2's named comparison
    modes)."""
    value = (raw or "").strip().lower()
    if value in _COMPARE_FALSE_ALIASES:
        return None
    if value in _COMPARE_TRUE_ALIASES:
        return "previous_period"
    if value in COMPARE_CHOICES:
        return value
    raise DRFValidationError({"compare": [f"Неизвестный режим сравнения: {raw!r}."]})


class AnalyticsDashboardView(APIView):
    """`GET /api/v1/analytics/dashboard/?period=&start_date=&end_date=&compare=&teacher=&group=&course=&subject=`

    Admin can see any slice (or everything, with no filters at all). A
    Teacher is always scoped to their own data — a `teacher` query param
    from a Teacher is ignored in favour of their own profile, and a `group`
    param for a group they don't teach comes back as an empty dashboard
    rather than another teacher's numbers.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Analytics"], parameters=[AnalyticsQuerySerializer], responses=AnalyticsDashboardSerializer)
    def get(self, request):
        params = AnalyticsQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = params.validated_data

        compare_mode = _resolve_compare_mode(data.get("compare", ""))
        if compare_mode == "custom" and not (data.get("compare_start_date") and data.get("compare_end_date")):
            raise DRFValidationError(
                {"compare_start_date": ["compare=custom требует compare_start_date и compare_end_date."]}
            )

        teacher_id = data["teacher"].id if data.get("teacher") else None
        group_id = data["group"].id if data.get("group") else None
        course_id = data["course"].id if data.get("course") else None
        subject_id = data["subject"].id if data.get("subject") else None

        if not _is_admin(request.user):
            teacher = _teacher_profile(request)
            # No id can ever be 0 — forcing this keeps every downstream
            # query empty instead of special-casing "no teacher profile".
            teacher_id = teacher.id if teacher is not None else 0
            if teacher is not None and group_id is not None and not Group.objects.for_teacher(teacher).filter(id=group_id).exists():
                group_id = 0

        dashboard = get_dashboard(
            period=data["period"],
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            compare=compare_mode,
            compare_start_date=data.get("compare_start_date"),
            compare_end_date=data.get("compare_end_date"),
            teacher_id=teacher_id,
            group_id=group_id,
            course_id=course_id,
            subject_id=subject_id,
        )
        return Response(dashboard)


# ---------------------------------------------------------------------------
# Monthly Teacher Reports
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(tags=["Monthly Reports"]),
    retrieve=extend_schema(tags=["Monthly Reports"]),
    create=extend_schema(tags=["Monthly Reports"], request=MonthlyTeacherReportCreateSerializer, responses=MonthlyTeacherReportSerializer),
    partial_update=extend_schema(tags=["Monthly Reports"], request=MonthlyTeacherReportCommentSerializer, responses=MonthlyTeacherReportSerializer),
)
class MonthlyTeacherReportViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """A Teacher's own once-a-month report (spec: "Один Teacher может иметь
    только один отчёт за один месяц" — `MonthlyTeacherReport`'s own
    unique_teacher_monthly_report constraint). A Teacher may only see and
    create/comment on their own reports; Admin may see every report but
    never creates or edits one — every figure besides `comment` is always
    computed, never entered (see .services.monthly_report)."""

    serializer_class = MonthlyTeacherReportSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["year", "month", "teacher"]
    ordering_fields = ["year", "month", "created_at"]
    ordering = ["-year", "-month"]

    def get_queryset(self):
        qs = MonthlyTeacherReport.objects.select_related("teacher__user").prefetch_related("teacher__subjects")
        if _is_admin(self.request.user):
            return qs
        teacher = _teacher_profile(self.request)
        if teacher is None:
            return qs.none()
        return qs.filter(teacher=teacher)

    def create(self, request, *args, **kwargs):
        if _is_admin(request.user):
            raise PermissionDenied("Отчёт создаёт только тренер — администратор может только просматривать.")
        teacher = _teacher_profile(request)
        if teacher is None:
            raise PermissionDenied("Профиль тренера не найден.")

        body = MonthlyTeacherReportCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        report, created = MonthlyTeacherReport.objects.get_or_create(
            teacher=teacher, year=body.validated_data["year"], month=body.validated_data["month"]
        )
        out = MonthlyTeacherReportSerializer(report, context=self.get_serializer_context()).data
        if created:
            return Response(out, status=status.HTTP_201_CREATED)
        # Not an error — the unique-per-month rule is a fact of the domain,
        # not a mistake the Teacher made; the frontend surfaces this as
        # "already exists, open it" rather than a validation failure.
        return Response({"detail": "exists", "report": out}, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        if not kwargs.get("partial", False):
            raise MethodNotAllowed("PUT")

        instance = self.get_object()
        if _is_admin(request.user):
            raise PermissionDenied("Администратор может только просматривать отчёты тренеров.")
        teacher = _teacher_profile(request)
        if teacher is None or instance.teacher_id != teacher.id:
            raise PermissionDenied("Вы можете редактировать только свой отчёт.")

        serializer = MonthlyTeacherReportCommentSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MonthlyTeacherReportSerializer(instance, context=self.get_serializer_context()).data)

    @extend_schema(tags=["Monthly Reports"], request=None, responses={200: {"type": "string", "format": "binary"}})
    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        report = self.get_object()
        pdf_bytes = build_monthly_report_pdf(report)
        filename = f"report-{report.teacher_id}-{report.year}-{report.month:02d}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


# ---------------------------------------------------------------------------
# Academy Monthly Reports — the Admin-only, whole-academy counterpart of the
# Monthly Teacher Report above (spec: "Это НЕ отчёт отдельного
# преподавателя. Это общий отчёт по всей академии"). A Teacher must never
# reach this data (spec §2) — enforced here on the backend via `IsAdmin`,
# never left to the frontend hiding a nav item/button.
# ---------------------------------------------------------------------------

@extend_schema_view(
    list=extend_schema(tags=["Academy Reports"]),
    retrieve=extend_schema(tags=["Academy Reports"]),
    create=extend_schema(tags=["Academy Reports"], request=AcademyMonthlyReportCreateSerializer, responses=AcademyMonthlyReportSerializer),
    partial_update=extend_schema(tags=["Academy Reports"], request=AcademyMonthlyReportCommentSerializer, responses=AcademyMonthlyReportSerializer),
)
class AcademyMonthlyReportViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """One report per calendar month for the whole academy (spec: "Не
    создавать два отчёта за один месяц" — `AcademyMonthlyReport`'s own
    unique_academy_monthly_report constraint). Admin-only end to end; every
    figure besides `comment` is always computed, never entered (see
    .services.academy_monthly_report)."""

    queryset = AcademyMonthlyReport.objects.all()
    serializer_class = AcademyMonthlyReportSerializer
    permission_classes = [IsAuthenticated, IsAdmin]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ["year", "month"]
    ordering_fields = ["year", "month", "created_at"]
    ordering = ["-year", "-month"]

    def create(self, request, *args, **kwargs):
        body = AcademyMonthlyReportCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        report, created = AcademyMonthlyReport.objects.get_or_create(
            year=body.validated_data["year"], month=body.validated_data["month"]
        )
        out = AcademyMonthlyReportSerializer(report, context=self.get_serializer_context()).data
        if created:
            return Response(out, status=status.HTTP_201_CREATED)
        # Not an error — the unique-per-month rule is a fact of the domain,
        # not a mistake the Admin made; the frontend surfaces this as
        # "already exists, open it" rather than a validation failure.
        return Response({"detail": "exists", "report": out}, status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        if not kwargs.get("partial", False):
            raise MethodNotAllowed("PUT")

        instance = self.get_object()
        serializer = AcademyMonthlyReportCommentSerializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AcademyMonthlyReportSerializer(instance, context=self.get_serializer_context()).data)

    @extend_schema(tags=["Academy Reports"], request=None, responses={200: {"type": "string", "format": "binary"}})
    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        report = self.get_object()
        pdf_bytes = build_academy_monthly_report_pdf(report)
        filename = f"academy-report-{report.year}-{report.month:02d}.pdf"
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
