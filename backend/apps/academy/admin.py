from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from apps.users.import_export.formats import UnsupportedFileFormat

from .admin_views import analytics_view, generate_lessons_for_group_view, schedule_view
from .constants import WEEKDAY_CODES, WEEKDAY_LABELS_SHORT
from .models import (
    Attendance,
    Course,
    CourseLessonPlan,
    Group,
    GroupSchedule,
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
    """The `days_of_week` model field has no form field of its own here on
    purpose — it's part of the read-only legacy compatibility block (see
    GroupAdmin.readonly_fields/legacy_days_of_week_display): an admin
    creating or editing a Group can no longer accidentally configure a new
    group's schedule through it. Real schedule configuration always goes
    through a Teaching Program (models.GroupSchedule), added below."""

    students = forms.ModelMultipleChoiceField(
        queryset=Student.objects.filter(is_active=True),
        required=False,
        label="Выбор студентов",
        help_text=(
            "Студенты принадлежат группе и могут посещать разные учебные программы "
            "внутри этой группы. Начните вводить имя, чтобы найти студента."
        ),
        widget=forms.SelectMultiple(
            attrs={"class": "ok-multiselect-source", "data-placeholder": "Поиск студента..."}
        ),
    )

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
            "end_date": (
                "Общий период существования группы. Расписание занятий настраивается "
                "отдельно для каждой учебной программы ниже."
            ),
            "max_students": "Оставьте пустым, если количество студентов не ограничено.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
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


class GroupScheduleInline(admin.TabularInline):
    """Every recurring schedule slot of the group — each row is one учебной
    программы (teacher + subject, see models.GroupTeacher) time slot, and
    every row is equally editable/removable here. Add as many teachers as
    the group needs: several rows with the same teacher+subject are the
    same program's several weekly slots; a new teacher+subject combination
    is automatically its own, independent program (see
    models.GroupSchedule.save())."""

    model = GroupSchedule
    extra = 1
    fields = ("day_of_week", "start_time", "end_time", "teacher", "subject", "room", "is_active")
    autocomplete_fields = ("teacher", "subject", "room")
    verbose_name = "Слот расписания программы"
    verbose_name_plural = "Расписание учебных программ"


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

    list_display = ("group", "teacher", "subject", "active_badge", "plan_progress", "created_at")
    list_filter = ("is_active", "group", "teacher", "subject")
    search_fields = ("group__name", "teacher__user__first_name", "teacher__user__last_name", "subject__name")
    autocomplete_fields = ("group", "teacher", "subject")
    readonly_fields = ("created_at", "updated_at", "is_legacy_primary")
    inlines = [GroupTeacherLessonPlanInline]
    ordering = ("group", "id")
    list_per_page = 30

    fieldsets = (
        ("Тренер / программа", {"fields": ("group", "teacher", "subject", "is_active")}),
        (
            "Системная информация",
            {"fields": ("is_legacy_primary", "created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

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
    """A Group is only a container for identity, course, students, status
    and general period — see module docstring above GroupTeacher in
    models.py. Every real teaching detail (teacher, subject, schedule,
    room, individual plan) lives on its учебные программы (models.
    GroupTeacher/GroupSchedule/GroupTeacherLessonPlan), added below via
    GroupScheduleInline — there is no "main teacher"/"main schedule": every
    program is equally first-class.
    """

    form = GroupAdminForm
    list_display = (
        "name", "course", "teacher_programs_summary",
        "students_count_display", "status_badge", "start_date", "end_date",
    )
    list_filter = ("status", "course", "start_date")
    search_fields = ("name", "teachers__teacher__user__first_name", "teachers__teacher__user__last_name")
    ordering = ("-start_date", "name")
    readonly_fields = (
        "created_at", "updated_at",
        "group_summary", "capacity_summary", "schedule_link_detail", "teaching_programs_summary",
        "teacher", "room", "start_time", "end_time", "legacy_days_of_week_display",
    )
    autocomplete_fields = ("course", "teacher", "room")
    actions = ["generate_lessons_action", "pause_groups", "activate_groups"]
    inlines = [GroupScheduleInline]
    list_per_page = 25

    def get_fieldsets(self, request, obj=None):
        fieldsets = [
            (
                "Основная информация",
                {
                    "fields": ("name", "course", "status", "description"),
                    "description": "Основные данные учебной группы.",
                },
            ),
        ]
        if obj is not None:
            fieldsets.append(("Сводка группы", {"fields": ("group_summary",)}))
        fieldsets += [
            (
                "Период обучения группы",
                {
                    "fields": ("start_date", "end_date"),
                    "description": (
                        "Общий период существования группы. Конкретные даты и время занятий "
                        "задаются отдельно в учебных программах ниже."
                    ),
                },
            ),
            (
                "Студенты",
                {
                    "fields": ("capacity_summary", "max_students", "students"),
                    "description": (
                        "Студенты принадлежат группе и могут посещать разные учебные программы "
                        "внутри этой группы."
                    ),
                },
            ),
            (
                "Тренеры и учебные программы",
                {
                    "fields": ("schedule_link_detail", "teaching_programs_summary"),
                    "description": (
                        "Добавьте каждого тренера отдельной учебной программой (см. «Расписание "
                        "учебных программ» ниже — «+ Добавить ещё одну» добавляет любое число "
                        "тренеров). Каждая программа полностью равноправна и имеет собственный "
                        "предмет, расписание и, по желанию, собственный индивидуальный план "
                        "занятий, независимый от других программ этой группы."
                    ),
                },
            ),
            (
                "Поля для обратной совместимости",
                {
                    "fields": ("teacher", "room", "start_time", "end_time", "legacy_days_of_week_display"),
                    "classes": ("collapse",),
                    "description": mark_safe(
                        '<div class="ok-alert ok-alert-warning"><i class="bi bi-exclamation-triangle"></i>'
                        "<span>Эти поля сохранены только для совместимости со старыми данными. "
                        "Они не влияют на расписание и генерацию занятий и доступны только для "
                        "просмотра. Используйте «Тренеры и учебные программы» выше для любой новой "
                        "настройки.</span></div>"
                    ),
                },
            ),
            ("Системная информация", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
        ]
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

    def save_model(self, request, obj, form, change):
        # Defer lesson generation until save_related() below, once every
        # inline GroupSchedule row (Teacher Program slot) has saved too —
        # otherwise the first Teacher Program alone would greedily consume
        # plan rows meant for another one, generated the instant Group.save()
        # fires and before this same request even gets to add the rest of
        # the schedule.
        obj._defer_schedule_sync = True
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        # Same deferral as save_model, for each GroupSchedule row the
        # inline formset saves (see GroupScheduleInline).
        instances = formset.save(commit=False)
        for obj in instances:
            obj._defer_schedule_sync = True
            obj.save()
        formset.save_m2m()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.save_students()
        # Now that every inline schedule row (Teacher Program slot) is
        # persisted, generate exactly once for the complete picture
        # (idempotent either way, see lesson_generator).
        try:
            generate_lessons_for_group(form.instance)
        except LessonGenerationError:
            pass

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

    @admin.display(description="Просмотр расписания")
    def schedule_link_detail(self, obj: Group) -> str:
        if not obj.pk:
            # Kept terse here on purpose — the full explanation lives once,
            # in teaching_programs_summary just below, to avoid repeating
            # the same callout twice in the same fieldset.
            return "—"
        url = f"{reverse('admin:academy_schedule')}?group={obj.pk}"
        return format_html(
            '<a class="btn btn-outline-success btn-sm" href="{}">'
            '<i class="bi bi-calendar-week"></i> Открыть расписание учебных программ</a>',
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

    @admin.display(description="")
    def group_summary(self, obj: Group) -> str:
        """Read-only "at a glance" panel (spec: GROUP SUMMARY) — every value
        is calculated on the fly from the group's own related data, nothing
        stored or duplicated as a separate KPI record."""
        if not obj.pk:
            return "—"

        students_count = obj.students_count
        capacity_label = f"{students_count} / {obj.max_students}" if obj.max_students else f"{students_count} / ∞"
        programs_count = obj.teachers.filter(is_active=True).count()

        if obj.end_date:
            period_label = f"{obj.start_date:%d.%m.%Y} – {obj.end_date:%d.%m.%Y}"
        else:
            period_label = f"{obj.start_date:%d.%m.%Y} – …"

        today = timezone.localdate()
        upcoming_lessons = obj.lessons.filter(date__gte=today, status=Lesson.Status.PLANNED).count()

        cards = [
            ("bi-mortarboard", "Курс", obj.course.name),
            ("bi-flag", "Статус", obj.get_status_display()),
            ("bi-people", "Студенты", capacity_label),
            ("bi-calendar-range", "Период", period_label),
            ("bi-person-badge", "Учебные программы", str(programs_count)),
            ("bi-calendar-check", "Ближайшие занятия", str(upcoming_lessons)),
        ]
        cards_html = "".join(
            format_html(
                '<div class="ok-kpi-card"><div class="ok-kpi-icon"><i class="bi {}"></i></div>'
                '<div class="ok-kpi-value">{}</div><div class="ok-kpi-label">{}</div></div>',
                icon, value, label,
            )
            for icon, label, value in cards
        )
        return format_html('<div class="ok-kpi-grid" style="margin-bottom:0;">{}</div>', mark_safe(cards_html))

    @admin.display(description="")
    def capacity_summary(self, obj: Group) -> str:
        """Spec §3.C: selected count / capacity used / free places, with a
        clear warning once capacity is exceeded."""
        if not obj.pk:
            return mark_safe(
                '<p class="ok-help-text" style="margin:0 0 0.5rem;">'
                "Количество выбранных студентов появится после сохранения группы.</p>"
            )

        selected = obj.students_count
        if not obj.max_students:
            return format_html(
                '<div class="okan-mini-stats" style="margin:0 0 0.75rem;">'
                '<div class="okan-mini-stat">Выбрано студентов: <strong>{}</strong></div>'
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
            '<div class="okan-mini-stat">Выбрано студентов: <strong>{}</strong></div>'
            '<div class="okan-mini-stat">Вместимость: <strong>{} / {}</strong></div>'
            "<div class=\"okan-mini-stat\">{}</div>"
            "</div>",
            selected, selected, obj.max_students, capacity_badge,
        )

    @admin.display(description="Дни недели (устар.)")
    def legacy_days_of_week_display(self, obj: Group) -> str:
        if not obj.days_of_week:
            return "—"
        day_labels = dict(DAY_CHOICES)
        return ", ".join(day_labels.get(day, day) for day in obj.days_of_week)

    @admin.display(description="")
    def teaching_programs_summary(self, obj: Group) -> str:
        """Every Teaching Program of this group, rendered as equal-weight
        cards — no field or ordering here marks one program as more
        "primary" than another (spec §4/§5)."""
        if not obj.pk:
            return mark_safe(
                '<div class="ok-alert ok-alert-warning"><i class="bi bi-info-circle"></i>'
                "<span>Сначала сохраните группу, затем добавьте учебные программы ниже.</span></div>"
            )

        day_labels = dict(DAY_CHOICES)
        programs = list(
            obj.teachers.select_related("teacher__user", "subject").prefetch_related("schedules")
        )
        if not programs:
            return mark_safe(
                '<div class="ok-alert ok-alert-warning"><i class="bi bi-exclamation-triangle"></i>'
                "<span>У группы пока нет ни одной учебной программы. Добавьте тренера через "
                "«Расписание учебных программ» ниже — она появится здесь автоматически.</span></div>"
            )

        cards = []
        for index, group_teacher in enumerate(programs, start=1):
            active_slots = sorted(
                (s for s in group_teacher.schedules.all() if s.is_active),
                key=lambda s: (WEEKDAY_CODES.index(s.day_of_week), s.start_time),
            )
            schedule_rows = "".join(
                format_html(
                    '<div>{} {}–{} · {}</div>',
                    day_labels.get(s.day_of_week, s.day_of_week), s.start_time.strftime("%H:%M"),
                    s.end_time.strftime("%H:%M"), s.room.name if s.room_id else "без аудитории",
                )
                for s in active_slots
            )
            plan_count = group_teacher.lesson_plans.count()
            plan_badge = (
                _badge("ok-badge-success", f"Свой план: {plan_count} занятий")
                if plan_count
                else _badge("ok-badge-muted", "Общий план курса")
            )
            status_badge = (
                _badge("ok-badge-success", "Активна") if group_teacher.is_active else _badge("ok-badge-danger", "Неактивна")
            )
            lesson_count = Lesson.objects.filter(group_teacher=group_teacher).count()

            plan_url = reverse("admin:academy_groupteacher_change", args=[group_teacher.pk])
            lessons_url = f"{reverse('admin:academy_lesson_changelist')}?group_teacher__id__exact={group_teacher.pk}"

            cards.append(
                format_html(
                    '<div class="ok-card" style="margin-bottom:0.85rem;">'
                    '<div class="ok-card-header">Учебная программа №{} — {} {}</div>'
                    '<div class="ok-card-body">'
                    '<div style="margin-bottom:0.5rem;"><strong>Тренер:</strong> {}'
                    '<span style="margin-left:0.75rem;"><strong>Предмет:</strong> {}</span></div>'
                    '<div style="margin-bottom:0.5rem;"><strong>Расписание:</strong>{}</div>'
                    '<div style="margin-bottom:0.75rem;">{}</div>'
                    '<a class="btn btn-outline-success btn-sm" href="{}">Расписание и план занятий →</a> '
                    '<a class="btn btn-outline-success btn-sm" href="{}">Занятия ({}) →</a>'
                    "</div></div>",
                    index, group_teacher.subject.name if group_teacher.subject_id else "без предмета", status_badge,
                    group_teacher.teacher, group_teacher.subject.name if group_teacher.subject_id else "—",
                    mark_safe(schedule_rows) if schedule_rows else " нет активных слотов",
                    plan_badge,
                    plan_url, lessons_url, lesson_count,
                )
            )
        return mark_safe("".join(cards))

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
