"""Preview → import.

``preview(upload, user, ...)`` reads and validates the file and stores the
validated rows in an ImportBatch (status «Проверка»). ``commit(batch, ...)``
imports the rows the admin selected — from the stored server-side rows,
re-validated against the current database, one transaction per record — and
can be called several times with chunks of rows (progress in the UI); the
last call passes ``finalize``.

Imported records are always unpublished (draft, or the source review /
archived status for site content). An existing record is skipped unless the
admin explicitly confirmed updating it; a published record is never updated.
"""
from __future__ import annotations

import datetime as dt

from django.db import transaction
from django.utils import timezone

from apps.academy_news.models import Article

from ..models import ImportBatch
from .reader import read_upload
from .schema import TYPES
from .validate import MODELS, RowValidator, find_duplicate

TEXT_FIELDS = {
    "events": ["title", "title_ky", "title_en", "excerpt", "excerpt_ky", "excerpt_en", "body", "body_ky", "body_en",
               "category", "starts_at", "ends_at", "location", "branch_id", "registration_enabled",
               "registration_limit"],
    "achievements": ["title", "title_ky", "title_en", "excerpt", "excerpt_ky", "excerpt_en", "body", "body_ky",
                     "body_en", "category", "date", "recipient"],
    "news": ["title", "excerpt", "body", "category", "published_at"],
}


class ImportRejected(Exception):
    pass


def preview(uploaded, user, *, csv_kind: str | None = None, kinds: list[str] | None = None) -> ImportBatch:
    sheets = read_upload(uploaded, csv_kind=csv_kind)
    if kinds:
        sheets = {k: v for k, v in sheets.items() if k in kinds}
        if not sheets:
            raise ImportRejected("В файле нет выбранных листов.")
    validator = RowValidator()
    rows = []
    for kind in TYPES:
        if kind not in sheets:
            continue
        _, data = sheets[kind]
        rows.extend(validator.validate(kind, number, raw) for number, raw in data)
    present = [k for k in TYPES if k in sheets]
    return ImportBatch.objects.create(
        file_name=(getattr(uploaded, "name", "") or "file")[:255],
        file_size=getattr(uploaded, "size", 0) or 0,
        created_by=user,
        content_type=present[0] if len(present) == 1 else ImportBatch.ContentType.MIXED,
        total_rows=len(rows),
        rows=rows,
        report={"sheets": {k: len(sheets[k][1]) for k in present}, "rows": {}},
    )


def _python_values(kind: str, values: dict) -> dict:
    out = {f: values[f] for f in TEXT_FIELDS[kind] if f in values}
    for f in ("starts_at", "ends_at", "published_at"):
        if out.get(f):
            out[f] = dt.datetime.fromisoformat(out[f])
    if out.get("date"):
        out["date"] = dt.date.fromisoformat(out["date"])
    return out


def _import_row(row: dict, user, allow_update: bool) -> dict:
    kind = row["kind"]
    model = MODELS[kind]
    values = row["values"]
    duplicate = find_duplicate(kind, values)  # the database may have changed since the preview
    fields = _python_values(kind, values)
    if duplicate:
        if not allow_update:
            return {"result": "skipped", "message": "Уже существует — пропущено.", "object_id": duplicate["id"]}
        if not duplicate["updatable"]:
            return {"result": "skipped", "object_id": duplicate["id"],
                    "message": "Запись уже опубликована — импорт не меняет опубликованный контент, правьте в редакторе."}
        with transaction.atomic():
            obj = model.objects.select_for_update().get(pk=duplicate["id"])
            if obj.status == "published":
                return {"result": "skipped", "object_id": obj.pk, "message": "Запись опубликована — не обновлена."}
            for name, value in fields.items():
                setattr(obj, name, value)
            if kind == "events" and "ends_at" not in fields:
                obj.ends_at = None
            obj.full_clean(exclude=["cover", "slug"])
            obj.save()
        return {"result": "updated", "message": "Обновлено (статус записи не изменён).", "object_id": obj.pk}

    with transaction.atomic():
        obj = model(**fields)
        if values.get("slug") and not model.objects.filter(slug=values["slug"]).exists():
            obj.slug = values["slug"]
        if kind == "news":
            obj.status = Article.Status.DRAFT
            obj.author = user
            if not fields.get("published_at"):
                obj.published_at = timezone.now()
        else:
            obj.status = values["status"] if values["status"] in ("draft", "review", "archived") else "draft"
            obj.created_by = user
        obj.full_clean(exclude=["cover", "slug"])
        obj.save()
    return {"result": "created", "message": "Создано как черновик." if obj.status == "draft"
            else f"Создано, статус «{obj.get_status_display()}».", "object_id": obj.pk}


def commit(batch: ImportBatch, user, *, keys: list[str], update_keys: list[str], finalize: bool) -> ImportBatch:
    """Import the given rows of a previewed batch (idempotent per row)."""
    from django.core.exceptions import ValidationError

    by_key = {r["key"]: r for r in batch.rows}
    unknown = [k for k in keys if k not in by_key]
    if unknown:
        raise ImportRejected(f"Неизвестные строки: {', '.join(unknown[:5])}.")
    with transaction.atomic():
        batch = ImportBatch.objects.select_for_update().get(pk=batch.pk)
        if batch.status == ImportBatch.Status.CANCELLED:
            raise ImportRejected("Импорт этого файла отменён. Загрузите его заново.")
        if batch.status not in (ImportBatch.Status.PREVIEW, ImportBatch.Status.IMPORTING):
            raise ImportRejected("Этот файл уже импортирован. Загрузите его заново.")
        if batch.status == ImportBatch.Status.PREVIEW:
            batch.status = ImportBatch.Status.IMPORTING
            batch.save(update_fields=["status"])
    updates = set(update_keys)
    results = dict(batch.report.get("rows", {}))
    validator = RowValidator()
    for key in keys:
        if key in results:
            continue  # already processed in an earlier chunk
        row = by_key[key]
        if not row["valid"]:
            result = {"result": "failed", "message": "; ".join(e["message"] for e in row["errors"])}
        else:
            # Relations are checked again: a branch may have been deleted since the preview.
            if row["values"].get("branch_id") and row["values"]["branch_id"] not in validator.branches.values():
                result = {"result": "failed", "message": "Филиал удалён после проверки файла."}
            else:
                try:
                    result = _import_row(row, user, key in updates)
                except ValidationError as exc:
                    result = {"result": "failed", "message": "; ".join(exc.messages)}
                except Exception as exc:  # noqa: BLE001 — one bad row must not stop the others
                    result = {"result": "failed", "message": f"Ошибка сохранения: {exc.__class__.__name__}."}
        result.update(kind=row["kind"], row=row["row"], title=row["title"],
                      verification_note=row.get("verification_note", ""), cover=row.get("cover", ""))
        if row.get("translations"):
            result["translations"] = row["translations"]
        results[key] = result

    with transaction.atomic():
        batch = ImportBatch.objects.select_for_update().get(pk=batch.pk)
        batch.report = {**batch.report, "rows": results}
        counts = {"created": 0, "updated": 0, "skipped": 0, "failed": 0}
        for r in results.values():
            counts[r["result"]] += 1
        batch.created_count, batch.updated_count = counts["created"], counts["updated"]
        batch.skipped_count, batch.failed_count = counts["skipped"], counts["failed"]
        batch.selected_rows = len(results)
        if finalize:
            batch.finished_at = timezone.now()
            if counts["failed"] and not (counts["created"] or counts["updated"]):
                batch.status = ImportBatch.Status.FAILED
            elif counts["failed"]:
                batch.status = ImportBatch.Status.PARTIAL
            else:
                batch.status = ImportBatch.Status.COMPLETED
        batch.save()
    return batch
