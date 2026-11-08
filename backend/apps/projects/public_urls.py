"""Public (no-login) student projects gallery — mounted at /api/v1/public/projects/."""
from django.urls import path

from .public_views import PublicProjectDetailView, PublicProjectListView

urlpatterns = [
    path("", PublicProjectListView.as_view(), name="public-projects"),
    path("<str:key>/", PublicProjectDetailView.as_view(), name="public-project-detail"),
]
