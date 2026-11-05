"""Вход на сайт «Общая статистика» по ключу доступа (заголовок X-Dashboard-Key).

Подключён только к представлениям apps.performance (только чтение), поэтому
ключ не открывает ни один другой эндпоинт LMS. Пользователь при входе по
ключу — анонимный: `request.auth` — запись DashboardAccessKey.
"""
from __future__ import annotations

from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .services.access_keys import resolve_key

HEADER = "HTTP_X_DASHBOARD_KEY"


class DashboardKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        raw = request.META.get(HEADER, "").strip()
        if not raw:
            return None  # дальше — обычный вход сотрудника (JWT)
        key = resolve_key(raw)
        if key is None:
            raise AuthenticationFailed("Ключ доступа недействителен или отключён.", code="invalid_dashboard_key")
        return AnonymousUser(), key

    def authenticate_header(self, request):
        return "Dashboard-Key"
