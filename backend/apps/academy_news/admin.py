"""Managing public academy news in the Django admin.

Create / edit / delete articles, upload a cover and any number of photos
(several at once through «Добавить фотографии»), captions and order in the
inline, a category, draft → publish (now or on a future date) → unpublish.
Who may do it is Django's own model permissions: a superuser, or a staff
account given the «Новости академии» permissions.
"""
from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.html import format_html

from .images import validate_image
from .models import Article, ArticlePhoto

MAX_BULK_PHOTOS = 40


def _badge(css: str, label: str) -> str:
    return format_html('<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label)


def _preview(field_file, height: int = 64) -> str:
    if not field_file:
        return "—"
    return format_html('<img src="{}" alt="" style="height:{}px;border-radius:8px;object-fit:cover" loading="lazy">',
                       field_file.url, height)


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        files = data if isinstance(data, (list, tuple)) else ([data] if data else [])
        if len(files) > MAX_BULK_PHOTOS:
            raise ValidationError(f"За один раз — не больше {MAX_BULK_PHOTOS} фотографий.")
        cleaned = []
        for upload in files:
            single = super().clean(upload, initial)
            validate_image(single)
            cleaned.append(single)
        return cleaned


class ArticleAdminForm(forms.ModelForm):
    new_photos = MultipleImageField(
        required=False, label="Добавить фотографии",
        help_text="Можно выбрать сразу несколько файлов (JPEG, PNG, WebP до 15 МБ). Подписи и порядок — ниже, в «Фотографиях».",
    )

    class Meta:
        model = Article
        fields = "__all__"
        widgets = {
            "excerpt": forms.Textarea(attrs={"rows": 2}),
            "body": forms.Textarea(attrs={"rows": 18}),
        }


class ArticlePhotoInline(admin.TabularInline):
    model = ArticlePhoto
    extra = 0
    fields = ("preview", "image", "caption", "order")
    readonly_fields = ("preview",)
    ordering = ("order", "id")

    @admin.display(description="Превью")
    def preview(self, obj: ArticlePhoto) -> str:
        return _preview(obj.thumb or obj.image)


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    form = ArticleAdminForm
    list_display = ("title", "cover_preview", "category", "status_badge", "published_at", "is_featured", "photo_count")
    list_filter = ("status", "category", "is_featured", "published_at")
    search_fields = ("title", "excerpt", "body")
    date_hierarchy = "published_at"
    readonly_fields = ("cover_large_preview", "public_link", "author", "created_at", "updated_at")
    inlines = [ArticlePhotoInline]
    actions = ["publish_now", "unpublish"]
    fieldsets = (
        (None, {"fields": ("title", "slug", "category", "excerpt", "body")}),
        ("Обложка", {"fields": ("cover", "cover_large_preview", "cover_caption")}),
        ("Фотографии", {"fields": ("new_photos",)}),
        ("Публикация", {
            "fields": ("status", "published_at", "is_featured", "show_author", "author", "public_link"),
            "description": "«Черновик» не виден на сайте. «Опубликована» с датой в будущем — появится в это время.",
        }),
        ("Служебное", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("photos")

    def save_model(self, request, obj, form, change):
        if not change and obj.author_id is None:
            obj.author = request.user
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        uploads = form.cleaned_data.get("new_photos") or []
        start = (max((p.order for p in form.instance.photos.all()), default=-1) + 1) if uploads else 0
        for offset, upload in enumerate(uploads):
            ArticlePhoto.objects.create(article=form.instance, image=upload, order=start + offset)
        if uploads:
            self.message_user(request, f"Добавлено фотографий: {len(uploads)}.", messages.SUCCESS)

    @admin.display(description="Статус")
    def status_badge(self, obj: Article) -> str:
        if obj.status == Article.Status.DRAFT:
            return _badge("ok-badge-muted", "Черновик")
        if obj.published_at > timezone.now():
            return _badge("ok-badge-warning", "Запланирована")
        return _badge("ok-badge-success", "На сайте")

    @admin.display(description="Обложка")
    def cover_preview(self, obj: Article) -> str:
        return _preview(obj.cover_thumb or obj.cover, 40)

    @admin.display(description="Текущая обложка")
    def cover_large_preview(self, obj: Article) -> str:
        return _preview(obj.cover_thumb or obj.cover, 140)

    @admin.display(description="Фото")
    def photo_count(self, obj: Article) -> int:
        return len(obj.photos.all())

    @admin.display(description="Адрес на сайте")
    def public_link(self, obj: Article) -> str:
        if not obj.pk:
            return "Появится после сохранения."
        return format_html("<code>/news/{}</code>{}", obj.slug, "" if obj.is_public else " — пока не видна посетителям")

    @admin.action(description="Опубликовать сейчас")
    def publish_now(self, request, queryset):
        now = timezone.now()
        for article in queryset:
            article.status = Article.Status.PUBLISHED
            if article.published_at > now:
                article.published_at = now
            article.save()
        self.message_user(request, f"Опубликовано: {queryset.count()}.", messages.SUCCESS)

    @admin.action(description="Снять с публикации (в черновики)")
    def unpublish(self, request, queryset):
        for article in queryset:
            article.status = Article.Status.DRAFT
            article.save()
        self.message_user(request, f"Снято с публикации: {queryset.count()}.", messages.SUCCESS)
