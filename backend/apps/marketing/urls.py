from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

# Под /api/v1/marketing/ — изоляция ролей с базовым доступом пропускает сюда
# сотрудников (apps.accounting.access.STAFF_ONLY_ALLOWED_PREFIXES); права —
# IsMarketingTeam (маркетинг и администратор).
router = DefaultRouter()
router.register("content", views.ContentItemViewSet, basename="marketing-content")
router.register("tasks", views.MarketingTaskViewSet, basename="marketing-task")
router.register("campaigns", views.CampaignViewSet, basename="marketing-campaign")

urlpatterns = [
    path("meta/", views.MetaView.as_view(), name="marketing-meta"),
    path("dashboard/", views.DashboardView.as_view(), name="marketing-dashboard"),
    path("reports/", views.ReportView.as_view(), name="marketing-report"),
    path("", include(router.urls)),
]
