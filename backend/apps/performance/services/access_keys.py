"""Ключи доступа к сайту «Общая статистика» (см. models.DashboardAccessKey)."""
from __future__ import annotations

import datetime as dt
import hashlib
import secrets

from django.db.models import Q
from django.utils import timezone

from ..models import DashboardAccessKey

KEY_PREFIX = "okd_"
TOUCH_EVERY = dt.timedelta(minutes=10)  # не писать в базу на каждый запрос телевизора


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_key(name: str, *, created_by=None, expires_at=None) -> tuple[DashboardAccessKey, str]:
    """Создать ключ; возвращает (запись, ключ). Ключ больше нигде не хранится."""
    raw = KEY_PREFIX + secrets.token_urlsafe(32)
    key = DashboardAccessKey.objects.create(
        name=name, key_hash=hash_key(raw), prefix=raw[len(KEY_PREFIX):len(KEY_PREFIX) + 6],
        created_by=created_by, expires_at=expires_at,
    )
    return key, raw


def resolve_key(raw: str) -> DashboardAccessKey | None:
    """Активный и не истёкший ключ — или None."""
    if not raw or len(raw) > 200:
        return None
    now = timezone.now()
    key = (DashboardAccessKey.objects.filter(key_hash=hash_key(raw), is_active=True)
           .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)).first())
    if key and (key.last_used_at is None or now - key.last_used_at > TOUCH_EVERY):
        DashboardAccessKey.objects.filter(pk=key.pk).update(last_used_at=now)
    return key
