"""Student & Parent Portal accounts.

One unified role (User.Role.STUDENT_PARENT) per family: a `PortalAccount`
is the portal side of that User and `StudentLink` says which students it
may see. A parent with several children has one account linked to each of
them; nothing else ever widens what an account can read (see
services.scope — every portal query starts from these links).

Passwords live only in User.password (Django's hasher). The temporary
password handed out at provisioning / reset is returned once by that one
API response and is never stored, logged or shown again — this model keeps
only *when* credentials were issued and whether the first-login change is
still pending.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.academy.models import Student


class PortalAccount(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="portal_account", verbose_name="Аккаунт",
    )
    students = models.ManyToManyField(
        Student, through="StudentLink", related_name="portal_accounts", verbose_name="Студенты",
    )
    # Digits only — how the Assistant finds a family's existing account when
    # a brother or sister is enrolled (services.accounts.family_accounts).
    parent_phone = models.CharField(max_length=30, blank=True, db_index=True, verbose_name="Телефон родителя (цифры)")
    must_change_password = models.BooleanField(
        default=True, verbose_name="Сменить пароль при входе",
        help_text="Пока включено, кабинет открывает только смену пароля.",
    )
    can_view_payments = models.BooleanField(
        default=True, verbose_name="Показывать оплату",
        help_text="Видит ли семья в кабинете свои начисления и платежи.",
    )
    credentials_issued_at = models.DateTimeField(null=True, blank=True, verbose_name="Данные для входа выданы")
    password_changed_at = models.DateTimeField(null=True, blank=True, verbose_name="Пароль изменён владельцем")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="Создал",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создан")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменён")

    class Meta:
        verbose_name = "Аккаунт кабинета ученика"
        verbose_name_plural = "Аккаунты кабинета ученика"
        ordering = ["-created_at"]

    def __str__(self):
        return self.user.username

    @property
    def credentials_status(self) -> str:
        """disabled — login switched off; pending — the temporary password
        has not been replaced yet; active — the family uses its own one."""
        if not self.user.is_active:
            return "disabled"
        return "pending" if self.must_change_password else "active"


class StudentLink(models.Model):
    account = models.ForeignKey(PortalAccount, on_delete=models.CASCADE, related_name="links", verbose_name="Аккаунт")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="portal_links", verbose_name="Студент")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="Связал",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Связан")

    class Meta:
        verbose_name = "Связь аккаунта со студентом"
        verbose_name_plural = "Связи аккаунтов со студентами"
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(fields=["account", "student"], name="unique_portal_account_student"),
        ]

    def __str__(self):
        return f"{self.account} → {self.student}"
