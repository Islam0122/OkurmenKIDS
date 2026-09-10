from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig

class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.users"
    # The "users" app group itself is hidden from the sidebar (its models
    # are exposed through custom groups instead — see JAZZMIN_SETTINGS),
    # but Django admin still renders this as breadcrumb text on every
    # Teacher/Subject/User page, so it needs a real Russian name rather
    # than the auto-capitalised "Users".
    verbose_name = "Пользователи"

    def ready(self) -> None:
        import apps.users.signals

class OkurmenKidsAdminConfig(AdminConfig):
    default_site = "apps.users.admin_site.OkurmenKidsAdminSite"
