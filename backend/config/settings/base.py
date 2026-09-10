import os
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

environ.Env.read_env(
    os.path.join(BASE_DIR, ".env")
)

SECRET_KEY = env(
    "SECRET_KEY",
    default="django-insecure-change-me",
)

DEBUG = False

ALLOWED_HOSTS = []

DJANGO_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "drf_spectacular",
    "django_filters",
]

LOCAL_APPS = [
    "apps.users.apps.UsersConfig",
]

INSTALLED_APPS = (
    DJANGO_APPS
    + THIRD_PARTY_APPS
    + LOCAL_APPS
)

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME":
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator",
    },
    {
        "NAME":
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator",
    },
    {
        "NAME":
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator",
    },
    {
        "NAME":
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator",
    },
]

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7

LANGUAGE_CODE = "ru"

TIME_ZONE = "Asia/Bishkek"

USE_I18N = True
USE_TZ = True


STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "users.User"


REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # "DEFAULT_PERMISSION_CLASSES": [
    #     "rest_framework.permissions.IsAuthenticated",
    # ],
    "DEFAULT_SCHEMA_CLASS": (
        "drf_spectacular.openapi.AutoSchema"
    ),
    "DEFAULT_PAGINATION_CLASS": (
        "rest_framework.pagination.PageNumberPagination"
    ),
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

EMAIL_VERIFICATION_TOKEN_MAX_AGE = 60 * 60 * 24 * 3  # 3 days

FRONTEND_BASE_URL = env(
    "FRONTEND_BASE_URL",
    default="http://localhost:8000",
)

SPECTACULAR_SETTINGS = {
    "TITLE": "OkurmenKIDS API",
    "DESCRIPTION": "REST API for OkurmenKIDS Academy Management System",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "TAGS": [
        {"name": "Authentication", "description": "Authentication and authorization"},
        {"name": "Trainers", "description": "Trainer management"},
        {"name": "Students", "description": "Student management"},
        {"name": "Groups", "description": "Group management"},
        {"name": "Courses", "description": "Course management"},
        {"name": "Rooms", "description": "Classroom management"},
        {"name": "Schedules", "description": "Schedule management"},
        {"name": "Attendance", "description": "Attendance management"},
        {"name": "Homework", "description": "Homework management"},
        {"name": "KPI", "description": "KPI and performance analytics"},
    ],
}

from .cors import *

JAZZMIN_SETTINGS = {
    "site_title": "OkurmenKIDS",
    "site_header": "OkurmenKIDS",
    "site_brand": "OkurmenKIDS",
    # No custom logo asset — the sidebar brand mark is drawn with CSS
    # (an "OK" emblem + wordmark) instead of an <img>; hide Jazzmin's
    # bundled default logo rather than requiring a new binary asset.
    "site_logo_classes": "ok-hidden-logo",

    "welcome_sign": "Добро пожаловать в OkurmenKIDS 👋",
    "copyright": "OkurmenKIDS © 2026",

    "show_sidebar": True,
    "navigation_expanded": True,
    "use_google_fonts_cdn": False,
    "show_ui_builder": True,
    "changeform_format": "single",



    # Hide the raw "Users" app group from the sidebar — Teacher and Subject
    # are exposed instead under the "Обучение" custom group below, in the
    # order the product actually wants them shown. Admin accounts stay
    # reachable under "Система".
    "hide_apps": ["users"],

    "custom_links": {
        "обучение": [
            {"name": "Тренеры", "model": "users.teacher", "icon": "bi bi-person-badge"},
            {"name": "Предметы", "model": "users.subject", "icon": "bi bi-journal-bookmark"},
            {"name": "Студенты · скоро", "url": "#", "icon": "bi bi-mortarboard"},
            {"name": "Группы · скоро", "url": "#", "icon": "bi bi-people"},
            {"name": "Расписание · скоро", "url": "#", "icon": "bi bi-calendar-week"},
            {"name": "Посещаемость · скоро", "url": "#", "icon": "bi bi-clipboard-check"},
            {"name": "Домашние задания · скоро", "url": "#", "icon": "bi bi-journal-text"},
            {"name": "KPI · скоро", "url": "#", "icon": "bi bi-graph-up-arrow"},
        ],
    },

    # NOTE: Jazzmin lower-cases every key in "icons" internally, so custom
    # group keys above are kept lowercase too — otherwise the icon lookup
    # silently misses. The sidebar visually re-uppercases these via CSS
    # (.nav-header { text-transform: uppercase }), which is also just the
    # more typical look for section labels in a premium dashboard.
    "icons": {
        "обучение": "bi bi-mortarboard-fill",
        "система": "bi bi-gear",
        "auth": "bi bi-people",
        "auth.group": "bi bi-people",
        "users.user": "bi bi-shield-lock",
        # "model"-type custom_links entries ignore their own "icon" key and
        # look the icon up here by "app_label.model" instead — so Тренеры
        # and Предметы need entries here too, not just in custom_links.
        "users.teacher": "bi bi-person-badge",
        "users.subject": "bi bi-journal-bookmark",
    },
    "default_icon_parents": "bi bi-folder2",
    "default_icon_children": "bi bi-circle",

    # UI tweaks (fonts, icons, colours) — everything else lives in the CSS.
    "custom_css": "okurmenkids/css/theme.css",
    "custom_js": "okurmenkids/js/ui.js",
}

JAZZMIN_UI_TWEAKS = {
"theme": "flatly",

"navbar": "navbar-white navbar-light",
"no_navbar_border": True,
"navbar_fixed": True,

"sidebar": "sidebar-light-primary",
"sidebar_fixed": True,
"sidebar_nav_flat_style": True,
"sidebar_nav_child_indent": True,

"footer_fixed": False,
"layout_boxed": False,

"accent": "accent-success",

"button_classes": {
    "primary": "btn-success",
    "secondary": "btn-outline-success",
    "info": "btn-success",
    "warning": "btn-warning",
    "danger": "btn-danger",
    "success": "btn-success",
},


}
