from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    """Student projects: work students build on their own and present to their
    trainer; the trainer reviews it and registers it in the LMS (only a
    trainer creates a project — see access.py)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.projects"
    verbose_name = "Проекты студентов"

    def ready(self):
        from . import signals  # noqa: F401 — public gallery cache invalidation
