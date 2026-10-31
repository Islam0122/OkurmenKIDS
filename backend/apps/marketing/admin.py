"""Django admin маркетинга — только для администратора (просмотр и правка).
Сотрудники маркетинга работают в кабинете /marketing."""
from __future__ import annotations

from django.contrib import admin

from .models import Campaign, ContentItem, MarketingTask


@admin.register(ContentItem)
class ContentItemAdmin(admin.ModelAdmin):
    list_display = ("title", "channel", "format", "publish_date", "status", "responsible", "updated_at")
    list_filter = ("status", "channel", "format")
    search_fields = ("title", "description")
    date_hierarchy = "publish_date"
    raw_id_fields = ("responsible", "created_by")
    readonly_fields = ("published_at", "created_at", "updated_at")


@admin.register(MarketingTask)
class MarketingTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "due_date", "priority", "status", "responsible", "updated_at")
    list_filter = ("status", "priority")
    search_fields = ("title", "description")
    raw_id_fields = ("responsible", "created_by")
    readonly_fields = ("completed_at", "created_at", "updated_at")


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "channel", "status", "start_date", "end_date", "leads", "sales", "responsible")
    list_filter = ("status", "channel")
    search_fields = ("name", "result")
    raw_id_fields = ("responsible", "created_by")
