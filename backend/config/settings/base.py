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
    "apps.data_io.apps.DataIoConfig",
    "apps.news.apps.NewsConfig",
    "apps.feedback.apps.FeedbackConfig",
    "apps.scholarships.apps.ScholarshipsConfig",
    "apps.testing.apps.TestingConfig",
    "apps.training.apps.TrainingConfig",
    "apps.worklog.apps.WorklogConfig",
    "apps.assistant.apps.AssistantConfig",
    "apps.accounting.apps.AccountingConfig",

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
    # Records who changed a group's trainer (academy.TrainerAssignment.changed_by).
    "apps.academy.services.trainer_history.ActorMiddleware",
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

# Logs redacted metadata for every CSRF rejection and shows a friendly page
# on public feedback links — see config/csrf.py. Rejection rules unchanged.
CSRF_FAILURE_VIEW = "config.csrf.csrf_failure"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7

LANGUAGE_CODE = "ru-ru"

TIME_ZONE = "Asia/Bishkek"

USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# No project-level static/ directory — every static asset (Jazzmin theme
# CSS/JS, admin templates' assets) lives under its owning app's own
# static/ folder and is picked up by the default AppDirectoriesFinder.
# STATICFILES_DIRS is for *extra* directories beyond that; pointing it at
# a directory that doesn't exist just produces a staticfiles.W004 warning
# on every check/test run.

MEDIA_URL = "/media/"
MEDIA_ROOT = os.getenv("MEDIA_ROOT", str(BASE_DIR / "media"))

# Whether Django itself serves MEDIA_URL when DEBUG is off (see
# config/urls.py). Off by default; production.py turns it on because there
# is no separate web server/CDN in front of the app on Railway.
SERVE_MEDIA = False


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# KPI weights — the one place they are defined (services.kpi_engine).
# Equal weights = the project's existing KPI formula. Retention and teacher
# workload are reported alongside but are not part of the total.
KPI_WEIGHTS = {"attendance": 0.25, "homework": 0.25, "lesson_completion": 0.25, "progress": 0.25}

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
        # Public feedback survey links (per client IP, no login) — see
        # apps/feedback/public.py. Shared by the HTML page and the JSON API.
        "feedback_view": "300/hour",
        "feedback_submit": "30/hour",
        # Public training portal (apps/training, per client IP, no login).
        # A whole class often shares one school IP, hence the generous reads.
        "training_read": "3000/hour",
        "training_start": "120/hour",
        "training_write": "3000/hour",
        # Public schedule site (apps/academy/public_schedule_views, per IP, no login).
        "public_schedule": env("PUBLIC_SCHEDULE_RATE", default="1200/hour"),
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

# Optional absolute origin for public feedback survey links (e.g.
# "https://kids.okurmen.kg"). Empty = the host the Admin is using right now,
# via request.build_absolute_uri — see apps/feedback/public.py.
FEEDBACK_PUBLIC_BASE_URL = env("FEEDBACK_PUBLIC_BASE_URL", default="")

# The LMS itself (React SPA): where trainers and the Team Lead sign in
# (<LMS_FRONTEND_URL>/login). Shown on the Django admin login page and in the
# user admin, so nobody tries to enter the LMS through /admin/.
LMS_FRONTEND_URL = env("LMS_FRONTEND_URL", default="https://okurmen-kids-drab.vercel.app").rstrip("/")

# Assistant «Контроль активности»: thresholds of the student statuses
# (Норма / Требует внимания / Низкая активность / В зоне риска) and of the
# categories. Any key set here overrides its default in
# apps.assistant.activity.DEFAULT_THRESHOLDS, e.g. {"risk_attendance": 45}.
ASSISTANT_CONTROL_THRESHOLDS: dict = {}

# Бухгалтерия (apps.accounting): может ли бухгалтер сам утверждать начисления
# (по умолчанию — только директор), разрешена ли выплата сверх остатка и шаг
# округления сумм (0.01 — до тыйына).
ACCOUNTING_ACCOUNTANT_CAN_APPROVE = env.bool("ACCOUNTING_ACCOUNTANT_CAN_APPROVE", default=False)
ACCOUNTING_ALLOW_OVERPAYMENT = env.bool("ACCOUNTING_ALLOW_OVERPAYMENT", default=False)
ACCOUNTING_ROUNDING_QUANTUM = env("ACCOUNTING_ROUNDING_QUANTUM", default="0.01")

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
        {"name": "News", "description": "Teacher-facing news and announcements"},
        {"name": "Feedback", "description": "Feedback surveys for parents and students"},
        {"name": "Scholarships", "description": "Monthly scholarship evaluation, ranking and trainer feedback"},
    ],
}

from .cors import *

JAZZMIN_SETTINGS = {
    "site_title": "OkurmenKids",
    "site_header": "OkurmenKids",
    "site_brand": "OkurmenKids",
    "site_logo": "images/logo.png",
    "site_icon": "images/logo.png",
    # No extra Bootstrap classes needed — sizing/visibility for the real
    # logo.png is handled by the .sidebar-brand rules in theme.css.
    "site_logo_classes": "",
    "show_ui_builder": False,
    "welcome_sign": "Добро пожаловать в OkurmenKids ",
    "copyright": "OkurmenKIDS © 2026",

    "show_sidebar": True,
    "navigation_expanded": True,
    "use_google_fonts_cdn": False,
    "changeform_format": "single",



    # Hide the raw Django app groups from the sidebar — every model in them
    # is exposed instead through the sections below, grouped the way an
    # academy admin actually thinks about them rather than by app label.
    "hide_apps": ["users", "academy", "data_io", "news", "feedback", "scholarships", "testing", "training"],

    # Sidebar sections, in display order. Each key is one collapsible
    # section of the custom sidebar (templates/admin/base_site.html); the
    # "Главная" link above them is rendered by that template itself.
    #
    # - "model" entries keep Jazzmin's own permission check (view/change
    #   perm on that model); their label comes from verbose_name_plural.
    # - "url" entries are for custom admin views; their "permissions" key
    #   (all required) is the only sidebar-level gate, the views keep
    #   their own backend checks.
    "custom_links": {
        "академия": [
            {"name": "Студенты", "model": "academy.student", "icon": "bi bi-mortarboard"},
            {"name": "Группы", "model": "academy.group", "icon": "bi bi-people"},
            {"name": "Тренеры", "model": "users.teacher", "icon": "bi bi-person-badge"},
            {
                # Operational control of trainers (not KPI) — see
                # control_admin_views; access is decided there
                # (services.control.access), so no sidebar-level gate.
                "name": "Контроль тренеров",
                "url": "admin:academy_control_teachers",
                "icon": "bi bi-clipboard2-check",
            },
            {
                "name": "Неактивные студенты",
                "url": "admin:academy_inactive_students",
                "icon": "bi bi-person-dash",
                "permissions": ["academy.view_studentstatusevent"],
            },
        ],

        # Reports for the academy's management — Admin/superuser only
        # (backend-enforced in report_admin_views; this permission only
        # hides the entry from non-admin staff, same as "Отчёт академии").
        "отчёты": [
            {
                "name": "Обзор",
                "url": "admin:academy_reports_overview",
                "icon": "bi bi-graph-up",
                "permissions": ["academy.view_academymonthlyreport"],
            },
            {
                "name": "Группы",
                "url": "admin:academy_reports_groups",
                "icon": "bi bi-layers",
                "permissions": ["academy.view_academymonthlyreport"],
            },
            {
                "name": "Предметы",
                "url": "admin:academy_reports_subjects",
                "icon": "bi bi-book",
                "permissions": ["academy.view_academymonthlyreport"],
            },
            {
                "name": "Тренеры",
                "url": "admin:academy_reports_teachers",
                "icon": "bi bi-mortarboard",
                "permissions": ["academy.view_academymonthlyreport"],
            },
        ],

        "обучение": [
            {"name": "Курсы", "model": "academy.course", "icon": "bi bi-collection-play"},
            {"name": "Планы занятий", "model": "academy.courselessonplan", "icon": "bi bi-list-check"},
            {"name": "Предметы", "model": "users.subject", "icon": "bi bi-book"},
            {"name": "Занятия", "model": "academy.lesson", "icon": "bi bi-easel"},
            {"name": "Расписание", "url": "admin:academy_schedule", "icon": "bi bi-calendar3"},
            # Tests define what is asked (questions, settings, publishing);
            # Sessions define who takes a test, when and for which group,
            # and hold the results. «Создать сессию» lives inside «Сессии».
            {"name": "Тесты", "model": "testing.test", "icon": "bi bi-clipboard2-check"},
            {"name": "Сессии", "model": "testing.testsession", "icon": "bi bi-broadcast"},
            {"name": "Результаты тестов", "model": "testing.testresult", "icon": "bi bi-clipboard-data"},
            {"name": "Мониторинг экзаменов", "url": "admin:testing_exam_monitoring", "icon": "bi bi-shield-check"},
        ],

        # Public training portal (React app): tests come from training
        # sessions marked «Публичная тренировка»; here — its texts, the real
        # exam link, videos and useful links.
        "тренировочный портал": [
            {"name": "Тренажёры", "model": "training.trainer", "icon": "bi bi-controller"},
            {"name": "Попытки тренажёров", "model": "training.trainingattempt", "icon": "bi bi-person-lines-fill"},
            {"name": "Настройки портала", "model": "training.portalsettings", "icon": "bi bi-sliders"},
            {"name": "Видео", "model": "training.trainingvideo", "icon": "bi bi-camera-video"},
            {"name": "Полезные ссылки", "model": "training.traininglink", "icon": "bi bi-link-45deg"},
        ],

        "аналитика": [
            {"name": "Обзор аналитики", "url": "admin:academy_analytics", "icon": "bi bi-graph-up-arrow"},
            {"name": "Посещаемость", "model": "academy.attendance", "icon": "bi bi-clipboard-check"},
            {"name": "Домашние задания", "model": "academy.homework", "icon": "bi bi-journal-text"},
            {"name": "Результаты домашних заданий", "model": "academy.homeworkresult", "icon": "bi bi-check2-square"},
            {"name": "Отчёты преподавателей", "model": "academy.monthlyteacherreport", "icon": "bi bi-file-earmark-text"},
            {
                "name": "Отчёт академии",
                "url": "admin:academy_report_monitor",
                "icon": "bi bi-building",
                # Sidebar-level gate on top of the real one (`_require_admin`
                # in academy_report_monitor_view/academy_report_detail_view)
                # — a superuser/Admin always passes `has_perm` regardless of
                # explicit grants, so this only ever hides the entry for a
                # non-admin staff account, never the backend check itself.
                "permissions": ["academy.view_academymonthlyreport"],
            },
            {
                # Scholarship period report — analytics, not scholarship
                # management, so it lives here rather than under "стипендии".
                "name": "Отчёты по стипендиям",
                "url": "admin:scholarships_report",
                "icon": "bi bi-file-earmark-bar-graph",
                "permissions": ["scholarships.view_scholarshipperiod"],
            },
        ],

        # The period is the one container: student evaluations, trainer
        # feedback and the run log are reached from inside a period
        # (its dashboard tabs), not as separate sidebar sections.
        "стипендии": [
            {"name": "Стипендиальные периоды", "model": "scholarships.scholarshipperiod", "icon": "bi bi-trophy"},
            {"name": "Стипендии", "model": "scholarships.scholarshipaward", "icon": "bi bi-award"},
        ],

        "коммуникация": [
            {"name": "Опросы", "model": "feedback.survey", "icon": "bi bi-ui-checks"},
            {"name": "Аналитика отзывов", "url": "admin:feedback_analytics", "icon": "bi bi-bar-chart-line"},
            {"name": "Новости", "model": "news.news", "icon": "bi bi-megaphone"},
        ],

        "ресурсы": [
            {"name": "Аудитории", "model": "academy.room", "icon": "bi bi-door-open"},
        ],

        "система": [
            {
                # A "url" link (not "model") so the short label is used —
                # Jazzmin labels model links with their verbose_name.
                "name": "Настройки",
                "url": "admin:scholarships_scholarshipconfiguration_changelist",
                "icon": "bi bi-sliders",
                "permissions": ["scholarships.view_scholarshipconfiguration"],
            },
            {"name": "Центр помощи", "url": "admin:academy_help", "icon": "bi bi-question-circle"},
        ],
    },

    # Section keys above are kept lowercase (Jazzmin lower-cases lookups);
    # the sidebar re-uppercases them via CSS (.ok-nav-section__label).
    "icons": {
        # A section key listed here gets an icon next to its sidebar
        # heading (templates/admin/base_site.html); others stay text-only.
        "отчёты": "bi bi-bar-chart-line",
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
        "academy.monthlyteacherreport": "bi bi-file-earmark-text",
        "data_io.exporttemplate": "bi bi-file-earmark-ruled",
        "news.news": "bi bi-megaphone",
        "feedback.survey": "bi bi-ui-checks",
        "scholarships.scholarshipperiod": "bi bi-trophy",
        "scholarships.scholarshipevaluation": "bi bi-person-lines-fill",
        "scholarships.scholarshipaward": "bi bi-award",
        "scholarships.trainerfeedback": "bi bi-chat-square-text",
        "scholarships.scholarshipconfiguration": "bi bi-sliders",
        "scholarships.scholarshiprunlog": "bi bi-journal-text",
        "testing.test": "bi bi-clipboard2-check",
        "testing.testsession": "bi bi-broadcast",
        "testing.testresult": "bi bi-clipboard-data",
        "training.portalsettings": "bi bi-sliders",
        "training.trainer": "bi bi-controller",
        "training.trainingattempt": "bi bi-person-lines-fill",
        "training.trainingvideo": "bi bi-camera-video",
        "training.traininglink": "bi bi-link-45deg",
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


# ---------------------------------------------------------------------------
# Public schedule site (schedule.okurmenkids.com) — what it may publish.
# ---------------------------------------------------------------------------
PUBLIC_SCHEDULE_SHOW_TRAINERS = env.bool("PUBLIC_SCHEDULE_SHOW_TRAINERS", default=True)
PUBLIC_SCHEDULE_SHOW_ROOMS = env.bool("PUBLIC_SCHEDULE_SHOW_ROOMS", default=True)
PUBLIC_SCHEDULE_PAST_DAYS = env.int("PUBLIC_SCHEDULE_PAST_DAYS", default=31)
PUBLIC_SCHEDULE_FUTURE_DAYS = env.int("PUBLIC_SCHEDULE_FUTURE_DAYS", default=120)
PUBLIC_SCHEDULE_CACHE_SECONDS = env.int("PUBLIC_SCHEDULE_CACHE_SECONDS", default=60)
