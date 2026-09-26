from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.academy.models import Student

from .models import (
    EligibilityStatus,
    ScholarshipAward,
    ScholarshipEvaluation,
    ScholarshipPeriod,
    ScholarshipRunLog,
    TrainerFeedback,
)
from .permissions import (
    IsAdminOrTeacher,
    IsAdminOrTeacherReadOnly,
    IsScholarshipAdmin,
    can_manage,
    is_admin,
    teacher_profile,
)
from .serializers import (
    AwardAddSerializer,
    AwardSerializer,
    EvaluationDetailSerializer,
    EvaluationListSerializer,
    GenerateRequestSerializer,
    PeriodWriteSerializer,
    RequiredFeedbackSerializer,
    ScholarshipPeriodSerializer,
    TeacherPeriodSerializer,
    TrainerFeedbackSerializer,
)
from .services import analytics
from .services.feedback import required_feedback, validate_feedback_target
from .services.generation import (
    add_award,
    approve_period,
    create_period,
    generate_period,
    get_active_configuration,
    recalculate_period,
    remove_award,
    update_period,
)
from .services.periods import latest_award_date

TAGS = ["Scholarships"]


def _as_drf_error(exc: DjangoValidationError) -> DRFValidationError:
    return DRFValidationError({"detail": exc.messages})


@extend_schema_view(
    list=extend_schema(tags=TAGS),
    retrieve=extend_schema(tags=TAGS),
    create=extend_schema(tags=TAGS, request=PeriodWriteSerializer, responses=ScholarshipPeriodSerializer),
    partial_update=extend_schema(tags=TAGS, request=PeriodWriteSerializer, responses=ScholarshipPeriodSerializer),
)
class ScholarshipPeriodViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Scholarship periods — the container of everything else. Admin sees
    everything and may create/edit periods; a Teacher only the period
    dates/status (to know where feedback is due)."""

    permission_classes = [IsAuthenticated, IsAdminOrTeacherReadOnly]
    filterset_fields = ["status", "award_day"]
    ordering_fields = ["period_start", "evaluation_date"]
    ordering = ["-period_start", "-award_day"]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = ScholarshipPeriod.objects.all()
        if is_admin(self.request.user):
            qs = analytics.annotate_periods(qs)
        return qs

    def get_serializer_class(self):
        if self.action in ("create", "partial_update"):
            return PeriodWriteSerializer
        return ScholarshipPeriodSerializer if is_admin(self.request.user) else TeacherPeriodSerializer

    def _require(self, action_name: str) -> None:
        if not can_manage(self.request.user, action_name):
            raise PermissionDenied("Недостаточно прав для этого действия.")

    def _period_response(self, period, status_code=status.HTTP_200_OK):
        return Response(ScholarshipPeriodSerializer(self.get_queryset().get(pk=period.pk)).data, status=status_code)

    def create(self, request, *args, **kwargs):
        self._require("generate")
        body = PeriodWriteSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            period = create_period(**body.validated_data, user=request.user, trigger=ScholarshipRunLog.Trigger.API)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return self._period_response(period, status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        if not kwargs.get("partial"):
            raise DRFValidationError({"detail": ["Используйте PATCH."]})
        self._require("generate")
        period = self.get_object()
        body = PeriodWriteSerializer(period, data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        try:
            period = update_period(period, **body.validated_data, user=request.user, trigger=ScholarshipRunLog.Trigger.API)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return self._period_response(period)

    @extend_schema(tags=TAGS, request=AwardAddSerializer, responses=AwardSerializer)
    @action(detail=True, methods=["post"], url_path="awards", permission_classes=[IsAuthenticated, IsScholarshipAdmin])
    def add_award(self, request, pk=None):
        """Give an eligible student of a draft period a scholarship by hand
        (refused once the limit is reached)."""
        self._require("generate")
        period = self.get_object()
        body = AwardAddSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            award = add_award(period, body.validated_data["evaluation"], user=request.user,
                              trigger=ScholarshipRunLog.Trigger.API)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(AwardSerializer(award).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=TAGS, request=None, responses={204: None})
    @action(detail=True, methods=["delete"], url_path=r"awards/(?P<award_id>\d+)",
            permission_classes=[IsAuthenticated, IsScholarshipAdmin])
    def remove_award(self, request, pk=None, award_id=None):
        self._require("generate")
        period = self.get_object()
        award = get_object_or_404(ScholarshipAward, pk=award_id, period=period)
        try:
            remove_award(period, award, user=request.user, trigger=ScholarshipRunLog.Trigger.API)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(tags=TAGS, request=GenerateRequestSerializer, responses=ScholarshipPeriodSerializer)
    @action(detail=False, methods=["post"], permission_classes=[IsAuthenticated, IsScholarshipAdmin])
    def generate(self, request):
        self._require("generate")
        body = GenerateRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        award_day = body.validated_data["award_day"]
        award_date = body.validated_data.get("award_date") or latest_award_date(award_day, timezone.localdate())
        try:
            result = generate_period(award_date, award_day, user=request.user, trigger=ScholarshipRunLog.Trigger.API)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        data = ScholarshipPeriodSerializer(self.get_queryset().get(pk=result.period.pk)).data
        if result.created:
            return Response(data, status=status.HTTP_201_CREATED)
        return Response({"detail": "exists", "period": data}, status=status.HTTP_200_OK)

    @extend_schema(tags=TAGS, request=None, responses=ScholarshipPeriodSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsScholarshipAdmin])
    def recalculate(self, request, pk=None):
        self._require("generate")
        period = self.get_object()
        try:
            recalculate_period(period, user=request.user, trigger=ScholarshipRunLog.Trigger.API)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(ScholarshipPeriodSerializer(self.get_queryset().get(pk=period.pk)).data)

    @extend_schema(tags=TAGS, request=None, responses=ScholarshipPeriodSerializer)
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsScholarshipAdmin])
    def approve(self, request, pk=None):
        self._require("approve")
        period = self.get_object()
        try:
            approve_period(period, user=request.user, trigger=ScholarshipRunLog.Trigger.API)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        return Response(ScholarshipPeriodSerializer(self.get_queryset().get(pk=period.pk)).data)

    @extend_schema(tags=TAGS, responses=EvaluationListSerializer(many=True))
    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated, IsScholarshipAdmin])
    def ranking(self, request, pk=None):
        period = self.get_object()
        qs = analytics.ranking_queryset(period)
        if request.query_params.get("eligible") == "true":
            qs = qs.filter(eligibility_status=EligibilityStatus.ELIGIBLE)
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(EvaluationListSerializer(page, many=True).data)

    @extend_schema(tags=TAGS, responses={200: dict})
    @action(detail=True, methods=["get"], permission_classes=[IsAuthenticated, IsScholarshipAdmin])
    def analytics(self, request, pk=None):
        return Response(analytics.period_analytics(self.get_object()))

    @extend_schema(tags=TAGS, responses={200: {"type": "string", "format": "binary"}})
    @action(detail=True, methods=["get"], url_path="export", permission_classes=[IsAuthenticated, IsScholarshipAdmin])
    def export(self, request, pk=None):
        period = self.get_object()
        response = HttpResponse(analytics.export_ranking_csv(period), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="scholarship-{period.period_start}-{period.period_end}.csv"'
        return response

    @extend_schema(tags=TAGS, responses={200: dict})
    @action(detail=False, methods=["get"], url_path="summary", permission_classes=[IsAuthenticated, IsScholarshipAdmin])
    def summary(self, request):
        """Awards by month across all periods, plus the active configuration."""
        try:
            config = get_active_configuration()
            config_data = {
                "name": config.name,
                "award_mode": config.award_mode,
                "award_days": list(config.award_days),
                "max_recipients": config.max_recipients,
                "weights": {
                    "attendance": config.attendance_weight,
                    "homework": config.homework_weight,
                    "feedback": config.feedback_weight,
                },
                "subject_aggregation": config.subject_aggregation,
                "auto_approve": config.auto_approve,
            }
        except DjangoValidationError as exc:
            config_data = {"error": exc.messages}
        return Response({"configuration": config_data, "awards_by_month": analytics.awards_by_month()})


@extend_schema_view(
    list=extend_schema(tags=TAGS, parameters=[
        OpenApiParameter("period", int), OpenApiParameter("student", int), OpenApiParameter("eligibility_status", str),
    ]),
    retrieve=extend_schema(tags=TAGS),
)
class ScholarshipEvaluationViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, IsScholarshipAdmin]
    filterset_fields = ["period", "student", "eligibility_status"]
    search_fields = ["student_name", "group_name"]
    ordering_fields = ["rank", "overall_score", "student_name"]
    ordering = ["period", "rank", "student_name"]

    def get_queryset(self):
        return ScholarshipEvaluation.objects.select_related("period", "award").prefetch_related("subject_scores")

    def get_serializer_class(self):
        return EvaluationDetailSerializer if self.action in ("retrieve", "student_history") else EvaluationListSerializer

    @extend_schema(tags=TAGS, responses=EvaluationDetailSerializer(many=True))
    @action(detail=False, methods=["get"], url_path=r"student/(?P<student_id>\d+)")
    def student_history(self, request, student_id=None):
        """Every evaluation (with subject breakdown) of one student, newest first."""
        student = get_object_or_404(Student, pk=student_id)
        qs = self.get_queryset().filter(student=student).order_by("-period__period_start", "-period__award_day")
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(EvaluationDetailSerializer(page, many=True).data)


@extend_schema_view(list=extend_schema(tags=TAGS), retrieve=extend_schema(tags=TAGS))
class ScholarshipAwardViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AwardSerializer
    permission_classes = [IsAuthenticated, IsScholarshipAdmin]
    filterset_fields = ["period", "student", "status"]
    ordering = ["-award_date", "rank"]

    def get_queryset(self):
        return ScholarshipAward.objects.select_related("evaluation")


@extend_schema_view(
    list=extend_schema(tags=TAGS),
    retrieve=extend_schema(tags=TAGS),
    create=extend_schema(tags=TAGS),
    partial_update=extend_schema(tags=TAGS),
    update=extend_schema(tags=TAGS),
)
class TrainerFeedbackViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Trainer feedback. A Teacher only ever sees and writes their own
    feedback, for students they taught in that period; an Admin can review
    and correct any of it. Nothing here can touch awards."""

    serializer_class = TrainerFeedbackSerializer
    permission_classes = [IsAuthenticated, IsAdminOrTeacher]
    filterset_fields = ["period", "student", "subject", "teacher"]
    ordering = ["-period__period_start", "student__last_name", "subject__name"]

    def get_queryset(self):
        qs = TrainerFeedback.objects.select_related("student", "subject", "teacher__user", "period")
        if is_admin(self.request.user):
            return qs
        return qs.filter(teacher=teacher_profile(self.request.user))

    def _resolve_teacher(self, data):
        if is_admin(self.request.user):
            teacher = data.get("teacher")
            if teacher is None:
                raise DRFValidationError({"teacher": ["Укажите тренера, от имени которого вносится оценка."]})
            return teacher
        return teacher_profile(self.request.user)

    def _validate_target(self, *, period, teacher, student, subject, exclude_id=None):
        try:
            validate_feedback_target(period=period, teacher=teacher, student=student, subject=subject)
        except DjangoValidationError as exc:
            raise _as_drf_error(exc)
        duplicate = TrainerFeedback.objects.filter(period=period, teacher=teacher, student=student, subject=subject)
        if exclude_id:
            duplicate = duplicate.exclude(pk=exclude_id)
        if duplicate.exists():
            raise DRFValidationError({"detail": ["Оценка по этому студенту и предмету уже внесена — отредактируйте её."]})

    def perform_create(self, serializer):
        data = serializer.validated_data
        teacher = self._resolve_teacher(data)
        self._validate_target(period=data["period"], teacher=teacher, student=data["student"], subject=data["subject"])
        try:
            with transaction.atomic():
                serializer.save(teacher=teacher, created_by=self.request.user, updated_by=self.request.user)
        except IntegrityError:
            raise DRFValidationError({"detail": ["Оценка по этому студенту и предмету уже внесена."]})

    def perform_update(self, serializer):
        instance = serializer.instance
        data = serializer.validated_data
        if not is_admin(self.request.user):
            # A Teacher edits only the scores/comment of their own row —
            # never re-targets it to another student/subject/period.
            for key in ("period", "student", "subject", "teacher"):
                data.pop(key, None)
        teacher = data.get("teacher", instance.teacher)
        self._validate_target(
            period=data.get("period", instance.period),
            teacher=teacher,
            student=data.get("student", instance.student),
            subject=data.get("subject", instance.subject),
            exclude_id=instance.pk,
        )
        serializer.save(updated_by=self.request.user)

    @extend_schema(
        tags=TAGS,
        parameters=[OpenApiParameter("period", int, required=True)],
        responses=RequiredFeedbackSerializer(many=True),
    )
    @action(detail=False, methods=["get"], url_path="required")
    def required(self, request):
        """The logged-in Teacher's to-do list for a period: every student and
        subject they taught, with the feedback already given (if any)."""
        teacher = teacher_profile(request.user)
        if teacher is None:
            raise PermissionDenied("Список обязательных оценок доступен только тренеру.")
        period_id = request.query_params.get("period")
        if not period_id or not str(period_id).isdigit():
            raise DRFValidationError({"period": ["Укажите период."]})
        period = get_object_or_404(ScholarshipPeriod, pk=period_id)
        items = required_feedback(teacher, period)
        return Response({
            "period": TeacherPeriodSerializer(period).data,
            "total": len(items),
            "missing": sum(1 for item in items if not item.is_submitted),
            "items": RequiredFeedbackSerializer(items, many=True).data,
        })
