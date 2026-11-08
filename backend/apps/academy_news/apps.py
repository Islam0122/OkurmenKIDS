from django.apps import AppConfig


class AcademyNewsConfig(AppConfig):
    """Public academy news (OkurmenKids Digital, /news): articles with a cover
    and a photo gallery, written in the Django admin, read by everyone. Not
    to be confused with apps.news — internal notices for trainers."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.academy_news"
    verbose_name = "Новости академии (публичный сайт)"

    def ready(self):
        from . import signals  # noqa: F401 — public cache invalidation
