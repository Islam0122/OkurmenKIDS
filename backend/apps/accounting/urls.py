from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

app_name = "accounting"

router = DefaultRouter()
router.register("salary-profiles", views.SalaryProfileViewSet, basename="salary-profile")
router.register("salary-rules", views.SalaryRuleViewSet, basename="salary-rule")
router.register("student-payments", views.StudentPaymentViewSet, basename="student-payment")
router.register("periods", views.PayrollPeriodViewSet, basename="period")
router.register("payrolls", views.PayrollViewSet, basename="payroll")
router.register("payments", views.PaymentViewSet, basename="payment")
router.register("adjustments", views.AdjustmentViewSet, basename="adjustment")
router.register("audit-log", views.AuditLogViewSet, basename="audit-log")
router.register("my/payrolls", views.MyPayrollViewSet, basename="my-payroll")

urlpatterns = [
    path("me/", views.MeView.as_view(), name="me"),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("options/", views.OptionsView.as_view(), name="options"),
    path("students/", views.StudentLookupView.as_view(), name="students"),
    path("employees/", views.EmployeeListView.as_view(), name="employees"),
    path("reports/payroll.pdf", views.PayrollReportPdfView.as_view(), name="report-pdf"),
    path("reports/payroll.xlsx", views.PayrollReportXlsxView.as_view(), name="report-xlsx"),
    path("", include(router.urls)),
]
