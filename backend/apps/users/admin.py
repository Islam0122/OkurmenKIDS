from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.password_validation import validate_password
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from apps.users.models import Subject, Teacher, User
from apps.users.services import change_teacher_password_and_send, create_teacher


# ---------------------------------------------------------------------------
# User admin
# ---------------------------------------------------------------------------

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = (
        "username",
        "email",
        "full_name",
        "role_badge",
        "verified_badge",
        "active_badge",
        "created_at",
    )
    list_filter = ("role", "is_verified", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")
    readonly_fields = ("created_at", "updated_at", "last_login", "date_joined")
    ordering = ("-created_at",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Личные данные", {"fields": ("first_name", "last_name", "email")}),
        (
            "Права доступа",
            {
                "fields": (
                    "role",
                    "is_verified",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Даты", {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )

    @admin.display(description="Полное имя")
    def full_name(self, obj: User) -> str:
        return obj.get_full_name() or "—"

    @admin.display(description="Роль")
    def role_badge(self, obj: User) -> str:
        css = "ok-badge-success" if obj.role == User.Role.ADMIN else "ok-badge-muted"
        return format_html(
            '<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>',
            css,
            obj.get_role_display(),
        )

    @admin.display(description="Подтверждён")
    def verified_badge(self, obj: User) -> str:
        css = "ok-badge-success" if obj.is_verified else "ok-badge-muted"
        label = "Подтверждён" if obj.is_verified else "Не подтверждён"
        return format_html('<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label)

    @admin.display(description="Статус")
    def active_badge(self, obj: User) -> str:
        css = "ok-badge-success" if obj.is_active else "ok-badge-danger"
        label = "Активен" if obj.is_active else "Деактивирован"
        return format_html('<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label)


# ---------------------------------------------------------------------------
# Subject admin
# ---------------------------------------------------------------------------

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "active_badge", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Статус")
    def active_badge(self, obj: Subject) -> str:
        css = "ok-badge-success" if obj.is_active else "ok-badge-muted"
        label = "Активен" if obj.is_active else "Неактивен"
        return format_html('<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label)


# ---------------------------------------------------------------------------
# Trainer ("Add Trainer") form — creates User + Teacher in one step.
# Admin sets the password directly; the backend never generates one.
# ---------------------------------------------------------------------------

class AddTrainerForm(forms.ModelForm):
    """Single form used by "Add Trainer": collects User + Teacher fields,
    including a password Admin chooses, so Admin never has to create a User
    first and a Teacher second.

    The account always starts with ``is_verified=False`` — verification is
    a deliberate, separate step (admin action or ``/trainers/{id}/verify/``),
    never something set at creation time.
    """

    first_name = forms.CharField(label="Имя", max_length=100)
    last_name = forms.CharField(label="Фамилия", max_length=100, required=False)
    email = forms.EmailField(label="Email")
    username = forms.CharField(label="Логин", max_length=150)
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput)
    password_confirm = forms.CharField(
        label="Подтверждение пароля", widget=forms.PasswordInput
    )

    class Meta:
        model = Teacher
        fields = [
            "phone",
            "image",
            "subjects",
            "position",
            "experience_years",
            "bio",
            "hire_date",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field_order = [
            "first_name",
            "last_name",
            "email",
            "username",
            "password",
            "password_confirm",
            "phone",
            "image",
            "subjects",
            "position",
            "experience_years",
            "bio",
            "hire_date",
            "is_active",
        ]
        self.order_fields(field_order)

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Пользователь с таким логином уже существует.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Пользователь с таким email уже существует.")
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        password_confirm = cleaned.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "Пароли не совпадают.")
        elif password:
            # Run this against a throwaway, not-yet-saved User so the
            # UserAttributeSimilarityValidator has something sensible to
            # compare against.
            temp_user = User(
                username=cleaned.get("username", ""),
                email=cleaned.get("email", ""),
                first_name=cleaned.get("first_name", ""),
                last_name=cleaned.get("last_name", ""),
            )
            try:
                validate_password(password, user=temp_user)
            except forms.ValidationError as exc:
                self.add_error("password", exc)
        return cleaned


class ChangeTrainerForm(forms.ModelForm):
    """Used when editing an existing Trainer — no username/email/password
    fields here. Credentials are controlled by Admin only via the dedicated
    "Изменить пароль и отправить" page, not free-text edits here that could
    silently desync User <-> Teacher.
    """

    class Meta:
        model = Teacher
        fields = [
            "phone",
            "image",
            "subjects",
            "position",
            "experience_years",
            "bio",
            "hire_date",
            "is_active",
        ]


class ChangeTeacherPasswordForm(forms.Form):
    new_password = forms.CharField(label="Новый пароль", widget=forms.PasswordInput)
    new_password_confirm = forms.CharField(
        label="Подтверждение пароля", widget=forms.PasswordInput
    )

    def __init__(self, *args, teacher: Teacher, **kwargs):
        self.teacher = teacher
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("new_password")
        confirm = cleaned.get("new_password_confirm")
        if password and confirm and password != confirm:
            self.add_error("new_password_confirm", "Пароли не совпадают.")
        elif password:
            try:
                validate_password(password, user=self.teacher.user)
            except forms.ValidationError as exc:
                self.add_error("new_password", exc)
        return cleaned


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = (
        "teacher_name",
        "email",
        "phone",
        "subjects_list",
        "active_badge",
        "verified_badge",
        "hire_date",
        "change_password_link",
    )
    list_filter = ("is_active", "user__is_verified", "subjects")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    filter_horizontal = ("subjects",)
    actions = ["verify_accounts", "deactivate_trainers"]

    @admin.display(description="Тренер")
    def teacher_name(self, obj: Teacher) -> str:
        return obj.user.get_full_name() or obj.user.username

    @admin.display(description="Email")
    def email(self, obj: Teacher) -> str:
        return obj.user.email

    @admin.display(description="Предметы")
    def subjects_list(self, obj: Teacher) -> str:
        return ", ".join(obj.subjects.values_list("name", flat=True)) or "—"

    @admin.display(description="Подтверждён")
    def verified_badge(self, obj: Teacher) -> str:
        css = "ok-badge-success" if obj.user.is_verified else "ok-badge-warning"
        label = "Подтверждён" if obj.user.is_verified else "Ожидает"
        return format_html('<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label)

    @admin.display(description="Статус")
    def active_badge(self, obj: Teacher) -> str:
        css = "ok-badge-success" if obj.is_active else "ok-badge-danger"
        label = "Активен" if obj.is_active else "Деактивирован"
        return format_html('<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label)

    @admin.display(description="Пароль")
    def change_password_link(self, obj: Teacher) -> str:
        url = reverse("admin:users_teacher_change_password", args=[obj.pk])
        return format_html('<a href="{}">Изменить и отправить</a>', url)

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = AddTrainerForm
        else:
            kwargs["form"] = ChangeTrainerForm
        return super().get_form(request, obj, **kwargs)

    def save_form(self, request, form, change):
        if change:
            return super().save_form(request, form, change)

        # "Add Trainer": create User (role=TEACHER) + Teacher atomically
        # using the password Admin entered, then email those exact
        # credentials to the trainer.
        cleaned = form.cleaned_data
        result = create_teacher(
            username=cleaned["username"],
            email=cleaned["email"],
            first_name=cleaned["first_name"],
            last_name=cleaned.get("last_name", ""),
            password=cleaned["password"],
            phone=cleaned.get("phone", ""),
            image=cleaned.get("image"),
            subjects=list(cleaned.get("subjects", [])),
            position=cleaned.get("position") or "Тренер",
            experience_years=cleaned.get("experience_years", 0),
            bio=cleaned.get("bio", ""),
            hire_date=cleaned.get("hire_date"),
            is_active=cleaned.get("is_active", True),
        )
        self._pending_creation_result = result
        # Subjects were already applied inside create_teacher(); the admin
        # machinery still calls form.save_m2m() after save_related(), and
        # since we bypassed form.save() entirely (create_teacher() does its
        # own atomic save), that attribute was never set — make it a no-op.
        form.save_m2m = lambda: None
        return result.teacher

    def response_add(self, request, obj, post_url_continue=None):
        result = getattr(self, "_pending_creation_result", None)
        if result is not None:
            if result.email_sent:
                messages.success(
                    request,
                    f"Тренер «{obj.user.get_full_name() or obj.user.username}» создан, "
                    f"учётные данные отправлены на {obj.user.email}.",
                )
            else:
                messages.warning(
                    request,
                    f"Тренер создан, но письмо с учётными данными не отправлено "
                    f"({result.email_error}). Используйте «Изменить пароль и отправить».",
                )
        return super().response_add(request, obj, post_url_continue)

    # -- Custom "change password and send" page -----------------------

    def get_urls(self):
        custom_urls = [
            path(
                "<int:teacher_id>/change-password/",
                self.admin_site.admin_view(self.change_password_view),
                name="users_teacher_change_password",
            ),
        ]
        return custom_urls + super().get_urls()

    def change_password_view(self, request, teacher_id):
        teacher = get_object_or_404(Teacher.objects.select_related("user"), pk=teacher_id)

        if request.method == "POST":
            form = ChangeTeacherPasswordForm(request.POST, teacher=teacher)
            if form.is_valid():
                new_password = form.cleaned_data["new_password"]
                result = change_teacher_password_and_send(teacher, new_password)
                if result.email_sent:
                    self.message_user(
                        request,
                        f"Пароль изменён, новые данные отправлены на {teacher.user.email}.",
                        messages.SUCCESS,
                    )
                else:
                    self.message_user(
                        request,
                        f"Пароль изменён, но письмо не отправлено ({result.email_error}).",
                        messages.WARNING,
                    )
                return redirect(reverse("admin:users_teacher_changelist"))
        else:
            form = ChangeTeacherPasswordForm(teacher=teacher)

        context = {
            **self.admin_site.each_context(request),
            "title": f"Изменить пароль — {teacher.user.get_full_name() or teacher.user.username}",
            "teacher": teacher,
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/users/change_teacher_password.html", context)

    # -- Actions ------------------------------------------------------

    @admin.action(description="Подтвердить аккаунт(ы)")
    def verify_accounts(self, request, queryset):
        updated = 0
        for teacher in queryset.select_related("user"):
            if not teacher.user.is_verified:
                teacher.user.is_verified = True
                teacher.user.save(update_fields=["is_verified", "updated_at"])
                updated += 1
        self.message_user(request, f"Подтверждено аккаунтов: {updated}.", messages.SUCCESS)

    @admin.action(description="Деактивировать тренера(ов)")
    def deactivate_trainers(self, request, queryset):
        updated = 0
        for teacher in queryset.select_related("user"):
            teacher.is_active = False
            teacher.user.is_active = False
            teacher.user.save(update_fields=["is_active", "updated_at"])
            teacher.save(update_fields=["is_active", "updated_at"])
            updated += 1
        self.message_user(request, f"Деактивировано: {updated}.", messages.SUCCESS)



from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
admin.site.unregister(Group)