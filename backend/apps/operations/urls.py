from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import task_views, views

# Шаблоны повторений регистрируются раньше задач: иначе «recurrences» был бы
# принят за id задачи (tasks/{pk}/).
router = DefaultRouter()
router.register("tasks/recurrences", task_views.RecurrenceViewSet, basename="task-recurrence")
router.register("tasks", task_views.TaskViewSet, basename="task")
router.register("work-reports", task_views.WorkReportViewSet, basename="work-report")
router.register("notifications", task_views.NotificationViewSet, basename="notification")
router.register("operations/kpi/targets", views.KPITargetViewSet, basename="ops-kpi-target")
router.register("operations/issues", views.IssueViewSet, basename="ops-issue")

# /api/v1/operations/… — кабинет операционного директора (CanOversee).
operations = [
    path("meta/", views.MetaView.as_view(), name="ops-meta"),
    path("dashboard/", views.DashboardView.as_view(), name="ops-dashboard"),
    path("departments/", views.DepartmentsView.as_view(), name="ops-departments"),
    path("departments/<str:key>/", views.DepartmentDetailView.as_view(), name="ops-department"),
    path("employees/", views.EmployeesView.as_view(), name="ops-employees"),
    path("employees/<int:pk>/", views.EmployeeProfileView.as_view(), name="ops-employee"),
    path("trainers/", views.TrainersView.as_view(), name="ops-trainers"),
    path("trainers/<int:pk>/", views.TrainerDetailView.as_view(), name="ops-trainer"),
    path("team-leads/", views.TeamLeadsView.as_view(), name="ops-team-leads"),
    path("assistants/", views.AssistantsView.as_view(), name="ops-assistants"),
    path("students/problems/", views.ProblemStudentsView.as_view(), name="ops-problem-students"),
    path("sales/", views.SalesView.as_view(), name="ops-sales"),
    path("sales/head/", views.HeadOfSalesView.as_view(), name="ops-sales-head"),
    path("marketing/", views.MarketingView.as_view(), name="ops-marketing"),
    path("hr/", views.HRView.as_view(), name="ops-hr"),
    path("attendance/", views.StaffAttendanceView.as_view(), name="ops-attendance"),
    path("daily/", views.DailyControlView.as_view(), name="ops-daily"),
    path("kpi/", views.KPIOverviewView.as_view(), name="ops-kpi"),
    path("kpi/history/", views.KPIHistoryView.as_view(), name="ops-kpi-history"),
    path("reports/", views.ReportsView.as_view(), name="ops-reports"),
    path("reports/export/", views.ReportExportView.as_view(), name="ops-reports-export"),
    path("activity/", views.ActivityView.as_view(), name="ops-activity"),
    path("settings/", views.SettingsView.as_view(), name="ops-settings"),
    path("scan/", views.ScanView.as_view(), name="ops-scan"),
]

urlpatterns = [
    path("operations/", include(operations)),
    path("", include(router.urls)),
]
