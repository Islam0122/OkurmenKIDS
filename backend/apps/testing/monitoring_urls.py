"""Monitoring API — mounted under /api/v1/ in config/urls.py."""
from django.urls import path

from . import monitoring_api as views

urlpatterns = [
    path("monitoring/overview/", views.OverviewView.as_view(), name="monitoring-overview"),
    path("monitoring/attempts/", views.AttemptListView.as_view(), name="monitoring-attempts"),
    path("monitoring/attempts/<uuid:attempt_id>/", views.AttemptDetailView.as_view(), name="monitoring-attempt-detail"),
    path("monitoring/teachers/", views.TeacherPerformanceView.as_view(), name="monitoring-teachers"),
    path("monitoring/groups/", views.GroupListView.as_view(), name="monitoring-groups"),
    path("monitoring/groups/<int:group_id>/", views.GroupDetailView.as_view(), name="monitoring-group-detail"),
    path("monitoring/trainers/", views.TrainerListView.as_view(), name="monitoring-trainers"),
    path("monitoring/trainers/<uuid:session_id>/", views.TrainerDetailView.as_view(), name="monitoring-trainer-detail"),
    path("monitoring/questions/", views.QuestionStatsView.as_view(), name="monitoring-questions"),
    path("monitoring/filters/", views.FilterOptionsView.as_view(), name="monitoring-filters"),
    path("monitoring/results/", views.ResultListView.as_view(), name="results-list"),
    path("monitoring/results/summary/", views.ResultSummaryView.as_view(), name="results-summary"),
    path("monitoring/results/students/", views.ResultStudentsView.as_view(), name="results-students"),
    path("monitoring/results/breakdown/", views.ResultBreakdownView.as_view(), name="results-breakdown"),
    path("monitoring/results/export/", views.ResultExportView.as_view(), name="results-export"),
]
