"""Public website content in the Django admin — for administrators.

Marketing staff never use the Django admin (User.LMS_ONLY_ROLES); they work
in the LMS cabinet /marketing/site through the CMS API (cms.py). The admin
gives administrators the same content with the same workflow and a preview
link to the public website.
"""
from __future__ import annotations

from django.contrib import admin, messages
from django.utils import timezone
from django.utils.html import format_html

from . import models as m
from .cms import preview_url


def _thumb(field_file, height: int = 48) -> str:
    if not field_file:
        return "—"
    return format_html('<img src="{}" alt="" style="height:{}px;border-radius:8px;object-fit:cover" loading="lazy">',
                       field_file.url, height)


class WorkflowAdmin(admin.ModelAdmin):
    preview_kind: str | None = None
    actions = ["publish_now", "send_to_review", "move_to_draft", "archive"]
    readonly_fields = ("preview_link", "created_by", "reviewed_by", "created_at", "updated_at")
    list_filter = ("status",)

    def save_model(self, request, obj, form, change):
        if not change and obj.created_by_id is None:
            obj.created_by = request.user
        if obj.status == m.Workflow.PUBLISHED and "status" in form.changed_data:
            obj.reviewed_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Статус")
    def state(self, obj) -> str:
        labels = {"draft": "Черновик", "review": "На согласовании", "scheduled": "Запланировано",
                  "published": "На сайте", "archived": "В архиве"}
        return labels[obj.workflow_state]

    @admin.display(description="Предпросмотр")
    def preview_link(self, obj) -> str:
        if not obj.pk or not self.preview_kind:
            return "Сохраните, чтобы получить ссылку."
        link = preview_url(self.preview_kind, obj.pk)
        if link["url"]:
            return format_html('<a href="{}" target="_blank" rel="noopener">Открыть на сайте</a>', link["url"])
        return "Задайте PUBLIC_WEBSITE_URL, чтобы открыть предпросмотр."

    def _set(self, request, queryset, status: str, label: str):
        updated = 0
        for obj in queryset:
            obj.status = status
            if status == m.Workflow.PUBLISHED:
                obj.reviewed_by = request.user
                if obj.published_at > timezone.now():
                    obj.published_at = timezone.now()
            obj.save()
            updated += 1
        self.message_user(request, f"{label}: {updated}.", messages.SUCCESS)

    @admin.action(description="Опубликовать сейчас")
    def publish_now(self, request, queryset):
        if queryset.model is m.Testimonial:
            queryset = queryset.filter(consent=True)
        self._set(request, queryset, m.Workflow.PUBLISHED, "Опубликовано")

    @admin.action(description="Отправить на согласование")
    def send_to_review(self, request, queryset):
        self._set(request, queryset, m.Workflow.REVIEW, "На согласовании")

    @admin.action(description="Снять с публикации (в черновики)")
    def move_to_draft(self, request, queryset):
        self._set(request, queryset, m.Workflow.DRAFT, "В черновиках")

    @admin.action(description="В архив")
    def archive(self, request, queryset):
        self._set(request, queryset, m.Workflow.ARCHIVED, "В архиве")


class EventPhotoInline(admin.TabularInline):
    model = m.EventPhoto
    extra = 0
    fields = ("preview", "image", "caption", "order")
    readonly_fields = ("preview",)

    @admin.display(description="Превью")
    def preview(self, obj):
        return _thumb(obj.thumb or obj.image)


class AchievementPhotoInline(EventPhotoInline):
    model = m.AchievementPhoto


class RegistrationInline(admin.TabularInline):
    model = m.EventRegistration
    extra = 0
    fields = ("parent_name", "phone", "child_name", "child_age", "comment", "status", "created_at")
    readonly_fields = ("parent_name", "phone", "child_name", "child_age", "comment", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(m.CoursePage)
class CoursePageAdmin(WorkflowAdmin):
    preview_kind = "course"
    list_display = ("title", "course", "age_min", "age_max", "duration", "state", "is_featured", "order")
    list_editable = ("order",)
    list_filter = ("status", "is_featured", "icon")
    search_fields = ("title", "tagline", "body")
    autocomplete_fields = ()


@admin.register(m.Event)
class EventAdmin(WorkflowAdmin):
    preview_kind = "event"
    list_display = ("title", "category", "starts_at", "location", "state", "registration_enabled")
    list_filter = ("status", "category", "registration_enabled", "starts_at")
    search_fields = ("title", "excerpt", "location")
    date_hierarchy = "starts_at"
    inlines = [EventPhotoInline, RegistrationInline]


@admin.register(m.Achievement)
class AchievementAdmin(WorkflowAdmin):
    preview_kind = "achievement"
    list_display = ("title", "category", "date", "state", "is_featured")
    list_filter = ("status", "category", "is_featured")
    search_fields = ("title", "excerpt", "body")
    date_hierarchy = "date"
    inlines = [AchievementPhotoInline]


@admin.register(m.TeamMember)
class TeamMemberAdmin(WorkflowAdmin):
    list_display = ("__str__", "position", "group", "teacher", "photo_approved", "state", "order")
    list_editable = ("order",)
    list_filter = ("status", "group", "photo_approved")
    search_fields = ("name", "position", "specialization")


@admin.register(m.Testimonial)
class TestimonialAdmin(WorkflowAdmin):
    list_display = ("author_name", "author_role", "rating", "consent", "state", "is_featured", "order")
    list_editable = ("order",)
    list_filter = ("status", "author_role", "consent", "is_featured")
    search_fields = ("author_name", "text")


@admin.register(m.SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    filter_horizontal = ("featured_projects", "featured_news")

    def has_add_permission(self, request):
        return not m.SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(m.HomeSection)
class HomeSectionAdmin(admin.ModelAdmin):
    list_display = ("key", "is_visible", "order", "title")
    list_editable = ("is_visible", "order")


@admin.register(m.Statistic)
class StatisticAdmin(admin.ModelAdmin):
    list_display = ("value", "label", "is_active", "order")
    list_editable = ("is_active", "order")


@admin.register(m.Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "phone", "is_active", "order")
    list_editable = ("is_active", "order")


@admin.register(m.PromoBanner)
class PromoBannerAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "starts_at", "ends_at", "order")
    list_editable = ("is_active", "order")


@admin.register(m.MediaCategory)
class MediaCategoryAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(m.MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ("title", "preview", "kind", "category", "size", "created_at")
    list_filter = ("kind", "category")
    search_fields = ("title", "alt")
    readonly_fields = ("preview", "kind", "size", "uploaded_by", "created_at", "updated_at")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.uploaded_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description="Превью")
    def preview(self, obj):
        return _thumb(obj.file) if obj.kind == m.MediaAsset.Kind.IMAGE and obj.file else obj.get_kind_display()


@admin.register(m.Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("parent_name", "phone", "child_age", "course", "branch", "contact_method", "status", "created_at")
    list_filter = ("status", "course", "branch", "contact_method", "created_at")
    list_editable = ("status",)
    search_fields = ("parent_name", "phone", "message")
    readonly_fields = [f.name for f in m.Lead._meta.fields if f.name not in ("status", "note")]
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False


@admin.register(m.EventRegistration)
class EventRegistrationAdmin(admin.ModelAdmin):
    list_display = ("parent_name", "phone", "event", "child_age", "status", "created_at")
    list_filter = ("status", "event")
    list_editable = ("status",)
    search_fields = ("parent_name", "phone", "child_name")
    readonly_fields = ("event", "parent_name", "phone", "child_name", "child_age", "comment", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(m.ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    """Read-only history of bulk imports (the import itself is in the LMS cabinet)."""
    list_display = ("file_name", "content_type", "status", "created_by", "total_rows", "created_count",
                    "updated_count", "skipped_count", "failed_count", "created_at")
    list_filter = ("status", "content_type")
    readonly_fields = [f.name for f in m.ImportBatch._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
