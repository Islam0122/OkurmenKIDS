"""«Тренировочный портал» in the Django admin: portal settings (texts and
the real exam link), useful videos and links. Tests themselves are made in
«Тесты» and published to the portal from a training session's settings
(«Публичная тренировка»)."""
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from apps.testing.admin import AdminRoleOnly

from .models import PortalSettings, TrainingLink, TrainingVideo


@admin.register(PortalSettings)
class PortalSettingsAdmin(AdminRoleOnly, admin.ModelAdmin):
    fieldsets = (
        ("Главная страница", {"fields": ("hero_title", "hero_subtitle", "start_button_label")}),
        ("Настоящий экзамен", {"fields": ("exam_button_label", "exam_url", "exam_open_in_new_tab")}),
    )

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not PortalSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        # One row: the list goes straight to its form.
        from django.shortcuts import redirect

        return redirect(reverse("admin:training_portalsettings_change", args=[PortalSettings.load().pk]))


class _OrderedContentAdmin(AdminRoleOnly, admin.ModelAdmin):
    list_display = ("title", "category", "order", "published", "updated_at")
    list_editable = ("order", "published")
    list_filter = ("published", "category")
    search_fields = ("title", "description", "category")
    actions = ["publish", "unpublish"]

    @admin.action(description="Опубликовать")
    def publish(self, request, queryset):
        queryset.update(published=True)

    @admin.action(description="Снять с публикации")
    def unpublish(self, request, queryset):
        queryset.update(published=False)


@admin.register(TrainingVideo)
class TrainingVideoAdmin(_OrderedContentAdmin):
    list_display = ("title", "category", "duration", "link", "order", "published", "updated_at")
    fields = ("title", "description", "video_url", "thumbnail_url", "category", "duration", "order", "published")

    @admin.display(description="Видео")
    def link(self, obj):
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">открыть</a>', obj.video_url)


@admin.register(TrainingLink)
class TrainingLinkAdmin(_OrderedContentAdmin):
    fields = ("title", "description", "url", "category", "icon", "order", "published")
