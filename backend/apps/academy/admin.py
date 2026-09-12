from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.data_io.admin_mixin import TemplatedIOAdminMixin
from apps.users.import_export.formats import UnsupportedFileFormat, is_valid_phone

from .admin_views import (
    analytics_view,
    generate_lessons_for_group_view,
    group_teacher_workspace_view,
    group_workspace_add_existing_students_view,
    group_workspace_add_program_view,
    group_workspace_add_schedule_view,
    group_workspace_add_student_view,
    group_workspace_add_teacher_view,
    group_workspace_analytics_view,
    group_workspace_attendance_view,
    group_workspace_generate_lessons_view,
    group_workspace_homework_view,
    group_workspace_lessons_view,
    group_workspace_overview_view,
    group_workspace_programs_view,
    group_workspace_remove_schedule_view,
    group_workspace_remove_student_view,
    group_workspace_remove_teacher_view,
    group_workspace_schedule_view,
    group_workspace_students_view,
    group_workspace_teachers_view,
    schedule_view,
)
from .models import (
    Attendance,
    Course,
    CourseLessonPlan,
    Group,
    GroupTeacher,
    GroupTeacherLessonPlan,
    Homework,
    HomeworkResult,
    Lesson,
    Room,
    Student,
)
from .services.import_export import (
    StudentImportValidationError,
    build_student_import_template,
    export_students,
    import_students,
    preview_students_import_rows,
)
from .services.lesson_generator import LessonGenerationError, generate_lessons_for_group
from .widgets import SubjectCardsWidget


def _badge(css: str, label: str) -> str:
    return format_html('<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label)


# ---------------------------------------------------------------------------
# Course catalogue
# ---------------------------------------------------------------------------

class CourseAdminForm(forms.ModelForm):
    """Only swaps the ``subjects`` widget — everything else about the form
    (validation, ``save()``, the M2M write) stays exactly what
    ``ModelForm``/``ModelAdmin`` already do for a plain ``ManyToManyField``.
    """

    class Meta:
        model = Course
        fields = "__all__"
        widgets = {
            # "select2-hidden-accessible" isn't ours — it's the exact class
            # Jazzmin's own change_form.js checks for (`noSelect2` in
            # jazzmin/static/jazzmin/js/change_form.js) to skip a <select>
            # it would otherwise auto-upgrade with Select2. Setting it
            # up front (rather than after the fact) stops that from ever
            # running on this field, since jazzmin's check happens on
            # page load against whatever classes are already in the HTML.
            "subjects": SubjectCardsWidget(attrs={"class": "ok-subject-cards-source select2-hidden-accessible"}),
        }


@admin.register(Course)
class CourseAdmin(TemplatedIOAdminMixin, admin.ModelAdmin):
    io_adapter_key = "academy.course"
    form = CourseAdminForm
    list_display = ("name", "count_lesson", "subjects_list", "lesson_plans_progress", "created_at")
    search_fields = ("name", "description")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 25
    actions = ["export_selected_csv"]
    change_list_template = "admin/academy/course/change_list.html"

    fieldsets = (
        ("Основная информация", {"fields": ("name", "count_lesson", "subjects", "description")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        # Django admin always appends "Hold down Control..." to any
        # SelectMultiple-based widget's help text (see ModelAdmin.
        # formfield_for_dbfield) — meaningless for a click-to-toggle card
        # grid, so put the model field's own help text back afterwards.
        formfield = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == "subjects" and formfield is not None:
            formfield.help_text = db_field.help_text
        return formfield

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .prefetch_related("subjects")
            .annotate(_lesson_plans_count=Count("lesson_plans", distinct=True))
        )

    @admin.display(description="Предметы")
    def subjects_list(self, obj: Course) -> str:
        names = [s.name for s in obj.subjects.all()]
        return ", ".join(names) if names else "—"

    @admin.display(description="План занятий")
    def lesson_plans_progress(self, obj: Course) -> str:
        planned = getattr(obj, "_lesson_plans_count", 0)
        css = "ok-badge-success" if planned == obj.count_lesson and planned > 0 else "ok-badge-warning"
        return _badge(css, f"{planned} / {obj.count_lesson}")


@admin.register(CourseLessonPlan)
class CourseLessonPlanAdmin(TemplatedIOAdminMixin, admin.ModelAdmin):
    io_adapter_key = "academy.courselessonplan"
    list_display = ("course", "lesson_number", "subject", "topic", "homework_badge")
    list_filter = ("course", "subject")
    search_fields = ("topic", "description", "course__name")
    ordering = ("course", "lesson_number")
    autocomplete_fields = ("course", "subject")
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 30
    actions = ["export_selected_csv"]
    change_list_template = "admin/academy/courselessonplan/change_list.html"

    fieldsets = (
        ("Расположение", {"fields": ("course", "lesson_number", "subject")}),
        ("Содержание", {"fields": ("topic", "description", "youtube_url", "presentation_urls")}),
        ("Домашнее задание", {"fields": ("homework_title", "homework_description")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("course", "subject")

    @admin.display(description="ДЗ задано")
    def homework_badge(self, obj: CourseLessonPlan) -> str:
        return _badge("ok-badge-success", "Да") if obj.homework_title else _badge("ok-badge-muted", "Нет")


# ---------------------------------------------------------------------------
# Rooms & students
# ---------------------------------------------------------------------------

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "capacity", "active_badge", "schedule_link", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at", "schedule_link_detail")
    list_per_page = 25

    fieldsets = (
        ("Основная информация", {"fields": ("name", "capacity", "description", "is_active")}),
        ("Расписание", {"fields": ("schedule_link_detail",)}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Статус", ordering="is_active")
    def active_badge(self, obj: Room) -> str:
        return _badge("ok-badge-success", "Активна") if obj.is_active else _badge("ok-badge-danger", "Неактивна")

    @admin.display(description="Расписание")
    def schedule_link(self, obj: Room) -> str:
        if not obj.pk:
            return "—"
        url = f"{reverse('admin:academy_schedule')}?room={obj.pk}"
        return format_html('<a class="btn btn-outline-success btn-sm" href="{}">Расписание аудитории</a>', url)

    @admin.display(description="Расписание аудитории")
    def schedule_link_detail(self, obj: Room) -> str:
        if not obj.pk:
            return "Появится после сохранения аудитории."
        return self.schedule_link(obj)


class StudentImportForm(forms.Form):
    file = forms.FileField(
        label="Файл (CSV или XLSX)",
        widget=forms.ClearableFileInput(attrs={"class": "ok-input"}),
    )


class StudentBulkRowForm(forms.Form):
    """One row of the bulk-add table (spec §10). Every field is optional at
    the Django field level on purpose: a required first_name would make
    Django reject a trailing blank row before clean() ever gets a chance to
    tell "intentionally empty" apart from "filled in but invalid" — the
    distinction the whole feature depends on (empty rows are silently
    skipped, filled-but-broken rows are a real, row-numbered error)."""

    first_name = forms.CharField(
        max_length=100, required=False, label="Имя студента",
        widget=forms.TextInput(attrs={"class": "ok-input", "placeholder": "Имя"}),
    )
    last_name = forms.CharField(
        max_length=100, required=False, label="Фамилия",
        widget=forms.TextInput(attrs={"class": "ok-input", "placeholder": "Фамилия"}),
    )
    phone = forms.CharField(
        max_length=30, required=False, label="Телефон",
        widget=forms.TextInput(attrs={"class": "ok-input", "placeholder": "Телефон"}),
    )
    group = forms.ModelChoiceField(
        queryset=Group.objects.all(), required=False, label="Группа",
        widget=forms.Select(attrs={"class": "ok-input"}),
    )
    is_active = forms.BooleanField(required=False, initial=True, label="Активен")

    def clean(self):
        cleaned = super().clean()
        first_name = (cleaned.get("first_name") or "").strip()
        last_name = (cleaned.get("last_name") or "").strip()
        phone = (cleaned.get("phone") or "").strip()
        group = cleaned.get("group")
        cleaned["first_name"] = first_name
        cleaned["last_name"] = last_name
        cleaned["phone"] = phone

        if not first_name and not last_name and not phone and group is None:
            cleaned["_blank"] = True
            return cleaned
        cleaned["_blank"] = False

        if not first_name:
            raise forms.ValidationError("Имя обязательно для заполненной строки.")
        if phone and not is_valid_phone(phone):
            raise forms.ValidationError(f"Некорректный номер телефона «{phone}».")
        return cleaned


class StudentBulkFormSet(forms.BaseFormSet):
    def clean(self):
        if any(self.errors):
            return
        seen = set()
        for form in self.forms:
            data = getattr(form, "cleaned_data", None) or {}
            if data.get("_blank", True):
                continue
            key = (data["first_name"].lower(), data["last_name"].lower(), data["phone"])
            if key in seen:
                raise forms.ValidationError(
                    f'Повторяющаяся строка: «{data["first_name"]} {data["last_name"]}». '
                    "Уберите дубликат или измените данные, чтобы продолжить."
                )
            seen.add(key)


StudentBulkFormSetFactory = forms.formset_factory(
    StudentBulkRowForm, formset=StudentBulkFormSet, extra=3, can_delete=False
)


class StudentAssignGroupForm(forms.Form):
    group = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=False,
        label="Группа",
        help_text="Оставьте пустым, чтобы снять выбранных студентов с текущей группы.",
        widget=forms.Select(attrs={"class": "ok-input"}),
    )


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("student_column", "group_column", "phone", "active_badge", "created_at", "row_actions")
    list_filter = ("group", "is_active")
    search_fields = ("first_name", "last_name", "phone", "parent_phone")
    ordering = ("last_name", "first_name")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("group",)
    list_per_page = 25
    actions = ["activate_students", "deactivate_students", "assign_group_action", "export_selected_csv"]
    change_list_template = "admin/academy/student/change_list.html"

    fieldsets = (
        ("Основная информация", {"fields": ("first_name", "last_name", "group", "is_active")}),
        ("Контакты", {"fields": ("phone", "parent_phone")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    # -- students are never hard-deleted from the Admin UI ---------------
    # Attendance/Homework/history must survive forever — see models.Student
    # docstring context in the task spec. Deactivation (is_active=False) is
    # the only supported removal path; has_delete_permission=False alone
    # already makes Django hide every delete surface it renders (the
    # "Delete" object-tool, the delete_selected bulk action, and the
    # /delete/ confirmation route itself all gate on this one check) — the
    # two method overrides below are pure defense in depth in case anything
    # ever calls them directly.

    def has_delete_permission(self, request, obj=None):
        return False

    def delete_model(self, request, obj):
        raise PermissionDenied("Удаление студентов запрещено. Используйте деактивацию.")

    def delete_queryset(self, request, queryset):
        raise PermissionDenied("Удаление студентов запрещено. Используйте деактивацию.")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("group")

    # -- list columns -----------------------------------------------------

    @admin.display(description="Студент", ordering="last_name")
    def student_column(self, obj: Student) -> str:
        initials = (
            (obj.first_name[:1] if obj.first_name else "") + (obj.last_name[:1] if obj.last_name else "")
        ).upper() or "?"
        name = f"{obj.first_name} {obj.last_name}".strip()
        url = reverse("admin:academy_student_detail", args=[obj.pk])
        return format_html(
            '<a class="ok-student-row-link" href="{}">'
            '<span class="ok-student-avatar ok-person-avatar">{}</span>'
            '<span class="ok-student-name">{}</span>'
            "</a>",
            url, initials, name,
        )

    @admin.display(description="Группа", ordering="group__name")
    def group_column(self, obj: Student) -> str:
        if not obj.group_id:
            return _badge("ok-badge-muted", "Без группы")
        url = reverse("admin:academy_group_change", args=[obj.group_id])
        return format_html('<a class="ok-student-group" href="{}">{}</a>', url, obj.group.name)

    @admin.display(description="Статус", ordering="is_active")
    def active_badge(self, obj: Student) -> str:
        return _badge("ok-badge-success", "Активен") if obj.is_active else _badge("ok-badge-danger", "Неактивен")

    @admin.display(description="")
    def row_actions(self, obj: Student) -> str:
        detail_url = reverse("admin:academy_student_detail", args=[obj.pk])
        edit_url = reverse("admin:academy_student_change", args=[obj.pk])
        return format_html(
            '<div class="ok-student-actions">'
            '<a class="ok-btn-secondary ok-btn-sm" href="{}" title="Профиль"><i class="bi bi-eye"></i></a>'
            '<a class="ok-btn-secondary ok-btn-sm" href="{}" title="Изменить"><i class="bi bi-pencil"></i></a>'
            "</div>",
            detail_url, edit_url,
        )

    # -- bulk actions (safe: no hard delete among them) -------------------

    @admin.action(description="Экспортировать выбранных студентов (CSV)")
    def export_selected_csv(self, request, queryset):
        return export_students(queryset, "csv")

    @admin.action(description="Активировать выбранных студентов")
    def activate_students(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"Активировано студентов: {updated}.", messages.SUCCESS)

    @admin.action(description="Деактивировать выбранных студентов")
    def deactivate_students(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            f"Деактивировано студентов: {updated}. Посещаемость, домашние задания и история сохранены.",
            messages.SUCCESS,
        )

    @admin.action(description="Назначить группу выбранным студентам")
    def assign_group_action(self, request, queryset):
        ids = ",".join(str(pk) for pk in queryset.values_list("pk", flat=True))
        return redirect(f"{reverse('admin:academy_student_assign_group')}?ids={ids}")

    def get_urls(self):
        custom_urls = [
            path("import/", self.admin_site.admin_view(self.import_view), name="academy_student_import"),
            path("export/", self.admin_site.admin_view(self.export_view), name="academy_student_export"),
            path("template/", self.admin_site.admin_view(self.template_view), name="academy_student_template"),
            path("bulk-add/", self.admin_site.admin_view(self.bulk_add_view), name="academy_student_bulk_add"),
            path(
                "assign-group/",
                self.admin_site.admin_view(self.assign_group_view),
                name="academy_student_assign_group",
            ),
            path(
                "<int:student_id>/detail/",
                self.admin_site.admin_view(self.detail_view),
                name="academy_student_detail",
            ),
            path(
                "<int:student_id>/toggle-active/",
                self.admin_site.admin_view(self.toggle_active_view),
                name="academy_student_toggle_active",
            ),
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
            return export_students(queryset, fmt)
        except UnsupportedFileFormat as exc:
            self.message_user(request, str(exc), messages.ERROR)
            return redirect(reverse("admin:academy_student_changelist"))

    def template_view(self, request):
        return build_student_import_template()

    def import_view(self, request):
        preview = None
        preview_rows = None
        failed = False

        if request.method == "POST":
            form = StudentImportForm(request.POST, request.FILES)
            if form.is_valid():
                file_obj = form.cleaned_data["file"]
                if "preview" in request.POST:
                    try:
                        preview_rows, preview = preview_students_import_rows(file_obj)
                    except UnsupportedFileFormat as exc:
                        messages.error(request, str(exc))
                else:
                    try:
                        file_obj.seek(0)
                        result = import_students(file_obj)
                    except UnsupportedFileFormat as exc:
                        messages.error(request, str(exc))
                    except StudentImportValidationError as exc:
                        preview = exc.preview
                        failed = True
                        try:
                            file_obj.seek(0)
                            preview_rows, _ = preview_students_import_rows(file_obj)
                        except UnsupportedFileFormat:
                            preview_rows = None
                    else:
                        messages.success(
                            request,
                            f"Импорт завершён: создано {result.created}, обновлено {result.updated} "
                            f"из {result.total} студентов.",
                        )
                        return redirect(reverse("admin:academy_student_changelist"))
        else:
            form = StudentImportForm()

        context = {
            **self.admin_site.each_context(request),
            "title": "Импорт студентов",
            "opts": self.model._meta,
            "form": form,
            "preview": preview,
            "preview_rows": preview_rows,
            "failed": failed,
            "export_fields": "id, first_name, last_name, phone, parent_phone, group, is_active",
            "changelist_url": reverse("admin:academy_student_changelist"),
            "template_url": reverse("admin:academy_student_template"),
        }
        return render(request, "admin/academy/student_import.html", context)

    def bulk_add_view(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied

        created_count = None
        if request.method == "POST":
            formset = StudentBulkFormSetFactory(request.POST)
            if formset.is_valid():
                rows_to_create = [
                    form.cleaned_data for form in formset.forms if not form.cleaned_data.get("_blank", True)
                ]
                if rows_to_create:
                    with transaction.atomic():
                        for data in rows_to_create:
                            student = Student(
                                first_name=data["first_name"],
                                last_name=data["last_name"],
                                phone=data["phone"],
                                group=data.get("group"),
                                is_active=data.get("is_active", True),
                            )
                            student.full_clean()
                            student.save()
                    self.message_user(
                        request, f"Добавлено студентов: {len(rows_to_create)}.", messages.SUCCESS
                    )
                    return redirect(reverse("admin:academy_student_changelist"))
                messages.warning(request, "Не добавлено ни одного студента — все строки были пустыми.")
        else:
            formset = StudentBulkFormSetFactory()

        context = {
            **self.admin_site.each_context(request),
            "title": "Массовое добавление студентов",
            "opts": self.model._meta,
            "formset": formset,
            "created_count": created_count,
            "changelist_url": reverse("admin:academy_student_changelist"),
        }
        return render(request, "admin/academy/student/bulk_add.html", context)

    def assign_group_view(self, request):
        ids_param = request.GET.get("ids") or request.POST.get("ids") or ""
        student_ids = [int(pk) for pk in ids_param.split(",") if pk.strip().isdigit()]
        students = Student.objects.filter(pk__in=student_ids).select_related("group")

        if not students.exists():
            self.message_user(request, "Не выбрано ни одного студента.", messages.WARNING)
            return redirect(reverse("admin:academy_student_changelist"))

        if request.method == "POST":
            form = StudentAssignGroupForm(request.POST)
            if form.is_valid():
                group = form.cleaned_data["group"]
                updated = students.update(group=group)
                label = group.name if group else "Без группы"
                self.message_user(request, f'Группа «{label}» назначена студентам: {updated}.', messages.SUCCESS)
                return redirect(reverse("admin:academy_student_changelist"))
        else:
            form = StudentAssignGroupForm()

        context = {
            **self.admin_site.each_context(request),
            "title": "Назначить группу",
            "opts": self.model._meta,
            "form": form,
            "students": students,
            "ids": ids_param,
            "changelist_url": reverse("admin:academy_student_changelist"),
        }
        return render(request, "admin/academy/student/assign_group.html", context)

    def detail_view(self, request, student_id):
        student = get_object_or_404(Student.objects.select_related("group__course"), pk=student_id)

        attendance_qs = Attendance.objects.filter(student=student)
        attendance_total = attendance_qs.count()
        attendance_present = attendance_qs.filter(status=Attendance.Status.PRESENT).count()
        attendance_pct = round(100 * attendance_present / attendance_total, 1) if attendance_total else None

        homework_results_qs = HomeworkResult.objects.filter(student=student)
        homework_submitted = homework_results_qs.filter(
            status__in=[
                HomeworkResult.Status.SUBMITTED,
                HomeworkResult.Status.LATE,
                HomeworkResult.Status.CHECKED,
            ]
        ).count()
        homework_checked = homework_results_qs.filter(status=HomeworkResult.Status.CHECKED).count()
        homework_assigned = (
            Homework.objects.filter(lesson__group_id=student.group_id).count() if student.group_id else 0
        )
        homework_pending = max(homework_assigned - homework_submitted, 0) if student.group_id else None

        context = {
            **self.admin_site.each_context(request),
            "title": str(student),
            "opts": self.model._meta,
            "student": student,
            "attendance_stats": {
                "total": attendance_total,
                "present": attendance_present,
                "absent": attendance_qs.filter(status=Attendance.Status.ABSENT).count(),
                "late": attendance_qs.filter(status=Attendance.Status.LATE).count(),
                "excused": attendance_qs.filter(status=Attendance.Status.EXCUSED).count(),
                "rate": attendance_pct,
            },
            "homework_stats": {
                "assigned": homework_assigned,
                "submitted": homework_submitted,
                "checked": homework_checked,
                "pending": homework_pending,
            },
            "change_url": reverse("admin:academy_student_change", args=[student.pk]),
            "changelist_url": reverse("admin:academy_student_changelist"),
            "toggle_active_url": reverse("admin:academy_student_toggle_active", args=[student.pk]),
            "attendance_url": (
                f"{reverse('admin:academy_attendance_changelist')}?student__id__exact={student.pk}"
            ),
            "homework_results_url": (
                f"{reverse('admin:academy_homeworkresult_changelist')}?student__id__exact={student.pk}"
            ),
            "group_url": (
                reverse("admin:academy_group_change", args=[student.group_id]) if student.group_id else None
            ),
        }
        return render(request, "admin/academy/student/detail.html", context)

    def toggle_active_view(self, request, student_id):
        student = get_object_or_404(Student, pk=student_id)
        if request.method != "POST" or not self.has_change_permission(request, student):
            raise PermissionDenied

        student.is_active = not student.is_active
        student.save(update_fields=["is_active", "updated_at"])
        if student.is_active:
            self.message_user(request, f"«{student}» активирован.", messages.SUCCESS)
        else:
            self.message_user(
                request,
                f"«{student}» деактивирован. Посещаемость, домашние задания и история сохранены.",
                messages.SUCCESS,
            )
        next_url = request.POST.get("next") or reverse("admin:academy_student_detail", args=[student_id])
        return redirect(next_url)


# ---------------------------------------------------------------------------
# Group — the busiest admin screen: course/teacher/room, schedule, a modern
# student picker, and the "Сгенерировать занятия" action.
# ---------------------------------------------------------------------------

class GroupAdminForm(forms.ModelForm):
    """The Group form now covers only the group's own identity/period/limits
    fields. Students, Teaching Programs and Schedule all moved to the Group
    Workspace (see admin_views.py's group_workspace_* views) — a Group has
    no `students` field of its own (Student.group is the FK, managed from
    the Workspace's Students tab) and schedule rows are no longer an inline
    here (see the Workspace's Schedule tab). teacher/room/start_time/
    end_time/days_of_week are legacy model fields (see their help_text on
    Group) — shown read-only in the "Системная информация" tab via
    GroupAdmin.readonly_fields, never editable here."""

    class Meta:
        model = Group
        fields = "__all__"
        labels = {
            "name": "Название группы",
            "status": "Статус группы",
            "start_date": "Дата начала группы",
            "end_date": "Дата окончания группы",
            "max_students": "Максимальное количество студентов",
        }
        help_texts = {
            "start_date": "Общий период существования группы.",
            "end_date": "Общий период существования группы.",
            "max_students": "Оставьте пустым, если количество студентов не ограничено.",
        }


class GroupTeacherLessonPlanInline(admin.TabularInline):
    """A GroupTeacher's own lesson-by-lesson plan — the per-teacher
    counterpart of CourseLessonPlan (see models.GroupTeacherLessonPlan).
    Empty (no rows) means this teacher keeps using the group's shared
    course plan, exactly as before this feature existed."""

    model = GroupTeacherLessonPlan
    extra = 1
    fields = ("lesson_number", "topic", "homework_title", "description")
    ordering = ("lesson_number",)
    verbose_name = "Занятие плана"
    verbose_name_plural = "Индивидуальный план занятий"


@admin.register(GroupTeacher)
class GroupTeacherAdmin(admin.ModelAdmin):
    """Every Teacher Program of every group, all equally: no field here
    marks one kind of program as more central than another — is_legacy_primary
    is purely historical bookkeeping (see its help_text) and lives in the
    collapsed system-info fieldset, not among the day-to-day fields above."""

    list_display = (
        "group", "teacher", "subject", "active_badge", "plan_progress", "workspace_link", "created_at",
    )
    list_filter = ("is_active", "group", "teacher", "subject")
    search_fields = ("group__name", "teacher__user__first_name", "teacher__user__last_name", "subject__name")
    autocomplete_fields = ("group", "teacher", "subject")
    readonly_fields = ("created_at", "updated_at", "is_legacy_primary", "workspace_link_detail")
    inlines = [GroupTeacherLessonPlanInline]
    ordering = ("group", "id")
    list_per_page = 30

    fieldsets = (
        ("Тренер / программа", {"fields": ("group", "teacher", "subject", "is_active", "workspace_link_detail")}),
        (
            "Системная информация",
            {"fields": ("is_legacy_primary", "created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def get_urls(self):
        custom_urls = [
            path(
                "<int:group_teacher_id>/workspace/",
                self.admin_site.admin_view(group_teacher_workspace_view),
                name="academy_groupteacher_workspace",
            ),
        ]
        return custom_urls + super().get_urls()

    @admin.display(description="Рабочее пространство")
    def workspace_link(self, obj: GroupTeacher) -> str:
        if not obj.pk:
            return "—"
        url = reverse("admin:academy_groupteacher_workspace", args=[obj.pk])
        return format_html(
            '<a class="btn btn-outline-success btn-sm" href="{}">'
            '<i class="bi bi-kanban"></i> Открыть →</a>',
            url,
        )

    @admin.display(description="Рабочее пространство программы")
    def workspace_link_detail(self, obj: GroupTeacher) -> str:
        if not obj.pk:
            return "Появится после сохранения программы."
        return self.workspace_link(obj)

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("group", "teacher__user", "subject")
            .annotate(_plan_count=Count("lesson_plans", distinct=True))
        )

    @admin.display(description="Активен", ordering="is_active")
    def active_badge(self, obj: GroupTeacher) -> str:
        return _badge("ok-badge-success", "Да") if obj.is_active else _badge("ok-badge-danger", "Нет")

    @admin.display(description="План")
    def plan_progress(self, obj: GroupTeacher) -> str:
        count = getattr(obj, "_plan_count", 0)
        if count:
            return _badge("ok-badge-success", f"Свой план: {count}")
        return _badge("ok-badge-muted", "Общий план курса")


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    """A Group is only a container for identity, course, status and general
    period — see module docstring above GroupTeacher in models.py. This
    admin form covers *only* that: students, Teaching Programs and Schedule
    all live in the Group Workspace instead (see admin_views.py's
    group_workspace_* views, wired below via get_urls()) — there is no
    "main teacher"/"main schedule" there either: every program is equally
    first-class.
    """

    form = GroupAdminForm
    list_display = (
        "name", "course", "teacher_programs_summary",
        "students_count_display", "status_badge", "start_date", "end_date", "workspace_link",
    )
    list_filter = ("status", "course", "start_date")
    search_fields = ("name", "teachers__teacher__user__first_name", "teachers__teacher__user__last_name")
    ordering = ("-start_date", "name")
    readonly_fields = (
        "created_at", "updated_at", "capacity_summary", "workspace_summary",
        "teacher", "room", "start_time", "end_time", "days_of_week",
    )
    autocomplete_fields = ("course",)
    actions = ["generate_lessons_action", "pause_groups", "activate_groups"]
    list_per_page = 25

    def get_fieldsets(self, request, obj=None):
        # These "ok-admin-group-tab-*" classes carry no visual meaning to
        # Django/Jazzmin's own fieldset rendering — they're read back out by
        # templates/admin/academy/group/change_form.html, which groups
        # fieldsets sharing a tab class into one tab pane (via {% regroup %}).
        # Fieldsets meant for the same tab must stay contiguous below for
        # that grouping to work. See that template for the tab shell itself.
        tab_main = ("ok-admin-group-section", "ok-admin-group-tab-main")
        tab_limits = ("ok-admin-group-section", "ok-admin-group-tab-limits")
        tab_system = ("ok-admin-group-section", "ok-admin-group-tab-system")

        fieldsets = [
            (
                "Основная информация",
                {
                    "fields": ("name", "course", "status", "description"),
                    "description": "Основные данные учебной группы.",
                    "classes": tab_main,
                },
            ),
        ]
        fieldsets.append(
            ("Рабочее пространство", {"fields": ("workspace_summary",), "classes": tab_main})
        )
        fieldsets += [
            (
                "Период обучения",
                {
                    "fields": ("start_date", "end_date"),
                    "description": "Общий период существования группы.",
                    "classes": tab_main,
                },
            ),
            (
                "Ограничения",
                {
                    "fields": ("max_students", "capacity_summary"),
                    "description": "Максимальное количество студентов в группе.",
                    "classes": tab_limits,
                },
            ),
            (
                "Системная информация",
                {"fields": ("created_at", "updated_at"), "classes": tab_system},
            ),
        ]
        if obj is not None:
            fieldsets.append(
                (
                    "Устаревшие поля",
                    {
                        "fields": ("teacher", "room", "start_time", "end_time", "days_of_week"),
                        "description": (
                            "Оставлены только для совместимости со старыми данными. Не используются "
                            "и не редактируются — реальное расписание задаётся в рабочем пространстве группы."
                        ),
                        "classes": tab_system,
                    },
                )
            )
        return fieldsets

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("course")
            .annotate(
                active_students_count=Count("students", filter=Q(students__is_active=True), distinct=True),
                active_teacher_programs_count=Count(
                    "teachers", filter=Q(teachers__is_active=True), distinct=True
                ),
            )
        )

    def response_add(self, request, obj, post_url_continue=None):
        # Spec: after creating a Group, go straight to its Workspace instead
        # of the usual changelist/"add another" screen — "Save and continue
        # editing" and "Save and add another" are left alone (they're
        # explicit admin intent to keep working the plain form).
        if "_continue" not in request.POST and "_addanother" not in request.POST:
            self.message_user(
                request, f"Группа «{obj}» создана. Открыто рабочее пространство.", messages.SUCCESS
            )
            return redirect(reverse("admin:academy_group_workspace", args=[obj.pk]))
        return super().response_add(request, obj, post_url_continue)

    @admin.display(description="Студенты", ordering="active_students_count")
    def students_count_display(self, obj: Group) -> str:
        count = getattr(obj, "active_students_count", None) or 0
        if obj.max_students:
            css = "ok-badge-danger" if count >= obj.max_students else "ok-badge-success" if count else "ok-badge-muted"
            label = f"{count} / {obj.max_students}"
        else:
            css = "ok-badge-muted"
            label = f"{count} / ∞"
        return _badge(css, label)

    @admin.display(description="Тренеры / программы", ordering="active_teacher_programs_count")
    def teacher_programs_summary(self, obj: Group) -> str:
        count = getattr(obj, "active_teacher_programs_count", None)
        if count is None:
            count = obj.teachers.filter(is_active=True).count()
        if not count:
            return _badge("ok-badge-danger", "Нет тренеров")
        label = "программа" if count == 1 else ("программы" if 2 <= count <= 4 else "программ")
        return _badge("ok-badge-success", f"{count} {label}")

    @admin.display(description="Статус", ordering="status")
    def status_badge(self, obj: Group) -> str:
        css_map = {
            Group.Status.ACTIVE: "ok-badge-success",
            Group.Status.PAUSED: "ok-badge-warning",
            Group.Status.COMPLETED: "ok-badge-muted",
            Group.Status.CANCELLED: "ok-badge-danger",
        }
        return _badge(css_map.get(obj.status, "ok-badge-muted"), obj.get_status_display())

    @admin.display(description="Рабочее пространство")
    def workspace_link(self, obj: Group) -> str:
        if not obj.pk:
            return "—"
        url = reverse("admin:academy_group_workspace", args=[obj.pk])
        return format_html(
            '<a class="btn btn-outline-success btn-sm" href="{}"><i class="bi bi-kanban"></i> Открыть →</a>', url
        )

    @admin.display(description="")
    def workspace_summary(self, obj: Group) -> str:
        """Compact summary + link (spec §3): students count, programs
        count, and a prominent button into the Group Workspace — everything
        else (schedule, lesson generation, analytics...) lives there now."""
        if not obj.pk:
            return mark_safe(
                '<p class="ok-help-text" style="margin:0;">'
                "Рабочее пространство появится после сохранения группы.</p>"
            )
        students_count = obj.students_count
        programs_count = obj.teachers.filter(is_active=True).count()
        url = reverse("admin:academy_group_workspace", args=[obj.pk])
        return format_html(
            '<div class="ok-group-form-summary">'
            '<div class="okan-mini-stats" style="margin:0;">'
            "<div class=\"okan-mini-stat\">Студентов: <strong>{}</strong></div>"
            "<div class=\"okan-mini-stat\">Учебных программ: <strong>{}</strong></div>"
            "</div>"
            '<a class="btn btn-success" href="{}"><i class="bi bi-kanban"></i> Открыть рабочее пространство →</a>'
            "</div>",
            students_count, programs_count, url,
        )

    @admin.display(description="")
    def capacity_summary(self, obj: Group) -> str:
        """Spec §3.C: selected count / capacity used / free places, with a
        clear warning once capacity is exceeded."""
        if not obj.pk:
            return mark_safe(
                '<p class="ok-help-text" style="margin:0 0 0.5rem;">'
                "Количество студентов появится после сохранения группы.</p>"
            )

        selected = obj.students_count
        if not obj.max_students:
            return format_html(
                '<div class="okan-mini-stats" style="margin:0 0 0.75rem;">'
                '<div class="okan-mini-stat">Студентов сейчас: <strong>{}</strong></div>'
                '<div class="okan-mini-stat">Вместимость: <strong>Без ограничения</strong></div>'
                "</div>",
                selected,
            )

        free_places = obj.max_students - selected
        if free_places < 0:
            capacity_badge = _badge("ok-badge-danger", f"Превышена на {abs(free_places)}")
        elif free_places == 0:
            capacity_badge = _badge("ok-badge-warning", "Мест нет")
        else:
            capacity_badge = _badge("ok-badge-success", f"Свободно: {free_places}")

        return format_html(
            '<div class="okan-mini-stats" style="margin:0 0 0.75rem;">'
            '<div class="okan-mini-stat">Студентов сейчас: <strong>{}</strong></div>'
            '<div class="okan-mini-stat">Вместимость: <strong>{} / {}</strong></div>'
            "<div class=\"okan-mini-stat\">{}</div>"
            "</div>",
            selected, selected, obj.max_students, capacity_badge,
        )

    @admin.action(description="Сгенерировать занятия по плану курса")
    def generate_lessons_action(self, request, queryset):
        for group in queryset:
            try:
                created = generate_lessons_for_group(group)
            except LessonGenerationError as exc:
                self.message_user(request, f"«{group.name}»: {exc}", messages.ERROR)
                continue
            if created:
                self.message_user(
                    request, f"«{group.name}»: создано занятий — {len(created)}.", messages.SUCCESS
                )
            else:
                self.message_user(
                    request, f"«{group.name}»: новых занятий не создано (уже сгенерированы).", messages.WARNING
                )

    @admin.action(description="Приостановить выбранные группы")
    def pause_groups(self, request, queryset):
        updated = queryset.update(status=Group.Status.PAUSED)
        self.message_user(request, f"Приостановлено групп: {updated}.", messages.SUCCESS)

    @admin.action(description="Активировать выбранные группы")
    def activate_groups(self, request, queryset):
        updated = queryset.update(status=Group.Status.ACTIVE)
        self.message_user(request, f"Активировано групп: {updated}.", messages.SUCCESS)

    def get_urls(self):
        custom_urls = [
            path(
                "<int:group_id>/workspace/",
                self.admin_site.admin_view(group_workspace_overview_view),
                name="academy_group_workspace",
            ),
            path(
                "<int:group_id>/workspace/students/",
                self.admin_site.admin_view(group_workspace_students_view),
                name="academy_group_workspace_students",
            ),
            path(
                "<int:group_id>/workspace/students/add/",
                self.admin_site.admin_view(group_workspace_add_student_view),
                name="academy_group_workspace_students_add",
            ),
            path(
                "<int:group_id>/workspace/students/add-existing/",
                self.admin_site.admin_view(group_workspace_add_existing_students_view),
                name="academy_group_workspace_students_add_existing",
            ),
            path(
                "<int:group_id>/workspace/students/<int:student_id>/remove/",
                self.admin_site.admin_view(group_workspace_remove_student_view),
                name="academy_group_workspace_students_remove",
            ),
            path(
                "<int:group_id>/workspace/teachers/",
                self.admin_site.admin_view(group_workspace_teachers_view),
                name="academy_group_workspace_teachers",
            ),
            path(
                "<int:group_id>/workspace/teachers/add/",
                self.admin_site.admin_view(group_workspace_add_teacher_view),
                name="academy_group_workspace_teachers_add",
            ),
            path(
                "<int:group_id>/workspace/teachers/<int:group_teacher_id>/remove/",
                self.admin_site.admin_view(group_workspace_remove_teacher_view),
                name="academy_group_workspace_teachers_remove",
            ),
            path(
                "<int:group_id>/workspace/programs/",
                self.admin_site.admin_view(group_workspace_programs_view),
                name="academy_group_workspace_programs",
            ),
            path(
                "<int:group_id>/workspace/programs/add/",
                self.admin_site.admin_view(group_workspace_add_program_view),
                name="academy_group_workspace_programs_add",
            ),
            path(
                "<int:group_id>/workspace/schedule/",
                self.admin_site.admin_view(group_workspace_schedule_view),
                name="academy_group_workspace_schedule",
            ),
            path(
                "<int:group_id>/workspace/schedule/add/",
                self.admin_site.admin_view(group_workspace_add_schedule_view),
                name="academy_group_workspace_schedule_add",
            ),
            path(
                "<int:group_id>/workspace/schedule/<int:schedule_id>/remove/",
                self.admin_site.admin_view(group_workspace_remove_schedule_view),
                name="academy_group_workspace_schedule_remove",
            ),
            path(
                "<int:group_id>/workspace/lessons/",
                self.admin_site.admin_view(group_workspace_lessons_view),
                name="academy_group_workspace_lessons",
            ),
            path(
                "<int:group_id>/workspace/attendance/",
                self.admin_site.admin_view(group_workspace_attendance_view),
                name="academy_group_workspace_attendance",
            ),
            path(
                "<int:group_id>/workspace/homework/",
                self.admin_site.admin_view(group_workspace_homework_view),
                name="academy_group_workspace_homework",
            ),
            path(
                "<int:group_id>/workspace/analytics/",
                self.admin_site.admin_view(group_workspace_analytics_view),
                name="academy_group_workspace_analytics",
            ),
            path(
                "<int:group_id>/workspace/generate-lessons/",
                self.admin_site.admin_view(group_workspace_generate_lessons_view),
                name="academy_group_workspace_generate_lessons",
            ),
        ]
        return custom_urls + super().get_urls()


# ---------------------------------------------------------------------------
# Lessons — with inline Homework and Attendance, per spec
# ---------------------------------------------------------------------------

class HomeworkInline(admin.TabularInline):
    model = Homework
    extra = 0
    fields = ("title", "deadline")
    show_change_link = True


class AttendanceInline(admin.TabularInline):
    model = Attendance
    extra = 0
    fields = ("student", "status", "comment")
    autocomplete_fields = ("student",)


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("date", "time_range", "group", "lesson_teacher", "subject", "status_badge")
    list_filter = ("date", "group", "subject", "status", "teacher", "group_teacher")
    search_fields = ("topic", "description", "group__name")
    date_hierarchy = "date"
    ordering = ("date", "start_time")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("group", "room", "subject", "teacher", "group_teacher")
    inlines = [HomeworkInline, AttendanceInline]
    actions = ["mark_completed", "mark_cancelled"]
    list_per_page = 30

    fieldsets = (
        (
            "Основное",
            {
                "fields": (
                    "group", "group_teacher", "teacher", "plan", "individual_plan", "lesson_number",
                    "date", "start_time", "end_time", "room", "subject",
                )
            },
        ),
        ("Содержание урока", {"fields": ("topic", "description", "youtube_url", "presentation_urls")}),
        ("Статус", {"fields": ("status", "cancellation_reason")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("group__teacher__user", "teacher__user", "room", "subject")
        )

    @admin.display(description="Время")
    def time_range(self, obj: Lesson) -> str:
        return f"{obj.start_time.strftime('%H:%M')}–{obj.end_time.strftime('%H:%M')}"

    @admin.display(description="Тренер", ordering="teacher")
    def lesson_teacher(self, obj: Lesson):
        return obj.effective_teacher

    @admin.display(description="Статус", ordering="status")
    def status_badge(self, obj: Lesson) -> str:
        css_map = {
            Lesson.Status.PLANNED: "ok-badge-muted",
            Lesson.Status.COMPLETED: "ok-badge-success",
            Lesson.Status.CANCELLED: "ok-badge-danger",
        }
        return _badge(css_map.get(obj.status, "ok-badge-muted"), obj.get_status_display())

    @admin.action(description="Отметить как проведённые")
    def mark_completed(self, request, queryset):
        updated = queryset.update(status=Lesson.Status.COMPLETED)
        self.message_user(request, f"Отмечено проведёнными: {updated}.", messages.SUCCESS)

    @admin.action(description="Отменить выбранные занятия")
    def mark_cancelled(self, request, queryset):
        updated = queryset.update(status=Lesson.Status.CANCELLED)
        self.message_user(request, f"Отменено занятий: {updated}.", messages.SUCCESS)


# ---------------------------------------------------------------------------
# Homework & results
# ---------------------------------------------------------------------------

class HomeworkResultInline(admin.TabularInline):
    model = HomeworkResult
    extra = 0
    fields = ("student", "status", "score", "comment")
    autocomplete_fields = ("student",)


@admin.register(Homework)
class HomeworkAdmin(admin.ModelAdmin):
    list_display = ("title", "lesson", "deadline", "results_summary")
    list_filter = ("lesson__group", "lesson__group_teacher")
    search_fields = ("title", "description", "lesson__group__name")
    autocomplete_fields = ("lesson",)
    readonly_fields = ("created_at", "updated_at")
    inlines = [HomeworkResultInline]
    list_per_page = 25

    fieldsets = (
        ("Основное", {"fields": ("lesson", "title", "description", "deadline")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("lesson__group")
            .annotate(_results_count=Count("results", distinct=True))
        )

    @admin.display(description="Результатов")
    def results_summary(self, obj: Homework) -> int:
        return getattr(obj, "_results_count", 0)


@admin.register(HomeworkResult)
class HomeworkResultAdmin(admin.ModelAdmin):
    list_display = ("student", "homework", "status_badge", "score_badge", "checked_at")
    list_filter = ("status", "homework__lesson__group", "homework__lesson__group_teacher")
    search_fields = ("student__first_name", "student__last_name", "homework__title")
    autocomplete_fields = ("student", "homework")
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 30

    fieldsets = (
        ("Результат", {"fields": ("homework", "student", "status", "score", "comment")}),
        ("Даты", {"fields": ("submitted_at", "checked_at")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("student", "homework__lesson__group")

    @admin.display(description="Статус", ordering="status")
    def status_badge(self, obj: HomeworkResult) -> str:
        css_map = {
            HomeworkResult.Status.NOT_SUBMITTED: "ok-badge-muted",
            HomeworkResult.Status.SUBMITTED: "ok-badge-warning",
            HomeworkResult.Status.CHECKED: "ok-badge-success",
            HomeworkResult.Status.LATE: "ok-badge-danger",
        }
        return _badge(css_map.get(obj.status, "ok-badge-muted"), obj.get_status_display())

    @admin.display(description="Балл", ordering="score")
    def score_badge(self, obj: HomeworkResult) -> str:
        if obj.score is None:
            return "—"
        css = "ok-badge-success" if obj.score >= 8 else "ok-badge-warning" if obj.score >= 5 else "ok-badge-danger"
        return _badge(css, f"{obj.score}/10")


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("lesson_date", "student", "group", "status_badge", "comment_short")
    list_filter = ("lesson__date", "lesson__group", "lesson__group_teacher", "status")
    search_fields = ("student__first_name", "student__last_name", "lesson__group__name")
    autocomplete_fields = ("student", "lesson")
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 30

    fieldsets = (
        ("Запись", {"fields": ("lesson", "student", "status", "comment")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("student", "lesson__group")

    @admin.display(description="Дата", ordering="lesson__date")
    def lesson_date(self, obj: Attendance):
        return obj.lesson.date

    @admin.display(description="Группа", ordering="lesson__group")
    def group(self, obj: Attendance):
        return obj.lesson.group

    @admin.display(description="Комментарий")
    def comment_short(self, obj: Attendance) -> str:
        if not obj.comment:
            return "—"
        return obj.comment if len(obj.comment) <= 40 else f"{obj.comment[:40]}..."

    @admin.display(description="Статус", ordering="status")
    def status_badge(self, obj: Attendance) -> str:
        css_map = {
            Attendance.Status.PRESENT: "ok-badge-success",
            Attendance.Status.ABSENT: "ok-badge-danger",
            Attendance.Status.LATE: "ok-badge-warning",
            Attendance.Status.EXCUSED: "ok-badge-muted",
        }
        return _badge(css_map.get(obj.status, "ok-badge-muted"), obj.get_status_display())


# ---------------------------------------------------------------------------
# "Расписание" и "Аналитика" — custom admin pages (no model of their own),
# built on Lesson and on AnalyticsService respectively.
#
# Django admin only lets a ModelAdmin nest extra URLs under its own
# <app_label>/<model_name>/ prefix, and neither screen is tied to a single
# model — so both are added directly onto the admin site's own URLconf
# instead, the same approach Django's own docs use for a site-wide custom
# admin view.
# ---------------------------------------------------------------------------

_original_get_urls = admin.site.get_urls


def _get_urls_with_schedule():
    custom_urls = [
        path("academy/schedule/", admin.site.admin_view(schedule_view), name="academy_schedule"),
        path(
            "academy/schedule/generate-lessons/<int:group_id>/",
            admin.site.admin_view(generate_lessons_for_group_view),
            name="academy_schedule_generate_lessons",
        ),
        path("academy/analytics/", admin.site.admin_view(analytics_view), name="academy_analytics"),
    ]
    return custom_urls + _original_get_urls()


admin.site.get_urls = _get_urls_with_schedule
