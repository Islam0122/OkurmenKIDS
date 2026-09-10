from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("students", views.StudentViewSet, basename="student")
router.register("groups", views.GroupViewSet, basename="group")
router.register("rooms", views.RoomViewSet, basename="room")
router.register("schedules", views.ScheduleViewSet, basename="schedule")
router.register("attendance", views.AttendanceViewSet, basename="attendance")
router.register("homework", views.HomeworkViewSet, basename="homework")
router.register("kpi", views.KPIViewSet, basename="kpi")

urlpatterns = [
    path("", include(router.urls)),
]
