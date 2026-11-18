import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="bulk_copy.run")
def run_bulk_copy(operation_pk: int) -> str:
    """Large copies run here; the result (or the error) is stored on the operation."""
    from .models import BulkCopyOperation
    from .services import engine

    op = BulkCopyOperation.objects.filter(pk=operation_pk).first()
    if op is None:
        return "missing"
    try:
        return engine.execute(op).status
    except engine.CopyError as exc:
        logger.info("bulk copy %s refused: %s", op.operation_id, exc.message)
        return "failed"
