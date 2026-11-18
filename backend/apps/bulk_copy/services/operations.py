"""Starting a copy: idempotency, the audit record, inline or background run."""
from __future__ import annotations

import uuid

from django.conf import settings

from ..models import BulkCopyOperation
from . import engine

# Above this many writes the copy runs as a Celery task when a broker is
# configured (CELERY_TASK_ALWAYS_EAGER is on without one — then inline).
BACKGROUND_THRESHOLD = 1500


def start(req: engine.CopyRequest, *, user, fingerprint: str, operation_id: uuid.UUID,
          confirm_overwrite: bool) -> tuple[BulkCopyOperation, bool]:
    """Returns (operation, replayed). The operation is APPLIED when it ran
    inline, QUEUED when it went to the background worker."""
    existing = BulkCopyOperation.objects.filter(operation_id=operation_id).first()
    if existing is not None:
        if existing.created_by_id != user.pk:
            raise engine.CopyError("Этот идентификатор операции уже использован.", "conflict")
        return existing, True

    # The same dry run the preview showed — checked now, and again under locks at execution.
    current = engine.plan(req, user)
    if current.fingerprint() != fingerprint:
        raise engine.CopyError("Данные изменились после предпросмотра. Обновите предпросмотр и проверьте его ещё раз.",
                               "conflict")
    if current.count(engine.OVERWRITE) and not confirm_overwrite:
        raise engine.CopyError(f"Будет перезаписано записей: {current.count(engine.OVERWRITE)}. Подтвердите перезапись.",
                               "confirmation_required")
    if not current.writes:
        raise engine.CopyError("Нечего копировать: все записи пропущены или уже совпадают.")

    op = BulkCopyOperation.objects.create(
        operation_id=operation_id, created_by=user, fingerprint=fingerprint,
        request={**req.to_json(), "confirm_overwrite": confirm_overwrite},
        categories=sorted(req.categories),
        source_group=req.source_group, source_group_name=req.source_group.name,
        source_subject=req.source_subject, source_subject_name=req.source_subject.name,
        source_start=req.source_start, source_end=req.source_end,
        target_group=req.target_group, target_group_name=req.target_group.name,
        target_subject=req.target_subject, target_subject_name=req.target_subject.name,
        target_start=req.target_start, target_end=req.target_end,
    )
    background = len(current.writes) > BACKGROUND_THRESHOLD and not getattr(settings, "CELERY_TASK_ALWAYS_EAGER", True)
    if background:
        from ..tasks import run_bulk_copy

        run_bulk_copy.delay(op.pk)
        return op, False
    return engine.execute(op), False
