from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q
from django.urls import path, reverse
from django.utils.html import format_html

from .admin_views import generate_lessons_for_group_view, schedule_view
from .models import (
    KPIAttendance,
    KPIGroup,
    KPIHomework,
    KPILesson,
    KPIStudent,
    KPITeacher,
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
from .services.kpi_calculator import (
    calculate_attendance_kpi,
    calculate_group_kpi,
    calculate_homework_kpi,
    calculate_lesson_kpi,
    calculate_student_kpi,
    calculate_teacher_kpi,
)
from .services.lesson_generator import LessonGenerationError, generate_lessons_for_group

DAY_CHOICES = [
    ("mon", "Пн"), ("tue", "Вт"), ("wed", "Ср"), ("thu", "Чт"),
    ("fri", "Пт"), ("sat", "Сб"), ("sun", "Вс"),
]


def _badge(css: str, label: str) -> str:
    return format_html('<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label)


def _percent_badge(value: float) -> str:
    css = "ok-badge-success" if value >= 80 else "ok-badge-warning" if value >= 50 else "ok-badge-danger"
    return _badge(css, f"{value}%")


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


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "group", "phone", "active_badge", "created_at")
    list_filter = ("group", "is_active")
    search_fields = ("first_name", "last_name", "phone", "parent_phone")
    ordering = ("last_name", "first_name")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("group",)
    list_per_page = 25

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
# KPI — read-only analytics. Never hand-typed: created/refreshed only via
# the API's `.../calculate/` endpoints or the "Пересчитать KPI" action here.
# ---------------------------------------------------------------------------

class KPIReadOnlyAdminMixin:
    """Common behaviour for every KPI admin: view + recalculate, never freehand add."""

    def has_add_permission(self, request):
        return False

    def _recalculate_one(self, kpi):
        raise NotImplementedError

    @admin.action(description="Пересчитать KPI")
    def recalculate(self, request, queryset):
        count = 0
        for kpi in queryset:
            self._recalculate_one(kpi)
            count += 1
        self.message_user(request, f"Пересчитано записей KPI: {count}.", messages.SUCCESS)


@admin.register(KPIGroup)
class KPIGroupAdmin(KPIReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("group", "period", "total_students", "attendance_badge", "homework_badge", "average_score")
    list_filter = ("group",)
    search_fields = ("group__name",)
    ordering = ("-date_to",)
    readonly_fields = (
        "group", "date_from", "date_to", "total_students", "total_lessons", "completed_lessons",
        "cancelled_lessons", "attendance_percent", "homework_completion_percent", "average_score",
        "created_at", "updated_at",
    )
    actions = ["recalculate"]
    list_per_page = 25

    fieldsets = (
        ("Период", {"fields": ("group", "date_from", "date_to")}),
        ("Занятия", {"fields": ("total_students", "total_lessons", "completed_lessons", "cancelled_lessons")}),
        ("Показатели", {"fields": ("attendance_percent", "homework_completion_percent", "average_score")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("group")

    @admin.display(description="Период")
    def period(self, obj: KPIGroup) -> str:
        return f"{obj.date_from.strftime('%d.%m.%Y')} — {obj.date_to.strftime('%d.%m.%Y')}"

    @admin.display(description="Посещаемость")
    def attendance_badge(self, obj: KPIGroup) -> str:
        return _percent_badge(obj.attendance_percent)

    @admin.display(description="ДЗ")
    def homework_badge(self, obj: KPIGroup) -> str:
        return _percent_badge(obj.homework_completion_percent)

    def _recalculate_one(self, kpi: KPIGroup):
        calculate_group_kpi(kpi.group, kpi.date_from, kpi.date_to)


@admin.register(KPITeacher)
class KPITeacherAdmin(KPIReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("teacher", "period", "total_groups", "attendance_badge", "homework_badge", "average_student_score")
    list_filter = ("teacher",)
    search_fields = ("teacher__user__first_name", "teacher__user__last_name")
    ordering = ("-date_to",)
    readonly_fields = (
        "teacher", "date_from", "date_to", "total_groups", "total_lessons", "completed_lessons",
        "cancelled_lessons", "attendance_percent", "homework_completion_percent", "average_student_score",
        "created_at", "updated_at",
    )
    actions = ["recalculate"]
    list_per_page = 25

    fieldsets = (
        ("Период", {"fields": ("teacher", "date_from", "date_to")}),
        ("Занятия", {"fields": ("total_groups", "total_lessons", "completed_lessons", "cancelled_lessons")}),
        ("Показатели", {"fields": ("attendance_percent", "homework_completion_percent", "average_student_score")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("teacher__user")

    @admin.display(description="Период")
    def period(self, obj: KPITeacher) -> str:
        return f"{obj.date_from.strftime('%d.%m.%Y')} — {obj.date_to.strftime('%d.%m.%Y')}"

    @admin.display(description="Посещаемость")
    def attendance_badge(self, obj: KPITeacher) -> str:
        return _percent_badge(obj.attendance_percent)

    @admin.display(description="ДЗ")
    def homework_badge(self, obj: KPITeacher) -> str:
        return _percent_badge(obj.homework_completion_percent)

    def _recalculate_one(self, kpi: KPITeacher):
        calculate_teacher_kpi(kpi.teacher, kpi.date_from, kpi.date_to)


@admin.register(KPIStudent)
class KPIStudentAdmin(KPIReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("student", "group", "period", "attendance_badge", "homework_badge", "average_score")
    list_filter = ("group", "student")
    search_fields = ("student__first_name", "student__last_name", "group__name")
    ordering = ("-date_to",)
    readonly_fields = (
        "student", "group", "date_from", "date_to", "total_lessons", "present_count", "absent_count",
        "late_count", "attendance_percent", "total_homeworks", "completed_homeworks", "missed_homeworks",
        "homework_completion_percent", "average_score", "created_at", "updated_at",
    )
    actions = ["recalculate"]
    list_per_page = 25

    fieldsets = (
        ("Период", {"fields": ("student", "group", "date_from", "date_to")}),
        ("Посещаемость", {"fields": ("total_lessons", "present_count", "absent_count", "late_count", "attendance_percent")}),
        ("Домашние задания", {"fields": ("total_homeworks", "completed_homeworks", "missed_homeworks", "homework_completion_percent", "average_score")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("student", "group")

    @admin.display(description="Период")
    def period(self, obj: KPIStudent) -> str:
        return f"{obj.date_from.strftime('%d.%m.%Y')} — {obj.date_to.strftime('%d.%m.%Y')}"

    @admin.display(description="Посещаемость")
    def attendance_badge(self, obj: KPIStudent) -> str:
        return _percent_badge(obj.attendance_percent)

    @admin.display(description="ДЗ")
    def homework_badge(self, obj: KPIStudent) -> str:
        return _percent_badge(obj.homework_completion_percent)

    def _recalculate_one(self, kpi: KPIStudent):
        calculate_student_kpi(kpi.student, kpi.group, kpi.date_from, kpi.date_to)


@admin.register(KPILesson)
class KPILessonAdmin(KPIReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("lesson", "attendance_badge", "homework_badge", "average_homework_score")
    list_filter = ("lesson__group",)
    search_fields = ("lesson__group__name", "lesson__topic")
    ordering = ("-lesson__date",)
    readonly_fields = (
        "lesson", "total_students", "present_count", "absent_count", "late_count", "attendance_percent",
        "total_homeworks", "homework_completed_count", "homework_completion_percent", "average_homework_score",
        "created_at", "updated_at",
    )
    actions = ["recalculate"]
    list_per_page = 25

    fieldsets = (
        ("Занятие", {"fields": ("lesson",)}),
        ("Посещаемость", {"fields": ("total_students", "present_count", "absent_count", "late_count", "attendance_percent")}),
        ("Домашние задания", {"fields": ("total_homeworks", "homework_completed_count", "homework_completion_percent", "average_homework_score")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("lesson__group")

    @admin.display(description="Посещаемость")
    def attendance_badge(self, obj: KPILesson) -> str:
        return _percent_badge(obj.attendance_percent)

    @admin.display(description="ДЗ")
    def homework_badge(self, obj: KPILesson) -> str:
        return _percent_badge(obj.homework_completion_percent)

    def _recalculate_one(self, kpi: KPILesson):
        calculate_lesson_kpi(kpi.lesson)


@admin.register(KPIAttendance)
class KPIAttendanceAdmin(KPIReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("group", "period", "total_records", "attendance_badge")
    list_filter = ("group",)
    search_fields = ("group__name",)
    ordering = ("-date_to",)
    readonly_fields = (
        "group", "date_from", "date_to", "total_records", "present_count", "absent_count",
        "late_count", "excused_count", "attendance_percent", "created_at", "updated_at",
    )
    actions = ["recalculate"]
    list_per_page = 25

    fieldsets = (
        ("Период", {"fields": ("group", "date_from", "date_to")}),
        ("Показатели", {"fields": ("total_records", "present_count", "absent_count", "late_count", "excused_count", "attendance_percent")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("group")

    @admin.display(description="Период")
    def period(self, obj: KPIAttendance) -> str:
        return f"{obj.date_from.strftime('%d.%m.%Y')} — {obj.date_to.strftime('%d.%m.%Y')}"

    @admin.display(description="Посещаемость")
    def attendance_badge(self, obj: KPIAttendance) -> str:
        return _percent_badge(obj.attendance_percent)

    def _recalculate_one(self, kpi: KPIAttendance):
        calculate_attendance_kpi(kpi.group, kpi.date_from, kpi.date_to)


@admin.register(KPIHomework)
class KPIHomeworkAdmin(KPIReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ("group", "period", "total_homeworks", "completion_badge", "average_score")
    list_filter = ("group",)
    search_fields = ("group__name",)
    ordering = ("-date_to",)
    readonly_fields = (
        "group", "date_from", "date_to", "total_homeworks", "total_results", "submitted_count",
        "checked_count", "not_submitted_count", "late_count", "completion_percent", "average_score",
        "created_at", "updated_at",
    )
    actions = ["recalculate"]
    list_per_page = 25

    fieldsets = (
        ("Период", {"fields": ("group", "date_from", "date_to")}),
        ("Показатели", {"fields": (
            "total_homeworks", "total_results", "submitted_count", "checked_count",
            "not_submitted_count", "late_count", "completion_percent", "average_score",
        )}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("group")

    @admin.display(description="Период")
    def period(self, obj: KPIHomework) -> str:
        return f"{obj.date_from.strftime('%d.%m.%Y')} — {obj.date_to.strftime('%d.%m.%Y')}"

    @admin.display(description="Выполнение")
    def completion_badge(self, obj: KPIHomework) -> str:
        return _percent_badge(obj.completion_percent)

    def _recalculate_one(self, kpi: KPIHomework):
        calculate_homework_kpi(kpi.group, kpi.date_from, kpi.date_to)


# ---------------------------------------------------------------------------
# "Расписание" — a custom admin page (no model of its own) built on Lesson.
#
# Django admin only lets a ModelAdmin nest extra URLs under its own
# <app_label>/<model_name>/ prefix, and this screen deliberately isn't tied
# to a single model (it reads Lesson filtered several different ways) — so
# it's added directly onto the admin site's own URLconf instead, the same
# approach Django's own docs use for a site-wide custom admin view.
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
    ]
    return custom_urls + _original_get_urls()


admin.site.get_urls = _get_urls_with_schedule
