from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import report_views, views

router = DefaultRouter()
router.register("courses", views.CourseViewSet, basename="course")
router.register("course-lesson-plans", views.CourseLessonPlanViewSet, basename="course-lesson-plan")
router.register("rooms", views.RoomViewSet, basename="room")
router.register("students", views.StudentViewSet, basename="student")
router.register("groups", views.GroupViewSet, basename="group")
router.register("schedules", views.GroupScheduleViewSet, basename="schedule")
router.register("programs", views.GroupTeacherViewSet, basename="program")
router.register("program-lesson-plans", views.GroupTeacherLessonPlanViewSet, basename="program-lesson-plan")
router.register("lessons", views.LessonViewSet, basename="lesson")
router.register("attendance", views.AttendanceViewSet, basename="attendance")
router.register("homework", views.HomeworkViewSet, basename="homework")
router.register("homework-results", views.HomeworkResultViewSet, basename="homework-result")
router.register("monthly-reports", views.MonthlyTeacherReportViewSet, basename="monthly-report")
router.register("academy-reports", views.AcademyMonthlyReportViewSet, basename="academy-report")

urlpatterns = [
    path("analytics/dashboard/", views.AnalyticsDashboardView.as_view(), name="analytics-dashboard"),
    path("availability/", views.TeacherAvailabilityView.as_view(), name="teacher-availability"),
    # 📊 Reports (admin-only) — see report_views.
    path("reports/overview/", report_views.ReportsOverviewView.as_view(), name="reports-overview"),
    path("reports/filters/", report_views.ReportsFilterOptionsView.as_view(), name="reports-filters"),
    path("reports/groups/", report_views.ReportsGroupsView.as_view(), name="reports-groups"),
    path("reports/groups/<int:pk>/", report_views.ReportsGroupDetailView.as_view(), name="reports-group-detail"),
    path("reports/teachers/", report_views.ReportsTeachersView.as_view(), name="reports-teachers"),
    path("reports/teachers/<int:pk>/", report_views.ReportsTeacherDetailView.as_view(), name="reports-teacher-detail"),
    path("reports/export/pdf/", report_views.ReportsExportPdfView.as_view(), name="reports-export-pdf"),
    path("reports/export/excel/", report_views.ReportsExportExcelView.as_view(), name="reports-export-excel"),
    path("", include(router.urls)),
]
