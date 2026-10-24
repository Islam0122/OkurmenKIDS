"""Django Admin → Платежи студентов → «Управление платежом».

Страница платежа оплаты обучения с действиями бухгалтера: исправить
(дата, сумма, способ, договор, назначение, распределение), исправить дату
создания записи, аннулировать (с подтверждением и причиной), посмотреть и
повторно распечатать чек, история изменений. Формы ничего не сохраняют сами:
каждое действие — сервис (`services.corrections`, `payments.reverse_payment`,
`receipts.mark_printed`) с проверкой прав, блокировками и журналом аудита.
Права проверяет сервис: директор и менеджер получают отказ даже при прямом
POST-запросе.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.accounting.models import StudentPayment

from .models import Invoice, PaymentAllocation, Receipt, StudentBillingProfile
from .permissions import can_view_money, is_billing_accountant
from .services import BillingError, corrections, payments, receipts
from .services.receipt_pdf import receipt_rows, render_receipt_pdf

PURPOSES = [("", "— не менять —"), (StudentPayment.Purpose.TUITION, "Оплата обучения"),
            (StudentPayment.Purpose.PREPAYMENT, "Предоплата / аванс")]


class CorrectForm(forms.Form):
    received_date = forms.DateField(label="Дата фактического поступления денег", required=False,
                                    widget=forms.DateInput(attrs={"type": "date"}))
    amount = forms.DecimalField(label="Сумма, сом", max_digits=14, decimal_places=2, min_value=Decimal("0.01"),
                                required=False)
    method = forms.ChoiceField(label="Способ оплаты", choices=[("", "— не менять —"), *StudentPayment.Method.choices],
                               required=False)
    reference = forms.CharField(label="Номер документа", max_length=100, required=False)
    comment = forms.CharField(label="Комментарий", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    purpose = forms.ChoiceField(label="Назначение", choices=PURPOSES, required=False)
    profile = forms.IntegerField(label="Перенести на договор (id)", required=False,
                                 help_text="Только если платёж ошибочно привязан к другому студенту.")
    allocations = forms.CharField(
        label="Новое распределение", required=False, widget=forms.Textarea(attrs={"rows": 3}),
        help_text="По строке: «номер начисления = сумма», например INV-2026-000083 = 53000. "
                  "Пусто — распределение не меняется.",
    )
    confirm_closed_period = forms.BooleanField(label="Подтверждаю исправление в утверждённом / закрытом периоде",
                                               required=False)
    reason = forms.CharField(label="Причина корректировки", widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, payment: StudentPayment, **kwargs):
        super().__init__(*args, **kwargs)
        self.payment = payment
        self.fields["received_date"].initial = payment.received_date
        self.fields["amount"].initial = payment.amount
        self.fields["reference"].initial = payment.reference
        self.fields["comment"].initial = payment.comment

    def clean_allocations(self):
        text = self.cleaned_data["allocations"].strip()
        if not text:
            return None
        items = []
        for line in text.splitlines():
            if not line.strip():
                continue
            number, _, value = line.partition("=")
            invoice = Invoice.objects.filter(number=number.strip()).first()
            if invoice is None:
                raise forms.ValidationError(f"Начисление {number.strip()} не найдено.")
            try:
                items.append((invoice, Decimal(value.strip().replace(",", "."))))
            except InvalidOperation:
                raise forms.ValidationError(f"Некорректная сумма в строке «{line}».")
        return items

    def service_kwargs(self) -> dict:
        data, p = self.cleaned_data, self.payment
        kwargs = {"reason": data["reason"], "confirm_closed_period": data["confirm_closed_period"]}
        if data["received_date"] and data["received_date"] != p.received_date:
            kwargs["received_date"] = data["received_date"]
        if data["amount"] is not None and data["amount"] != p.amount:
            kwargs["amount"] = data["amount"]
        for name in ("method", "purpose"):
            if data[name]:
                kwargs[name] = data[name]
        for name in ("reference", "comment"):
            if data[name] != getattr(p, name):
                kwargs[name] = data[name]
        if data["profile"]:
            kwargs["profile"] = get_object_or_404(StudentBillingProfile, pk=data["profile"])
        if data["allocations"] is not None:
            kwargs["allocations"] = data["allocations"]
        return kwargs


class CreatedAtForm(forms.Form):
    created_at = forms.DateTimeField(label="Дата и время создания записи",
                                     widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    reason = forms.CharField(label="Причина", widget=forms.Textarea(attrs={"rows": 2}))


class VoidForm(forms.Form):
    confirm = forms.BooleanField(label="Подтверждаю аннулирование этого платежа")
    reason = forms.CharField(label="Причина аннулирования", widget=forms.Textarea(attrs={"rows": 2}))


def _payment(pk) -> StudentPayment:
    return get_object_or_404(
        StudentPayment.objects.select_related("student", "billing_profile__plan", "created_by", "group"),
        pk=pk, billing_profile__isnull=False,
    )


def manage_payment_view(request, pk, admin_site):
    """Страница платежа: данные, распределения, чек, история и действия."""
    if not can_view_money(request.user):
        messages.error(request, "Платежи доступны только бухгалтерии и директору.")
        return redirect("admin:index")
    payment = _payment(pk)
    can_edit = is_billing_accountant(request.user)
    forms_ = {"correct": CorrectForm(payment=payment), "created_at": CreatedAtForm(initial={
        "created_at": payment.created_at.strftime("%Y-%m-%dT%H:%M")}), "void": VoidForm()}
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "correct":
                form = forms_["correct"] = CorrectForm(request.POST, payment=payment)
                if form.is_valid():
                    result = corrections.correct_payment(payment, actor=request.user, **form.service_kwargs())
                    if result["changed"]:
                        messages.success(request, "Платёж исправлен: " + ", ".join(result["changed"]) + ".")
                        for w in result["warnings"]:
                            messages.warning(request, f"Расчётный период {w['period']} ({w['status']}): исправление "
                                                      f"записано в журнал.")
                    else:
                        messages.info(request, "Изменений нет — ничего не сохранено.")
                    return redirect(request.path)
            elif action == "created_at":
                form = forms_["created_at"] = CreatedAtForm(request.POST)
                if form.is_valid():
                    corrections.correct_created_at(payment, actor=request.user, **form.cleaned_data)
                    messages.success(request, "Дата создания записи исправлена.")
                    return redirect(request.path)
            elif action == "void":
                form = forms_["void"] = VoidForm(request.POST)
                if form.is_valid():
                    if payment.kind == StudentPayment.Kind.REFUND:
                        payments.reverse_refund(payment, actor=request.user, reason=form.cleaned_data["reason"])
                    else:
                        payments.reverse_payment(payment, actor=request.user, reason=form.cleaned_data["reason"])
                    messages.success(request, f"Платёж №{payment.pk} аннулирован, чек аннулирован.")
                    return redirect(request.path)
            elif action == "reprint":
                receipt = get_object_or_404(Receipt, payment=payment)
                receipts.mark_printed(receipt, actor=request.user)
                response = HttpResponse(render_receipt_pdf(receipt), content_type="application/pdf")
                response["Content-Disposition"] = f'inline; filename="receipt-{receipt.number}.pdf"'
                return response
        except BillingError as exc:
            messages.error(request, exc.message)
            return redirect(request.path)
    receipt = Receipt.objects.filter(payment=payment).first()
    context = {
        **admin_site.each_context(request), "title": f"Платёж №{payment.pk}", "payment": payment,
        "receipt": receipt, "receipt_rows": receipt_rows(receipt) if receipt else [],
        "allocations": PaymentAllocation.objects.filter(payment=payment).select_related("invoice").order_by("pk"),
        "history": corrections.payment_history(payment), "forms": forms_, "can_edit": can_edit,
        "is_void": payment.status == StudentPayment.Status.VOID,
        "list_url": reverse("admin:accounting_studentpayment_changelist"),
    }
    return render(request, "admin/billing/manage_payment.html", context)
