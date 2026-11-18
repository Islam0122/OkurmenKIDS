from django.apps import AppConfig


class BulkCopyConfig(AppConfig):
    """Bulk copy of a group's lesson records (attendance, homework results,
    homework scores) from one group / subject / period to another — with an
    explicit lesson mapping, a dry-run preview, an audit log and safe undo.
    Writes only the existing academy models; see services/engine.py."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bulk_copy"
    verbose_name = "Массовое копирование данных"
