import posixpath
import re

from django.conf import settings
from django.contrib import admin
from django.http import Http404
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
    # Отчёты для родителей: groups/{id}/parent-reports/…, parent-reports/ (см. apps.reports).
    path("api/v1/", include("apps.reports.urls")),
    path("api/v1/", include("apps.news.urls")),
    path("api/v1/", include("apps.feedback.urls")),
    path("api/v1/", include("apps.scholarships.urls")),
    path("api/v1/", include("apps.testing.urls")),
    path("api/v1/", include("apps.training.urls")),
    path("api/v1/", include("apps.testing.monitoring_urls")),
    path("api/v1/", include("apps.worklog.urls")),
    # Проекты студентов — projects/, projects/{id}/images/ (см. apps.projects).
    path("api/v1/", include("apps.projects.urls")),
    # Публичная галерея опубликованных проектов (без входа, только GET) — apps.projects.public.
    path("api/v1/public/projects/", include("apps.projects.public_urls")),
    # Публичные новости академии (без входа, только GET) — apps.academy_news.
    path("api/v1/public/news/", include("apps.academy_news.public_urls")),
    # «Общая статистика» академии: ежедневные показатели и TV-режим (см. apps.performance).
    path("api/v1/monthly-performance/", include("apps.performance.urls")),
    # Public leaderboard (no login, GET only) — see apps.leaderboard.
    path("api/v1/", include("apps.leaderboard.urls")),
    # Assistant Workspace — the Assistant's operational API (see apps.assistant).
    path("api/v1/assistant/", include("apps.assistant.urls")),
    # Месячная матрица посещаемости и ДЗ — все роли академии (apps.attendance_matrix).
    path("api/v1/attendance-matrix/", include("apps.attendance_matrix.urls")),
    # Учебные месяцы программ и прогресс групп (apps.academic_progress).
    path("api/v1/academic-progress/", include("apps.academic_progress.urls")),
    # Бухгалтерия и зарплаты (см. apps.accounting).
    path("api/v1/accounting/", include("apps.accounting.urls")),
    # Учёт прихода и ухода сотрудников по QR-коду офиса (см. apps.staff_attendance).
    path("api/v1/staff-attendance/", include("apps.staff_attendance.urls")),
    # HR-кабинет: вакансии, кандидаты, собеседования, отчёты (см. apps.recruitment).
    # Сотрудники HR — /api/v1/hr/employees/ (apps.users.hr).
    path("api/v1/hr/", include("apps.recruitment.urls")),
    # Кабинет маркетинга: контент-план, задачи, главная, отчёты (см. apps.marketing).
    path("api/v1/marketing/", include("apps.marketing.urls")),
    # Операционное управление: кабинет операционного директора (operations/),
    # задачи и отчёты каждого сотрудника (tasks/, work-reports/), уведомления.
    path("api/v1/", include("apps.operations.urls")),
    # Публичный карьерный сайт: опубликованные вакансии и отклики (без входа).
    path("api/v1/public/careers/", include("apps.recruitment.public_urls")),

    # Web Push для установленного PWA: подписки устройств и настройки (apps.push).
    path("api/v1/push/", include("apps.push.urls")),

    # Public feedback survey links (no login) — /feedback/s/<token>/
    path("feedback/", include("apps.feedback.public_urls")),

    # Student test pages (no login: session key + name) — /exam/
    path("exam/", include("apps.testing.public_urls")),


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


def serve_public_media(request, path, document_root=None):
    """Загрузки из MEDIA_ROOT — кроме закрытого каталога (резюме кандидатов
    и другие персональные файлы отдаются только через API с проверкой прав).
    Путь нормализуется так же, как в serve(), поэтому «a/../private/…» тоже
    не проходит."""
    from apps.recruitment.storage import PRIVATE_MEDIA_DIR

    normalized = posixpath.normpath(path).lstrip("/")
    if normalized == PRIVATE_MEDIA_DIR or normalized.startswith(PRIVATE_MEDIA_DIR + "/"):
        raise Http404
    return serve_media(request, path, document_root=document_root)


if settings.DEBUG or settings.SERVE_MEDIA:
    # In development (DEBUG) and on Railway (no separate web server, see
    # docs/media.md) Django serves MEDIA_URL itself. serve() resolves paths
    # inside document_root only — "..", absolute paths and directory
    # listings are rejected.
    urlpatterns += [
        re_path(
            r"^%s(?P<path>.*)$" % re.escape(settings.MEDIA_URL.lstrip("/")),
            serve_public_media,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]
