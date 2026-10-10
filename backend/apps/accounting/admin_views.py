"""Django Admin: Бухгалтерия → Обслуживание базы данных → Очистка данных.

Только суперпользователь (проверка в самом представлении, не только в меню).
Перед удалением показываются количества записей по каждой таблице; нужно
ввести `DELETE ACCOUNTING` и подтвердить наличие резервной копии, для полной
очистки — дополнительно `FULL RESET`. Если с момента открытия страницы
количества изменились, удаление не выполняется и страница показывает новые.
Само удаление — services.maintenance.purge (одна транзакция, откат при ошибке).
"""
from __future__ import annotations

import json

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse

from .services import AccountingError, maintenance


def _fingerprint(counts: dict) -> str:
    """Снимок количеств всех таблиц бухгалтерии на момент показа страницы."""
    return json.dumps(counts, sort_keys=True)


class PurgeForm(forms.Form):
    mode = forms.ChoiceField(choices=[(maintenance.PAYROLL, "Расчёты зарплаты"), (maintenance.FULL, "Полная очистка")],
                             widget=forms.HiddenInput)
    snapshot = forms.CharField(widget=forms.HiddenInput)
    confirm_phrase = forms.CharField(
        label=f"Введите «{maintenance.CONFIRM_PHRASE}»", max_length=40, strip=True,
        widget=forms.TextInput(attrs={"autocomplete": "off", "class": "ok-input"}),
    )
    backup_confirmed = forms.BooleanField(
        label="Резервная копия базы данных сделана; понимаю, что без неё операция необратима", required=True,
    )
    full_phrase = forms.CharField(
        label=f"Дополнительное подтверждение полной очистки: введите «{maintenance.FULL_CONFIRM_PHRASE}»",
        max_length=40, strip=True, required=False,
        widget=forms.TextInput(attrs={"autocomplete": "off", "class": "ok-input"}),
    )
    include_tariffs = forms.BooleanField(label="Также удалить историю тарифов курсов", required=False)

    def clean_confirm_phrase(self):
        value = self.cleaned_data["confirm_phrase"]
        if value != maintenance.CONFIRM_PHRASE:
            raise forms.ValidationError(f"Нужно ввести ровно «{maintenance.CONFIRM_PHRASE}».")
        return value

    def clean(self):
        data = super().clean()
        if data.get("mode") == maintenance.FULL and data.get("full_phrase") != maintenance.FULL_CONFIRM_PHRASE:
            self.add_error("full_phrase", f"Для полной очистки введите ровно «{maintenance.FULL_CONFIRM_PHRASE}».")
        if data.get("mode") != maintenance.FULL:
            data["include_tariffs"] = False
        return data


def _rows(tables, counts):
    return [{"label": t.label, "db_table": t.db_table, "count": counts[t.key], "note": t.note} for t in tables]


def _modes(counts: dict) -> list[dict]:
    return [
        {
            "key": maintenance.PAYROLL,
            "title": "Режим A — Очистить расчёты зарплаты",
            "delete": _rows(maintenance.tables_to_delete(maintenance.PAYROLL), counts),
            "keep": _rows(maintenance.tables_kept(maintenance.PAYROLL), counts),
            "notes": [
                "Завершённые циклы курсов сохраняются: при следующем расчёте зарплаты начисления за них будут "
                "созданы заново по действующим правилам и тарифам.",
            ],
        },
        {
            "key": maintenance.FULL,
            "title": "Режим B — Полная очистка бухгалтерии",
            "delete": _rows(maintenance.tables_to_delete(maintenance.FULL), counts),
            "keep": _rows(maintenance.tables_kept(maintenance.FULL), counts),
            "tariffs": _rows([maintenance.TARIFF_TABLE], counts)[0],
            "notes": [
                "Пользователи, тренеры, группы, курсы, предметы, уроки и посещаемость не удаляются.",
            ],
        },
    ]


def purge_view(request, admin_site):
    if not (request.user.is_active and request.user.is_superuser):
        raise PermissionDenied("Очистка данных бухгалтерии доступна только суперпользователю.")
    counts = maintenance.preview()
    errors: dict[str, PurgeForm] = {}
    if request.method == "POST":
        form = PurgeForm(request.POST)
        if form.is_valid():
            mode, tariffs = form.cleaned_data["mode"], form.cleaned_data["include_tariffs"]
            if form.cleaned_data["snapshot"] != _fingerprint(counts):
                messages.error(request, "Количество записей изменилось с момента открытия страницы. "
                                        "Проверьте новые цифры и подтвердите ещё раз.")
            else:
                try:
                    deleted = maintenance.purge(mode, actor=request.user, include_tariffs=tariffs)
                except Exception as exc:  # noqa: BLE001 — откат уже выполнен транзакцией
                    message = exc.message if isinstance(exc, AccountingError) else f"{type(exc).__name__}: {exc}"
                    messages.error(request, f"Очистка не выполнена, изменения отменены. {message}")
                else:
                    total = sum(deleted.values())
                    details = ", ".join(f"{k}: {v}" for k, v in deleted.items() if v) or "нечего было удалять"
                    messages.success(request, f"Удалено записей: {total} ({details}).")
                    return redirect(reverse("admin:accounting_maintenance_purge"))
        errors[request.POST.get("mode", "")] = form
    context = {
        **admin_site.each_context(request),
        "title": "Очистка данных бухгалтерии",
        "modes": _modes(counts),
        "forms": {m: errors.get(m) or PurgeForm(initial={"mode": m}) for m in (maintenance.PAYROLL, maintenance.FULL)},
        "snapshot": _fingerprint(counts),
        "confirm_phrase": maintenance.CONFIRM_PHRASE,
        "full_phrase": maintenance.FULL_CONFIRM_PHRASE,
    }
    return render(request, "admin/accounting/maintenance_purge.html", context)
