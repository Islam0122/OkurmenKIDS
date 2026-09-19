from __future__ import annotations

import datetime as dt

from django import forms
from django.contrib import admin
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from apps.users.models import Teacher

from .models import News


def _badge(css: str, label: str) -> str:
    return format_html('<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label)


def _pluralize_teacher(count: int) -> str:
    mod10, mod100 = count % 10, count % 100
    if mod10 == 1 and mod100 != 11:
        word = "тренер"
    elif 2 <= mod10 <= 4 and not (12 <= mod100 <= 14):
        word = "тренера"
    else:
        word = "тренеров"
    return f"{count} {word}"


_TYPE_BADGE_CSS = {
    News.NewsType.INFO: "ok-badge-info",
    News.NewsType.IMPORTANT: "ok-badge-danger",
    News.NewsType.WARNING: "ok-badge-warning",
    News.NewsType.EVENT: "ok-badge-success",
}


class NewsAdminForm(forms.ModelForm):
    teachers = forms.ModelMultipleChoiceField(
        queryset=Teacher.objects.none(),
        required=False,
        label="Тренеры",
        help_text="Кому именно адресована новость — только при аудитории «Выбранным».",
        widget=forms.SelectMultiple(
            attrs={
                "class": "ok-multiselect-source",
                "data-add-label": "Добавить тренера",
            }
        ),
    )

    class Meta:
        model = News
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teachers"].queryset = (
            Teacher.objects.filter(is_active=True).select_related("user").order_by("user__first_name", "user__last_name")
        )

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
    list_display = ("title", "type_badge", "audience_badge", "published_badge", "expires_at", "created_at", "reads_column")
    list_filter = ("type", "audience", "is_published", "created_at")
    search_fields = ("title", "text")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)

    def get_queryset(self, request):
        # Both fields feed reads_column/reads_overview below — prefetched
        # once here so a changelist page never runs a query per row.
        return super().get_queryset(request).prefetch_related("teachers__user", "reads__teacher__user")

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            ("Новость", {"fields": ("title", "text", "type")}),
            ("Показ тренерам", {"fields": ("audience", "teachers", "is_published", "expires_at")}),
        ]
        if obj is not None and obj.pk is not None:
            fieldsets.append(("👁 Прочтения", {"fields": ("reads_overview",)}))
        fieldsets.append(("Служебное", {"fields": ("created_at",)}))
        return fieldsets

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.pk is not None:
            return (*self.readonly_fields, "reads_overview")
        return self.readonly_fields

    @admin.display(description="Тип", ordering="type")
    def type_badge(self, obj: News) -> str:
        return _badge(_TYPE_BADGE_CSS.get(obj.type, "ok-badge-muted"), obj.get_type_display())

    @admin.display(description="Аудитория", ordering="audience")
    def audience_badge(self, obj: News) -> str:
        if obj.audience == News.Audience.ALL:
            return _badge("ok-badge-muted", "Всем")
        count = len(obj.teachers.all())
        return _badge("ok-badge-info", f"Выбранным ({count})")

    @admin.display(description="Опубликовано", ordering="is_published", boolean=False)
    def published_badge(self, obj: News) -> str:
        return _badge("ok-badge-success", "Да") if obj.is_published else _badge("ok-badge-muted", "Нет")

    def _target_teachers(self, obj: News) -> list[Teacher]:
        """Who this News is actually addressed to — the same scope the
        Teacher-facing API uses to decide visibility (see
        News.objects.visible_to), so this list never includes a Teacher
        the news wasn't meant for."""
        if obj.audience == News.Audience.SELECTED:
            return list(obj.teachers.all())
        return list(Teacher.objects.filter(is_active=True).select_related("user"))

    def _read_at_by_teacher(self, obj: News, target_ids: set[int]) -> dict[int, dt.datetime]:
        return {r.teacher_id: r.read_at for r in obj.reads.all() if r.teacher_id in target_ids}

    @admin.display(description="Прочтения")
    def reads_column(self, obj: News) -> str:
        targets = self._target_teachers(obj)
        reads = self._read_at_by_teacher(obj, {t.id for t in targets})
        return f"{len(reads)} / {len(targets)}"

    @admin.display(description="Прочтения")
    def reads_overview(self, obj: News) -> str:
        targets = self._target_teachers(obj)
        reads = self._read_at_by_teacher(obj, {t.id for t in targets})

        if obj.audience == News.Audience.SELECTED:
            summary = f"Кому отправлено: {_pluralize_teacher(len(targets))}. Прочитали: {len(reads)} из {len(targets)}."
        else:
            summary = f"Прочитали: {len(reads)} из {len(targets)}."

        if not targets:
            return format_html('<p class="ok-news-reads-summary">{}</p>', summary)

        read_rows = sorted((t for t in targets if t.id in reads), key=lambda t: reads[t.id])
        unread_rows = sorted((t for t in targets if t.id not in reads), key=lambda t: str(t))

        # One format_html_join call for both read/unread rows — concatenating
        # two separately-escaped SafeString results with `+` would silently
        # drop the "safe" marking and get double-escaped by the outer
        # format_html() call below.
        rows = [(True, t, timezone.localtime(reads[t.id]).strftime("%d.%m %H:%M")) for t in read_rows] + [
            (False, t, "Не прочитано") for t in unread_rows
        ]
        rows_html = format_html_join(
            "",
            '<div class="ok-news-read-row {}"><i class="bi {}"></i>'
            '<span class="ok-news-read-name">{}</span>'
            '<span class="ok-news-read-time">{}</span></div>',
            (
                ("is-read" if is_read else "is-unread", "bi-check-circle-fill" if is_read else "bi-circle", str(t), time_label)
                for is_read, t, time_label in rows
            ),
        )

        return format_html(
            '<div class="ok-news-reads"><p class="ok-news-reads-summary">{}</p>'
            '<div class="ok-news-reads-list">{}</div></div>',
            summary,
            rows_html,
        )
