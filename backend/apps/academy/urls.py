from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("courses", views.CourseViewSet, basename="course")
router.register("course-lesson-plans", views.CourseLessonPlanViewSet, basename="course-lesson-plan")
router.register("rooms", views.RoomViewSet, basename="room")
router.register("students", views.StudentViewSet, basename="student")
router.register("groups", views.GroupViewSet, basename="group")
router.register("group-schedules", views.GroupScheduleViewSet, basename="group-schedule")
router.register("lessons", views.LessonViewSet, basename="lesson")
router.register("attendance", views.AttendanceViewSet, basename="attendance")
router.register("homeworks", views.HomeworkViewSet, basename="homework")
router.register("homework-results", views.HomeworkResultViewSet, basename="homework-result")

urlpatterns = [
    path("analytics/dashboard/", views.AnalyticsDashboardView.as_view(), name="analytics-dashboard"),
    path("teacher-availability/", views.TeacherAvailabilityView.as_view(), name="teacher-availability"),
    path("", include(router.urls)),
]
