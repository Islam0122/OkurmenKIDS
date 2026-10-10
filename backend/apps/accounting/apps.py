from django.apps import AppConfig


class AccountingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounting"
    verbose_name = "Бухгалтерия и зарплаты"

    def ready(self) -> None:
        from . import signals  # noqa: F401
