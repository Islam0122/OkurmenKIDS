from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q
from django.utils.html import format_html

from .models import KPI, Attendance, Group, Homework, Room, Schedule, Student
from .services import calculate_attendance_stats, calculate_homework_stats

DAY_CHOICES = [
    ("mon", "Пн"),
    ("tue", "Вт"),
    ("wed", "Ср"),
    ("thu", "Чт"),
    ("fri", "Пт"),
    ("sat", "Сб"),
    ("sun", "Вс"),
]


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("name", "capacity", "active_badge", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    ordering = ("name",)
    readonly_fields = ("created_at", "updated_at")
    list_per_page = 25

    fieldsets = (
        ("Основная информация", {"fields": ("name", "capacity", "description", "is_active")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    @admin.display(description="Статус", ordering="is_active")
    def active_badge(self, obj: Room) -> str:
        css = "ok-badge-success" if obj.is_active else "ok-badge-danger"
        label = "Активна" if obj.is_active else "Неактивна"
        return format_html(
            '<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label
        )


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "group", "active_badge", "created_at")
    list_filter = ("group", "is_active")
    search_fields = ("first_name", "last_name")
    ordering = ("last_name", "first_name", "-created_at")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("group",)
    list_per_page = 25

    fieldsets = (
        ("Основная информация", {"fields": ("first_name", "last_name", "group", "is_active")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("group")

    @admin.display(description="Студент", ordering="last_name")
    def full_name(self, obj: Student) -> str:
        return f"{obj.first_name} {obj.last_name}".strip()

    @admin.display(description="Статус", ordering="is_active")
    def active_badge(self, obj: Student) -> str:
        css = "ok-badge-success" if obj.is_active else "ok-badge-danger"
        label = "Активен" if obj.is_active else "Неактивен"
        return format_html(
            '<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label
        )


# ---------------------------------------------------------------------------
# Group
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
            attrs={
                "class": "ok-multiselect-source",
                "data-placeholder": "Поиск студента...",
            }
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
        "name",
        "teacher",
        "room",
        "schedule_summary",
        "students_count",
        "max_students",
        "status_badge",
        "start_date",
        "end_date",
    )
    list_filter = ("status", "teacher", "room", "start_date")
    search_fields = ("name", "teacher__user__first_name", "teacher__user__last_name")
    ordering = ("-start_date", "name")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("teacher", "room")
    list_per_page = 25

    fieldsets = (
        ("Основная информация", {"fields": ("name", "teacher", "room", "status", "description")}),
        ("Период и время", {"fields": ("start_date", "end_date", "start_time", "end_time", "days_of_week")}),
        ("Студенты", {"fields": ("max_students", "students")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("teacher__user", "room")
            .annotate(
                active_students_count=Count(
                    "students", filter=Q(students__is_active=True), distinct=True
                )
            )
        )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.save_students()

    @admin.display(description="Студенты", ordering="active_students_count")
    def students_count(self, obj: Group) -> int:
        return getattr(obj, "active_students_count", None) or 0

    @admin.display(description="Расписание")
    def schedule_summary(self, obj: Group) -> str:
        day_labels = dict(DAY_CHOICES)
        days = ", ".join(day_labels.get(d, d) for d in (obj.days_of_week or []))
        if not days:
            return "—"
        return f"{days} · {obj.start_time.strftime('%H:%M')}–{obj.end_time.strftime('%H:%M')}"

    @admin.display(description="Статус", ordering="status")
    def status_badge(self, obj: Group) -> str:
        css_map = {
            Group.Status.ACTIVE: "ok-badge-success",
            Group.Status.PAUSED: "ok-badge-warning",
            Group.Status.COMPLETED: "ok-badge-muted",
            Group.Status.CANCELLED: "ok-badge-danger",
        }
        css = css_map.get(obj.status, "ok-badge-muted")
        return format_html(
            '<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>',
            css,
            obj.get_status_display(),
        )


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ("date", "time_range", "group", "teacher", "room", "cancelled_badge")
    list_filter = ("date", "group", "room", "group__teacher", "is_cancelled")
    search_fields = ("group__name", "group__teacher__user__first_name", "group__teacher__user__last_name")
    date_hierarchy = "date"
    ordering = ("date", "start_time")
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("group", "room")
    list_per_page = 25

    fieldsets = (
        ("Занятие", {"fields": ("group", "date", "start_time", "end_time", "room")}),
        ("Отмена", {"fields": ("is_cancelled", "cancellation_reason")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("group__teacher__user", "room")

    @admin.display(description="Время")
    def time_range(self, obj: Schedule) -> str:
        return f"{obj.start_time.strftime('%H:%M')}–{obj.end_time.strftime('%H:%M')}"

    @admin.display(description="Тренер", ordering="group__teacher")
    def teacher(self, obj: Schedule):
        return obj.group.teacher

    @admin.display(description="Статус")
    def cancelled_badge(self, obj: Schedule) -> str:
        css, label = ("ok-badge-danger", "Отменено") if obj.is_cancelled else ("ok-badge-success", "Проведено")
        return format_html(
            '<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>', css, label
        )


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("date", "student", "group", "status_badge", "comment_short")
    list_filter = ("date", "group", "status")
    search_fields = ("student__first_name", "student__last_name", "group__name")
    date_hierarchy = "date"
    ordering = ("-date",)
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("student", "group")
    list_per_page = 30

    fieldsets = (
        ("Запись", {"fields": ("group", "student", "date", "status", "comment")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("student", "group")

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
        css = css_map.get(obj.status, "ok-badge-muted")
        return format_html(
            '<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}</span>',
            css,
            obj.get_status_display(),
        )


# ---------------------------------------------------------------------------
# Homework
# ---------------------------------------------------------------------------

@admin.register(Homework)
class HomeworkAdmin(admin.ModelAdmin):
    list_display = ("date", "student", "group", "score_badge", "comment_short")
    list_filter = ("date", "group")
    search_fields = ("student__first_name", "student__last_name", "group__name")
    date_hierarchy = "date"
    ordering = ("-date",)
    readonly_fields = ("created_at", "updated_at")
    autocomplete_fields = ("student", "group")
    list_per_page = 30

    fieldsets = (
        ("Результат", {"fields": ("group", "student", "date", "score", "comment")}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("student", "group")

    @admin.display(description="Комментарий")
    def comment_short(self, obj: Homework) -> str:
        if not obj.comment:
            return "—"
        return obj.comment if len(obj.comment) <= 40 else f"{obj.comment[:40]}..."

    @admin.display(description="Результат", ordering="score")
    def score_badge(self, obj: Homework) -> str:
        if obj.score >= 8:
            css = "ok-badge-success"
        elif obj.score >= 5:
            css = "ok-badge-warning"
        else:
            css = "ok-badge-danger"
        return format_html(
            '<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}/10</span>', css, obj.score
        )


# ---------------------------------------------------------------------------
# KPI
# ---------------------------------------------------------------------------

@admin.register(KPI)
class KPIAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "group",
        "period",
        "attendance_badge",
        "homework_badge",
        "average_score_badge",
    )
    list_filter = ("group", "student")
    search_fields = ("student__first_name", "student__last_name", "group__name")
    ordering = ("-date_to",)
    readonly_fields = ("created_at", "updated_at", "analytics_display")
    autocomplete_fields = ("student", "group")
    list_per_page = 25

    fieldsets = (
        ("Период", {"fields": ("student", "group", "date_from", "date_to")}),
        ("Аналитика", {"fields": ("analytics_display",)}),
        ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("student", "group")

    @admin.display(description="Период")
    def period(self, obj: KPI) -> str:
        return f"{obj.date_from.strftime('%d.%m.%Y')} — {obj.date_to.strftime('%d.%m.%Y')}"

    def _attendance(self, obj: KPI) -> dict:
        return calculate_attendance_stats(obj.student_id, obj.group_id, obj.date_from, obj.date_to)

    def _homework(self, obj: KPI) -> dict:
        return calculate_homework_stats(obj.student_id, obj.group_id, obj.date_from, obj.date_to)

    @admin.display(description="Посещаемость")
    def attendance_badge(self, obj: KPI) -> str:
        pct = self._attendance(obj)["attendance_percentage"]
        css = "ok-badge-success" if pct >= 80 else "ok-badge-warning" if pct >= 50 else "ok-badge-danger"
        return format_html(
            '<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}%</span>', css, pct
        )

    @admin.display(description="Домашние задания")
    def homework_badge(self, obj: KPI) -> str:
        pct = self._homework(obj)["homework_percentage"]
        css = "ok-badge-success" if pct >= 80 else "ok-badge-warning" if pct >= 50 else "ok-badge-danger"
        return format_html(
            '<span class="ok-badge {}"><span class="ok-badge-dot"></span>{}%</span>', css, pct
        )

    @admin.display(description="Средний балл")
    def average_score_badge(self, obj: KPI) -> str:
        avg = self._homework(obj)["average_score"]
        return f"{avg}/10"

    @admin.display(description="Аналитика за период")
    def analytics_display(self, obj: Group) -> str:
        if not obj.pk:
            return "Аналитика появится после сохранения периода."

        attendance = self._attendance(obj)
        homework = self._homework(obj)

        return format_html(
            '<div style="display:flex; gap:2rem; flex-wrap:wrap;">'
            '<div>'
            '<div style="font-weight:600; margin-bottom:0.35rem;">Посещаемость</div>'
            '<div>Всего занятий: <strong>{}</strong></div>'
            '<div>Присутствовал: <strong>{}</strong></div>'
            '<div>Отсутствовал: <strong>{}</strong></div>'
            '<div>Опоздал: <strong>{}</strong></div>'
            '<div>Уважительная причина: <strong>{}</strong></div>'
            '<div>Посещаемость: <strong>{}%</strong></div>'
            "</div>"
            '<div>'
            '<div style="font-weight:600; margin-bottom:0.35rem;">Домашние задания</div>'
            '<div>Всего записей: <strong>{}</strong></div>'
            '<div>Средний балл: <strong>{}/10</strong></div>'
            '<div>Выполнение: <strong>{}%</strong></div>'
            "</div>"
            "</div>",
            attendance["total_lessons"],
            attendance["present"],
            attendance["absent"],
            attendance["late"],
            attendance["excused"],
            attendance["attendance_percentage"],
            homework["total_records"],
            homework["average_score"],
            homework["homework_percentage"],
        )
