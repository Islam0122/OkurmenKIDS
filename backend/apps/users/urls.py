from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import hr, views

router = DefaultRouter()
router.register("trainers", views.TrainerViewSet, basename="trainer")
router.register("subjects", views.SubjectViewSet, basename="subject")

# Раздел «Сотрудники» HR-менеджера: /api/v1/hr/employees/.
hr_router = DefaultRouter()
hr_router.register("employees", hr.HREmployeeViewSet, basename="hr-employee")

auth_urlpatterns = [
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("refresh/", views.RefreshView.as_view(), name="auth-refresh"),
    path("me/", views.MeView.as_view(), name="auth-me"),
]

urlpatterns = [
    path("", views.health, name="users-health"),
    path("auth/", include(auth_urlpatterns)),
    path("hr/", include(hr_router.urls)),
    path("", include(router.urls)),
]
