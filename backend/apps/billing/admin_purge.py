"""Django Admin → «Платёжные профили студентов» → «Удалить профиль из
бухгалтерии»: предварительный отчёт и подтверждение (`services.profile_purge`).

Два режима: обычное удаление (профиль без проведённых платежей) и «Полный
сброс» (удаляются и проведённые платежи с чеками — отдельное подтверждение
фразой, списком показанных платежей и отметкой о закрытых периодах).

Доступ — ТОЛЬКО суперпользователь Django (`is_superuser`). Проверяется в
трёх местах независимо: действие списка не показывается и при вызове
отказывает, страница отчёта / подтверждения отвечает 403 на GET и POST,
сам сервис отказывает любому другому пользователю. Разрешения, роль
бухгалтера, директора или `is_staff` доступа не дают.
"""
from __future__ import annotations

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .models import StudentBillingProfile
from .services import BillingError, profile_purge

DENIED = "Удалить профиль из бухгалтерии может только суперпользователь."


def guard(request) -> None:
    if not profile_purge.is_allowed(request.user):
        raise PermissionDenied(DENIED)


class PurgeForm(forms.Form):
    fingerprint = forms.CharField(widget=forms.HiddenInput)
    reason = forms.CharField(label="Причина удаления", widget=forms.Textarea(attrs={"rows": 2}), strip=True)
    last_name = forms.CharField(label="Для подтверждения введите фамилию ученика", strip=True,
                                widget=forms.TextInput(attrs={"autocomplete": "off"}))

    def __init__(self, *args, student, **kwargs):
        super().__init__(*args, **kwargs)
        self.student = student

    def clean_last_name(self):
        value = self.cleaned_data["last_name"]
        if value.casefold() != (self.student.last_name or "").strip().casefold():
            raise forms.ValidationError("Фамилия не совпадает.")
        return value


class FullResetForm(PurgeForm):
    payment_ids = forms.CharField(widget=forms.HiddenInput)
    phrase = forms.CharField(label=f"Введите «{profile_purge.FULL_PHRASE}»", strip=True,
                             widget=forms.TextInput(attrs={"autocomplete": "off"}))
    money_acknowledged = forms.BooleanField(
        label="Понимаю: проведённые платежи и чеки будут удалены из учёта и отчётов о поступлениях; "
              "реальные деньги внесу заново в новый профиль", required=True)
    confirm_closed_period = forms.BooleanField(
        label="Подтверждаю удаление платежей из утверждённого / закрытого расчётного периода", required=False)

    def clean_phrase(self):
        value = self.cleaned_data["phrase"]
        if value != profile_purge.FULL_PHRASE:
            raise forms.ValidationError(f"Нужно ввести ровно «{profile_purge.FULL_PHRASE}».")
        return value

    def payment_list(self) -> list[int]:
        return [int(pk) for pk in self.cleaned_data["payment_ids"].split(",") if pk.strip().isdigit()]


def _initial(report) -> dict:
    return {"fingerprint": report["fingerprint"],
            "payment_ids": ",".join(str(p["id"]) for p in report["real_money"])}


def purge_view(request, pk: int, admin_site):
    guard(request)
    profile = get_object_or_404(StudentBillingProfile.objects.select_related("student", "plan"), pk=pk)
    report = profile_purge.preview(profile, actor=request.user)
    form = PurgeForm(initial=_initial(report), student=profile.student)
    full_form = FullResetForm(initial=_initial(report), student=profile.student)
    if request.method == "POST":
        full = request.POST.get("mode") == "full"
        bound = (FullResetForm if full else PurgeForm)(request.POST, student=profile.student)
        if full:
            full_form = bound
        else:
            form = bound
        allowed = report["full_reset_available"] if full else report["can_delete"]
        if bound.is_valid() and allowed:
            options = {"full_reset": True, "confirmed_payment_ids": bound.payment_list(),
                       "confirm_closed_period": bound.cleaned_data["confirm_closed_period"]} if full else {}
            try:
                deleted = profile_purge.purge(profile, actor=request.user, reason=bound.cleaned_data["reason"],
                                              fingerprint=bound.cleaned_data["fingerprint"], **options)
            except BillingError as exc:
                messages.error(request, f"Удаление не выполнено, изменения отменены. {exc.message}")
                report = profile_purge.preview(profile, actor=request.user)
            else:
                messages.success(request, f"Профиль «{report['student']}» удалён из бухгалтерии "
                                          f"(записей: {sum(deleted.values())}). Данные обучения не изменены; "
                                          "копия удалённых записей — в журнале аудита.")
                return redirect(reverse("admin:billing_studentbillingprofile_changelist"))
    return render(request, "admin/billing/profile_purge.html", {
        **admin_site.each_context(request), "title": "Удалить профиль из бухгалтерии", "report": report,
        "form": form, "full_form": full_form, "opts": StudentBillingProfile._meta,
    })


__all__ = ["DENIED", "guard", "purge_view"]
