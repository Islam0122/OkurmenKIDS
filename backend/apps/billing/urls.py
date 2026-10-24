"""Оплата обучения — /api/v1/accounting/billing/ (внутри зоны бухгалтерии,
поэтому изолированный бухгалтер имеет к ней доступ; менеджер и
администратор оплаты — по своим правам)."""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "billing"

router = DefaultRouter()
router.register("plans", views.PlanViewSet, basename="plan")
router.register("profiles", views.ProfileViewSet, basename="profile")
router.register("terms-changes", views.TermsChangeViewSet, basename="terms-change")
router.register("packages", views.PackageViewSet, basename="package")
router.register("consumptions", views.ConsumptionViewSet, basename="consumption")
router.register("invoices", views.InvoiceViewSet, basename="invoice")
router.register("payments", views.PaymentViewSet, basename="payment")
router.register("allocations", views.AllocationViewSet, basename="allocation")
router.register("reservations", views.ReservationViewSet, basename="reservation")
router.register("tasks", views.TaskViewSet, basename="task")
router.register("contacts", views.ContactViewSet, basename="contact")
router.register("notifications", views.NotificationViewSet, basename="notification")
router.register("receipts", views.ReceiptViewSet, basename="receipt")

urlpatterns = [
    path("me/", views.MeView.as_view(), name="me"),
    path("options/", views.OptionsView.as_view(), name="options"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("students/", views.StudentsView.as_view(), name="students"),
    path("debts/", views.DebtorsView.as_view(), name="debts"),
    path("reports/summary/", views.FinancialReportView.as_view(), name="report-summary"),
    path("reports/period/", views.PeriodReportView.as_view(), name="report-period"),
    path("periods/", views.PeriodsView.as_view(), name="periods"),
    path("periods/review/", views.PeriodReviewView.as_view(), name="period-review"),
    path("audit-log/", views.AuditView.as_view(), name="audit-log"),
    path("queues/counts/", views.QueueCountsView.as_view(), name="queue-counts"),
    path("queues/<str:queue>/", views.QueueView.as_view(), name="queue"),
    path("analytics/", views.AnalyticsView.as_view(), name="analytics"),
    path("settings/", views.SettingsView.as_view(), name="settings"),
    path("", include(router.urls)),
]
