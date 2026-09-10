from django.apps import AppConfig


class AcademyConfig(AppConfig):
    name = 'apps.academy'

    def ready(self) -> None:
        import apps.academy.signals  # noqa: F401
