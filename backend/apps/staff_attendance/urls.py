from django.urls import path

from . import views

# Личные эндпоинты — под me/: только их бухгалтерская изоляция пропускает
# (apps.accounting.access.ALLOWED_PREFIXES).
urlpatterns = [
    path("me/status/", views.MeStatusView.as_view(), name="staff-attendance-me-status"),
    path("me/locations/<str:code>/", views.MeLocationView.as_view(), name="staff-attendance-me-location"),
    path("me/check-in/", views.MeCheckInView.as_view(), name="staff-attendance-check-in"),
    path("me/check-out/", views.MeCheckOutView.as_view(), name="staff-attendance-check-out"),
    path("me/history/", views.MeHistoryView.as_view(), name="staff-attendance-me-history"),
    path("me/stats/", views.MeStatsView.as_view(), name="staff-attendance-me-stats"),

    path("admin/meta/", views.AdminMetaView.as_view(), name="staff-attendance-meta"),
    path("admin/overview/", views.AdminOverviewView.as_view(), name="staff-attendance-overview"),
    path("admin/records/", views.AdminRecordsView.as_view(), name="staff-attendance-records"),
    path("admin/export/", views.AdminExportView.as_view(), name="staff-attendance-export"),
    path("admin/employees/<int:user_id>/", views.AdminEmployeeView.as_view(), name="staff-attendance-employee"),
    path("admin/employees/<int:user_id>/schedule/", views.EmployeeScheduleView.as_view(),
         name="staff-attendance-employee-schedule"),
    path("admin/sessions/", views.AdminManualSessionView.as_view(), name="staff-attendance-manual-session"),
    path("admin/sessions/<int:session_id>/adjust/", views.AdminAdjustSessionView.as_view(),
         name="staff-attendance-adjust"),
    path("admin/adjustments/", views.AdminAdjustmentsView.as_view(), name="staff-attendance-adjustments"),
    path("admin/locations/", views.LocationListView.as_view(), name="staff-attendance-locations"),
    path("admin/locations/<int:pk>/", views.LocationDetailView.as_view(), name="staff-attendance-location"),
    path("admin/locations/<int:pk>/qr.svg", views.LocationQRView.as_view(), name="staff-attendance-location-qr"),
    path("admin/settings/", views.SettingsView.as_view(), name="staff-attendance-settings"),
    path("admin/schedules/", views.ScheduleListView.as_view(), name="staff-attendance-schedules"),
    path("admin/log/", views.AdminLogView.as_view(), name="staff-attendance-log"),
]
