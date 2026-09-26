import re

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as serve_media

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
    path("api/v1/", include("apps.feedback.urls")),
    path("api/v1/", include("apps.scholarships.urls")),

    # Public feedback survey links (no login) — /feedback/s/<token>/
    path("feedback/", include("apps.feedback.public_urls")),

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
elif settings.SERVE_MEDIA:
    # static() is a no-op once DEBUG is off, so production (Railway, no
    # separate web server) routes uploads through the same serve() view
    # directly. serve() resolves paths inside document_root only — "..",
    # absolute paths and directory listings are rejected.
    urlpatterns += [
        re_path(
            r"^%s(?P<path>.*)$" % re.escape(settings.MEDIA_URL.lstrip("/")),
            serve_media,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]
