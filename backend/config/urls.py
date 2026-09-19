from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),

    # API v1 — one flat namespace; apps.users.urls contributes auth/
    # trainers/subjects, apps.academy.urls contributes everything else,
    # apps.news.urls contributes the Teacher-facing news feed.
    path("api/v1/", include("apps.users.urls")),
    path("api/v1/", include("apps.academy.urls")),
    path("api/v1/", include("apps.news.urls")),

    # API documentation
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "swagger-ui/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
