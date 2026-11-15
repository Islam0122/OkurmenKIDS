from django.contrib import admin

from .models import Comment, CommunityNotification, Post, PostImage, Report


class PostImageInline(admin.TabularInline):
    model = PostImage
    extra = 0
    fields = ("width", "height", "order")
    readonly_fields = ("width", "height")


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    """Day-to-day moderation is in the LMS («Сообщество»); admin is for support."""

    list_display = ("id", "author_student", "group", "category", "status", "is_announcement", "is_pinned", "published_at")
    list_filter = ("status", "category", "is_announcement", "audience")
    search_fields = ("text", "author_student__first_name", "author_student__last_name")
    raw_id_fields = ("author_student", "author", "group", "moderated_by", "website_testimonial")
    inlines = [PostImageInline]


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "author_student", "status", "created_at")
    list_filter = ("status",)
    raw_id_fields = ("post", "author_student", "author", "parent", "moderated_by")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "comment", "reason", "status", "created_at")
    list_filter = ("status", "reason")
    raw_id_fields = ("post", "comment", "reporter_student", "resolved_by")


@admin.register(CommunityNotification)
class CommunityNotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "kind", "is_read", "created_at")
    list_filter = ("kind", "is_read")
    raw_id_fields = ("recipient", "post", "comment")
