from django.apps import AppConfig


class WebsiteConfig(AppConfig):
    """Public website CMS (okurmen-public-website/): courses pages, events,
    achievements, team, testimonials, homepage blocks, media library and
    enrollment leads. Content is edited by marketing in the LMS cabinet
    (/api/v1/marketing/site/) and by admins in Django admin; visitors read it
    through /api/v1/public/site/ (published only, no login)."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.website"
    verbose_name = "Публичный сайт"

    def ready(self):
        from . import signals  # noqa: F401 — public cache invalidation
