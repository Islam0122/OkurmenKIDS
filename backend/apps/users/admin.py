from __future__ import annotations

import secrets
import string

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .import_export.formats import UnsupportedFileFormat
from .import_export.subjects import export_subjects
from .import_export.teachers import (
    TeacherImportValidationError,
    export_teachers,
    import_teachers,
    preview_teachers_import,
)
from .models import Subject, Teacher, User
from .services import change_teacher_password_and_send, create_teacher

admin.site.unregister(Group)


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
        return format_html(
            '<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label
        )

    @admin.display(description="Статус")
    def active_badge(self, obj: User) -> str:
        css = "ok-badge-success" if obj.is_active else "ok-badge-danger"
        label = "Активен" if obj.is_active else "Деактивирован"
        return format_html(
            '<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label
        )


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "description_short",
        "teachers_count",
        "active_badge",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    ordering = ("name",)
    readonly_fields = (
        "created_at",
        "updated_at",
        "teachers_count_detail",
    )
    list_per_page = 25
    actions = (
        "activate_subjects",
        "deactivate_subjects",
        "export_selected_csv",
    )
    change_list_template = "admin/users/subject/change_list.html"

    fieldsets = (
        (
            "Основная информация",
            {
                "fields": (
                    "name",
                    "description",
                    "is_active",
                ),
            },
        ),
        (
            "Статистика",
            {
                "fields": ("teachers_count_detail",),
            },
        ),
        (
            "Системная информация",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .annotate(teachers_count=Count("teachers", distinct=True))
        )

    @admin.display(description="Описание")
    def description_short(self, obj: Subject) -> str:
        if not obj.description:
            return "—"
        if len(obj.description) > 60:
            return f"{obj.description[:60]}..."
        return obj.description

    @admin.display(description="Тренеры", ordering="teachers_count")
    def teachers_count(self, obj: Subject) -> int:
        return getattr(obj, "teachers_count", 0)

    @admin.display(description="Тренеры")
    def teachers_count_detail(self, obj: Subject) -> str:
        if not obj.pk:
            return "0"
        count = getattr(obj, "teachers_count", None)
        if count is None:
            count = obj.teachers.count()
        return str(count)

    @admin.display(description="Статус", ordering="is_active")
    def active_badge(self, obj: Subject) -> str:
        css = "ok-badge-success" if obj.is_active else "ok-badge-danger"
        label = "Активен" if obj.is_active else "Неактивен"

        return format_html(
            '<span class="ok-badge {}">'
            '<span class="ok-badge-dot"></span>{}'
            "</span>",
            css,
            label,
        )

    @admin.action(description="Активировать выбранные предметы")
    def activate_subjects(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Активировано предметов: {updated}.")

    @admin.action(description="Деактивировать выбранные предметы")
    def deactivate_subjects(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"Деактивировано предметов: {updated}.")

    @admin.action(description="Экспортировать выбранные предметы (CSV)")
    def export_selected_csv(self, request, queryset):
        return export_subjects(queryset, "csv")

    def get_urls(self):
        custom_urls = [
            path("export/", self.admin_site.admin_view(self.export_view), name="users_subject_export"),
        ]
        return custom_urls + super().get_urls()

    def export_view(self, request):
        fmt = request.GET.get("format", "csv")
        # ChangeList treats every unrecognized GET param as a field lookup,
        # so `?format=` (ours, not a filter) has to be stripped before it
        # builds the queryset or it 500s trying to filter by a "format" field.
        original_get = request.GET
        request.GET = original_get.copy()
        request.GET.pop("format", None)
        try:
            changelist = self.get_changelist_instance(request)
            queryset = changelist.get_queryset(request)
        finally:
            request.GET = original_get
        try:
            return export_subjects(queryset, fmt)
        except UnsupportedFileFormat as exc:
            self.message_user(request, str(exc), messages.ERROR)
            return redirect(reverse("admin:users_subject_changelist"))


class AddTrainerForm(forms.ModelForm):
    first_name = forms.CharField(
        label="Имя",
        max_length=100,
        widget=forms.TextInput(attrs={"placeholder": "Иван", "class": "ok-input"}),
    )
    last_name = forms.CharField(
        label="Фамилия",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Иванов", "class": "ok-input"}),
    )
    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"placeholder": "teacher@okurmen.kg", "class": "ok-input"}),
    )
    username = forms.CharField(
        label="Логин (необязательно)",
        max_length=150,
        required=False,
        help_text="Если оставить пустым, сгенерируется из Email",
        widget=forms.TextInput(attrs={"placeholder": "Автовычисление...", "class": "ok-input"}),
    )
    password = forms.CharField(
        label="Пароль (необязательно)",
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Автогенерация...", "class": "ok-input"}),
        help_text="Оставьте пустым — сгенерируется автоматически",
    )

    subjects = forms.ModelMultipleChoiceField(
        queryset=Subject.objects.none(),
        required=False,
        label="Предметы",
        widget=forms.SelectMultiple(
            attrs={
                "class": "ok-subject-select",
                "data-placeholder": "Поиск и выбор предметов...",
            }
        ),
    )

    class Meta:
        model = Teacher
        fields = [
            "phone",
            "position",
            "experience_years",
            "hire_date",
            "image",
            "is_active",
            "bio",
        ]
        widgets = {
            "phone": forms.TextInput(attrs={"placeholder": "+996 (555) 00-00-00", "class": "ok-input"}),
            "position": forms.TextInput(attrs={"placeholder": "Senior Trainer", "class": "ok-input"}),
            "experience_years": forms.NumberInput(attrs={"class": "ok-input", "min": 0}),
            "hire_date": forms.DateInput(attrs={"type": "date", "class": "ok-input"}),
            "bio": forms.Textarea(attrs={"rows": 3, "class": "ok-input", "placeholder": "Краткая биография..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["subjects"].queryset = Subject.objects.filter(is_active=True)
        self.fields["position"].initial = "Тренер"
        self.fields["experience_years"].initial = 1
        self.fields["hire_date"].initial = timezone.now().date()

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Пользователь с таким email уже существует.")
        return email

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if username and User.objects.filter(username=username).exists():
            raise forms.ValidationError("Пользователь с таким логином уже существует.")
        return username

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        username = cleaned.get("username")
        password = cleaned.get("password")

        if email and not username:
            base_username = email.split("@")[0]
            candidate = base_username
            counter = 1
            while User.objects.filter(username=candidate).exists():
                candidate = f"{base_username}{counter}"
                counter += 1
            cleaned["username"] = candidate

        if not password:
            alphabet = string.ascii_letters + string.digits
            cleaned["password"] = "".join(secrets.choice(alphabet) for _ in range(10))
        else:
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


class SubjectMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj: Subject) -> str:
        return obj.name


class ChangeTrainerForm(forms.ModelForm):
    subjects = SubjectMultipleChoiceField(
        queryset=Subject.objects.none(),
        required=False,
        label="Предметы",
        widget=forms.SelectMultiple(
            attrs={
                "class": "ok-subject-select",
                "data-placeholder": "Поиск и выбор предметов...",
            }
        ),
    )

    class Meta:
        model = Teacher
        fields = [
            "position",
            "subjects",
            "experience_years",
            "bio",
            "phone",
            "image",
            "hire_date",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_subjects = Subject.objects.filter(is_active=True)
        if self.instance and self.instance.pk:
            current_subjects = self.instance.subjects.all()
            self.fields["subjects"].queryset = (active_subjects | current_subjects).distinct()
        else:
            self.fields["subjects"].queryset = active_subjects


class TeacherImportForm(forms.Form):
    file = forms.FileField(
        label="Файл (CSV или XLSX)",
        widget=forms.ClearableFileInput(attrs={"class": "ok-input"}),
    )


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
        "avatar_and_name",
        "email_link",
        "subjects_badges",
        "verified_badge",
        "active_badge",
        "schedule_link",
        "change_password_link",
    )
    list_display_links = ("avatar_and_name",)
    list_filter = ("is_active", "user__is_verified", "subjects")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name", "phone")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 20
    actions = ["verify_accounts", "deactivate_trainers", "export_selected_csv"]
    add_form_template = "admin/users/add_teacher.html"
    change_list_template = "admin/users/teacher/change_list.html"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("user")
            .prefetch_related("subjects")
        )

    add_fieldsets = (
        (
            "Личные и контактные данные",
            {
                "fields": ("first_name", "last_name", "email", "phone"),
            },
        ),
        (
            "Специализация и опыт",
            {
                "fields": (
                    "subjects",
                    "position",
                    "experience_years",
                    "hire_date",
                ),
            },
        ),
        (
            "Учётная запись",
            {
                "description": "Логин и пароль сгенерируются автоматически, если оставить их пустыми.",
                "fields": ("username", "password"),
            },
        ),
        (
            "Дополнительно",
            {
                "classes": ("collapse",),
                "fields": ("image", "is_active", "bio"),
            },
        ),
    )

    fieldsets = (
        (
            "Основное",
            {
                "fields": (
                    "user",
                    "phone",
                    "position",
                    "experience_years",
                    "hire_date",
                ),
            },
        ),
        (
            "Предметы и инфо",
            {
                "fields": ("subjects", "image", "is_active", "bio"),
            },
        ),
    )

    def get_fieldsets(self, request, obj=None):
        if not obj:
            return self.add_fieldsets
        return super().get_fieldsets(request, obj)

    @admin.display(description="Тренер", ordering="user__first_name")
    def avatar_and_name(self, obj: Teacher) -> str:
        name = obj.user.get_full_name() or obj.user.username
        if obj.image:
            img_html = format_html(
                '<img src="{}" class="ok-person-avatar" style="width:34px; height:34px;" />',
                obj.image.url,
            )
        else:
            initial = name[0].upper() if name else "T"
            img_html = format_html(
                '<div class="ok-person-avatar" style="width:34px; height:34px; font-size:0.85rem;">{}</div>',
                initial,
            )

        return format_html(
            '<div style="display:flex; align-items:center; gap:0.75rem;">'
            "{}"
            '<div style="display:flex; flex-direction:column;">'
            '<span style="font-weight:600; color:var(--ok-text);">{}</span>'
            '<span style="font-size:0.75rem; color:var(--ok-text-muted);">@{}</span>'
            "</div>"
            "</div>",
            img_html,
            name,
            obj.user.username,
        )

    @admin.display(description="Email", ordering="user__email")
    def email_link(self, obj: Teacher) -> str:
        if not obj.user.email:
            return "—"
        return format_html(
            '<a href="mailto:{}" style="color:var(--ok-text-secondary); text-decoration:none;">'
            '<i class="bi bi-envelope" style="margin-right:4px;"></i>{}'
            '</a>',
            obj.user.email,
            obj.user.email,
        )

    @admin.display(description="Предметы")
    def subjects_badges(self, obj: Teacher) -> str:
        subjects = list(obj.subjects.all())
        if not subjects:
            return format_html(
                '<span style="color:var(--ok-text-muted); font-size:0.8rem;">{}</span>', "—"
            )

        max_show = 2
        visible = subjects[:max_show]
        more_count = len(subjects) - max_show

        badges_list = [
            format_html('<span class="ok-chip">{}</span>', s.name) for s in visible
        ]

        if more_count > 0:
            badges_list.append(
                format_html('<span class="ok-chip-more">+{}</span>', more_count)
            )

        return mark_safe("".join(badges_list))

    @admin.display(description="Подтверждён", ordering="user__is_verified")
    def verified_badge(self, obj: Teacher) -> str:
        css = "ok-badge-success" if obj.user.is_verified else "ok-badge-warning"
        label = "Подтверждён" if obj.user.is_verified else "Ожидает"
        return format_html(
            '<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>',
            css,
            label,
        )

    @admin.display(description="Статус", ordering="is_active")
    def active_badge(self, obj: Teacher) -> str:
        css = "ok-badge-success" if obj.is_active else "ok-badge-danger"
        label = "Активен" if obj.is_active else "Деактивирован"
        return format_html(
            '<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>',
            css,
            label,
        )

    @admin.display(description="Расписание")
    def schedule_link(self, obj: Teacher) -> str:
        # academy.admin_views.schedule_view — schedule has no model of its
        # own, so it's reached by URL name rather than a cross-app import.
        url = f"{reverse('admin:academy_schedule')}?teacher={obj.pk}"
        return format_html(
            '<a class="btn btn-secondary" style="padding:0.25rem 0.6rem; font-size:0.75rem; display:inline-flex; align-items:center; gap:0.3rem;" href="{}">'
            '<i class="bi bi-calendar-week"></i>Расписание</a>',
            url,
        )

    @admin.display(description="Действия")
    def change_password_link(self, obj: Teacher) -> str:
        url = reverse("admin:users_teacher_change_password", args=[obj.pk])
        return format_html(
            '<a class="btn btn-secondary" style="padding:0.25rem 0.6rem; font-size:0.75rem; display:inline-flex; align-items:center; gap:0.3rem;" href="{}">'
            '<i class="bi bi-key"></i>Пароль</a>',
            url,
        )

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            kwargs["form"] = AddTrainerForm
        else:
            kwargs["form"] = ChangeTrainerForm
        return super().get_form(request, obj, **kwargs)

    def save_form(self, request, form, change):
        if change:
            return super().save_form(request, form, change)

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
        form.save_m2m = lambda: None
        return result.teacher

    def response_add(self, request, obj, post_url_continue=None):
        result = getattr(self, "_pending_creation_result", None)
        if result is not None:
            if result.email_sent:
                messages.success(
                    request,
                    f"Тренер «{obj.user.get_full_name() or obj.user.username}» успешно создан, "
                    f"учётные данные отправлены на {obj.user.email}.",
                )
            else:
                messages.warning(
                    request,
                    f"Тренер создан, но письмо с учётными данными не отправлено "
                    f"({result.email_error}). Используйте кнопку «Пароль» для повторной отправки.",
                )
        return super().response_add(request, obj, post_url_continue)

    def get_urls(self):
        custom_urls = [
            path(
                "<path:teacher_id>/change-password/",
                self.admin_site.admin_view(self.change_password_view),
                name="users_teacher_change_password",
            ),
            path("import/", self.admin_site.admin_view(self.import_view), name="users_teacher_import"),
            path("export/", self.admin_site.admin_view(self.export_view), name="users_teacher_export"),
        ]
        return custom_urls + super().get_urls()

    @admin.action(description="Экспортировать выбранных тренеров (CSV)")
    def export_selected_csv(self, request, queryset):
        return export_teachers(queryset, "csv")

    def export_view(self, request):
        fmt = request.GET.get("format", "csv")
        # ChangeList treats every unrecognized GET param as a field lookup,
        # so `?format=` (ours, not a filter) has to be stripped before it
        # builds the queryset or it 500s trying to filter by a "format" field.
        original_get = request.GET
        request.GET = original_get.copy()
        request.GET.pop("format", None)
        try:
            changelist = self.get_changelist_instance(request)
            queryset = changelist.get_queryset(request)
        finally:
            request.GET = original_get
        try:
            return export_teachers(queryset, fmt)
        except UnsupportedFileFormat as exc:
            self.message_user(request, str(exc), messages.ERROR)
            return redirect(reverse("admin:users_teacher_changelist"))

    def import_view(self, request):
        preview = None
        failed = False

        if request.method == "POST":
            form = TeacherImportForm(request.POST, request.FILES)
            if form.is_valid():
                file_obj = form.cleaned_data["file"]
                if "preview" in request.POST:
                    try:
                        preview = preview_teachers_import(file_obj)
                    except UnsupportedFileFormat as exc:
                        messages.error(request, str(exc))
                else:
                    try:
                        result = import_teachers(file_obj)
                    except UnsupportedFileFormat as exc:
                        messages.error(request, str(exc))
                    except TeacherImportValidationError as exc:
                        preview = exc.preview
                        failed = True
                    else:
                        messages.success(
                            request,
                            f"Импорт завершён: создано {result.created}, обновлено {result.updated} "
                            f"из {result.total} тренеров.",
                        )
                        return redirect(reverse("admin:users_teacher_changelist"))
        else:
            form = TeacherImportForm()

        context = {
            **self.admin_site.each_context(request),
            "title": "Импорт тренеров",
            "opts": self.model._meta,
            "form": form,
            "preview": preview,
            "failed": failed,
            "export_fields": (
                "username, email, first_name, last_name, phone, position, experience_years, "
                "bio, hire_date, subjects, is_active, is_verified"
            ),
            "changelist_url": reverse("admin:users_teacher_changelist"),
        }
        return render(request, "admin/users/teacher_import.html", context)

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
        self.message_user(request, f"Деактивировано тренеров: {updated}.", messages.SUCCESS)