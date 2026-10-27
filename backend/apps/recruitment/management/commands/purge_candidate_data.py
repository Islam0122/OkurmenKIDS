"""Удаление персональных данных кандидатов по сроку хранения.

    python manage.py purge_candidate_data            # показать, кого затронет
    python manage.py purge_candidate_data --apply    # удалить
    python manage.py purge_candidate_data --days 180 --apply

Затрагиваются только кандидаты без найма и без действующих откликов, по
которым ничего не происходило дольше срока (`RECRUITMENT_RETENTION_DAYS`).
Отклики, этапы и даты остаются для отчётов; ФИО, контакты, анкета, письмо,
резюме и заметки стираются (apps.recruitment.services.intake.erase).
"""
from django.core.management.base import BaseCommand

from apps.recruitment.services import intake
from apps.recruitment.services.common import RecruitmentError


class Command(BaseCommand):
    help = "Удалить персональные данные кандидатов, срок хранения которых истёк."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=None, help="Срок хранения, дней (по умолчанию из настроек).")
        parser.add_argument("--apply", action="store_true", help="Удалить (без флага — только показать).")

    def handle(self, *args, days=None, apply=False, **options):
        candidates = list(intake.retention_candidates(days))
        if not apply:
            self.stdout.write(f"Срок хранения истёк у {len(candidates)} кандидатов. Запустите с --apply, чтобы удалить.")
            return
        erased = 0
        for candidate in candidates:
            try:
                intake.erase(candidate, None, "Истёк срок хранения данных")
                erased += 1
            except RecruitmentError as exc:
                self.stderr.write(f"#{candidate.pk}: {exc.message}")
        self.stdout.write(self.style.SUCCESS(f"Персональные данные удалены: {erased}."))
