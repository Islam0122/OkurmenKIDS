"""Assistant Workspace API — /api/v1/assistant/.

Thin views over the existing academy services: every write goes through
the same function the Django admin / Team Lead workspace uses, never a copy
of it here:

* student status — services.student_status (deactivate / pause /
  reactivate / continue);
* student's group — services.student_enrollment (enroll / transfer / add
  to group), which records the transfer in the student's history;
* a group's trainer + weekly slots — services.group_academic_config
  .save_program_config (GroupSchedule.clean(): trainer / room / group
  conflicts);
* a new group — services.group_setup.create_group (the above, chained);
* lessons — services.lesson_generator, services.lesson_move,
  services.lesson_reschedule.cancel_and_reschedule;
* attendance — services.attendance_service.bulk_mark_attendance;
* scholarships — apps.scholarships.services.generation (generate a period,
  add an award to a draft period). Approval and payments stay Admin's.

Every view requires an Admin or an active Assistant (IsAdminOrAssistant);
nothing here is reachable for a Trainer or a Team Lead. Objects are looked
up academy-wide by id on purpose — the Assistant's zone *is* the whole
academy's operations — and every write re-validates its target (an open
group, a student's current status) in the service layer.
"""
from __future__ import annotations

import datetime as dt

from django.contrib.admin.models import CHANGE, LogEntry
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academy.models import Group, GroupTeacher, Homework, Lesson, Student, StudentStatusEvent
from apps.academy.services import student_status
from apps.academy.services.attendance_service import bulk_mark_attendance
from apps.academy.services.group_academic_config import save_program_config
from apps.academy.services.group_setup import ProgramSpec, create_group
from apps.academy.services.lesson_generator import generate_lessons_for_group_with_report
from apps.academy.services.lesson_move import move_lesson
from apps.academy.services.lesson_reschedule import cancel_and_reschedule
from apps.academy.services.student_enrollment import add_students_to_group, enroll_student, transfer_student
from apps.scholarships.models import EligibilityStatus, ScholarshipAward, ScholarshipEvaluation, ScholarshipPeriod, ScholarshipRunLog
from apps.scholarships.services.generation import add_award, generate_period, get_active_configuration
from apps.scholarships.services.periods import latest_award_date
from apps.users.permissions import IsAdmin, IsAdminOrAssistant

from . import activity, monthly, monthly_pdf, records, selectors
from .serializers import (
    PAUSE,
    ActivateSerializer,
    AttendanceEntrySerializer,
    AwardAddSerializer,
    BulkActionSerializer,
    DeactivateSerializer,
    GenerateScholarshipSerializer,
    GroupCreateSerializer,
    GroupUpdateSerializer,
    LessonCancelSerializer,
    LessonMoveSerializer,
    ProgramSerializer,
    StudentCreateSerializer,
    StudentIdsSerializer,
    StudentUpdateSerializer,
    TransferSerializer,
)

TAGS = ["Assistant"]


def _drf_error(exc: DjangoValidationError) -> DRFValidationError:
    if hasattr(exc, "error_dict"):
        return DRFValidationError({key: DjangoValidationError(value).messages for key, value in exc.error_dict.items()})
    return DRFValidationError({"detail": exc.messages})


class _Pagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class AssistantView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrAssistant]

    def body(self, serializer_class, **kwargs):
        serializer = serializer_class(data=self.request.data, **kwargs)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def paginate(self, queryset, row):
        paginator = _Pagination()
        page = paginator.paginate_queryset(queryset, self.request, view=self)
        return paginator.get_paginated_response([row(item) for item in page])


def _parse_date(value, default: dt.date) -> dt.date:
    try:
        return dt.date.fromisoformat(value) if value else default
    except ValueError:
        raise DRFValidationError({"date": "Неверный формат даты (ожидается ГГГГ-ММ-ДД)."})


def _generation_summary(group: Group) -> dict:
    report = generate_lessons_for_group_with_report(group)
    return {
        "created": report.created,
        "updated": report.updated,
        "rescheduled": report.rescheduled,
        "expected": report.expected,
        "missing": report.missing,
        "warnings": report.warnings,
        "errors": report.errors,
    }


# ---------------------------------------------------------------------------
# Dashboard / reference data
# ---------------------------------------------------------------------------

@extend_schema(tags=TAGS, responses={200: dict})
class DashboardView(AssistantView):
    def get(self, request):
        return Response(selectors.dashboard())


@extend_schema(tags=TAGS, responses={200: dict})
class SearchView(AssistantView):
    """GET ?q= — students, groups, trainers and the coming week's lessons."""

    def get(self, request):
        return Response(selectors.search(request.query_params.get("q", "")))


@extend_schema(tags=TAGS, responses={200: dict})
class OptionsView(AssistantView):
    """Everything the workspace's forms pick from: courses (with subjects),
    trainers, rooms, open groups, weekdays, deactivation reasons."""

    def get(self, request):
        return Response(selectors.options())


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------

@extend_schema(tags=TAGS, request=GroupCreateSerializer, responses={200: dict})
class GroupListView(AssistantView):
    def get(self, request):
        qs = selectors.filter_groups(selectors.groups_queryset(), request.query_params)
        return self.paginate(qs, selectors.group_card)

    def post(self, request):
        data = self.body(GroupCreateSerializer)
        programs = [ProgramSpec(teacher=p["teacher"], subject=p["subject"], slots=p["slots"]) for p in data["programs"]]
        try:
            group = create_group(
                name=data["name"], course=data["course"], start_date=data["start_date"],
                end_date=data.get("end_date"), max_students=data.get("max_students"),
                description=data.get("description", ""), programs=programs, students=data["students"],
                user=request.user,
            )
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        payload = selectors.group_detail(group)
        if data["generate_lessons"] and programs:
            payload["generation"] = _generation_summary(group)
        return Response(payload, status=status.HTTP_201_CREATED)


@extend_schema(tags=TAGS, request=GroupUpdateSerializer, responses={200: dict})
class GroupDetailView(AssistantView):
    def get(self, request, pk):
        return Response(selectors.group_detail(get_object_or_404(Group, pk=pk)))

    def patch(self, request, pk):
        group = get_object_or_404(Group, pk=pk)
        data = self.body(GroupUpdateSerializer)
        before = {field: getattr(group, field) for field in data}
        for field, value in data.items():
            setattr(group, field, value)
        try:
            group.full_clean()
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        with transaction.atomic():
            group.save()
            changed = [f"{field}: {before[field]} → {value}" for field, value in data.items() if before[field] != value]
            if changed:
                LogEntry.objects.log_actions(
                    user_id=request.user.pk, queryset=[group], action_flag=CHANGE,
                    change_message="Изменено: " + "; ".join(changed), single_object=True,
                )
        return Response(selectors.group_detail(group))


@extend_schema(tags=TAGS, request=StudentIdsSerializer, responses={200: dict})
class GroupStudentsView(AssistantView):
    """Add existing students to the group (each one gets a history event)."""

    def post(self, request, pk):
        group = get_object_or_404(Group, pk=pk)
        data = self.body(StudentIdsSerializer)
        try:
            events = add_students_to_group(group, data["students"], event_date=data.get("event_date"),
                                           comment=data["comment"], performed_by=request.user)
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        return Response({"added": len(events), "group": selectors.group_detail(group)})


@extend_schema(tags=TAGS, request=ProgramSerializer, responses={200: dict})
class GroupProgramView(AssistantView):
    """Create or change one Teaching Program of the group — trainer, subject
    and its exact list of weekly slots — through the Team Lead's own
    «Учебная конфигурация» service. A slot clashing with the trainer's, the
    room's or the group's other slots is refused with the clash named."""

    def post(self, request, pk):
        group = get_object_or_404(Group, pk=pk)
        data = self.body(ProgramSerializer)
        program = None
        if data.get("program"):
            program = get_object_or_404(GroupTeacher, pk=data["program"], group=group)
        try:
            save_program_config(group, user=request.user, teacher=data["teacher"], subject=data["subject"],
                                slot_items=data["slots"], program=program)
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        return Response(selectors.group_detail(group))


@extend_schema(tags=TAGS, request=None, responses={200: dict})
class GroupGenerateLessonsView(AssistantView):
    def post(self, request, pk):
        group = get_object_or_404(Group, pk=pk)
        summary = _generation_summary(group)
        if summary["errors"] and not (summary["created"] or summary["updated"] or summary["rescheduled"]):
            raise DRFValidationError({"detail": summary["errors"]})
        return Response(summary)


# ---------------------------------------------------------------------------
# Students
# ---------------------------------------------------------------------------

@extend_schema(tags=TAGS, request=StudentCreateSerializer, responses={200: dict})
class StudentListView(AssistantView):
    def get(self, request):
        qs = selectors.filter_students(selectors.students_queryset(), request.query_params)
        return self.paginate(qs, selectors.student_row)

    def post(self, request):
        data = self.body(StudentCreateSerializer)
        try:
            student = enroll_student(
                first_name=data["first_name"], last_name=data["last_name"], phone=data["phone"],
                parent_phone=data["parent_phone"], group=data["group"],
                enrollment_date=data.get("enrollment_date"), performed_by=request.user,
            )
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        return Response(selectors.student_detail(student), status=status.HTTP_201_CREATED)


@extend_schema(tags=TAGS, request=StudentUpdateSerializer, responses={200: dict})
class StudentDetailView(AssistantView):
    def get(self, request, pk):
        return Response(selectors.student_detail(get_object_or_404(Student, pk=pk)))

    def patch(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        data = self.body(StudentUpdateSerializer)
        before = {field: getattr(student, field) for field in data}
        for field, value in data.items():
            setattr(student, field, value.strip() if isinstance(value, str) else value)
        try:
            student.full_clean()
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        with transaction.atomic():
            student.save()
            changed = [f"{field}: {before[field] or '—'} → {getattr(student, field) or '—'}"
                       for field in data if before[field] != getattr(student, field)]
            if changed:
                LogEntry.objects.log_actions(
                    user_id=request.user.pk, queryset=[student], action_flag=CHANGE,
                    change_message="Изменено: " + "; ".join(changed), single_object=True,
                )
        return Response(selectors.student_detail(student))


def _deactivate(student: Student, data: dict, user) -> StudentStatusEvent:
    """«Деактивировать» with reason «Пауза» is a pause (the student is
    expected back), any other reason a withdrawal."""
    if data["reason"] == PAUSE:
        return student_status.pause_student(
            student, reason=StudentStatusEvent.Reason.WILL_CONTINUE_LATER, comment=data.get("comment", ""),
            expected_return_date=data.get("expected_return_date"), event_date=data.get("event_date"),
            performed_by=user,
        )
    return student_status.deactivate_student(
        student, reason=data["reason"], comment=data.get("comment", ""), event_date=data.get("event_date"),
        performed_by=user,
    )


def _activate(student: Student, data: dict, user) -> StudentStatusEvent:
    """Back to ACTIVE: from a pause (continue_student — the group is
    optional) or from a withdrawal (reactivate_student — the group is
    required)."""
    student.refresh_from_db(fields=["status", "group"])
    group = data.get("group")
    if student.status == Student.Status.PAUSED:
        return student_status.continue_student(
            student, group=group, event_date=data.get("event_date"), comment=data.get("comment", ""),
            performed_by=user,
        )
    if student.status == Student.Status.WITHDRAWN:
        if group is not None and group.status not in (Group.Status.ACTIVE, Group.Status.PAUSED):
            raise DjangoValidationError({"group": f"Группа «{group.name}» закрыта — выберите другую."})
        return student_status.reactivate_student(
            student, group=group, event_date=data.get("event_date") or timezone.localdate(),
            comment=data.get("comment", ""), performed_by=user,
        )
    raise DjangoValidationError(f"Студент «{student}» — {student.get_status_display().lower()}: активировать нечего.")


class _StudentActionView(AssistantView):
    serializer_class = None

    def act(self, student, data):  # pragma: no cover - overridden
        raise NotImplementedError

    def post(self, request, pk):
        student = get_object_or_404(Student, pk=pk)
        data = self.body(self.serializer_class)
        try:
            self.act(student, data)
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        return Response(selectors.student_detail(student))


@extend_schema(tags=TAGS, request=DeactivateSerializer, responses={200: dict})
class StudentDeactivateView(_StudentActionView):
    """Never deletes the student: their status changes (withdrawn, or paused
    for reason «Пауза») and the history keeps why and when."""

    serializer_class = DeactivateSerializer

    def act(self, student, data):
        return _deactivate(student, data, self.request.user)


@extend_schema(tags=TAGS, request=ActivateSerializer, responses={200: dict})
class StudentActivateView(_StudentActionView):
    serializer_class = ActivateSerializer

    def act(self, student, data):
        return _activate(student, data, self.request.user)


@extend_schema(tags=TAGS, request=TransferSerializer, responses={200: dict})
class StudentTransferView(_StudentActionView):
    serializer_class = TransferSerializer

    def act(self, student, data):
        return transfer_student(student, group=data["group"], event_date=data.get("event_date"),
                                comment=data["comment"], performed_by=self.request.user)


@extend_schema(tags=TAGS, request=BulkActionSerializer, responses={200: dict})
class StudentBulkView(AssistantView):
    """One workflow for several selected students. Each student is handled
    on their own (a paused one can't be «deactivated», a withdrawn one can't
    be transferred) and the response says, per student, what happened — one
    refusal never undoes the others."""

    def post(self, request):
        data = self.body(BulkActionSerializer)
        action = data["action"]
        results = []
        for student in data["students"]:
            try:
                with transaction.atomic():
                    if action in ("transfer", "add_to_group"):
                        transfer_student(student, group=data["group"], event_date=data.get("event_date"),
                                         comment=data["comment"], performed_by=request.user)
                    elif action == "deactivate":
                        _deactivate(student, data, request.user)
                    elif action == "activate":
                        _activate(student, data, request.user)
                results.append({"id": student.pk, "name": str(student), "ok": True})
            except DjangoValidationError as exc:
                results.append({"id": student.pk, "name": str(student), "ok": False, "error": " ".join(exc.messages)})
        done = sum(1 for r in results if r["ok"])
        return Response({"done": done, "failed": len(results) - done, "results": results})


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

@extend_schema(tags=TAGS, responses={200: dict})
class ScheduleView(AssistantView):
    """Lessons between ?start= and ?end= (inclusive, max 62 days; default:
    this week), optionally ?group= / ?teacher=, plus the weekly slots'
    current conflicts."""

    def get(self, request):
        today = timezone.localdate()
        start = _parse_date(request.query_params.get("start"), today - dt.timedelta(days=today.weekday()))
        end = _parse_date(request.query_params.get("end"), start + dt.timedelta(days=6))
        if end < start or (end - start).days > 62:
            raise DRFValidationError({"end": "Диапазон — от 1 до 62 дней."})
        return Response({
            "start": start,
            "end": end,
            "lessons": selectors.lessons_between(start, end, request.query_params),
            "conflicts": selectors.schedule_conflicts(),
        })


@extend_schema(tags=TAGS, request=LessonMoveSerializer, responses={200: dict})
class LessonMoveView(AssistantView):
    def post(self, request, pk):
        lesson = get_object_or_404(Lesson.objects.select_related("group", "room"), pk=pk)
        data = self.body(LessonMoveSerializer)
        try:
            move_lesson(lesson, date=data["date"], start_time=data["start_time"], end_time=data["end_time"],
                        user=request.user)
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        moved = selectors.lessons_between(lesson.date, lesson.date, {"group": lesson.group_id})
        return Response(next((row for row in moved if row["id"] == lesson.pk), {}))


@extend_schema(tags=TAGS, request=LessonCancelSerializer, responses={200: dict})
class LessonCancelView(AssistantView):
    """Cancel a lesson; by default its topic moves to the next free
    occurrence of its program (services.lesson_reschedule)."""

    def post(self, request, pk):
        lesson = get_object_or_404(Lesson, pk=pk)
        data = self.body(LessonCancelSerializer)
        try:
            lesson, result = cancel_and_reschedule(lesson, request.user, reason=data["reason"],
                                                   reschedule=data["reschedule"])
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        payload = {"id": lesson.pk, "status": lesson.status, "rescheduled_to": None, "warning": ""}
        if result is not None:
            if result.makeup is not None:
                payload["rescheduled_to"] = {"id": result.makeup.pk, "date": result.makeup.date,
                                             "start": result.makeup.start_time.strftime("%H:%M")}
            payload["warning"] = result.warning
        return Response(payload)


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

@extend_schema(tags=TAGS, responses={200: dict})
class AttendanceDayView(AssistantView):
    def get(self, request):
        day = _parse_date(request.query_params.get("date"), timezone.localdate())
        return Response({"date": day, "lessons": selectors.attendance_for_day(day, request.query_params)})


@extend_schema(tags=TAGS, request=AttendanceEntrySerializer(many=True), responses={200: dict})
class AttendanceLessonView(AssistantView):
    """Mark or correct a lesson's attendance (the trainer's own bulk-marking
    service) — Admin only. For an Assistant attendance is read-only (403):
    it is the trainer's record. Not for a cancelled lesson; every save is
    logged."""

    permission_classes = [IsAuthenticated, IsAdmin]

    def post(self, request, pk):
        lesson = get_object_or_404(Lesson, pk=pk)
        if lesson.status == Lesson.Status.CANCELLED:
            raise DRFValidationError({"detail": "Занятие отменено — посещаемость не отмечается."})
        entries = AttendanceEntrySerializer(data=request.data, many=True)
        entries.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                records = bulk_mark_attendance(lesson, entries.validated_data)
                LogEntry.objects.log_actions(
                    user_id=request.user.pk, queryset=[lesson], action_flag=CHANGE,
                    change_message=f"Посещаемость отмечена/исправлена ассистентом: {len(records)} студ.",
                    single_object=True,
                )
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        day = selectors.attendance_for_day(lesson.date, {"group": lesson.group_id})
        return Response(next((row for row in day if row["id"] == lesson.pk), {}))


# ---------------------------------------------------------------------------
# Scholarships
# ---------------------------------------------------------------------------

def _period_row(period: ScholarshipPeriod) -> dict:
    awards = list(period.awards.select_related("student__group", "evaluation").order_by("rank"))
    return {
        "id": period.pk,
        "title": str(period),
        "period_start": period.period_start,
        "period_end": period.period_end,
        "evaluation_date": period.evaluation_date,
        "status": period.status,
        "status_display": period.get_status_display(),
        "max_recipients": period.max_recipients,
        "award_amount": str(period.award_amount) if period.award_amount is not None else None,
        "awards": [
            {
                "id": a.pk,
                "student": {"id": a.student_id, "name": str(a.student)},
                "group": a.student.group.name if a.student.group_id else "",
                "rank": a.rank,
                "score": str(a.evaluation.overall_score) if a.evaluation.overall_score is not None else None,
                "amount": str(a.amount),
                "status": a.status,
                "status_display": a.get_status_display(),
                "payment_status": a.payment_status,
                "payment_status_display": a.get_payment_status_display(),
            }
            for a in awards
        ],
    }


@extend_schema(tags=TAGS, responses={200: dict})
class ScholarshipListView(AssistantView):
    def get(self, request):
        periods = ScholarshipPeriod.objects.order_by("-period_start", "-award_day")[:12]
        try:
            config = get_active_configuration()
            award_days = list(config.award_days)
        except DjangoValidationError:
            award_days = []
        return Response({
            "award_days": award_days,
            "pending": ScholarshipAward.objects.filter(status=ScholarshipAward.Status.PENDING).count(),
            "periods": [_period_row(p) for p in periods],
        })


@extend_schema(tags=TAGS, request=GenerateScholarshipSerializer, responses={200: dict})
class ScholarshipGenerateView(AssistantView):
    """Form (calculate) the scholarship period of the latest finished cycle
    — the same idempotent generation the Admin runs. The result is a draft
    for the Admin to approve (unless the settings auto-approve)."""

    def post(self, request):
        data = self.body(GenerateScholarshipSerializer)
        try:
            config = get_active_configuration()
            award_day = data.get("award_day") or (config.award_days[0] if config.award_days else None)
            if award_day is None:
                raise DjangoValidationError("В настройках стипендии не задан день начисления.")
            award_date = data.get("award_date") or latest_award_date(award_day, timezone.localdate())
            result = generate_period(award_date, award_day, user=request.user, trigger=ScholarshipRunLog.Trigger.API)
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        return Response({"created": result.created, "period": _period_row(result.period)},
                        status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK)


@extend_schema(tags=TAGS, request=AwardAddSerializer, responses={200: dict})
class ScholarshipPeriodAwardsView(AssistantView):
    """GET: eligible students of the period who have no scholarship yet.
    POST {evaluation}: give one of them a scholarship by hand (draft period
    only, within the limit)."""

    def get(self, request, pk):
        period = get_object_or_404(ScholarshipPeriod, pk=pk)
        candidates = (
            ScholarshipEvaluation.objects.filter(period=period, eligibility_status=EligibilityStatus.ELIGIBLE,
                                                 award__isnull=True)
            .order_by("rank", "student_name")
        )
        return Response([
            {"id": e.pk, "student_id": e.student_id, "student_name": e.student_name, "group_name": e.group_name,
             "rank": e.rank, "overall_score": str(e.overall_score) if e.overall_score is not None else None}
            for e in candidates
        ])

    def post(self, request, pk):
        period = get_object_or_404(ScholarshipPeriod, pk=pk)
        data = self.body(AwardAddSerializer)
        evaluation = get_object_or_404(ScholarshipEvaluation, pk=data["evaluation"], period=period)
        try:
            add_award(period, evaluation, user=request.user, trigger=ScholarshipRunLog.Trigger.API)
        except DjangoValidationError as exc:
            raise _drf_error(exc)
        return Response(_period_row(period), status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Read-only records: attendance & homework of a group, «Контроль активности»
# ---------------------------------------------------------------------------

@extend_schema(tags=TAGS, responses={200: dict})
class GroupAttendanceView(AssistantView):
    """GET — a group's attendance: summary, held lessons, students.
    ?period=today|week|month|all|custom (&start=&end=), ?student=, ?teacher=,
    ?status=present|absent|late|excused|unmarked."""

    def get(self, request, pk):
        return Response(records.group_attendance(get_object_or_404(Group, pk=pk), request.query_params))


@extend_schema(tags=TAGS, responses={200: dict})
class GroupHomeworkView(AssistantView):
    """GET — a group's homework: summary and the list (same filters as
    attendance; ?status=open|review|complete|missing)."""

    def get(self, request, pk):
        return Response(records.group_homework(get_object_or_404(Group, pk=pk), request.query_params))


@extend_schema(tags=TAGS, responses={200: dict})
class LessonDetailView(AssistantView):
    """GET — one lesson: marks of every student and its homework."""

    def get(self, request, pk):
        lesson = get_object_or_404(Lesson.objects.select_related(*records.LESSON_RELATED), pk=pk)
        return Response(records.lesson_detail(lesson))


@extend_schema(tags=TAGS, responses={200: dict})
class HomeworkDetailView(AssistantView):
    """GET — one homework: its lesson, stats and every student's result."""

    def get(self, request, pk):
        return Response(records.homework_detail(get_object_or_404(Homework, pk=pk)))


@extend_schema(tags=TAGS, responses={200: dict})
class ControlView(AssistantView):
    """GET — «Контроль активности»: who stops attending / doing homework.
    ?period=7d|14d|30d|month|all (default 30d), ?group=, ?category=, ?sort=."""

    def get(self, request):
        return Response(activity.control_overview(request.query_params))


@extend_schema(tags=TAGS, responses={200: dict})
class ControlStudentView(AssistantView):
    """GET — one student's activity profile and timeline (?period=)."""

    def get(self, request, pk):
        student = get_object_or_404(Student.objects.select_related("group"), pk=pk)
        return Response(activity.student_profile(student, request.query_params.get("period", "30d")))


def _report_filters(params) -> dict:
    """Departure filters: ?group=&teacher=&reason= (a reason code or «unknown»)."""
    def as_int(key):
        value = params.get(key)
        return int(value) if value and str(value).isdigit() else None
    reason = params.get("reason") or None
    if reason and reason != "unknown" and reason not in StudentStatusEvent.Reason.values:
        reason = None
    return {"group": as_int("group"), "teacher": as_int("teacher"), "reason": reason}


def _monthly_report(year, month, request=None):
    """The one source for the page and the PDF: (report, None) or (None, 400)."""
    try:
        return monthly.monthly_report(
            int(year), int(month),
            filters=_report_filters(request.query_params) if request else None,
        ), None
    except (TypeError, ValueError, monthly.ReportError) as exc:
        message = str(exc) if isinstance(exc, monthly.ReportError) else "Неверный месяц или год."
        return None, Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(tags=TAGS, responses={200: dict})
class MonthlyReportView(AssistantView):
    """GET — «Месячный отчёт» for ?year=&month= (default: the current month).
    Computed on demand from existing data, read only: requesting it again
    is «Обновить». Nothing about trainers — that is the Team Lead's report."""

    def get(self, request):
        today = timezone.localdate()
        report, error = _monthly_report(request.query_params.get("year") or today.year,
                                        request.query_params.get("month") or today.month, request)
        return error or Response(report)


@extend_schema(tags=TAGS, responses={200: {"type": "string", "format": "binary"}})
class MonthlyReportPdfView(AssistantView):
    """GET — the same «Месячный отчёт» as an A4 PDF attachment
    (monthly_report_<month>_<year>.pdf). Same data, same permission."""

    def get(self, request, year, month):
        report, error = _monthly_report(year, month, request)
        if error:
            return error
        response = HttpResponse(monthly_pdf.build_monthly_pdf(report), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{monthly_pdf.pdf_filename(report["year"], report["month"])}"'
        response["Cache-Control"] = "no-store"
        return response
