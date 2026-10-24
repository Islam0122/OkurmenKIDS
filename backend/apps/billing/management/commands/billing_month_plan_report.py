"""Отчёт по планам стоимости учебных месяцев (только чтение, dry-run).

По каждому договору по программе: итоговая стоимость, стандартная, скидка,
Σ выставленных начислений, прогноз оставшихся месяцев (по плану договора или
прежнему правилу), есть ли план и совпадает ли его сумма с итоговой. В
`mismatches` — договоры, у которых начисления + прогноз ≠ итоговой стоимости
или сумма плана ≠ итоговой: их бухгалтер исправляет вручную (план месяцев
с причиной, корректировка начислений). Ничего не меняет.

    manage.py billing_month_plan_report            # только несоответствия
    manage.py billing_month_plan_report --all      # все договоры по программе
"""
import json
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.billing.models import StudentBillingProfile
from apps.billing.services.contracts import payment_schedule


class Command(BaseCommand):
    help = "Договоры, у которых сумма месячных начислений не соответствует итоговой цене (только чтение)."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Показать все договоры по программе.")

    def handle(self, *args, **options):
        rows, mismatches = [], []
        profiles = (StudentBillingProfile.objects.filter(duration_months__isnull=False)
                    .select_related("student", "plan").prefetch_related("month_prices").order_by("pk"))
        for profile in profiles:
            schedule = payment_schedule(profile)
            if schedule is None:
                continue
            plan_total = sum((r.amount for r in profile.month_prices.all()), Decimal("0")) if profile.month_plan_mode else None
            issues = list(schedule["issues"])
            if plan_total is not None and plan_total != profile.final_course_price:
                issues.append(f"Сумма плана месяцев {plan_total} ≠ итоговой стоимости {profile.final_course_price}.")
            row = {
                "profile": profile.pk, "student": str(profile.student), "plan": profile.plan.name,
                "status": profile.status, "payment_mode": profile.payment_mode,
                "month_plan_mode": profile.month_plan_mode or "EVEN (прежнее правило)",
                "standard_course_price": str(profile.standard_course_price),
                "final_course_price": str(profile.final_course_price), "discount": str(profile.discount_amount),
                "invoiced": str(schedule["invoiced"]), "projected": str(schedule["projected"]),
                "plan_total": None if plan_total is None else str(plan_total),
                "months": [{"month": m["month_number"], "state": m["state"], "amount": str(m["amount"]),
                            "standard_price": None if m.get("standard_price") is None else str(m["standard_price"])}
                           for m in schedule["months"]],
                "issues": issues,
            }
            if issues:
                mismatches.append(row)
            if options["all"]:
                rows.append(row)
        report = {"dry_run": True, "contracts": profiles.count(), "mismatches": mismatches}
        if options["all"]:
            report["all"] = rows
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
