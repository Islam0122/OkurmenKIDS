"""API HR-кабинета (/api/v1/hr/…): вакансии, кандидаты, отклики,
собеседования, напоминания, главная и кадровые отчёты.

Только HR-менеджер (`IsHRManager`): анкеты, контакты, резюме, заметки и
отчёты другим ролям и посетителям недоступны. Публичный карьерный сайт —
отдельный API (`public.py`) с белым списком полей. Сотрудники — apps.users.hr.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Count, Max, Min, OuterRef, Q, Subquery
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.hr import ROLE_CHOICES, HREmployeeCreateSerializer, HRPagination
from apps.users.models import User
from apps.users.permissions import IsHRManager

from .models import AccountRequest, Application, Candidate, HRActivity, InternalNote, Interview, Vacancy
from .serializers import (
    AccountRequestCreateSerializer,
    AccountRequestSerializer,
    ActivitySerializer,
    ApplicationCreateSerializer,
    ApplicationSerializer,
    ApplicationUpdateSerializer,
    CancelSerializer,
    CandidateListSerializer,
    CandidateSerializer,
    CandidateWriteSerializer,
    EraseSerializer,
    InterviewCreateSerializer,
    InterviewSerializer,
    InterviewUpdateSerializer,
    MergeSerializer,
    NoShowSerializer,
    NoteCreateSerializer,
    NoteSerializer,
    ResultSerializer,
    StatusChangeSerializer,
    VacancySerializer,
    VacancyStatusSerializer,
    VacancyWriteSerializer,
    choices,
    person,
)
from .services import activity, files, hiring, intake, pipeline, reminders, reports, vacancies
from .services.common import RecruitmentError

TAGS = ["HR"]
PERMISSIONS = [IsAuthenticated, IsHRManager]
CALENDAR_MAX_DAYS = 62
BOARD_COLUMN_LIMIT = 50


def error_response(exc: RecruitmentError) -> Response:
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
    if params.get("source") in Application.Source.values:
        filters["source"] = params["source"]
    if params.get("position", "").strip():
        filters["position"] = params["position"].strip()[:100]
    return filters


def _changed(instance, data: dict) -> list[str]:
    return [str(instance._meta.get_field(k).verbose_name) for k, v in data.items() if getattr(instance, k) != v]


# ---------------------------------------------------------------------------
# Вакансии
# ---------------------------------------------------------------------------

class VacancyViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                     mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Вакансии: карточка, черновики, публикация, пауза, закрытие, архив.
    Удаления нет — завершённую вакансию закрывают и архивируют; отклики и
    история остаются."""

    permission_classes = PERMISSIONS
    pagination_class = HRPagination
    http_method_names = ["get", "post", "patch"]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "responsible", "work_format", "employment_type"]
    search_fields = ["title", "department", "location", "summary"]
    ordering_fields = ["title", "created_at", "published_at", "status", "applications_count"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Vacancy.objects.select_related("responsible").annotate(
            applications_count=Count("applications", distinct=True),
            active_count=Count("applications", filter=~Q(applications__status__in=pipeline.TERMINAL), distinct=True),
            new_count=Count("applications", filter=Q(applications__status=Application.Status.NEW), distinct=True),
        )
        if self.request.query_params.get("active") == "true":
            qs = qs.filter(status__in=vacancies.ACCEPTS_CANDIDATES)
        return qs

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return VacancyWriteSerializer
        return VacancySerializer

    def _read(self, vacancy) -> dict:
        return VacancySerializer(self.get_queryset().get(pk=vacancy.pk)).data

    @extend_schema(tags=TAGS, request=VacancyWriteSerializer, responses=VacancySerializer)
    def create(self, request, *args, **kwargs):
        serializer = VacancyWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Новая вакансия — всегда черновик: на сайт она попадает только кнопкой «Опубликовать».
        vacancy = serializer.save(created_by=request.user, status=Vacancy.Status.DRAFT)
        activity.log(HRActivity.Kind.VACANCY_CREATED, request.user, vacancy=vacancy, message=vacancy.title)
        return Response(self._read(vacancy), status=status.HTTP_201_CREATED)

    @extend_schema(tags=TAGS, request=VacancyWriteSerializer, responses=VacancySerializer)
    def update(self, request, *args, **kwargs):
        vacancy = self.get_object()
        serializer = VacancyWriteSerializer(vacancy, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        changed = _changed(vacancy, serializer.validated_data)
        vacancy = serializer.save()
        if changed:
            activity.log(HRActivity.Kind.VACANCY_UPDATED, request.user, vacancy=vacancy,
                         message=f"{vacancy.title}: {', '.join(changed)}")
        return Response(self._read(vacancy))

    @extend_schema(tags=TAGS, request=VacancyStatusSerializer, responses=VacancySerializer)
    @action(detail=True, methods=["post"], url_path="status")
    def change_status(self, request, pk=None):
        vacancy = self.get_object()
        serializer = VacancyStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            vacancy = vacancies.change_status(vacancy, serializer.validated_data["status"], request.user)
        except RecruitmentError as exc:
            return error_response(exc)
        return Response(self._read(vacancy))


# ---------------------------------------------------------------------------
# Кандидаты (люди)
# ---------------------------------------------------------------------------

def _applications_qs():
    next_interview = Interview.objects.filter(application=OuterRef("pk"), status=Interview.Status.SCHEDULED) \
        .order_by().values("application").annotate(first=Min("scheduled_at")).values("first")
    return Application.objects.select_related("candidate", "vacancy", "responsible", "hired_user") \
        .prefetch_related("account_requests").annotate(next_interview_at=Subquery(next_interview))


class CandidateViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                       viewsets.GenericViewSet):
    """Люди: профиль и контакты, все отклики, заметки HR, история,
    объединение дублей, удаление персональных данных."""

    permission_classes = PERMISSIONS
    pagination_class = HRPagination
    http_method_names = ["get", "post", "patch"]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["last_name", "first_name", "middle_name", "phone", "phone_digits", "email"]
    ordering_fields = ["last_name", "created_at", "last_applied_on"]
    ordering = ["-created_at"]

    def get_queryset(self):
        qs = Candidate.objects.select_related("merged_into").annotate(
            applications_count=Count("applications", distinct=True),
            active_count=Count("applications", filter=~Q(applications__status__in=pipeline.TERMINAL), distinct=True),
            last_applied_on=Max("applications__applied_on"),
        )
        if self.action == "list" and self.request.query_params.get("include_closed") != "true":
            qs = qs.filter(merged_into__isnull=True)
        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return CandidateListSerializer
        if self.action in ("update", "partial_update"):
            return CandidateWriteSerializer
        return CandidateSerializer

    def _read(self, candidate) -> dict:
        candidate = Candidate.objects.select_related("merged_into").get(pk=candidate.pk)
        apps = _applications_qs().filter(candidate=candidate).order_by("-created_at", "-id")
        return CandidateSerializer(candidate, context={"applications": apps, "with_duplicates": True}).data

    @extend_schema(tags=TAGS, responses=CandidateSerializer)
    def retrieve(self, request, *args, **kwargs):
        return Response(self._read(self.get_object()))

    @extend_schema(tags=TAGS, request=CandidateWriteSerializer, responses=CandidateSerializer)
    def update(self, request, *args, **kwargs):
        candidate = self.get_object()
        if candidate.erased_at or candidate.merged_into_id:
            return error_response(RecruitmentError("Эта запись закрыта для изменений.", "candidate_closed"))
        serializer = CandidateWriteSerializer(candidate, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        changed = _changed(candidate, serializer.validated_data)
        candidate = serializer.save()
        intake.update_contacts(candidate)
        candidate.save(update_fields=["email", "phone_digits", "updated_at"])
        if changed:
            activity.log(HRActivity.Kind.CANDIDATE_UPDATED, request.user, candidate=candidate,
                         message="Изменено: " + ", ".join(changed))
        return Response(self._read(candidate))

    @extend_schema(tags=TAGS, request=NoteCreateSerializer, responses=NoteSerializer(many=True))
    @action(detail=True, methods=["get", "post"])
    def notes(self, request, pk=None):
        """Внутренние заметки HR (кандидату и посетителям сайта не видны)."""
        candidate = self.get_object()
        if request.method == "GET":
            notes = candidate.internal_notes.select_related("author", "application")
            return Response(NoteSerializer(notes, many=True).data)
        serializer = NoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application = None
        if serializer.validated_data.get("application"):
            application = get_object_or_404(candidate.applications, pk=serializer.validated_data["application"])
        note = InternalNote.objects.create(candidate=candidate, application=application, author=request.user,
                                           text=serializer.validated_data["text"])
        activity.log(HRActivity.Kind.CANDIDATE_NOTE, request.user, candidate=candidate, application=application,
                     message="Добавлена заметка HR")
        return Response(NoteSerializer(note).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=TAGS, responses=ActivitySerializer(many=True))
    @action(detail=True, methods=["get"])
    def history(self, request, pk=None):
        candidate = self.get_object()
        entries = reports.visible_activity(candidate.activities.select_related("actor", "candidate", "employee"))
        return Response(ActivitySerializer(entries[:200], many=True).data)

    @extend_schema(tags=TAGS, request=MergeSerializer, responses=CandidateSerializer)
    @action(detail=True, methods=["post"])
    def merge(self, request, pk=None):
        """Эта запись — дубль `target`: отклики, заметки и история переходят к `target`."""
        source = self.get_object()
        serializer = MergeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            target = intake.merge(source, serializer.validated_data["target"], request.user)
        except RecruitmentError as exc:
            return error_response(exc)
        return Response(self._read(target))

    @extend_schema(tags=TAGS, request=EraseSerializer, responses=CandidateSerializer)
    @action(detail=True, methods=["post"])
    def erase(self, request, pk=None):
        """Удалить персональные данные (по запросу кандидата или по сроку хранения)."""
        candidate = self.get_object()
        serializer = EraseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            candidate = intake.erase(candidate, request.user, serializer.validated_data.get("reason", ""))
        except RecruitmentError as exc:
            return error_response(exc)
        return Response(self._read(candidate))


# ---------------------------------------------------------------------------
# Отклики
# ---------------------------------------------------------------------------

class ApplicationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                         mixins.UpdateModelMixin, viewsets.GenericViewSet):
    """Отклики — единица воронки: этап, ответственный, резюме, собеседования, найм.

    Фильтры: `status`, `vacancy`, `source`, `responsible`, `channel`,
    `date_from`/`date_to` (дата отклика), `active=true`, `duplicates=true`,
    поиск — ФИО, телефон, email, номер заявки."""

    permission_classes = PERMISSIONS
    pagination_class = HRPagination
    http_method_names = ["get", "post", "patch"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "vacancy", "source", "responsible", "channel", "candidate"]
    search_fields = ["number", "candidate__last_name", "candidate__first_name", "candidate__middle_name",
                     "candidate__phone", "candidate__phone_digits", "candidate__email", "position", "vacancy__title"]
    ordering_fields = ["applied_on", "created_at", "candidate__last_name", "status", "status_changed_at"]
    ordering = ["-created_at", "-id"]

    def get_queryset(self):
        qs = _applications_qs()
        p = self.request.query_params
        if p.get("active") == "true":
            qs = qs.exclude(status__in=pipeline.TERMINAL)
        if p.get("duplicates") == "true":
            qs = qs.filter(needs_duplicate_review=True)
        date_from, date_to = parse_date(p.get("date_from")), parse_date(p.get("date_to"))
        if date_from:
            qs = qs.filter(applied_on__gte=date_from)
        if date_to:
            qs = qs.filter(applied_on__lte=date_to)
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return ApplicationCreateSerializer
        if self.action in ("update", "partial_update"):
            return ApplicationUpdateSerializer
        return ApplicationSerializer

    def _read(self, application) -> dict:
        return ApplicationSerializer(_applications_qs().get(pk=application.pk)).data

    @extend_schema(tags=TAGS, request=ApplicationCreateSerializer, responses=ApplicationSerializer)
    def create(self, request, *args, **kwargs):
        serializer = ApplicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resume = request.FILES.get("resume")
        try:
            if resume is not None:
                files.validate_resume(resume)
            application = intake.create_by_hr(request.user, **serializer.split())
            if resume is not None:
                files.attach_resume(application, resume)
        except RecruitmentError as exc:
            return error_response(exc)
        return Response(self._read(application), status=status.HTTP_201_CREATED)

    @extend_schema(tags=TAGS, request=ApplicationUpdateSerializer, responses=ApplicationSerializer)
    def update(self, request, *args, **kwargs):
        application = self.get_object()
        serializer = ApplicationUpdateSerializer(application, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        changed = _changed(application, serializer.validated_data)
        serializer.save()
        if changed:
            activity.log(HRActivity.Kind.CANDIDATE_UPDATED, request.user, application=application,
                         message=f"Отклик {application.number}: " + ", ".join(changed))
        return Response(self._read(application))

    @extend_schema(tags=TAGS, request=StatusChangeSerializer, responses=ApplicationSerializer)
    @action(detail=True, methods=["post"], url_path="status")
    def change_status(self, request, pk=None):
        application = self.get_object()
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            pipeline.change_status(application, serializer.validated_data["status"], request.user,
                                   serializer.validated_data.get("comment", ""))
        except RecruitmentError as exc:
            return error_response(exc)
        return Response(self._read(application))

    @extend_schema(tags=TAGS, responses=OpenApiTypes.BINARY)
    @action(detail=True, methods=["get", "post"])
    def resume(self, request, pk=None):
        """GET — резюме (только через API, `Cache-Control: no-store`;
        `?inline=1` — открыть PDF в браузере); POST (multipart `resume`) — прикрепить или заменить."""
        application = self.get_object()
        if request.method == "POST":
            upload = request.FILES.get("resume")
            if upload is None:
                return bad_request("Прикрепите файл резюме (поле resume).")
            try:
                files.attach_resume(application, upload)
            except RecruitmentError as exc:
                return error_response(exc)
            activity.log(HRActivity.Kind.CANDIDATE_UPDATED, request.user, application=application,
                         message=f"Отклик {application.number}: прикреплено резюме")
            return Response(self._read(application))
        if not application.resume:
            return error_response(RecruitmentError("К отклику не прикреплено резюме.", "no_resume", status=404))
        try:
            handle = application.resume.open("rb")
        except FileNotFoundError:
            return error_response(RecruitmentError("Файл резюме не найден в хранилище.", "missing_file", status=404))
        ext = application.resume.name.rsplit(".", 1)[-1].lower()
        inline = request.query_params.get("inline") == "1" and ext == "pdf"
        response = FileResponse(handle, as_attachment=not inline,
                                filename=application.resume_name or f"resume.{ext}",
                                content_type=files.CONTENT_TYPES.get(ext, "application/octet-stream"))
        response["Cache-Control"] = "no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox; default-src 'none'"
        activity.log(HRActivity.Kind.RESUME_ACCESSED, request.user, application=application,
                     message=f"Отклик {application.number}: {'просмотр' if inline else 'скачивание'} резюме")
        return response

    @extend_schema(tags=TAGS, request=None, responses=ApplicationSerializer)
    @action(detail=True, methods=["post"], url_path="not-duplicate")
    def not_duplicate(self, request, pk=None):
        application = intake.dismiss_duplicate(self.get_object(), request.user)
        return Response(self._read(application))

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def board(self, request):
        """Доска этапов: действующие отклики по колонкам (до 50 в колонке, плюс
        число всех) и закрытые за последние 30 дней."""
        qs = self.filter_queryset(self.get_queryset())
        recent = timezone.now() - timedelta(days=30)
        columns = []
        for value, label in Application.Status.choices:
            column = qs.filter(status=value)
            if value in pipeline.TERMINAL:
                column = column.filter(status_changed_at__gte=recent)
            items = list(column.order_by("-status_changed_at", "-id")[:BOARD_COLUMN_LIMIT])
            columns.append({"status": value, "label": label, "count": column.count(),
                            "items": ApplicationSerializer(items, many=True).data})
        return Response({"columns": columns})

    @extend_schema(tags=TAGS, responses=CandidateSerializer)
    @action(detail=True, methods=["post"])
    def hire(self, request, pk=None):
        """Принять на работу: создать учётную запись тем же механизмом, что и
        раздел «Сотрудники» (роль — только из разрешённых HR). HR подтверждает
        операцию в интерфейсе; сервер проверяет этап, дубли и права."""
        application = self.get_object()
        try:
            hiring.check_hireable(application)
        except RecruitmentError as exc:
            return error_response(exc)
        c = application.candidate
        data = {"first_name": c.first_name, "last_name": c.last_name, "email": c.email}
        data.update(request.data.items())
        if data.get("role") not in User.HR_MANAGEABLE_ROLES:
            return error_response(RecruitmentError(
                "Эту должность HR не оформляет сам — отправьте запрос администратору.", "role_requires_approval",
                status=403, extra={"requestable": data.get("role") in dict(hiring.requestable_roles())}))
        serializer = HREmployeeCreateSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        try:
            hiring.hire(application, request.user, serializer.save)
        except RecruitmentError as exc:
            return error_response(exc)
        return Response(self._read(application))

    @extend_schema(tags=TAGS, request=AccountRequestCreateSerializer, responses=AccountRequestSerializer)
    @action(detail=True, methods=["post"], url_path="account-request")
    def account_request(self, request, pk=None):
        """Роль вне полномочий HR: запрос администратору вместо обхода ограничений."""
        application = self.get_object()
        serializer = AccountRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            created = hiring.request_account(application, request.user, **serializer.validated_data)
        except RecruitmentError as exc:
            return error_response(exc)
        return Response(AccountRequestSerializer(created).data, status=status.HTTP_201_CREATED)


class AccountRequestViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Запросы учётных записей (только чтение для HR; решение — администратор в Django admin)."""

    permission_classes = PERMISSIONS
    serializer_class = AccountRequestSerializer
    pagination_class = HRPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["status", "application"]

    def get_queryset(self):
        return AccountRequest.objects.select_related("application__candidate", "requested_by")


# ---------------------------------------------------------------------------
# Собеседования
# ---------------------------------------------------------------------------

class InterviewViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Календарь: ?date_from&date_to (не больше 62 дней), ?application или ?candidate.
    Фильтры: interviewer, vacancy, status."""

    permission_classes = PERMISSIONS
    serializer_class = InterviewSerializer
    pagination_class = None
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        return Interview.objects.select_related("application__candidate", "vacancy", "interviewer")

    @extend_schema(tags=TAGS, responses=InterviewSerializer(many=True))
    def list(self, request, *args, **kwargs):
        p = request.query_params
        qs = self.get_queryset()
        if (p.get("application") or "").isdigit():
            qs = qs.filter(application_id=int(p["application"]))
        elif (p.get("candidate") or "").isdigit():
            qs = qs.filter(application__candidate_id=int(p["candidate"]))
        else:
            date_from, date_to = parse_date(p.get("date_from")), parse_date(p.get("date_to"))
            if not date_from or not date_to or date_to < date_from:
                return bad_request("Укажите период: date_from и date_to (YYYY-MM-DD).")
            if (date_to - date_from).days > CALENDAR_MAX_DAYS:
                return bad_request(f"Период календаря — не больше {CALENDAR_MAX_DAYS} дней.")
            start, end = reports.period_bounds(date_from, date_to)
            qs = qs.filter(scheduled_at__gte=start, scheduled_at__lt=end)
        for key in ("interviewer", "vacancy"):
            if (p.get(key) or "").isdigit():
                qs = qs.filter(**{f"{key}_id": int(p[key])})
        if p.get("status") in Interview.Status.values:
            qs = qs.filter(status=p["status"])
        return Response(InterviewSerializer(qs.order_by("scheduled_at", "id"), many=True).data)

    def _run(self, fn, *args, **kwargs) -> Response:
        try:
            interview = fn(*args, **kwargs)
        except RecruitmentError as exc:
            return error_response(exc)
        return Response(InterviewSerializer(self.get_queryset().get(pk=interview.pk)).data)

    @extend_schema(tags=TAGS, request=InterviewCreateSerializer, responses=InterviewSerializer)
    def create(self, request, *args, **kwargs):
        serializer = InterviewCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        application = data.pop("application")
        confirm = data.pop("confirm", False)
        response = self._run(pipeline.schedule_interview, application, request.user, confirm=confirm, **data)
        if response.status_code == 200:
            response.status_code = status.HTTP_201_CREATED
        return response

    @extend_schema(tags=TAGS, request=InterviewUpdateSerializer, responses=InterviewSerializer)
    def partial_update(self, request, *args, **kwargs):
        """Изменение деталей; новое время — перенос (возвращается новая встреча)."""
        interview = self.get_object()
        serializer = InterviewUpdateSerializer(interview, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        confirm = data.pop("confirm", False)
        return self._run(pipeline.update_interview, interview, request.user, confirm=confirm, **data)

    @extend_schema(tags=TAGS, request=CancelSerializer, responses=InterviewSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        interview = self.get_object()
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._run(pipeline.cancel_interview, interview, request.user, serializer.validated_data["reason"])

    @extend_schema(tags=TAGS, request=NoShowSerializer, responses=InterviewSerializer)
    @action(detail=True, methods=["post"], url_path="no-show")
    def no_show(self, request, pk=None):
        interview = self.get_object()
        serializer = NoShowSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._run(pipeline.mark_no_show, interview, request.user, serializer.validated_data.get("comment", ""))

    @extend_schema(tags=TAGS, request=ResultSerializer, responses=InterviewSerializer)
    @action(detail=True, methods=["post"])
    def result(self, request, pk=None):
        interview = self.get_object()
        serializer = ResultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self._run(pipeline.complete_interview, interview, request.user, **serializer.validated_data)


# ---------------------------------------------------------------------------
# Справочники, напоминания, главная, отчёты
# ---------------------------------------------------------------------------

class MetaView(APIView):
    """Справочники для форм: этапы, источники, форматы, результаты, роли, люди."""

    permission_classes = PERMISSIONS

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        people = User.objects.filter(is_active=True).order_by("last_name", "first_name")
        return Response({
            "application_statuses": choices(Application.Status),
            "sources": choices(Application.Source),
            "channels": choices(Application.Channel),
            "vacancy_statuses": choices(Vacancy.Status),
            "work_formats": choices(Vacancy.WorkFormat),
            "employment_types": choices(Vacancy.EmploymentType),
            "currencies": choices(Vacancy.Currency),
            "interview_statuses": choices(Interview.Status),
            "interview_formats": choices(Interview.Format),
            "interview_results": choices(Interview.Result),
            "next_steps": choices(Interview.NextStep),
            "hire_roles": [{"value": value, "label": label} for value, label in ROLE_CHOICES],
            "requestable_roles": [{"value": value, "label": label} for value, label in hiring.requestable_roles()],
            "people": [person(u) for u in people],
            "resume_max_mb": files.max_bytes() // (1024 * 1024),
            "today": timezone.localdate().isoformat(),
        })


class RemindersView(APIView):
    """?mine=true — только встречи и отклики пользователя."""

    permission_classes = PERMISSIONS

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        items = reminders.reminders(request.user, mine=request.query_params.get("mine") == "true")
        return Response({"count": len(items), "results": items})


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
    response["Cache-Control"] = "no-store"
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
    """?month=YYYY-MM (по умолчанию текущий) или ?date_from&date_to (до 366
    дней), фильтры по вакансии, ответственному, источнику, должности, ?export=csv."""

    permission_classes = PERMISSIONS

    @extend_schema(tags=TAGS, responses=OpenApiTypes.OBJECT)
    def get(self, request):
        p = request.query_params
        filters = report_filters(p)
        if p.get("date_from") or p.get("date_to"):
            first, last = parse_date(p.get("date_from")), parse_date(p.get("date_to"))
            if not first or not last or last < first:
                return bad_request("Период: date_from и date_to (YYYY-MM-DD), начало не позже конца.")
            if (last - first).days >= reports.MAX_PERIOD_DAYS:
                return bad_request(f"Период отчёта — не больше {reports.MAX_PERIOD_DAYS} дней.")
            report = reports.period_report(first, last, filters, f"{first.isoformat()} — {last.isoformat()}")
            name = f"hr-period-{first.isoformat()}-{last.isoformat()}.csv"
        else:
            value = p.get("month") or timezone.localdate().strftime("%Y-%m")
            try:
                year, month = (int(part) for part in value.split("-"))
                date(year, month, 1)
            except (TypeError, ValueError):
                return bad_request("Месяц — в формате YYYY-MM.")
            report = reports.monthly(year, month, filters)
            name = f"hr-monthly-{report['month']}.csv"
        if p.get("export") == "csv":
            return _csv_response(reports.monthly_csv(report), name)
        return Response(report)

