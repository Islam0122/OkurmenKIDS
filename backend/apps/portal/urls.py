from django.urls import path

from . import views

app_name = "portal"

student = "students/<int:student_id>/"

urlpatterns = [
    path("me/", views.MeView.as_view(), name="me"),
    path("password/", views.PasswordChangeView.as_view(), name="password"),
    path(f"{student}dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path(f"{student}schedule/", views.ScheduleView.as_view(), name="schedule"),
    path(f"{student}homework/", views.HomeworkListView.as_view(), name="homework"),
    path(f"{student}homework/next/", views.NextHomeworkView.as_view(), name="homework-next"),
    path(f"{student}homework/<int:homework_id>/", views.HomeworkDetailView.as_view(), name="homework-detail"),
    path(f"{student}attendance/", views.AttendanceView.as_view(), name="attendance"),
    path(f"{student}notifications/", views.NotificationsView.as_view(), name="notifications"),
    path(f"{student}feedback/", views.FeedbackView.as_view(), name="feedback"),
    path(f"{student}payments/", views.PaymentsView.as_view(), name="payments"),
    path(f"{student}payments/transactions/", views.PaymentTransactionsView.as_view(), name="payment-transactions"),
    path(f"{student}payments/documents/", views.PaymentDocumentsView.as_view(), name="payment-documents"),
    path(f"{student}payments/receipts/<int:receipt_id>/", views.ReceiptDetailView.as_view(), name="receipt-detail"),
    path(f"{student}payments/receipts/<int:receipt_id>/pdf/", views.ReceiptPdfView.as_view(), name="receipt-pdf"),
    path(f"{student}achievements/", views.AchievementsView.as_view(), name="achievements"),
    path(f"{student}reports/monthly/", views.MonthlyReportView.as_view(), name="monthly-report"),
    path(f"{student}reports/monthly/pdf/", views.MonthlyReportPdfView.as_view(), name="monthly-report-pdf"),
]
