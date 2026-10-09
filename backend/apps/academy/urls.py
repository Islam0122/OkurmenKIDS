from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import control_views, report_views, schedule_views, views

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
    # Reports (Admin + Team Lead, read-only) — see report_views.
    path("reports/overview/", report_views.ReportsOverviewView.as_view(), name="reports-overview"),
    path("reports/filters/", report_views.ReportsFilterOptionsView.as_view(), name="reports-filters"),
    path("reports/groups/", report_views.ReportsGroupsView.as_view(), name="reports-groups"),
    path("reports/groups/<int:pk>/", report_views.ReportsGroupDetailView.as_view(), name="reports-group-detail"),
    path("reports/subjects/", report_views.ReportsSubjectsView.as_view(), name="reports-subjects"),
    path("reports/subjects/<int:pk>/", report_views.ReportsSubjectDetailView.as_view(), name="reports-subject-detail"),
    path("reports/students/", report_views.ReportsStudentsView.as_view(), name="reports-students"),
    path("reports/teachers/", report_views.ReportsTeachersView.as_view(), name="reports-teachers"),
    path("reports/teachers/<int:pk>/", report_views.ReportsTeacherDetailView.as_view(), name="reports-teacher-detail"),
    path("reports/export/pdf/", report_views.ReportsExportPdfView.as_view(), name="reports-export-pdf"),
    path("reports/export/excel/", report_views.ReportsExportExcelView.as_view(), name="reports-export-excel"),
    # Control — is every lesson's attendance/homework/scores filled in? See control_views.
    path("control/", control_views.ControlOverviewView.as_view(), name="control-overview"),
    path("control/detail/", control_views.ControlDetailView.as_view(), name="control-detail"),
    path("control/lessons/<int:pk>/", control_views.ControlLessonView.as_view(), name="control-lesson"),
    # «Расписание» of Team Lead / Assistant (read; writes via apps.assistant) — see schedule_views.
    path("schedule/options/", schedule_views.ScheduleOptionsView.as_view(), name="schedule-options"),
    path("schedule/board/", schedule_views.ScheduleBoardView.as_view(), name="schedule-board"),
    path("schedule/free-rooms/", schedule_views.FreeRoomsView.as_view(), name="schedule-free-rooms"),
    path("schedule/check/", schedule_views.ConflictCheckView.as_view(), name="schedule-check"),
    path("", include(router.urls)),
]
