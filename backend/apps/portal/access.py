"""Server-side isolation of Student & Parent Portal accounts.

`PortalIsolationMiddleware` lets a STUDENT_PARENT account reach only:

* sign-in (login / refresh / me),
* the portal API (/api/v1/portal/),
* public, anonymous pages of the platform (they answer anyone anyway).

Every other API URL and the Django admin answer 403 — however the request
got there (a crafted URL, an id from somewhere, a new staff endpoint added
later without thinking of this role). It does not depend on the
`permission_classes` of individual LMS views, so a staff endpoint that only
checks `IsAuthenticated` stays closed to portal accounts automatically.

While the account still has its temporary password, only the password
change itself (and `me/`) is open inside the portal API: the first-login
change cannot be skipped by calling the data endpoints directly.

Which *students* an account may read is decided in services.scope.
"""
from __future__ import annotations

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse

from apps.accounting.access import _request_user

PORTAL_API_PREFIX = "/api/v1/portal/"

ALLOWED_PREFIXES = (
    "/api/v1/auth/login/",
    "/api/v1/auth/refresh/",
    "/api/v1/auth/me/",
    PORTAL_API_PREFIX,
    # Anonymous public sites (leaderboard, schedule, projects, news, careers…).
    "/api/v1/public/",
)
# Open while the first-login password change is still pending.
PASSWORD_PENDING_PREFIXES = (
    "/api/v1/auth/",
    f"{PORTAL_API_PREFIX}me/",
    f"{PORTAL_API_PREFIX}password/",
)
# Non-API pages a signed-in browser session may still open.
_GUARDED_PREFIXES = ("/api/", "/admin/", "/schema/", "/swagger-ui/", "/redoc/")


def is_portal_user(user) -> bool:
    from apps.users.models import User

    return bool(user is not None and getattr(user, "is_authenticated", False)
                and getattr(user, "role", None) in User.PORTAL_ROLES)


def password_change_pending(user) -> bool:
    account = getattr(user, "portal_account", None)
    return bool(account is None or account.must_change_password)


def _deny(path: str, message: str, code: str):
    if path.startswith("/api/"):
        return JsonResponse({"detail": message, "code": code}, status=403)
    return HttpResponseForbidden(message)


class PortalIsolationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        static = "/" + settings.STATIC_URL.lstrip("/")
        if path.startswith(static) or not path.startswith(_GUARDED_PREFIXES):
            return self.get_response(request)
        # Only a request that carries credentials can be a portal account.
        if not request.headers.get("Authorization") and not request.COOKIES.get(settings.SESSION_COOKIE_NAME):
            return self.get_response(request)
        user = _request_user(request)
        if not is_portal_user(user):
            return self.get_response(request)
        if not path.startswith(ALLOWED_PREFIXES):
            return _deny(path, "Раздел недоступен: кабинет ученика и родителя работает только в /student/.",
                         "portal_only")
        if path.startswith(PORTAL_API_PREFIX) and not path.startswith(PASSWORD_PENDING_PREFIXES) \
                and password_change_pending(user):
            return _deny(path, "Сначала смените временный пароль.", "password_change_required")
        return self.get_response(request)
