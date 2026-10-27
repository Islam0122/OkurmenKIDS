"""API HR-кабинета (/api/v1/hr/…): вакансии, кандидаты, собеседования,
главная и кадровые отчёты. Только HR-менеджер (`IsHRManager`): контакты и
заметки кандидатов другим ролям недоступны. Сотрудники — apps.users.hr."""
from __future__ import annotations

from datetime import date

from django.db.models import Count, Min, OuterRef, Subquery
from django.http import HttpResponse
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.hr import HREmployeeCreateSerializer, HRPagination
from apps.users.models import User
from apps.users.permissions import IsHRManager

from .models import Candidate, HRActivity, Interview, Vacancy
from .serializers import (
    ActivitySerializer,
    CancelSerializer,
    CandidateSerializer,
    CandidateWriteSerializer,
    InterviewCreateSerializer,
    InterviewSerializer,
    InterviewUpdateSerializer,
    NoteSerializer,
    ResultSerializer,
    StatusChangeSerializer,
    VacancySerializer,
    person,
)
from .services import activity, pipeline, reports

TAGS = ["HR"]
PERMISSIONS = [IsAuthenticated, IsHRManager]
CALENDAR_MAX_DAYS = 62


def error_response(exc: pipeline.RecruitmentError) -> Response:
    return Response({"detail": exc.message, "code": exc.code, **exc.extra}, status=exc.status)


def bad_request(message: str) -> Response:
    return Response({"detail": message, "code": "invalid_params"}, status=status.HTTP_400_BAD_REQUEST)


def parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def report_filters(params) -> dict:
    filters = {}
    for key in ("vacancy", "responsible"):
        if (params.get(key) or "").isdigit():
            filters[key] = int(params[key])
    if params.get("source") in Candidate.Source.values:
        filters["source"] = params["source"]
    if params.get("position", "").strip():
        filters["position"] = params["position"].strip()[:100]
    return filters


def _changed(instance, data: dict) -> list[str]:
    return [instance._meta.get_field(k).verbose_name for k, v in data.items() if getattr(instance, k) != v]


# ---------------------------------------------------------------------------
# Вакансии
# ---------------------------------------------------------------------------

class VacancyViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                     mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Справочник вакансий. Удаления нет: вакансию закрывают статусом."""

    permission_classes = PERMISSIONS
    serializer_class = VacancySerializer
    pagination_class = HRPagination
    http_method_names = ["get", "post", "patch"]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "responsible"]
    search_fields = ["title", "department", "description"]
    ordering_fields = ["title", "created_at", "status"]
    ordering = ["status", "-created_at"]

    def get_queryset(self):
        return Vacancy.objects.select_related("responsible").annotate(candidates_count=Count("candidates"))

    def perform_create(self, serializer):
        vacancy = serializer.save(created_by=self.request.user)
        activity.log(HRActivity.Kind.VACANCY_CREATED, self.request.user, vacancy=vacancy, message=vacancy.title)

    def perform_update(self, serializer):
        changed = _changed(serializer.instance, serializer.validated_data)
        vacancy = serializer.save()
        if changed:
            activity.log(HRActivity.Kind.VACANCY_UPDATED, self.request.user, vacancy=vacancy,
                         message=f"{vacancy.title}: {', '.join(map(str, changed))}")


# ---------------------------------------------------------------------------
# Кандидаты
# ---------------------------------------------------------------------------

class CandidateViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                       mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = PERMISSIONS
    pagination_class = HRPagination
    http_method_names = ["get", "post", "patch"]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "vacancy", "source", "responsible"]
    search_fields = ["last_name", "first_name", "middle_name", "phone", "email", "position", "vacancy__title"]
    ordering_fields = ["added_on", "last_name", "status", "status_changed_at", "created_at"]
    ordering = ["-added_on", "-id"]

    def get_queryset(self):
        next_interview = Interview.objects.filter(candidate=OuterRef("pk"), status=Interview.Status.SCHEDULED) \
            .order_by().values("candidate").annotate(first=Min("scheduled_at")).values("first")
        qs = Candidate.objects.select_related("vacancy", "responsible", "hired_user").annotate(
            next_interview_at=Subquery(next_interview))
        position = self.request.query_params.get("position", "").strip()
        if position:
            qs = qs.filter(reports.candidate_filter({"position": position[:100]}))
        if self.request.query_params.get("active") == "true":
            qs = qs.exclude(status__in=pipeline.TERMINAL)
        return qs

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CandidateWriteSerializer
        return CandidateSerializer

    def _read(self, candidate) -> dict:
        return CandidateSerializer(self.get_queryset().get(pk=candidate.pk)).data

    @extend_schema(tags=TAGS, responses=CandidateSerializer)
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        candidate = serializer.save(created_by=request.user, status_changed_at=timezone.now(),
                                    responsible=serializer.validated_data.get("responsible", request.user))
        activity.log(HRActivity.Kind.CANDIDATE_CREATED, request.user, candidate=candidate, vacancy=candidate.vacancy,
                     to_status=candidate.status, message=candidate.position_label)
        # Начало истории этапов: время входа в «Новый кандидат».
        activity.log(HRActivity.Kind.CANDIDATE_STATUS, request.user, candidate=candidate,
                     to_status=candidate.status, message="Кандидат добавлен")
        return Response(self._read(candidate), status=status.HTTP_201_CREATED)

    @extend_schema(tags=TAGS, responses=CandidateSerializer)
    def update(self, request, *args, **kwargs):
        candidate = self.get_object()
        serializer = self.get_serializer(candidate, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        changed = _changed(candidate, serializer.validated_data)
        serializer.save()
        if changed:
            activity.log(HRActivity.Kind.CANDIDATE_UPDATED, request.user, candidate=candidate,
                         message="Изменено: " + ", ".join(map(str, changed)))
        return Response(self._read(candidate))

    @extend_schema(tags=TAGS, request=StatusChangeSerializer, responses=CandidateSerializer)
    @action(detail=True, methods=["post"], url_path="status")
    def change_status(self, request, pk=None):
        candidate = self.get_object()
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            pipeline.change_status(candidate, serializer.validated_data["status"], request.user,
                                   serializer.validated_data.get("comment", ""))
        except pipeline.RecruitmentError as exc:
            return error_response(exc)
        return Response(self._read(candidate))

    @extend_schema(tags=TAGS, request=NoteSerializer, responses=ActivitySerializer)
    @action(detail=True, methods=["post"])
    def notes(self, request, pk=None):
        """Запись в историю взаимодействия: звонок, письмо, договорённость."""
        candidate = self.get_object()
        serializer = NoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = activity.log(HRActivity.Kind.CANDIDATE_NOTE, request.user, candidate=candidate,
                             message=serializer.validated_data["text"])
        return Response(ActivitySerializer(entry).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=TAGS, responses=ActivitySerializer(many=True))
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        candidate = self.get_object()
        entries = candidate.activities.select_related("actor", "candidate", "employee")
        return Response(ActivitySerializer(entries, many=True).data)

    @extend_schema(tags=TAGS, responses=CandidateSerializer)
    @action(detail=True, methods=["post"])
    def hire(self, request, pk=None):
        """Принять на работу: создать учётную запись тем же механизмом, что и
        раздел «Сотрудники» (роль — только из разрешённых HR)."""
        candidate = self.get_object()
        if candidate.hired_user_id:
            return error_response(pipeline.RecruitmentError(
                "Кандидат уже принят: учётная запись сотрудника создана.", "already_hired", status=409))
        data = {"first_name": candidate.first_name, "last_name": candidate.last_name, "email": candidate.email}
        data.update(request.data.items())
        serializer = HREmployeeCreateSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        try:
            pipeline.hire(candidate, request.user, serializer.save)
        except pipeline.RecruitmentError as exc:
            return error_response(exc)
        return Response(self._read(candidate))


# ---------------------------------------------------------------------------
# Собеседования
# ---------------------------------------------------------------------------

class InterviewViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Календарь: ?date_from&date_to (не больше 62 дней) или ?candidate.
    Фильтры: interviewer, vacancy, status."""

    permission_classes = PERMISSIONS
    serializer_class = InterviewSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        return Interview.objects.select_related("candidate", "vacancy", "interviewer")

    @extend_schema(tags=TAGS, responses=InterviewSerializer(many=True))
    def list(self, request, *args, **kwargs):
        p = request.query_params
        qs = self.get_queryset()
        if (p.get("candidate") or "").isdigit():
            qs = qs.filter(candidate_id=int(p["candidate"]))
        else:
            date_from, date_to = parse_date(p.get("date_from")), parse_date(p.get("date_to"))
            if not date_from or not date_to or date_to < date_from:
                return bad_request("Укажите период: date_from и date_to (YYYY-MM-DD).")
            if (date_to - date_from).days > CALENDAR_MAX_DAYS:
                return bad_request(f"Период календаря — не больше {CALENDAR_MAX_DAYS} дней.")
            start, _ = reports.day_bounds(date_from)
            _, end = reports.day_bounds(date_to)
            qs = qs.filter(scheduled_at__gte=start, scheduled_at__lt=end)
        for key in ("interviewer", "vacancy"):
            if (p.get(key) or "").isdigit():
                qs = qs.filter(**{f"{key}_id": int(p[key])})
        if p.get("status") in Interview.Status.values:
            qs = qs.filter(status=p["status"])
        return Response(InterviewSerializer(qs.order_by("scheduled_at", "id"), many=True).data)

    @extend_schema(tags=TAGS, request=InterviewCreateSerializer, responses=InterviewSerializer)
    def create(self, request, *args, **kwargs):
        serializer = InterviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        candidate = data.pop("candidate")
        confirm = data.pop("confirm", False)
        if data.get("vacancy") is None:
            data.pop("vacancy", None)
        try:
            interview = pipeline.schedule_interview(candidate, request.user, confirm=confirm, **data)
        except pipeline.RecruitmentError as exc:
            return error_response(exc)
        return Response(InterviewSerializer(interview).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=TAGS, request=InterviewUpdateSerializer, responses=InterviewSerializer)
    def partial_update(self, request, *args, **kwargs):
        interview = self.get_object()
        serializer = InterviewUpdateSerializer(interview, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        confirm = data.pop("confirm", False)
        try:
            interview = pipeline.update_interview(interview, request.user, confirm=confirm, **data)
        except pipeline.RecruitmentError as exc:
            return error_response(exc)
        return Response(InterviewSerializer(interview).data)

    @extend_schema(tags=TAGS, request=CancelSerializer, responses=InterviewSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        interview = self.get_object()
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            interview = pipeline.cancel_interview(interview, request.user, serializer.validated_data["reason"])
        except pipeline.RecruitmentError as exc:
            return error_response(exc)
        return Response(InterviewSerializer(interview).data)

    @extend_schema(tags=TAGS, request=ResultSerializer, responses=InterviewSerializer)
    @action(detail=True, methods=["post"])
    def result(self, request, pk=None):
        interview = self.get_object()
        serializer = ResultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            interview = pipeline.complete_interview(interview, request.user, **serializer.validated_data)
        except pipeline.RecruitmentError as exc:
            return error_response(exc)
        return Response(InterviewSerializer(interview).data)


# ---------------------------------------------------------------------------
# Справочники, главная, отчёты
# ---------------------------------------------------------------------------

def _choices(choices) -> list[dict]:
    return [{"value": value, "label": label} for value, label in choices]


class MetaView(APIView):
    """Справочники для форм: этапы, источники, форматы, результаты, люди."""

    permission_classes = PERMISSIONS

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        people = User.objects.filter(is_active=True).order_by("last_name", "first_name")
        return Response({
            "candidate_statuses": _choices(Candidate.Status.choices),
            "sources": _choices(Candidate.Source.choices),
            "vacancy_statuses": _choices(Vacancy.Status.choices),
            "interview_statuses": _choices(Interview.Status.choices),
            "interview_formats": _choices(Interview.Format.choices),
            "interview_results": _choices(Interview.Result.choices),
            "next_steps": _choices(Interview.NextStep.choices),
            "people": [person(u) for u in people],
            "today": timezone.localdate().isoformat(),
        })


class DashboardView(APIView):
    permission_classes = PERMISSIONS

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        today = timezone.localdate()
        date_from = parse_date(request.query_params.get("date_from")) or today.replace(day=1)
        date_to = parse_date(request.query_params.get("date_to")) or today
        if date_to < date_from:
            return bad_request("Начало периода позже окончания.")
        return Response(reports.dashboard(date_from, date_to))


def _csv_response(content: str, filename: str) -> HttpResponse:
    response = HttpResponse(content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class DailyReportView(APIView):
    """?date=YYYY-MM-DD (по умолчанию сегодня), фильтры, ?export=csv."""

    permission_classes = PERMISSIONS

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        p = request.query_params
        day = parse_date(p.get("date")) if p.get("date") else timezone.localdate()
        if day is None:
            return bad_request("Дата — в формате YYYY-MM-DD.")
        report = reports.daily(day, report_filters(p))
        if p.get("export") == "csv":
            return _csv_response(reports.daily_csv(report), f"hr-daily-{day.isoformat()}.csv")
        return Response(report)


class MonthlyReportView(APIView):
    """?month=YYYY-MM (по умолчанию текущий), фильтры, ?export=csv."""

    permission_classes = PERMISSIONS

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        p = request.query_params
        value = p.get("month") or timezone.localdate().strftime("%Y-%m")
        try:
            year, month = (int(part) for part in value.split("-"))
            date(year, month, 1)
        except (TypeError, ValueError):
            return bad_request("Месяц — в формате YYYY-MM.")
        report = reports.monthly(year, month, report_filters(p))
        if p.get("export") == "csv":
            return _csv_response(reports.monthly_csv(report), f"hr-monthly-{report['month']}.csv")
        return Response(report)

