"""Django Admin → Оплата обучения → «Неправильные данные».

Страница поиска ошибочных финансовых записей (платежи, чеки, начисления,
брони) и их исправления в два шага: форма → проверка «было / станет» с
причиной и предупреждением о влиянии на долг, аванс и отчёты → «Сохранить
исправление». Открытие страницы или формы ничего не меняет. Аннулирование —
отдельное действие с подтверждением (сторно / VOID, ничего не удаляется,
повторно — запрещено).

Доступ — только с разрешением `billing.correct_financial_records`
(суперпользователь — по политике Django, у него все разрешения). Проверка —
в каждом представлении, а сами изменения выполняют сервисы с их собственной
проверкой прав, блокировками и журналом аудита; дополнительно каждое
исправление записывается в журнал как `admin_financial_correction`.
"""
from __future__ import annotations

from decimal import Decimal

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.accounting.models import PayrollAuditLog, StudentPayment
from apps.accounting.services import audit

from .admin_views import CorrectForm
from .models import Invoice, Receipt, Reservation, ReservationAllocation, StudentBillingProfile
from .services import BillingError, corrections, invoices, payments, record_corrections, reservations

PERMISSION = "billing.correct_financial_records"
IMPACT = ("Исправление сразу меняет задолженность, свободный аванс, статусы начислений и финансовые отчёты "
          "(поступления — по дате денег, начисления — по периоду). Платёж и чек не создаются заново; "
          "старые значения сохраняются в журнале.")
JOURNAL_ACTIONS = ("admin_financial_correction", "billing_payment_correct", "billing_payment_reverse",
                   "billing_refund_reverse", "billing_invoice_correct", "billing_invoice_period", "billing_invoice_move",
                   "billing_invoice_void", "billing_reservation_update", "billing_reservation_transfer",
                   "billing_reservation_allocation", "billing_reservation_cancel", "billing_reservation_payment_void",
                   "billing_receipt_update", "billing_receipt_reissue", "billing_receipt_cancel")


def allowed(user) -> bool:
    return bool(user and user.is_active and user.has_perm(PERMISSION))


def _guard(request):
    if not allowed(request.user):
        raise PermissionDenied("Нужно разрешение «Исправление неправильных финансовых данных».")


def _context(request, admin_site, **extra):
    return {**admin_site.each_context(request), "title": "Неправильные данные",
            "home": reverse("admin:billing_financialcorrection_changelist"), **extra}


def _log(actor, instance, operation: str, *, old, new, reason: str, related: dict):
    audit.log(actor, instance, "admin_financial_correction",
              old=old, new={**new, "operation": operation, "related": related}, reason=reason)


# ---------------------------------------------------------------------------
# Поиск
# ---------------------------------------------------------------------------

class SearchForm(forms.Form):
    kind = forms.ChoiceField(label="Что искать", required=False, choices=[
        ("", "Всё"), ("payments", "Платежи и чеки"), ("invoices", "Начисления"), ("reservations", "Брони")])
    student = forms.CharField(label="Студент", required=False)
    number = forms.CharField(label="№ платежа, чека или начисления", required=False)
    received_from = forms.DateField(label="Поступление с", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    received_to = forms.DateField(label="по", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    period_from = forms.DateField(label="Период начисления с", required=False,
                                  widget=forms.DateInput(attrs={"type": "date"}))
    period_to = forms.DateField(label="по", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    amount = forms.DecimalField(label="Сумма", required=False, max_digits=14, decimal_places=2)
    status = forms.CharField(label="Статус", required=False, help_text="confirmed / void, OPEN / PAID / OVERDUE / VOID, "
                                                                       "PENDING / PAID / CANCELLED")


def _student_q(prefix: str, text: str) -> Q:
    q = Q()
    for part in text.split():
        q &= Q(**{f"{prefix}first_name__icontains": part}) | Q(**{f"{prefix}last_name__icontains": part})
    return q


def search(data: dict) -> dict:
    kind, student, number = data.get("kind") or "", (data.get("student") or "").strip(), (data.get("number") or "").strip()
    found = {"payments": [], "invoices": [], "reservations": []}
    if kind in ("", "payments"):
        qs = StudentPayment.objects.filter(billing_profile__isnull=False).select_related("student", "receipt")
        if student:
            qs = qs.filter(_student_q("student__", student))
        if number:
            term = number.lstrip("№#")
            qs = qs.filter(Q(receipt__number__icontains=term) | Q(reference__icontains=term)
                           | (Q(pk=int(term)) if term.isdigit() else Q(pk__in=[])))
        if data.get("received_from"):
            qs = qs.filter(received_date__gte=data["received_from"])
        if data.get("received_to"):
            qs = qs.filter(received_date__lte=data["received_to"])
        if data.get("amount") is not None:
            qs = qs.filter(amount=data["amount"])
        if data.get("status"):
            qs = qs.filter(status=data["status"])
        found["payments"] = list(qs.order_by("-received_date", "-pk")[:100])
    if kind in ("", "invoices"):
        qs = Invoice.objects.select_related("profile__student", "package")
        if student:
            qs = qs.filter(_student_q("profile__student__", student))
        if number:
            qs = qs.filter(number__icontains=number)
        if data.get("period_from"):
            qs = qs.filter(period_date__gte=data["period_from"])
        if data.get("period_to"):
            qs = qs.filter(period_date__lte=data["period_to"])
        if data.get("amount") is not None:
            qs = qs.filter(amount=data["amount"])
        if data.get("status"):
            qs = qs.filter(status=data["status"])
        found["invoices"] = list(qs.order_by("-period_date", "-pk")[:100])
    if kind in ("", "reservations"):
        qs = Reservation.objects.select_related("profile__student", "payment")
        if student:
            qs = qs.filter(_student_q("profile__student__", student))
        if number:
            qs = qs.filter(Q(payment__receipt__number__icontains=number)
                           | (Q(payment_id=int(number)) if number.isdigit() else Q(pk__in=[])))
        if data.get("amount") is not None:
            qs = qs.filter(expected_amount=data["amount"])
        if data.get("status"):
            qs = qs.filter(status=data["status"])
        found["reservations"] = list(qs.order_by("-pk")[:100])
    return found


def index_view(request, admin_site):
    _guard(request)
    form = SearchForm(request.GET or None)
    results = search(form.cleaned_data) if request.GET and form.is_valid() else None
    return render(request, "admin/billing/corrections.html",
                  _context(request, admin_site, mode="search", form=form, results=results))


# ---------------------------------------------------------------------------
# Исправление: форма → проверка «было / станет» → сохранение
# ---------------------------------------------------------------------------

class InvoiceForm(forms.Form):
    amount = forms.DecimalField(label="Сумма начисления", required=False, max_digits=14, decimal_places=2,
                                min_value=Decimal("0"))
    due_date = forms.DateField(label="Срок оплаты (дата)", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    due_lesson = forms.IntegerField(label="Срок оплаты (урок месяца №)", required=False, min_value=1)
    period_date = forms.DateField(label="Период начисления", required=False,
                                  widget=forms.DateInput(attrs={"type": "date"}))
    profile = forms.IntegerField(label="Перенести на договор (id)", required=False,
                                 help_text="Только для не начатого и не оплаченного начисления.")
    note = forms.CharField(label="Примечание", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    reason = forms.CharField(label="Причина исправления", widget=forms.Textarea(attrs={"rows": 2}))


class ReservationForm(forms.Form):
    expected_amount = forms.DecimalField(label="Сумма брони (неоплаченной)", required=False, max_digits=14,
                                         decimal_places=2, min_value=Decimal("0.01"))
    reserved_until = forms.DateField(label="Бронь до", required=False, widget=forms.DateInput(attrs={"type": "date"}))
    paid_date = forms.DateField(label="Дата оплаты брони (дата поступления денег)", required=False,
                                widget=forms.DateInput(attrs={"type": "date"}))
    paid_amount = forms.DecimalField(label="Сумма оплаты брони", required=False, max_digits=14, decimal_places=2,
                                     min_value=Decimal("0.01"))
    profile = forms.IntegerField(label="Перенести на договор (id)", required=False)
    allocation = forms.ChoiceField(label="Условие зачёта брони (договор)", required=False,
                                   choices=[("", "— не менять —"), *ReservationAllocation.choices])
    reason = forms.CharField(label="Причина исправления", widget=forms.Textarea(attrs={"rows": 2}))


def _fmt(value):
    if value in (None, ""):
        return "—"
    return str(value)


def _payment_changes(payment, kwargs) -> list[tuple]:
    labels = {"received_date": "Дата поступления", "amount": "Сумма", "method": "Способ оплаты",
              "reference": "Документ", "comment": "Комментарий", "purpose": "Назначение"}
    rows = [(labels[k], _fmt(getattr(payment, k)), _fmt(v)) for k, v in kwargs.items() if k in labels]
    if "profile" in kwargs:
        rows.append(("Договор / студент", f"#{payment.billing_profile_id} · {payment.student}",
                     f"#{kwargs['profile'].pk} · {kwargs['profile'].student}"))
    if "allocations" in kwargs:
        current = ", ".join(f"{a.invoice.number}={a.amount}" for a in
                            payment.billing_allocations.filter(status="ACTIVE").select_related("invoice")) or "—"
        rows.append(("Распределение", current, ", ".join(f"{i.number}={a}" for i, a in kwargs["allocations"]) or "—"))
    return rows


def _invoice_changes(invoice, data) -> tuple[list[tuple], dict]:
    rows, kwargs = [], {}
    for field, label in (("amount", "Сумма"), ("due_date", "Срок (дата)"), ("due_lesson", "Срок (урок №)"),
                         ("period_date", "Период начисления")):
        value = data.get(field)
        if value not in (None, "") and value != getattr(invoice, field):
            rows.append((label, _fmt(getattr(invoice, field)), _fmt(value)))
            kwargs[field] = value
    note = (data.get("note") or "").strip()
    if note and note != invoice.snapshot.get("note", ""):
        rows.append(("Примечание", _fmt(invoice.snapshot.get("note")), note))
        kwargs["note"] = note
    if data.get("profile") and data["profile"] != invoice.profile_id:
        target = get_object_or_404(StudentBillingProfile.objects.select_related("student"), pk=data["profile"])
        rows.append(("Договор", f"#{invoice.profile_id} · {invoice.profile.student}", f"#{target.pk} · {target.student}"))
        kwargs["profile"] = target
    return rows, kwargs


def _reservation_changes(reservation, data) -> tuple[list[tuple], dict]:
    rows, kwargs = [], {}
    if data.get("expected_amount") is not None and data["expected_amount"] != reservation.expected_amount:
        rows.append(("Сумма брони", _fmt(reservation.expected_amount), _fmt(data["expected_amount"])))
        kwargs["expected_amount"] = data["expected_amount"]
    if data.get("reserved_until") and data["reserved_until"] != reservation.reserved_until:
        rows.append(("Бронь до", _fmt(reservation.reserved_until), _fmt(data["reserved_until"])))
        kwargs["reserved_until"] = data["reserved_until"]
    payment = reservation.payment
    if data.get("paid_date") and payment and data["paid_date"] != payment.received_date:
        rows.append(("Дата оплаты брони", _fmt(payment.received_date), _fmt(data["paid_date"])))
        kwargs["paid_date"] = data["paid_date"]
    if data.get("paid_amount") is not None and payment and data["paid_amount"] != payment.amount:
        rows.append(("Сумма оплаты брони", _fmt(payment.amount), _fmt(data["paid_amount"])))
        kwargs["paid_amount"] = data["paid_amount"]
    if data.get("profile") and data["profile"] != reservation.profile_id:
        target = get_object_or_404(StudentBillingProfile.objects.select_related("student"), pk=data["profile"])
        rows.append(("Договор / студент", f"#{reservation.profile_id} · {reservation.profile.student}",
                     f"#{target.pk} · {target.student}"))
        kwargs["profile"] = target
    if data.get("allocation") and data["allocation"] != reservation.profile.reservation_allocation:
        rows.append(("Условие зачёта брони", reservation.profile.get_reservation_allocation_display(),
                     dict(ReservationAllocation.choices)[data["allocation"]]))
        kwargs["allocation"] = data["allocation"]
    return rows, kwargs


def _apply_payment(request, payment, kwargs, reason):
    result = corrections.correct_payment(payment, actor=request.user, reason=reason, **kwargs)
    return result["changed"]


def _apply_invoice(request, invoice, kwargs, reason):
    if "profile" in kwargs:
        if len(kwargs) > 1:
            raise BillingError("Перенос на другой договор — отдельным исправлением, без других изменений.",
                               code="invalid")
        created = record_corrections.move_invoice(invoice, actor=request.user, profile=kwargs["profile"], reason=reason)
        return [f"перенесено: {created.number}"]
    return record_corrections.correct_invoice(invoice, actor=request.user, reason=reason, **kwargs)["changed"]


def _apply_reservation(request, reservation, kwargs, reason):
    done = []
    with transaction.atomic():
        if "expected_amount" in kwargs or "reserved_until" in kwargs:
            reservations.update_reservation(reservation, actor=request.user, reason=reason,
                                            expected_amount=kwargs.get("expected_amount"),
                                            reserved_until=kwargs.get("reserved_until"))
            done.append("бронь")
        if "paid_date" in kwargs or "paid_amount" in kwargs:
            corrections.correct_payment(reservation.payment, actor=request.user, reason=reason,
                                        received_date=kwargs.get("paid_date"), amount=kwargs.get("paid_amount"))
            done.append("оплата брони")
        if "allocation" in kwargs:
            record_corrections.change_reservation_allocation(reservation.profile, actor=request.user,
                                                             mode=kwargs["allocation"], reason=reason)
            done.append("условие зачёта")
        if "profile" in kwargs:
            record_corrections.transfer_reservation(reservation, actor=request.user, profile=kwargs["profile"],
                                                    reason=reason)
            done.append("перенос")
    return done


ENTITIES = {
    "payment": (lambda pk: get_object_or_404(StudentPayment.objects.select_related("student", "billing_profile"),
                                             pk=pk, billing_profile__isnull=False), "Платёж"),
    "invoice": (lambda pk: get_object_or_404(Invoice.objects.select_related("profile__student", "package"), pk=pk),
                "Начисление"),
    "reservation": (lambda pk: get_object_or_404(Reservation.objects.select_related("profile__student", "payment"),
                                                 pk=pk), "Бронь"),
}


def _related(kind, obj) -> dict:
    if kind == "payment":
        receipt = Receipt.objects.filter(payment=obj).first()
        return {"payment": obj.pk, "receipt": receipt.number if receipt else None,
                "invoices": list(obj.billing_allocations.values_list("invoice__number", flat=True))}
    if kind == "invoice":
        return {"invoice": obj.number, "profile": obj.profile_id,
                "payments": list(obj.allocations.values_list("payment_id", flat=True))}
    return {"reservation": obj.pk, "profile": obj.profile_id, "payment": obj.payment_id}


def correct_view(request, kind, pk, admin_site):
    """Шаг 1 — форма; шаг 2 (`step=review`) — «было / станет» и предупреждение;
    шаг 3 (`step=confirm`) — сохранение сервисом. «Отмена» — назад к поиску."""
    _guard(request)
    if kind not in ENTITIES:
        raise PermissionDenied
    loader, title = ENTITIES[kind]
    obj = loader(pk)
    if kind == "payment":
        form = CorrectForm(request.POST or None, payment=obj)
    elif kind == "invoice":
        form = InvoiceForm(request.POST or None, initial={"amount": obj.amount, "due_date": obj.due_date,
                                                          "due_lesson": obj.due_lesson, "period_date": obj.period_date,
                                                          "note": obj.snapshot.get("note", "")})
    else:
        form = ReservationForm(request.POST or None, initial={
            "expected_amount": obj.expected_amount, "reserved_until": obj.reserved_until,
            "paid_date": obj.payment.received_date if obj.payment_id else None,
            "paid_amount": obj.payment.amount if obj.payment_id else None,
            "allocation": obj.profile.reservation_allocation})
    step, changes = "form", []
    if request.method == "POST" and form.is_valid():
        reason = form.cleaned_data["reason"].strip()
        try:
            if kind == "payment":
                kwargs = form.service_kwargs()
                kwargs.pop("reason", None)
                kwargs.pop("confirm_closed_period", None)
                changes = _payment_changes(obj, kwargs)
                kwargs["confirm_closed_period"] = form.cleaned_data["confirm_closed_period"]
            elif kind == "invoice":
                changes, kwargs = _invoice_changes(obj, form.cleaned_data)
            else:
                changes, kwargs = _reservation_changes(obj, form.cleaned_data)
            if not changes:
                messages.info(request, "Изменений нет — ничего не сохранено.")
            elif request.POST.get("step") == "confirm":
                apply = {"payment": _apply_payment, "invoice": _apply_invoice, "reservation": _apply_reservation}[kind]
                with transaction.atomic():
                    done = apply(request, obj, kwargs, reason)
                    _log(request.user, obj, "correct", reason=reason, related=_related(kind, obj),
                         old={label: old for label, old, _new in changes},
                         new={label: new for label, _old, new in changes} | {"applied": done})
                messages.success(request, f"{title} исправлен(о): " + ", ".join(label for label, *_ in changes) + ".")
                return redirect(reverse("admin:billing_financialcorrection_changelist") + f"?number={_number(kind, obj)}")
            else:
                step = "review"
        except BillingError as exc:
            messages.error(request, exc.message)
    return render(request, "admin/billing/corrections.html", _context(
        request, admin_site, mode="correct", step=step, kind=kind, obj=obj, entity=title, form=form,
        changes=changes, impact=IMPACT))


def _number(kind, obj) -> str:
    if kind == "invoice":
        return obj.number or ""
    if kind == "payment":
        return str(obj.pk)
    return str(obj.payment_id or "")


# ---------------------------------------------------------------------------
# Аннулирование ошибочной операции
# ---------------------------------------------------------------------------

class VoidConfirmForm(forms.Form):
    confirm = forms.BooleanField(label="Подтверждаю аннулирование этой операции")
    reason = forms.CharField(label="Причина", widget=forms.Textarea(attrs={"rows": 2}))


def void_view(request, kind, pk, admin_site):
    _guard(request)
    if kind not in ENTITIES:
        raise PermissionDenied
    loader, title = ENTITIES[kind]
    obj = loader(pk)
    form = VoidConfirmForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        reason = form.cleaned_data["reason"].strip()
        try:
            with transaction.atomic():
                related = _related(kind, obj)
                if kind == "payment":
                    if obj.kind == StudentPayment.Kind.REFUND:
                        payments.reverse_refund(obj, actor=request.user, reason=reason)
                    else:
                        payments.reverse_payment(obj, actor=request.user, reason=reason)
                elif kind == "invoice":
                    invoices.void_invoice(obj, actor=request.user, reason=reason)
                else:
                    if obj.status == Reservation.Status.CANCELLED:
                        raise BillingError("Бронь уже отменена.", code="bad_status")
                    if obj.payment_id and obj.payment.status == StudentPayment.Status.CONFIRMED:
                        payments.reverse_payment(obj.payment, actor=request.user, reason=f"Ошибочная бронь: {reason}")
                        obj.refresh_from_db()
                    reservations.cancel_reservation(obj, actor=request.user, reason=reason)
                _log(request.user, obj, "void", old={"status": getattr(obj, "status", None)},
                     new={"status": "VOID/CANCELLED"}, reason=reason, related=related)
            messages.success(request, f"{title} аннулирован(а). Записи сохранены, расчёты пересчитаны.")
            return redirect("admin:billing_financialcorrection_changelist")
        except BillingError as exc:
            messages.error(request, exc.message)
    return render(request, "admin/billing/corrections.html", _context(
        request, admin_site, mode="void", kind=kind, obj=obj, entity=title, form=form, impact=IMPACT))


def journal_view(request, admin_site):
    """Журнал исправлений (только чтение)."""
    _guard(request)
    rows = (PayrollAuditLog.objects.filter(action__in=JOURNAL_ACTIONS).select_related("actor")
            .order_by("-created_at", "-pk")[:300])
    return render(request, "admin/billing/corrections.html", _context(request, admin_site, mode="journal", rows=rows))
