"""Fast-loading WebP copies of student-project images.

Projects keep their original upload (often a full-page PNG screenshot of
several megabytes). Cards and the gallery should never download that, so
every image gets the same two WebP copies the news and website use
(`academy_news.images.make_variants`): «large» (≤ 1600 px) and «thumb»
(≤ 640 px).

No database columns are involved: the copies live next to the original under
a deterministic name (`<original>.thumb.webp`, `<original>.large.webp`), are
made when an image is saved, removed when it is deleted, and — for uploads
that predate this module — made on first public use (or in bulk with
`manage.py build_project_image_variants`).
"""
from __future__ import annotations

import logging

from django.core.files.base import ContentFile
from PIL import Image

from apps.academy_news.images import make_variants

logger = logging.getLogger(__name__)

KINDS = ("large", "thumb")


def variant_name(original_name: str, kind: str) -> str:
    return f"{original_name}.{kind}.webp"


def _url(storage, name: str) -> str | None:
    try:
        return storage.url(name)
    except Exception:  # noqa: BLE001 — a URL problem must never break a public page
        return None


def build_variants(field) -> bool:
    """Write the WebP copies of an image field. True when they exist afterwards."""
    if not field or not field.name:
        return False
    storage = field.storage
    try:
        _, _, files = make_variants(field)
        for kind in KINDS:
            name = variant_name(field.name, kind)
            if storage.exists(name):
                storage.delete(name)
            saved = storage.save(name, ContentFile(files[kind].read()))
            if saved != name:  # the storage renamed it — never leave an unreachable copy
                storage.delete(saved)
                return False
        return True
    except Exception:  # noqa: BLE001 — a broken upload keeps working with its original file
        logger.warning("Could not build WebP copies of %s", field.name, exc_info=True)
        return False
    finally:
        try:
            field.close()
        except Exception:  # noqa: BLE001
            pass


def drop_variants(field) -> None:
    if not field or not field.name:
        return
    for kind in KINDS:
        try:
            field.storage.delete(variant_name(field.name, kind))
        except Exception:  # noqa: BLE001
            pass


def has_variants(field) -> bool:
    return bool(field and field.name) and all(field.storage.exists(variant_name(field.name, k)) for k in KINDS)


def image_asset(field, *, build_missing: bool = True) -> dict | None:
    """The public image object `{url, thumb, width, height, caption}` (the same
    shape as the website's images), or None. Falls back to the original file
    when no WebP copy can be made."""
    if not field or not field.name:
        return None
    storage = field.storage
    original = _url(storage, field.name)
    if not original:
        return None
    if not has_variants(field) and build_missing:
        build_variants(field)
    width = height = None
    try:
        with storage.open(field.name, "rb") as handle, Image.open(handle) as probe:
            width, height = probe.size  # header only — the pixels are not decoded
    except Exception:  # noqa: BLE001
        pass
    if has_variants(field):
        return {
            "url": _url(storage, variant_name(field.name, "large")) or original,
            "thumb": _url(storage, variant_name(field.name, "thumb")) or original,
            "width": width,
            "height": height,
            "caption": "",
        }
    return {"url": original, "thumb": original, "width": width, "height": height, "caption": ""}
