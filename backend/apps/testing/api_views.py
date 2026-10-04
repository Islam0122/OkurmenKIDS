"""Test bank REST API (ADMIN role; TEAM_LEAD may only read).

    GET/POST              /api/v1/tests/
    GET/PATCH/DELETE      /api/v1/tests/{id}/
    GET/POST              /api/v1/tests/{id}/questions/
    POST                  /api/v1/tests/{id}/questions/reorder/   {"order": [question ids]}
    GET/PATCH/DELETE      /api/v1/tests/{id}/questions/{question_id}/

Questions are only reachable through their test. Writes use the same
services as the admin section (services/questions.py, question_rules.py).
"""
from __future__ import annotations

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.users.permissions import IsAdminOrTeamLeadReadOnly

from .models import Test, TestStatus
from .serializers import QuestionSerializer, TestSerializer
from .services import questions as question_service


class TestViewSet(viewsets.ModelViewSet):
    serializer_class = TestSerializer
    permission_classes = [IsAdminOrTeamLeadReadOnly]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        tests = (
            Test.objects.select_related("subject")
            .annotate(
                questions_total=Count("questions", distinct=True),
                attempts_total=Count("sessions__attempts", distinct=True),
            )
            .order_by("-updated_at")
        )
        params = self.request.query_params
        if params.get("status") in TestStatus.values:
            tests = tests.filter(status=params["status"])
        if query := (params.get("q") or "").strip():
            tests = tests.filter(Q(title__icontains=query) | Q(description__icontains=query))
        return tests


class TestQuestionViewSet(viewsets.ModelViewSet):
    serializer_class = QuestionSerializer
    permission_classes = [IsAdminOrTeamLeadReadOnly]
    pagination_class = None  # a test's questions are always returned whole, in order
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    lookup_url_kwarg = "question_id"

    def get_test(self) -> Test:
        if not hasattr(self, "_test"):
            self._test = get_object_or_404(Test, pk=self.kwargs["test_id"])
        return self._test

    def get_queryset(self):
        return self.get_test().questions.prefetch_related("options").order_by("order", "created_at")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if "test_id" in self.kwargs:
            context["test"] = self.get_test()
        return context

    def perform_destroy(self, instance):
        test = instance.test
        instance.delete()
        question_service.renumber(test)

    @action(detail=False, methods=["post"])
    def reorder(self, request, test_id=None):
        ids = request.data.get("order")
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            return Response({"order": "Ожидается список id вопросов."}, status=status.HTTP_400_BAD_REQUEST)
        if not question_service.reorder_questions(self.get_test(), ids):
            return Response(
                {"order": "Список должен содержать ровно все вопросы теста."}, status=status.HTTP_409_CONFLICT
            )
        return Response(QuestionSerializer(self.get_queryset(), many=True).data)
