"""Форма личного расписания для Django admin.

Администратор видит понятные элементы — карточки дней недели, таблицу часов
по дням и режим перерыва, — а в модель форма пишет те же поля, что и API:

* `work_days` — список 0…6;
* `work_start`/`work_end` и `break_start`/`break_end` — базовые часы (часы
  понедельника, если он рабочий, иначе первого рабочего дня);
* `day_hours` — только дни, часы которых отличаются от базовых.

Все проверки выполняются на сервере (форма + `AttendanceWorkSchedule.clean`);
JavaScript только помогает заполнять поля.
"""
from __future__ import annotations

from datetime import time

from django import forms
from django.urls import reverse

from apps.users.models import User

from .models import (
    ALL_WEEKDAYS,
    WEEKDAY_LABELS,
    WEEKDAY_SHORT,
    AttendanceSettings,
    AttendanceWorkSchedule,
    DayHours,
    check_day_hours,
    parse_day_hours,
)

TIME_FORMAT = "%H:%M"


class BreakMode:
    NONE = "none"
    SAME = "same"
    PER_DAY = "per_day"
    choices = (
        (NONE, "Без перерыва"),
        (SAME, "Одинаковый для всех дней"),
        (PER_DAY, "Разный по дням"),
    )


# ---------------------------------------------------------------------------
# Сотрудник: ФИО, должность, отдел
# ---------------------------------------------------------------------------

def _related(user, name):
    try:
        return getattr(user, name)
    except Exception:  # RelatedObjectDoesNotExist у обратной OneToOne
        return None


def employee_card(user) -> dict:
    """ФИО, должность и отдел (если известен) для выбора сотрудника.

    Должность — из зарплатного профиля бухгалтерии, затем из профиля тренера,
    иначе — роль в LMS (как в бухгалтерии). Отдел — направление из зарплатного
    профиля; нет профиля — отдел не показывается."""
    salary = _related(user, "salary_profile")
    teacher = _related(user, "teacher_profile")
    role_label = user.get_role_display()
    position = (getattr(salary, "position", "") or getattr(teacher, "position", "") or role_label).strip()
    department = ""
    if salary is not None:
        from apps.accounting.models import Department

        department = Department(salary.effective_department).label
    return {
        "id": user.pk,
        "full_name": user.get_full_name() or user.username,
        "username": user.username,
        "position": position,
        "department": department,
        "role_label": role_label,
    }


def employee_label(user) -> str:
    card = employee_card(user)
    return " · ".join(part for part in (card["full_name"], card["position"], card["department"]) if part)


class EmployeeSelect(forms.Select):
    """Select2 с поиском на сервере. В HTML попадает только выбранный
    сотрудник — список всех пользователей не выгружается на страницу."""

    template_name = "django/forms/widgets/select.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["attrs"].update({
            "data-employee-select": "1",
            "data-search-url": reverse("admin:staff_attendance_attendanceworkschedule_employee_search"),
            "data-placeholder": "Начните вводить имя, должность или логин…",
        })
        return context

    def optgroups(self, name, value, attrs=None):
        selected = {str(v) for v in value if v not in (None, "")}
        options = [self.create_option(name, "", "", not selected, 0)]
        if selected:
            users = User.objects.filter(pk__in=selected).select_related("salary_profile", "teacher_profile")
            for index, user in enumerate(users, start=1):
                options.append(self.create_option(name, str(user.pk), employee_label(user), True, index))
        return [(None, options, 0)]


class EmployeeChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return employee_label(obj)


# ---------------------------------------------------------------------------
# Форма
# ---------------------------------------------------------------------------

def _time_field(label: str) -> forms.TimeField:
    return forms.TimeField(
        label=label, required=False, input_formats=[TIME_FORMAT, "%H:%M:%S"],
        widget=forms.TimeInput(format=TIME_FORMAT, attrs={"type": "time", "class": "ok-ws-time", "step": 60}),
    )


def day_field(weekday: int, part: str) -> str:
    return f"d{weekday}_{part}"


class WorkScheduleAdminForm(forms.ModelForm):
    user = EmployeeChoiceField(
        queryset=User.objects.filter(is_active=True), label="Сотрудник", widget=EmployeeSelect,
        error_messages={"required": "Выберите сотрудника.",
                        "invalid_choice": "Сотрудник не найден или деактивирован."},
    )
    work_days = forms.TypedMultipleChoiceField(
        label="Рабочие дни", choices=[(str(d), WEEKDAY_LABELS[d]) for d in ALL_WEEKDAYS], coerce=int,
        widget=forms.CheckboxSelectMultiple, error_messages={"required": "Выберите хотя бы один рабочий день."},
    )
    break_mode = forms.ChoiceField(label="Перерыв", choices=BreakMode.choices, widget=forms.RadioSelect,
                                   initial=BreakMode.NONE)
    break_start = _time_field("Начало перерыва")
    break_end = _time_field("Конец перерыва")
    late_grace_minutes = forms.IntegerField(
        label="Льготное время опоздания (минуты)", required=False, min_value=0, max_value=240,
        widget=forms.NumberInput(attrs={"min": 0, "max": 240, "step": 1, "inputmode": "numeric"}),
        error_messages={"min_value": "Не может быть меньше 0 минут.",
                        "max_value": "Не больше 240 минут (4 часа).",
                        "invalid": "Введите целое число минут."},
    )
    valid_from = forms.DateField(label="Действует с", required=False,
                                 widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    valid_until = forms.DateField(label="Действует по", required=False,
                                  widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))

    class Meta:
        model = AttendanceWorkSchedule
        fields = ["user", "work_days", "work_start", "work_end", "break_start", "break_end", "day_hours",
                  "late_grace_minutes", "valid_from", "valid_until", "is_active", "note"]
        widgets = {
            # Считаются в clean() из таблицы по дням; на странице не выводятся.
            "work_start": forms.HiddenInput, "work_end": forms.HiddenInput, "day_hours": forms.HiddenInput,
            "note": forms.Textarea(attrs={"rows": 2, "maxlength": 255,
                                          "placeholder": "Например: работает по сокращённому графику до конца испытательного срока"}),
        }
        labels = {"is_active": "Расписание действует", "note": "Комментарий администратора"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = AttendanceSettings.load()
        for name in ("work_start", "work_end", "day_hours"):
            self.fields[name].required = False
        for weekday in ALL_WEEKDAYS:
            label = WEEKDAY_LABELS[weekday]
            self.fields[day_field(weekday, "start")] = _time_field(f"{label}: начало")
            self.fields[day_field(weekday, "end")] = _time_field(f"{label}: окончание")
            self.fields[day_field(weekday, "break_start")] = _time_field(f"{label}: начало перерыва")
            self.fields[day_field(weekday, "break_end")] = _time_field(f"{label}: конец перерыва")
        self.fields["late_grace_minutes"].widget.attrs["placeholder"] = f"{self.config.late_grace_minutes}"
        self._set_initial()

    # -- initial ---------------------------------------------------------

    def _set_initial(self):
        instance = self.instance
        if instance.pk:
            days = list(instance.work_days or [])
            base = instance.base_hours
            try:
                overrides = parse_day_hours(instance.day_hours)
            except Exception:
                overrides = {}
        else:
            days = list(self.config.work_days or [])
            base = DayHours(self.config.work_start, self.config.work_end)
            overrides = {}
            self.initial.setdefault("is_active", True)
        self.initial["work_days"] = [str(d) for d in days]
        per_day = {d: overrides.get(str(d), base) for d in ALL_WEEKDAYS}
        for weekday, hours in per_day.items():
            self.initial[day_field(weekday, "start")] = hours.start
            self.initial[day_field(weekday, "end")] = hours.end
            self.initial[day_field(weekday, "break_start")] = hours.break_start
            self.initial[day_field(weekday, "break_end")] = hours.break_end
        breaks = {(per_day[d].break_start, per_day[d].break_end) for d in days} or {(None, None)}
        if breaks == {(None, None)}:
            mode = BreakMode.NONE
        elif len(breaks) == 1:
            mode = BreakMode.SAME
            self.initial["break_start"], self.initial["break_end"] = next(iter(breaks))
        else:
            mode = BreakMode.PER_DAY
        self.initial["break_mode"] = mode
        if mode != BreakMode.SAME:
            self.initial["break_start"] = self.initial["break_end"] = None

    # -- validation ------------------------------------------------------

    def clean_user(self):
        user = self.cleaned_data["user"]
        duplicate = AttendanceWorkSchedule.objects.filter(user=user).exclude(pk=self.instance.pk).first()
        if duplicate:
            raise forms.ValidationError(
                "У этого сотрудника уже есть личное расписание — откройте его в списке и отредактируйте."
            )
        return user

    def clean_work_days(self):
        return sorted(set(self.cleaned_data["work_days"]))

    def clean(self):
        cleaned = super().clean()
        days = cleaned.get("work_days") or []
        # Строки нерабочих дней скрыты и не сохраняются — их ошибки не мешают.
        for weekday in set(ALL_WEEKDAYS) - set(days):
            for part in ("start", "end", "break_start", "break_end"):
                self._errors.pop(day_field(weekday, part), None)
                cleaned.pop(day_field(weekday, part), None)
        if (cleaned.get("break_mode") or BreakMode.NONE) != BreakMode.SAME:
            for name in ("break_start", "break_end"):
                self._errors.pop(name, None)
        mode = cleaned.get("break_mode") or BreakMode.NONE
        hours_by_day: dict[int, DayHours] = {}
        same_break_errors: dict[str, list[str]] = {}

        for weekday in days:
            start = cleaned.get(day_field(weekday, "start"))
            end = cleaned.get(day_field(weekday, "end"))
            missing = False
            for part, value, message in (("start", start, "Укажите начало рабочего дня."),
                                         ("end", end, "Укажите окончание рабочего дня.")):
                if value is None and day_field(weekday, part) not in self.errors:
                    self.add_error(day_field(weekday, part), message)
                missing = missing or value is None
            if missing:
                continue
            if mode == BreakMode.PER_DAY:
                break_start = cleaned.get(day_field(weekday, "break_start"))
                break_end = cleaned.get(day_field(weekday, "break_end"))
            elif mode == BreakMode.SAME:
                break_start, break_end = cleaned.get("break_start"), cleaned.get("break_end")
            else:
                break_start = break_end = None
            hours = DayHours(start, end, break_start, break_end)
            if mode == BreakMode.SAME:
                errors = check_day_hours(DayHours(start, end))
                for part, message in check_day_hours(hours, WEEKDAY_LABELS[weekday]).items():
                    if part.startswith("break"):
                        same_break_errors.setdefault(part, []).append(message)
            else:
                errors = check_day_hours(hours)
            for part, message in errors.items():
                if not part.startswith("break") or mode == BreakMode.PER_DAY:
                    self.add_error(day_field(weekday, part), message)
            if not errors:
                hours_by_day[weekday] = hours

        if mode == BreakMode.SAME:
            if cleaned.get("break_start") is None and "break_start" not in self.errors:
                self.add_error("break_start", "Укажите начало перерыва.")
            if cleaned.get("break_end") is None and "break_end" not in self.errors:
                self.add_error("break_end", "Укажите конец перерыва.")
            for part, messages in same_break_errors.items():
                if part not in self.errors and cleaned.get("break_start") and cleaned.get("break_end"):
                    # Одна причина на поле: «перерыв вне рабочего времени» для
                    # нескольких дней сводится к одному сообщению со списком дней.
                    self.add_error(part, messages[0] if len(messages) == 1 else
                                   _merge_day_messages(messages))

        if days and len(hours_by_day) == len(days):
            base_day = 0 if 0 in days else days[0]
            base = hours_by_day[base_day]
            cleaned["work_start"], cleaned["work_end"] = base.start, base.end
            cleaned["break_start"], cleaned["break_end"] = base.break_start, base.break_end
            cleaned["day_hours"] = {str(d): h.as_json() for d, h in hours_by_day.items() if h != base}
        else:
            # Ошибки уже показаны у полей таблицы; модель не должна валидировать
            # недостроенное расписание.
            for name in ("work_start", "work_end"):
                cleaned[name] = getattr(self.instance, name, None) or time(0, 0)
            cleaned["break_start"] = cleaned["break_end"] = None
            cleaned["day_hours"] = {}
            if not self.errors:
                self.add_error("work_days", "Выберите хотя бы один рабочий день.")
        return cleaned

    def _post_clean(self):
        if self.errors:
            # Не прогоняем model.clean() поверх незавершённых данных — иначе
            # ошибки скрытых полей продублируют уже показанные.
            return
        super()._post_clean()

    # -- template helpers ------------------------------------------------

    def selected_days(self) -> set[int]:
        if self.is_bound:
            raw = self.data.getlist(self.add_prefix("work_days")) if hasattr(self.data, "getlist") else \
                self.data.get(self.add_prefix("work_days"), [])
        else:
            raw = self.initial.get("work_days", [])
        result = set()
        for value in raw:
            try:
                result.add(int(value))
            except (TypeError, ValueError):
                continue
        return result

    def day_rows(self) -> list[dict]:
        selected = self.selected_days()
        rows = []
        for weekday in ALL_WEEKDAYS:
            fields = {part: self[day_field(weekday, part)] for part in ("start", "end", "break_start", "break_end")}
            rows.append({
                "weekday": weekday,
                "label": WEEKDAY_LABELS[weekday],
                "short": WEEKDAY_SHORT[weekday],
                "selected": weekday in selected,
                "weekend": weekday >= 5,
                **fields,
                "hours_errors": [*fields["start"].errors, *fields["end"].errors],
                "break_errors": [*fields["break_start"].errors, *fields["break_end"].errors],
            })
        return rows

    def day_cards(self) -> list[dict]:
        selected = self.selected_days()
        return [{"widget": widget, "weekday": int(widget.data["value"]), "short": WEEKDAY_SHORT[int(widget.data["value"])],
                 "selected": int(widget.data["value"]) in selected}
                for widget in self["work_days"]]

    def hidden_errors(self) -> list[str]:
        """Ошибки полей, которые не выводятся на странице (на всякий случай)."""
        return [str(e) for name in ("work_start", "work_end", "day_hours") for e in self[name].errors]


def _merge_day_messages(messages: list[str]) -> str:
    days, reason = [], None
    for message in messages:
        day, _, text = message.partition(": ")
        days.append(day)
        reason = reason or text
    return f"{', '.join(days)}: {reason}"
