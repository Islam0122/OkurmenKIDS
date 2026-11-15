from django.apps import AppConfig


class CommunityConfig(AppConfig):
    """«Сообщество» — the private student community of the Student Portal:
    posts (pre-moderated), comments, likes, reports, moderation and the
    hand-off of approved reviews to the website's testimonials CMS."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.community"
    verbose_name = "Сообщество учеников"
