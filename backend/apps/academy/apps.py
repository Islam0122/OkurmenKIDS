from django.apps import AppConfig


class AcademyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.academy"
    verbose_name = "Академия"

    def ready(self) -> None:
        import apps.academy.signals  # noqa: F401