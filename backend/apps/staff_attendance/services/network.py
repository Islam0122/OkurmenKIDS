"""Необязательная проверка «отметка сделана из офисной сети».

Работает, только если сервер видит настоящий IP клиента: за прокси (Railway,
балансировщик) это первый адрес X-Forwarded-For, и доверять ему можно лишь
когда прокси его перезаписывает — поэтому заголовок учитывается только при
ATTENDANCE_TRUST_X_FORWARDED_FOR=True.
"""
from __future__ import annotations

import ipaddress

from django.conf import settings
from django.core.exceptions import ValidationError


def parse_networks(text: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks = []
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        try:
            networks.append(ipaddress.ip_network(line, strict=False))
        except ValueError as exc:
            raise ValidationError({"office_networks": f"Неверная сеть: {line}"}) from exc
    return networks


def client_ip(request) -> str | None:
    if getattr(settings, "ATTENDANCE_TRUST_X_FORWARDED_FOR", False):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def ip_in_networks(ip: str | None, text: str) -> bool:
    if not ip:
        return False
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in network for network in parse_networks(text))
