from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("worklog/entries", views.WorkLogEntryViewSet, basename="worklog-entry")
router.register("worklog/reports", views.TeamLeadReportViewSet, basename="worklog-report")

urlpatterns = [
    path("worklog/options/", views.WorkLogOptionsView.as_view(), name="worklog-options"),
    path("", include(router.urls)),
]
