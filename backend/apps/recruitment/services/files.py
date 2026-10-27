"""Резюме кандидатов: проверка формата, размера и содержимого.

Принимаются только PDF и DOCX не больше `RECRUITMENT_RESUME_MAX_MB`. Формат
проверяется не по расширению и не по заявленному Content-Type, а по
содержимому: PDF начинается с `%PDF-`, DOCX — ZIP-архив с `word/document.xml`.
Файл сохраняется в закрытое хранилище под случайным именем
(`models.resume_path`), исходное имя — только для скачивания.
"""
from __future__ import annotations

import os
import zipfile

from django.conf import settings

from .common import RecruitmentError

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def max_bytes() -> int:
    return settings.RECRUITMENT_RESUME_MAX_MB * 1024 * 1024


def _is_docx(upload) -> bool:
    try:
        with zipfile.ZipFile(upload) as archive:
            names = set(archive.namelist())
    except (zipfile.BadZipFile, OSError, ValueError):
        return False
    return "word/document.xml" in names and "[Content_Types].xml" in names


def validate_resume(upload) -> str:
    """Проверить загруженный файл; вернуть расширение (`pdf` / `docx`)."""
    name = os.path.basename(upload.name or "")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in CONTENT_TYPES:
        raise RecruitmentError("Резюме — только в формате PDF или DOCX.", "resume_format")
    if upload.size == 0:
        raise RecruitmentError("Файл резюме пустой.", "resume_empty")
    if upload.size > max_bytes():
        raise RecruitmentError(f"Резюме больше {settings.RECRUITMENT_RESUME_MAX_MB} МБ.", "resume_too_large")
    upload.seek(0)
    if ext == "pdf":
        valid = upload.read(5) == b"%PDF-"
    else:
        valid = _is_docx(upload)
    upload.seek(0)
    if not valid:
        raise RecruitmentError("Файл повреждён или не соответствует формату PDF/DOCX.", "resume_content")
    return ext


def safe_display_name(name: str, ext: str) -> str:
    """Исходное имя без пути и управляющих символов (для Content-Disposition)."""
    base = os.path.basename(name or "").replace("\x00", "")
    base = "".join(ch for ch in base if ch.isprintable() and ch not in '"\\/')[:200].strip()
    if not base.lower().endswith(f".{ext}"):
        base = f"{base or 'resume'}.{ext}"
    return base


def attach_resume(application, upload) -> None:
    """Сохранить резюме отклика; прежний файл удаляется."""
    ext = validate_resume(upload)
    old = application.resume.name if application.resume else ""
    application.resume.save(f"resume.{ext}", upload, save=False)
    application.resume_name = safe_display_name(upload.name, ext)
    application.resume_size = upload.size
    application.save(update_fields=["resume", "resume_name", "resume_size", "updated_at"])
    if old:
        application.resume.storage.delete(old)
