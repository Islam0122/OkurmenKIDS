from django.apps import AppConfig


class AssistantConfig(AppConfig):
    """Assistant Workspace API. No models of its own — it works on the
    existing academy / scholarships data through their services."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.assistant"
    verbose_name = "Assistant Workspace"
