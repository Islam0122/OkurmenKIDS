"""Fast-loading copies of uploaded photos.

Every cover and gallery photo keeps its original file and gets two WebP
copies: «large» (up to 1600 px, for the article and the lightbox) and
«thumb» (up to 640 px, for cards and the gallery grid). The original size is
stored too, so pages reserve the right space before an image arrives.
"""
from __future__ import annotations

import io
import os
import uuid

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageOps

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_PIXELS = 60_000_000
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
SIZES = {"large": 1600, "thumb": 640}
WEBP_QUALITY = 80


def upload_path(instance, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()[:10]
    return f"news/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{ext}"


def validate_image(field_file) -> None:
    """Only real JPEG / PNG / WebP pictures of a sane size."""
    if field_file is None:
        return
    size = getattr(field_file, "size", 0) or 0
    if size > MAX_UPLOAD_BYTES:
        raise ValidationError(f"Файл больше {MAX_UPLOAD_BYTES // (1024 * 1024)} МБ.")
    try:
        field_file.seek(0)
        with Image.open(field_file) as probe:
            fmt = probe.format
            width, height = probe.size
            probe.verify()
    except Exception:
        raise ValidationError("Это не изображение или файл повреждён.")
    finally:
        try:
            field_file.seek(0)
        except Exception:
            pass
    if fmt not in ALLOWED_FORMATS:
        raise ValidationError("Допустимы JPEG, PNG и WebP.")
    if width * height > MAX_PIXELS:
        raise ValidationError("Слишком большое изображение (больше 60 Мп).")


def make_variants(field_file) -> tuple[int, int, dict[str, ContentFile]]:
    """(width, height, {"large": file, "thumb": file}) for an uploaded image,
    rotated by its EXIF orientation, metadata dropped."""
    field_file.open("rb")
    field_file.seek(0)
    with Image.open(field_file) as source:
        image = ImageOps.exif_transpose(source)
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
        width, height = image.size
        variants = {}
        for name, limit in SIZES.items():
            copy = image.copy()
            copy.thumbnail((limit, limit), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            copy.save(buffer, "WEBP", quality=WEBP_QUALITY, method=4)
            variants[name] = ContentFile(buffer.getvalue(), name=f"{uuid.uuid4().hex}.webp")
    return width, height, variants
