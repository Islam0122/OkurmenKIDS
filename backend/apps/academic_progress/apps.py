from django.apps import AppConfig


class AcademicProgressConfig(AppConfig):
    """Monthly Academic Progress: a program's lessons split into study months
    («учебные блоки») with their own subject and lesson count; a group's
    current month and progress are computed from its completed lessons."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.academic_progress"
    verbose_name = "Учебные месяцы программ"
