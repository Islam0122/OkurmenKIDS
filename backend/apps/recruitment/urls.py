from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.users.hr import HREmployeeViewSet

from . import views

# Под /api/v1/hr/ — изоляция ролей с базовым доступом пропускает сюда HR
# (apps.accounting.access.STAFF_ONLY_ALLOWED_PREFIXES); права — IsHRManager.
router = DefaultRouter()
# Сотрудники (учётные записи) — apps.users.hr.
router.register("employees", HREmployeeViewSet, basename="hr-employee")
router.register("vacancies", views.VacancyViewSet, basename="hr-vacancy")
router.register("candidates", views.CandidateViewSet, basename="hr-candidate")
router.register("applications", views.ApplicationViewSet, basename="hr-application")
router.register("interviews", views.InterviewViewSet, basename="hr-interview")
router.register("account-requests", views.AccountRequestViewSet, basename="hr-account-request")

urlpatterns = [
    path("meta/", views.MetaView.as_view(), name="hr-meta"),
    path("dashboard/", views.DashboardView.as_view(), name="hr-dashboard"),
    path("reminders/", views.RemindersView.as_view(), name="hr-reminders"),
    path("reports/daily/", views.DailyReportView.as_view(), name="hr-report-daily"),
    path("reports/monthly/", views.MonthlyReportView.as_view(), name="hr-report-monthly"),
    path("", include(router.urls)),
]
