"""Community photos: private storage, no metadata, short-lived signed links.

* Stored under MEDIA_ROOT/private/community — a folder config/urls.py never
  serves — so a photo of a child has no public address.
* Only re-encoded WebP copies are kept (EXIF, camera GPS etc. are dropped by
  re-encoding; the uploaded original is never written).
* Pages get `signed_url()` links valid for a few hours; the media view checks
  the signature and that the post is still visible to the community or to
  staff — anonymous, unsigned or expired requests get 404.
"""
from __future__ import annotations

import os
import uuid

from django.core import signing
from django.core.files.storage import FileSystemStorage
from django.utils import timezone
from django.utils.deconstruct import deconstructible

from apps.academy_news.images import make_variants, validate_image
from apps.recruitment.storage import private_root

SIGNING_SALT = "community.media"
LINK_MAX_AGE = 6 * 60 * 60
MAX_IMAGE_MB = 10


@deconstructible
class CommunityStorage(FileSystemStorage):
    def __init__(self, **kwargs):
        kwargs.setdefault("location", os.path.join(private_root(), "community"))
        super().__init__(**kwargs)

    def url(self, name):
        raise ValueError("Фото сообщества не имеют публичной ссылки — только media.signed_url().")


def community_storage() -> CommunityStorage:
    return CommunityStorage()


def image_path(instance, filename: str) -> str:
    return f"{timezone.now():%Y/%m}/{uuid.uuid4().hex}.webp"


def prepare(upload) -> tuple[int, int, dict]:
    """Validate an upload and return (width, height, {"large", "thumb"} WebP files)."""
    from django.core.exceptions import ValidationError

    if (getattr(upload, "size", 0) or 0) > MAX_IMAGE_MB * 1024 * 1024:
        raise ValidationError(f"Фото больше {MAX_IMAGE_MB} МБ.")
    validate_image(upload)
    return make_variants(upload)


def signed_url(image, variant: str) -> str:
    token = signing.dumps({"i": image.pk, "v": variant}, salt=SIGNING_SALT, compress=True)
    return f"/api/v1/community/media/{token}/"


def read_token(token: str) -> tuple[int, str] | None:
    try:
        data = signing.loads(token, salt=SIGNING_SALT, max_age=LINK_MAX_AGE)
    except signing.BadSignature:
        return None
    if data.get("v") not in ("large", "thumb"):
        return None
    return int(data["i"]), data["v"]
