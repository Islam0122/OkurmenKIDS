"""Public training portal API — mounted under /api/v1/ in config/urls.py."""
from django.urls import path

from . import exam_api, views

attempt = "training/attempts/<uuid:attempt_id>/"
exam = "training/exam-attempts/<uuid:attempt_id>/"

urlpatterns = [
    path("training/portal/", views.PortalView.as_view(), name="training-portal"),
    path("training/tests/", views.TestListView.as_view(), name="training-test-list"),
    path("training/tests/<uuid:test_id>/", views.TestDetailView.as_view(), name="training-test-detail"),
    path("training/attempts/", views.AttemptStartView.as_view(), name="training-attempt-start"),
    path(attempt, views.AttemptView.as_view(), name="training-attempt"),
    path(attempt + "answers/<uuid:question_id>/", views.AnswerView.as_view(), name="training-answer"),
    path(attempt + "answers/<uuid:question_id>/check/", views.AnswerCheckView.as_view(), name="training-answer-check"),
    path(attempt + "events/", views.AttemptEventView.as_view(), name="training-attempt-events"),
    path(attempt + "submit/", views.AttemptSubmitView.as_view(), name="training-attempt-submit"),
    path(attempt + "result/", views.AttemptResultView.as_view(), name="training-attempt-result"),
    # Exam attempts in the same test UI (token from /exam/?key=…).
    path(exam, exam_api.ExamAttemptView.as_view(), name="exam-attempt"),
    path(exam + "answers/<uuid:question_id>/", exam_api.ExamAnswerView.as_view(), name="exam-answer"),
    path(exam + "events/", exam_api.ExamEventView.as_view(), name="exam-events"),
    path(exam + "submit/", exam_api.ExamSubmitView.as_view(), name="exam-submit"),
    path(exam + "result/", exam_api.ExamResultView.as_view(), name="exam-result"),
    path("training/leaderboard/", views.LeaderboardView.as_view(), name="training-leaderboard"),
    path("training/videos/", views.VideoListView.as_view(), name="training-videos"),
    path("training/links/", views.LinkListView.as_view(), name="training-links"),
]
