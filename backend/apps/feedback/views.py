"""Feedback JSON API.

Admin endpoints (``/api/v1/feedback/surveys/…``, ``/api/v1/feedback/questions/…``,
``/api/v1/feedback/analytics/overview/``) require the ADMIN role. Teachers
have no access to surveys or responses in this version — the organisation
has not defined a policy for it yet (see docs/feedback.md).

Public endpoints (``/api/v1/feedback/public/<token>/…``) need no login, are
IP-throttled, and only ever expose what ``public.public_payload`` returns.
"""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Prefetch, ProtectedError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsAdmin

from .models import Survey, SurveyAnswer, SurveyQuestion
from .public import (
    FeedbackSubmitThrottle,
    FeedbackViewThrottle,
    has_submitted,
    mark_submitted,
    public_payload,
)
from .serializers import (
    PublicSubmissionSerializer,
    QuestionInputSerializer,
    ReorderSerializer,
    SurveyDetailSerializer,
    SurveyQuestionSerializer,
    SurveyResponseSerializer,
    SurveySerializer,
)
from .services import builder
from .services.analytics import FeedbackFilters, overview, question_stats
from .services.export import export_responses_csv
from .services.submission import UNAVAILABLE_MESSAGES, SubmissionData, SubmissionError, submit_response


def _drf_error(exc: DjangoValidationError) -> ValidationError:
    if hasattr(exc, "error_dict"):
        return ValidationError(exc.message_dict)
    return ValidationError({"detail": exc.messages})


def _run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DjangoValidationError as exc:
        raise _drf_error(exc)


@extend_schema(tags=["Feedback"])
class SurveyAdminViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsAdmin]
    search_fields = ["title"]
    filterset_fields = ["audience", "status", "visibility_mode"]
    ordering_fields = ["created_at", "title"]

    def get_queryset(self):
        return Survey.objects.select_related("group", "teacher__user", "subject").annotate(
            question_count=Count("questions", distinct=True),
            response_count=Count("responses", distinct=True),
        )

    def get_serializer_class(self):
        return SurveyDetailSerializer if self.action == "retrieve" else SurveySerializer

    def perform_create(self, serializer):
        survey = serializer.save(created_by=self.request.user)
        builder.log_admin_action(self.request.user, survey, "Опрос создан через API.")

    def perform_destroy(self, instance):
        if instance.has_responses():
            raise ValidationError({"detail": "У опроса есть ответы — удалить его нельзя. Закройте опрос вместо удаления."})
        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError({"detail": "Опрос используется и не может быть удалён."})

    def _detail(self, survey, code=status.HTTP_200_OK):
        survey = self.get_queryset().get(pk=survey.pk)
        return Response(SurveyDetailSerializer(survey, context=self.get_serializer_context()).data, status=code)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        return self._detail(_run(builder.publish_survey, self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return self._detail(_run(builder.close_survey, self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return self._detail(_run(builder.reopen_survey, self.get_object(), request.user))

    @action(detail=True, methods=["post"], url_path="regenerate-link")
    def regenerate_link(self, request, pk=None):
        return self._detail(_run(builder.regenerate_link, self.get_object(), request.user))

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        return self._detail(builder.duplicate_survey(self.get_object(), request.user), status.HTTP_201_CREATED)

    @extend_schema(request=QuestionInputSerializer, responses=SurveyQuestionSerializer)
    @action(detail=True, methods=["post"], url_path="questions")
    def add_question(self, request, pk=None):
        survey = self.get_object()
        payload = QuestionInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        question = _run(builder.create_question, survey, payload.validated_data)
        return Response(SurveyQuestionSerializer(question).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=ReorderSerializer)
    @action(detail=True, methods=["post"], url_path="questions/reorder")
    def reorder_questions(self, request, pk=None):
        survey = self.get_object()
        payload = ReorderSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        _run(builder.reorder_questions, survey, payload.validated_data["order"])
        return self._detail(survey)

    def _filtered_responses(self, survey, request):
        filters = FeedbackFilters.from_query(request.query_params)
        filters.survey_id = survey.pk
        return filters.responses(Survey.objects.filter(pk=survey.pk))

    @extend_schema(responses=SurveyResponseSerializer(many=True))
    @action(detail=True, methods=["get"])
    def responses(self, request, pk=None):
        survey = self.get_object()
        qs = self._filtered_responses(survey, request).prefetch_related(
            Prefetch("answers", queryset=SurveyAnswer.objects.select_related("question")),
            "answers__option_links__option",
        )
        search = (request.query_params.get("search") or "").strip()
        if search:
            qs = qs.filter(answers__text_value__icontains=search).distinct()
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(SurveyResponseSerializer(page, many=True).data)

    @action(detail=True, methods=["get"])
    def analytics(self, request, pk=None):
        survey = self.get_object()
        responses = self._filtered_responses(survey, request)
        stats = question_stats(survey, responses, text_search=(request.query_params.get("search") or "").strip())
        data = []
        for entry in stats:
            entry = {k: v for k, v in entry.items() if k != "question"}
            if "texts" in entry:
                # Text answers are listed without any respondent identity.
                entry["texts"] = [{"text": t["text"], "submitted_at": t["submitted_at"]} for t in entry["texts"]]
            data.append(entry)
        return Response({"response_count": responses.count(), "questions": data})

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        survey = self.get_object()
        content = export_responses_csv(survey, self._filtered_responses(survey, request))
        builder.log_admin_action(request.user, survey, "Ответы экспортированы в CSV.")
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="survey-{survey.pk}-responses.csv"'
        return response


@extend_schema(tags=["Feedback"])
class SurveyQuestionAdminViewSet(
    mixins.RetrieveModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated, IsAdmin]
    serializer_class = SurveyQuestionSerializer
    queryset = SurveyQuestion.objects.select_related("survey").prefetch_related("options")

    @extend_schema(request=QuestionInputSerializer)
    def update(self, request, *args, **kwargs):
        question = self.get_object()
        payload = QuestionInputSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        question = _run(builder.update_question, question, payload.validated_data)
        return Response(SurveyQuestionSerializer(question).data)

    def partial_update(self, request, *args, **kwargs):
        # Options are synced as a whole list, so a question is always
        # written in full; PATCH is accepted as an alias of PUT.
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        _run(builder.delete_question, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        question = _run(builder.duplicate_question, self.get_object())
        return Response(SurveyQuestionSerializer(question).data, status=status.HTTP_201_CREATED)


@extend_schema(tags=["Feedback"])
class FeedbackOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        data = overview(FeedbackFilters.from_query(request.query_params))
        data["surveys"] = [
            {"id": s.id, "title": s.title, "audience": s.audience, "status": s.status, "response_count": s.response_count}
            for s in data["surveys"]
        ]
        return Response(data)


# -- Public ---------------------------------------------------------------


def _published_survey(token: str) -> Survey:
    survey = get_object_or_404(Survey.objects.select_related("group", "teacher__user", "subject"), public_token=token)
    # A draft is indistinguishable from a wrong link.
    if survey.status == Survey.Status.DRAFT:
        raise Http404
    return survey


@extend_schema(tags=["Feedback"])
class PublicSurveyView(APIView):
    """GET /feedback/public/<token>/ — the survey form definition."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [FeedbackViewThrottle]

    def get(self, request, token):
        survey = _published_survey(token)
        availability = survey.availability()
        if availability != Survey.Availability.AVAILABLE:
            return Response(
                {"title": survey.title, "availability": availability, "message": UNAVAILABLE_MESSAGES[availability]}
            )
        data = {"availability": availability, "already_submitted": False, **public_payload(survey)}
        if not survey.allow_multiple_submissions and has_submitted(request, survey):
            data["already_submitted"] = True
        return Response(data)


@extend_schema(tags=["Feedback"], request=PublicSubmissionSerializer)
class PublicSurveySubmitView(APIView):
    """POST /feedback/public/<token>/submit/ — submit one response."""

    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [FeedbackSubmitThrottle]

    def post(self, request, token):
        survey = _published_survey(token)
        if not survey.allow_multiple_submissions and has_submitted(request, survey):
            return Response(
                {"errors": {"__all__": "Вы уже ответили на этот опрос."}}, status=status.HTTP_409_CONFLICT
            )
        payload = PublicSubmissionSerializer(data=request.data)
        if not payload.is_valid():
            return Response({"errors": payload.errors}, status=status.HTTP_400_BAD_REQUEST)
        try:
            submit_response(survey, SubmissionData(**payload.validated_data))
        except SubmissionError as exc:
            return Response({"errors": exc.errors}, status=status.HTTP_400_BAD_REQUEST)
        response = Response({"message": survey.confirmation_message}, status=status.HTTP_201_CREATED)
        mark_submitted(response, survey)
        return response
