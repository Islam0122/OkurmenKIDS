"""CSRF failure handler (settings.CSRF_FAILURE_VIEW).

Rejection itself stays entirely with Django's CsrfViewMiddleware — this
view only runs *after* a request was already refused, and does two things:

1. Logs one WARNING line of request metadata so a 403 in production can be
   diagnosed from the Railway logs (method, redacted path, Origin, Referer
   origin, User-Agent, whether a CSRF cookie was present, Django's reason).
   It never logs cookie values, the CSRF token, session/auth headers, form
   data, full Referer URLs, or the secret token of a public survey link.
2. Shows parents/students on a public feedback link a friendly page instead
   of Django's technical 403. Every other path keeps Django's default page.
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.shortcuts import render
from django.views.csrf import csrf_failure as django_csrf_failure

logger = logging.getLogger("okurmenkids.security.csrf")

_SURVEY_TOKEN = re.compile(r"^(/feedback/s/)[^/]+")


def _redacted_path(path: str) -> str:
    return _SURVEY_TOKEN.sub(r"\1<token>", path)


def _origin_of(url: str) -> str:
    """Scheme + host only — a full Referer can carry tokens or query data."""
    if not url:
        return "-"
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else "<unparseable>"


def csrf_failure(request, reason=""):
    path = _redacted_path(request.path)
    logger.warning(
        "CSRF rejected: method=%s path=%s origin=%s referer_origin=%s host=%s secure=%s "
        "csrf_cookie=%s reason=%r user_agent=%r",
        request.method,
        path,
        request.META.get("HTTP_ORIGIN", "-"),
        _origin_of(request.META.get("HTTP_REFERER", "")),
        # Raw header, not get_host(): the handler must never raise itself.
        request.META.get("HTTP_HOST", "-")[:200],
        request.is_secure(),
        settings.CSRF_COOKIE_NAME in request.COOKIES,
        reason,
        request.META.get("HTTP_USER_AGENT", "-")[:200],
    )

    if path.startswith("/feedback/s/"):
        return render(
            request,
            "feedback/public_message.html",
            {
                "survey": None,
                "title": "Не удалось отправить ответ",
                "message": "Страница устарела или открыта необычным способом. "
                "Откройте ссылку на опрос заново и отправьте ответ ещё раз.",
                "icon": "lock",
            },
            status=403,
        )
    return django_csrf_failure(request, reason=reason)
