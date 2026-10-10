from django.conf import settings
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .access import ensure_accountant_group, sync_accountant_access


@receiver(post_migrate)
def create_accountant_group(sender, **kwargs):
    if getattr(sender, "label", None) == "accounting":
        ensure_accountant_group()


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def sync_accountant_group(sender, instance, raw=False, **kwargs):
    if not raw:
        sync_accountant_access(instance)
