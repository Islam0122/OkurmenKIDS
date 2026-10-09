"""Read-only report on how complete the trainer history is.

Lists lessons that count for no trainer — no stored `Lesson.teacher` and no
trainer assignment covering their date (legacy data the 0023 migration could
not attribute without guessing) — and programs without an open assignment.
Nothing is changed: the safe fix for a listed lesson is to set its trainer by
hand (admin → Занятия → «Тренер»), after checking who actually taught it.
"""
from django.core.management.base import BaseCommand
from django.db.models import Exists, OuterRef, Q

from apps.academy.models import GroupTeacher, Lesson, TrainerAssignment


class Command(BaseCommand):
    help = "Show lessons and programs whose trainer can't be determined from the history (read only)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50, help="How many lessons to list (default 50).")

    def handle(self, *args, limit, **options):
        covering = TrainerAssignment.objects.filter(
            program_id=OuterRef("group_teacher_id"), start_date__lte=OuterRef("date"),
        ).filter(Q(end_date__isnull=True) | Q(end_date__gt=OuterRef("date")))
        orphans = (
            Lesson.objects.filter(teacher__isnull=True).exclude(Exists(covering))
            .select_related("group").order_by("group__name", "date")
        )
        total = orphans.count()
        self.stdout.write(f"Занятий без определимого тренера: {total}")
        for lesson in orphans[:limit]:
            self.stdout.write(f"  #{lesson.pk} {lesson.group.name} {lesson.date:%d.%m.%Y} №{lesson.lesson_number} ({lesson.get_status_display()})")
        if total > limit:
            self.stdout.write(f"  … и ещё {total - limit}")

        no_open = GroupTeacher.objects.filter(is_active=True).exclude(
            Exists(TrainerAssignment.objects.filter(program_id=OuterRef("pk"), end_date__isnull=True))
        )
        self.stdout.write(f"Активных программ без текущего назначения: {no_open.count()}")
        for program in no_open.select_related("group", "teacher__user")[:limit]:
            self.stdout.write(f"  программа #{program.pk}: {program}")
