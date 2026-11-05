"""Private storage of generated report images.

The PNGs show children's names, attendance and grades, so they never get a
public URL: they live under ``MEDIA_ROOT/private/parent_reports`` (the
``private`` directory is never served by config/urls.py) and are downloaded
only through ``/api/v1/parent-reports/{id}/download/``, which checks access.
"""
from __future__ import annotations

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible

from apps.recruitment.storage import PRIVATE_MEDIA_DIR


def reports_root() -> str:
    return getattr(settings, "PARENT_REPORTS_ROOT", None) or os.path.join(
        str(settings.MEDIA_ROOT), PRIVATE_MEDIA_DIR, "parent_reports"
    )


@deconstructible
class ReportImageStorage(FileSystemStorage):
    def __init__(self, **kwargs):
        kwargs.setdefault("location", reports_root())
        super().__init__(**kwargs)

    def url(self, name):
        raise ValueError("У изображений отчётов нет публичной ссылки — только скачивание через API.")


def report_image_storage() -> ReportImageStorage:
    return ReportImageStorage()
