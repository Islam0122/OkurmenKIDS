"""Закрытое хранилище резюме кандидатов.

Файлы лежат в `RECRUITMENT_PRIVATE_ROOT` (по умолчанию `MEDIA_ROOT/private`,
то есть на том же постоянном томе, что и остальные загрузки). Публичной ссылки
у них нет: `config/urls.py` не отдаёт `/media/private/…`, а `url()` здесь
запрещён. Скачать резюме можно только через HR API
(`/api/v1/hr/applications/{id}/resume/`), где проверяются права.
"""
from __future__ import annotations

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible

# Каталог внутри MEDIA_ROOT, который config/urls.py никогда не отдаёт.
PRIVATE_MEDIA_DIR = "private"


def private_root() -> str:
    return settings.RECRUITMENT_PRIVATE_ROOT or os.path.join(str(settings.MEDIA_ROOT), PRIVATE_MEDIA_DIR)


@deconstructible
class PrivateStorage(FileSystemStorage):
    def __init__(self, **kwargs):
        kwargs.setdefault("location", private_root())
        super().__init__(**kwargs)

    def url(self, name):
        raise ValueError("У закрытых файлов нет публичной ссылки — только скачивание через HR API.")


def private_storage() -> PrivateStorage:
    return PrivateStorage()
