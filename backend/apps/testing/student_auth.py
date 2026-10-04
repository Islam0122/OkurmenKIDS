"""Student sign-in for the student portal (/student/).

Students have no LMS accounts — users.User and its JWT are for staff only,
and adding a student role there would touch every staff permission check.
The student side has always worked through the Django session (/exam/
remembers attempts per browser); the portal does the same: the student
enters the personal code an administrator issued (StudentPortalAccess) and
the session remembers who they are. Regenerating or disabling the code, or
the student leaving the academy, signs them out on the next request.
"""
from __future__ import annotations

from functools import wraps

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme, urlencode

from .models import StudentPortalAccess, normalize_portal_code

SESSION_STUDENT = "student_portal_student"
SESSION_CODE = "student_portal_code"

# Wrong codes allowed per client IP per hour — same approach as the session
# keys on /exam/ (a class signing in from one school IP is never affected by
# correct codes).
FAILED_CODES_PER_HOUR = 20


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else "") or request.META.get("REMOTE_ADDR", "")


def _failed_key(request) -> str:
    return f"testing:portal-login-fail:{_client_ip(request)}"


def too_many_failed_codes(request) -> bool:
    return (cache.get(_failed_key(request)) or 0) >= FAILED_CODES_PER_HOUR


def record_failed_code(request) -> None:
    key = _failed_key(request)
    if cache.add(key, 1, timeout=3600):
        return
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=3600)


def find_access(raw_code: str) -> StudentPortalAccess | None:
    code = normalize_portal_code(raw_code)
    if not code:
        return None
    return (
        StudentPortalAccess.objects.select_related("student")
        .filter(code=code, is_active=True, student__is_active=True)
        .first()
    )


def login(request, access: StudentPortalAccess) -> None:
    request.session.cycle_key()  # no session fixation
    request.session[SESSION_STUDENT] = access.student_id
    request.session[SESSION_CODE] = access.code
    access.last_login_at = timezone.now()
    access.save(update_fields=["last_login_at"])


def logout(request) -> None:
    request.session.pop(SESSION_STUDENT, None)
    request.session.pop(SESSION_CODE, None)
    request.session.cycle_key()


def current_student(request):
    """The signed-in student, or None. Re-checked on every request."""
    student_id = request.session.get(SESSION_STUDENT)
    code = request.session.get(SESSION_CODE)
    if not student_id or not code:
        return None
    access = (
        StudentPortalAccess.objects.select_related("student__group__course")
        .filter(student_id=student_id, code=code, is_active=True, student__is_active=True)
        .first()
    )
    if access is None:
        logout(request)
        return None
    return access.student


def safe_next(request, fallback: str) -> str:
    candidate = request.POST.get("next") or request.GET.get("next") or ""
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return fallback


def student_required(view):
    """Pages: redirect to the sign-in page. Sets ``request.student``."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        student = current_student(request)
        if student is None:
            return redirect(f"{reverse('student_portal_login')}?{urlencode({'next': request.get_full_path()})}")
        request.student = student
        return view(request, *args, **kwargs)

    return wrapper


def student_required_api(view):
    """JSON endpoints: 401 instead of a redirect."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        student = current_student(request)
        if student is None:
            return JsonResponse({"error": "Войдите в кабинет студента."}, status=401)
        request.student = student
        return view(request, *args, **kwargs)

    return wrapper
