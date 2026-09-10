from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig

class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"

    def ready(self) -> None:
        import apps.users.signals

class OkurmenKidsAdminConfig(AdminConfig):
    default_site = "apps.users.admin_site.OkurmenKidsAdminSite"
