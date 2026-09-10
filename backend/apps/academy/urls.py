from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("courses", views.CourseViewSet, basename="course")
router.register("course-lesson-plans", views.CourseLessonPlanViewSet, basename="course-lesson-plan")
router.register("rooms", views.RoomViewSet, basename="room")
router.register("students", views.StudentViewSet, basename="student")
router.register("groups", views.GroupViewSet, basename="group")
router.register("lessons", views.LessonViewSet, basename="lesson")
router.register("attendance", views.AttendanceViewSet, basename="attendance")
router.register("homeworks", views.HomeworkViewSet, basename="homework")
router.register("homework-results", views.HomeworkResultViewSet, basename="homework-result")
router.register("kpi/groups", views.KPIGroupViewSet, basename="kpi-group")
router.register("kpi/teachers", views.KPITeacherViewSet, basename="kpi-teacher")
router.register("kpi/students", views.KPIStudentViewSet, basename="kpi-student")
router.register("kpi/lessons", views.KPILessonViewSet, basename="kpi-lesson")
router.register("kpi/attendance", views.KPIAttendanceViewSet, basename="kpi-attendance")
router.register("kpi/homework", views.KPIHomeworkViewSet, basename="kpi-homework")

# `.../calculate/` takes the *source* entity's id (Group/Teacher/Student/Lesson),
# so these are plain APIViews rather than actions on the KPI viewsets above
# (whose detail pk is the KPI record's own id).
kpi_calculate_urlpatterns = [
    path("kpi/groups/<int:pk>/calculate/", views.KPIGroupCalculateView.as_view(), name="kpi-group-calculate"),
    path("kpi/teachers/<int:pk>/calculate/", views.KPITeacherCalculateView.as_view(), name="kpi-teacher-calculate"),
    path("kpi/students/<int:pk>/calculate/", views.KPIStudentCalculateView.as_view(), name="kpi-student-calculate"),
    path("kpi/lessons/<int:pk>/calculate/", views.KPILessonCalculateView.as_view(), name="kpi-lesson-calculate"),
    path("kpi/attendance/<int:pk>/calculate/", views.KPIAttendanceCalculateView.as_view(), name="kpi-attendance-calculate"),
    path("kpi/homework/<int:pk>/calculate/", views.KPIHomeworkCalculateView.as_view(), name="kpi-homework-calculate"),
]

urlpatterns = kpi_calculate_urlpatterns + [
    path("", include(router.urls)),
]
