from django.apps import AppConfig


class PortalConfig(AppConfig):
    """Student & Parent Portal: the STUDENT_PARENT accounts, their links to
    students, and the read-mostly API those accounts use (/api/v1/portal/).
    Every figure it shows comes from the existing academy / testing /
    billing records — nothing is computed or stored a second time here."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.portal"
    verbose_name = "Кабинет ученика и родителя"
