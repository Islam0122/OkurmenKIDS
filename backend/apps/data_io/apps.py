from django.apps import AppConfig


class DataIoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.data_io"
    verbose_name = "Импорт и экспорт"

    def ready(self) -> None:
        # Populates the model-adapter registry (apps.data_io.registry) as a
        # side effect — mirrors Django admin's own autodiscovery pattern.
        # Must happen in ready(), not at import time, so the academy/users
        # apps (and their models) are fully loaded first.
        from .adapters import academy, users  # noqa: F401
