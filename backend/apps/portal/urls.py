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
    path(f"{student}homework/<int:homework_id>/", views.HomeworkDetailView.as_view(), name="homework-detail"),
    path(f"{student}attendance/", views.AttendanceView.as_view(), name="attendance"),
    path(f"{student}notifications/", views.NotificationsView.as_view(), name="notifications"),
    path(f"{student}feedback/", views.FeedbackView.as_view(), name="feedback"),
    path(f"{student}payments/", views.PaymentsView.as_view(), name="payments"),
    path(f"{student}reports/monthly/", views.MonthlyReportView.as_view(), name="monthly-report"),
    path(f"{student}reports/monthly/pdf/", views.MonthlyReportPdfView.as_view(), name="monthly-report-pdf"),
]
