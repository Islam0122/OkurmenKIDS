"""Django admin подбора: только согласование учётных записей.

HR работает в HR-кабинете (/hr). Здесь администратор решает запросы HR на
учётную запись для ролей, которыми HR не управляет сам: «Одобрить» создаёт
пользователя обычным механизмом LMS (без пароля — его задаёт администратор на
странице пользователя) и связывает его с откликом; «Отклонить» закрывает запрос.
"""
from __future__ import annotations

from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from apps.users.permissions import is_admin_user

from .models import AccountRequest
from .services import hiring
from .services.common import RecruitmentError


@admin.register(AccountRequest)
class AccountRequestAdmin(admin.ModelAdmin):
    list_display = ("username", "role_label", "candidate", "status", "requested_by", "created_at", "user_link")
    list_filter = ("status", "role")
    search_fields = ("username", "email", "first_name", "last_name")
    readonly_fields = ("application", "role", "username", "email", "first_name", "last_name", "comment", "status",
                       "requested_by", "decided_by", "decided_at", "decision_comment", "created_at")
    actions = ("approve", "reject")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return is_admin_user(request.user)

    def has_view_permission(self, request, obj=None):
        return is_admin_user(request.user)

    def has_module_permission(self, request):
        return is_admin_user(request.user)

    @admin.display(description="Роль")
    def role_label(self, obj):
        return dict(hiring.User.Role.choices).get(obj.role, obj.role)

    @admin.display(description="Кандидат")
    def candidate(self, obj):
        return obj.application.candidate.full_name

    @admin.display(description="Учётная запись")
    def user_link(self, obj):
        user = obj.application.hired_user
        if obj.status != AccountRequest.Status.APPROVED or user is None:
            return "—"
        return format_html('<a href="{}">{}</a>', reverse("admin:users_user_change", args=[user.pk]), user.username)

    @admin.action(description="Одобрить и создать учётную запись")
    def approve(self, request, queryset):
        for item in queryset:
            try:
                hiring.approve_request(item, request.user)
            except RecruitmentError as exc:
                self.message_user(request, f"{item.username}: {exc.message}", messages.ERROR)
                continue
            self.message_user(request, f"{item.username}: учётная запись создана. Задайте пароль на странице "
                                       f"пользователя.", messages.SUCCESS)

    @admin.action(description="Отклонить")
    def reject(self, request, queryset):
        for item in queryset:
            try:
                hiring.reject_request(item, request.user, "Отклонено администратором")
            except RecruitmentError as exc:
                self.message_user(request, f"{item.username}: {exc.message}", messages.ERROR)
                continue
            self.message_user(request, f"{item.username}: запрос отклонён.", messages.SUCCESS)
