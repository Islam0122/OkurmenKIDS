from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("parent-reports", views.ParentReportViewSet, basename="parent-report")

urlpatterns = [
    path("groups/<int:group_id>/parent-reports/preview/", views.GroupReportPreviewView.as_view(), name="parent-report-preview"),
    path("groups/<int:group_id>/parent-reports/generate/", views.GroupReportGenerateView.as_view(), name="parent-report-generate"),
    path("", include(router.urls)),
]
