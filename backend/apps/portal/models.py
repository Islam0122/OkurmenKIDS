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


# ---------------------------------------------------------------------------
# Bulk account generation (Assistant Workspace → Студенты → Кабинеты).
#
# A run is one batch: every student in the chosen scope is recorded as an
# item up front (already has an account / pending / created / failed), and
# the accounts are then provisioned a few at a time through the same
# services.accounts.provision_account the single-student flow uses.
#
# Plaintext passwords are never stored. A generated password exists in
# memory only while its account is being created; it is then kept as a
# Fernet token (`sealed_password`, key derived from SECRET_KEY) until the
# one-time XLSX export is downloaded or the secrets expire — whichever comes
# first — and is wiped at that point. The run and item rows never carry the
# password itself.
# ---------------------------------------------------------------------------

class BulkAccountRun(models.Model):
    class Scope(models.TextChoices):
        ALL = "all", "Все активные студенты"
        GROUPS = "groups", "Выбранные группы"

    class Status(models.TextChoices):
        PENDING = "pending", "В очереди"
        RUNNING = "running", "Выполняется"
        COMPLETED = "completed", "Завершён"

    class ExportState(models.TextChoices):
        NONE = "none", "Нет учётных данных"
        READY = "ready", "Готов к выгрузке"
        DOWNLOADED = "downloaded", "Выгружен"
        EXPIRED = "expired", "Истёк срок выгрузки"

    scope = models.CharField(max_length=10, choices=Scope.choices, verbose_name="Охват")
    group_ids = models.JSONField(default=list, blank=True, verbose_name="Группы")
    group_names = models.JSONField(default=list, blank=True, verbose_name="Названия групп")
    retry_of = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="retries", verbose_name="Повтор для",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True,
                              verbose_name="Статус")
    export_state = models.CharField(max_length=12, choices=ExportState.choices, default=ExportState.NONE,
                                    verbose_name="Выгрузка")
    secrets_expire_at = models.DateTimeField(null=True, blank=True, verbose_name="Пароли удаляются")
    exported_at = models.DateTimeField(null=True, blank=True, verbose_name="Выгружен")
    exported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="Выгрузил",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
        verbose_name="Запустил",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name="Запущен")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Завершён")

    class Meta:
        verbose_name = "Пакетное создание аккаунтов"
        verbose_name_plural = "Пакетное создание аккаунтов"
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"Пакет №{self.pk}"


class BulkAccountRunItem(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        CREATED = "created", "Аккаунт создан"
        EXISTING = "existing", "Аккаунт уже был"
        FAILED = "failed", "Ошибка"

    run = models.ForeignKey(BulkAccountRun, on_delete=models.CASCADE, related_name="items", verbose_name="Пакет")
    student = models.ForeignKey(
        Student, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="Студент",
    )
    # Snapshots, so the report stays readable if the student or group is later renamed or removed.
    student_name = models.CharField(max_length=300, verbose_name="Студент (ФИО)")
    group_name = models.CharField(max_length=150, blank=True, verbose_name="Группа")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True,
                              verbose_name="Статус")
    login = models.CharField(max_length=40, blank=True, verbose_name="Логин")
    account = models.ForeignKey(
        PortalAccount, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="Аккаунт",
    )
    error = models.CharField(max_length=500, blank=True, verbose_name="Причина ошибки")
    # Fernet token of the temporary password — see the section comment above. Cleared after export/expiry.
    sealed_password = models.TextField(blank=True, verbose_name="Зашифрованный временный пароль")
    issued_at = models.DateTimeField(null=True, blank=True, verbose_name="Учётные данные созданы")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Добавлен")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Изменён")

    class Meta:
        verbose_name = "Строка пакета"
        verbose_name_plural = "Строки пакета"
        ordering = ["pk"]
        indexes = [models.Index(fields=["run", "status"])]

    def __str__(self):
        return f"{self.student_name}: {self.get_status_display()}"
