from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

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

urlpatterns = [
    path("analytics/dashboard/", views.AnalyticsDashboardView.as_view(), name="analytics-dashboard"),
    path("availability/", views.TeacherAvailabilityView.as_view(), name="teacher-availability"),
    path("", include(router.urls)),
]
