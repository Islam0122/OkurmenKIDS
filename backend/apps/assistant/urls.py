from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path("options/", views.OptionsView.as_view(), name="options"),
    path("groups/", views.GroupListView.as_view(), name="groups"),
    path("groups/<int:pk>/", views.GroupDetailView.as_view(), name="group-detail"),
    path("groups/<int:pk>/students/", views.GroupStudentsView.as_view(), name="group-students"),
    path("groups/<int:pk>/programs/", views.GroupProgramView.as_view(), name="group-programs"),
    path("groups/<int:pk>/generate-lessons/", views.GroupGenerateLessonsView.as_view(), name="group-generate-lessons"),
    path("students/", views.StudentListView.as_view(), name="students"),
    path("students/bulk/", views.StudentBulkView.as_view(), name="students-bulk"),
    path("students/<int:pk>/", views.StudentDetailView.as_view(), name="student-detail"),
    path("students/<int:pk>/deactivate/", views.StudentDeactivateView.as_view(), name="student-deactivate"),
    path("students/<int:pk>/activate/", views.StudentActivateView.as_view(), name="student-activate"),
    path("students/<int:pk>/transfer/", views.StudentTransferView.as_view(), name="student-transfer"),
    path("schedule/", views.ScheduleView.as_view(), name="schedule"),
    path("lessons/<int:pk>/move/", views.LessonMoveView.as_view(), name="lesson-move"),
    path("lessons/<int:pk>/cancel/", views.LessonCancelView.as_view(), name="lesson-cancel"),
    path("attendance/", views.AttendanceDayView.as_view(), name="attendance"),
    path("attendance/lessons/<int:pk>/", views.AttendanceLessonView.as_view(), name="attendance-lesson"),
    path("scholarships/", views.ScholarshipListView.as_view(), name="scholarships"),
    path("scholarships/generate/", views.ScholarshipGenerateView.as_view(), name="scholarships-generate"),
    path("scholarships/periods/<int:pk>/awards/", views.ScholarshipPeriodAwardsView.as_view(), name="scholarship-awards"),
]
