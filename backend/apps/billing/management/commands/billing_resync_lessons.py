"""Досчитать в учебные месяцы проведённые уроки, которые не были обработаны.

    python manage.py billing_resync_lessons --dry-run      # показать, сколько уроков не засчитано
    python manage.py billing_resync_lessons [--profile ID]

Нужен для договоров, оформленных до исправления: уроки, проведённые с даты
начала договора до его оформления, не попадали в учебный месяц («IT 0 из 12»
при посещениях). Правила те же, что при проведении урока (приоритетный
предмет, членство в группе на дату урока, правило пропусков тарифа, даты
договора). Посещаемость, тарифы, суммы уже выставленных начислений и платежи
не меняются; уже списанные уроки не дублируются; повторный запуск ничего не
меняет. Новые начисления создаются по обычным правилам перехода месяцев.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.billing.models import StudentBillingProfile
from apps.billing.services.lessons import lesson_breakdown, sync_profile_history


class Command(BaseCommand):
    help = "Списать в учебные месяцы проведённые, но не обработанные уроки (идемпотентно)."

    def add_arguments(self, parser):
        parser.add_argument("--profile", type=int, help="Только этот договор.")
        parser.add_argument("--dry-run", action="store_true", help="Только показать.")

    def handle(self, *args, **opts):
        profiles = StudentBillingProfile.objects.exclude(status=StudentBillingProfile.Status.INACTIVE).select_related(
            "student", "plan").order_by("pk")
        if opts["profile"]:
            profiles = profiles.filter(pk=opts["profile"])
        total = 0
        for profile in profiles:
            missing = lesson_breakdown(profile)["totals"].get("not_processed", 0)
            if not missing:
                continue
            if opts["dry_run"]:
                self.stdout.write(f"#{profile.pk} {profile.student}: не засчитано уроков — {missing}")
                total += missing
                continue
            with transaction.atomic():
                consumed = sync_profile_history(profile)["consumed"]
            total += consumed
            self.stdout.write(f"#{profile.pk} {profile.student}: засчитано уроков — {consumed}")
        verb = "Не засчитано" if opts["dry_run"] else "Засчитано"
        self.stdout.write(self.style.SUCCESS(f"{verb} уроков всего: {total}"))
