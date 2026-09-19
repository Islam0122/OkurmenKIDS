from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("teacher/news", views.TeacherNewsViewSet, basename="teacher-news")

urlpatterns = [
    path("", include(router.urls)),
]
