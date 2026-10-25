"""Django Admin → «Платёжные профили студентов» → «Удалить профиль из
бухгалтерии»: предварительный отчёт и подтверждение (`services.profile_purge`).

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


def purge_view(request, pk: int, admin_site):
    guard(request)
    profile = get_object_or_404(StudentBillingProfile.objects.select_related("student", "plan"), pk=pk)
    report = profile_purge.preview(profile, actor=request.user)
    form = PurgeForm(initial={"fingerprint": report["fingerprint"]}, student=profile.student)
    if request.method == "POST":
        form = PurgeForm(request.POST, student=profile.student)
        if form.is_valid() and report["can_delete"]:
            try:
                deleted = profile_purge.purge(profile, actor=request.user, reason=form.cleaned_data["reason"],
                                              fingerprint=form.cleaned_data["fingerprint"])
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
        "form": form, "opts": StudentBillingProfile._meta,
    })


__all__ = ["DENIED", "guard", "purge_view"]
