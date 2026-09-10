from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.users import views

router = DefaultRouter()
router.register("trainers", views.TrainerViewSet, basename="trainer")

auth_urlpatterns = [
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("refresh/", views.RefreshView.as_view(), name="auth-refresh"),
    path("me/", views.MeView.as_view(), name="auth-me"),
]

urlpatterns = [
    path("", views.health, name="users-health"),
    path("auth/", include(auth_urlpatterns)),
    path("", include(router.urls)),
]
