"""Постоянный QR-код офиса: HTTPS-ссылка на страницу отметки LMS с публичным
кодом офиса. Никаких токенов, паролей и данных сотрудников."""
from __future__ import annotations

import io
from urllib.parse import urlencode

import segno
from django.conf import settings

from ..models import AttendanceLocation


def scan_url(location: AttendanceLocation) -> str:
    base = (getattr(settings, "ATTENDANCE_QR_BASE_URL", "") or settings.LMS_FRONTEND_URL).rstrip("/")
    return f"{base}/attendance/scan?{urlencode({'office': location.code})}"


def qr_svg(location: AttendanceLocation, scale: int = 10) -> str:
    buffer = io.BytesIO()
    segno.make(scan_url(location), error="m").save(buffer, kind="svg", scale=scale, border=2, xmldecl=False)
    return buffer.getvalue().decode()
