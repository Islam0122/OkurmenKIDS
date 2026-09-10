from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from apps.users.import_export.formats import UnsupportedFileFormat

from .admin_views import analytics_view, generate_lessons_for_group_view, schedule_view
from .constants import WEEKDAY_CODES, WEEKDAY_LABELS_SHORT
from .models import (
    Attendance,
    Course,
    CourseLessonPlan,
    Group,
    Homework,
    HomeworkResult,
    Lesson,
    Room,
    Student,
)
from .services.import_export import (
    StudentImportValidationError,
    export_students,
    import_students,
    preview_students_import,
)
from .services.lesson_generator import LessonGenerationError, generate_lessons_for_group

DAY_CHOICES = [(code, WEEKDAY_LABELS_SHORT[code]) for code in WEEKDAY_CODES]


def _badge(css: str, label: str) -> str:
    return format_html('<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label)


# ---------------------------------------------------------------------------
# Course catalogue
# ---------------------------------------------------------------------------

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("name", "count_lesson", "subjects_list", "lesson_plans_progress", "created_at")
    filter_horizontal = ("subjects",)
    search_fields = ("name", "description")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 25

    fieldsets = (
        ("Основная информация", {"fields": ("name", "count_lesson", "subjects", "description")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

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
class CourseLessonPlanAdmin(admin.ModelAdmin):
    list_display = ("course", "lesson_number", "subject", "topic", "homework_badge")
    list_filter = ("course", "subject")
    search_fields = ("topic", "description", "course__name")
    ordering = ("course", "lesson_number")
    autocomplete_fields = ("course", "subject")
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 30

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


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "group", "phone", "active_badge", "created_at")
    list_filter = ("group", "is_active")
    search_fields = ("first_name", "last_name", "phone", "parent_phone")
    ordering = ("last_name", "first_name")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("group",)
    list_per_page = 25
    actions = ["export_selected_csv"]
    change_list_template = "admin/academy/student/change_list.html"

    fieldsets = (
        ("Основная информация", {"fields": ("first_name", "last_name", "group", "is_active")}),
        ("Контакты", {"fields": ("phone", "parent_phone")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("group")

    @admin.display(description="Студент", ordering="last_name")
    def full_name(self, obj: Student) -> str:
        return f"{obj.first_name} {obj.last_name}".strip()

    @admin.display(description="Статус", ordering="is_active")
    def active_badge(self, obj: Student) -> str:
        return _badge("ok-badge-success", "Активен") if obj.is_active else _badge("ok-badge-danger", "Неактивен")

    @admin.action(description="Экспортировать выбранных студентов (CSV)")
    def export_selected_csv(self, request, queryset):
        return export_students(queryset, "csv")

    def get_urls(self):
        custom_urls = [
            path("import/", self.admin_site.admin_view(self.import_view), name="academy_student_import"),
            path("export/", self.admin_site.admin_view(self.export_view), name="academy_student_export"),
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

    def import_view(self, request):
        preview = None
        failed = False

        if request.method == "POST":
            form = StudentImportForm(request.POST, request.FILES)
            if form.is_valid():
                file_obj = form.cleaned_data["file"]
                if "preview" in request.POST:
                    try:
                        preview = preview_students_import(file_obj)
                    except UnsupportedFileFormat as exc:
                        messages.error(request, str(exc))
                else:
                    try:
                        result = import_students(file_obj)
                    except UnsupportedFileFormat as exc:
                        messages.error(request, str(exc))
                    except StudentImportValidationError as exc:
                        preview = exc.preview
                        failed = True
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
            "failed": failed,
            "export_fields": "id, first_name, last_name, phone, parent_phone, group, is_active",
            "changelist_url": reverse("admin:academy_student_changelist"),
        }
        return render(request, "admin/academy/student_import.html", context)


# ---------------------------------------------------------------------------
# Group — the busiest admin screen: course/teacher/room, schedule, a modern
# student picker, and the "Сгенерировать занятия" action.
# ---------------------------------------------------------------------------

class GroupAdminForm(forms.ModelForm):
    days_of_week = forms.MultipleChoiceField(
        choices=DAY_CHOICES,
        required=False,
        label="Дни недели",
        widget=forms.CheckboxSelectMultiple,
    )

    students = forms.ModelMultipleChoiceField(
        queryset=Student.objects.filter(is_active=True),
        required=False,
        label="Студенты",
        help_text="Поиск и выбор студентов этой группы.",
        widget=forms.SelectMultiple(
            attrs={"class": "ok-multiselect-source", "data-placeholder": "Поиск студента..."}
        ),
    )

    class Meta:
        model = Group
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["days_of_week"].initial = self.instance.days_of_week
            current_students = Student.objects.filter(group=self.instance)
            self.fields["students"].queryset = (
                Student.objects.filter(is_active=True) | current_students
            ).distinct()
            self.fields["students"].initial = current_students

    def save_students(self):
        """Assign/unassign Student.group to match the widget's selection.

        Group has no `students` field of its own (Student.group is the FK),
        so this can't go through the normal m2m-save path — it's called
        explicitly from GroupAdmin.save_related once the group has a pk.
        """
        selected = self.cleaned_data.get("students", Student.objects.none())
        selected_ids = list(selected.values_list("id", flat=True))
        Student.objects.filter(group=self.instance).exclude(id__in=selected_ids).update(group=None)
        Student.objects.filter(id__in=selected_ids).update(group=self.instance)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    form = GroupAdminForm
    list_display = (
        "name", "course", "teacher", "room", "schedule_summary",
        "students_count_display", "status_badge", "start_date", "end_date",
    )
    list_filter = ("status", "course", "teacher", "room", "start_date")
    search_fields = ("name", "teacher__user__first_name", "teacher__user__last_name")
    ordering = ("-start_date", "name")
    readonly_fields = ("created_at", "updated_at", "schedule_link_detail")
    autocomplete_fields = ("course", "teacher", "room")
    actions = ["generate_lessons_action", "pause_groups", "activate_groups"]
    list_per_page = 25

    fieldsets = (
        ("Основная информация", {"fields": ("name", "course", "teacher", "room", "status", "description")}),
        ("Период и время", {"fields": ("start_date", "end_date", "start_time", "end_time", "days_of_week")}),
        ("Студенты", {"fields": ("max_students", "students")}),
        ("Расписание", {"fields": ("schedule_link_detail",)}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("teacher__user", "room", "course")
            .annotate(
                active_students_count=Count("students", filter=Q(students__is_active=True), distinct=True)
            )
        )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.save_students()

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

    @admin.display(description="Расписание")
    def schedule_summary(self, obj: Group) -> str:
        day_labels = dict(DAY_CHOICES)
        days = ", ".join(day_labels.get(d, d) for d in (obj.days_of_week or []))
        if not days:
            return "—"
        return f"{days} · {obj.start_time.strftime('%H:%M')}–{obj.end_time.strftime('%H:%M')}"

    @admin.display(description="Расписание группы")
    def schedule_link_detail(self, obj: Group) -> str:
        if not obj.pk:
            return "Появится после сохранения группы."
        day_labels = dict(DAY_CHOICES)
        days = ", ".join(day_labels.get(d, d) for d in (obj.days_of_week or [])) or "—"
        url = f"{reverse('admin:academy_schedule')}?group={obj.pk}"
        return format_html(
            '<div style="margin-bottom:0.5rem;">'
            "<div>Дни: <strong>{}</strong></div>"
            "<div>Время: <strong>{}–{}</strong></div>"
            "<div>Аудитория: <strong>{}</strong></div>"
            "<div>Тренер: <strong>{}</strong></div>"
            "</div>"
            '<a class="btn btn-outline-success btn-sm" href="{}">Открыть расписание группы</a>',
            days,
            obj.start_time.strftime("%H:%M"),
            obj.end_time.strftime("%H:%M"),
            obj.room or "—",
            obj.teacher,
            url,
        )

    @admin.display(description="Статус", ordering="status")
    def status_badge(self, obj: Group) -> str:
        css_map = {
            Group.Status.ACTIVE: "ok-badge-success",
            Group.Status.PAUSED: "ok-badge-warning",
            Group.Status.COMPLETED: "ok-badge-muted",
            Group.Status.CANCELLED: "ok-badge-danger",
        }
        return _badge(css_map.get(obj.status, "ok-badge-muted"), obj.get_status_display())

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
    list_display = ("date", "time_range", "group", "teacher", "subject", "status_badge")
    list_filter = ("date", "group", "subject", "status", "group__teacher")
    search_fields = ("topic", "description", "group__name")
    date_hierarchy = "date"
    ordering = ("date", "start_time")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("group", "room", "subject")
    inlines = [HomeworkInline, AttendanceInline]
    actions = ["mark_completed", "mark_cancelled"]
    list_per_page = 30

    fieldsets = (
        ("Основное", {"fields": ("group", "plan", "lesson_number", "date", "start_time", "end_time", "room", "subject")}),
        ("Содержание урока", {"fields": ("topic", "description", "youtube_url", "presentation_urls")}),
        ("Статус", {"fields": ("status", "cancellation_reason")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("group__teacher__user", "room", "subject")

    @admin.display(description="Время")
    def time_range(self, obj: Lesson) -> str:
        return f"{obj.start_time.strftime('%H:%M')}–{obj.end_time.strftime('%H:%M')}"

    @admin.display(description="Тренер", ordering="group__teacher")
    def teacher(self, obj: Lesson):
        return obj.group.teacher

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
    list_filter = ("lesson__group",)
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
    list_filter = ("status", "homework__lesson__group")
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
    list_filter = ("lesson__date", "lesson__group", "status")
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
