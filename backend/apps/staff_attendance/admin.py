"""Django admin учёта прихода и ухода.

* Конфигурация — офисы и QR, общие настройки (требования к отметке: GPS,
  офисная сеть), личные расписания, исключения из графика, учёт сотрудника
  (включение, исключение из расчётов) — добавлять, менять и удалять может
  ТОЛЬКО суперпользователь (`SuperuserConfigAdmin`). Остальным, у кого есть
  право просмотра, — только просмотр. Те же правила в API (access.can_manage).
* Сессии, события, исправления, журнал и разрешения «Отпросился» — только
  просмотр: исправления — через API с причиной, разрешения — в кабинете
  операционного директора (с аудитом)."""
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.forms.models import model_to_dict
from django.http import JsonResponse
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html

from apps.users.models import User

from .admin_forms import WorkScheduleAdminForm, employee_card, employee_label
from .models import (
    WEEKDAY_SHORT,
    AttendanceAdjustment,
    AttendanceAdminLog,
    AttendanceEmployeeSettings,
    AttendanceEvent,
    AttendancePermission,
    AttendanceLocation,
    AttendanceScheduleException,
    AttendanceSession,
    AttendanceSettings,
    AttendanceWorkSchedule,
)


class SuperuserConfigAdmin(admin.ModelAdmin):
    """Изменять конфигурацию учёта может только суперпользователь —
    независимо от роли и выданных Django-прав."""

    def has_add_permission(self, request, *args):
        return request.user.is_active and request.user.is_superuser and super().has_add_permission(request, *args)

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser and super().has_delete_permission(request, obj)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AttendanceLocation)
class AttendanceLocationAdmin(SuperuserConfigAdmin):
    list_display = ("name", "latitude", "longitude", "radius_m", "is_active", "code")
    list_filter = ("is_active",)
    readonly_fields = ("code", "created_at", "updated_at")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AttendanceSettings)
class AttendanceSettingsAdmin(SuperuserConfigAdmin):
    list_display = ("__str__", "timezone", "work_start", "work_end", "late_grace_minutes", "max_gps_accuracy_m")
    readonly_fields = ("updated_at", "updated_by")

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not AttendanceSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AttendanceWorkSchedule)
class AttendanceWorkScheduleAdmin(SuperuserConfigAdmin):
    """Личные расписания: форма для HR — сотрудник через поиск, дни недели
    карточками, часы по дням, перерыв, льготное время и период действия.
    Шаблон: templates/admin/staff_attendance/attendanceworkschedule/."""

    form = WorkScheduleAdminForm
    list_display = ("employee", "days_display", "hours_display", "break_display", "grace_display",
                    "period_display", "status_display")
    list_display_links = ("employee",)
    list_filter = ("is_active", "user__role")
    search_fields = ("user__username", "user__first_name", "user__last_name", "note")
    list_select_related = ("user", "user__salary_profile", "user__teacher_profile")
    readonly_fields = ("updated_at", "updated_by")
    ordering = ("user__last_name", "user__first_name")
    SEARCH_PAGE_SIZE = 20

    class Media:
        css = {"all": ("admin/css/vendor/select2/select2.min.css", "staff_attendance/admin/schedule.css")}
        js = ("admin/js/vendor/jquery/jquery.min.js", "admin/js/vendor/select2/select2.full.min.js",
              "admin/js/vendor/select2/i18n/ru.js", "admin/js/jquery.init.js",
              "staff_attendance/admin/schedule.js")

    # -- список ------------------------------------------------------------

    @admin.display(description="Сотрудник", ordering="user__last_name")
    def employee(self, obj):
        card = employee_card(obj.user)
        sub = " · ".join(p for p in (card["position"], card["department"]) if p)
        return format_html('<strong>{}</strong><div class="ok-ws-list-sub">{}</div>', card["full_name"], sub)

    @admin.display(description="Рабочие дни")
    def days_display(self, obj):
        return format_days(obj.work_days)

    @admin.display(description="Часы")
    def hours_display(self, obj):
        hours = {obj.hours_for(d) for d in obj.work_days or []}
        hours.discard(None)
        if len(hours) > 1:
            return format_html('{}–{} <span class="ok-badge ok-badge-info">по дням</span>',
                               f"{obj.work_start:%H:%M}", f"{obj.work_end:%H:%M}")
        return f"{obj.work_start:%H:%M}–{obj.work_end:%H:%M}"

    @admin.display(description="Перерыв")
    def break_display(self, obj):
        if obj.break_start and obj.break_end:
            return f"{obj.break_start:%H:%M}–{obj.break_end:%H:%M}"
        return "—"

    @admin.display(description="Льгота", ordering="late_grace_minutes")
    def grace_display(self, obj):
        if obj.late_grace_minutes is None:
            return format_html('<span class="ok-ws-muted">{}</span>', "общая")
        return f"{obj.late_grace_minutes} мин"

    @admin.display(description="Период действия")
    def period_display(self, obj):
        if not obj.valid_from and not obj.valid_until:
            return "Бессрочно"
        start = f"с {obj.valid_from:%d.%m.%Y}" if obj.valid_from else ""
        end = f"по {obj.valid_until:%d.%m.%Y}" if obj.valid_until else ""
        return " ".join(p for p in (start, end) if p)

    @admin.display(description="Статус", ordering="is_active")
    def status_display(self, obj):
        today = timezone.localdate()
        if not obj.is_active:
            return format_html('<span class="ok-badge ok-badge-muted"><span class="ok-badge-dot"></span>{}</span>',
                               "Выключено")
        if obj.valid_from and today < obj.valid_from:
            return format_html('<span class="ok-badge ok-badge-info"><span class="ok-badge-dot"></span>{}</span>',
                               "Запланировано")
        if obj.valid_until and today > obj.valid_until:
            return format_html('<span class="ok-badge ok-badge-warning"><span class="ok-badge-dot"></span>{}</span>',
                               "Истекло")
        return format_html('<span class="ok-badge ok-badge-success"><span class="ok-badge-dot"></span>{}</span>',
                           "Действует")

    # -- поиск сотрудника (Select2) ---------------------------------------

    def get_urls(self):
        info = self.opts.app_label, self.opts.model_name
        return [
            path("employee-search/", self.admin_site.admin_view(self.employee_search_view),
                 name="%s_%s_employee_search" % info),
            *super().get_urls(),
        ]

    def employee_search_view(self, request):
        if not (self.has_add_permission(request) or self.has_change_permission(request)):
            raise PermissionDenied
        term = (request.GET.get("term") or "").strip()
        try:
            page = max(1, int(request.GET.get("page") or 1))
        except ValueError:
            page = 1
        try:
            current = int(request.GET.get("current") or 0)
        except ValueError:
            current = 0
        qs = (User.objects.staff().filter(is_active=True)
              .select_related("salary_profile", "teacher_profile", "attendance_schedule")
              .order_by("last_name", "first_name", "username"))
        for word in term.split()[:5]:
            qs = qs.filter(Q(first_name__icontains=word) | Q(last_name__icontains=word)
                           | Q(username__icontains=word) | Q(email__icontains=word)
                           | Q(salary_profile__position__icontains=word)
                           | Q(teacher_profile__position__icontains=word))
        offset = (page - 1) * self.SEARCH_PAGE_SIZE
        users = list(qs[offset:offset + self.SEARCH_PAGE_SIZE + 1])
        results = []
        for user in users[:self.SEARCH_PAGE_SIZE]:
            card = employee_card(user)
            has_schedule = hasattr(user, "attendance_schedule") and user.pk != current
            results.append({**card, "text": employee_label(user), "has_schedule": has_schedule,
                            "disabled": has_schedule})
        return JsonResponse({"results": results, "pagination": {"more": len(users) > self.SEARCH_PAGE_SIZE}})

    # -- сохранение: кто изменил + журнал, как в API -----------------------

    def save_model(self, request, obj, form, change):
        from .views import _diff, _log

        before = model_to_dict(AttendanceWorkSchedule.objects.get(pk=obj.pk)) if change else {}
        obj.updated_by = request.user
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            _log(request.user, "schedule_update", obj, _diff(before, model_to_dict(obj)))

    def delete_model(self, request, obj):
        from .views import _diff, _log

        with transaction.atomic():
            _log(request.user, "schedule_delete", obj, _diff({}, model_to_dict(obj)))
            super().delete_model(request, obj)

    def render_change_form(self, request, context, add=False, change=False, form_url="", obj=None):
        config = AttendanceSettings.load()
        context.update({
            "global_grace": config.late_grace_minutes,
            "global_hours": f"{config.work_start:%H:%M}–{config.work_end:%H:%M}",
            "global_days": format_days(config.work_days),
        })
        return super().render_change_form(request, context, add, change, form_url, obj)


def format_days(days) -> str:
    """[0, 1, 2, 3, 4] → «Пн–Пт», [0, 2, 4] → «Пн, Ср, Пт»."""
    days = sorted(set(days or []))
    if not days:
        return "—"
    groups, run = [], [days[0]]
    for day in days[1:]:
        if day == run[-1] + 1:
            run.append(day)
        else:
            groups.append(run)
            run = [day]
    groups.append(run)
    parts = []
    for group in groups:
        if len(group) >= 3:
            parts.append(f"{WEEKDAY_SHORT[group[0]]}–{WEEKDAY_SHORT[group[-1]]}")
        else:
            parts.extend(WEEKDAY_SHORT[d] for d in group)
    return ", ".join(parts)


@admin.register(AttendanceScheduleException)
class AttendanceScheduleExceptionAdmin(SuperuserConfigAdmin):
    """Отпуск, больничный, отгул или особые часы сотрудника на дату / период.
    Действует поверх личного и общего графика: в эти дни опоздания и
    «нет прихода» не считаются (или считаются от особых часов)."""

    list_display = ("user", "kind", "period_display", "hours_display", "note", "created_by")
    list_filter = ("kind", "user__role")
    search_fields = ("user__username", "user__first_name", "user__last_name", "note")
    autocomplete_fields = ("user",)
    date_hierarchy = "date_from"
    list_select_related = ("user", "created_by")
    readonly_fields = ("created_at", "created_by")
    fields = ("user", "kind", ("date_from", "date_to"), ("work_start", "work_end"), "note",
              ("created_at", "created_by"))

    @admin.display(description="Период", ordering="date_from")
    def period_display(self, obj):
        if obj.date_from == obj.date_to:
            return f"{obj.date_from:%d.%m.%Y}"
        return f"{obj.date_from:%d.%m.%Y} – {obj.date_to:%d.%m.%Y}"

    @admin.display(description="Часы")
    def hours_display(self, obj):
        if obj.work_start and obj.work_end:
            return f"{obj.work_start:%H:%M}–{obj.work_end:%H:%M}"
        return "—"

    def save_model(self, request, obj, form, change):
        from .views import _diff, _log

        before = model_to_dict(AttendanceScheduleException.objects.get(pk=obj.pk)) if change else {}
        if not change:
            obj.created_by = request.user
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            _log(request.user, "schedule_exception_update", obj, _diff(before, model_to_dict(obj)))

    def delete_model(self, request, obj):
        from .views import _diff, _log

        with transaction.atomic():
            _log(request.user, "schedule_exception_delete", obj, _diff({}, model_to_dict(obj)))
            super().delete_model(request, obj)


@admin.register(AttendanceEmployeeSettings)
class AttendanceEmployeeSettingsAdmin(SuperuserConfigAdmin):
    """Учёт конкретного сотрудника: включён ли (отмечается ли он вообще) и
    учитывается ли в расчётах посещаемости, опозданий и KPI."""

    list_display = ("user", "tracking_enabled", "excluded_from_calculations", "note", "updated_at", "updated_by")
    list_filter = ("tracking_enabled", "excluded_from_calculations", "user__role")
    search_fields = ("user__username", "user__first_name", "user__last_name", "note")
    autocomplete_fields = ("user",)
    list_select_related = ("user", "updated_by")
    readonly_fields = ("updated_at", "updated_by")

    def save_model(self, request, obj, form, change):
        from .views import _diff, _log

        before = model_to_dict(AttendanceEmployeeSettings.objects.get(pk=obj.pk)) if change else {}
        obj.updated_by = request.user
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            _log(request.user, "employee_settings_update", obj, _diff(before, model_to_dict(obj)))

    def delete_model(self, request, obj):
        from .views import _diff, _log

        with transaction.atomic():
            _log(request.user, "employee_settings_delete", obj, _diff({}, model_to_dict(obj)))
            super().delete_model(request, obj)


@admin.register(AttendancePermission)
class AttendancePermissionAdmin(ReadOnlyAdmin):
    """История «Отпросился». Создание и отмена — в кабинете операционного
    директора (API пишет аудит); здесь — только просмотр."""

    list_display = ("user", "kind", "starts_at", "ends_at", "status", "reason", "approved_by", "cancelled_by")
    list_filter = ("status", "kind", "user__role")
    search_fields = ("user__username", "user__first_name", "user__last_name", "reason")
    list_select_related = ("user", "approved_by", "cancelled_by")
    date_hierarchy = "starts_at"


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(ReadOnlyAdmin):
    list_display = ("user", "work_date", "checked_in_at", "checked_out_at", "status", "late_minutes", "is_adjusted")
    list_filter = ("status", "user__role", "is_adjusted", "source", "work_date")
    search_fields = ("user__username", "user__first_name", "user__last_name")
    date_hierarchy = "work_date"


@admin.register(AttendanceEvent)
class AttendanceEventAdmin(ReadOnlyAdmin):
    list_display = ("user", "kind", "occurred_at", "location", "distance_m", "accuracy_m")
    list_filter = ("kind", "user__role")
    search_fields = ("user__username", "user__first_name", "user__last_name")


@admin.register(AttendanceAdjustment)
class AttendanceAdjustmentAdmin(ReadOnlyAdmin):
    list_display = ("session", "action", "adjusted_by", "created_at")
    search_fields = ("session__user__username", "reason")


@admin.register(AttendanceAdminLog)
class AttendanceAdminLogAdmin(ReadOnlyAdmin):
    list_display = ("action", "object_type", "object_id", "actor", "created_at")
