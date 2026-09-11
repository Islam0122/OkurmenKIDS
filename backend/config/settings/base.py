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
SITE_URL = os.getenv("SITE_URL")
DEBUG = False

ALLOWED_HOSTS = []

DJANGO_APPS = [
    "jazzmin",
    # Swaps in OkurmenKidsAdminSite (custom dashboard template + live
    # stats) as the default admin site — see apps/users/apps.py and
    # apps/users/admin_site.py. Must replace "django.contrib.admin"
    # here, not merely subclass it elsewhere, or admin.site.urls keeps
    # resolving to the stock AdminSite and the dashboard never renders.
    "apps.users.apps.OkurmenKidsAdminConfig",
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
    "apps.academy.apps.AcademyConfig",

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

LANGUAGE_CODE = "ru-ru"

TIME_ZONE = "Asia/Bishkek"

USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# No project-level static/ directory — every static asset (Jazzmin theme
# CSS/JS, admin templates' assets) lives under its owning app's own
# static/ folder and is picked up by the default AppDirectoriesFinder.
# STATICFILES_DIRS is for *extra* directories beyond that; pointing it at
# a directory that doesn't exist just produces a staticfiles.W004 warning
# on every check/test run.

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "users.User"


REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    # Safe-by-default: any view/action that forgets to declare its own
    # permission_classes falls back to "must be authenticated" rather than
    # DRF's own library default (AllowAny). Every view in this project sets
    # its own permissions explicitly anyway — this is a foot-gun guard for
    # whatever gets added next, not a behavior change for what exists today.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
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
    # Group/Lesson/Attendance/HomeworkResult all have their own `status`
    # field, so drf-spectacular's auto-naming collides on plain "Status"
    # and falls back to opaque names like "StatusB16Enum" — give each one
    # its real name instead.
    "ENUM_NAME_OVERRIDES": {
        "GroupStatusEnum": "apps.academy.models.Group.Status",
        "LessonStatusEnum": "apps.academy.models.Lesson.Status",
        "AttendanceStatusEnum": "apps.academy.models.Attendance.Status",
        "HomeworkResultStatusEnum": "apps.academy.models.HomeworkResult.Status",
    },
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
        {"name": "Analytics", "description": "KPI and performance analytics"},
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
    "changeform_format": "single",



    # Hide the raw "Users"/"Academy" app groups from the sidebar — every
    # model in them is exposed instead through the custom groups below,
    # grouped the way an academy admin actually thinks about them
    # (teaching staff/students, organisation, day-to-day control, system)
    # rather than by Django app label.
    "hide_apps": ["users", "academy"],

    "custom_links": {
        "обучение": [
            {"name": "Курсы", "model": "academy.course", "icon": "bi bi-collection-play"},
            {"name": "Планы занятий", "model": "academy.courselessonplan", "icon": "bi bi-list-check"},
            {"name": "Группы", "model": "academy.group", "icon": "bi bi-people"},
            {"name": "Студенты", "model": "academy.student", "icon": "bi bi-mortarboard"},
            {"name": "Тренеры", "model": "users.teacher", "icon": "bi bi-person-badge"},
            {"name": "Предметы", "model": "users.subject", "icon": "bi bi-journal-bookmark"},
            {"name": "Аудитории", "model": "academy.room", "icon": "bi bi-door-open"},
            {"name": "Занятия", "model": "academy.lesson", "icon": "bi bi-calendar-week"},
            {"name": "Расписание", "url": "admin:academy_schedule", "icon": "bi bi-calendar-week"},
            {"name": "Посещаемость", "model": "academy.attendance", "icon": "bi bi-clipboard-check"},
            {"name": "Домашние задания", "model": "academy.homework", "icon": "bi bi-journal-text"},
            {"name": "Результаты ДЗ", "model": "academy.homeworkresult", "icon": "bi bi-check2-square"},
        ],
        "аналитика": [
            {"name": "Dashboard", "url": "admin:academy_analytics", "icon": "bi bi-graph-up-arrow"},
        ],
        "система": [
            {"name": "Администраторы", "model": "users.user", "icon": "bi bi-shield-lock"},
        ],
    },

    # NOTE: Jazzmin lower-cases every key in "icons" internally, so custom
    # group keys above are kept lowercase too — otherwise the icon lookup
    # silently misses. The sidebar visually re-uppercases these via CSS
    # (.nav-header { text-transform: uppercase }), which is also just the
    # more typical look for section labels in a premium dashboard.
    "icons": {
        "обучение": "bi bi-mortarboard-fill",
        "аналитика": "bi bi-clipboard-data",
        "система": "bi bi-gear",
        "auth": "bi bi-people",
        "auth.group": "bi bi-people",
        "users.user": "bi bi-shield-lock",
        # "model"-type custom_links entries ignore their own "icon" key and
        # look the icon up here by "app_label.model" instead — so every
        # model-backed entry above needs an entry here too, not just in
        # custom_links.
        "users.teacher": "bi bi-person-badge",
        "users.subject": "bi bi-journal-bookmark",
        "academy.course": "bi bi-collection-play",
        "academy.courselessonplan": "bi bi-list-check",
        "academy.student": "bi bi-mortarboard",
        "academy.group": "bi bi-people",
        "academy.room": "bi bi-door-open",
        "academy.lesson": "bi bi-calendar-week",
        "academy.attendance": "bi bi-clipboard-check",
        "academy.homework": "bi bi-journal-text",
        "academy.homeworkresult": "bi bi-check2-square",
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
