"""Test bank API — mounted under /api/v1/ in config/urls.py."""
from django.urls import path

from .api_views import TestQuestionViewSet, TestViewSet

tests = TestViewSet.as_view({"get": "list", "post": "create"})
test_detail = TestViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})
questions = TestQuestionViewSet.as_view({"get": "list", "post": "create"})
question_detail = TestQuestionViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})
reorder = TestQuestionViewSet.as_view({"post": "reorder"})

urlpatterns = [
    path("tests/", tests, name="testing-test-list"),
    path("tests/<uuid:pk>/", test_detail, name="testing-test-detail"),
    path("tests/<uuid:test_id>/questions/", questions, name="testing-question-list"),
    path("tests/<uuid:test_id>/questions/reorder/", reorder, name="testing-question-reorder"),
    path("tests/<uuid:test_id>/questions/<uuid:question_id>/", question_detail, name="testing-question-detail"),
]
