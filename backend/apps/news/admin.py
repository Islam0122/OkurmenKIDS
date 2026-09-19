from __future__ import annotations

from django import forms
from django.contrib import admin
from django.utils.html import format_html

from .models import News, NewsRead


def _badge(css: str, label: str) -> str:
    return format_html('<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label)


_TYPE_BADGE_CSS = {
    News.NewsType.INFO: "ok-badge-info",
    News.NewsType.IMPORTANT: "ok-badge-danger",
    News.NewsType.WARNING: "ok-badge-warning",
    News.NewsType.EVENT: "ok-badge-success",
}


class NewsAdminForm(forms.ModelForm):
    class Meta:
        model = News
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        audience = cleaned_data.get("audience")
        teachers = cleaned_data.get("teachers")

        if audience == News.Audience.SELECTED and not teachers:
            self.add_error(
                "teachers",
                "Выберите хотя бы одного тренера — аудитория новости установлена как «Выбранным».",
            )

        return cleaned_data


@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    form = NewsAdminForm
    list_display = ("title", "type_badge", "audience_badge", "published_badge", "created_at", "expires_at")
    list_filter = ("type", "audience", "is_published", "created_at")
    search_fields = ("title", "text")
    ordering = ("-created_at",)
    filter_horizontal = ("teachers",)
    readonly_fields = ("created_at",)
    fieldsets = (
        (None, {"fields": ("title", "text", "type")}),
        ("Показ тренерам", {"fields": ("audience", "teachers", "is_published", "expires_at")}),
        ("Служебное", {"fields": ("created_at",)}),
    )

    @admin.display(description="Тип", ordering="type")
    def type_badge(self, obj: News) -> str:
        return _badge(_TYPE_BADGE_CSS.get(obj.type, "ok-badge-muted"), obj.get_type_display())

    @admin.display(description="Аудитория", ordering="audience")
    def audience_badge(self, obj: News) -> str:
        if obj.audience == News.Audience.ALL:
            return _badge("ok-badge-muted", "Всем")
        count = obj.teachers.count()
        return _badge("ok-badge-info", f"Выбранным ({count})")

    @admin.display(description="Опубликовано", ordering="is_published", boolean=False)
    def published_badge(self, obj: News) -> str:
        return _badge("ok-badge-success", "Да") if obj.is_published else _badge("ok-badge-muted", "Нет")


@admin.register(NewsRead)
class NewsReadAdmin(admin.ModelAdmin):
    list_display = ("news", "teacher", "read_at")
    list_filter = ("read_at",)
    search_fields = (
        "news__title",
        "teacher__user__username",
        "teacher__user__first_name",
        "teacher__user__last_name",
    )
    ordering = ("-read_at",)
    readonly_fields = ("news", "teacher", "read_at")

    def has_add_permission(self, request) -> bool:
        # Read records are only ever created by a Teacher marking News as
        # read via the API — nothing for an Admin to add by hand here.
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False
